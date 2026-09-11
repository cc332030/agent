#!/usr/bin/env python3
"""
检查本规范集合的"规范性"（确定性检查，不依赖 AI）。

检查项（每项对应一个 check_ 函数，逐条见各函数 docstring 的判定口径）：
  1. 引用存在性：所有 `.adoc` 中的 `specs/...` 引用（反引号按仓库根、`link:` 按相对
     当前文件）都必须指向真实文件，避免规范间交叉引用悬空。
  2. 链接格式：内部 `link:` 须用相对路径，禁止根绝对路径与越出仓库根的写法。
  3. 节名引用存在性：`link:x.adoc[]「节名」` 引用的节必须真实存在，防改名后静默悬空。
  4. 技术栈一致：AGENTS_COMMON.adoc 技术栈层登记与 specs/stack/ 实际文件双向一致。
  5. 调度器登记完整性：被引用的规范文件必须都在加载调度器中登记（登记集合 ⊇ 被引用
     集合），防"只建文件不登记"导致规则实际失效。
  6. 私有约定误导入：禁止把项目私有强约束（C/IC 前缀、@Bean c 前缀等）当作通用规范。
  7. 历史来源声明：禁止指向旧文件/旧命名/旧位置的历史来源注记（会让引用悬空）。
  8. INSTALL 模板：INSTALL.adoc 的 AGENTS.adoc 入口模板代码块须逐字保留（含换行空行）。
  9. 文档注水兜底：只拦机械可判定、必然成立的形态（纯占位段、完全逐字重复段）；
     "是否有价值、是否长篇大论"属语义判断，交人 review，不设字符数阈值以免误伤。
 10. 规范要点防线：根目录 AGENTS.adoc 必须仍含"完整性校验含干净子 agent 复核"底线。
 11. 规范优先级防线：specs/core/priority.adoc 必须仍在，且 L1/L2/L3 分级与最高关注项
     （P1 git mv / P2 完整性校验 / P3 内容不减少）仍存在、仍标为 L1，防被删/降级。
 12. 提示词主侧重与优先级防线：PROMPTS.adoc 登记表 + 各提示词代码块的 `primary` +
     公共片段 `priority-rules` 的 L1/L2/L3 必须一致存在，防侧重/方向被删或降级。
 13. AsciiDoc 语法：有 asciidoctor 时对全部 .adoc 做一次编译验证。

范围：只校验本仓库自己维护的规范、模板与工具（`.adoc` 文本、CI 配置、脚本行为），
**不对引用方项目做任何代码/工作区检查**——引用方只使用公共内容（`AGENTS_COMMON.adoc`
+ `specs/`，可另行下载 `script/clean_tmp.py`），其内部操作在本仓库的校验中不可见。

用法：
  python3 script/check_specs.py             # 阶段级进度 + 错误清单（默认）
  python3 script/check_specs.py --verbose   # 追加逐文件进度（排查某文件时用）
  python3 script/check_specs.py --help

退出码：0 通过，1 存在不规范项。
"""

import argparse
import os
import posixpath
import re
import shutil
import sys
import subprocess

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
# 安装文档（非规范本体，但属本仓库维护范围，且其内代码块模板须逐字保留，一并纳入机械校验）
INSTALL_FILE = os.path.join(REPO_ROOT, "INSTALL.adoc")
# 本仓库自身规范入口（根目录 AGENTS.adoc，非通用规范，但属本仓库维护范围）
PROJECT_FILE = os.path.join(REPO_ROOT, "AGENTS.adoc")

# 公共任务提示词（非规范本体，但属本仓库维护范围）：登记入口、正文目录与公共片段。
# 提示词侧重点错即方向错（后续操作全做错），故对「主侧重 + 优先级」加机械防线，
# 防止调整/去重时把方向性内容删掉或降级；语义是否被削弱仍由人/子 agent 复核承担。
PROMPTS_FILE = os.path.join(REPO_ROOT, "PROMPTS.adoc")
PROMPTS_DIR = os.path.join(REPO_ROOT, "prompts")
COMMON_PROMPT_FILE = os.path.join(PROMPTS_DIR, "_common.txt")

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
    (r"(?:早期版本|之前的版本|原先)", "疑似'早期版本…'历史来源声明"),
    (r"原位于[^，。]*迁移至此", "疑似'原位于…迁移至此'变更来源声明"),
    (r"从通用规范中移除", "疑似规范迁移来源声明"),
    (r"原通用规范内的引用", "疑似旧规范引用迁移来源声明"),
]

errors = []


VERBOSE = False


