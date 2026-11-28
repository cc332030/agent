#!/usr/bin/env python3
"""钉住『提交前换行符门禁』真实存在且会调用实扫脚本（纯 stdlib）。

PR/规范声称「提交前与 CI 两道门禁缺一不可」。CI 那道在 check-specs.yml，
本地这道必须落在受版本控制、可核对的钩子里，否则 `--no-verify` 之外的普通提交
也不会被拦。本守卫核两件事：

* `.githooks/pre-commit` 存在、可执行、且调用 `script/guard/check_line_ending.py`；
* `script/guard/install_git_hooks.py` 存在且会把 `core.hooksPath` 指到 `.githooks`。

这样「有没有提交前门禁、它是否调实扫」可核对，防被删或掏空。

退出码：0 齐备；1 有缺口；2 前置错误。
"""

import argparse
import os
import stat
import sys


def check(repo: str):
    """返回缺口描述列表（空＝齐备）。"""
    problems = []
    hook = os.path.join(repo, ".githooks", "pre-commit")
    installer = os.path.join(repo, "script", "guard", "install_git_hooks.py")

    if not os.path.isfile(hook):
        problems.append("缺 .githooks/pre-commit——提交前门禁没有落点")
    else:
        if not (os.stat(hook).st_mode & stat.S_IXUSR):
            problems.append(".githooks/pre-commit 不可执行——git 不会运行它")
        try:
            body = open(hook, encoding="utf-8").read()
        except OSError as exc:
            problems.append(f".githooks/pre-commit 读不出来：{exc}")
        else:
            if "check_line_ending.py" not in body:
                problems.append(".githooks/pre-commit 没有调用 check_line_ending.py——钩子里核的不是换行符")

    if not os.path.isfile(installer):
        problems.append("缺 script/guard/install_git_hooks.py——没有可核对的钩子安装入口")
    else:
        try:
            body = open(installer, encoding="utf-8").read()
        except OSError as exc:
            problems.append(f"install_git_hooks.py 读不出来：{exc}")
        else:
            if "core.hooksPath" not in body or ".githooks" not in body:
                problems.append("install_git_hooks.py 未把 core.hooksPath 指向 .githooks——装完钩子不生效")
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description="核提交前换行符门禁落点齐备")
    ap.add_argument("--repo", default=".", help="要核对的仓库根（默认当前目录）")
    args = ap.parse_args(argv)
    problems = check(args.repo)
    if problems:
        print("提交前门禁守卫：发现缺口：")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("提交前门禁守卫：钩子与安装入口齐备，且钩子调用行尾实扫。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
