#!/usr/bin/env python3
"""
fetch-specs.py - 把本规范集合（AGENTS_COMMON.adoc + specs/）批量取到本地副本。

定位：
  规范常部署于外网、网络可能不佳，AGENTS_COMMON.adoc「加载方式」建议先把入口与其 specs/
  取到本地副本再读取。本脚本就是那个"取"的抓手：**一次运行把本次会话要用的规范全部取全**，
  目标项目无需自己拼文件清单、也无需逐条下载。

  文件清单**从入口自身解析**（解析 MANIFEST_FILE 的加载调度器里登记的 specs/... 条目），
  故新增一份规范时**不需要改本脚本**、也不会漏取。取到的副本**落到用户路径下的唯一落点**
  （见下「落点」），不在每个项目里各存一份。

用法（在目标项目根目录执行，入口名随平台而异、只给脚本名即可）：
  fetch-specs                          # 取到落点（用户家目录下的 `<落点父目录>/<落点名>`，见下「落点」）
  fetch-specs --base <URL>             # 换规范来源（默认 https://agent.c332030.com，同源镜像可用）
  fetch-specs --keep                   # 保留本地已有的非空副本（不动已取到的那一份）
  fetch-specs --force                  # 同默认（保留写法，与 --keep 相反）
  fetch-specs --list                   # 只打印将要取的文件清单，不下载

环境变量：
  AGENT_SPECS_BASE   规范来源地址，等价于 --base（默认取仓库站点）

落点（**只有一处**：用户家目录下的 `<落点父目录>/<落点名>`＝`CACHE_HOME_DIR`/`CACHE_APP_DIR`）：
  - 落点**不按平台取目录**：不管什么系统、什么环境都是用户家目录下的这一个路径（用户口径），
    家目录取不到时报错退出、**不静默换地方**——换落点等于让「副本在哪」变成环境相关的事实，
    入口文档写下的那一个路径就与实际的落点对不上了（安装文档只会写这一个落点）；
  - 落点下按来源地址分目录（见 `cache_slot_dir`）——换过 `--base` 取到的不同来源副本互不覆盖；
    且**只进不出**：本脚本不删除落点里的任何文件（含换源留下的旧副本），要清理由人来做
    （清理属不可逆操作，见 specs/core/execution.adoc「破坏性操作」）。
  - **安装脚本自己也落这里**（见 `INSTALL_SCRIPTS`）：规范副本进来源槽，取规范脚本与本脚本
    配套的 `clean_tmp.py` 落**落点根下**——跨来源共用一份，下次重装直接跑落点里的入口，
    不必再手工下载一遍（用户口径：下载的文件一律只落这一个地方）。

  安装侧对落点的说明与"取回/更新"口径（用户读到的落点描述）以安装文档 `INSTALL.adoc`
  「取规范到本地副本」为唯一真源，本节只讲**本脚本自己的取舍**，不复述那几句。

行为与副作用：
  - 只写「落点目录」，不写项目里其他位置；
  - **默认以远程为准**：每份清单内文件都按"取回的字节与本地不同才落盘"核对，远端改过就刷新
    （安装脚本会更新，重复执行安装时须能拿到最新的一份）；取回失败时**保留本地已有的那一份**
    并如实报失败，**不得**把本地副本删掉换成没有；
  - `--keep` 反过来：本地已有且非空即不动（只补缺失项），要最新内容就别加它；
  - 退出码：0 成功；1 有文件没取到（清单同时打印失败项）；2 参数或前置条件错误；
  - 网络请求带超时（见 `TIMEOUT_SECONDS`）、失败重试一次；
  - `--keep` 之外**不做备份**：落点是那份文件自己的位置，被改动过的副本按"以远程为准"覆盖掉
    ——**须留本地改动时用 `--keep`**；
  - 并发受限（见 `DEFAULT_WORKERS`），不把对端打满。

安全保证：
  - **只读远端、只写落点目录内**：落点不是调用方给的路径，而是本脚本按本机用户目录算出来的
    固定位置，故不存在"借参数写到任意位置"的越界面；
  - 不删除任何既有文件（含落点目录里的多余文件）——清理走项目的清理脚本。

已知限制：
  - 不做时间维度的过期判断：判据是**内容**而不是时间——每份文件都先把远端内容取到内存、
    与本地逐字节比较后才决定落不落盘，故没有"本地那份看起来还新、实际已经过期"这条失效；
    代价是每次运行都要把清单内文件取一遍；
  - `--keep` 下本地副本可能落后于远端，此时**以落点里的旧副本为读到的内容**——是否要最新
    由调用方按任务判（安装流程一律按默认的"以远程为准"走）；
  - 内容比对只看字节：远端对同一份规范做格式等价改写（如仅换行/顺序）同样会落盘刷新。
"""