def log(msg: str) -> None:
    """阶段级进度日志（始终输出）。立即 flush：既要给人看，也可能被 CI 与测试实时捕获。

    不打时间戳：本脚本是纯本地毫秒级校验，时间戳只会淹没真正重要的进度与结论
    （在单元测试输出中尤其明显），对排查没帮助。
    """
    print(msg, flush=True)


def detail(msg: str) -> None:
    """逐文件级进度日志（默认**不输出**，`--verbose` 时输出）。

    默认静默：全量检查会对每个文件逐条打印（26 个文件 × 多项检查），在 CI 日志与
    单元测试输出里数百行噪音会盖住真正有用的信息（进度小结与错误清单）。
    """
    if VERBOSE:
        print(msg, flush=True)


def phase(name: str) -> None:
    """标记一个检查阶段的开始。"""
    log(f"▶ {name}...")


def phase_done() -> None:
    """标记当前阶段结束。"""
    log("  ✓ 完成")


def err(msg: str, path: str = "", line: int = 0) -> None:
    loc = path
    if line:
        loc = f"{path}:{line}"
    errors.append(f"[不规范] {loc}: {msg}")


def collect_adoc_files():
    """收集纳入检查的 .adoc 文件。

    口径：`specs/` 下全部规范文件 + 通用规范入口 `AGENTS_COMMON.adoc` + 项目自身规范
    `AGENTS.adoc` + 安装文档 `INSTALL.adoc`——即"随规范集合维护的全部文档"，
    **不止 specs/ 一个目录**（下文各检查的 docstring 一律以本口径为准）。
    README/PROMPTS 等面向使用者的说明文档不在本集合内（其维护检查见 CI 其余步骤），
    但提示词的**方向性内容**（主侧重/优先级）另由 check_prompts_primary 专门盯住。
    """
    result = []
    for root, _, files in os.walk(SPECS_DIR):
        for f in files:
            if f.endswith(".adoc"):
                result.append(os.path.join(root, f))
    result.append(GENERIC_FILE)
    # Agent 项目自身规范入口（根目录 AGENTS.adoc，非通用规范，但属本仓库维护范围，一并校验）
    if os.path.isfile(PROJECT_FILE):
        result.append(PROJECT_FILE)
    # 安装文档（其内代码块模板逐字保留，纳入机械校验，避免模板被折叠/丢失换行）
    if os.path.isfile(INSTALL_FILE):
        result.append(INSTALL_FILE)
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
        detail(f"  [{i}/{len(files)}] 检查 {rel}")
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


def _ref_base(f: str) -> str:
    """某规范文件内 `link:` 引用的解析基准（相对仓库根目录，根文件为空串）。

    AGENTS_COMMON.adoc 与 INSTALL.adoc、AGENTS.adoc 均位于仓库根，其引用按**从仓库根
    开始**的路径解析（与 AsciiDoc 中根级文件的惯例写法一致）；其余文件按"相对当前文件
    所在目录"解析（与 IDE/浏览器相对语义一致）。注：根文件按仓库根解析时，对同目录文件
    的 `link:README.adoc[]` 这类写法**检查器无法与本文件约定区分**（`README.adoc` 既非
    specs/ 下、也不在检查集合内），故根文件的跨文件引用统一按仓库根基准书写。
    """
    if f in (GENERIC_FILE, INSTALL_FILE, PROJECT_FILE):
        return ""
    return os.path.relpath(os.path.dirname(f), REPO_ROOT).replace("\\", "/")


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
        base = _ref_base(f)
        detail(f"  [{i}/{len(files)}] 检查 {rel}")
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


def check_dispatcher_registry():
    """调度器登记完整性：被引用的规范文件必须都在调度器中登记。

    背景：AGENTS_COMMON.adoc 的加载调度器是规范文件的**唯一登记处**。若某规范
    文件被其他规范引用、却未在调度器登记，按调度器执行时它永远不会被加载，
    其中规则实际失效（如 doc-module.adoc 曾被 doc.adoc / doc-design.adoc /
    doc-lifecycle.adoc 引用但未登记）。本检查用机械方式钉住
    「调度器登记集合 ⊇ 被引用集合」，使『写文件』与『登记调度器』成为同一动作。
    """
    phase("调度器登记完整性检查")
    with open(GENERIC_FILE, encoding="utf-8") as fh:
        registered = set(extract_specs_refs(fh.read(), ""))
    referenced = set()
    for f in collect_adoc_files():
        base = _ref_base(f)
        with open(f, encoding="utf-8") as fh:
            referenced |= set(extract_specs_refs(fh.read(), base))
    missing = sorted(referenced - registered)
    log(f"  调度器登记 {len(registered)} 个, 被引用 {len(referenced)} 个")
    for m in missing:
        err(f"规范文件被引用但未在加载调度器登记（不会被加载、其中规则实际失效）: {m}",
            "AGENTS_COMMON.adoc")
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
                        detail(f"  [{i}/{len(files)}] 检查 {rel}")
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
                            detail(f"  [{i}/{len(files)}] 检查 {rel}")
                            found_in_file = True
                        err(f"{desc}（『不保留无用的历史来源声明』），应删除或改为直接指向当前有效表述", rel, j)
        checked += 1
    log(f"  扫描 {checked} 个文件")
    phase_done()


