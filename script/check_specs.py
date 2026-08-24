#!/usr/bin/env python3
"""
检查本规范集合的"规范性"（确定性检查，不依赖 AI）。

检查项：
  1. AsciiDoc 基础语法（块级结构、反引号路径）通过 asciidoctor 验证（若已安装）。
  2. 所有 spec 文件（含 AGENTS_COMMON.adoc）中的每个 `specs/...` 引用文件必须真实存在
     （既校验 AGENTS_COMMON.adoc 加载调度器登记/引用的文件，也校验各 spec 文件之间互相
     引用的文件，避免 spec 间交叉引用悬空）。
  3. AGENTS_COMMON.adoc 技术栈层登记的栈文件，必须与 specs/stack/ 实际文件双向一致
     （既不能登记不存在的栈，也不能漏登记已存在的栈）。
  4. 禁止误导入私有强约束约定（如 ctool4j 的 C/IC 前缀、@Bean c 前缀等被当作
     强制规范的表述；中性示例允许保留）。

退出码：0 通过，1 存在不规范项。
"""

import os
import posixpath
import re
import shutil
import sys
import subprocess
import time

# 兼容 Windows GBK 等非 UTF-8 终端，统一按 UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# AGENTS_COMMON.adoc 是通用规范入口，位于仓库根目录（引用方以仓库根为基准解析
# 其内部 specs/... 引用，故下文对其链接解析用 base_dir=""）。
GENERIC_FILE = os.path.join(REPO_ROOT, "AGENTS_COMMON.adoc")
SPECS_DIR = os.path.join(REPO_ROOT, "specs")

# 误导入的私有约定特征（中性化后应消除）。
# 注意：只针对"被当作强制规范"的强约束表述，中性示例（如 `CList.of(...)` 作为
# 项目自有库举例、CStrUtils 等）允许保留，不在此列。
FORBIDDEN_PATTERNS = [
    (r"\bC[A-Z]\w*\b\s+(class|接口)", "疑似 C 前缀类名/接口误导入"),
    (r"\bIC[A-Z]\w*\b", "疑似 IC 前缀接口误导入"),
    (r"@Bean\s+\w*c\w*", "疑似 @Bean c 前缀私有约定误导入"),
]

# 『不保留无用的历史来源声明』的机械抓手：拦截文档里描述"之前是什么、后来改成什么"
# 的变更来源/历史来源陈述（如"早期版本…""原位于…迁移至此…""真正的 agents.md"等）。
# 这类陈述指向旧命名/旧位置，会让引用悬空、且属无用的历史包袱，故一律不得保留。
# 注意：只针对明确的"来源/变更"陈述句式，不得用单个通用词（如"重命名""早期"）
# 以免误伤 git 规范中"重命名必须用 git mv"等中性合理表述。
HISTORICAL_NOTE_PATTERNS = [
    (r"真正的 agents\.md", "指向旧 agents.md 命名的历史来源注记"),
    (r"早期版本", "疑似'早期版本…'历史来源声明"),
    (r"原位于[^，。]*迁移至此", "疑似'原位于…迁移至此'变更来源声明"),
    (r"从通用规范中移除", "疑似规范迁移来源声明"),
    (r"原通用规范内的引用", "疑似旧规范引用迁移来源声明"),
]

errors = []
_phase_start = 0.0


def log(msg: str) -> None:
    """带时间戳的进度日志，立即 flush 避免被缓冲吞掉。"""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def phase(name: str) -> None:
    """标记一个检查阶段的开始。"""
    global _phase_start
    _phase_start = time.time()
    log(f"▶ {name}...")


def phase_done() -> None:
    """标记当前阶段结束，打印耗时。"""
    elapsed = time.time() - _phase_start
    log(f"  ✓ 完成 ({elapsed:.1f}s)")


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
    result.append(GENERIC_FILE)
    # Agent 项目自身规范入口（根目录 AGENTS.adoc，非通用规范，但属本仓库维护范围，一并校验）
    project = os.path.join(REPO_ROOT, "AGENTS.adoc")
    if os.path.isfile(project):
        result.append(project)
    return result


