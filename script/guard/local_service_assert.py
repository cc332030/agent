#!/usr/bin/env python3
"""『用例的请求落点必须被断言限制在本机』的机械断言件（纯 stdlib）。

要治的失效
----------
规范侧已经写了两条：用例只允许在本机跑、**涉及请求服务要有断言把落点限制在本机**
（`specs/general/testing.adoc`「环境与兼容」）。但**"某个地址算不算本机"在代码里是可判定的**
（回环地址集合由 RFC 6890 界定），留在**口头约定**上时，"配置里写了 `localhost` 就算限住了"
照旧通行——而 `localhost` 只是**名字**，落点由解析结果决定；地址被改成内网 IP 或域名时，
没有任何一次检查会发声。

本件把那条判据落成可执行的两半：

* **断言（供用例调用）**：`assert_loopback(host, where)`——把名字解析成地址再判回环，
  **命中即失败**、**解析不出地址同样失败**（不静默跳过）。回环集合含 `127.0.0.0/8`、`::1`、
  IPv4-mapped 的 `::ffff:127.0.0.1`（RFC 6890）。
* **现场自检（供 CI/本地校验调用）**：`check_repo`／`--repo <目录>`——按规则数据
  （`script/specs-rules/local-service.toml` 的 `scan_prefixes`／`scan_exempt_globs`）
  扫发出真实请求的用例文件，报出"没有回环断言"的那些。**扫描面分两片**：
  `scan_*` 指测试源码树、`guard_*` 指本仓库自己的用例树（`script/` 下的 `*_test.py`）——
  两片都要有文件，否则本仓库那一片"一份都没核到"却被记作通过。

**判据的边界**：本件判定的是**文本事实**（这套用例里有没有一条会失败的回环断言）；
"那条断言跑起来到底拦不拦得住"属运行时事实，**以断言件自身的用例为准**
（`script/guard/local_service_assert_test.py`：它在本机跑绿，就是这条判据在本机成立的那一步）。

用法
----
    python3 script/guard/local_service_assert.py --repo .      # 查本仓库
    python3 script/guard/local_service_assert.py --list-files  # 只列出被核的文件

退出码：0 全绿；1 有违规；2 参数或前置条件错误。**一份用例都没核到**按 1 退出——
"核不到"与"核过且通过"必须分得开。
"""

import argparse
import fnmatch
import ipaddress
import os
import re
import socket
import sys
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
RULES_FILE = os.path.join(os.path.dirname(HERE), "specs-rules", "local-service.toml")
RULES_KEY = "local_service_assert"


class LocalServiceViolation(AssertionError):
    """请求落点越出本机（或落点无法判定）——按失败处理，不按通过。"""


def _is_loopback(value) -> bool:
    """`value`（已解析成 IP 的字符串）是否属本机。

    回环集合按 RFC 6890：`127.0.0.0/8`、`::1`；IPv4-mapped 的 `::ffff:127.0.0.1`
    同属回环（`ipaddress` 按地址族判时会把它算作 IPv6，故显式折一次）。
    """
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return False
    if getattr(addr, "ipv4_mapped", None) is not None:
        addr = addr.ipv4_mapped
    return addr.is_loopback


def resolve_addresses(host):
    """把 `host`（名字或 IP 字面量）解析成地址列表。

    解析不出时返回空列表——**调用方须按失败处理**（空结果不等于"没有非回环地址"）。
    """
    host = (host or "").strip().strip("[]")
    if not host:
        return []
    try:
        ipaddress.ip_address(host)
        return [host]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except (OSError, UnicodeError):
        return []
    return sorted({info[4][0] for info in infos})


def assert_loopback(host, where="请求落点"):
    """断言 `host` 的**全部**解析结果都落在本机；任一越界或解析不出即抛出。

    这是"请求服务须有本机断言"那条判据的可执行形态：断言的是**真实请求要用的那一个地址**
    （或被所有请求共用的配置源头），不是配置里写的字面量。
    """
    addresses = resolve_addresses(host)
    if not addresses:
        raise LocalServiceViolation(
            f"{where}：{host!r} 解析不出任何地址——按失败处理（不得静默跳过）")
    outside = [a for a in addresses if not _is_loopback(a)]
    if outside:
        raise LocalServiceViolation(
            f"{where}：{host!r} 解析到 {outside}，不在本机（回环）范围内——"
            "用例只允许在本机跑；连得上目标服务不构成豁免")
    return addresses