def check_install_codeblock():
    """校验 INSTALL.adoc 中 AGENTS.adoc 入口模板代码块逐字保留（机械抓手）。

    背景：AI 读取 INSTALL.adoc 在目标项目创建 AGENTS.adoc 时，若模板代码块内的
    换行/空行被折叠、行被合并，会导致生成文档样式改变。为让『逐字原样保留』成为
    可执行约束而非靠自觉，本检查扫描 INSTALL.adoc 的模板代码块，逐一确认每段必备
    行都各自独立成行（未被合并/折叠），且必备行之间的空行分隔完好。
    """
    phase("INSTALL 入口模板代码块检查")
    if not os.path.isfile(INSTALL_FILE):
        log("  未找到 INSTALL.adoc，跳过")
        phase_done()
        return
    with open(INSTALL_FILE, encoding="utf-8") as fh:
        lines = fh.readlines()

    # 定位模板代码块定界（首个 ``----`` 为开，其后下一个 ``----`` 为闭）
    delim = [i for i, l in enumerate(lines) if l.strip() == "----"]
    if len(delim) < 2:
        err("INSTALL.adoc 未找到完整的模板代码块定界符 `----`（需一对）",
            os.path.relpath(INSTALL_FILE, REPO_ROOT))
        phase_done()
        return
    open_i, close_i = delim[0], delim[1]
    body = lines[open_i + 1:close_i]

    # 必备内容：每行必须各自独立成行（不得与其它行合并/折叠）。
    REQUIRED_LINES = [
        "= Agent 规范入口",
        "本项目的 agent 执行规范入口为：",
        "https://agent.c332030.com/AGENTS_COMMON.adoc",
        "读取该入口及其引用的 specs/ 规范，并持续遵守其全部要求。",
        "规范属强制约束：**开工前必须先读取规范再执行**，不得因未读取/记不全而跳过或放宽任何条款。",
    ]
    found = {s: False for s in REQUIRED_LINES}
    for raw in body:
        line = raw.rstrip("\n").rstrip("\r")
        if line in found:
            found[line] = True
    for s, ok in found.items():
        if not ok:
            err(f"INSTALL.adoc 模板代码块缺失或行被合并/改写：未找到独立成行的『{s}』"
                "（模板须逐字原样保留，不得折叠换行）",
                os.path.relpath(INSTALL_FILE, REPO_ROOT))

    # 必备行之间须有恰当的空行分隔，确保样式不变（防止空行被吞掉导致段落粘连）
    indices = [i for i, raw in enumerate(body) if raw.rstrip("\n\r") in found]
    for a, b in zip(indices, indices[1:]):
        gap = b - a
        # 『入口为：』与 URL 之间、URL 与『读取…』之间需空行，其余相邻段落之间同样应留空行
        if gap < 2:
            prev = body[a].rstrip("\n\r")
            nxt = body[b].rstrip("\n\r")
            err(f"INSTALL.adoc 模板代码块中『{prev}』与『{nxt}』之间缺少空行"
                "（空行被吞会导致样式变化，须逐字保留）",
                os.path.relpath(INSTALL_FILE, REPO_ROOT))
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
        base = _ref_base(f)
        found_in_file = False
        with open(f, encoding="utf-8") as fh:
            for j, line in enumerate(fh.readlines(), 1):
                for m in re.finditer(r"\blink:([^\[]+)\[", line):
                    target = m.group(1).strip()
                    # 外部链接（带 scheme）与页内锚点（#...）除外
                    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", target) or target.startswith("#"):
                        continue
                    if not found_in_file:
                        detail(f"  [{i}/{len(files)}] 检查 {rel}")
                        found_in_file = True
                    if target.startswith("/"):
                        err("内部链接禁止用根绝对路径（link:/specs/... 在 IDE 中会按文件系统根解析、无法跳转），"
                            f"应改为相对路径（如 link:../specs/...[]），实际为 link:{target}[", rel, j)
                        continue
                    resolved = posixpath.normpath(posixpath.join(base, target))
                    if resolved == ".." or resolved.startswith("../") or os.path.isabs(resolved):
                        err(f"链接目标越出仓库根: link:{target}[", rel, j)
    phase_done()


