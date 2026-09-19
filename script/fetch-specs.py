#!/usr/bin/env python3
"""
fetch-specs.py - 把本规范集合（AGENTS_COMMON.adoc + specs/）批量取到本地副本。

定位：
  规范常部署于外网、网络可能不佳，AGENTS_COMMON.adoc「加载方式」建议先把入口与其 specs/
  取到本地副本再读取。本脚本就是那个"取"的抓手：**一次运行把本次会话要用的规范全部取全**，
  目标项目无需自己拼文件清单、也无需逐条下载。

  文件清单**从入口自身解析**（解析 AGENTS_COMMON.adoc 加载调度器里登记的 specs/... 条目），
  故新增一份规范时**不需要改本脚本**、也不会漏取（手工清单的典型失效正是"漏了 specs/"）。

  副本**默认落在共享缓存**（见下「共享缓存」），不在每个项目里各存一份。

用法（在目标项目根目录执行，入口名随平台而异、只给脚本名即可）：
  fetch-specs                          # 取到共享缓存（默认；不在当前项目里落副本）
  fetch-specs --local                  # 取到 <当前工作目录>/<DEFAULT_OUT>/（项目内副本）
  fetch-specs --local --out tmp/specs  # 项目内副本换落点（相对当前工作目录）
  fetch-specs --cache-dir <目录>       # 共享缓存换落点（显式指定优先）
  fetch-specs --base <URL>             # 换规范来源（默认 https://agent.c332030.com，同源镜像可用）
  fetch-specs --force                  # 忽略本地副本、强制重取（需最新规范时用）
  fetch-specs --list                   # 只打印将要取的文件清单，不下载

环境变量：
  AGENT_SPECS_BASE   规范来源地址，等价于 --base（默认取仓库站点）
  AGENT_SPECS_CACHE  共享缓存落点，等价于 --cache-dir（显式参数优先）

共享缓存（默认行为，推荐；理由与放弃的备选做法见下）：
  - 落点：平台用户级缓存目录（见 `shared_cache_dir`），按平台取**该平台公认的缓存位置**；
  - 目的：同一台机器上的**所有项目共用一份**——同一个文件不因项目数而下载多遍，缓存
    **跨项目复用**（项目一多，逐项目下载是纯重复流量与重复等待）；
  - 缓存内容按来源地址分目录（见 `cache_slot_dir`）：换过 `--base` 取到的不同来源副本
    互不覆盖，也不会被后续运行静默改写；
  - 缓存**只进不出**：本脚本不删除缓存里的任何文件（含换源留下的旧副本），要清理由人来做
    （清理属不可逆操作，见 specs/core/execution.adoc「破坏性操作」）；
  - 明确不缓存的两类（有意如此，不当缺陷）：`--base` 指向**本机**时（服务端内容可能每次
    都在变，缓存会给出过期副本）、以及 `--local/--out` 指定的项目内落点（临时产物语义、
    按项目清理）。

行为与副作用：
  - 只写「落点目录」（共享缓存落点，或 `--local` 时当前工作目录下的落点），不写项目里其他位置；
  - 默认**增量**：本地已有且非空的文件跳过，只补缺失项（想刷新用 `--force`）；
  - 退出码：0 成功；1 有文件没取到（清单同时打印失败项）；2 参数或前置条件错误；
  - 网络请求带超时（见 `TIMEOUT_SECONDS`）、失败重试一次；
  - 并发受限（见 `DEFAULT_WORKERS`），不把对端打满。

安全保证：
  - 只读远端、只写落点目录内：`--local` 落点必须位于当前工作目录之下（拒绝 `--out ../x`
    一类越界）；共享缓存落点只接受平台缓存目录**之下**的路径（拒绝借 `--cache-dir` 写到
    任意位置），两处落点互不越界；
  - 不删除任何既有文件（含落点目录里的多余文件）——清理走项目的清理脚本。

已知限制：
  - 缓存不做过期与重新校验：远端规范更新后，默认的增量语义仍会跳过已有的那份，需要最新
    内容须显式 `--force`（放弃"按时间过期"是因为它会把"取到旧副本"变成间歇性故障，
    排查成本更高）。
"""

import argparse
import concurrent.futures
import http.client
import os
import re
import sys
import urllib.parse
import urllib.request

DEFAULT_BASE = "https://agent.c332030.com"
# 项目内落点目录（相对调用方的工作目录，仅 --local 时用）；docstring 按常量名引用、不抄字面值
DEFAULT_OUT = "tmp/agent-specs"
# 共享缓存目录名：POSIX 落在 $XDG_CACHE_HOME 下、Windows 落在 %LOCALAPPDATA%\Cache 下
CACHE_APP_DIR = "agent-specs"
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
        description="把 agent 规范集合（AGENTS_COMMON.adoc + specs/）取到本地副本",
    )
    parser.add_argument("--base",
                        default=os.environ.get("AGENT_SPECS_BASE", DEFAULT_BASE),
                        help="规范来源地址（默认 https://agent.c332030.com）")
    parser.add_argument("--local", action="store_true",
                        help="落点取当前项目内的 --out（临时产物语义），不写共享缓存")
    parser.add_argument("--out", default=DEFAULT_OUT,
                        help="项目内落点目录，相对当前工作目录（默认见 DEFAULT_OUT，仅 --local 时用）")
    parser.add_argument("--cache-dir",
                        default=os.environ.get("AGENT_SPECS_CACHE", ""),
                        help="共享缓存落点（默认按平台取用户级缓存目录；仅在不写 --local 时用）")
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
    """项目内落点必须位于当前工作目录之下——只写调用方项目内，不做越界写入。"""
    cwd = os.path.abspath(os.getcwd())
    dest = os.path.abspath(out_dir)
    if dest != cwd and not dest.startswith(cwd + os.sep):
        raise ValueError(f"项目内落点必须位于当前工作目录之下，拒绝: {out_dir} -> {dest}")
    return dest