import argparse
import concurrent.futures
import http.client
import os
import re
import stat
import sys
import urllib.parse
import urllib.request

DEFAULT_BASE = "https://agent.c332030.com"
# 落点父目录：用户家目录下的这一层（落点只有这一个，不另按平台取目录）
CACHE_HOME_DIR = ".cache"
# 落点目录名：落点父目录下的这一层（`CACHE_HOME_DIR/CACHE_APP_DIR` 即那条用户路径）
CACHE_APP_DIR = "agent-specs"
# 入口 + 顶层说明文件；specs/ 下的文件从入口的调度器登记解析得到
MANIFEST_FILE = "AGENTS_COMMON.adoc"
OPTIONAL_FILES = ("README.adoc",)
# 与本脚本同处的安装脚本：一并取到落点**根下**（不在来源槽里）——跨来源共用一份。
# 用户口径是"下载的文件一律只落这一个地方"，故下载完就不必再来第二次；
# 薄壳也一并取回：只取逻辑代码时，落点里那份没法直接跑（入口层三件事见 specs/general/script.adoc）。
INSTALL_SCRIPTS = ("script/fetch-specs.py", "script/fetch-specs.sh", "script/fetch-specs.bat",
                   "script/clean_tmp.py")
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
    parser.add_argument("--keep", action="store_true",
                        help="保留本地已有的非空副本（不动已取到的那一份、只补缺失项）")
    parser.add_argument("--force", action="store_true",
                        help="忽略本地副本、强制重取（与 --keep 相反，即默认行为）")
    parser.add_argument("--no-scripts", action="store_true",
                        help="只取规范副本，不把安装脚本（本脚本与其平台入口、清理脚本）取到落点")
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
    """落点内路径（相对清单里的仓库路径）。

    安装脚本那一组的 `rel` 带来源侧的目录（`script/fetch-specs.py`），而落点根下只放
    文件名——见 `fetch_install_scripts`。
    """
    if rel in INSTALL_SCRIPTS:
        return os.path.join(out_dir, os.path.basename(rel))
    return os.path.join(out_dir, *rel.split("/"))


def local_bytes(dest):
    """本地副本的字节（不存在或读不到时按"没有本地副本"处理）。

    读不到**不等于失败**：默认语义是"以远程为准"，读不到就走"本地没有、按新取落盘"，
    报错只该出现在"远端也取不到"那一侧（否则一次权限问题会把可自愈的情形报成失败）。
    """
    try:
        with open(dest, "rb") as fh:
            return fh.read()
    except OSError:
        return b""