def _collect_section_names(path: str):
    """收集一个 .adoc 文件的所有节标题文本（去掉 `=` 前缀）。

    AsciiDoc 节标题形如 `== 设计文档`、`=== 信息归属（同一信息只写一处）`。
    返回节标题正文集合，并收录别名以便引用方按习惯省略括号说明：
      * 完整标题；
      * 去掉括号后缀的简化名（`信息归属（同一信息只写一处）` → `信息归属`）；
      * 括号内的文字（`分类与懒加载（加载调度器）` → `加载调度器`）。
    `----` 代码块内的行不采集（如 INSTALL.adoc 模板首行 `= Agent 规范入口` 并非节）。
    """
    names = set()
    in_block = False
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip() == "----":
                in_block = not in_block
                continue
            if in_block:
                continue
            m = re.match(r"^(=+)\s+(.+?)\s*$", line)
            if not m:
                continue
            title = m.group(2)
            names.add(title)
            simple = re.sub(r"[（(].*$", "", title).strip()
            if simple:
                names.add(simple)
            for inner in re.findall(r"[（(]([^（）()]+)[）)]", title):
                if inner.strip():
                    names.add(inner.strip())
    return names


def check_section_refs():
    """校验『{文件}「节名」』式引用指向的节真实存在（机械抓手）。

    背景：规范间常以 `link:xxx.adoc[]「某节名」` 形式引用具体小节。文件存在性由
    check_refs_exist 覆盖，但**节名是否真实存在不会被任何检查发现**——某节被改名
    后，其余文件的引用会静默悬空（check_specs.py 原先的检查死角）。本检查按
    `link:<目标>[]「<节名>」` 的写法，解析目标文件、核对节名真实存在，让『节名引用
    不悬空』成为可执行约束，规范改名/重整时自动兜住。

    同一 link 后并列多个「节名」（如 `link:x.adoc[]「A」「B」`）时**逐个校验**。
    仅校验能在仓库内解析、且目标为 .adoc 的引用；占位符/目录/外部链接跳过。
    """
    phase("节名引用存在性检查")
    files = collect_adoc_files()
    checked = 0
    for i, f in enumerate(files, 1):
        rel = os.path.relpath(f, REPO_ROOT)
        base = _ref_base(f)
        found_in_file = False
        with open(f, encoding="utf-8") as fh:
            for j, line in enumerate(fh.readlines(), 1):
                # 匹配 `link:目标[]` 及其后连续出现的「节名」（同一行内，可并列多个）
                for m in re.finditer(r"\blink:([^\[]+)\[\]((?:\s*「[^」]+」)+)", line):
                    target = m.group(1).strip()
                    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", target) or target.startswith(("#", "/")):
                        continue
                    if not target.endswith(".adoc") or _is_placeholder_ref(target):
                        continue
                    resolved = posixpath.normpath(posixpath.join(base, target))
                    if resolved == ".." or resolved.startswith("../"):
                        continue
                    path = os.path.join(REPO_ROOT, *resolved.split("/"))
                    if not os.path.isfile(path):
                        continue  # 文件不存在由 check_refs_exist 报告
                    names = _collect_section_names(path)
                    for sec in re.findall(r"「([^」]+)」", m.group(2)):
                        section = sec.strip()
                        if not found_in_file:
                            detail(f"  [{i}/{len(files)}] 检查 {rel}")
                            found_in_file = True
                        checked += 1
                        simple = re.sub(r"[（(].*$", "", section).strip()
                        if section not in names and simple not in names:
                            err(f"引用了不存在的节名: {resolved}「{section}」"
                                f"（该节可能已改名/删除，须同步更新引用）", rel, j)
    log(f"  校验 {checked} 处节名引用")
    phase_done()


# 『文档不得注水』的机械可判定形态（保守口径，只拦"必然成立"的形态，避免误伤
# 简短但有实质内容的条目——语义判断不在机械检查范围，由人 review 承担）。
# 占位词：整段除它之外没有任何实质内容时，才算"无实质内容的占位段"。
# 判定刻意**不含字符数阈值**——"参考：""内容为：" 这类短引导句是正常文档写法，
# 按字数判注水必然误伤；短不等于水，篇幅问题属语义判断、交人 review。
FILLER_PLACEHOLDER_WORDS = ("此处", "本段", "待补", "待完善", "待补充", "后续补充",
                            "内容同上", "详见上文", "TODO", "略")
