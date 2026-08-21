"""
clean-tmp.py - 删除 tmp 目录下文件/目录的安全清理脚本，严格限制不超出 tmp 范围。

定位：
  以「执行命令时的当前工作目录(CWD)」为项目根，清理 CWD 下的 tmp/ 目录。
  因此本脚本无需下载到目标项目，可从任意位置（本地文件、远程 URL、stdin）加载执行，
  在目标项目的根目录下运行即可清理该项目自身的 tmp。

用法（在目标项目根目录执行）:
  python clean-tmp.py                清空 tmp 下全部内容
  python clean-tmp.py a.log          删除 tmp/a.log
  python clean-tmp.py sub b.log      删除多个

  # 远程加载（Linux/macOS，本仓库脚本的 https 地址替换 <script-url>）：
  curl -s <script-url> | python3 - [相对tmp的路径...]

  # Windows PowerShell（先下载到本地再执行）：
  Invoke-WebRequest <script-url> -OutFile clean-tmp.py
  python clean-tmp.py [相对tmp的路径...]

说明:
  - 传入参数视为相对 tmp 根目录的路径（如 a.log、sub/b.log）
  - 无参数时清空 tmp 下全部内容
  - 每个目标路径都会拼接到 tmp 根下，经 os.path.realpath 规范化后校验，
    必须位于 tmp 目录内；任何路径穿越（../、/、绝对路径指向 tmp 外、符号链接指向 tmp 外）
    都会被规范化后识别并拒绝，防止误删 tmp 之外的文件
"""
import argparse
import os
import shutil
import sys


def tmp_root() -> str:
    """tmp 根目录：以当前工作目录(CWD)为项目根，tmp 在项目根下"""
    return os.path.join(os.getcwd(), "tmp")


def resolve_safe(root: str, target: str) -> str:
    """
    将相对 tmp 的路径规范化为绝对路径，并确保位于 tmp 内；越界则抛错。
    os.path.realpath 会解析 ..、.、绝对路径、符号链接，
    因此任何路径穿越（如 ../ 跳出 tmp、/ 指向根、盘符绝对路径）都会被规范化后识别出越界。
    """
    if not target:
        raise ValueError("空路径被拒绝")
    full = os.path.realpath(os.path.join(root, target))
    real_root = os.path.realpath(root) + os.sep
    if not full.startswith(real_root):
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
    parser.add_argument("targets", nargs="*", help="relative paths under tmp")
    args = parser.parse_args()

    root = tmp_root()

    if not os.path.isdir(root):
        print(f"tmp not exist, nothing to clean: {root}")
        return 0

    if not args.targets:
        # 无参数：清空 tmp 下全部内容（均为临时产物）
        print(f"Cleaning all under: {root}")
        for entry in os.listdir(root):
            remove_item(os.path.join(root, entry))
        print("tmp cleaned.")
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