def download_one(base, rel, out_dir, keep):
    """取一份文件、按**内容**决定落不落盘。返回 (rel, 状态, 说明)。

    状态取值：`new`（本地没有，新落盘）/ `updated`（远端内容不同，已刷新）/ `same`
    （内容一致，不动）/ `keep`（`--keep` 下本地已有非空，未核内容）/ `fail`。

    **默认以远程为准**（安装脚本会更新，重复执行安装时须能拿到最新的一份）：先把远端内容
    取到内存、与本地逐字节比较，不同才落盘。放弃"本地已有就跳过"是因为它把安装的**结果**
    绑在"本地以前取过什么"上——远端修好了、加了一节规范，重复执行安装仍旧什么都不做
    （本仓库实证：安装规则与抓取脚本本身都在持续更新）。判据因此是**内容**、不是时间。

    **先取到内存、再原子落盘**（临时文件 + `os.replace`）：直接以 `wb` 覆盖既有文件时，
    取到一半失败会把原本完好的本地副本截断成半份——那比"没更新"更坏（副本看起来在、
    内容却是坏的）。原子替换保证**要么整份新内容、要么原样保留旧内容**；再加上"取回失败
    即保留本地那一份、只报失败"，故脚本在任何一次失败下都不会把副本变小或变没。

    **注意原子替换抵不住的那条路径（本仓库实证）**：调用方若用 `fetch-specs > tmp/x.adoc`
    把**落点里的某一份文件**当成命令的 stdout（重定向先清空目标、再执行命令），失败时
    命令没写出新内容——本地那份被 shell 截断成 `0 B`，且 `0 B` 在后续任何 `open()` 里
    都读得通、不像"没有"。这是调用方的用法问题，故：①判据取"本地**存在**"而不是"本地
    非空"（如上），`0 B` 那份同样算"以前取到过的那一份"、失败时照样只报失败、不被当成
    "新取"；②输出里如实写明失败项"本地已有那一份原样保留"，让 `0 B` 的成因一眼可查。

    `--keep` 恢复旧的增量语义（本地已有且非空即不取、只补缺失项）：需要"不动我本地那份"
    时用；要最新内容按默认走即可。
    """
    dest = target_path(out_dir, rel)
    # 本地已有那份（不是"非空"那份）：判据是**本地存在**——空文件同样是"以前取到过的那一份"
    # 的位置，取回失败必须把它保住（否则 `> dest` 截断留下的空文件会被当成"本地没有"，
    # 失败一次即把副本变成 `0 B`，而 `0 B` 的文件在任何 `open()` 里都读得通、不像"没有"）
    before = local_bytes(dest) if os.path.isfile(dest) else None
    if keep and before:
        return rel, "keep", "已存在（--keep）"
    last_err = None
    for attempt in (1, 2):          # 失败重试一次，避免偶发抖动让整批失败
        try:
            data = fetch_text(base, rel).encode("utf-8")
            if before is not None and data == before:
                return rel, "same", f"{len(data)} B（与远程一致）"
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            tmp = f"{dest}.part"
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, dest)
            return rel, ("updated" if before is not None else "new"), f"{len(data)} B"
        except OSError as e:        # 网络类错误统一按 OSError 处理
            last_err = e
            try:
                if os.path.exists(f"{dest}.part"):
                    os.remove(f"{dest}.part")
            except OSError:
                pass
            if attempt == 2:
                break
    return rel, "fail", (f"{last_err}（本地已有那一份原样保留）" if before is not None
                         else str(last_err))


def fetch_install_scripts(base, out_dir, keep):
    """把安装脚本一并取到落点**根下**。返回与 `download_one` 同形的结果列表。

    清单由 `INSTALL_SCRIPTS` 给出（相对来源根，本仓库里就是 `script/` 下那几个），
    落点里**只保留文件名**（`<落点根>/fetch-specs.py`）——目录层级是来源侧的排布，
    照搬会在落点里多出一层 `script/`，且下载来的入口按逻辑代码的相对位置取同目录的
    兄弟文件（见 `fetch-specs.sh` 的 `dirname "$0"`），多一层即整组取不到。
    `--no-scripts` 时调用方不调本函数。语义与规范副本一致：**以远程为准**、失败保留
    本地已有那一份（判据与理由见 `download_one`——同一套"内容不同才落盘 + 原子替换"）。
    """
    results = []
    for rel in INSTALL_SCRIPTS:
        results.append(download_one(base, rel, out_dir, keep))
        _ensure_executable(target_path(out_dir, rel), rel)
    return results