FILLER_DUP_MIN_CHARS = 12       # 判重段落的实质字符下限（只滤掉"重复标点/符号行"，短而真实的重复条目仍应报）
FILLER_MIN_SUBSTANCE_CHARS = 4  # 段落"实质字符"下限：低于此值视为格式分隔行（如 `：`、`——`），不判注水
# 承载实质内容的行结构：列表条目、表格行、链接、块属性、注释行
MEANINGFUL_LINE_PAT = re.compile(r"^\s*(?:\*|\d+\.|\||\[|<|link:|include::)")
# 判"是否只剩占位词"时需忽略的标点与格式符
FILLER_NOISE_PAT = re.compile(r"[\s*`\-—、。，,：:；;（）()\[\]\"\'“”~…]")


def _iter_blocks(path: str):
    """按 AsciiDoc 块结构切分正文，逐块产出 (起始行号, 行列表, 是否含承载行)。

    代码块（`----` 定界）内容、节标题与块属性行不计入段落；空行分段。列表/表格等
    结构行归入所在段，并标记该段是否"含承载实质内容的行"——只有**整段都没有承载行**
    时才可能是注水段（避免把正常规则条目误判为注水）。
    """
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()
    in_block = False
    para, start, meaningful = [], 0, False
    for i, raw in enumerate(lines, 1):
        line = raw.rstrip("\n").rstrip("\r")
        if line.strip() == "----":
            in_block = not in_block
            continue
        if in_block:
            continue
        stripped = line.strip()
        if not stripped:
            if para:
                yield start, para, meaningful
                para, start, meaningful = [], 0, False
            continue
        if re.match(r"^=+\s+", stripped) or stripped.startswith(":") or stripped.startswith("["):
            if para:
                yield start, para, meaningful
                para, start, meaningful = [], 0, False
            continue
        if not para:
            start = i
        para.append(line)
        if MEANINGFUL_LINE_PAT.match(line):
            meaningful = True
    if para:
        yield start, para, meaningful


def _para_metrics(para: list) -> tuple:
    """统计段落：去格式符后的实质字符数、条目数、是否含列表标记。"""
    texts, items, has_bullet = set(), 0, False
    for line in para:
        s = line.strip()
        if re.match(r"^\s*(?:[*]|\d+\.)\s+", line):
            has_bullet = True
            items += 1
        norm = FILLER_NOISE_PAT.sub("", s)
        if norm:
            texts.add(norm)
    return len("".join(sorted(texts))), items, has_bullet


def _placeholder_only(text: str) -> bool:
    """整段是否"只剩占位词、没有别的实质内容"。

    去掉占位词与标点、格式符后若不再剩任何字符，即判为占位段（如"此处待补充""（略）"）；
    只要还留有别的字词（"参考：""内容为：""第 3 步：略"）就不算——短引导句与
    "标题词 + 后接内容"都是正常文档写法，机械检查不得误伤。按词长从长到短去除，
    避免先去掉短词（"待补"）导致长词（"待补充"）只被去掉前缀、残留无关字符。
    """
    rest = text
    for word in sorted(FILLER_PLACEHOLDER_WORDS, key=len, reverse=True):
        rest = rest.replace(word, "")
    return FILLER_NOISE_PAT.sub("", rest) == ""


def _substance_chars(text: str) -> int:
    """段落的"实质字符"数（去掉标点/格式符后剩下的字数）。

    用于滤掉纯格式行（如 `：`、`——`、`***`）——它们既非占位也非内容，
    判注水属误报，故低于下限时不参与占位段/重复段判定。
    """
    return len(FILLER_NOISE_PAT.sub("", text))


def check_filler_docs():
    """『文档不得注水』机械兜底（只拦机械可判定、必然成立的形态）。

    背景：规范要求"禁止无意义、划水、凑字数"，若只停留在文档里的要求、无任何抓手，
    则属"定义未执行"。本检查保守地钉住两类必然成立、且不误伤正常内容的形态：
      1) 纯占位段：整段除占位词外无任何实质内容（"此处待补充"这类占位）；
      2) 同段重复：同一文件内出现**完全逐字相同且承载实质内容**的段落（凑数堆砌）。
    "内容是否有价值、是否长篇大论、是否流水账"属语义判断，不作机械判定——交人
    review 承担；机械检查只盯"必然成立"的形态，避免把简短但真实的条目判成注水。
    """
    phase("文档注水检查")
    files = collect_adoc_files()
    for i, f in enumerate(files, 1):
        rel = os.path.relpath(f, REPO_ROOT)
        detail(f"  [{i}/{len(files)}] 检查 {rel}")
        seen_paras = set()
        for lineno, para, meaningful in _iter_blocks(f):
            text = " ".join(p.strip() for p in para).strip()
            # 0) 纯格式行（`：`、`——`、`***` 等）：无实质字符，不判注水（防误报）
            if _substance_chars(text) < FILLER_MIN_SUBSTANCE_CHARS:
                continue
            # 1) 纯占位段：整段无承载行，且除占位词外没有实质内容
            if not meaningful and _placeholder_only(text):
                err(f"疑似注水：无实质内容的占位段『{text[:30]}』"
                    "（『文档不得注水』），补上可核对的实质内容或删除", rel, lineno)
                continue
            # 2) 同段重复：逐字相同且承载实质内容的段落（凑数堆砌）——**对全部段落判重**，
            #    不只判"含列表/表格行"的段落：否则同段重复出现在节标题分隔的两处时会被漏掉
            if _substance_chars(text) >= FILLER_DUP_MIN_CHARS:
                if text in seen_paras:
                    err(f"疑似注水：与上文完全重复的段落『{text[:30]}』"
                        "（『文档不得注水』），合并去重", rel, lineno)
                    continue
                seen_paras.add(text)
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


