"""
clean-tmp.py - 删除 tmp 目录下文件/目录的安全清理脚本，严格限制不超出 tmp 范围。

定位：
  以「执行命令时的当前工作目录(CWD)」为项目根，清理 CWD 下的 tmp/ 目录。
  因此本脚本无需下载到目标项目，可从任意位置（本地文件、远程 URL、stdin）加载执行，
  在目标项目的根目录下运行即可清理该项目自身的 tmp。

用法（在目标项目根目录执行）:
  python3 clean-tmp.py                仅显示 tmp 内容，不删除（安全模式，见下）
  python3 clean-tmp.py --all          清空 tmp 下全部内容（显式确认）
  python3 clean-tmp.py a.log          删除 tmp/a.log
  python3 clean-tmp.py sub b.log      删除多个

  # 远程加载（Linux/macOS，本仓库脚本的 https 地址替换 <script-url>）：
  curl -s <script-url> | python3 - --all            # 清空
  curl -s <script-url> | python3 - a.log sub/b.log # 删除指定

  # Windows PowerShell（先下载到本地再执行）：
  Invoke-WebRequest <script-url> -OutFile clean-tmp.py
  python3 clean-tmp.py [参数...]

安全保证（远程执行同样生效）：
  - 只操作「CWD 下的 tmp/」，绝不创建 tmp，tmp 不存在即退出；
  - 边界基准用 os.path.abspath（不跟随符号链接），即使 tmp/ 本身是指向外部的符号链接，
    也会被识别为越界而拒绝，防止清空链接指向的外部目录；
  - 每个目标路径经 os.path.realpath 规范化后校验，必须位于 tmp 内；
    任何路径穿越（../、/、绝对路径、符号链接指向 tmp 外）都会被拒绝；
  - 全量清空 tmp 必须显式传入 --all，防止远程执行时无差别误删。
"""
import argparse
import os
import shutil
import sys


def tmp_root() -> str:
    """tmp 路径：以当前工作目录(CWD)为项目根，tmp 在项目根下（不做真实路径解析，防止跟随符号链接）"""
    return os.path.join(os.getcwd(), "tmp")


def expected_root() -> str:
    """
    合法清理范围的边界基准：基于 os.path.abspath，不跟随 tmp/ 自身的符号链接。
    即使 tmp/ 是指向外部的符号链接，abspath 仍保持为「CWD/tmp」，外部真实路径不会被认作合法范围。
    """
    return os.path.abspath(tmp_root())


def resolve_safe(root: str, target: str) -> str:
    """
    将相对 tmp 的路径解析为真实绝对路径，并确保位于合法范围（abspath(tmp)）内；越界则抛错。
    os.path.realpath 会解析 ..、.、绝对路径、符号链接，
    因此任何路径穿越（../ 跳出 tmp、/ 指向根、盘符绝对路径、符号链接指向 tmp 外）都会被识别出越界。
    """
    if not target:
        raise ValueError("空路径被拒绝")
    full = os.path.realpath(os.path.join(root, target))
    boundary = expected_root() + os.sep
    if not full.startswith(boundary):
        raise ValueError(f"路径超出 tmp 范围: '{target}' -> '{full}'")
    return full


def remove_item(full: str) -> None:
    """删除文件或目录（目录递归删除）；符号链接只删链接本身，不跟随"""
    if os.path.isdir(full) and not os.path.islink(full):
        shutil.rmtree(full)
    else:
        os.remove(full)


def main() -> int:
    parser = argparse.ArgumentParser(description="Safe clean tmp (based on CWD)")
    parser.add_argument("--all", action="store_true", help="clear all under tmp (explicit)")
    parser.add_argument("targets", nargs="*", help="relative paths under tmp")
    args = parser.parse_args()

    root = tmp_root()

    # tmp 必须真实存在且非符号链接，否则拒绝操作（防清空符号链接指向的外部目录）
    if os.path.islink(root):
        print(f"REJECTED: tmp is a symbolic link, refuse to operate: {root}")
        return 1
    if not os.path.isdir(root):
        print(f"tmp not exist, nothing to clean: {root}")
        return 0

    if args.all:
        print(f"Cleaning all under: {root}")
        for entry in os.listdir(root):
            remove_item(os.path.join(root, entry))
        print("tmp cleaned.")
        return 0

    if not args.targets:
        print("No target specified. Use --all to clear entire tmp, or list relative paths to delete.")
        return 0

    for target in args.targets:
        try:
            full = resolve_safe(root, target)
        except ValueError as e:
            print(f"REJECTED: {e}")
            continue
        if os.path.lexists(full):
            remove_item(full)
            print(f"deleted: {full}")
        else:
            print(f"skip (not exist): {full}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