def _rules():
    """读规则数据（扫描面与豁免面外置，改口径不动本件）。"""
    try:
        with open(RULES_FILE, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise SystemExit(f"规则数据不可读（{RULES_FILE}）：{exc}——"
                         "『请求落点须被断言限住』的扫描面无从取值，不得当成通过")
    rules = data.get("tokens", {}).get(RULES_KEY)
    if not isinstance(rules, dict):
        raise SystemExit(f"规则数据里没有 `{RULES_KEY}`——该条没有任何机械抓手，不得静默跳过")
    return rules


# 一条会失败的回环断言长什么样：语义取"判定落点是不是回环、不是就让用例红"。
_LOOPBACK_ASSERT = re.compile(
    r"(isLoopbackAddress|assert_loopback|is_loopback|assertLoopback"
    r"|isLoopback[^\n]{0,40}(assertTrue|assertThat|assert)"
    r"|(assertTrue|assertThat|assert)[^\n]{0,40}isLoopback)")


def _requests_service(text, markers, contexters):
    """该文件是否发出真实请求。

    **两点都要命中**才判为请求类用例：① 有请求客户端；② 真有发起动作。
    只认请求客户端时，一个**校验脚本**里出现 `HttpClient` 这类字样（它核的正是"别人的用例
    有没有断言"）就会被当成请求类用例——那是把被核对象与核对工具混为一谈。
    """
    return (any(_hit(text, marker) for marker in markers)
            and any(_hit(text, cue) for cue in contexters))


# 代码行（`fetch(` / `curl ` 这类靠上下文取胜的标记只在这一类行里认）。
# 两种形态：① 命令行（可带缩进与 `$ ` 提示符）；② **调用/赋值的起始位置**——
# 该记号紧跟在 `=`、`(`、`,` 或行首之后（`x = fetch(`、`f = requests.get(`、
# `assert InetAddress...`、`return C.A(`）。于是 `import ...RestTemplate;` 这类
# **只是提到客户端**的行不算、`def _run_fetch(` 这类**定义**也不算。
_CLI_LINE = re.compile(r"^\s*(?:\$\s+)?[\w./-]*(?:curl|wget)\s")


_CALL_SITE = re.compile(r"(?:[=(,]|\breturn|\bassert)")


def _at_call_site(prefix):
    """`marker` 前面那段是不是"调用/赋值的起始位置"（只有行首缩进，或停在 `=`、`(`、`,`、
    `return`、`assert` 之后）。

    `x = fetch(`、`f(requests.get(`、`assert InetAddress…` 是；
    `import …RestTemplate;`、`def _run_fetch(`、正文里的 `说 curl 是` 不是——
    后三种只是**提到**客户端，不构成"发出请求"。
    """
    return bool(_CALL_SITE.search(prefix)) or not prefix.strip()


def _hit(text, marker):
    """`marker` 是否作为**代码记号**出现。

    两条边界：① 字母开头的标记须**自成边界**——`fetch(` 不该命中 `_run_fetch(`；
    ② 靠上下文取胜的标记（`fetch(`、`curl `）只在**代码位置**认：命令行，或调用/赋值
    的起始处（`x = fetch(`、`assert InetAddress…`、`return C.A(`）。于是
    `import …RestTemplate;` 这类**只是提到客户端**的行不算、`def _run_fetch(` 这类定义也不算。

    逐次 `find` 推进、**每次只跳过一个匹配**：同一行里先出现的可能是"只是提到客户端"
    的那个，后出现的才是真正的调用。
    """
    start = 0
    for _ in range(text.count(marker)):
        idx = text.find(marker, start)
        if idx < 0:
            break
        start = idx + 1              # 只看下一个匹配，不当成命中后返回
        before = text[idx - 1] if idx else " "
        if marker[0].isalnum() and (before.isalnum() or before == "_"):
            continue
        line_start = text.rfind("\n", 0, idx) + 1
        line_end = text.find("\n", idx)
        line = text[line_start: line_end if line_end >= 0 else len(text)]
        prefix = line[: idx - line_start]
        # 以标点起头的标记（` requests.get(`、`.execute(`、`curl `）语义就是"调用形态本身"：
        # 逐字出现即是请求路径；**不再走下面那条'代码位置'判据**——词法上没有合适的
        # 前边界可锚（`requests.get(` 前面通常是 `print(` 或 `=`，取 `(`/`=` 一律命中，
        # 于是"只看位置"这一层等于放行全体，请求类文件一个都不被核到）。
        if not marker[0].isalnum():
            return True
        if _CLI_LINE.search(line):
            return True
        if _at_call_site(prefix):
            return True
    return False


def _exempt(rel, globs):
    return any(fnmatch.fnmatch(rel, pat) for pat in globs)


def _scan_files(root, prefixes, suffixes):
    """按扫描面收文件（只走目录、不做模式匹配——扫描面在规则数据里，本件不解析通配）。"""
    found = []
    for prefix in prefixes:
        base = os.path.join(root, *prefix.rstrip("/").split("/"))
        if not os.path.isdir(base):
            continue
        for cur, dirs, names in os.walk(base):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in names:
                if name.endswith(tuple(suffixes)):
                    rel = os.path.relpath(os.path.join(cur, name), root)
                    found.append(rel.replace(os.sep, "/"))
    return sorted(set(found))


def _scan_surfaces(root, rules):
    """两片扫描面各自的文件清单：`[(面名, [相对路径…]), …]`。

    两片各按规则数据里的 `*_prefixes` + `*_suffixes` 收：本仓库的用例只落在
    `guard_*` 那一片，拿 `scan_*` 去收时一份都没有——"核不到"于是混进"核过且通过"。
    """
    return [(name, _scan_files(root, rules.get(f"{name}_prefixes") or [],
                               rules.get(f"{name}_suffixes") or []))
            for name in ("scan", "guard")]


def check_repository(root):
    """返回违规清单（`[(相对路径, 说明)]`）；空清单即全绿。"""
    rules = _rules()
    prefixes = rules.get("scan_prefixes") or []
    suffixes = rules.get("scan_suffixes") or []
    markers = rules.get("request_markers") or []
    contexters = rules.get("request_call_cues") or []
    exempt = rules.get("scan_exempt_globs") or []
    if not prefixes or not suffixes or not markers or not contexters:
        raise SystemExit(f"规则数据 `{RULES_KEY}` 的扫描面或请求标记为空——"
                         "核不到任何用例时不得记作通过")
    files = []
    # 一片都收不到才是"核不到"。单片刻为空不算：某片（如 `src/`）在某个仓库里本就可能
    # 不存在，而另一片刻收得到文件时检查是真跑过的。
    for _name, surfaced in _scan_surfaces(root, rules):
        files.extend(surfaced)
    files = sorted(set(files))
    if not files:
        raise SystemExit("两片扫描面下一份用例文件都没核到——"
                         "'核不到'与'核过且通过'必须分得开")
    problems = []
    for rel in files:
        if _exempt(rel, exempt):
            continue
        with open(os.path.join(root, *rel.split("/")), encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        if not _requests_service(text, markers, contexters):
            continue
        if not _LOOPBACK_ASSERT.search(text):
            problems.append((rel, "发出真实请求，却没有一条会失败的本机（回环）断言——"
                                  "把目标地址换成内网 IP 或域名时这套用例不会红"))
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description="用例请求落点须被断言限制在本机")
    parser.add_argument("--repo", default=".", help="被检查的项目根目录（默认当前目录）")
    parser.add_argument("--list-files", action="store_true", help="只列出被核的用例文件")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.repo)
    if args.list_files:
        for _name, surfaced in _scan_surfaces(root, _rules()):
            for rel in surfaced:
                print(rel)
        return 0
    try:
        problems = check_repository(root)
    except SystemExit as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    for rel, msg in problems:
        print(f"[违规] {rel}: {msg}")
    if problems:
        return 1
    print("OK 请求落点断言检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