def _ensure_executable(dest, rel):
    """给落点里的入口脚本补上可执行位——**落点里的那份也要能直接跑**。

    本仓库里 `fetch-specs.sh` 带可执行位（见 specs/general/script.adoc「入口脚本须能直接
    执行」），但 HTTP 取回的是字节、不带文件模式，落点里那份默认是 `0644`：安装流程要
    "下次重装直接跑落点里的入口"就会失败。故按扩展名判定（`.sh`/`.py` 补可执行位），
    **只加不减**（已有可执行位不动，也不去"收紧"任何文件的权限）；`.bat` 不需要。
    """
    if not rel.endswith((".sh", ".py")):
        return
    try:
        mode = os.stat(dest).st_mode
        if not mode & stat.S_IXUSR:
            os.chmod(dest, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        pass    # 权限补不上（只读挂载、Windows 等）不该把"取到了文件"报成失败


def install_scripts_dir():
    """安装脚本的落点：落点**根下**（不在来源槽里）。

    规范副本按来源分槽（换过 `--base` 的副本互不覆盖），但安装脚本**跨来源共用一份**
    ——"下载的东西一律只落这一个地方"这条要对得上：同一个人从哪个来源取，落点里都是
    同一份入口，下次重装直接跑它即可（见脚本头部「落点」）。
    """
    return os.path.join(shared_cache_dir(), CACHE_HOME_DIR, CACHE_APP_DIR)


def shared_cache_dir():
    """落点所在的那一层目录：**用户的家目录**。

    **落点只有一处**（用户口径：不管什么系统、什么环境，都是用户家目录下
    `CACHE_HOME_DIR/CACHE_APP_DIR` 那一个路径），故这里不按平台另取一套缓存目录：
    家目录取不到时直接报错，由调用方如实说明卡在哪一步——**不静默换一个落点**：
    换落点等于让"副本在哪"变成环境相关的事实，入口文档写下的那一个路径就与实际的落点
    对不上了，"再运行一次即是更新"也无从核对。

    **判据要判"是不是真的家目录"、不能只判空串**（本仓库实证）：`HOME` 被设成空串时
    `os.path.expanduser("~")` 不会抛错，而是返回文件系统根——只判"空串或未展开的原样 `~`"
    会让副本静默落到根目录下的落点（正是上面要防的"静默换落点"）。故除空串与未展开的
    原样 `~` 外，还须拒掉根目录本身，且要求展开后的路径**确实是一个已存在的目录**
    ——三条任一不成立即按取不到家目录报错，不换地方。
    """
    home = os.path.expanduser("~")
    if not home or home == "~" or os.path.abspath(home) == os.path.abspath(os.sep) \
            or not os.path.isdir(home):
        raise ValueError(
            f"本机取不到用户家目录（展开得到 {home!r}），无法定位用户家目录下的 "
            f"{CACHE_HOME_DIR}/{CACHE_APP_DIR}")
    return home


def cache_slot_dir(home_dir, base):
    """某个来源地址在落点里的专属子目录（按来源分槽）。

    换过 `--base` 时（站点挂了换同源镜像、内网走自建地址）取到的副本**内容不同却同名**，
    直接覆盖会把上一来源的副本悄悄改掉、也无法解释"为什么同一份规范这次不一样"。
    故按来源地址分槽：来源相同则命中同一份、来源不同则各存各的（见
    specs/general/dependency.adoc「构建可重现」——同一清单在任意环境应得到同一份内容）。
    散列按来源地址的规范形态（scheme + 主机 + 端口 + 路径）取值，`https://a.com` 与
    `https://a.com/` 落到同一槽。
    """
    parsed = urllib.parse.urlsplit(base)
    slot = parsed.netloc + parsed.path.rstrip("/")
    slot = re.sub(r"[^A-Za-z0-9._-]+", "_", slot).strip("_") or "default"
    return os.path.join(home_dir, CACHE_HOME_DIR, CACHE_APP_DIR, slot)


def resolve_out_dir(args):
    """定出本次落点：`shared_cache_dir()` 与两个落点常量拼出的那一处，其下按来源分槽。

    **不曾保留的备选做法**（撤掉它们正是本函数的全部内容）：按平台各取一套缓存目录、
    留一批换落点的参数与环境变量、缓存不可得或来源指向本机时自动退回项目内临时目录
    ——每一种都会让"副本在哪"变成环境相关的事实（理由与用户口径见脚本头部「落点」）。
    """
    return cache_slot_dir(shared_cache_dir(), args.base)


def main(argv=None):
    args = parse_args(argv)
    try:
        out_dir = resolve_out_dir(args)
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
        # 同一次失败里也要说清"本地那份还在不在"——只报"取清单失败"时，调用方无法判断
        # 落点里那份是"过期的旧副本"还是"根本没取到过"（见脚本头部「取回失败保留本地那一份」）
        print("说明: 本地落点里已有的那一份**原样保留**（本次未落盘任何文件）；"
              "要确认它是哪一版可对比远端内容，重试本脚本即可补取。", file=sys.stderr)
        return EXIT_USAGE

    # 顶层说明文件是"有则取"：取不到不算失败（仓库未放该文件时站点会回落到首页 HTML，
    # 由 fetch_text 判为取不到并跳过——不得把首页 HTML 当成"取到的说明文件"存进落点）
    if args.list:
        for rel in sorted(targets + optional):
            print(rel)
        print(f"# 共 {len(targets)} 份（必取）+ {len(optional)} 份（有则取），来源 {base}")
        print(f"# 落点: {out_dir}（用户家目录下的 {CACHE_HOME_DIR}/{CACHE_APP_DIR}）")
        scripts_dir = install_scripts_dir()
        for rel in INSTALL_SCRIPTS:
            print(f"{rel}  ->  {target_path(scripts_dir, rel)}")
        print(f"# 安装脚本 {len(INSTALL_SCRIPTS)} 份，落点根下: {scripts_dir}"
              f"{'（--no-scripts 时不取）' if args.no_scripts else ''}")
        return EXIT_OK

    # `--force` 与默认同为"以远程为准"，此处只保留它的写法（与 `--keep` 相反）；
    # `--keep` 下 `download_one` 自己判"本地已有即不动"
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(download_one, base, rel, out_dir, args.keep)
                   for rel in sorted(targets)]
        for fut in concurrent.futures.as_completed(futures):
            results.append(fut.result())
    for rel in optional:
        results.append(download_one(base, rel, out_dir, args.keep))
    # 安装脚本落**落点根下**（不在来源槽里）：这是"下载的文件一律只落这一个地方"里
    # 「安装脚本」那一半——取完规范就不必再手工下载一遍入口（见脚本头部「落点」）。
    # 清单在 `INSTALL_SCRIPTS`，与本脚本同处 `script/`；`--no-scripts` 时整组跳过。
    if not args.no_scripts:
        results.extend(fetch_install_scripts(base, install_scripts_dir(), args.keep))

    fresh = [r for r in results if r[1] == "new"]
    updated = [r for r in results if r[1] == "updated"]
    same = [r for r in results if r[1] == "same"]
    kept = [r for r in results if r[1] == "keep"]
    failed = [r for r in results if r[1] == "fail"]

    print(f"落点: {out_dir}")
    if not args.no_scripts:
        print(f"安装脚本: {install_scripts_dir()}（落点根下）")
    print(f"来源: {base}")
    if args.keep:
        # `--keep` 下"新取"是**没取回来**的那些（本地没有、只留了个空文件占位）：不并进
        # "已有保留"里，否则 `--keep` 结果会把"一份都没拿到"报成"全部保留"（本仓库实证）
        print(f"结果: 已保留 {len(kept) + len(same)}、新取 {len(fresh)}、失败 {len(failed)}"
              f"（共 {len(results)}；--keep：不动已取到的那些）")
        for rel, _, why in fresh:
            print(f"  [新取] {rel} -- {why}（本地原本没有）")
    else:
        print(f"结果: 新取 {len(fresh)}、刷新 {len(updated)}、内容一致 {len(same)}、"
              f"失败 {len(failed)}（共 {len(results)}；以远程为准）")
    if updated:
        for rel, _, why in updated:
            print(f"  [刷新] {rel} -- {why}")
    if failed:
        for rel, _, why in failed:
            print(f"  [失败] {rel} -- {why}", file=sys.stderr)
        print("提示: 失败项**保留本地已有的那一份**（本地原本没有才算真缺）、重试本脚本即可补取；"
              "失败项若显示为 `0 B`，先见脚本头部「原子替换抵不住的那条路径」"
              "（多为把落点里的文件当成命令 stdout 的用法所致）。", file=sys.stderr)
        return EXIT_INCOMPLETE
    if not fresh and not updated and not args.keep:
        print("说明: 清单内文件与远程逐字节一致，落点未改动（判据是内容，不是时间）。")
    if updated:
        print("提示: 本地副本**已被远程内容覆盖**（落点是本脚本自己的那份）——"
              "要留本地改动请先备份、或下次加 --keep。")
    print(f"规范已就绪：读取落点下的 {MANIFEST_FILE} 及其引用的 specs/ 规范，并持续遵守。")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