def check_priority_guard():
    """『规范优先级防线』：最高关注项必须仍在、且仍为最高级（L1）。

    背景：规范已按业界做法（RFC 2119 / ISO shall-should-may / 关键性分级）分为
    L1 强制 / L2 建议 / L3 允许三级，并单列"最高关注项"（不可降级）。最大的风险是
    **重构/去重时把最高关注项删掉或降级**——这正是本仓库发生过的问题（同一最高
    关注项在多处出现被 AI 判为"重复"而合并）。本检查机械钉住：

      * specs/core/priority.adoc 存在（分级与最高关注项的落点）；
      * 三级定义（L1 强制 / L2 建议 / L3 允许）仍存在；
      * 三个最高关注项 P1/P2/P3 仍存在，且其关联的 L1 关键词仍出现；
      * specs/core/execution.adoc 仍保留 `git mv` 铁律（最高关注项 P1 的必加载层落点）。

    只钉"存在性与级别"，不改写内容——语义是否被削弱仍由人/子 agent 复核承担。
    """
    phase("规范优先级防线检查")
    rel_priority = "specs/core/priority.adoc"
    path = os.path.join(REPO_ROOT, rel_priority)
    if not os.path.isfile(path):
        err("缺少规范优先级文件 specs/core/priority.adoc——L1/L2/L3 分级与最高关注项无处定义",
            rel_priority)
        return
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    # 分级定义必须齐全（防只留 L1、删掉 L2/L3 或反之）
    for key in ("L1 强制", "L2 建议", "L3 允许"):
        if key not in text:
            err(f"规范优先级防线被破坏：{rel_priority} 缺失分级定义『{key}』", rel_priority)
    # 最高关注项 P1/P2/P3 必须仍在，且须各自保持"最高/L1"定性
    for pid, name in (("P1", "git mv"), ("P2", "完整性"), ("P3", "内容不得减少")):
        if pid not in text:
            err(f"规范优先级防线被破坏：{rel_priority} 缺失最高关注项 {pid}（{name}）——"
                "最高关注项不得被删除或降级", rel_priority)
        elif "不可降级" not in text:
            err(f"规范优先级防线被破坏：{rel_priority} 缺失『不可降级』声明——"
                "最高关注项须明确只能加强、不得削弱", rel_priority)
    # 最高关注项 P1 的必加载层落点仍须保留 git mv 铁律
    exec_path = os.path.join(REPO_ROOT, "specs/core/execution.adoc")
    if not os.path.isfile(exec_path):
        err("缺少 specs/core/execution.adoc，最高关注项 P1（git mv）的必加载层落点丢失",
            "specs/core/execution.adoc")
    else:
        with open(exec_path, encoding="utf-8") as fh:
            exec_text = fh.read()
        if "git mv" not in exec_text:
            err("规范优先级防线被破坏：specs/core/execution.adoc 缺失 `git mv` 铁律——"
                "最高关注项 P1 的必加载层落点被删除/改写", "specs/core/execution.adoc")
    phase_done()


# 提示词「主侧重（方向前提）」与「优先级规则」的机械防线口径：
#   * 每个提示词的侧重点用一段**块级短语**承载，形如 `**主侧重（…）**：**检查修复问题**——…`；
#     两侧分别锚定「主侧重」标签与「方向」标签，中间即侧重内容本身。
PRIMARY_LABEL = "主侧重"
PRIMARY_LINE = re.compile(
    r"\*\*主侧重[^*]*\*\*\s*[:：]\s*\*\*([^*]+)\*\*[^\n]*方向")