def shared_cache_dir():
    """平台公认的用户级缓存目录（本机所有项目共用一份副本的最外层落点）。

    取值按各平台自己的约定，不另造一套：POSIX 用 `XDG_CACHE_HOME`、未设时用 `~/.cache`
    （XDG Base Directory Specification）；Windows 用 `LOCALAPPDATA` 下的 `Cache`（Microsoft
    收窄后的 Local 应用数据约定；**不用** `APPDATA` 漫游目录——缓存是机器本地物、不该被同步）。
    两者都取不到（环境变量被清空、也没有家目录）时返回 None，由调用方退回项目内落点。
    """
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        return os.path.join(base, "Cache") if base else None
    base = os.environ.get("XDG_CACHE_HOME") or (
        os.path.join(os.path.expanduser("~"), ".cache") if os.path.expanduser("~") else None)
    return base or None


def cache_slot_dir(cache_dir, base):
    """某个来源地址在共享缓存里的专属子目录（按来源分槽）。

    换过 `--base` 时（站点挂了换同源镜像、内网走自建地址）取到的副本**内容不同却同名**，
    直接覆盖会把上一来源的副本悄悄改掉、也无法解释"为什么同一份规范这次不一样"。
    故按来源地址分槽：来源相同则命中同一份、跨项目复用，来源不同则各存各的（见
    specs/general/dependency.adoc「构建可重现」——同一清单在任意环境应得到同一份内容）。
    散列按来源地址的规范形态（scheme + 主机 + 端口 + 路径）取值，`https://a.com` 与
    `https://a.com/` 落到同一槽。
    """
    parsed = urllib.parse.urlsplit(base)
    slot = parsed.netloc + parsed.path.rstrip("/")
    slot = re.sub(r"[^A-Za-z0-9._-]+", "_", slot).strip("_") or "default"
    return os.path.join(cache_dir, CACHE_APP_DIR, slot)


def resolve_out_dir(args):
    """定出本次落点。返回 (落点, 是否共享缓存)。

    共享缓存是**默认**：默认落点若取项目内目录，同一台机器上每个项目各存一份、项目一多
    就是同一批文件的重复下载（用户实测诉求：别每个项目都下载一遍）。故默认取平台的用户级
    缓存目录，由所有项目共用；要项目内副本（可随项目一起清理、便于隔离）时显式 `--local`。
    共享缓存不可得（环境变量与家目录都取不到）或来源是本机时退回项目内落点，并在调用方
    打印相应说明——**不静默改变语义**。
    退回的判据是本机来源：`localhost`/回环 IP 上的服务端内容可能每次都在变（本地开发时
    改完即取），拿缓存副本会给出过期内容。
    """
    if args.cache_dir:
        dest = os.path.abspath(os.path.expanduser(args.cache_dir))
        root = shared_cache_dir()
        if not root:
            raise ValueError("本机取不到用户级缓存目录，无法校验 --cache-dir 的落点边界")
        root = os.path.abspath(os.path.expanduser(root))
        if dest != root and not dest.startswith(root + os.sep):
            raise ValueError(
                f"--cache-dir 必须位于本机缓存目录 {root} 之下、不能借用它写到任意位置，拒绝: {dest}")
        return cache_slot_dir(dest, args.base), True
    if args.local:
        return check_out_dir(args.out), False
    if is_local_base(args.base):
        return check_out_dir(args.out), False
    root = shared_cache_dir()
    if not root:
        return check_out_dir(args.out), False
    return cache_slot_dir(root, args.base), True


def is_local_base(base):
    """来源是否指向本机（回环地址/`localhost`）——本机来源不缓存（服务端内容可能每次在变）。"""
    host = (urllib.parse.urlsplit(base).hostname or "").lower()
    return host in ("localhost", "::1") or host.startswith("127.")


def main(argv=None):
    args = parse_args(argv)
    try:
        out_dir, shared = resolve_out_dir(args)
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
        print(f"# 落点: {out_dir}（{'共享缓存' if shared else '项目内副本'}）")
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

    if shared:
        print(f"落点: {out_dir}（共享缓存：本机所有项目共用这一份）")
    else:
        print(f"落点: {out_dir}（项目内副本）")
        if not args.local and not args.cache_dir:
            print("说明: 未落到共享缓存——来源是本机地址，或本机取不到用户级缓存目录"
                  "（可用 --cache-dir 显式指定）", file=sys.stderr)
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
