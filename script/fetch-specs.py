#!/usr/bin/env python3
"""
fetch-specs.py - 把本规范集合（AGENTS_COMMON.adoc + specs/）批量取到目标项目的临时目录。

定位：
  规范常部署于外网、网络可能不佳，AGENTS_COMMON.adoc「加载方式」建议先把入口与其 specs/
  取到本地副本再读取。本脚本就是那个"取"的抓手：**一次运行把本次会话要用的规范全部取全**，
  目标项目无需自己拼文件清单、也无需逐条下载。

  文件清单**从入口自身解析**（解析 AGENTS_COMMON.adoc 加载调度器里登记的 specs/... 条目），
  故新增一份规范时**不需要改本脚本**、也不会漏取（手工清单的典型失效正是"漏了 specs/"）。

用法（在目标项目根目录执行，入口名随平台而异、只给脚本名即可）：
  fetch-specs                    # 取到 <当前工作目录>/tmp/agent-specs/
  fetch-specs --out tmp/specs    # 换落点（相对当前工作目录）
  fetch-specs --base <URL>       # 换规范来源（默认 https://agent.c332030.com，同源镜像可用）
  fetch-specs --force            # 忽略本地副本、强制重取（需最新规范时用）
  fetch-specs --list             # 只打印将要取的文件清单，不下载

环境变量：
  AGENT_SPECS_BASE  规范来源地址，等价于 --base（默认取仓库站点）

行为与副作用：
  - 只写「当前工作目录下的落点目录」（默认 tmp/，相对调用方的工作目录，不假设脚本自身所在目录）；
  - 默认**增量**：本地已有且非空的文件跳过，只补缺失项（想刷新用 --force）；
  - 退出码：0 成功；1 有文件没取到（清单同时打印失败项）；2 参数或前置条件错误；
  - 网络请求带超时、失败重试一次；并发受限（默认 4），不把对端打满。

安全保证：
  - 只读远端、只写落点目录内；落点必须位于当前工作目录之下（拒绝 --out ../x 一类越界）；
  - 不删除任何既有文件（含落点目录里的多余文件）——清理走项目的清理脚本。
"""
import argparse
import concurrent.futures
import http.client
import os
import re
import sys
import urllib.request

DEFAULT_BASE = "https://agent.c332030.com"
# 入口 + 顶层说明文件；specs/ 下的文件从入口的调度器登记解析得到
MANIFEST_FILE = "AGENTS_COMMON.adoc"
OPTIONAL_FILES = ("README.adoc",)
SPECS_REF_RE = re.compile(r"specs/[A-Za-z0-9_./-]+\.adoc")
TIMEOUT_SECONDS = 30
DEFAULT_WORKERS = 4

EXIT_OK = 0
EXIT_INCOMPLETE = 1
EXIT_USAGE = 2


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="fetch-specs",
        description="把 agent 规范集合（AGENTS_COMMON.adoc + specs/）取到当前项目的临时目录",
    )
    parser.add_argument("--out", default="tmp/agent-specs",
                        help="落点目录，相对当前工作目录（默认 tmp/agent-specs）")
    parser.add_argument("--base",
                        default=os.environ.get("AGENT_SPECS_BASE", DEFAULT_BASE),
                        help="规范来源地址（默认 https://agent.c332030.com）")
    parser.add_argument("--force", action="store_true",
                        help="忽略本地副本、强制重取（需要最新规范时用）")
    parser.add_argument("--list", action="store_true",
                        help="只打印将要取的文件清单，不下载")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help="并发请求数（默认 4）")
    return parser.parse_args(argv)


def fetch_text(base, path):
    """取一份远端文本（UTF-8 解码）。失败抛 OSError。

    **判据不只看状态码**：站点对**任何未命中的路径**都回落成首页 HTML 并返回 200，
    只判状态码会把"不存在的内容"当成取到了（实测：请求本仓库并不存在的 `LICENSE`
    返回 200 + 首页 HTML 18 KB，写进落点后看起来像一份取到的文件）。故文本类产物
    再核一条：**必须是 UTF-8 文本、且不是站点首页**（首页含 SPA 骨架 `<!DOCTYPE html>`
    与站点标题），命中即按取不到处理。
    """
    url = f"{base.rstrip('/')}/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "agent-specs-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        raw = resp.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise OSError(f"不是 UTF-8 文本: {e}") from e
    if text.lstrip().lower().startswith("<!doctype html") or "<html" in text[:200].lower():
        raise OSError("取回的是站点 HTML 页面（该路径在规范站点上不存在，站点回落到首页）")
    return text


