#!/usr/bin/env python3
"""install-line-ending-hook —— 在**目标项目**里安装换行符门禁的提交前钩子。

随规范分发（`script/specs-config.toml` 的 `[scripts].all`），随取规范脚本落到本地副本
根下。规范「提交前与 CI 的换行符门禁」把两道门禁定为 L1；CI 那道由项目自己的流水线
接，本地这道由本件接：**把钩子写进目标项目的 `.githooks/`，再把该项目的 `core.hooksPath`
指过去**。钩子与实扫脚本都从本地副本复制，引用方不必另写实现、也不改只读副本。

为什么钩子放 `.githooks/` 而不是 `.git/hooks/`：`.git/hooks/` 不被 git 跟踪、不可核对；
放在项目内的 `.githooks/` 后可被 review、可被 CI 守卫核齐备。为什么复制扫描器而不直接
引用本地副本：副本只读且按用户家目录定位、同机多项目共用，项目里留一份可核对的副本更稳。

用法（在目标项目根目录执行）：
    python3 <落点>/install-line-ending-hook.py [--repo .] [--source <落点目录>]

退出码：0 安装成功；1 安装不完整（如源文件缺失）；2 前置条件错误（不是 git 工作区 /
git 不可用 / 命令失败）。安装后可用 `git config --local core.hooksPath` 核到 `.githooks`。
"""

import argparse
import os
import shutil
import stat
import subprocess
import sys

HOOK_NAME = "pre-commit"
HOOKS_DIR = ".githooks"
SCAN_NAME = "check_line_ending.py"
SCAN_REL = os.path.join("script", "guard", SCAN_NAME)

HOOK_BODY = """#!/bin/sh
# 提交前换行符门禁（随 agent 规范分发；取值标准见规范 specs/general/encoding.adoc）。
# 由 install-line-ending-hook.py 安装；CI 里另有同名门禁，挡住 --no-verify 绕过者。
repo_root=$(git rev-parse --show-toplevel) || exit 2
exec python3 "$repo_root/script/guard/check_line_ending.py" --repo "$repo_root"
"""

