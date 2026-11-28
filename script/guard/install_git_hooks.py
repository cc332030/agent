#!/usr/bin/env python3
"""把仓库内的提交前门禁接进本地 git：设置 core.hooksPath 指向 .githooks/。

为什么需要一步安装：git 不跟踪 `.git/hooks/`，提交前门禁要随仓库分发、可核对，
只能把钩子放进受版本控制的 `.githooks/` 并显式设置 `core.hooksPath`。

用法：
    python3 script/guard/install_git_hooks.py [--repo .]

退出码：0 安装成功；2 前置条件错误（不是 git 工作区 / git 不可用 / 命令失败）。
安装后可用 `git config --local core.hooksPath` 核到 `.githooks`。
"""

import argparse
import os
import subprocess
import sys


def install(repo: str) -> str:
    """设置 core.hooksPath 指向仓库内的 .githooks，返回设置后的值。"""
    git_path = os.path.join(repo, ".git")
    if not (os.path.isdir(git_path) or os.path.isfile(git_path)):
        raise RuntimeError(f"{repo} 不是 git 工作区（缺 .git）——无从安装钩子")
    hook_dir = os.path.join(repo, ".githooks")
    if not os.path.isfile(os.path.join(hook_dir, "pre-commit")):
        raise RuntimeError(f"仓库缺 {hook_dir}/pre-commit——提交前门禁没有落点")
    try:
        out = subprocess.run(
            ["git", "config", "--local", "core.hooksPath", ".githooks"],
            cwd=repo, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"git config core.hooksPath 执行失败：{exc}") from exc
    if out.returncode != 0:
        raise RuntimeError(f"git config core.hooksPath 返回 {out.returncode}：{out.stderr.strip()}")
    return ".githooks"


def main(argv=None):
    ap = argparse.ArgumentParser(description="安装仓库内的提交前换行符门禁（core.hooksPath=.githooks）")
    ap.add_argument("--repo", default=".", help="要安装钩子的仓库根（默认当前目录）")
    args = ap.parse_args(argv)
    try:
        value = install(args.repo)
    except RuntimeError as exc:
        print(f"安装提交前门禁失败：{exc}")
        return 2
    print(f"提交前门禁已安装：core.hooksPath={value}，pre-commit 将在每次提交前核行尾。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