def manifest_targets(base):
    """从入口自身解析要取的文件清单。

    入口（AGENTS_COMMON.adoc）的加载调度器**唯一登记**了全部公共规范文件，故清单以它为准：
    新增规范文件时它必然被登记，清单随之自动变全（手工维护清单的失效形态正是漏项）。
    返回 (清单, 缺失的可选文件)；入口文件本身必然在清单里。
    """
    text = fetch_text(base, MANIFEST_FILE)
    specs = sorted(set(SPECS_REF_RE.findall(text)))
    if not specs:
        raise OSError(f"未能在 {MANIFEST_FILE} 中解析出任何 specs/ 清单")
    targets = [MANIFEST_FILE] + list(specs)
    return targets, list(OPTIONAL_FILES)


def target_path(out_dir, rel):
    """落点内路径（相对清单里的仓库路径）。"""
    return os.path.join(out_dir, *rel.split("/"))


def download_one(base, rel, out_dir, force):
    """取一份文件；已存在且非空时默认跳过。返回 (rel, 状态, 说明)。

    **先取到内存、再原子落盘**（临时文件 + `os.replace`）：直接以 `wb` 覆盖既有文件时，
    取到一半失败会把原本完好的本地副本截断成半份——那比"没更新"更坏（副本看起来在、
    内容却是坏的）。原子替换保证**要么整份新内容、要么原样保留旧内容**。
    """
    dest = target_path(out_dir, rel)
    if not force and os.path.isfile(dest) and os.path.getsize(dest) > 0:
        return rel, "skip", "已存在"
    last_err = None
    for attempt in (1, 2):          # 失败重试一次，避免偶发抖动让整批失败
        try:
            data = fetch_text(base, rel).encode("utf-8")
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            tmp = f"{dest}.part"
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, dest)
            return rel, "ok", f"{len(data)} B"
        except OSError as e:        # 网络类错误统一按 OSError 处理
            last_err = e
            try:
                if os.path.exists(f"{dest}.part"):
                    os.remove(f"{dest}.part")
            except OSError:
                pass
            if attempt == 2:
                break
    return rel, "fail", str(last_err)


def check_out_dir(out_dir):
    """落点必须位于当前工作目录之下——本脚本只写调用方项目内，不做越界写入。"""
    cwd = os.path.abspath(os.getcwd())
    dest = os.path.abspath(out_dir)
    if dest != cwd and not dest.startswith(cwd + os.sep):
        raise ValueError(f"落点必须位于当前工作目录之下，拒绝: {out_dir} -> {dest}")
    return dest


def main(argv=None):
    args = parse_args(argv)
    try:
        out_dir = check_out_dir(args.out)
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return EXIT_USAGE

    if args.workers < 1:
        print("错误: --workers 至少为 1", file=sys.stderr)
        return EXIT_USAGE

    base = args.base
    try:
        targets, optional = manifest_targets(base)
    except Exception as e:                                  # noqa: BLE001 - 网络与解析都按同一路径报错
        print(f"错误: 取入口清单失败（{base}/{MANIFEST_FILE}）: {e}", file=sys.stderr)
        return EXIT_USAGE

    # 顶层说明文件是"有则取"：取不到不算失败（仓库未放该文件时站点会回落到首页 HTML，
    # 由 fetch_text 判为取不到并跳过——不得把首页 HTML 当成"取到的说明文件"存进落点）
    if args.list:
        for rel in sorted(targets + optional):
            print(rel)
        print(f"# 共 {len(targets)} 份（必取）+ {len(optional)} 份（有则取），来源 {base}")
        return EXIT_OK

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(download_one, base, rel, out_dir, args.force)
                   for rel in sorted(targets)]
        for fut in concurrent.futures.as_completed(futures):
            results.append(fut.result())
    for rel in optional:
        results.append(download_one(base, rel, out_dir, args.force))

    ok = [r for r in results if r[1] == "ok"]
    skipped = [r for r in results if r[1] == "skip"]
    failed = [r for r in results if r[1] == "fail"]

    print(f"落点: {out_dir}")
    print(f"来源: {base}")
    print(f"结果: 新取 {len(ok)}、已有跳过 {len(skipped)}、失败 {len(failed)}"
          f"（共 {len(results)}）")
    if failed:
        for rel, _, why in failed:
            print(f"  [失败] {rel} -- {why}", file=sys.stderr)
        print("提示: 重试本脚本即可补取缺失项；需要最新内容加 --force。", file=sys.stderr)
        return EXIT_INCOMPLETE
    print("规范已就绪：读取落点下的 AGENTS_COMMON.adoc 及其引用的 specs/ 规范，并持续遵守。")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