# 登记表侧重列：`| **<侧重>** | 主侧重片段 \`primary\``；侧重内容两侧的引号/星号
# 只为排版强调，比对时统一剥掉，避免"同一侧重、写法不同"被误判为未登记。
PRIMARY_ADOC = re.compile(
    r"\|\s*\*\*([^*|]+?)\*\*\s*\|\s*主侧重片段 `primary`")
# 提示词正文的「主侧重（方向性前提，先读）」段：`**主侧重（…）**：**<侧重>**——…`。
# 用更宽的行内锚点扫描，确保侧重值出现在正文说明段（而非仅在片段占位符里）。
PRIMARY_ANY = re.compile(
    r"\*\*主侧重[^*\n]*\*\*\s*[:：]\s*\*\*([^*|\n]+?)\*\*")


def _normalize_primary(text: str) -> str:
    """归一化侧重方向文本：去掉排版用的引号/星号/空白，便于登记表与正文比对。"""
    return text.strip().strip('"\'“”*').strip()
#   优先级规则归并用语（RFC 2119 / ISO shall-should-may 的对应关系），三级定义缺一即防线被破坏。
PRIORITY_TERMS = {
    "L1": ("必须", "严禁"),
    "L2": ("应当",),
    "L3": ("可以",),
}


def _iter_prompt_files():
    """列出公共任务提示词文档（`prompts/` 下非 `_` 前缀的 .adoc）。"""
    if not os.path.isdir(PROMPTS_DIR):
        return []
    return sorted(os.path.join(PROMPTS_DIR, f)
                  for f in os.listdir(PROMPTS_DIR)
                  if f.endswith(".adoc") and not f.startswith("_"))