def check_asciidoctor_syntax():
    """若环境有 asciidoctor，做一次语法编译验证。

    用 shutil.which 跨平台检测（Windows `where` / Linux `command -v` 通用），
    避免因命令不存在而误判为"跳过"。CI 中应在运行本脚本前安装 asciidoctor，
    使语法验证真正执行。
    """
    phase("AsciiDoc 语法编译验证")
    if shutil.which("asciidoctor") is None:
        log("  提示: 未检测到 asciidoctor，跳过语法编译验证"
            "（CI 中请先在运行本脚本前安装，见 workflow）。")
        return
    files = collect_adoc_files()
    for i, f in enumerate(files, 1):
        rel = os.path.relpath(f, REPO_ROOT)
        log(f"  [{i}/{len(files)}] 检查 {rel}")
        try:
            r = subprocess.run(
                ["asciidoctor", "-o", "-", "-a", "outfilesuffix=.html", f],
                capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                err(f"asciidoctor 语法错误: {r.stderr.strip()}", f)
        except subprocess.TimeoutExpired:
            err(f"asciidoctor 超时 (30s)，文件可能过大或 asciidoctor 卡死: {os.path.relpath(f, REPO_ROOT)}")
    phase_done()


def _is_placeholder_ref(ref: str) -> bool:
    """判断一个引用是否指向目录 / 占位符 / 尚不存在的示例（非真实具体文件）。"""
    return (ref.endswith("/")
            or ref.endswith("...")
            or "<" in ref or ">" in ref)


def extract_specs_refs(text: str, base_dir: str = ""):
    """提取文中所有指向仓库内具体文件的引用，归一化为从仓库根开始的相对路径。

    `base_dir` 为当前文件所在目录（相对仓库根，POSIX 分隔，根文件为空串），用于
    解析 link: 的相对目标。兼容两类写法：

      * 反引号包裹：`` `specs/general/coding.adoc` ``——按**从仓库根开始**的相对
        路径解析（AGENTS_COMMON.adoc 加载调度 / 正文里惯例用这种写法）。
      * AsciiDoc 超链接：`link:xxx[]`——按**相对当前文件所在目录**解析（IDE 与
        浏览器相对语义一致），目标可能是 `../general/x.adoc` 等含 `../` 的形式。

    排除：目录、占位符、外部 scheme 链接、页内锚点、根绝对路径及越出仓库根的相对路径。
    """
    refs = []
    # 反引号：根目录相对
    for r in re.findall(r"`(specs/[^`\s]+)`", text):
        if _is_placeholder_ref(r):
            continue
        refs.append(r)
    # link:：相对当前文件目录
    for raw in re.findall(r"\blink:([^\[]+)\[", text):
        t = raw.strip()
        if not t or t.startswith("#"):
            continue
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", t):  # 外部 scheme 链接
            continue
        if t.startswith("/"):  # 根绝对路径，格式检查单独报告，此处不参与存在性
            continue
        resolved = posixpath.normpath(posixpath.join(base_dir, t))
        if resolved == ".." or resolved.startswith("../"):
            continue  # 越出仓库根，格式检查单独报告
        if _is_placeholder_ref(resolved):
            continue
        refs.append(resolved)
    # 去重并保持顺序
    seen, out = set(), []
    for r in refs:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def check_refs_exist():
    """校验所有 spec 文件（含 AGENTS_COMMON.adoc）中的 `specs/...` 引用真实存在。

    覆盖两类引用：
      * AGENTS_COMMON.adoc 加载调度器登记/引用的文件；
      * 各 spec 文件之间互相引用的文件（此前只查 AGENTS_COMMON.adoc，
        会漏掉 spec 间交叉引用悬空，如 java-testing.adoc 引用已不存在的
        specs/stack/testing.adoc）。
    """
    phase("引用文件存在性检查")
    files = collect_adoc_files()
    for i, f in enumerate(files, 1):
        rel = os.path.relpath(f, REPO_ROOT)
        # AGENTS_COMMON.adoc 内部 specs/... 约定从仓库根解析（与其实际位于仓库根目录一致）
        if f == GENERIC_FILE:
            base = ""
        else:
            base = os.path.relpath(os.path.dirname(f), REPO_ROOT).replace("\\", "/")
        log(f"  [{i}/{len(files)}] 扫描 {rel}")
        with open(f, encoding="utf-8") as fh:
            text = fh.read()
        refs = extract_specs_refs(text, base)
        for ref in refs:
            target = os.path.join(REPO_ROOT, *ref.split("/"))
            if not os.path.isfile(target):
                err(f"引用了不存在的文件: {ref}", rel)
            else:
                # 检查被引用文件是否真的存在且可读
                try:
                    open(target, encoding="utf-8").close()
                except Exception as e:  # noqa
                    err(f"文件无法读取: {ref} ({e})", rel)
    phase_done()


def check_stack_consistency():
    """AGENTS_COMMON.adoc 技术栈层登记 vs specs/stack/ 实际文件，双向一致。"""
    phase("技术栈一致性检查")
    with open(GENERIC_FILE, encoding="utf-8") as fh:
        text = fh.read()
    # 提取登记的技术栈文件：specs/stack/xxx.adoc（AGENTS_COMMON.adoc 内部 specs/... 从仓库根解析，base_dir=""）
    registered = set(extract_specs_refs(text, ""))
    registered_stack = {r for r in registered if r.startswith("specs/stack/")}

    actual = set()
    stack_dir = os.path.join(SPECS_DIR, "stack")
    if os.path.isdir(stack_dir):
        for f in os.listdir(stack_dir):
            if f.endswith(".adoc"):
                actual.add(f"specs/stack/{f}")

    log(f"  已登记: {len(registered_stack)} 个, 实际存在: {len(actual)} 个")

    # 登记了但不存在（已被上一项覆盖，这里再明确提示栈语义）
    for r in registered_stack - actual:
        err(f"技术栈层登记了不存在的栈文件: {r}", "AGENTS_COMMON.adoc")
    # 实际存在但未登记（防止漏加载）
    for a in actual - registered_stack:
        err(f"specs/stack/ 存在但未在技术栈层登记（可能漏加载）: {a}", "AGENTS_COMMON.adoc")
    phase_done()


def check_forbidden_patterns():
    """检查是否误导入私有强约束约定。"""
    phase("私有约定误导入检查")
    files = collect_adoc_files()
    checked = 0
    total_lines = 0
    for i, f in enumerate(files, 1):
        rel = os.path.relpath(f, REPO_ROOT)
        # AGENTS_COMMON.adoc 作为加载器允许出现中性示例路径，跳过其私有约定命中
        with open(f, encoding="utf-8") as fh:
            lines = fh.readlines()
        total_lines += len(lines)
        found_in_file = False
        for j, line in enumerate(lines, 1):
            for pat, desc in FORBIDDEN_PATTERNS:
                if re.search(pat, line):
                    if not found_in_file:
                        log(f"  [{i}/{len(files)}] 检查 {rel}")
                        found_in_file = True
                    err(f"{desc}", rel, j)
        checked += 1
    log(f"  扫描 {checked} 个文件, 共 {total_lines} 行")
    phase_done()


def check_historical_notes():
    """检查『不保留无用的历史来源声明』是否被遵守（机械抓手）。

    规范要求：不得添加指向旧文件/旧命名/旧位置的历史来源注记（旧文件可能已无法
    追溯、会让引用悬空），引用一律直接指向当前有效的地址。本检查扫描所有规范文件，
    拦截描述"之前是什么、后来改成什么"的变更来源/历史来源陈述（早期版本、原位于…
    迁移至此、真正的 agents.md 等），使该条规范真正有可执行抓手、而非仅靠自觉。
    """
    phase("历史来源声明检查")
    files = collect_adoc_files()
    checked = 0
    for i, f in enumerate(files, 1):
        rel = os.path.relpath(f, REPO_ROOT)
        found_in_file = False
        with open(f, encoding="utf-8") as fh:
            for j, line in enumerate(fh.readlines(), 1):
                for pat, desc in HISTORICAL_NOTE_PATTERNS:
                    if re.search(pat, line):
                        if not found_in_file:
                            log(f"  [{i}/{len(files)}] 检查 {rel}")
                            found_in_file = True
                        err(f"{desc}（『不保留无用的历史来源声明』），应删除或改为直接指向当前有效表述", rel, j)
        checked += 1
    log(f"  扫描 {checked} 个文件")
    phase_done()


def check_link_refs():
    """校验内部文档链接 link: 的格式：须用相对路径，禁止根绝对、禁止越出仓库根。

    背景：AsciiDoc 的 link: 目标既在 IDE 里解析、也在浏览器/站点里解析。若写成
    根绝对路径 `link:/specs/...`，站点按仓库根解析看似正确，但 IDE 会把 `/` 当
    文件系统盘符根解析，导致 IDE 无法跳转；只有写相对当前文件所在目录的相对路径
    （如 `link:../general/x.adoc`）才能让 IDE 与浏览器按同一相对语义一致跳转。
    """
    phase("文档链接格式检查")
    files = collect_adoc_files()
    for i, f in enumerate(files, 1):
        rel = os.path.relpath(f, REPO_ROOT)
        # AGENTS_COMMON.adoc 内部 specs/... 约定从仓库根解析（与其实际位于仓库根目录一致）
        if f == GENERIC_FILE:
            base = ""
        else:
            base = os.path.relpath(os.path.dirname(f), REPO_ROOT).replace("\\", "/")
        found_in_file = False
        with open(f, encoding="utf-8") as fh:
            for j, line in enumerate(fh.readlines(), 1):
                for m in re.finditer(r"\blink:([^\[]+)\[", line):
                    target = m.group(1).strip()
                    # 外部链接（带 scheme）与页内锚点（#...）除外
                    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", target) or target.startswith("#"):
                        continue
                    if not found_in_file:
                        log(f"  [{i}/{len(files)}] 检查 {rel}")
                        found_in_file = True
                    if target.startswith("/"):
                        err("内部链接禁止用根绝对路径（link:/specs/... 在 IDE 中会按文件系统根解析、无法跳转），"
                            f"应改为相对路径（如 link:../specs/...[]），实际为 link:{target}[", rel, j)
                        continue
                    resolved = posixpath.normpath(posixpath.join(base, target))
                    if resolved == ".." or resolved.startswith("../") or os.path.isabs(resolved):
                        err(f"链接目标越出仓库根: link:{target}[", rel, j)
    phase_done()


def check_principle_guard():
    """校验规范"要点防线"仍在（防『定义完整性校验却不执行/被意外误删』）。

    作为逐层防线：一旦根目录 AGENTS.adoc「规范调整」里"调整后须做完整性校验、且含干净
    子 agent 复核、不得只定义不执行"这条底线被删除或改写，check_specs.py 即可通过
    低耗机械校验发现，从而用测试用例钉住这类"难在定稿时发现"的坑。

    判定：根目录 AGENTS.adoc 必须同时含有『子 agent』与『完整性』两个关键词，否则视为
    完整性校验机制被破坏。
    """
    phase("规范要点防线检查")
    path = os.path.join(REPO_ROOT, "AGENTS.adoc")
    rel = os.path.relpath(path, REPO_ROOT).replace("\\", "/")
    if not os.path.isfile(path):
        err("缺少 Agent 项目自身规范入口 AGENTS.adoc，无法核验『调整后须做完整性校验』要点防线是否存在", rel)
        return
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    for key in ("子 agent", "完整性"):
        if key not in text:
            err(f"规范要点防线被破坏：{rel} 缺失『{key}』——『调整规范后必须真正执行完整性校验』这条底线可能被删除/改写", rel)
    phase_done()


def main():
    log(f"检查根目录: {REPO_ROOT}")
    log(f"共发现 {len(collect_adoc_files())} 个 .adoc 文件")
    print()

    check_refs_exist()
    check_link_refs()
    check_stack_consistency()
    check_forbidden_patterns()
    check_historical_notes()
    check_principle_guard()
    check_asciidoctor_syntax()

    print()
    if errors:
        log(f"发现 {len(errors)} 个规范性问题：")
        for e in errors:
            print("  - " + e)
        sys.exit(1)
    log("OK 规范检查全部通过。")
    sys.exit(0)


if __name__ == "__main__":
    main()