SCAN_BODY = r'''#!/usr/bin/env python3
"""换行符实扫：git 索引侧禁 CRLF/mixed，工作区侧须与 gitattributes 声明一致（纯 stdlib）。

随规范安装到目标项目的 script/guard/ 下。用法：python3 script/guard/check_line_ending.py [--repo .]
退出码：0 合规；1 有违规；2 前置条件错误（不是 git 工作区 / 没核到文件）。
"""

import argparse
import os
import re
import subprocess
import sys

BINARY_ATTR_RE = re.compile(r"\bbinary\b|-text")


def expected_eol(attr):
    if BINARY_ATTR_RE.search(attr):
        return None
    if "eol=crlf" in attr:
        return "crlf"
    if "eol=lf" in attr or "text" in attr:
        return "lf"
    return None


def eol_violations(lines):
    out = []
    for raw in lines:
        line = raw.rstrip("\n")
        if "\t" not in line:
            continue
        meta, path = line.split("\t", 1)
        mi = re.search(r"\bi/(\w+)", meta)
        mw = re.search(r"\bw/(\w+)", meta)
        ma = re.search(r"\battr/(.*)$", meta)
        if not (mi and mw and ma):
            continue
        idx, wt, attr = mi.group(1), mw.group(1), ma.group(1).strip()
        want = expected_eol(attr)
        if want is None:
            continue
        if idx in ("crlf", "mixed"):
            out.append(f"{path}: index EOL is {idx} (committed bytes must be LF)")
        if wt == "mixed" or (wt != "none" and wt != want):
            out.append(f"{path}: worktree EOL is {wt}, expected {want} per {attr}")
    return out


def scan(repo):
    git_path = os.path.join(repo, ".git")
    if not (os.path.isdir(git_path) or os.path.isfile(git_path)):
        raise RuntimeError(f"{repo} is not a git worktree (no .git)")
    try:
        out = subprocess.run(["git", "ls-files", "--eol"], cwd=repo,
                             capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"git ls-files --eol failed: {exc}") from exc
    if out.returncode != 0:
        raise RuntimeError(f"git ls-files --eol returned {out.returncode}: {out.stderr.strip()}")
    lines = [ln for ln in out.stdout.splitlines() if "\t" in ln]
    return len(lines), eol_violations(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="scan git line endings (index + worktree)")
    ap.add_argument("--repo", default=".", help="repository root (default: current dir)")
    args = ap.parse_args(argv)
    try:
        count, violations = scan(args.repo)
    except RuntimeError as exc:
        print(f"line-ending guard precondition failed: {exc}")
        return 2
    if count == 0:
        print("line-ending guard: no file scanned (git ls-files --eol empty) - not a pass")
        return 2
    if violations:
        print(f"line-ending guard: {count} files scanned, {len(violations)} violations:")
        for v in violations:
            print(f"  - {v}")
        return 1
    print(f"line-ending guard: {count} files scanned, all compliant.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def _write(path, body, executable=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)
    if executable:
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def install(repo, source=None):
    """把钩子与实扫脚本装进 repo，并设 core.hooksPath。返回安装摘要。"""
    repo = os.path.abspath(repo)
    git_path = os.path.join(repo, ".git")
    if not (os.path.isdir(git_path) or os.path.isfile(git_path)):
        raise RuntimeError(f"{repo} 不是 git 工作区（缺 .git）——无从安装钩子")
    source = os.path.abspath(source) if source else os.path.dirname(os.path.abspath(__file__))
    # 实扫脚本随 `[scripts].all` 分发时按文件名拍平到落点根（见 fetch-specs 的
    # `target_path`），故先找 `<落点根>/<SCAN_NAME>`；也兼容带 script/guard/ 结构的源目录。
    scan_src = os.path.join(source, SCAN_NAME)
    if not os.path.isfile(scan_src):
        scan_src = os.path.join(source, SCAN_REL)
    if not os.path.isfile(scan_src):
        raise RuntimeError(f"本地副本里缺 {SCAN_NAME}（找的是 {os.path.join(source, SCAN_NAME)} "
                           f"或 {os.path.join(source, SCAN_REL)}）——"
                           "先重跑取规范脚本，补齐安装脚本再装钩子")
    hook = os.path.join(repo, HOOKS_DIR, HOOK_NAME)
    scan_dst = os.path.join(repo, SCAN_REL)
    _write(hook, HOOK_BODY, executable=True)
    with open(scan_src, encoding="utf-8") as fh:
        _write(scan_dst, fh.read(), executable=True)
    try:
        out = subprocess.run(
            ["git", "config", "--local", "core.hooksPath", HOOKS_DIR],
            cwd=repo, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"git config core.hooksPath 执行失败：{exc}") from exc
    if out.returncode != 0:
        raise RuntimeError(f"git config core.hooksPath 返回 {out.returncode}：{out.stderr.strip()}")
    return f"core.hooksPath={HOOKS_DIR}，钩子 {HOOKS_DIR}/{HOOK_NAME}、实扫 {SCAN_REL} 已就位"


def main(argv=None):
    ap = argparse.ArgumentParser(description="在目标项目安装换行符提交前门禁")
    ap.add_argument("--repo", default=".", help="目标项目根（默认当前目录）")
    ap.add_argument("--source", default=None,
                    help="本地副本目录（默认本脚本所在目录；实扫脚本从那里复制）")
    args = ap.parse_args(argv)
    try:
        summary = install(args.repo, args.source)
    except RuntimeError as exc:
        print(f"安装提交前门禁失败：{exc}", file=sys.stderr)
        return 2
    print(f"提交前门禁已安装：{summary}；CI 侧门禁仍须由项目流水线自行接入。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