def check_prompts_primary():
    """『提示词主侧重与优先级防线』：侧重方向与分级规则不得被删或降级。

    背景：提示词的**侧重点是最核心、方向性的内容**——后续所有操作与要求都依据它，
    方向错了后面全做错。故提示词显式标注「主侧重（方向前提）」并按业界共识
    （RFC 2119 / RFC 8174、ISO/IEC Directives Part 2）引入 L1/L2/L3 优先级，指明
    哪里是重点。本检查机械钉住（调整/去重不得让它们消失或降级）：

      * `PROMPTS.adoc` 登记表仍标注每个提示词的**主侧重**（`| **主侧重** | 主侧重片段 `primary` …`）；
      * 每个提示词代码块内仍注入 `primary`（主侧重）与 `priority-rules`（优先级）片段；
      * 公共片段 `priority-rules` 仍含 L1/L2/L3 三级关键字与 RFC 2119 / ISO 依据；
      * 侧重点与登记表双向一致（防两个提示词的侧重被复制成同一个 = 方向混用）。

    只钉"存在性与一致性"，不改写内容——语义是否被削弱仍由人/子 agent 复核承担。
    """
    phase("提示词主侧重与优先级防线检查")
    rel_prompts = os.path.relpath(PROMPTS_FILE, REPO_ROOT).replace("\\", "/")

    if not os.path.isfile(PROMPTS_FILE):
        err(f"缺少提示词登记入口 {rel_prompts}——提示词的主侧重与优先级无处登记",
            rel_prompts)
        phase_done()
        return
    with open(PROMPTS_FILE, encoding="utf-8") as fh:
        registry_text = fh.read()

    # 登记表须用「主侧重片段 primary」明确标出侧重列（防登记表被改成无方向信息的清单）
    if "主侧重片段 `primary`" not in registry_text:
        err(f"提示词登记表未标注主侧重（缺少『主侧重片段 `primary`』）——"
            "侧重点属方向性内容，登记时不得省略", rel_prompts)

    registered = {}
    for name in PRIMARY_ADOC.findall(registry_text):
        registered[_normalize_primary(name)] = True

    files = _iter_prompt_files()
    if not files:
        err("prompts/ 下未找到任何任务提示词文档（除 `_` 前缀公共片段外）",
            "prompts/")

    primaries = []
    for f in files:
        rel = os.path.relpath(f, REPO_ROOT).replace("\\", "/")
        with open(f, encoding="utf-8") as fh:
            text = fh.read()
        # 1) 侧重方向须显式声明（放在正文最前，含"方向"字样）
        m = PRIMARY_LINE.search(text)
        if not m:
            err("提示词未显式声明『主侧重（方向前提）』——侧重点是最核心、方向性的内容，"
                "不得省去（须形如 `**主侧重（…）**：**<侧重>**——…方向…`）", rel)
            primary = None
        else:
            primary = m.group(1).strip()
            primaries.append(_normalize_primary(primary))
            # 正文说明段的侧重值须与方向性声明一致（防两处侧重写成两个＝方向自相矛盾）
            for other in PRIMARY_ANY.findall(text):
                if _normalize_primary(other) != _normalize_primary(primary) \
                        and _normalize_primary(other) != "本任务唯一主侧重":
                    err(f"提示词内主侧重写法不一致（『{primary}』与『{other.strip()}』）——"
                        "侧重须独此一个方向、不得自相矛盾", rel)
        # 2) 登记表须登记该提示词的侧重，且与正文一致（防同名/防侧重被复制混用）
        if primary is not None and _normalize_primary(primary) not in registered:
            err(f"提示词主侧重『{primary}』未在 {rel_prompts} 登记表中标注"
                "（登记表与正文须一致）", rel_prompts)
        # 3) 代码块内须注入 primary 与 priority-rules 两个公共片段
        for tag in ("primary", "priority-rules"):
            if f"include::_common.txt[tag={tag}]" not in text:
                err(f"提示词代码块未注入公共片段 `{tag}`——"
                    f"{'主侧重（方向）' if tag == 'primary' else '优先级规则'}缺失，"
                    "AI 无法据此判断重点", rel)

    # 4) 侧重方向不得雷同：两个提示词侧重不同（review=检查修复、refactor=重构），
    #    复制成同一个即方向混用。判定用**实际读到的侧重集合**，而非登记表条目数
    #    （登记表有两行、侧重却写成同一个时，条数相同但方向已混用）。
    if len(set(primaries)) < len(primaries):
        err(f"提示词主侧重出现重复：{sorted(set(primaries))}——"
            "各提示词侧重不同、须独立声明，复制成同一个即方向混用", rel_prompts)

    # 5) 公共片段 priority-rules 须仍在，且含三级分级与业界依据
    rel_common = os.path.relpath(COMMON_PROMPT_FILE, REPO_ROOT).replace("\\", "/")
    if not os.path.isfile(COMMON_PROMPT_FILE):
        err(f"缺少提示词公共片段 {rel_common}——优先级规则（L1/L2/L3）无处定义", rel_common)
    else:
        with open(COMMON_PROMPT_FILE, encoding="utf-8") as fh:
            common = fh.read()
        if "tag=priority-rules" not in common.replace("::", "=") and "tag::priority-rules" not in common:
            err(f"公共片段 {rel_common} 缺少 `priority-rules` 片段——"
                "提示词无法引入业界共识的优先级规则", rel_common)
        else:
            block = common.split("tag::priority-rules[]", 1)[-1].split("end::priority-rules[]", 1)[0]
            for level in ("L1 强制", "L2 建议", "L3 允许"):
                if level not in block:
                    err(f"公共片段 `priority-rules` 缺失分级定义『{level}』——"
                        "优先级被删/降级后 AI 无法判断哪里是重点", rel_common)
            for level, terms in PRIORITY_TERMS.items():
                if not any(t in block for t in terms):
                    err(f"公共片段 `priority-rules` 缺失 {level} 的判定用语（{'/'.join(terms)}）", rel_common)
            if "RFC 2119" not in block or "ISO" not in block:
                err("公共片段 `priority-rules` 未给业界共识依据（RFC 2119 / ISO）——"
                    "提示词要求按业界共识加载优先级规则，依据须保留", rel_common)
            if "不可降级" not in block:
                err("公共片段 `priority-rules` 缺失『不可降级』要求——"
                    "L1 须不可协商、不得被降级", rel_common)
    phase_done()


def main(argv=None) -> int:
    """命令行入口：解析参数、顺序执行全部检查、汇总错误并返回退出码。

    参数：`-v/--verbose` 打开逐文件进度日志（默认只打阶段级进度与最终结论）。
    """
    global VERBOSE
    parser = argparse.ArgumentParser(
        description="本规范集合的完整性机械校验（引用/链接/节名/栈登记/调度器/私有约定/"
                    "历史来源/INSTALL 模板/文档注水/git mv/要点防线 + AsciiDoc 语法）")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="输出逐文件进度（默认静默，仅打印阶段进度与错误清单）")
    args = parser.parse_args(argv)
    VERBOSE = args.verbose

    log(f"检查根目录: {REPO_ROOT}")
    log(f"共发现 {len(collect_adoc_files())} 个 .adoc 文件")
    print()

    check_refs_exist()
    check_link_refs()
    check_section_refs()
    check_stack_consistency()
    check_dispatcher_registry()
    check_forbidden_patterns()
    check_historical_notes()
    check_install_codeblock()
    check_filler_docs()
    check_principle_guard()
    check_priority_guard()
    check_prompts_primary()
    check_asciidoctor_syntax()

    print()
    if errors:
        log(f"发现 {len(errors)} 个规范性问题：")
        for e in errors:
            print("  - " + e)
        return 1
    log("OK 规范检查全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

