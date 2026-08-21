#!/usr/bin/env python3
"""
检查本规范集合的"规范性"（确定性检查，不依赖 AI）。

检查项：
  1. AsciiDoc 基础语法（块级结构、反引号路径）通过 asciidoctor 验证（若已安装）。
  2. AGENTS.adoc 中登记的所有 `specs/...` 引用文件必须真实存在。
  3. AGENTS.adoc 技术栈层登记的栈文件，必须与 specs/stack/ 实际文件双向一致
     （既不能登记不存在的栈，也不能漏登记已存在的栈）。
  4. 禁止误导入私有强约束约定（如 ctool4j 的 C/IC 前缀、@Bean c 前缀等被当作
     强制规范的表述；中性示例允许保留）。

退出码：0 通过，1 存在不规范项。
"""

import os
import re
import sys
import subprocess

# 兼容 Windows GBK 等非 UTF-8 终端，统一按 UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS_FILE = os.path.join(REPO_ROOT, "AGENTS.adoc")
SPECS_DIR = os.path.join(REPO_ROOT, "specs")

# 误导入的私有约定特征（中性化后应消除）。
# 注意：只针对"被当作强制规范"的强约束表述，中性示例（如 `CList.of(...)` 作为
# 项目自有库举例、CStrUtils 等）允许保留，不在此列。
FORBIDDEN_PATTERNS = [
    (r"\bC[A-Z]\w*\b\s+(class|接口)", "疑似 C 前缀类名/接口误导入"),
    (r"\bIC[A-Z]\w*\b", "疑似 IC 前缀接口误导入"),
    (r"@Bean\s+\w*c\w*", "疑似 @Bean c 前缀私有约定误导入"),
]

errors = []


def err(msg: str, path: str = "", line: int = 0) -> None:
    loc = path
    if line:
        loc = f"{path}:{line}"
    errors.append(f"[不规范] {loc}: {msg}")


def collect_adoc_files():
    result = []
    for root, _, files in os.walk(SPECS_DIR):
        for f in files:
            if f.endswith(".adoc"):
                result.append(os.path.join(root, f))
    result.append(AGENTS_FILE)
    return result


def check_asciidoctor_syntax():
    """若环境有 asciidoctor，做一次语法编译验证。"""
    if subprocess.run(["where", "asciidoctor"], capture_output=True,
                      shell=True).returncode != 0:
        print("提示: 未检测到 asciidoctor，跳过语法编译验证（可使用官方 action 在 CI 中验证）。")
        return
    for f in collect_adoc_files():
        r = subprocess.run(["asciidoctor", "-o", "-", "-a", "outfilesuffix=.html", f],
                           capture_output=True, text=True)
        if r.returncode != 0:
            err(f"asciidoctor 语法错误: {r.stderr.strip()}", f)


def extract_specs_refs(text: str):
    """提取文中 `specs/...` 形式的相对引用，仅保留指向具体文件的路径。

    过滤两类非文件项：
      * 占位符（如 `specs/...`，以 `...` 结尾）；
      * 目录本身（如 `specs/stack/`，以 `/` 结尾）。
    """
    refs = re.findall(r"`(specs/[^`\s]+)`", text)
    return [r for r in refs if not r.endswith("/") and not r.endswith("...")]


def check_refs_exist():
    with open(AGENTS_FILE, encoding="utf-8") as fh:
        text = fh.read()
    refs = extract_specs_refs(text)
    for ref in refs:
        target = os.path.join(REPO_ROOT, ref)
        if not os.path.isfile(target):
            err(f"AGENTS.adoc 引用了不存在的文件: {ref}", "AGENTS.adoc")
        else:
            # 检查被引用文件是否真的存在且可读
            try:
                open(target, encoding="utf-8").close()
            except Exception as e:  # noqa
                err(f"文件无法读取: {ref} ({e})", "AGENTS.adoc")


def check_stack_consistency():
    """AGENTS.adoc 技术栈层登记 vs specs/stack/ 实际文件，双向一致。"""
    with open(AGENTS_FILE, encoding="utf-8") as fh:
        text = fh.read()
    # 提取登记的技术栈文件：specs/stack/xxx.adoc
    registered = set(extract_specs_refs(text))
    registered_stack = {r for r in registered if r.startswith("specs/stack/")}

    actual = set()
    stack_dir = os.path.join(SPECS_DIR, "stack")
    if os.path.isdir(stack_dir):
        for f in os.listdir(stack_dir):
            if f.endswith(".adoc"):
                actual.add(f"specs/stack/{f}")

    # 登记了但不存在（已被上一项覆盖，这里再明确提示栈语义）
    for r in registered_stack - actual:
        err(f"技术栈层登记了不存在的栈文件: {r}", "AGENTS.adoc")
    # 实际存在但未登记（防止漏加载）
    for a in actual - registered_stack:
        err(f"specs/stack/ 存在但未在技术栈层登记（可能漏加载）: {a}", "AGENTS.adoc")


def check_forbidden_patterns():
    for f in collect_adoc_files():
        # AGENTS.adoc 作为加载器允许出现中性示例路径，跳过其私有约定命中
        with open(f, encoding="utf-8") as fh:
            lines = fh.readlines()
        for i, line in enumerate(lines, 1):
            for pat, desc in FORBIDDEN_PATTERNS:
                if re.search(pat, line):
                    err(f"{desc}", f, i)


def main():
    print(f"检查根目录: {REPO_ROOT}")
    check_refs_exist()
    check_stack_consistency()
    check_forbidden_patterns()
    check_asciidoctor_syntax()

    if errors:
        print("\n发现以下规范性问题：")
        for e in errors:
            print("  - " + e)
        sys.exit(1)
    print("OK 规范检查全部通过。")
    sys.exit(0)


if __name__ == "__main__":
    main()
