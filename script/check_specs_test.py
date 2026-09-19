#!/usr/bin/env python3
"""check_specs.py 的单元测试（纯 stdlib unittest，零第三方依赖）。

针对每个检查函数覆盖正例与反例：
  * extract_specs_refs     —— 引用提取与归一化（根反引号 / link 相对 / 各类剔除）
  * check_refs_exist       —— 引用存在性（正：存在；反：悬空引用）
  * check_link_refs        —— 链接格式（正：相对且合法；反：根绝对 / 越出仓库根）
  * check_section_refs     —— 节名引用存在性（正：节存在；反：节已改名/删除）
  * check_stack_consistency—— 技术栈双向一致（正：登记且存在；反：漏登记 / 登记不存在）
  * check_dispatcher_layers—— 加载调度器分层结构（正：五层+维护层层头与条目齐备；反：层头被吞/空壳层头/节被改写）
  * check_forbidden_patterns—— 私有约定误导入（正：无命中；反：命中）
  * check_filler_docs      —— 文档注水兜底（正：简短条目/标题词+内容/纯格式行不误报；反：占位段/完全重复段）
  * check_self_check_guard —— 自检防线（正：自检规范+落点+登记齐备；反：文件被删/要点缺失/落点缺失/未登记）
  * check_source_guard     —— 来源防线（正：来源规范要点齐备；反：文件被删/要点缺失/未登记）
  * check_java_test_naming —— Java 测试类命名防线（正：两侧四类后缀判据齐备；反：后缀被删/调度器口径漂移）
  * check_line_ending_guard —— 换行符防线（正：LF 基准 + `.bat`/`.cmd` CRLF + `.gitattributes`/`.editorconfig` 齐备；反：文件被删/判据缺失/栈文件未写行尾/未登记）
  * check_review_guard   —— 评审备注落点防线（正：判据条 + 两个方向约束 + 两处引用齐备；反：文件被删/判据缺失/引用断开）
  * check_verify_guard   —— 规范验证防线（正：两问定式化节 + P2 + 本仓库落点三处一致；
                             反：文件被删/节改名/第二问被删/P2 或本仓库口径未同步/未登记）
  * check_priority_guard 另钉『怎么走』形态声明与各最高关注项的『依据』行（反：形态声明被删/依据被整段删）
  * check_spec_admission_guard 另钉读法形态与重构后的有效性核对（反：两节被删）
  * check_runtime_env_guard —— 运行环境须与项目声明一致防线（正：条文/判据/声明落点/降级路径/依据行与三处引用齐备；
                             反：整节被删/L1 被摘/"能跑通也不得换"被删/判据被抽/声明落点被删/降级路径被删/依据被删/引用与登记断开）
  * check_registry_mirror_guard —— 包源与镜像源防线（正：次序/降级边界/先实测/不覆盖既有配置/推荐非强制/栈侧落点与图书馆登记齐备；
                             反：文件或节被删、次序被抹平、先实测被删、覆盖既有配置、推荐被读成强制、栈侧落点或图书馆记录缺失）
  * check_index_page_guard —— 索引页触发判据防线（正：触发判据/空壳不建/只做导航/模块 README 齐备；
                             反：doc.adoc 判据被删、doc-module.adoc 按需口径被删、文件被删）

范围：只校验本仓库维护的规范/模板文本，**不检查 git 工作区状态、不检查引用方项目**
（引用方项目内部的 delete+create 等操作对本仓库校验不可见，详见 check_specs.py 文件头）。

运行方式：
  python -W ignore script/check_specs_test.py
或：
  python -W ignore -m unittest script.check_specs_test   （需将 script 按包导入）

注：文件命名为 `<被测文件>_test.py`（`_test` 后缀），使被测文件与其测试在目录
排序中相邻（check_specs.py 紧邻 check_specs_test.py）。
"""

import importlib.util
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))

_SPEC = importlib.util.spec_from_file_location(
    "check_specs", os.path.join(HERE, "check_specs.py"))
cm = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cm)  # type: ignore[union-attr]


def _mk_blackbox_base(root: str) -> str:
    """从官仓库示例构造一个标准基目录（AGENTS + general + core + stack）。"""
    specs = os.path.join(root, "specs")
    os.makedirs(os.path.join(specs, "general"), exist_ok=True)
    os.makedirs(os.path.join(specs, "core"), exist_ok=True)
    os.makedirs(os.path.join(specs, "stack"), exist_ok=True)
    return specs


class CheckSpecsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        # 保存模块全局并重定向到临时根，避免污染/依赖真实仓库
        self._orig = (cm.REPO_ROOT, cm.GENERIC_FILE, cm.SPECS_DIR, cm.PROJECT_SPECS_DIR,
                      cm.INSTALL_FILE, cm.PROJECT_FILE)
        self.root = tempfile.mkdtemp()
        cm.REPO_ROOT = self.root
        cm.GENERIC_FILE = os.path.join(self.root, "AGENTS_COMMON.adoc")
        cm.SPECS_DIR = os.path.join(self.root, "specs")
        cm.PROJECT_SPECS_DIR = os.path.join(self.root, "specs-project-maintainer")
        cm.INSTALL_FILE = os.path.join(self.root, "INSTALL.adoc")
        cm.PROJECT_FILE = os.path.join(self.root, "AGENTS.adoc")

    def tearDown(self) -> None:
        cm.errors.clear()
        (cm.REPO_ROOT, cm.GENERIC_FILE, cm.SPECS_DIR, cm.PROJECT_SPECS_DIR,
         cm.INSTALL_FILE, cm.PROJECT_FILE) = self._orig
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, relpath: str, content: str) -> None:
        """在临时根下按相对路径写文件（自动建父目录）。"""
        p = os.path.join(self.root, relpath)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)

    def error_texts(self) -> str:
        return "\n".join(cm.errors)



class TestCheckBudgetGuard(CheckSpecsTestCase):
    """钉住常驻层体积上限（防"越写越多捆住 AI"）。

    必加载层每次会话无条件加载，是最直接的注意力预算消耗者；此前只有方向无抓手，
    故用字节上限把"先归位、再新增"变成机械可拦。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_budget = cm.RESIDENT_BUDGET
        self._orig_items = cm.DISPATCHER_ITEMS_MAX
        self._orig_entry = cm.PROJECT_ENTRY_BUDGET

    def tearDown(self) -> None:
        cm.RESIDENT_BUDGET = self._orig_budget
        cm.DISPATCHER_ITEMS_MAX = self._orig_items
        cm.PROJECT_ENTRY_BUDGET = self._orig_entry
        super().tearDown()

    def _write_valid(self, filler=""):
        self.write("AGENTS_COMMON.adoc",
                   "= 入口\n\n== 分类与懒加载（加载调度器）\n"
                   "  ** 执行原则 → link:specs/core/execution.adoc[]\n"
                   "== 规范文件登记完整性\n" + filler)
        self.write("specs/core/execution.adoc", "= 执行原则\n" + filler)
        self.write("specs-project-maintainer/priority.adoc", "= 优先级\n" + filler)

    def test_valid_within_budget_passes(self):
        self._write_valid()
        cm.check_budget_guard()
        self.assertEqual(cm.errors, [])

    def test_resident_over_budget_reports(self):
        # 反例：常驻层体积超限（每次会话都为新增内容付上下文）
        cm.RESIDENT_BUDGET = 10
        self._write_valid(filler="x" * 200)
        cm.check_budget_guard()
        self.assertIn("常驻层体积超限", self.error_texts())

    def test_dispatcher_items_over_max_reports(self):
        # 反例：调度器条目过多（"该加载哪些"难以判全）
        cm.DISPATCHER_ITEMS_MAX = 0
        self._write_valid()
        cm.check_budget_guard()
        self.assertIn("条目数超限", self.error_texts())

    def test_missing_resident_file_reports(self):
        # 反例：必加载层文件缺失
        self.write("AGENTS_COMMON.adoc", "= 入口")
        cm.check_budget_guard()
        self.assertIn("缺少必加载层文件", self.error_texts())

    def test_project_entry_over_budget_reports(self):
        # 反例：项目自身入口 AGENTS.adoc 同为常驻物，超限须报
        # （它先于 AGENTS_COMMON.adoc 被读、每次会话都付上下文，故单列上限）
        cm.PROJECT_ENTRY_BUDGET = 10
        self._write_valid()
        self.write("AGENTS.adoc", "x" * 200)
        cm.check_budget_guard()
        self.assertIn("AGENTS.adoc 体积超限", self.error_texts())

    def test_project_entry_within_budget_passes(self):
        # 正例：AGENTS.adoc 在上限内不报
        self._write_valid()
        self.write("AGENTS.adoc", "= 入口\n\n小内容")
        cm.check_budget_guard()
        self.assertEqual(cm.errors, [])

    def test_dispatcher_section_rewritten_reports(self):
        # 反例：调度器节标题被改写 → 条目数抓手失效
        self.write("AGENTS_COMMON.adoc", "= 入口\n\n== 随便什么节\n")
        self.write("specs/core/execution.adoc", "= 执行原则")
        self.write("specs-project-maintainer/priority.adoc", "= 优先级")
        cm.check_budget_guard()
        self.assertIn("分类与懒加载", self.error_texts())


class TestCheckDispatcherLayers(CheckSpecsTestCase):
    """钉住加载调度器的分层结构（层头 + 每层条目数）。

    背景（本仓库实证）：按 `** ` 条目做"取到下一个条目"的替换时，会把夹在两条之间的
    层头行（`* 技术栈层（…）：`）一并吞掉，条目遂挂到上一层、加载触发条件出错，而
    **既有机械校验全绿**（登记/链接/体积都不看层头）。故机械钉住层头与"空壳层头"。
    """

    def _write(self, sec_body: str) -> None:
        self.write("AGENTS_COMMON.adoc",
                   "= 入口\n\n== 分类与懒加载（加载调度器）\n" + sec_body +
                   "\n== 规范文件登记完整性\n")

    def test_all_layers_present_passes(self):
        self._write(
            "* 必加载层（每次工作都须加载）：\n"
            "  ** 执行原则 → link:specs/core/execution.adoc[]\n"
            "* 通用层（涉及对应活动时加载，不得跳过）：\n"
            "  ** 编写代码 → link:specs/general/coding.adoc[]\n"
            "* 技术栈层（按项目实际使用的语言/技术栈加载）：\n"
            "  ** Java 项目 → link:specs/stack/java.adoc[]\n"
            "* 项目类型层（按项目在其自身规范中的主动声明加载）：\n"
            "  ** 通用工具/库类项目 → link:specs/general/doc-tool.adoc[]\n"
            "* 平台层（按使用平台加载）：\n"
            "  ** CNB 平台 → link:specs/platform/cnb.adoc[]\n"
            "* 项目自身维护层（只对维护共享内容的项目生效）：\n"
            "  ** 条目落点：说明\n")
        cm.check_dispatcher_layers()
        self.assertEqual(cm.errors, [])

    def test_missing_layer_header_reports(self):
        # 反例：技术栈层层头被吞掉（条目仍在，但挂到了通用层下）
        self._write(
            "* 必加载层（每次工作都须加载）：\n"
            "  ** 执行原则 → link:specs/core/execution.adoc[]\n"
            "* 通用层（涉及对应活动时加载，不得跳过）：\n"
            "  ** Java 项目 → link:specs/stack/java.adoc[]\n"
            "* 项目类型层（按项目在其自身规范中的主动声明加载）：\n"
            "  ** 工具库类项目 → link:specs/general/doc-tool.adoc[]\n"
            "* 平台层（按使用平台加载）：\n"
            "  ** CNB 平台 → link:specs/platform/cnb.adoc[]\n"
            "* 项目自身维护层（只对维护共享内容的项目生效）：\n"
            "  ** 条目落点：说明\n")
        cm.check_dispatcher_layers()
        self.assertIn("缺失「技术栈层」层头行", self.error_texts())

    def test_empty_layer_header_reports(self):
        # 反例：空壳层头（层头下无任何条目）
        self._write(
            "* 必加载层（每次工作都须加载）：\n"
            "  ** 执行原则 → link:specs/core/execution.adoc[]\n"
            "* 通用层（涉及对应活动时加载，不得跳过）：\n"
            "  ** 编写代码 → link:specs/general/coding.adoc[]\n"
            "* 技术栈层（按项目实际使用的语言/技术栈加载）：\n"
            "* 项目类型层（按项目在其自身规范中的主动声明加载）：\n"
            "  ** 工具库类项目 → link:specs/general/doc-tool.adoc[]\n"
            "* 平台层（按使用平台加载）：\n"
            "  ** CNB 平台 → link:specs/platform/cnb.adoc[]\n"
            "* 项目自身维护层（只对维护共享内容的项目生效）：\n"
            "  ** 条目落点：说明\n")
        cm.check_dispatcher_layers()
        self.assertIn("层头下没有任何条目", self.error_texts())

    def test_dispatcher_section_missing_reports(self):
        # 反例：调度器节被改写 → 结构防线失去抓手
        self.write("AGENTS_COMMON.adoc", "= 入口\n\n== 别的节\n")
        cm.check_dispatcher_layers()
        self.assertIn("分类与懒加载", self.error_texts())


class TestCheckDelegationGuard(CheckSpecsTestCase):
    """钉住从属者与能力自评、执行者来源选择（"定义了却不会执行"的高发盲点）。

    执行者来源这一半**已由"优先同源"收紧为"强制同 Agent + 不得点名外部 NPC"**，故本
    组用例同步按新口径写正例/反例：只留旧字样（"优先同源""同源不可用后换外部来源"）不再
    算通过——后者正是要被拦下的"换个 Agent 当第一手段"。
    """

    def _write_valid(self):
        self.write("AGENTS_COMMON.adoc", "= t\n\n从属者：加载由已加载入口驱动。\n")
        self.write("specs/general/self-check.adoc", "= t\n\n== 环境能力自评\n无机制走降级。\n")
        self.write("specs/general/collab.adoc",
                   "= t\n\n"
                   "**子任务必须由与执行者相同的 Agent 承担（L1，强制同 Agent）**："
                   "判据：**同 Agent** 与**同一 Agent 身份**。\n\n"
                   "**不得点名外部 Agent / 外部 NPC（L1）**：判定标准——"
                   "①**派发目标**是外部标识；②**交换面**超出本执行者可直接调用；"
                   "③结论**回传面**读不到。\n\n"
                   "* **子 Agent 不可用时的降级路径（L1）**：**不换任何外部来源**，"
                   "①**由执行者本人（主 agent）串行承担**。\n\n"
                   "* **优先一次性调用（L1）**\n")
        # 三视角复核口径的单一落点是 verify.adoc（testing.adoc 同名节只留一跳入口）
        self.write("specs/general/verify.adoc",
                   "= t\n\n* **执行者选择：强制同 Agent（L1）**：三视角复核一律由与执行者"
                   "相同的 Agent 承担，**不得点名外部 Agent / 外部 NPC**。\n")
        self.write("specs-project-maintainer/verify.adoc",
                   "= t\n\n**子 Agent 强制与执行者同 Agent（维护方落点）**\n")

    def test_valid_passes(self):
        self._write_valid()
        cm.check_delegation_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_delegation_mechanism_reports(self):
        # 反例：删掉"从属者适配"→ 子 agent/被引用方可以"没被派发"为由跳过加载
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "= t\n\n（加载由派发者转发、不靠入口）\n")
        cm.check_delegation_guard()
        self.assertIn("从属者", self.error_texts())

    def test_missing_capability_selfcheck_reports(self):
        # 反例：删掉"环境能力自评"→ 环境无清空/无子 agent 时照抄"已完成"
        self._write_valid()
        self.write("specs/general/self-check.adoc", "= t\n\n（无能力自评）\n")
        cm.check_delegation_guard()
        self.assertIn("环境能力自评", self.error_texts())

    def test_missing_same_agent_requirement_reports(self):
        # 反例：删掉"子任务必须与执行者同 Agent"→ 缺复核时随手抓外部执行者（不可核对）
        self._write_valid()
        self.write("specs/general/collab.adoc",
                   "= t\n\n* **优先一次性调用（L1）**\n\n* **子 Agent 不可用时的降级路径（L1）**\n")
        cm.check_delegation_guard()
        self.assertIn("子任务必须由与执行者相同的 Agent 承担", self.error_texts())

    def test_missing_named_external_npc_ban_reports(self):
        # 反例：删掉"不得点名外部 Agent / 外部 NPC"→ 评论里直接 @ 外部 NPC 又无人拦
        self._write_valid()
        self.write("specs/general/collab.adoc",
                   "= t\n\n**子任务必须由与执行者相同的 Agent 承担（L1，强制同 Agent）**："
                   "判据：**同 Agent** 与**同一 Agent 身份**。\n\n"
                   "* **子 Agent 不可用时的降级路径（L1）**：**不换任何外部来源**，"
                   "①**由执行者本人（主 agent）串行承担**。\n\n"
                   "* **优先一次性调用（L1）**\n")
        cm.check_delegation_guard()
        self.assertIn("不得点名外部 Agent / 外部 NPC", self.error_texts())

    def test_external_npc_ban_without_criteria_reports(self):
        # 反例：只留"不得点名外部 NPC"字样、判定标准被抽掉 → 判据不可执行（假绿）
        self._write_valid()
        self.write("specs/general/collab.adoc",
                   "= t\n\n**子任务必须由与执行者相同的 Agent 承担（L1，强制同 Agent）**："
                   "判据：**同 Agent** 与**同一 Agent 身份**。\n\n"
                   "**不得点名外部 Agent / 外部 NPC（L1）**\n\n"
                   "* **子 Agent 不可用时的降级路径（L1）**：**不换任何外部来源**，"
                   "①**由执行者本人（主 agent）串行承担**。\n\n"
                   "* **优先一次性调用（L1）**\n")
        cm.check_delegation_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_missing_same_agent_fallback_reports(self):
        # 反例：删掉"同 Agent 不可用时的降级路径"→ 只剩"换外部来源"一条路
        self._write_valid()
        self.write("specs/general/collab.adoc",
                   "= t\n\n**子任务必须由与执行者相同的 Agent 承担（L1，强制同 Agent）**："
                   "判据：**同 Agent** 与**同一 Agent 身份**。\n\n"
                   "**不得点名外部 Agent / 外部 NPC（L1）**：判定标准——①**派发目标**是外部标识；"
                   "②**交换面**超出本执行者可直接调用；③结论**回传面**读不到。\n\n"
                   "* **优先一次性调用（L1）**\n")
        cm.check_delegation_guard()
        self.assertIn("降级路径（L1）", self.error_texts())

    def test_missing_one_shot_call_reports(self):
        # 反例：删掉"优先一次性调用"→ 又回到"交一个有自主探查权的执行者"（超时无法判定）
        self._write_valid()
        self.write("specs/general/collab.adoc",
                   "= t\n\n**子任务必须由与执行者相同的 Agent 承担（L1，强制同 Agent）**："
                   "判据：**同 Agent** 与**同一 Agent 身份**。\n\n"
                   "**不得点名外部 Agent / 外部 NPC（L1）**：判定标准——①**派发目标**是外部标识；"
                   "②**交换面**超出本执行者可直接调用；③结论**回传面**读不到。\n\n"
                   "* **子 Agent 不可用时的降级路径（L1）**：**不换任何外部来源**，"
                   "①**由执行者本人（主 agent）串行承担**。\n")
        cm.check_delegation_guard()
        self.assertIn("优先一次性调用", self.error_texts())

    def test_missing_maintainer_executor_source_reports(self):
        # 反例：维护方落点丢掉"强制同 Agent"→ 又先去派外部 NPC
        self._write_valid()
        self.write("specs-project-maintainer/verify.adoc", "= t\n\n（无条件口径）\n")
        cm.check_delegation_guard()
        self.assertIn("子 Agent 强制与执行者同 Agent", self.error_texts())

    def test_missing_file_reports(self):
        self.write("AGENTS_COMMON.adoc", "从属者")
        cm.check_delegation_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_stale_wording_in_list_item_reports(self):
        # 反例（本轮实际漏检）：**清单概览行**回到旧口径（"优先同源 + 外部来源作备选"），
        # 而 `=== P6` 条目正文仍是新口径 → 旧防线只读 P6 条目、不看清单行，全绿放过。
        # 清单行更先被读到，按它读的维护方会继续把复核派给不可核对的外部执行者。
        self._write_valid()
        self.write("specs-project-maintainer/priority.adoc",
                   "= t\n\n"
                   "* **协作执行者选择（P6，条款本身 L1）**：需要子 Agent（子任务/复核）时"
                   "**优先用与执行者同源、可用的执行者**承担，"
                   "**外部来源（外部 NPC/另一个产品）只是同源不可用后的备选**。\n\n"
                   "**子 Agent 强制与执行者同 Agent（维护方落点）**\n")
        cm.check_delegation_guard()
        self.assertIn("重新放宽", self.error_texts())

    def test_stale_wording_appended_in_same_file_reports(self):
        # 反例：新口径字样都还在，但在同文件的另一句里**追加放宽**
        # （"拿不到同 Agent 时也可以换外部 Agent 顶替"）→ 只核"要素仍在"的写法会假绿。
        self._write_valid()
        path = os.path.join(self.root, "specs", "general", "collab.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.write("specs/general/collab.adoc",
                   text + "\n拿不到同 Agent 时也可以换外部 Agent 顶替。\n")
        cm.check_delegation_guard()
        self.assertIn("重新放宽", self.error_texts())

    def test_mixed_forbid_and_relax_in_one_clause_reports(self):
        # 反例（本项目真实形态）：同一分句前半句还在"不得点名外部…"、后半句却放宽
        # （"也不得把外部复核者当备选" → "也允许换外部复核者当备选"）。
        # 若否定词按整个分句判定，这类"前半句禁止、后半句放宽"会被误放行。
        self._write_valid()
        path = os.path.join(self.root, "specs-project-maintainer", "verify.adoc")
        self.write("specs-project-maintainer/verify.adoc",
                   "= t\n\n**子 Agent 强制与执行者同 Agent（维护方落点）**："
                   "**不得点名外部 Agent / 外部 NPC**、也允许换外部复核者当备选\n")
        cm.check_delegation_guard()
        self.assertIn("重新放宽", self.error_texts())
        self.assertTrue(os.path.isfile(path))

    def test_negated_wording_does_not_report(self):
        # 正例（**防误报**）：禁止式写法与旧口径的反例引用是正当文本，不得被拦
        # ——否则规范无法写"不得用外部 Agent 顶替"这类要求。
        self._write_valid()
        path = os.path.join(self.root, "specs", "general", "collab.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.write("specs/general/collab.adoc",
                   text + "\n**不得用外部 Agent 顶替**，也不得把外部 NPC 作备选；"
                          "不得改回『外部来源可以顶替』的宽松写法。\n")
        cm.check_delegation_guard()
        self.assertEqual(cm.errors, [])


class TestCheckGitMvSelfcheck(CheckSpecsTestCase):
    """钉住"本仓库自身侧"的 git mv 自查（P1 可机械核对的那一半）。

    引用方侧不可见属既有事实，但本仓库自己也是 git 工作区，故须有这一半抓手；
    非 git 目录/无暂存内容须**跳过不报错**（保持确定性与幂等）。
    """

    def test_non_git_root_skips_without_error(self):
        # 正例：临时根非 git 仓库 → 跳过、不报错（保证幂等）
        cm.check_git_mv_selfcheck()
        self.assertEqual(cm.errors, [])

    def test_real_repo_without_delete_add_passes(self):
        # 正例：对本仓库真实运行须无错（无 delete+add 形态）
        self.tearDown()
        self.setUp = lambda: None  # noqa: 仅为让本用例用真实根
        cm.REPO_ROOT_BACKUP = None
        # 直接用真实仓库根快速核对一次
        real = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cm.REPO_ROOT = real
        cm.check_git_mv_selfcheck()
        self.assertEqual([e for e in cm.errors if "暂存区" in e], [])



# --------------------------------------------------------------------------- #
# extract_specs_refs
# --------------------------------------------------------------------------- #
class TestExtractSpecsRefs(unittest.TestCase):
    """直接测纯函数，不依赖文件系统。"""

    def test_backtick_is_root_relative(self):
        text = "加载 `specs/general/coding.adoc`"
        self.assertEqual(cm.extract_specs_refs(text), ["specs/general/coding.adoc"])

    def test_link_relative_resolves_to_repo_path(self):
        text = "见 link:../general/coding.adoc[]"
        self.assertEqual(
            cm.extract_specs_refs(text, base_dir="specs/core"),
            ["specs/general/coding.adoc"])

    def test_link_same_dir(self):
        text = "link:execution.adoc[]"
        self.assertEqual(
            cm.extract_specs_refs(text, base_dir="specs/core"),
            ["specs/core/execution.adoc"])

    def test_external_rootabs_anchor_escape_excluded(self):
        text = ("link:https://example.com/a[] link:#anch "
                "link:/specs/general/x.adoc[] link:../../../y.adoc[] "
                "`specs/nope.adoc`")
        # 根绝对与越界的 link 不参与存在性；但反引号 specs/nope.adoc 属根相对，保留
        self.assertEqual(cm.extract_specs_refs(text, base_dir="specs/core"),
                         ["specs/nope.adoc"])

    def test_placeholder_excluded_dir_kept(self):
        # 占位符（`...`、`<...>`）不参与存在性；**目录型引用保留**（以 `/` 结尾），
        # 由调用方按 os.path.isdir 核对——原实现把目录型一并跳过，等于必然漏报。
        text = ("`specs/...` `specs/stack/` `specs/stack/<语言>-testing.adoc` "
                "link:../stack/<语言>-testing.adoc[]")
        self.assertEqual(cm.extract_specs_refs(text, base_dir="specs/core"),
                         ["specs/stack/"])

    def test_dedupe_preserve_order(self):
        text = "`specs/stack/java.adoc` `specs/stack/java.adoc` link:../stack/java.adoc[]"
        self.assertEqual(cm.extract_specs_refs(text, base_dir="specs/general"),
                         ["specs/stack/java.adoc"])


# --------------------------------------------------------------------------- #
# collect_adoc_files / _is_dir_ref / _is_placeholder_ref
# --------------------------------------------------------------------------- #
class TestCollectAdocFiles(CheckSpecsTestCase):
    """钉住"检查集合的覆盖面"：纳入 `library/**`、`prompts/**` 与仓库根全部 .adoc。

    原实现只收 `specs/` + `AGENTS_COMMON.adoc` + `AGENTS.adoc` + `INSTALL.adoc`，
    `library/**` 与根 `PUBLIC.adoc`/`README.adoc`/`PROMPTS.adoc`（连 `CHANGELOG.adoc`）
    全部漏收——语法编译、引用存在性、节名引用、链接格式四口径对它们整体失效。
    `prompts/**` 亦曾漏收，而它是要复制给未知项目执行的产物（见 `PUBLIC.adoc`）：
    其自身死链/悬空引用会随分发流出。
    """

    def test_library_files_collected(self):
        self.write("library/README.adoc", "= 图书馆\n")
        self.write("library/sources.adoc", "= 来源\n")
        files = cm.collect_adoc_files()
        self.assertIn("library/README.adoc", files)
        self.assertIn("library/sources.adoc", files)

    def test_root_docs_collected(self):
        self.write("PUBLIC.adoc", "= 公共内容入口索引\n")
        self.write("README.adoc", "= 说明\n")
        self.write("PROMPTS.adoc", "= 提示词\n")
        files = cm.collect_adoc_files()
        for rel in ("PUBLIC.adoc", "README.adoc", "PROMPTS.adoc"):
            self.assertIn(rel, files)

    def test_prompts_files_collected(self):
        # prompts/*.adoc 是要复制给未知项目执行的产物，其自身引用完整性须受四口径覆盖
        self.write("prompts/review.adoc", "= 提示词：检查修复\n")
        self.write("prompts/_common.txt", "公共片段\n")
        files = cm.collect_adoc_files()
        self.assertIn("prompts/review.adoc", files)
        # 非 .adoc（_common.txt）不入集合：四口径只针对 .adoc 引用
        self.assertNotIn("prompts/_common.txt", files)

    def test_prompts_dangling_ref_reported(self):
        self.write("AGENTS_COMMON.adoc", "= t\n")
        self.write("prompts/review.adoc", "见 link:no_such_file.adoc[]\n")
        cm.check_refs_exist()
        self.assertIn("prompts/no_such_file.adoc", self.error_texts())

    def test_prompts_dangling_section_ref_reported(self):
        self.write("AGENTS_COMMON.adoc", "= t\n")
        self.write("prompts/review.adoc",
                   "link:../specs/general/doc.adoc[]「不存在的节XYZ」\n")
        self.write("specs/general/doc.adoc", "= 文档\n\n== 真实节\n")
        cm.check_section_refs()
        self.assertIn("不存在的节XYZ", self.error_texts())

    def test_prompts_root_absolute_link_reported(self):
        self.write("AGENTS_COMMON.adoc", "= t\n")
        self.write("prompts/review.adoc", "见 link:/prompts/refactor.adoc[]\n")
        cm.check_link_refs()
        self.assertIn("根绝对", self.error_texts())

    def test_prompts_need_not_register_dispatcher(self):
        # prompts/ 非规范本体、不进规范加载链，其互相引用不得被要求登记进调度器
        self.write("AGENTS_COMMON.adoc", "= t\n")
        self.write("prompts/review.adoc", "见 link:refactor.adoc[]\n")
        self.write("prompts/refactor.adoc", "= 重构\n")
        cm.check_dispatcher_registry()
        self.assertEqual(cm.errors, [])

    def test_paths_are_repo_relative(self):
        # 统一为"仓库根相对 POSIX 路径"（"某文件在不在集合里"可直接核验）
        self.write("specs/general/coding.adoc", "= 编码\n")
        for f in cm.collect_adoc_files():
            self.assertFalse(os.path.isabs(f), f)
            self.assertNotIn("\\", f)

    def test_does_not_leak_real_repo_files(self):
        # 只收本仓库（此处为临时根）内的文件：不得把真实仓库的 library/ 漏收进来
        self.write("specs/general/coding.adoc", "= 编码\n")
        self.assertNotIn("library/README.adoc", cm.collect_adoc_files())


class TestRefKindPredicates(unittest.TestCase):
    """钉住 `_is_dir_ref` 与 `_is_placeholder_ref` 的分工（目录型不再整体跳过）。"""

    def test_dir_ref_recognized(self):
        self.assertTrue(cm._is_dir_ref("specs/"))
        self.assertTrue(cm._is_dir_ref("script/"))
        self.assertFalse(cm._is_dir_ref("specs/general/coding.adoc"))

    def test_dir_ref_is_not_placeholder(self):
        # 目录型有确定判据（目录是否存在），不得被当成占位符整体跳过
        self.assertFalse(cm._is_placeholder_ref("script/"))
        self.assertFalse(cm._is_placeholder_ref("specs/"))

    def test_true_placeholders_still_recognized(self):
        self.assertTrue(cm._is_placeholder_ref("specs/..."))
        self.assertTrue(cm._is_placeholder_ref("specs/**"))
        self.assertTrue(cm._is_placeholder_ref("specs/stack/<语言>.adoc"))


# --------------------------------------------------------------------------- #
# check_asciidoctor_syntax（--failure-level=WARN）
# --------------------------------------------------------------------------- #
class TestAsciidoctorFailureLevel(CheckSpecsTestCase):
    """钉住语法编译的**效力边界**：asciidoctor 默认对 WARNING/ERROR 仍返回 0。

    故命令行必须显式带 `--failure-level=WARN`，否则 `include::` 目标缺失、`image::`
    找不到这类"只告警不报错"的问题必然漏报（防线形同虚设）。
    """

    def test_failure_level_constant_present(self):
        src = open(os.path.join(os.path.dirname(cm.__file__),
                                "check_specs.py"), encoding="utf-8").read()
        self.assertIn("--failure-level=WARN", src)

    def test_no_asciidoctor_skips_without_error(self):
        # 本环境无 asciidoctor：跳过而非报错（保证幂等）
        orig = cm.shutil.which
        cm.shutil.which = lambda name: None
        try:
            cm.check_asciidoctor_syntax()
        finally:
            cm.shutil.which = orig
        self.assertEqual(cm.errors, [])


# --------------------------------------------------------------------------- #
# check_refs_exist：目录型引用
# --------------------------------------------------------------------------- #
class TestCheckRefsExistDirRefs(CheckSpecsTestCase):
    def test_existing_dir_ref_passes(self):
        self.write("AGENTS_COMMON.adoc", "见 `script/`")
        self.write("script/clean_tmp.py", "#!/usr/bin/env python3\n")
        cm.check_refs_exist()
        self.assertEqual(cm.errors, [])

    def test_missing_dir_ref_reports(self):
        # 反例：目录型引用指向不存在的目录 —— 原实现整体跳过，这里必须报出
        self.write("AGENTS_COMMON.adoc", "见 `script/`")
        cm.check_refs_exist()
        self.assertIn("不存在的目录", self.error_texts())
        self.assertIn("script/", self.error_texts())

    def test_missing_link_dir_ref_reports(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc", "见 link:../../gone-dir/[]")
        cm.check_refs_exist()
        self.assertIn("不存在的目录", self.error_texts())


# --------------------------------------------------------------------------- #
# check_refs_exist / check_section_refs：CHANGELOG 历史豁免
# --------------------------------------------------------------------------- #
class TestHistoricalFileExemption(CheckSpecsTestCase):
    """CHANGELOG.adoc 是只追加的变更历史：旧路径"查不到"是记录本身，不属悬空。"""

    def test_changelog_in_collected(self):
        self.write("CHANGELOG.adoc", "= 变更\n")
        self.assertIn("CHANGELOG.adoc", cm.collect_adoc_files())

    def test_changelog_old_paths_not_reported(self):
        self.write("CHANGELOG.adoc", "= 变更\n\n见 `specs/gone/old.adoc`\n")
        cm.check_refs_exist()
        self.assertEqual(cm.errors, [])

    def test_changelog_old_section_not_reported(self):
        self.write("CHANGELOG.adoc", "= 变更\n")
        self.write("specs/general/doc.adoc", "= 文档\n\n== 注释与文档\n")
        self.write("CHANGELOG.adoc",
                   "= 变更\n\n见 link:specs/general/doc.adoc[]「已改名节」\n")
        cm.check_section_refs()
        self.assertEqual(cm.errors, [])


# --------------------------------------------------------------------------- #
# check_refs_exist
# --------------------------------------------------------------------------- #
class TestCheckRefsExist(CheckSpecsTestCase):
    def test_valid_reference_passes(self):
        self.write("AGENTS_COMMON.adoc", "加载 `specs/general/coding.adoc`")
        self.write("specs/general/coding.adoc", "= 编码")
        cm.check_refs_exist()
        self.assertEqual(cm.errors, [])

    def test_dangling_backtick_reference_reports(self):
        self.write("AGENTS_COMMON.adoc", "加载 `specs/general/gone.adoc`")
        cm.check_refs_exist()
        self.assertIn("不存在", self.error_texts())
        self.assertIn("specs/general/gone.adoc", self.error_texts())

    def test_dangling_link_between_specs_reports(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/core/execution.adoc",
                   "见 link:../general/nothing.adoc[]")
        cm.check_refs_exist()
        self.assertIn("不存在", self.error_texts())
        self.assertIn("specs/general/nothing.adoc", self.error_texts())

    def test_link_pointing_to_existing_file_passes(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/core/execution.adoc",
                   "见 link:../general/doc-design.adoc[]")
        self.write("specs/general/doc-design.adoc", "= 设计")
        cm.check_refs_exist()
        self.assertEqual(cm.errors, [])


# --------------------------------------------------------------------------- #
# check_link_refs
# --------------------------------------------------------------------------- #
class TestCheckLinkRefs(CheckSpecsTestCase):
    def test_relative_link_passes(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/core/execution.adoc",
                   "见 link:../general/doc-design.adoc[]")
        cm.check_link_refs()
        self.assertEqual(cm.errors, [])

    def test_root_absolute_link_reports(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/core/execution.adoc",
                   "见 link:/specs/general/doc-design.adoc[]")
        cm.check_link_refs()
        self.assertIn("根绝对", self.error_texts())
        self.assertIn("link:/specs/general/doc-design.adoc", self.error_texts())

    def test_out_of_root_link_reports(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/core/execution.adoc", "见 link:../../../x.adoc[]")
        cm.check_link_refs()
        self.assertIn("越出仓库根", self.error_texts())

    def test_external_and_anchor_skipped(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc",
                   "link:https://example.com/a[] link:#sec-1[]")
        cm.check_link_refs()
        self.assertEqual(cm.errors, [])


# --------------------------------------------------------------------------- #
# check_stack_consistency
# --------------------------------------------------------------------------- #
class TestCheckStackConsistency(CheckSpecsTestCase):
    def test_registered_and_exists_passes(self):
        self.write("AGENTS_COMMON.adoc", "技术栈层登记 `specs/stack/java.adoc`")
        self.write("specs/stack/java.adoc", "= Java")
        cm.check_stack_consistency()
        self.assertEqual(cm.errors, [])

    def test_existing_but_not_registered_reports(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/stack/python.adoc", "= Python")
        cm.check_stack_consistency()
        self.assertIn("存在但未在技术栈层登记", self.error_texts())

    def test_registered_but_not_exists_reports(self):
        self.write("AGENTS_COMMON.adoc", "登记 `specs/stack/nodejs.adoc`")
        cm.check_stack_consistency()
        self.assertIn("不存在", self.error_texts())
        self.assertIn("specs/stack/nodejs.adoc", self.error_texts())


# --------------------------------------------------------------------------- #
# check_forbidden_patterns
# --------------------------------------------------------------------------- #
class TestCheckForbiddenPatterns(CheckSpecsTestCase):
    def test_clean_file_passes(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/review.adoc", "代码走 code review，无私有约定。")
        cm.check_forbidden_patterns()
        self.assertEqual(cm.errors, [])

    def test_private_interface_pattern_reports(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/review.adoc", "定义 ICFoo 接口。")
        cm.check_forbidden_patterns()
        self.assertNotEqual(cm.errors, [])
        self.assertIn("IC 前缀", self.error_texts())


# --------------------------------------------------------------------------- #
# check_historical_notes（『不保留无用的历史来源声明』机械抓手）
# --------------------------------------------------------------------------- #
class TestCheckHistoricalNotes(CheckSpecsTestCase):
    def test_clean_file_passes(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/git.adoc", "文件重命名必须使用 git mv。")
        cm.check_historical_notes()
        self.assertEqual(cm.errors, [])

    def test_early_version_note_reports(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc", "早期版本直接把 URL 交给 AI。")
        cm.check_historical_notes()
        self.assertNotEqual(cm.errors, [])
        self.assertIn("历史来源声明", self.error_texts())

    def test_migration_note_reports(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("AGENTS.adoc", "原位于通用规范必加载层，迁移至此并从通用规范中移除。")
        cm.check_historical_notes()
        self.assertNotEqual(cm.errors, [])
        self.assertIn("历史来源声明", self.error_texts())

    def test_old_naming_note_reports(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("AGENTS.adoc", "本文件是真正的 agents.md。")
        cm.check_historical_notes()
        self.assertNotEqual(cm.errors, [])
        self.assertIn("历史来源声明", self.error_texts())

    def test_git_mv_neutral_use_not_reported(self):
        # 中性合理表述（git 规范中"重命名"）不得误报
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/git.adoc", "文件移动/重命名必须使用 git mv，禁止 delete+create。")
        cm.check_historical_notes()
        self.assertEqual(cm.errors, [])


# --------------------------------------------------------------------------- #
# check_install_codeblock（INSTALL.adoc 模板代码块逐字保留）
# --------------------------------------------------------------------------- #
class TestCheckInstallCodeblock(CheckSpecsTestCase):
    TEMPLATE = """= Agent 规范安装

在目标项目根目录创建 `AGENTS.adoc`，内容为：

[source,asciidoc]
----
= Agent 规范入口

本项目的 agent 执行规范入口为：

https://agent.c332030.com/AGENTS_COMMON.adoc

读取该入口及其引用的 specs/ 规范，并持续遵守其全部要求。

规范属强制约束：**开工前必须先读取规范再执行**，不得因未读取/记不全而跳过或放宽任何条款。
----
"""

    # 入口文件名规则（默认 `AGENTS.adoc` + 兼容已存在的 `AGENTS.md`），与真实 INSTALL.adoc 同口径；
    # 单独一段便于反例只去掉它（钉住该规则被删时能被机械校验发现）。
    FILENAME_RULES = """
== 已存在 AGENTS 文档

先检查根目录是否已存在 agent 规范文档，按 `AGENTS.adoc` → `AGENTS.md` 顺序取第一个命中者：仅 `AGENTS.md`
存在时在它上面融合，文件名保持 `AGENTS.md`、**不重命名、不迁移**；已存在 `AGENTS.adoc` 时**不另建** `AGENTS.md`。
"""

    def test_wellformed_template_passes(self):
        # 正例须含入口文件名规则（默认 AGENTS.adoc + 兼容 AGENTS.md），与真实 INSTALL.adoc 同口径
        self.write("INSTALL.adoc", self.TEMPLATE + self.FILENAME_RULES)
        cm.check_install_codeblock()
        self.assertEqual(cm.errors, [])

    def test_missing_install_file_skips(self):
        # 不写 INSTALL.adoc：应跳过不报错
        self.write("AGENTS_COMMON.adoc", "= t")
        cm.check_install_codeblock()
        self.assertEqual(cm.errors, [])

    def test_collapsed_blank_lines_reports(self):
        # 反例：AI 折叠了代码块内的空行，导致段落粘连、样式改变
        collapsed = self.TEMPLATE.replace(
            "= Agent 规范入口\n\n本项目的 agent 执行规范入口为：\n\n"
            "https://agent.c332030.com/AGENTS_COMMON.adoc\n\n"
            "读取该入口及其引用的 specs/ 规范，并持续遵守其全部要求。",
            "= Agent 规范入口\n本项目的 agent 执行规范入口为：\n"
            "https://agent.c332030.com/AGENTS_COMMON.adoc\n"
            "读取该入口及其引用的 specs/ 规范，并持续遵守其全部要求。")
        self.write("INSTALL.adoc", collapsed)
        cm.check_install_codeblock()
        self.assertNotEqual(cm.errors, [])
        self.assertIn("缺少空行", self.error_texts())

    def test_merged_line_reports(self):
        # 反例：两段内容被合并到同一行，找不到独立成行的必备行
        merged = self.TEMPLATE.replace(
            "= Agent 规范入口\n\n本项目的 agent 执行规范入口为：",
            "= Agent 规范入口 本项目的 agent 执行规范入口为：")
        self.write("INSTALL.adoc", merged)
        cm.check_install_codeblock()
        self.assertNotEqual(cm.errors, [])
        self.assertIn("缺失或行被合并", self.error_texts())

    def test_missing_delimiters_reports(self):
        # 反例：代码块定界符不完整
        bad = self.TEMPLATE.replace("----\n", "")
        self.write("INSTALL.adoc", bad)
        cm.check_install_codeblock()
        self.assertIn("定界符", self.error_texts())

    def test_agents_md_only_in_fused_section_reports(self):
        # 反例：兼容规则只写"按 AGENTS.md 融合"，漏掉"不重命名 / 不另建"（会重命名或分叉出两个入口）
        doc = self.TEMPLATE + (
            "\n== 已存在 AGENTS 文档\n\n"
            "仅 `AGENTS.md` 存在时在它上面融合（文件名为 `AGENTS.md`）。\n")
        self.write("INSTALL.adoc", doc)
        cm.check_install_codeblock()
        self.assertIn("入口文件名规则被破坏", self.error_texts())

    def test_dropping_agents_md_compat_reports(self):
        # 反例：只认 AGENTS.adoc、把 AGENTS.md 兼容规则删掉（既有 AGENTS.md 的项目无法安装）
        self.write("INSTALL.adoc", self.TEMPLATE)  # TEMPLATE 不含 FILENAME_RULES
        cm.check_install_codeblock()
        self.assertNotEqual(cm.errors, [])
        self.assertIn("入口文件名规则被破坏", self.error_texts())
        self.assertIn("AGENTS.md", self.error_texts())


# --------------------------------------------------------------------------- #
# check_filler_docs（『禁止无意义/划水/凑字数文档』机械兜底）
# --------------------------------------------------------------------------- #
class TestCheckFillerDocs(CheckSpecsTestCase):
    def test_substantive_content_passes(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write(
            "specs/general/doc.adoc",
            "= 文档规范\n\n"
            "简短但有实质内容的一句话规则也必须保留（不因简短被判注水）。\n\n"
            "* 条目一：必须写清边界与默认值\n"
            "* 条目二：禁止写套话与复述结论\n")
        cm.check_filler_docs()
        self.assertEqual(cm.errors, [])

    def test_placeholder_paragraph_reports(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc", "= t\n\n此处待补充。\n")
        cm.check_filler_docs()
        self.assertIn("注水", self.error_texts())
        self.assertIn("占位段", self.error_texts())

    def test_repeated_paragraph_reports(self):
        dup = ("* 必须保证条目承载可核对的事实与边界，不得堆砌同义反复的空话套话："
               "凡无落点、无取值、无判定标准的说明一律不加，完全重复的段落一律合并去重不得保留。")
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc", f"= t\n\n{dup}\n\n{dup}\n")
        cm.check_filler_docs()
        self.assertIn("完全重复", self.error_texts())

    def test_plain_summary_sentence_passes(self):
        # 无列表结构的普通小结句不得误报
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/cnb.adoc",
                   "= cnb\n\n以下规范适用于 CNB 平台上的任务开发与合并请求管理。\n")
        cm.check_filler_docs()
        self.assertEqual(cm.errors, [])

    def test_heading_word_with_list_content_passes(self):
        # 「示例/参考」类标题词后接列表内容属正常文档写法，不得误报（防误伤）
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc",
                   "= t\n\n参考：\n\n* 示例一：说清核心即可\n* 示例二：不得长篇大论\n")
        cm.check_filler_docs()
        self.assertEqual(cm.errors, [])

    def test_short_conclusion_sentence_passes(self):
        # 简短但有核心的结论句不得因“篇幅短”被判注水（不得长篇大论 ≠ 不得写短句）
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc",
                   "= t\n\n文档是给人读的，说清核心即可，不得长篇大论也不得凑字数。\n")
        cm.check_filler_docs()
        self.assertEqual(cm.errors, [])

    def test_word_with_placeholder_char_not_reported(self):
        # 『略』只作为『详略程度』等词的一部分时不得误报
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc",
                   "= t\n\n判定依据：按内容范围区分，不按详略程度区分，范围大者进独立文档。\n")
        cm.check_filler_docs()
        self.assertEqual(cm.errors, [])

    def test_format_only_line_passes(self):
        # 纯格式行（`：`、`——`、`**`）无实质内容但属版式，不判注水（防误报）
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc", "= t\n\n：\n\n——\n\n**\n")
        cm.check_filler_docs()
        self.assertEqual(cm.errors, [])

    def test_short_repeated_paragraph_reports(self):
        # 短而完全逐字重复的段落同样应被拦（避免阈值过高导致抓手失效）
        dup = "* 重复的短条目内容用以验证判定"
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc", f"= t\n\n{dup}\n\n{dup}\n")
        cm.check_filler_docs()
        self.assertIn("完全重复", self.error_texts())


# --------------------------------------------------------------------------- #
# check_index_page_guard（『索引页触发判据防线』）
# --------------------------------------------------------------------------- #
class TestCheckIndexPageGuard(CheckSpecsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._orig_files = (cm.DOC_FILE, cm.DOC_MODULE_FILE)
        cm.DOC_FILE = os.path.join(self.root, "specs", "general", "doc.adoc")
        cm.DOC_MODULE_FILE = os.path.join(self.root, "specs", "general", "doc-module.adoc")

    def tearDown(self) -> None:
        cm.DOC_FILE, cm.DOC_MODULE_FILE = self._orig_files
        super().tearDown()

    DOC = (
        "= 文档规范\n\n== 文档组织与导航\n\n"
        "* 文档目录即站点导航：已承载文档的目录须有索引页。\n"
        "* **索引页的触发判据（「该不该建索引页」）**：索引页是「有下级内容」时才需要——\n"
        "  ** 目录下已存在实质文档（已承载实质文档） → 建索引页；**空目录/仅有索引页「自己」一律不建**；\n"
        "  ** 索引页**只做导航**：不得把上一级文档（如模块 README）**换个壳复制**；\n"
        "  ** 模块级导航由模块 `README` 承担**：模块内若无独立功能文档，**不必**另设一层索引。\n"
    )
    MODULE = (
        "= 模块级文档规范\n\n"
        "* 模块 `doc/` 下**按需**放 `README.adoc` 作模块文档索引——判据是模块 `doc/` 下是否已承载实质文档：\n"
        "  ** 已承载模块内功能/组件文档 → 放 `README.adoc`；\n"
        "  ** 模块 `doc/` 下无任何实质文档 → **不建**；导航由**模块自身 `README`** 承担。\n"
    )

    def _write_valid(self):
        self.write("specs/general/doc.adoc", self.DOC)
        self.write("specs/general/doc-module.adoc", self.MODULE)

    def test_valid_passes(self):
        self._write_valid()
        cm.check_index_page_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_doc_file_reports(self):
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "general", "doc.adoc"))
        cm.check_index_page_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_trigger_clause_removed_reports(self):
        # 反例：判据节被删 → 只剩「每级目录须有索引页」，失效复发
        self._write_valid()
        self.write("specs/general/doc.adoc", "= 文档规范\n\n== 文档组织与导航\n* 每级目录须有索引页。\n")
        cm.check_index_page_guard()
        self.assertIn("索引页的触发判据", self.error_texts())

    def test_empty_shell_clause_removed_reports(self):
        # 反例：「空目录不建索引页」被删 → 批量空壳索引重新被允许
        self._write_valid()
        bad = self.DOC.replace(
            "**空目录/仅有索引页「自己」一律不建**", "**空目录也应补齐索引**")
        self.write("specs/general/doc.adoc", bad)
        cm.check_index_page_guard()
        self.assertIn("空目录", self.error_texts())

    def test_module_readme_clause_removed_reports(self):
        # 反例：模块级导航归属被删 → 「每个模块都该有 doc/README.adoc」重新成立
        self._write_valid()
        self.write("specs/general/doc-module.adoc",
                   "= 模块级文档规范\n\n* 模块 `doc/` 下**应放** `README.adoc`。\n")
        cm.check_index_page_guard()
        self.assertIn("doc-module.adoc", self.error_texts())


# integration：完整合法样例全通过
# --------------------------------------------------------------------------- #
class TestIntegration(CheckSpecsTestCase):
    def test_fully_valid_tree_passes_all_checks(self):
        _mk_blackbox_base(self.root)
        self.write("AGENTS_COMMON.adoc",
                   "执行 link:specs/core/execution.adoc[]；"
                   "Java 登记 `specs/stack/java.adoc`；"
                   "通用层 `specs/general/doc-design.adoc`")
        self.write("specs/core/execution.adoc",
                   "见 link:../general/doc-design.adoc[]；link:../stack/java.adoc[]")
        self.write("specs/general/doc-design.adoc", "= 设计文档")
        self.write("specs/stack/java.adoc", "= Java")
        self.write("AGENTS.adoc",
                   "规范调整：调整后必须开启干净子 agent 验证完整性；不得只定义不执行")

        cm.check_refs_exist()
        cm.check_link_refs()
        cm.check_stack_consistency()
        cm.check_forbidden_patterns()
        cm.check_historical_notes()
        cm.check_principle_guard()
        self.assertEqual(cm.errors, [])


# --------------------------------------------------------------------------- #
# check_priority_guard（规范优先级防线：最高关注项不得被删/降级）
# --------------------------------------------------------------------------- #
class TestCheckPriorityGuard(CheckSpecsTestCase):
    """钉住 L1/L2/L3 分级与最高关注项 P1-P6 的存在性、级别与正文口径。"""

    # P6 的正文（口径）也须核对：本条曾出现"清单里列着、正文却是旧口径"——
    # 公共侧已收紧为"强制同 Agent、不得点名外部 NPC"，P6 却停在"优先同源 + 外部来源
    # 作备选"，按最高关注项读的维护方会照旧把复核派给不可核对的外部执行者。
    P6 = ("=== P6. 协作执行者选择：子任务一律同 Agent，不得点名外部执行者\n\n"
          "* **要求（L1，最高）**：一律由与执行者相同的 Agent（同 Agent 身份、同入口）承担，"
          "不得点名外部 Agent / 外部 NPC；不可用时**降级**为由执行者本人串行承担，或如实标悬置。\n"
          "* **依据**：IEEE 1028 软件评审。\n")

    def _write_valid(self):
        # 分级定义与最高关注项的**公共口径**在 specs/core/execution.adoc；
        # P1-P5 的**维护方不可降级清单**在 specs-project-maintainer/priority.adoc。
        self.write("specs/core/execution.adoc",
                   "= 执行原则（必加载层）\n\n"
                   "== 分级与最高关注项（先读）\n\n"
                   "**L1 强制**/**L2 建议**/**L3 允许**\n\n"
                   "规范条目分三级，最高关注项**不可降级**：最高关注项与其引用允许多处出现，"
                   "但一处是完整定义、其余是**一行引用**（**强调**用升级别 + 单一定义 + 显式引用）。\n\n"
                   "== 范围控制\n\n读取按最小必要，禁止全库扫描。\n\n"
                   "== 文件操作强制检查\n\n文件移动必须使用 `git mv`，禁止 delete+create。\n\n"
                   "== 破坏性操作\n不可逆操作先确认。\n\n"
                   "== 自检\n不得顺口编造，不知道就去查证。\n"
                   "（引用 `specs/general/source.adoc` 与 `specs/general/self-check.adoc`）\n")
        self.write("specs/general/source.adoc", "= 依据与来源真实性规范（通用层）\n")
        self.write("specs/general/self-check.adoc", "= 执行前自检规范（通用层）\n")
        self.write("specs-project-maintainer/priority.adoc",
                   "= 最高关注项与不可降级清单（维护方自查）\n\n"
                   "最高关注项**不可降级**：\n\n"
                   "=== P1. 文件移动/重命名必须用 `git mv`\n\n"
                   "* **要求（L1，最高）**：不得用 delete+create 代替。\n"
                   "* **依据**：变更可追溯（ISO 10007）。\n\n"
                   "=== P2. 规范完整性校验\n\n"
                   "* **要求（L1，最高）**：改完必须跑机械校验。\n"
                   "* **依据**：ISO/IEC/IEEE 29148。\n\n"
                   "=== P3. 内容不得减少\n\n"
                   "* **要求（L1，最高）**：内容一项不能少。\n"
                   "* **依据**：ISO 9001。\n\n"
                   "=== P4. 读取按最小必要；执行轮次须合并（少绕）\n\n"
                   "* **要求（L2 建议，最高关注项）**：只读最小必要信息集；执行轮次须合并（少绕，避免可供合并的调用被拆成多轮）。\n"
                   "* **依据**：Anthropic 工程博客《Effective context engineering for AI agents》。\n\n"
                   "=== P5. 不可逆操作先确认，不得编造事实与来源\n\n"
                   "* **要求（L1，最高）**：不可逆操作先确认；不得编造事实与来源。\n"
                   "* **依据**：ISO 10007。\n\n"
                   + self.P6)
        self.write("AGENTS.adoc",
                   "登记 `specs-project-maintainer/priority.adoc`\n"
                   "登记 `specs-project-maintainer/spec-lifecycle.adoc`\n"
                   "登记 `specs-project-maintainer/verify.adoc`\n"
                   "登记 `specs-project-maintainer/context.adoc`\n")
        # 分级/最高关注项本身也被 P2 等防线读取：给出最小可识别的公共文件
        self.write("AGENTS_COMMON.adoc", "= t\n")

    def test_valid_priority_file_passes(self):
        self._write_valid()
        cm.check_priority_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_priority_file_reports(self):
        # 反例：维护方的最高关注项清单整体被删
        self._write_valid()
        os.remove(os.path.join(self.root, "specs-project-maintainer", "priority.adoc"))
        cm.check_priority_guard()
        self.assertIn("缺少维护方最高关注项清单", self.error_texts())

    def test_missing_level_definition_reports(self):
        # 反例：公共分级定义被删（只剩 L1，L2/L3 消失）
        self._write_valid()
        self.write("specs/core/execution.adoc",
                   "= 执行原则\n\n**L1 强制**\n不可降级 git mv 破坏性操作 source.adoc 范围控制 一行引用 强调\n")
        cm.check_priority_guard()
        self.assertIn("L2 建议", self.error_texts())
        self.assertIn("L3 允许", self.error_texts())

    def test_dropped_top_priority_item_reports(self):
        # 反例：最高关注项 P1 被删（重构/去重最危险的误删）
        self.write("specs-project-maintainer/priority.adoc",
                   "= t\n**L1 强制**/**L2 建议**/**L3 允许**\n"
                   "不可降级 P2 完整性 P3 内容不得减少 P4 读取按最小必要 P5 不可逆操作\n")
        self.write("specs/core/execution.adoc",
                   "git mv context.adoc 破坏性操作 source.adoc")
        cm.check_priority_guard()
        self.assertIn("P1", self.error_texts())

    def test_dropped_p6_reports(self):
        # 反例：最高关注项 P6（协作执行者选择）被删 —— 与公共侧"强制同 Agent"的
        # 不可降级保护落点一起消失（清单里不再有这项，重构时会顺手清掉）
        self._write_valid()
        path = os.path.join(self.root, "specs-project-maintainer", "priority.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace("=== P6. 协作执行者选择：子任务一律同 Agent，不得点名外部执行者", "=== 协作方式")
        self.write("specs-project-maintainer/priority.adoc", text)
        cm.check_priority_guard()
        self.assertIn("P6", self.error_texts())

    def test_p6_stale_wording_reports(self):
        # 反例（**本轮实际发生的漏改**）：名字与级别还在、正文却是旧口径
        # （"优先同源 + 外部来源作备选"）→ 按最高关注项读的维护方继续派外部执行者。
        # 只核小标题/级别/依据行的旧防线对这种情形全绿，故此处必须报。
        self._write_valid()
        path = os.path.join(self.root, "specs-project-maintainer", "priority.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace(
                self.P6,
                "=== P6. 协作执行者选择\n\n"
                "* **要求（L1，最高）**：需要子 Agent 时优先用与执行者同源的执行者承担，"
                "外部来源（外部 NPC/另一个产品）只是同源不可用后的备选。\n"
                "* **依据**：IEEE 1028 软件评审。\n")
        self.write("specs-project-maintainer/priority.adoc", text)
        cm.check_priority_guard()
        self.assertIn("旧口径", self.error_texts())

    def test_p6_keyword_only_reports(self):
        # 反例：只留新口径的关键词、整条要求被抽掉（防"关键词出现过一次"式假绿）
        self._write_valid()
        path = os.path.join(self.root, "specs-project-maintainer", "priority.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace(
                self.P6,
                "=== P6. 协作执行者选择\n\n"
                "* **要求（L1，最高）**：不得点名外部 Agent。\n"
                "* **依据**：IEEE 1028。\n")
        self.write("specs-project-maintainer/priority.adoc", text)
        cm.check_priority_guard()
        self.assertIn("同 Agent 身份", self.error_texts())

    def test_dropped_non_downgrade_declaration_reports(self):
        # 反例：去掉"不可降级"声明 = 允许最高关注项被降级（公共口径在 execution.adoc）
        self._write_valid()
        path = os.path.join(self.root, "specs", "core", "execution.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace("最高关注项**不可降级**", "最高关注项")
        self.write("specs/core/execution.adoc", text)
        cm.check_priority_guard()
        self.assertIn("不可降级", self.error_texts())

    def test_execution_missing_git_mv_reports(self):
        # 反例：最高关注项 P1 的必加载层落点被改写
        self._write_valid()
        self.write("specs/core/execution.adoc", "文件操作见相关规范\n")
        cm.check_priority_guard()
        self.assertIn("git mv", self.error_texts())

    def test_leveling_method_moved_back_to_always_on_reports(self):
        # 反例：分级定义（读条目"该怎么做"的底线）被误删；分级必须留在公共层
        self._write_valid()
        path = os.path.join(self.root, "specs", "core", "execution.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace("**L1 强制**/**L2 建议**/**L3 允许**", "只分 L1")
        self.write("specs/core/execution.adoc", text)
        cm.check_priority_guard()
        self.assertIn("L2 建议", self.error_texts())

    def test_dropped_how_to_walk_declaration_reports(self):
        # 反例：最高关注项的保留形态（一处完整定义 + 其余一行引用）被删
        self._write_valid()
        path = os.path.join(self.root, "specs", "core", "execution.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace("一行引用", "随便引用")
        self.write("specs/core/execution.adoc", text)
        cm.check_priority_guard()
        self.assertIn("一行引用", self.error_texts())

    def test_dropped_basis_line_reports(self):
        # 反例：某最高关注项的『依据』行被整段删掉（依据可压成标准名/编号，但不能消失）
        self._write_valid()
        path = os.path.join(self.root, "specs-project-maintainer", "priority.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace("* **依据**：ISO 10007。\n", "")
        self.write("specs-project-maintainer/priority.adoc", text)
        cm.check_priority_guard()
        self.assertIn("依据", self.error_texts())

    def test_silently_downgraded_p1_reports(self):
        # 反例：P1-P3 被静默从 L1 降级为 L2（最高关注项条款本身即 L1 铁律）
        self._write_valid()
        path = os.path.join(self.root, "specs-project-maintainer", "priority.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace(
                "**要求（L1，最高）**：不得用 delete+create 代替。",
                "**要求（L2 建议）**：不得用 delete+create 代替。")
        self.write("specs-project-maintainer/priority.adoc", text)
        cm.check_priority_guard()
        self.assertIn("P1", self.error_texts())

    def test_silently_promoted_p4_reports(self):
        # 反例：P4 被静默从 L2 改标为 L1（级别不得顺手改写，须按定级口径判定）
        self._write_valid()
        path = os.path.join(self.root, "specs-project-maintainer", "priority.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace(
                "* **要求（L2 建议，最高关注项）**：只读最小必要信息集；执行轮次须合并"
                "（少绕，避免可供合并的调用被拆成多轮）。",
                "* **要求（L1，最高）**：只读最小必要信息集；执行轮次须合并"
                "（少绕，避免可供合并的调用被拆成多轮）。")
        self.write("specs-project-maintainer/priority.adoc", text)
        cm.check_priority_guard()
        self.assertIn("P4", self.error_texts())

    def test_p4_missing_throughput_half_reports(self):
        # 反例：P4 只留「少读」、把「少绕」（执行轮次须合并）那一半删掉——
        # 轮次是上下文的乘数，缺这一半时执行者会把可合并的调用拆成多轮
        self._write_valid()
        path = os.path.join(self.root, "specs-project-maintainer", "priority.adoc")
        with open(path, encoding="utf-8") as fh:
            text = (fh.read()
                    .replace("=== P4. 读取按最小必要；执行轮次须合并（少绕）",
                             "=== P4. 读取按最小必要")
                    .replace("；执行轮次须合并（少绕，避免可供合并的调用被拆成多轮）。", "。"))
        self.write("specs-project-maintainer/priority.adoc", text)
        cm.check_priority_guard()
        self.assertIn("少绕", self.error_texts())

    def test_silently_downgraded_p5_reports(self):
        # 反例：P5 被静默从 L1 降级为 L2（不可逆操作与来源真实性属无裁量余地的底线）
        self._write_valid()
        path = os.path.join(self.root, "specs-project-maintainer", "priority.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace(
                "**要求（L1，最高）**：不可逆操作先确认；不得编造事实与来源。",
                "**要求（L2 建议）**：不可逆操作先确认；不得编造事实与来源。")
        self.write("specs-project-maintainer/priority.adoc", text)
        cm.check_priority_guard()
        self.assertIn("P5", self.error_texts())

    def test_dropped_context_read_item_reports(self):
        # 反例：最高关注项 P4（读取按最小必要/长会话上下文治理）被删
        self.write("specs-project-maintainer/priority.adoc",
                   "= t\n**L1 强制**/**L2 建议**/**L3 允许**\n"
                   "不可降级 P1 git mv P2 完整性 P3 内容不得减少\n")
        self.write("specs/core/execution.adoc",
                   "git mv context.adoc 破坏性操作 source.adoc")
        cm.check_priority_guard()
        self.assertIn("P4", self.error_texts())

    def test_execution_missing_context_ref_reports(self):
        # 反例：最高关注项 P4 的必加载层落点（执行原则对其的引用）被改写
        self._write_valid()
        self.write("specs/core/execution.adoc", "读取范围见相关规范\n")
        cm.check_priority_guard()
        self.assertIn("范围控制", self.error_texts())

    def test_dropped_destructive_op_item_reports(self):
        # 反例：最高关注项 P5（不可逆操作先确认 + 不得编造）被删
        self.write("specs-project-maintainer/priority.adoc",
                   "= t\n**L1 强制**/**L2 建议**/**L3 允许**\n"
                   "不可降级 P1 git mv P2 完整性 P3 内容不得减少 P4 读取按最小必要\n")
        self.write("specs/core/execution.adoc",
                   "git mv context.adoc 破坏性操作 source.adoc")
        cm.check_priority_guard()
        self.assertIn("P5", self.error_texts())

    def test_execution_missing_destructive_section_reports(self):
        # 反例：P5 的必加载层落点（「破坏性操作」一节）被删
        self._write_valid()
        self.write("specs/core/execution.adoc",
                   "git mv context.adoc source.adoc\n")
        cm.check_priority_guard()
        self.assertIn("破坏性操作", self.error_texts())

    def test_execution_missing_source_ref_reports(self):
        # 反例：P5 的落点（"不得顺口编造"与来源真实性引用）被删
        self._write_valid()
        self.write("specs/core/execution.adoc",
                   "**L1 强制**/**L2 建议**/**L3 允许** 最高关注项 **不可降级** 一行引用 强调\n"
                   "git mv 破坏性操作 范围控制\n")
        cm.check_priority_guard()
        self.assertIn("不得编造事实与来源", self.error_texts())


# --------------------------------------------------------------------------- #
# check_spec_admission_guard（规范准入防线：分类/准入与提案校验口径不得被删）
# --------------------------------------------------------------------------- #
class TestCheckAdmissionGuard(CheckSpecsTestCase):
    """钉住规范分类与准入文件的存在性、要点、调度器登记与项目落点。

    准入口径（公共/项目归属、分层判定、该不该收、提案如何校验与升级）是后续新增
    规范的判定依据，被"精简/去重"顺手删掉后新增就会回到零散追加，故与最高关注项
    一样加机械防线。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_admission = cm.ADMISSION_FILE
        cm.ADMISSION_FILE = os.path.join(self.root, "specs-project-maintainer", "spec-lifecycle.adoc")

    def tearDown(self) -> None:
        cm.ADMISSION_FILE = self._orig_admission
        super().tearDown()

    def _write_valid(self):
        # 实现用「仓库根相对路径」登记/引用（与调度器口径一致），测试文件写在临时根下
        self.write("specs-project-maintainer/spec-lifecycle.adoc",
                   "= 规范分类与准入\n\n"
                   "== 公共规范还是项目规范（归属判定）\n\n"
                   "== 准入判定（该不该收进规范集合）\n\n"
                   "== 如何给一条规范定级（定级口径四问）\n\n"
                   "=== 与条款类型一一对应（L1 / L2 / L3 判定表）\n\n"
                   "=== 归属谁（对象 × 强度两维判定）\n\n"
                   "=== 归类举证（写入规范时同步登记）\n\n"
                   "=== 级别变更与复盘（防降级、防级别混乱）\n\n"
                   "== 新增规范的提案校验\n\n"
                   "检查是否已有标准；检查是否已有本项目条目；升级与举一反三。\n\n"
                   "== 同一条规则有两种读法（读的形态要跟着场景变）\n\n"
                   "执行场景只给规则与判定标准；依据与取舍归思考/决策场景。\n\n"
                   "== 规范集合的自身重构（瘦身与归位）\n\n"
                   "先判归属 → 再判层级 → 再判重复 → 最后压缩表述。\n"
                   "重构后须核对规范有效性（两形态分离 / 可执行性不降级 / 可见性不丢）。\n")
        self.write("AGENTS_COMMON.adoc",
                   "通用层登记 `specs-project-maintainer/spec-lifecycle.adoc`")
        self.write("AGENTS.adoc", "见 `specs-project-maintainer/spec-lifecycle.adoc`")

    def test_valid_admission_spec_passes(self):
        self._write_valid()
        cm.check_spec_admission_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_admission_file_reports(self):
        # 反例：准入规范文件整体被删（新增规范失去判定依据）
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("AGENTS.adoc", "= t")
        cm.check_spec_admission_guard()
        self.assertIn("缺少规范分类与准入文件", self.error_texts())

    def test_dropped_key_point_reports(self):
        # 反例：准入判定被删（只剩归属判定）→ 准入抓手失效
        self.write("specs-project-maintainer/spec-lifecycle.adoc",
                   "= t\n\n== 公共规范还是项目规范\n\n== 提案校验\n\n"
                   "检查是否已有标准；检查是否已有本项目条目；升级与举一反三。\n")
        self.write("AGENTS_COMMON.adoc", "登记 `specs-project-maintainer/spec-lifecycle.adoc`")
        self.write("AGENTS.adoc", "见 `specs-project-maintainer/spec-lifecycle.adoc`")
        cm.check_spec_admission_guard()
        self.assertIn("准入判定", self.error_texts())

    def test_dropped_escalation_point_reports(self):
        # 反例：举一反三（升级要求）被删 → 新增只会照抄用户原话
        self.write("specs-project-maintainer/spec-lifecycle.adoc",
                   "= t\n\n== 公共规范还是项目规范\n\n== 准入判定\n\n"
                   "== 提案校验\n\n检查是否已有标准；检查是否已有本项目条目。\n")
        self.write("AGENTS_COMMON.adoc", "登记 `specs-project-maintainer/spec-lifecycle.adoc`")
        self.write("AGENTS.adoc", "见 `specs-project-maintainer/spec-lifecycle.adoc`")
        cm.check_spec_admission_guard()
        self.assertIn("举一反三", self.error_texts())

    def test_dropped_leveling_criteria_reports(self):
        # 反例：定级口径（四问/判定表等）被删 → 条目级别再无判定依据、级别会重新混乱
        self._write_valid()
        path = os.path.join(self.root, "specs-project-maintainer", "spec-lifecycle.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        text = text.split("== 如何给一条规范定级")[0] + "== 新增规范的提案校验\n\n" + \
            text.split("== 新增规范的提案校验")[1]
        self.write("specs-project-maintainer/spec-lifecycle.adoc", text)
        cm.check_spec_admission_guard()
        self.assertIn("如何给一条规范定级", self.error_texts())

    def test_dropped_refactor_order_reports(self):
        # 反例：规范自身重构的判断顺序被删 → 会先删后想，把放错位置的内容直接删掉
        self._write_valid()
        path = os.path.join(self.root, "specs-project-maintainer", "spec-lifecycle.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.write("specs-project-maintainer/spec-lifecycle.adoc",
                   text.replace("先判归属 → 再判层级 → 再判重复 → 最后压缩表述。", "重构一下。"))
        cm.check_spec_admission_guard()
        self.assertIn("先判归属", self.error_texts())

    def test_dropped_reading_shape_reports(self):
        # 反例：读法形态判据被删 → "执行侧只给怎么走、依据归决策侧"的口径丢失，
        # 规范重新变成"给执行者一堆解释"或"为简洁把依据删掉"两个极端
        self._write_valid()
        path = os.path.join(self.root, "specs-project-maintainer", "spec-lifecycle.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        text = text.split("== 同一条规则有两种读法")[0] + "== 规范集合的自身重构" + \
            text.split("== 规范集合的自身重构")[1]
        self.write("specs-project-maintainer/spec-lifecycle.adoc", text)
        cm.check_spec_admission_guard()
        self.assertIn("同一条规则有两种读法", self.error_texts())

    def test_dropped_effectiveness_check_reports(self):
        # 反例：重构后的有效性核对被删 → 只查"内容丢没丢"，判据被压成口号/依据被删无人拦
        self._write_valid()
        path = os.path.join(self.root, "specs-project-maintainer", "spec-lifecycle.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace(
                "重构后须核对规范有效性（两形态分离 / 可执行性不降级 / 可见性不丢）。\n", "")
        self.write("specs-project-maintainer/spec-lifecycle.adoc", text)
        cm.check_spec_admission_guard()
        self.assertIn("重构后须核对规范有效性", self.error_texts())

    def test_not_registered_in_project_spec_reports(self):
        # 反例：文件存在但未在维护方入口 AGENTS.adoc 登记 → 永不被加载、规则实际失效
        self._write_valid()
        self.write("AGENTS.adoc", "= 项目自身规范\n")
        cm.check_spec_admission_guard()
        self.assertIn("未在", self.error_texts())
        self.assertIn("登记", self.error_texts())


# --------------------------------------------------------------------------- #
# check_section_refs（节名引用存在性：防改名后引用悬空）
# --------------------------------------------------------------------------- #
class TestCheckSectionRefs(CheckSpecsTestCase):
    def test_existing_section_ref_passes(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc-design.adoc", "= 设计文档规范\n\n== 信息归属\n\n内容")
        self.write("specs/general/doc.adoc",
                   "见 link:../general/doc-design.adoc[]「信息归属」")
        cm.check_section_refs()
        self.assertEqual(cm.errors, [])

    def test_renamed_section_reports(self):
        # 反例：目标节已改名，引用仍指向旧节名
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc-design.adoc", "= 设计文档规范\n\n== 信息归属\n\n内容")
        self.write("specs/general/doc.adoc",
                   "见 link:../general/doc-design.adoc[]「判定依据」")
        cm.check_section_refs()
        self.assertNotEqual(cm.errors, [])
        self.assertIn("不存在的节名", self.error_texts())
        self.assertIn("判定依据", self.error_texts())

    def test_section_with_parenthetical_passes(self):
        # 目标节名带括号说明，引用省略括号部分也应通过
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc-design.adoc", "= t\n\n=== 信息归属（同一信息只写一处）\n\n内容")
        self.write("specs/general/doc.adoc", "见 link:../general/doc-design.adoc[]「信息归属」")
        cm.check_section_refs()
        self.assertEqual(cm.errors, [])

    def test_non_adoc_and_external_targets_skipped(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc",
                   "link:https://example.com/x[]「任意」 link:#anch[]「任意」")
        cm.check_section_refs()
        self.assertEqual(cm.errors, [])

    def test_parallel_sections_second_reported(self):
        # 同一 link 后并列多个节名时，第二个也须校验
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc-design.adoc", "= t\n\n=== 信息归属\n\n内容")
        self.write("specs/general/doc.adoc",
                   "见 link:../general/doc-design.adoc[]「信息归属」「不存在的节」")
        cm.check_section_refs()
        self.assertIn("不存在的节", self.error_texts())

    def test_parenthetical_inner_alias_passes(self):
        # 节名 `分类与懒加载（加载调度器）` 的括号内文字可作为别名引用
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/target.adoc", "= t\n\n== 分类与懒加载（加载调度器）\n\n内容")
        self.write("specs/general/doc.adoc", "见 link:../general/target.adoc[]「加载调度器」")
        cm.check_section_refs()
        self.assertEqual(cm.errors, [])

    def test_intra_file_section_ref_passes(self):
        # 正例：写"同文件「节名」"且该节确实在本文件内 —— 应通过
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc",
                   "= t\n\n== 信息归属\n\n内容\n\n见同文件「信息归属」")
        cm.check_section_refs()
        self.assertEqual(cm.errors, [])

    def test_library_file_section_refs_are_checked(self):
        # 图书馆文件（仓库根 library/）纳入节名检查 —— 原实现漏收 library/**，
        # 其悬空节名无人发现（实测 library/README.adoc 曾有三处）
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc", "= 文档\n\n== 注释与文档\n")
        self.write("library/README.adoc",
                   "= 图书馆\n\n见 link:../specs/general/doc.adoc[]「不存在的节」\n")
        cm.check_section_refs()
        self.assertIn("不存在的节名", self.error_texts())

    def test_library_file_valid_section_refs_pass(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc", "= 文档\n\n== 注释与文档\n")
        self.write("library/README.adoc",
                   "= 图书馆\n\n见 link:../specs/general/doc.adoc[]「注释与文档」\n")
        cm.check_section_refs()
        self.assertEqual(cm.errors, [])

    def test_intra_file_section_ref_dangling_reports(self):
        # 反例：写"同文件「节名」"但本文件无此节（节实际在另一个文件）—— 须报悬空
        # （曾实测：verify.adoc 写"见同文件「规范集合的自身重构」"，而该节在
        #  spec-lifecycle.adoc，link: 式检查拦不住这类自然语言指向）
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc",
                   "= t\n\n== 真节\n\n内容\n\n见同文件「规范集合的自身重构」")
        cm.check_section_refs()
        self.assertNotEqual(cm.errors, [])
        self.assertIn("同文件「规范集合的自身重构」", self.error_texts())
        self.assertIn("在本文件不存在", self.error_texts())

    def test_intra_file_section_ref_with_parenthetical_passes(self):
        # 正例：本文件节名带括号说明，"同文件「简化名」"也应通过
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc",
                   "= t\n\n== 信息归属（同一信息只写一处）\n\n内容\n\n见同文件「信息归属」")
        cm.check_section_refs()
        self.assertEqual(cm.errors, [])

    def test_codeblock_heading_not_collected(self):
        # `----` 代码块内形如 `= xxx` 的行不得被当作节名（防漏报转误报）
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/target.adoc", "= t\n\n----\n= 代码块内的行\n----\n\n== 真节\n")
        self.write("specs/general/doc.adoc", "见 link:../general/target.adoc[]「代码块内的行」")
        cm.check_section_refs()
        self.assertIn("不存在的节名", self.error_texts())


# --------------------------------------------------------------------------- #
# 校验范围（不得检查 git 工作区 / 引用方项目）
# --------------------------------------------------------------------------- #
class TestScopeStaysOnCommonContent(CheckSpecsTestCase):
    """回归：机械校验只针对本仓库维护的规范/模板文本。

    背景：本仓库的绝大多数内容是**给其他项目用**的公共规范（`AGENTS_COMMON.adoc` +
    `specs/`）。面向"引用方项目工作区"的检查在本仓库既看不到对象、又对引用方无效
    （引用方用规范入口全文引用，不可能引用本仓库的脚本），只会白白给本仓库 CI
    加约束，故不得再引入（历史上曾有 `check_git_mv_usage` 被移除）。

    **边界（本仓库自身 vs 引用方）**：本仓库自己也是 git 工作区，其**暂存区**可核对，
    故允许且仅允许"本仓库自身侧"的 `git mv` 自查（`check_git_mv_selfcheck`：只读
    `git diff --cached --diff-filter=AD` 的状态行，不读工作区文件内容、不做逐文件
    比较，非 git 目录/无 git 一律跳过）。越出这条边界（读工作区文件内容、`git status`
    扫描、比较 HEAD 内容、把结论套到引用方）即属违规——那才是本用例要钉住的。
    """

    def test_no_workspace_file_reads(self):
        # 判据是"是否越界读工作区内容/扫工作区状态"，不是"是否出现 git 字样"：
        # 规范正文与"自身侧暂存区自查"里出现 git 调用属正常，故只钉住处界调用。
        src = open(os.path.join(HERE, "check_specs.py"), encoding="utf-8").read()
        for bad in ("git status", "HEAD:{", "--name-only", "ls-files"):
            self.assertNotIn(bad, src,
                             f"check_specs.py 不得越界读取工作区状态/文件内容（发现 {bad!r}）："
                             "本仓库内容主要给其他项目用，引用方工作区操作不可见；"
                             "自身侧只允许读暂存区的 `diff --cached --diff-filter=AD` 状态行")

    def test_self_side_git_check_is_bounded(self):
        # 正例：自身侧 git mv 自查必须是"暂存区状态行 + 跳过条件齐备"的受限实现
        src = open(os.path.join(HERE, "check_specs.py"), encoding="utf-8").read()
        self.assertIn("check_git_mv_selfcheck", src)
        body = src[src.index("def check_git_mv_selfcheck"):]
        body = body[:body.index(chr(10) + "def ")]
        self.assertIn("--cached", body, "须只查暂存区")
        self.assertIn("--diff-filter=AD", body, "须只取删除/新增两类状态")
        self.assertIn("os.path.isdir", body, "须在非 git 目录时跳过（保持幂等）")
        self.assertNotIn("open(", body, "不得读工作区文件内容")

    def test_lowered_rename_threshold_for_rewritten_moves(self):
        # 改写式移动（内容大幅重写，相似度低于 git 默认 50%）须仍被识别为 rename：
        # 阈值须低于默认值，否则合规的 `git mv` + 改写会被误判成 delete+create
        src = open(os.path.join(HERE, "check_specs.py"), encoding="utf-8").read()
        body = src[src.index("def check_git_mv_selfcheck"):]
        body = body[:body.index(chr(10) + "def ")]
        self.assertIn("-M10%", body,
                      "须用低于默认阈值的 -M10%（本仓库实证：搬家时入口被整篇重写，"
                      "相似度跌到 16%，默认阈值下只剩 删除+新增）")

    def test_git_untracked_file_does_not_break_checks(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc", "= 文档\n\n简短但有实质内容的一句话规则。\n")
        # 工作区存在未跟踪文件（模拟"delete+create 之类的工作区形态"）不得影响结论
        self.write("品牌新文件.adoc", "= x\n\n与本规范集合无关的内容。\n")
        cm.check_filler_docs()
        self.assertEqual(cm.errors, [])


# --------------------------------------------------------------------------- #
# check_principle_guard（规范要点防线：防『定义验证却不执行/被误删』）
# --------------------------------------------------------------------------- #
class TestCheckPrincipleGuard(CheckSpecsTestCase):
    def test_principle_present_passes(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("AGENTS.adoc",
                   "规范调整：调整后必须开启干净子 agent 验证完整性；不得只定义不执行")
        cm.check_principle_guard()
        self.assertEqual(cm.errors, [])

    def test_validation_keyword_removed_reports(self):
        # 反例：删掉了「完整性校验/子 agent 复核」约定（只定义校验、不要求执行）
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("AGENTS.adoc", "规范调整：写成文档即可，无需后续动作")
        cm.check_principle_guard()
        self.assertIn("要点防线被破坏", self.error_texts())
        self.assertIn("子 agent", self.error_texts())
        self.assertIn("完整性", self.error_texts())

    def test_missing_management_file_reports(self):
        self.write("AGENTS_COMMON.adoc", "= t")  # 未创建根目录 AGENTS.adoc
        cm.check_principle_guard()
        self.assertIn("缺少 Agent 项目自身规范入口", self.error_texts())



def _valid_usage_body() -> str:
    """生成一份含全部要点锚点的『依据的写入与关联』主题正文（正例基准）。

    与 `cm._LIBRARY_USAGE_ANCHORS` 同源：锚点即判据句/节名，缺一即"写入靠自觉、
    关联凭印象"会被读回来（写入无触发判据、反查无算法）。**定位协议的使用判据**
    （第四节）由 `_LIBRARY_LOCATING_USAGE_ANCHORS` 承载，本函数一并写入——
    两处合起来才是完整的"写入 + 关联 + 定位"协议。
    """
    head = "= 依据的写入与关联（图书馆使用协议）\n\n本文件是依据图书馆的主题之一。\n\n"
    return (head + "\n".join("- " + q for q in cm._LIBRARY_USAGE_ANCHORS)
            + "\n" + "\n".join("- " + q for q in cm._LIBRARY_LOCATING_USAGE_ANCHORS) + "\n")


def _valid_adoption_body() -> str:
    """生成一份含全部要点锚点的『规范准入与自身取舍』主题正文（正例基准）。

    与 `cm._LIBRARY_ADOPTION_ANCHORS` 同源：锚点即判据句，缺一即"同义性差异未写明"。
    """
    head = "= 规范准入与自身取舍的依据（依据图书馆）\n\n本文件是依据图书馆的主题之一。\n\n"
    return head + "\n".join("- " + q for q in cm._LIBRARY_ADOPTION_ANCHORS) + "\n"


class TestCheckLibraryGuard(CheckSpecsTestCase):
    """钉住『图书馆防线』：依据须查得到、对得上、引用不悬空（不在默认引用面内的内容）。

    依据不能只存在名称——规则执行久了就退化成"只记得是这么做的"，无法判断它还成不
    成立、无法据以取舍（specs/general/verify.adoc「验证总纲」的"防慢慢脱离初衷"）。
    图书馆（**仓库根 `library/`**）**不在默认引用面内**（本仓库内容全部会发布出去，
    区别只在"默认引用什么"——它没有公共加载项、引用方工作区里也没有本仓库的文件），
    是依据的落点，故其存在性、入口登记、逐字引文与引用可解析性都由本条机械钉住；
    **不按"自足性/是否夹带私有落点"口径核对**——那是对默认引用项的要求（不在默认
    引用面内的内容本就可以引用自己仓库的任何落点），图书馆落在仓库根后该口径不再适用。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_lib = (cm.LIBRARY_DIR, cm.LIBRARY_INDEX, cm.LIBRARY_TOPICS)
        self._orig_project = cm.PROJECT_FILE
        cm.LIBRARY_DIR = os.path.join(self.root, "library")
        cm.LIBRARY_INDEX = os.path.join(cm.LIBRARY_DIR, "README.adoc")
        cm.LIBRARY_TOPICS = ("sources.adoc", "adoption.adoc", "usage.adoc")
        cm.PROJECT_FILE = os.path.join(self.root, "AGENTS.adoc")

    def tearDown(self) -> None:
        (cm.LIBRARY_DIR, cm.LIBRARY_INDEX, cm.LIBRARY_TOPICS) = self._orig_lib
        cm.PROJECT_FILE = self._orig_project
        super().tearDown()

    def _write_valid(self) -> None:
        # 项目规范入口登记图书馆入口（写文件与登记是同一个动作）
        self.write("AGENTS.adoc",
                   "= 项目规范\n\n依据图书馆入口 library/README.adoc（见下「依据图书馆」）。\n")
        self.write("library/README.adoc",
                   "= 图书馆\n\n| link:sources.adoc[] | 外部标准原文摘录\n"
                   "| link:adoption.adoc[] | 规范准入与自身取舍的依据——同义性差异与覆盖点\n"
                   "| link:usage.adoc[] | 依据的写入与关联：触发特征、入库必写项、反查算法\n")
        self.write("library/sources.adoc",
                   "= 外部标准原文摘录\n\n"
                   + "\n".join("- " + q for q in cm.LIBRARY_QUOTE_ANCHORS)
                   + "\n")
        self.write("library/adoption.adoc", _valid_adoption_body())
        self.write("library/usage.adoc", _valid_usage_body())

    def test_valid_library_passes(self):
        self._write_valid()
        cm.check_library_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_library_index_reports(self):
        # 反例：图书馆入口整体被删（依据将只剩名称、无从核对）
        self._write_valid()
        os.remove(cm.LIBRARY_INDEX)
        cm.check_library_guard()
        self.assertIn("缺少图书馆入口", self.error_texts())

    def test_unregistered_in_project_entry_reports(self):
        # 反例：图书馆未在项目规范入口登记（读者无从知道何时加载它）
        self._write_valid()
        self.write("AGENTS.adoc", "= 项目规范\n")
        cm.check_library_guard()
        self.assertIn("未在本仓库项目规范入口", self.error_texts())

    def test_registered_topic_missing_file_reports(self):
        # 反例：入口登记了不存在的主题文件（读者按入口找不到依据）
        self._write_valid()
        self.write("library/README.adoc",
                   "= 图书馆\n\n| link:sources.adoc[] | 外部标准原文摘录\n| link:gone.adoc[] | 不存在\n")
        cm.check_library_guard()
        self.assertIn("不存在的主题文件", self.error_texts())

    def test_orphan_topic_file_reports(self):
        # 反例：主题目录里有文件却未登记（依据实际不可达）
        self._write_valid()
        self.write("library/internal.adoc", "= 未登记的主题\n")
        cm.check_library_guard()
        self.assertIn("未登记的主题文件", self.error_texts())

    def test_quote_anchor_deleted_reports(self):
        # 反例：逐字引文被压成名称（依据无从核对 = 图书馆的价值消失）
        self._write_valid()
        self.write("library/sources.adoc",
                   "= 外部标准原文摘录\n\n- RFC 2119 见官方文档\n")
        cm.check_library_guard()
        self.assertIn("缺失逐字引文锚点", self.error_texts())

    def test_dangling_ref_in_library_reports(self):
        # 反例：馆内引用悬空（依据链断在这里）——`specs/...` 反引号写法按仓库根解析
        self._write_valid()
        self.write("library/sources.adoc",
                   "= 外部标准原文摘录\n\n见 `specs/general/gone.adoc`\n"
                   + "\n".join("- " + q for q in cm.LIBRARY_QUOTE_ANCHORS)
                   + "\n")
        cm.check_library_guard()
        self.assertIn("指向不存在的文件", self.error_texts())

    def test_link_dangling_in_library_reports(self):
        # 反例：馆内 link: 引用悬空（相对本文件目录解析）
        self._write_valid()
        self.write("library/sources.adoc",
                   "= 外部标准原文摘录\n\n见 link:../specs/general/gone.adoc[]\n"
                   + "\n".join("- " + q for q in cm.LIBRARY_QUOTE_ANCHORS)
                   + "\n")
        cm.check_library_guard()
        self.assertIn("指向不存在的文件", self.error_texts())

    def _write_topic_body(self, body: str) -> None:
        """把 `body` 写进主题文件正文（避开入口登记表：表里的 link: 会被当作主题登记）。"""
        self.write("library/sources.adoc",
                   "= 外部标准原文摘录\n\n" + body + "\n"
                   + "\n".join("- " + q for q in cm.LIBRARY_QUOTE_ANCHORS) + "\n")

    def test_root_level_name_link_form_dangling_reports(self):
        # 反例：馆内以**根级文件名 + link: 写法**引用（`link:CHANGELOG.adoc[]`）而该文件不存在
        # 依据：馆内引用一律按仓库根基准——根级名走 link: 形态**同样是引用写法**，
        # 悬空即断链（原实现只按"本文件所在目录"解析 link: → 解析成 library/CHANGELOG.adoc，
        # 与反引号形态的基准不一致：文件缺失时 link: 形态漏报、文件在时又误报）
        self._write_valid()
        self._write_topic_body("变更历史见 link:CHANGELOG.adoc[]。")
        cm.check_library_guard()
        self.assertIn("指向不存在的文件", self.error_texts())

    def test_root_level_name_link_form_resolvable_passes(self):
        # 正例：根级文件名走 link: 形态、文件真实存在 → 不报（与反引号形态同一基准）
        self._write_valid()
        self.write("CHANGELOG.adoc", "= 变更历史\n")
        self._write_topic_body("变更历史见 link:CHANGELOG.adoc[]。")
        cm.check_library_guard()
        self.assertEqual(cm.errors, [])

    def test_ref_base_is_single_for_both_forms(self):
        # 钉住"同一引用只有一个基准"：同一文件两种写法（反引号 / link:）结论必须一致
        for form, label in (("`CHANGELOG.adoc`", "backtick"), ("link:CHANGELOG.adoc[]", "link")):
            self._write_valid()
            self.write("CHANGELOG.adoc", "= 变更历史\n")
            self._write_topic_body(f"变更历史见 {form}。")
            cm.errors.clear()
            cm.check_library_guard()
            self.assertEqual([e for e in cm.errors if "CHANGELOG" in e], [],
                             f"文件存在时 {label} 形态不应报错")
            os.remove(os.path.join(self.root, "CHANGELOG.adoc"))
            cm.errors.clear()
            cm.check_library_guard()
            self.assertIn("指向不存在的文件", self.error_texts(),
                          f"文件缺失时 {label} 形态必须报错")

    def test_root_level_file_ref_dangling_reports(self):
        # 反例：馆内以**根级文件名**写法引用（`PROMPTS.adoc`）而该文件不存在
        # 依据：馆内引用一律按仓库根解析——根级文件名同样是引用写法，悬空即断链
        # （此前正则只认"带目录前缀"的写法，`AGENTS.adoc`/`PROMPTS.adoc` 这类
        #  引用被整体跳过，改成不存在的名字也不会被发现）
        self._write_valid()
        self.write("library/README.adoc",
                   "= 图书馆\n\n| link:sources.adoc[] | 见 `PROMPTS.adoc`\n"
                   "| link:adoption.adoc[] | 规范准入与自身取舍的依据——同义性差异与覆盖点\n"
                   "| link:usage.adoc[] | 依据的写入与关联：触发特征、入库必写项、反查算法\n")
        cm.check_library_guard()
        self.assertIn("指向不存在的文件", self.error_texts())

    def test_root_level_file_ref_resolvable_passes(self):
        # 正例：根级文件名写法命中真实文件 → 不报
        self._write_valid()
        self.write("PROMPTS.adoc", "= 提示词\n")
        self.write("library/README.adoc",
                   "= 图书馆\n\n| link:sources.adoc[] | 见 `PROMPTS.adoc` 与 `AGENTS.adoc`\n"
                   "| link:adoption.adoc[] | 规范准入与自身取舍的依据——同义性差异与覆盖点\n"
                   "| link:usage.adoc[] | 依据的写入与关联：触发特征、入库必写项、反查算法\n")
        cm.check_library_guard()
        self.assertEqual(cm.errors, [])

    def test_adoption_topic_missing_anchor_reports(self):
        # 反例：『规范准入与自身取舍』主题的要点锚点被删——该主题的价值全在
        # "如实写明本集合自己的取舍与外部材料的差异"；缺了它，读者会把本站更严取舍
        # （配置类不写逻辑、先例优先优先级、NPC 禁合并）读成外部标准原文（依据不实）
        self._write_valid()
        self.write("library/adoption.adoc", "= 规范准入与自身取舍的依据\n\n说了一堆。\n")
        cm.check_library_guard()
        self.assertIn("缺失要点锚点", self.error_texts())

    def test_adoption_topic_anchor_kept_passes(self):
        # 正例：要点锚点齐备（含"同义性差异"节名与三条取舍的判据句）→ 不报
        self._write_valid()
        cm.errors.clear()
        cm.check_library_guard()
        self.assertEqual(cm.errors, [])

    def test_usage_topic_missing_anchor_reports(self):
        # 反例：『依据的写入与关联』主题的要点锚点被删——该主题的价值全在"写入有触发判据、
        # 反查有可执行算法"；缺了它，"写依据"重新靠自觉（不主动写、写什么凭发挥），
        # 或把规则本体抄进馆（第二真源、改一处必漏一处）
        self._write_valid()
        self.write("library/usage.adoc", "= 依据的写入与关联\n\n说了一堆。\n")
        cm.check_library_guard()
        self.assertIn("缺失要点锚点", self.error_texts())

    def test_usage_topic_anchor_kept_passes(self):
        # 正例：要点锚点齐备（写入触发特征 + 关联协议 + 反查解析算法 + 默认引用面边界）→ 不报
        self._write_valid()
        cm.errors.clear()
        cm.check_library_guard()
        self.assertEqual(cm.errors, [])

    def test_usage_topic_unregistered_reports(self):
        # 反例：新建 usage 主题文件却未登记入口（写文件与登记是同一个动作）——
        # usage.adoc 已列入 LIBRARY_TOPICS 下限，未登记即"写入判据"实际不可达
        self._write_valid()
        self.write("library/README.adoc",
                   "= 图书馆\n\n| link:sources.adoc[] | 外部标准原文摘录\n"
                   "| link:adoption.adoc[] | 规范准入与自身取舍的依据——同义性差异与覆盖点\n")
        cm.check_library_guard()
        self.assertIn("未登记的主题文件", self.error_texts())

    def test_usage_topic_anchors_are_constantized(self):
        # 要点锚点须被常量化（防线要能覆盖"写入判据与反查算法被删"），
        # 且须覆盖三节与关键判据句；第三节标题即"默认引用面与非引用面"（不得退回
        # "共享部分与私有部分"这一与平台事实不符的口径，见 check_ref_scope_wording_guard）
        anchors = cm._LIBRARY_USAGE_ANCHORS
        for q in ("== 一、什么时候该把依据写进图书馆（触发特征）",
                  "== 二、依据与规则怎么关联（关联协议）",
                  "=== 反查解析算法（只取一份，不遍历）",
                  "== 三、默认引用面与非引用面（外部项目怎么处理）",
                  "判据是问句，不是印象",
                  "以下情形**不写**",
                  "**入库必写项**",
                  "**终止条件（L1）**"):
            self.assertIn(q, anchors)

    def test_adoption_topic_unregistered_reports(self):
        # 反例：新建主题文件却未登记入口（写文件与登记是同一个动作）——
        # adoption.adoc 已列入 LIBRARY_TOPICS 下限，未登记即依据不可达
        self._write_valid()
        self.write("library/README.adoc",
                   "= 图书馆\n\n| link:sources.adoc[] | 外部标准原文摘录\n")
        cm.check_library_guard()
        self.assertIn("未登记的主题文件", self.error_texts())

    def test_resolvable_refs_do_not_report(self):
        # 正例：馆内引用真实存在（`specs/...` 反引号 + `../` 相对 link 都命中）
        self._write_valid()
        self.write("specs/general/verify.adoc", "= 验证\n")
        self.write("library/sources.adoc",
                   "= 外部标准原文摘录\n\n见 `specs/general/verify.adoc` 与 "
                   "link:../specs/general/verify.adoc[]\n"
                   + "\n".join("- " + q for q in cm.LIBRARY_QUOTE_ANCHORS)
                   + "\n")
        cm.check_library_guard()
        self.assertEqual(cm.errors, [])

    def test_source_markers_are_constantized(self):
        # 三类取样来源标记须被常量化（防线要能覆盖"依据被压成名称"）
        self.assertEqual(
            tuple(cm.LIBRARY_SOURCE_MARKERS),
            ("官方文本已取回", "官方网页已取回", "未逐字取回"))
        for m in cm.LIBRARY_SOURCE_MARKERS:
            self.assertIn(m, cm.LIBRARY_QUOTE_ANCHORS)

    def test_source_marker_deleted_reports(self):
        # 反例：把"取样来源标记"整体删掉（依据的可信度边界无从判断）→ 须报错
        self._write_valid()
        text = "= 外部标准原文摘录\n\n" + "\n".join(
            "- " + q for q in cm.LIBRARY_QUOTE_ANCHORS
            if q not in cm.LIBRARY_SOURCE_MARKERS) + "\n"
        self.write("library/sources.adoc", text)
        cm.check_library_guard()
        self.assertIn("缺失逐字引文锚点", self.error_texts())

    def test_dir_ref_in_library_resolves(self):
        # 目录型引用在馆内也须按目录存在性核对（不再整体跳过）
        self._write_valid()
        os.makedirs(os.path.join(self.root, "specs", "general"), exist_ok=True)
        self.write("library/sources.adoc",
                   "= 外部标准原文摘录\n\n见 `specs/general/`\n"
                   + "\n".join("- " + q for q in cm.LIBRARY_QUOTE_ANCHORS) + "\n")
        cm.check_library_guard()
        self.assertEqual(cm.errors, [])

    def test_dangling_dir_ref_in_library_reports(self):
        self._write_valid()
        self.write("library/sources.adoc",
                   "= 外部标准原文摘录\n\n见 `specs/gone-dir/`\n"
                   + "\n".join("- " + q for q in cm.LIBRARY_QUOTE_ANCHORS) + "\n")
        cm.check_library_guard()
        self.assertIn("不存在的目录", self.error_texts())


def _valid_locating_index_body() -> str:
    """含全部『依据定位』要点锚点的图书馆入口正文（正例基准）。

    与 `cm._LIBRARY_LOCATING_ANCHORS` 同源：锚点即主键口径/三步取值/形态约束，
    缺一即"馆无限大时定位退回整馆下载或按文件名猜"。
    """
    head = "= 图书馆\n\n本目录是本项目的图书馆。\n\n"
    return head + "\n".join("- " + q for q in cm._LIBRARY_LOCATING_ANCHORS) + "\n"


def _valid_locating_source_body() -> str:
    """含全部『依据定位』机制原文与取样状态的 sources 正文（正例基准）。

    与 `cm._LIBRARY_LOCATING_SOURCE_MARKERS` 同源：缺逐字引文则"主键是内容""只取一段"
    只是本站说法；缺"未实测"则把"支持 Range"当成既定事实。
    """
    head = "= 外部标准原文摘录\n\n"
    return head + "\n".join("- " + q for q in cm._LIBRARY_LOCATING_SOURCE_MARKERS) + "\n"


class TestCheckLibraryLocatingGuard(CheckSpecsTestCase):
    """钉住『依据定位防线』：馆无限大时"怎么准确定位到哪个文件"的协议不得被删或降级。

    背景（用户报告的真实问题）：图书馆**没有限制内容的大小与长度、也没有限制要存的范围**，
    将来可能特别大；其他项目引用时要在**不全量下载**的前提下准确找到"这条依据在哪个文件"。
    缺协议时只有几种坏做法：整馆下载、按主题名猜文件名（命名随重构变化）、把图书馆当全文
    检索引擎，**以及要求取用侧先说出"commit/版本号"再拼地址**（用户报告的失效：游客只有
    https，本仓库也不发布版本号，它根本不知道该取哪个 commit）。故本条钉住：入口侧协议要点
    （含作者侧/取用侧的区别与"入口 = 常驻层的固定地址"）、usage 侧使用判据、sources 侧机制
    原文与**如实**取样状态（本站与平台原始文件视图均未实测到 Range 生效，不得当成既定事实）、
    项目入口的口径，以及**"先取 commit 再拼地址"这一表述形态不得回退**。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_lib = (cm.LIBRARY_DIR, cm.LIBRARY_INDEX)
        self._orig_project = cm.PROJECT_FILE
        cm.LIBRARY_DIR = os.path.join(self.root, "library")
        cm.LIBRARY_INDEX = os.path.join(cm.LIBRARY_DIR, "README.adoc")
        cm.PROJECT_FILE = os.path.join(self.root, "AGENTS.adoc")

    def tearDown(self) -> None:
        (cm.LIBRARY_DIR, cm.LIBRARY_INDEX) = self._orig_lib
        cm.PROJECT_FILE = self._orig_project
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("AGENTS.adoc",
                   "= 项目规范\n\n依据图书馆：馆无体量上限，入口 = 常驻层的固定地址\n")
        self.write("library/README.adoc", _valid_locating_index_body())
        self.write("library/usage.adoc", _valid_usage_body())
        self.write("library/adoption.adoc", _valid_adoption_body())
        self.write("library/sources.adoc", _valid_locating_source_body())

    def test_valid_locating_passes(self):
        self._write_valid()
        cm.check_library_locating_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_index_reports(self):
        # 反例：图书馆入口整体被删（定位协议无处承载→退回整馆下载）
        self._write_valid()
        os.remove(cm.LIBRARY_INDEX)
        cm.check_library_locating_guard()
        self.assertIn("缺少图书馆入口", self.error_texts())

    def test_index_anchor_deleted_reports(self):
        # 反例：入口的主键/取值/形态约束被删（定位协议只剩名字）
        self._write_valid()
        self.write("library/README.adoc", "= 图书馆\n\n依据大时慢慢找即可\n")
        cm.check_library_locating_guard()
        self.assertIn("缺失『依据定位』要点", self.error_texts())

    def test_usage_side_missing_section_reports(self):
        # 反例：usage 侧缺"引用方怎么准确定位"节（使用判据无处可读）
        self._write_valid()
        body = _valid_usage_body().replace(
            "== 四、引用方怎么准确定位依据（不全量下载）", "== 四、定位")
        self.write("library/usage.adoc", body)
        cm.check_library_locating_guard()
        self.assertIn("引用方怎么准确定位依据", self.error_texts())

    def test_usage_side_missing_primary_key_reports(self):
        # 反例：去掉"主键是内容、不是路径"（改名即断档的根因被隐去）
        self._write_valid()
        body = _valid_usage_body().replace("**主键是内容、不是路径**", "主键")
        self.write("library/usage.adoc", body)
        cm.check_library_locating_guard()
        self.assertIn("主键是内容、不是路径", self.error_texts())

    def test_usage_side_missing_termination_reports(self):
        # 反例：终止条件被删（定位又会向下展开成第二真源）
        self._write_valid()
        body = _valid_usage_body().replace("**终止条件（L1，同上）**", "终止")
        self.write("library/usage.adoc", body)
        cm.check_library_locating_guard()
        self.assertIn("终止条件（L1，同上）", self.error_texts())

    def test_source_marker_missing_reports(self):
        # 反例：机制原文被删（"主键是内容""只取一段"变成本站说法）
        self._write_valid()
        self.write("library/sources.adoc", "= 外部标准原文摘录\n\ngit 与 RFC 7233 见官方文档\n")
        cm.check_library_locating_guard()
        self.assertIn("缺失『依据定位』的机制原文", self.error_texts())

    def test_source_range_not_marked_unverified_reports(self):
        # 反例：把"支持 Range"当成既定事实（本地站点其实未实测）
        self._write_valid()
        body = _valid_locating_source_body().replace("**未实测**", "已实测生效")
        self.write("library/sources.adoc", body)
        cm.check_library_locating_guard()
        self.assertIn("缺失『依据定位』的机制原文", self.error_texts())

    def test_project_entry_without_primary_key_reports(self):
        # 反例：项目入口未登记定位协议口径（读者不知道有这份协议）
        self._write_valid()
        self.write("AGENTS.adoc", "= 项目规范\n\n依据图书馆见别处\n")
        cm.check_library_locating_guard()
        self.assertIn("未含『依据定位』的口径", self.error_texts())

    def test_commit_as_client_prerequisite_reports(self):
        # 反例（用户报告的失效）：把"先取 commit 再拼地址"写成取用路径——
        # 游客只有 https、没有仓库与 git，取不到 commit
        self._write_valid()
        self.write("library/usage.adoc", _valid_usage_body()
                   + "\n取用方须先取当前 commit，再拼出原始文件地址。\n")
        cm.check_library_locating_guard()
        self.assertIn("取用前置", self.error_texts())

    def test_commit_in_address_exempt_when_negated(self):
        # 正例豁免：把该错误表述**本身**写出来（否定/失效记录）不得误伤
        self._write_valid()
        self.write("library/usage.adoc", _valid_usage_body()
                   + "\n不得把 commit 写进取值地址：取用侧取不到它。\n")
        cm.check_library_locating_guard()
        self.assertEqual(cm.errors, [])

    def test_long_library_file_name_reports(self):
        # 反例（用户报告的失效）：把主张写进文件名——名字写成一句话，
        # 每次链接与每次目录列举都替它付上下文，而名字本就不是检索键
        self._write_valid()
        long_name = "sources-and-locating-protocol-for-evidence.adoc"
        self.assertGreater(len(long_name), cm.LIBRARY_FILE_NAME_MAX)
        self.write("library/" + long_name, "= 依据的来源与定位协议\n")
        cm.check_library_locating_guard()
        self.assertIn("文件名过长", self.error_texts())

    def test_short_library_file_name_passes(self):
        # 正例：短词命名（名字不是主键、也不承担语义）
        self._write_valid()
        self.write("library/evidence.adoc", "= 依据\n")
        cm.check_library_locating_guard()
        self.assertEqual(cm.errors, [])

    def test_file_name_max_matches_module_file_limit(self):
        # 常量口径：与通用层『模块文件名』上限同值（32 字符，含扩展名）
        self.assertEqual(cm.LIBRARY_FILE_NAME_MAX, 32)

    def test_locating_anchors_constant_nonempty(self):
        # 常量完整性：锚点与取样标记须齐全（缺一即防线的判据面缩小）
        for q in ("== 依据的定位协议（入口 + 索引 + 单点取值）",
                  "**第一步：入口 = 常驻层里的固定地址（不要自己拼地址）**",
                  "**版本固化（可选加固，不得写成前置）**",
                  "**分段取值（馆特别大时怎么只取一段）**",
                  "**形态约束（L1）**", "**文件名协议（短、无语义、不承担定位）**",
                  "**取用侧**是**游客**"):
            self.assertIn(q, cm._LIBRARY_LOCATING_ANCHORS)
        for q in ("== 四、引用方怎么准确定位依据（不全量下载）",
                  "**主键是内容、不是路径**",
                  "**协议不承载的东西（形态约束，L1）**",
                  "**终止条件（L1，同上）**",
                  "**取用侧是游客**", "**只有 https、没有仓库、没有 git**",
                  "**文件名不承担定位（短、无语义，L1）**"):
            self.assertIn(q, cm._LIBRARY_LOCATING_USAGE_ANCHORS)
        for q in ("== 依据的定位与取值（git / RFC 9110）",
                  "names the **blob or tree** at the given path", "**未实测**"):
            self.assertIn(q, cm._LIBRARY_LOCATING_SOURCE_MARKERS)


class TestCheckPublicContentCoverage(CheckSpecsTestCase):
    """钉住『公共内容覆盖面防线』：公共内容的入口清单须完整、且与实际文件一致。

    背景：公共内容此前只有一句口头定义（"`AGENTS_COMMON.adoc` + `specs/`"），而
    `INSTALL.adoc`（接入时读）、`prompts/_common.txt`（AI 以纯文本读取公共片段）与
    `script/clean_tmp.py`（随规范分发的通用工具）同样会被引用方取到——清单缺失会让
    机械检查漏掉半个公共内容，或把"自足"要求误加到只对维护方成立的文件上。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_public = cm.PUBLIC_FILE
        self._orig_project = cm.PROJECT_FILE
        cm.PUBLIC_FILE = os.path.join(self.root, "PUBLIC.adoc")
        cm.PROJECT_FILE = os.path.join(self.root, "AGENTS.adoc")

    def tearDown(self) -> None:
        cm.PUBLIC_FILE = self._orig_public
        cm.PROJECT_FILE = self._orig_project
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("AGENTS.adoc", "= 项目规范\n\n公共内容入口清单见 PUBLIC.adoc。\n")
        self.write("PUBLIC.adoc",
                   "= 公共内容入口索引\n\n"
                   "== 公共内容入口清单\n"
                   "| `INSTALL.adoc` | 安装入口\n"
                   "| `AGENTS_COMMON.adoc` | 通用规范入口\n"
                   "| `specs/` | 规范正文\n"
                   "| `prompts/_common.txt` | 公共片段\n"
                   "| `script/clean_tmp.py` | 随规范分发的工具\n")
        self.write("INSTALL.adoc", "= 安装\n")
        self.write("AGENTS_COMMON.adoc", "= 入口\n")
        self.write("prompts/_common.txt", "片段\n")
        self.write("script/clean_tmp.py", "#!/usr/bin/env python3\n")

    def test_valid_listing_passes(self):
        self._write_valid()
        cm.check_public_content_coverage()
        self.assertEqual(cm.errors, [])

    def test_missing_listing_reports(self):
        # 反例：清单整体缺失（覆盖面界不清）
        self._write_valid()
        os.remove(cm.PUBLIC_FILE)
        cm.check_public_content_coverage()
        self.assertIn("缺少公共内容入口索引", self.error_texts())

    def test_entry_only_in_prose_reports(self):
        # 反例：入口只在正文被提一句、未列进「入口清单」表——此前用 `rel in 全文`
        # 判断，这种"被悄悄移出表格"的改动不会被发现（表格才是覆盖面的定义处）
        self._write_valid()
        self.write("PUBLIC.adoc",
                   "= 公共内容入口索引\n\n== 公共内容入口清单\n"
                   "| `AGENTS_COMMON.adoc` | 通用规范入口\n"
                   "| `specs/` | 规范正文\n"
                   "| `prompts/_common.txt` | 公共片段\n"
                   "| `script/clean_tmp.py` | 随规范分发的工具\n\n"
                   "== 组织与其边界\n\n引用方接入时读 `INSTALL.adoc`。\n")
        cm.check_public_content_coverage()
        self.assertIn("未把 INSTALL.adoc 列进", self.error_texts())

    def test_entry_in_table_link_form_passes(self):
        # 正例：同一格改用 AsciiDoc 惯用的 `link:` **文本**写法——表格结构、所在节、
        # 覆盖面均未变，纯排版，**不得**报"未列进表"
        # （原判据把"表格行的位置"与"文件名用反引号"混成一件：明明列在表里却报"未列出"）
        self._write_valid()
        self.write("PUBLIC.adoc",
                   "= 公共内容入口索引\n\n== 公共内容入口清单\n"
                   "| 安装入口 | link:INSTALL.adoc[INSTALL.adoc] |\n"
                   "| 通用规范入口 | link:AGENTS_COMMON.adoc[AGENTS_COMMON.adoc] |\n")
        cm.check_public_content_coverage()
        self.assertNotIn("未把", self.error_texts())

    def test_names_in_zone_accepts_forms_but_keeps_row_anchor(self):
        # 钉住判据口径：表格行内任一点名形式均命中；非表格行（正文提及）仍不命中
        z = "| 安装入口 |"
        self.assertTrue(cm._names_in_zone(z + " `INSTALL.adoc` |", "INSTALL.adoc"))
        self.assertTrue(cm._names_in_zone(z + " link:INSTALL.adoc[INSTALL.adoc] |", "INSTALL.adoc"))
        self.assertTrue(cm._names_in_zone(z + " link:INSTALL.adoc[] |", "INSTALL.adoc"))
        self.assertTrue(cm._names_in_zone(z + " INSTALL.adoc |", "INSTALL.adoc"))
        self.assertFalse(cm._names_in_zone("接入时读 INSTALL.adoc。", "INSTALL.adoc"))
        self.assertFalse(cm._names_in_zone(z + " `AGENTS_COMMON.adoc` |", "INSTALL.adoc"))

    def test_listing_not_registered_reports(self):
        # 反例：清单未在项目规范入口登记（维护方读不到它）
        self._write_valid()
        self.write("AGENTS.adoc", "= 项目规范\n")
        cm.check_public_content_coverage()
        self.assertIn("未在本仓库项目规范入口", self.error_texts())

    def test_entry_missing_from_listing_reports(self):
        # 反例：清单漏了公开入口（漏一个即半个公共内容不在覆盖面内）
        self._write_valid()
        self.write("PUBLIC.adoc",
                   "= 公共内容入口索引\n\n== 公共内容入口清单\n"
                   "| `AGENTS_COMMON.adoc` | 通用规范入口\n")
        cm.check_public_content_coverage()
        self.assertIn("未列出 INSTALL.adoc", self.error_texts())

    def test_entry_list_section_renamed_reports(self):
        # 反例：清单节的标题被改写 → 按节切表格区的定位失效，须报错（不得静默不查）
        self._write_valid()
        self.write("PUBLIC.adoc",
                   "= 公共内容入口索引\n\n== 入口一览\n"
                   "| `INSTALL.adoc` | 安装入口\n"
                   "| `AGENTS_COMMON.adoc` | 通用规范入口\n")
        cm.check_public_content_coverage()
        self.assertIn("未找到「公共内容入口清单」节", self.error_texts())

    def test_named_file_missing_reports(self):
        # 反例：清单点名了不存在的文件（清单与实际不一致）
        self._write_valid()
        self.write("PUBLIC.adoc",
                   "= 公共内容入口索引\n\n== 公共内容入口清单\n"
                   "| `INSTALL.adoc` | 安装入口\n"
                   "| `AGENTS_COMMON.adoc` | 通用规范入口\n"
                   "| `prompts/gone.txt` | 已改名\n")
        cm.check_public_content_coverage()
        self.assertIn("点名了不存在的文件", self.error_texts())

    def test_non_public_example_named_file_missing_reports(self):
        # 反例：「不属公共内容」一段的反向举例点名了不存在的文件 —— 原实现靠硬编码
        # 5 个 .adoc 名跳过该段，改名/新增举例都无人核；改按节切后须真实存在
        self._write_valid()
        self.write("PUBLIC.adoc",
                   "= 公共内容入口索引\n\n== 公共内容入口清单\n"
                   "| `INSTALL.adoc` | 安装入口\n"
                   "| `AGENTS_COMMON.adoc` | 通用规范入口\n"
                   "| `specs/` | 规范正文\n"
                   "| `prompts/_common.txt` | 公共片段\n"
                   "| `script/clean_tmp.py` | 随规范分发的工具\n"
                   "\n== 组织与其边界\n"
                   "* **不属公共内容入口清单**：`gone-internal.adoc`（已改名）\n")
        cm.check_public_content_coverage()
        self.assertIn("点名了不存在的文件", self.error_texts())

    def test_non_public_example_existing_files_pass(self):
        # 正例：「不属公共内容」一段点名真实存在的文件（不必再靠硬编码豁免名单）
        self._write_valid()
        self.write("internal-note.adoc", "= 维护方内容\n")
        self.write("PUBLIC.adoc",
                   "= 公共内容入口索引\n\n== 公共内容入口清单\n"
                   "| `INSTALL.adoc` | 安装入口\n"
                   "| `AGENTS_COMMON.adoc` | 通用规范入口\n"
                   "| `specs/` | 规范正文\n"
                   "| `prompts/_common.txt` | 公共片段\n"
                   "| `script/clean_tmp.py` | 随规范分发的工具\n"
                   "\n== 组织与其边界\n"
                   "* **不属公共内容入口清单**：`internal-note.adoc`（维护方内容）\n")
        cm.check_public_content_coverage()
        self.assertEqual(cm.errors, [])



class TestCheckDeliveryGuard(CheckSpecsTestCase):
    """钉住『交付形态与报告落点』：不得只冒一句过程性叙述、不得只交付不汇报。

    本轮实测失效（用户直接问责）：一轮 NPC 任务唯一对外的输出是一句过程性叙述
    （"Now let me check whether there's a …"）——既不是汇报、也没有任何提交。
    旧版 `delivery` 片段只写"有改动必须提交推送"，恰漏了"当次无改动也算完成态"
    与"过程性叙述不得外发"，故本组用例把这两条连同登记处同步一并钉住。
    """

    DELIVERY = ("// tag::delivery[]\n"
                "8. 交付：\n"
                "   - **CI/CD 等自动化场景**：必须提交并推送；**有改动**时**必须**把改动"
                "**提交并推送到 PR 分支**、**创建 PR**（只提交不推送/只推送不提交都不算）；"
                "**没有提交即等于没有交付**（**有改动却没提交也没推送**、**没有改动却没说明**"
                "都属交付失败）。\n"
                "   - **报告落点（L1）**：**过程性叙述**（现在去读 X、先看有没有 Z）"
                "**不得作为独立的一条评论**发出去（**答非所问**）；"
                "**结果与结论**须**汇总成一次完整汇报**（平台上即**一条评论**）；"
                "**输出通道只有两条**（最终汇报 / 必须停下确认），"
                "**除这两条之外的任何中间话一律不发**（自己认定的\"必要说明\"不构成"
                "**第三条通道**）。\n"
                "// end::delivery[]\n")

    def setUp(self) -> None:
        super().setUp()
        self._orig_prompts = (cm.PROMPTS_FILE, cm.PROMPTS_DIR, cm.COMMON_PROMPT_FILE,
                              cm.README_FILE)
        cm.PROMPTS_FILE = os.path.join(self.root, "PROMPTS.adoc")
        cm.PROMPTS_DIR = os.path.join(self.root, "prompts")
        cm.COMMON_PROMPT_FILE = os.path.join(self.root, "prompts", "_common.txt")
        cm.README_FILE = os.path.join(self.root, "README.adoc")

    def tearDown(self) -> None:
        (cm.PROMPTS_FILE, cm.PROMPTS_DIR, cm.COMMON_PROMPT_FILE,
         cm.README_FILE) = self._orig_prompts
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("prompts/_common.txt", self.DELIVERY)
        self.write("prompts/review.adoc",
                   "= 检查修复\n\n[listing]\n----\n"
                   "10. 交付即汇报（**有改动**须提交推送并建 PR，"
                   "**不得**只交付不汇报、**不得**只冒一句、**没有交付**；"
                   "**输出通道只有两条**、**任何中间话一律不发**）\n"
                   "include::_common.txt[tag=delivery]\n----\n")
        self.write("prompts/refactor.adoc",
                   "= 重构\n\n[listing]\n----\n"
                   "10. 交付即汇报（**有改动**须提交推送并建 PR，"
                   "**不得**只交付不汇报、**不得**只冒一句、**没有交付**；"
                   "**输出通道只有两条**、**任何中间话一律不发**）\n"
                   "include::_common.txt[tag=delivery]\n----\n")
        self.write("PROMPTS.adoc",
                   "* 公共约定：**交付即汇报**——**过程性叙述**不得作为评论发出；"
                   "**输出通道只有两条**、**除这两条之外的任何中间话一律不发**；"
                   "**没有改动却没说明**亦属交付失败。\n"
                   "* **题目与片段的改动边界**：补片段缺口**不扩大题面**、"
                   "**不得在两个提示词里各写一遍**。\n")
        self.write("README.adoc",
                   "# README\n\n**过程性叙述**不得作为独立评论发出去；"
                   "**输出通道只有两条**、**除这两条之外的任何中间话一律不发**；"
                   "\"报告说完成了**却没有任何提交**\"属交付失败。\n")

    def test_valid_delivery_passes(self):
        self._write_valid()
        cm.check_delivery_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_fragment_reports(self):
        # 反例：公共片段被删 → 两处提示词同时失去这条边界
        self._write_valid()
        self.write("prompts/_common.txt", "普通片段\n")
        cm.check_delivery_guard()
        self.assertIn("delivery", self.error_texts())

    def test_process_narrative_clause_removed_reports(self):
        # 反例（本轮实测失效的形态）：抽掉"过程性叙述不得作为独立评论发出"
        self._write_valid()
        self.write("prompts/_common.txt",
                   "// tag::delivery[]\n"
                   "8. 交付：**有改动**须**提交并推送到 PR 分支**、**创建 PR**；"
                   "**没有提交即等于没有交付**；**有改动却没提交也没推送**；"
                   "**没有改动却没说明**；**结果与结论**须**汇总成一次完整汇报**"
                   "（**一条评论**）。\n// end::delivery[]\n")
        cm.check_delivery_guard()
        self.assertIn("过程性叙述", self.error_texts())

    def test_zero_change_state_removed_reports(self):
        # 反例：抽掉"没有改动却没说明"这一态 → 回到"无改动时不知道要不要交付"
        self._write_valid()
        self.write("prompts/_common.txt",
                   "// tag::delivery[]\n"
                   "8. 交付：**有改动**须**提交并推送到 PR 分支**、**创建 PR**（只提交不推送）；"
                   "**没有提交即等于没有交付**；**有改动却没提交也没推送**；"
                   "**报告落点**：**过程性叙述**不得作为**独立的一条评论**（**答非所问**）；"
                   "**结果与结论**须**汇总成一次完整汇报**（**一条评论**）。\n"
                   "// end::delivery[]\n")
        cm.check_delivery_guard()
        self.assertIn("没有改动却没说明", self.error_texts())

    def test_prompt_missing_report_step_reports(self):
        # 反例：题面侧步骤被删（片段在、流程里却没有"交付即汇报"）
        self._write_valid()
        self.write("prompts/refactor.adoc",
                   "= 重构\n\ninclude::_common.txt[tag=delivery]\n")
        cm.check_delivery_guard()
        self.assertIn("交付即汇报", self.error_texts())

    def test_registry_not_synced_reports(self):
        # 反例：登记处未同步 → 提示词被复制到未知项目后公开面看不到这条边界
        self._write_valid()
        self.write("PROMPTS.adoc", "* 公共约定：改动范围边界。\n")
        cm.check_delivery_guard()
        self.assertIn("交付即汇报", self.error_texts())

    def test_edit_boundary_removed_reports(self):
        # 反例：抽掉"改题面 vs 补片段缺口"的改动边界 → 缺口只能等下一轮（旧任务继续按旧版执行）
        self._write_valid()
        self.write("PROMPTS.adoc",
                   "* 公共约定：**交付即汇报**——**过程性叙述**不得作为评论发出；"
                   "**没有改动却没说明**亦属交付失败。\n")
        cm.check_delivery_guard()
        self.assertIn("题目与片段的改动边界", self.error_texts())

    def test_output_channels_clause_removed_reports(self):
        # 反例（本轮识别出的第二个成因）：例外只写"必须停下确认这一种"、
        # 没写"除这两条之外的任何中间话一律不发" → 执行者自行认定"这属于必要的说明"
        # 就能再发一条，判据回到执行者手里，防线形同虚设
        self._write_valid()
        self.write("prompts/_common.txt",
                   "// tag::delivery[]\n"
                   "8. 交付：**有改动**须**提交并推送到 PR 分支**、**创建 PR**（只提交不推送）；"
                   "**没有提交即等于没有交付**；**有改动却没提交也没推送**；"
                   "**没有改动却没说明**；"
                   "**报告落点**：**过程性叙述**不得作为**独立的一条评论**（**答非所问**）；"
                   "**结果与结论**须**汇总成一次完整汇报**（**一条评论**）；"
                   "需中途说明的例外只有\"必须停下确认\"这一种。\n"
                   "// end::delivery[]\n")
        cm.check_delivery_guard()
        self.assertIn("输出通道只有两条", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例：README 使用要点未同步 → 公开面只看得见"禁止"、看不到这条边界
        self._write_valid()
        self.write("README.adoc", "# README\n\n普通说明。\n")
        cm.check_delivery_guard()
        self.assertIn("README.adoc", self.error_texts())


# --------------------------------------------------------------------------- #
# check_prompts_primary（提示词主侧重与优先级防线：方向不得被删/降级）
# --------------------------------------------------------------------------- #
class TestCheckPublicFacingDocsStaySelfContained(CheckSpecsTestCase):
    """钉住「公开面文档自足」：README/PROMPTS/INSTALL 不得给出维护方自查层的路径。

    背景（本轮重构暴露的真实缺陷）：`specs/` 已被刚性拦住"引用维护方自查层"，但
    `README.adoc`（公开站点首页由它渲染）、`PROMPTS.adoc`（公开提示词入口）与
    `INSTALL.adoc`（引用方安装文档）**同样会被未知项目看到**——它们里的路径引用方
    按同样方式解析，指向维护方自查层就是死链（该层不随公共内容分发）。本轮就发生过：
    README 在重构中新增了 8 处指向该层的链接。
    """

    def test_clean_public_docs_pass(self):
        self.write("README.adoc", "本仓库另有一层只对维护方成立的规范，不随公共内容分发。\n")
        self.write("PROMPTS.adoc", "分级见 `specs/core/execution.adoc`。\n")
        self.write("INSTALL.adoc", "安装文档。\n")
        cm.check_public_facing_docs_stay_self_contained()
        self.assertEqual(cm.errors, [])

    def test_readme_link_into_maintainer_layer_reports(self):
        self.write("README.adoc",
                   "定级判据见 link:specs-project-maintainer/spec-lifecycle.adoc[]。\n")
        cm.check_public_facing_docs_stay_self_contained()
        self.assertIn("公开面文档不得给出维护方自查层", self.error_texts())

    def test_prompts_link_into_maintainer_layer_reports(self):
        self.write("PROMPTS.adoc",
                   "定级见 `specs-project-maintainer/spec-lifecycle.adoc`。\n")
        cm.check_public_facing_docs_stay_self_contained()
        self.assertIn("PROMPTS.adoc", self.error_texts())

    def test_missing_docs_do_not_raise(self):
        cm.check_public_facing_docs_stay_self_contained()
        self.assertEqual(cm.errors, [])


class TestCheckSelfCheckGuard(CheckSpecsTestCase):
    """钉住执行前自检规范的存在性、要点与必加载层落点。

    自检是把"规范加载了却没被执行"兜住的关键环节，故与最高关注项一样加机械防线：
    文件被删、要点缺失、execution.adoc 落点丢失、未登记调度器，任一即报。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_self_check = cm.SELF_CHECK_FILE
        cm.SELF_CHECK_FILE = os.path.join(self.root, "specs", "general", "self-check.adoc")

    def tearDown(self) -> None:
        cm.SELF_CHECK_FILE = self._orig_self_check
        super().tearDown()

    def _write_valid(self):
        self.write("specs/general/self-check.adoc",
                   "= 执行前自检规范\n\n"
                   "== 知识边界\n\n不得顺口编造，不知道就去查证。\n\n"
                   "== 执行前自检清单（动手前逐项过）\n\n"
                   "适用范围是非平凡任务，逐项检查。\n\n"
                   "== 完成前自检\n\n对照原要求逐条核。\n")
        self.write("specs/core/execution.adoc",
                   "执行前自检见 `specs/general/self-check.adoc`。\n")
        self.write("AGENTS_COMMON.adoc",
                   "通用层登记 `specs/general/self-check.adoc`")

    def test_valid_self_check_spec_passes(self):
        self._write_valid()
        cm.check_self_check_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_file_reports(self):
        # 反例：自检规范文件整体被删（自检关口丢失）
        self.write("AGENTS_COMMON.adoc", "= t")
        cm.check_self_check_guard()
        self.assertIn("缺少执行前自检规范文件", self.error_texts())

    def test_dropped_checklist_reports(self):
        # 反例：删掉"执行前自检清单"（只剩泛泛要求，无逐项内容）
        self.write("specs/general/self-check.adoc",
                   "= 自检\n\n不得顺口编造。非平凡任务须自检。完成前自检。\n")
        self.write("specs/core/execution.adoc", "`specs/general/self-check.adoc`")
        self.write("AGENTS_COMMON.adoc", "登记 `specs/general/self-check.adoc`")
        cm.check_self_check_guard()
        self.assertIn("执行前自检清单", self.error_texts())

    def test_dropped_scope_boundary_reports(self):
        # 反例：删掉适用范围界定（会被"只对大任务"架空）
        self.write("specs/general/self-check.adoc",
                   "= 自检\n\n执行前自检清单。不得顺口编造。完成前自检。\n")
        self.write("specs/core/execution.adoc", "`specs/general/self-check.adoc`")
        self.write("AGENTS_COMMON.adoc", "登记 `specs/general/self-check.adoc`")
        cm.check_self_check_guard()
        self.assertIn("非平凡任务", self.error_texts())

    def test_execution_landing_point_missing_reports(self):
        # 反例：必加载层未引用自检规范 → 实际不会被加载
        self._write_valid()
        self.write("specs/core/execution.adoc", "见相关规范。\n")
        cm.check_self_check_guard()
        self.assertIn("自检", self.error_texts())

    def test_not_registered_in_dispatcher_reports(self):
        # 反例：文件存在但未登记调度器 → 永不被加载
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "= t")
        cm.check_self_check_guard()
        self.assertIn("未在加载调度器登记", self.error_texts())


class TestCheckSourceGuard(CheckSpecsTestCase):
    """钉住来源真实性规范的存在性与要点。

    来源一旦不实会污染整条下游引用链（引错标准、引不存在的文件），故机械钉住
    "引用当前真实存在的目标""只写名称编号""不得编造""宁可不引"四条要点。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_source = cm.SOURCE_FILE
        cm.SOURCE_FILE = os.path.join(self.root, "specs", "general", "source.adoc")

    def tearDown(self) -> None:
        cm.SOURCE_FILE = self._orig_source
        super().tearDown()

    def _write_valid(self):
        self.write("specs/general/source.adoc",
                   "= 依据与来源真实性\n\n"
                   "引用须指向当前真实存在的目标；外部标准只写名称与编号、不附链接；"
                   "不得编造编号与名称；无法确证时宁可不引。\n")
        self.write("AGENTS_COMMON.adoc", "登记 `specs/general/source.adoc`")

    def test_valid_source_spec_passes(self):
        self._write_valid()
        cm.check_source_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_file_reports(self):
        # 反例：来源规范文件整体被删
        self.write("AGENTS_COMMON.adoc", "= t")
        cm.check_source_guard()
        self.assertIn("缺少依据与来源真实性规范文件", self.error_texts())

    def test_dropped_no_fabrication_reports(self):
        # 反例：删掉"不得编造"（来源防线最核心的一条）
        self.write("specs/general/source.adoc",
                   "= t\n\n引用须指向当前真实存在的目标；只写名称编号、不附链接；宁可不引。\n")
        self.write("AGENTS_COMMON.adoc", "登记 `specs/general/source.adoc`")
        cm.check_source_guard()
        self.assertIn("不得编造", self.error_texts())

    def test_dropped_no_link_rule_reports(self):
        # 反例：删掉"不附链接"（出处写法要求）
        self.write("specs/general/source.adoc",
                   "= t\n\n引用须指向当前真实存在的目标；不得编造；宁可不引。\n")
        self.write("AGENTS_COMMON.adoc", "登记 `specs/general/source.adoc`")
        cm.check_source_guard()
        self.assertIn("不附链接", self.error_texts())

    def test_not_registered_in_dispatcher_reports(self):
        # 反例：文件存在但未登记调度器 → 永不被加载
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "= t")
        cm.check_source_guard()
        self.assertIn("未在加载调度器登记", self.error_texts())


class TestCheckVerifyGuard(CheckSpecsTestCase):
    """钉住「规范验证防线」：验证口径（三视角/效力等级/总纲）与其维护方落点须一致。

    验证的**规则**属公共内容（单一落点 `specs/general/verify.adoc`；`testing.adoc` 的
    同名节只留一跳入口——两处各写一份已实测漂移过一次）——
    任何项目改自己的规范/共享资产时都要问"改完怎么验"，且引用方确实需要三视角、效力
    等级与运行契约（否则"加得越多越忘掉初衷"）。维护方**自己的**动作落
    `specs-project-maintainer/verify.adoc` 与 `AGENTS.adoc`。故作防线：公共节与标准出处
    须在、维护方落点须在、P2 与 AGENTS.adoc 两处口径须一致指向三视角与效力等级。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_extra = (cm.PROJECT_FILE,)

    def tearDown(self) -> None:
        super().tearDown()

    def _pub(self):
        return os.path.join(self.root, "specs", "general", "verify.adoc")

    def _write_valid(self):
        self.write("specs/general/verify.adoc",
                   "= 测试规范（通用层，跨语言）\n\n"
                   "== 验证与运行契约\n\n"
                   "* 以真实结果为准。\n\n"
                   "=== 判准维度：严格执行 / 尽力而为\n\n严格执行与尽力而为两档，都须留证。\n\n"
                   "=== 验证的适用边界\n\n先判改动性质；代码类改动 / 规范类改动；"
                   "不改内容的操作（C 类：只改提交/历史或文件路径，内容逐字节不变，"
                   "不重跑全量编译与测试）；"
                   "\"内容没变\"不是\"少核对\"的借口；"
                   "判据问句\"会不会被未知项目加载\"；先判改动性质；不得互串；取**更严的一侧**；"
                   "每次验证都换一个干净上下文。\n\n"
                   "=== 验证的效力等级\n\n"
                   "确定项（判据本体验证）走机械校验；概念项只能启发式复核；未发现问题；悬置；"
                   "不得当作阻断交付的条件。\n\n"
                   "=== 验证总纲（回答\"验证什么、怎么算过\"）\n\n"
                   "| 视角 | 判定问题 | 标准出处\n"
                   "| **① 完整性** | 等价 | ISO 10007 |\n"
                   "| **② 有效性与认知质量** | 判据可判定、依据说对、代价说得清 | "
                   "ISO/IEC Directives Part 2、RFC 2119、ISO/IEC/IEEE 25010 |\n"
                   "| **③ 接纳面** | 未知项目加载可控 | ISO 9241-110 |\n"
                   "验证对象不止规范文件、也须能枚举\"如何验证\"。\n\n"
                   "=== 规范验证（改完规范后的三视角复核）\n\n"
                   "①完整性；②有效性与认知质量；③接纳面，由同一个干净子 agent 一并回答"
                   "（每次验证都换一个干净上下文）；②判据：可执行、依据、降级路径、读的形态、"
                   "常驻层只放底线、从属者可达、④性能；三问都须留证；三态台账；依据 IEEE 1028；"
                   "硬超时。\n\n"
                   "=== 运行契约（公共内容被未知项目加载时的可控性）\n\n"
                   "① 影响面；② 成本；③ 可控性；降级路径；不得让引用方依赖本仓库私有物；"
                   "依据 ISO 9241-110；接纳面须留证。\n")
        self.write("specs-project-maintainer/verify.adoc",
                   "= 验证的维护方落点（维护方自查）\n\n"
                   "* 完整性校验：跑机械校验 + 干净子 agent 三视角复核。\n"
                   "* 子 agent 复核必须自带硬超时。\n"
                   "* 留证按三态台账：通过／未发现问题／悬置，不得合并。\n"
                   "* 维护方侧的具名抓手是 `check_checklist_guard`。\n")
        self.write("specs-project-maintainer/priority.adoc",
                   "P2：改完必须跑机械校验 + 干净子 agent 语义复核；须答 ②有效性与认知质量；"
                   "须答 ③接纳面；同一个干净子 agent 一并回答；结论分档见「验证的效力等级」——"
                   "未发现问题、悬置、不得当作阻断交付的条件。\n")
        self.write("AGENTS.adoc",
                   "完整性校验：含 ②有效性与认知质量；含 ③接纳面；三视角合用一个子 agent；"
                   "结论强度按对象分档（见「验证的效力等级」）：只到未发现问题、不写成通过。\n")

    def test_valid_three_lens_formula_passes(self):
        self._write_valid()
        cm.check_verify_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_public_verify_file_reports(self):
        # 反例：公共验证口径文件整体被删
        self.write("specs-project-maintainer/priority.adoc", "P2")
        cm.check_verify_guard()
        self.assertIn("缺少公共验证规范文件", self.error_texts())

    def test_missing_charter_section_reports(self):
        # 反例：「验证总纲」被删（验证什么、怎么算过、标准出自哪里 重新无人负责）
        self._write_valid()
        p = self._pub()
        t = open(p, encoding="utf-8").read()
        self.write("specs/general/verify.adoc",
                   t.replace("=== 验证总纲（回答\"验证什么、怎么算过\"）", "=== 随便什么节"))
        cm.check_verify_guard()
        self.assertIn("验证总纲", self.error_texts())

    def test_missing_adoption_lens_reports(self):
        # 反例：删掉③接纳面（回到"只面对方规范本体与本仓库"的旧口径）
        self._write_valid()
        p = self._pub()
        t = open(p, encoding="utf-8").read()
        self.write("specs/general/verify.adoc", t.replace("③接纳面", "某某面"))
        cm.check_verify_guard()
        self.assertIn("③接纳面", self.error_texts())

    def test_missing_effectiveness_grades_section_reports(self):
        # 反例：删掉「验证的效力等级」节（回到"把复核结论当依据、把找不到问题当交付前提"）
        self._write_valid()
        p = self._pub()
        t = open(p, encoding="utf-8").read()
        self.write("specs/general/verify.adoc",
                   t.replace("=== 验证的效力等级", "=== 随便什么节"))
        cm.check_verify_guard()
        self.assertIn("效力等级", self.error_texts())

    def test_missing_concept_grade_boundary_reports(self):
        # 反例：去掉"不得阻断交付"这条边界（把复核当交付前置条件）
        self._write_valid()
        p = self._pub()
        t = open(p, encoding="utf-8").read()
        self.write("specs/general/verify.adoc", t.replace("不得当作阻断交付的条件", "另说"))
        cm.check_verify_guard()
        self.assertIn("不得当作阻断交付的条件", self.error_texts())

    def test_missing_standard_sources_reports(self):
        # 反例：标准出处被删（验证退化成"把脚本跑绿"、无从核对判据出自哪里）
        self._write_valid()
        p = self._pub()
        t = open(p, encoding="utf-8").read()
        self.write("specs/general/verify.adoc", t.replace("ISO/IEC Directives Part 2", "某标准"))
        cm.check_verify_guard()
        self.assertIn("ISO/IEC Directives Part 2", self.error_texts())

    def test_missing_runtime_contract_section_reports(self):
        # 反例：③只在文字上出现、却指不到判据（「运行契约」节被删）
        self._write_valid()
        p = self._pub()
        t = open(p, encoding="utf-8").read()
        self.write("specs/general/verify.adoc",
                   t.replace("=== 运行契约（公共内容被未知项目加载时的可控性）", "=== 别的节"))
        cm.check_verify_guard()
        self.assertIn("运行契约", self.error_texts())

    def test_dropped_criterion_reports(self):
        # 反例：重构时把②的判据中的「读的形态」静默删掉（内容减少，不是等价改写）
        self._write_valid()
        p = self._pub()
        t = open(p, encoding="utf-8").read()
        self.write("specs/general/verify.adoc", t.replace("读的形态", "某某形态"))
        cm.check_verify_guard()
        self.assertIn("读的形态", self.error_texts())

    def test_missing_maintainer_landing_point_reports(self):
        # 反例：维护方的验证义务落点被删（三视角在维护方一侧无人执行）
        self._write_valid()
        self.write("specs-project-maintainer/verify.adoc", "= 空\n")
        cm.check_verify_guard()
        self.assertIn("specs-project-maintainer/verify.adoc", self.error_texts())

    def test_p2_without_three_lenses_reports(self):
        # 反例：P2（最高关注项）退回"只核对要点是否全保留"
        self._write_valid()
        self.write("specs-project-maintainer/priority.adoc", "P2：改完跑机械校验 + 干净子 agent 语义复核。\n")
        cm.check_verify_guard()
        self.assertIn("specs-project-maintainer/priority.adoc", self.error_texts())

    def test_own_agents_without_three_lenses_reports(self):
        # 反例：本仓库 AGENTS.adoc 的完整性校验动作未同步三视角
        self._write_valid()
        self.write("AGENTS.adoc", "完整性校验：跑脚本 + 干净子 agent 复核要点。\n")
        cm.check_verify_guard()
        self.assertIn("AGENTS.adoc", self.error_texts())

    # ----- 接纳面防线（未知项目加载）-----

    def test_adoption_guard_missing_file_reports(self):
        # 反例：运行契约所在文件整体被删
        self.write("AGENTS_COMMON.adoc", "= t")
        cm.check_adoption_guard()
        self.assertIn("缺少验证与运行契约文件", self.error_texts())

    def test_adoption_guard_missing_section_reports(self):
        # 反例：「运行契约」节被删（未知项目加载的可控性重新无人负责）
        self.write("specs/general/verify.adoc", "= 测试规范\n\n== 单元测试\n\n只测必要。\n")
        cm.check_adoption_guard()
        self.assertIn("运行契约", self.error_texts())

    def test_adoption_guard_missing_dimension_reports(self):
        # 反例：三维中少一维（如可控性被删）= 判据不完整
        self.write("specs/general/verify.adoc",
                   "= 测试规范\n\n== 运行契约（未知项目加载）\n\n"
                   "① 影响面；② 成本；降级路径；不得让引用方依赖本仓库私有物；"
                   "依据 ISO 9241-110；接纳面须留证。\n")
        self.write("specs-project-maintainer/context.adoc",
                   "= 维护方清单\n\n运行契约：影响面 / 成本 / 可控性三维。\n")
        cm.check_adoption_guard()
        self.assertIn("③ 可控性", self.error_texts())

    def test_adoption_guard_missing_maintainer_list_reports(self):
        # 反例：维护方承接清单被删（维护方在新增公共内容时的核对职责无人承载）
        self.write("specs/general/verify.adoc",
                   "= 测试规范\n\n== 运行契约\n\n① 影响面；② 成本；③ 可控性；降级路径；"
                   "不得让引用方依赖本仓库私有物；依据 ISO 9241-110；接纳面须留证。\n")
        cm.check_adoption_guard()
        self.assertIn("specs-project-maintainer/context.adoc", self.error_texts())

    def test_public_content_private_ref_reports(self):
        # 反例：公共内容（specs/）把本仓库私有物当抓手引用 → 引用方读到死链
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/execution.adoc",
                   "= 执行原则\n\n本仓库自身的机械校验见 `script/check_specs.py` 的工具声明。\n")
        cm.check_public_content_has_no_private_refs()
        self.assertIn("script/check_specs.py", self.error_texts())

    def test_public_content_legitimate_agents_and_changelog_not_reported(self):
        # 正例：`AGENTS.adoc` 作为"引用方自己的项目规范"、`CHANGELOG.adoc` 作为通用默认
        # 文件名被提及，均为规范有意为之，不得误判为私有引用
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc",
                   "只对某个项目成立 → 该项目自身规范（引用方项目根目录 `AGENTS.adoc`）；"
                   "变更日志默认项目根 `CHANGELOG.adoc`。\n")
        cm.check_public_content_has_no_private_refs()
        self.assertEqual(cm.errors, [])


class TestCheckPublicContentSelfContained(CheckSpecsTestCase):
    """钉住「公共内容自足性」：公共内容不得引用引用方拿不到的私有落点。

    背景（本次重构暴露的真实缺陷）：**一个文件可以同时装着公共规则与项目自身规则**。
    它躺在公共侧（`specs/`）时，其中的项目自身落点就成了引用方读不到的死链——
    "本仓库的优先级见某私有文件"这类话，引用方既没有该文件、也没有加载它的入口，
    读到的规范只成立一半。故作防线：公共内容（`AGENTS_COMMON.adoc` + `specs/`）
    不得出现指向维护方自查层（`specs-project-maintainer/`）的引用。
    """

    def test_private_layer_ref_in_public_specs_reports(self):
        # 反例：公共规范正文引用维护方自查层的文件
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/testing.adoc",
                   "= 测试规范\n\n验证口径见 `specs-project-maintainer/verify.adoc`。\n")
        cm.check_public_content_is_self_contained()
        self.assertIn("specs-project-maintainer/", self.error_texts())

    def test_private_layer_ref_in_entry_reports(self):
        # 反例：公共入口（加载调度器）登记维护方自查层 → 引用方按调度器找不到该文件
        self.write("AGENTS_COMMON.adoc",
                   "= 入口\n\n项目自身维护层：link:specs-project-maintainer/priority.adoc[]\n")
        cm.check_public_content_is_self_contained()
        self.assertIn("specs-project-maintainer/", self.error_texts())

    def test_self_contained_public_content_passes(self):
        # 正例：公共内容里的规则全部在公共文件内自足表达
        self.write("AGENTS_COMMON.adoc",
                   "= 入口\n\n分级见 link:specs/core/execution.adoc[]「分级与最高关注项」\n")
        self.write("specs/general/testing.adoc",
                   "= 测试规范\n\n验证口径见 link:../core/execution.adoc[]。\n")
        cm.check_public_content_is_self_contained()
        self.assertEqual(cm.errors, [])

    def test_own_agents_adoc_may_reference_private_layer(self):
        # 正例：根 AGENTS.adoc 是项目自身内容，可以引用维护方自查层
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("AGENTS.adoc",
                   "= 项目自身规范\n\n最高关注项见 link:specs-project-maintainer/priority.adoc[]\n")
        cm.check_public_content_is_self_contained()
        self.assertEqual(cm.errors, [])

    def test_private_layer_ref_in_prompts_reports(self):
        # 反例：prompts/*.adoc 会被复制到未知项目执行，其私有落点同样是引用方读不到的死链
        # （PUBLIC.adoc：「自足要求的适用范围」②类，明写机械检查按公共内容口径覆盖它们）
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("prompts/review.adoc",
                   "= 提示词\n\n核对见 `specs-project-maintainer/verify.adoc`。\n")
        cm.check_public_content_is_self_contained()
        self.assertIn("prompts/review.adoc", self.error_texts())

    def test_prompts_without_private_refs_passes(self):
        # 正例：提示词自足表达，不指向本仓库私有落点
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("prompts/review.adoc",
                   "= 提示词\n\n加载项目规范入口后按规范执行。\n")
        cm.check_public_content_is_self_contained()
        self.assertEqual(cm.errors, [])

    def test_library_ref_in_public_specs_reports(self):
        # 反例：**图书馆与维护方自查层同属"不在默认引用面内"的落点**，公共内容里指向
        # `library/` 的路径同样是引用方读不到的死链。
        # 本轮实测失效：新增的「包源与镜像源」条在 specs/general/ci-cd.adoc 等处写了
        # link:../../library/mirrors.adoc[]，而当时三条防线全绿放过——本条此前只拦
        # `specs-project-maintainer/`。
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/dependency.adoc",
                   "= 依赖\n\n实测记录见 link:../../library/mirrors.adoc[]。\n")
        cm.check_public_content_is_self_contained()
        self.assertIn("library/", self.error_texts())

    def test_library_backtick_ref_in_public_specs_reports(self):
        # 反例：反引号写法同样命中（不只看 link: 形态）
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/core/execution.adoc",
                   "= 执行\n\n论证见 `library/adoption.adoc`。\n")
        cm.check_public_content_is_self_contained()
        self.assertIn("library/", self.error_texts())

    def test_library_name_without_path_passes(self):
        # 正例：只给**依据名**、不给可点开的路径，属正当表述（不得误伤）
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/dependency.adoc",
                   "= 依赖\n\n实测取值属依据，见图书馆「包源与镜像源」主题"
                   "（依据名：包源与镜像源（推荐次序与实测记录））。\n")
        cm.check_public_content_is_self_contained()
        self.assertEqual(cm.errors, [])

    def test_own_agents_adoc_may_reference_library(self):
        # 正例：根 AGENTS.adoc 是项目自身内容，可以引用图书馆
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("AGENTS.adoc",
                   "= 项目自身规范\n\n依据图书馆入口 link:library/README.adoc[]\n")
        cm.check_public_content_is_self_contained()
        self.assertEqual(cm.errors, [])


class TestCheckNoMechanismClaimsInPublic(CheckSpecsTestCase):
    """钉住「公共内容不得声明机械防线」：机械防线只有维护规范集合的那一方有。

    背景（放错位置的一类）：公共内容会被**未知项目**加载，那个项目里没有维护方的
    校验脚本与防线。公共内容一旦写"当前由某防线钉住""本仓库另有防线"或裸防线名
    （`check_xxx_yyy`），引用方读到的就是**宣称与实际不符**——规范文本声称有抓手，
    而引用方没有任何抓手可执行。故作防线：声明句与裸防线名都拦住；
    "维护规范集合的项目应设机械防线"这类**要求**（任何维护方都成立）不得误伤。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_extra = (cm.PROMPTS_FILE, cm.README_FILE)
        cm.PROMPTS_FILE = os.path.join(self.root, "PROMPTS.adoc")
        cm.README_FILE = os.path.join(self.root, "README.adoc")

    def tearDown(self) -> None:
        (cm.PROMPTS_FILE, cm.README_FILE) = self._orig_extra
        super().tearDown()

    def test_mechanism_claim_in_specs_reports(self):
        # 反例：公共内容（specs/）声明"当前存在某道防线"——引用方拿不到、也不该依赖
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/execution.adoc",
                   "= 执行原则\n\nP1 本条当前由机械防线钉住。\n")
        cm.check_no_mechanism_claims_in_public()
        self.assertIn("不得声明机械防线的存在", self.error_texts())

    def test_own_side_mechanism_claim_reports(self):
        # 反例：公共内容声明"本仓库另有防线"（私有元信息随规范分发）
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/verify.adoc",
                   "= 验证规范\n\n本仓库另有防线覆盖该项。\n")
        cm.check_no_mechanism_claims_in_public()
        self.assertIn("不得声明机械防线的存在", self.error_texts())

    def test_bare_check_function_name_in_public_reports(self):
        # 反例：公共内容出现裸防线名（私有抓手名）——引用方看不到、无从执行
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/execution.adoc",
                   "= 执行原则\n\nP1 要求：git mv。由 check_priority_guard 钉住。\n")
        cm.check_no_mechanism_claims_in_public()
        self.assertIn("check_priority_guard", self.error_texts())

    def test_public_readme_claim_reports(self):
        # 反例：README.adoc（介绍公共内容范围与形态）声称"当前由某防线钉住公共内容"
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("README.adoc", "= Agent\n\n公共内容当前由机械防线钉住。\n")
        cm.check_no_mechanism_claims_in_public()
        self.assertIn("README.adoc", self.error_texts())

    def test_requirement_to_have_defence_not_reported(self):
        # 正例：**要求**维护方设机械防线属通用规则（任何维护方都成立），不得误伤
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/execution.adoc",
                   "= 执行原则\n\n本条须由机械防线钉住；维护规范集合的项目应自行设机械防线。\n")
        self.write("README.adoc", "= Agent\n\n公共内容只保留要求与判据。\n")
        cm.check_no_mechanism_claims_in_public()
        self.assertEqual(cm.errors, [])

    def test_own_agents_adoc_may_declare_defence(self):
        # 正例：根 AGENTS.adoc 是项目自身内容，可以点名本仓库的具名防线
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("AGENTS.adoc",
                   "= 项目自身规范\n\n本仓库另有防线 check_priority_guard 钉住最高关注项。\n")
        cm.check_no_mechanism_claims_in_public()
        self.assertEqual(cm.errors, [])


class TestCheckLifecycleGuard(CheckSpecsTestCase):
    """钉住「任务生命周期防线」：节点自查、验证边界与拆分判据三处口径不得被删。

    三处"只在文本上成立、执行时不会真的发生"的缺口：
      * 任务从提出到收尾的**节点没有统一清单** → "做完了才发现方向理解错"，或"流程走完了
        但没人回头看规则是否有问题"（规则慢慢脱离初衷）；
      * **验证没有边界** → 改一行代码被要求三视角、改一条规范只跑机械校验，两头失效；
      * **拆分没有判据** → 多出一个没人维护、判据空转的东西（比不拆更坏）。
    故作防线：三节须仍在、要点齐备、且执行原则 / verify / AGENTS.adoc 三处口径一致。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_files = (cm.EXECUTION_FILE, cm.VERIFY_FILE, cm.ADMISSION_FILE)
        cm.EXECUTION_FILE = os.path.join(self.root, "specs", "core", "execution.adoc")
        cm.VERIFY_FILE = os.path.join(self.root, "specs-project-maintainer", "verify.adoc")
        cm.ADMISSION_FILE = os.path.join(self.root, "specs-project-maintainer", "spec-lifecycle.adoc")

    def tearDown(self) -> None:
        (cm.EXECUTION_FILE, cm.VERIFY_FILE, cm.ADMISSION_FILE) = self._orig_files
        super().tearDown()

    @staticmethod
    def _own_text():
        """本仓库落点：须指向通用层的边界节与拆分判据节。"""
        return ("== 验证的适用范围\n\n见 `specs/general/verify.adoc`「验证与运行契约」之"
                + "「验证的适用边界」；结论强度见「验证的效力等级」；"
                + "拆分判据见「一条规范何时该拆分」；"
                + "维护方验证义务见 `specs-project-maintainer/verify.adoc`。\n")

    @staticmethod
    def _nodes_text(nodes="提出|理解|方案|执行|验证|交付|复盘"):
        """节点清单须以表格行形态出现（`| **节点**（L1）`）——防线按行级钉住。"""
        body = "".join(f"| **{n}**（L1） | 到点必须能回答的问题\n" for n in nodes.split("|"))
        return ("= 执行原则\n\n== 任务生命周期与节点自查\n\n"
                "[cols=\"1,3\"]\n|===\n| 节点 | 到点必须能回答\n"
                + body
                + "|===\n\n* **哪些节点不设（L1）**：代码类改动不设复盘节点。\n")

    def _write_valid(self):
        self.write("specs/core/execution.adoc", self._nodes_text())
        self.write("specs/general/verify.adoc",
                   "= 测试规范\n\n== 验证与运行契约\n\n=== 验证的适用边界\n\n"
                   "先判改动性质：代码类改动按机械判据判过不过、规范类改动做三视角；"
                   "不改内容的操作（C 类）内容逐字节不变、不重跑全量编译与测试，"
                   "\"内容没变\"不是\"少核对\"的借口；"
                   "判据是「会不会被未知项目加载」；不得互串；取**更严的一侧**；"
                   "每次验证都换一个干净上下文；结论按**效力等级**标——确定项可判对错、"
                   "概念项只到未发现，不得当作阻断交付的条件。\n")
        self.write("specs-project-maintainer/verify.adoc",
                   "= 验证的维护方落点\n\n维护方的验证义务与落点。\n")
        self.write("specs-project-maintainer/spec-lifecycle.adoc",
                   "= 规范分类与准入\n\n== 一条规范何时该拆分\n\n"
                   "判据与用处不同；不拆就真的坏；拆后每一半都自足；默认不拆；"
                   "单独过准入九问。\n\n== 拆分后的自洽核对\n\n引用可达。\n")
        self.write("AGENTS.adoc", self._own_text())

    def test_valid_lifecycle_guard_passes(self):
        self._write_valid()
        cm.check_lifecycle_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_lifecycle_section_reports(self):
        # 反例：节点自查节被删（"到哪个节点查什么"重新无人负责）
        self._write_valid()
        self.write("specs/core/execution.adoc", "= 执行原则\n\n== 范围控制\n\n不蔓延。\n")
        cm.check_lifecycle_guard()
        self.assertIn("任务生命周期与节点自查", self.error_texts())

    def test_missing_node_reports(self):
        # 反例：七节点里少一个（如"方案"被删 → 去重删减前不再核覆盖完整性）
        self._write_valid()
        self.write("specs/core/execution.adoc",
                   self._nodes_text("提出|理解|执行|验证|交付|复盘"))
        self.write("AGENTS.adoc", self._own_text())
        cm.check_lifecycle_guard()
        self.assertIn("方案", self.error_texts())

    def test_missing_exemption_reports(self):
        # 反例：未写明哪些节点不设（概念性验证会外溢成所有任务的流程）
        self._write_valid()
        self.write("specs/core/execution.adoc",
                   self._nodes_text().split("* **哪些节点不设")[0])
        cm.check_lifecycle_guard()
        self.assertIn("代码类改动", self.error_texts())

    def test_missing_boundary_section_reports(self):
        # 反例：验证边界节被删（不先判改动性质，验证范围无处取值）
        self._write_valid()
        self.write("specs/general/verify.adoc", "= 测试规范\n\n== 单元测试\n\n跑。\n")
        self.write("AGENTS.adoc", "== 验证的适用范围\n\n见 `specs/general/verify.adoc`"
                   + "「验证与运行契约」；拆分判据见「一条规范何时该拆分」。\n")
        cm.check_lifecycle_guard()
        self.assertIn("验证的适用边界", self.error_texts())

    def test_missing_fresh_context_requirement_reports(self):
        # 反例：删掉"每次验证换一个干净上下文"（复用上下文等于自己复核自己）
        self._write_valid()
        self.write("specs/general/verify.adoc",
                   "= 测试规范\n\n== 验证与运行契约\n\n=== 验证的适用边界\n\n"
                   "先判改动性质：代码类改动按机械判据判过不过、规范类改动做三视角；"
                   "判据是「会不会被未知项目加载」；不得互串；取**更严的一侧**。\n")
        self.write("AGENTS.adoc", self._own_text())
        cm.check_lifecycle_guard()
        self.assertIn("干净上下文", self.error_texts())

    def test_missing_content_unchanged_boundary_reports(self):
        # 反例：删掉"不改内容的操作（C 类）不重跑全量校验"（压缩提交/纯改名又会被要求跑全量构建）
        self._write_valid()
        self.write("specs/general/verify.adoc",
                   "= 测试规范\n\n== 验证与运行契约\n\n=== 验证的适用边界\n\n"
                   "先判改动性质：代码类改动按机械判据判过不过、规范类改动做三视角；"
                   "判据是「会不会被未知项目加载」；不得互串；取**更严的一侧**；"
                   "每次验证都换一个干净上下文；结论按**效力等级**标——确定项可判对错、"
                   "概念项只到未发现，不得当作阻断交付的条件。\n")
        self.write("AGENTS.adoc", self._own_text())
        cm.check_lifecycle_guard()
        self.assertIn("不改内容的操作", self.error_texts())

    def test_missing_split_section_reports(self):
        # 反例：拆分判据节被删（拆分成为新的失控源）
        self._write_valid()
        self.write("specs-project-maintainer/spec-lifecycle.adoc", "= 规范分类与准入\n\n== 准入判定\n\n九问。\n")
        self.write("AGENTS.adoc", self._own_text())
        cm.check_lifecycle_guard()
        self.assertIn("一条规范何时该拆分", self.error_texts())

    def test_missing_split_condition_reports(self):
        # 反例：三条硬条件少一条（如"不拆就真的坏"被删）
        self._write_valid()
        self.write("specs-project-maintainer/spec-lifecycle.adoc",
                   "= 规范分类与准入\n\n== 一条规范何时该拆分\n\n"
                   "判据与用处不同；拆后每一半都自足；默认不拆；单独过准入九问。\n\n"
                   "== 拆分后的自洽核对\n\n引用可达。\n")
        self.write("AGENTS.adoc", self._own_text())
        cm.check_lifecycle_guard()
        self.assertIn("不拆就真的坏", self.error_texts())

    def test_own_agents_missing_landing_reports(self):
        # 反例：本仓库落点未指向通用层边界节（本仓库口径与通用层脱钩）
        self._write_valid()
        self.write("AGENTS.adoc", "== 规范组织\n\n随便写。\n")
        cm.check_lifecycle_guard()
        self.assertIn("AGENTS.adoc", self.error_texts())


class TestCheckJavaTestNaming(CheckSpecsTestCase):
    """钉住 Java 测试类命名契约（四类后缀）在规范与调度器两侧一致。

    后缀与构建工具的执行边界绑定（`PerfTests`/`IT` 不随常规测试执行），任一处漏掉
    某类后缀，引用方照另一处学习就会漏掉该类测试，故两侧都须写明四类判据。
    """

    JAVA_LINE = ("  ** Java 项目（存在 `.java`、`pom.xml`、`mvnw`、lombok 配置等）→ "
                 "link:specs/stack/java.adoc[] + link:specs/stack/java-testing.adoc[]"
                 "（测试类命名契约：`Tests` 常规、`BootTests` 启动型、`PerfTests` 性能、`IT` 端到端；"
                 "一个被测类可按需求/分类拆多个测试类、不得滥拆）")

    def setUp(self) -> None:
        super().setUp()
        self._orig_java = cm.JAVA_TEST_FILE
        cm.JAVA_TEST_FILE = os.path.join(self.root, "specs", "stack", "java-testing.adoc")

    def tearDown(self) -> None:
        cm.JAVA_TEST_FILE = self._orig_java
        super().tearDown()

    def _write_valid(self):
        self.write("specs/stack/java-testing.adoc",
                   "= Java 测试规范\n\n"
                   "== 测试类命名（L1 强制）\n"
                   "测试类名为「被测类名 + 测试类型后缀」：`Tests` 常规、`BootTests` 启动型、"
                   "`PerfTests` 性能、`IT` 端到端；后者独立于常规测试执行。\n"
                   "一个被测类可按需求/分类可拆成多个测试类；分类或属性相同的用例必须"
                   "归入同一个测试类；不得为每个场景一个类而拆，禁止滥拆。\n")
        self.write("AGENTS_COMMON.adoc", self.JAVA_LINE)

    def test_valid_naming_contract_passes(self):
        self._write_valid()
        cm.check_java_test_naming()
        self.assertEqual(cm.errors, [])

    def test_missing_file_reports(self):
        # 反例：Java 测试规范文件整体被删
        self.write("AGENTS_COMMON.adoc", self.JAVA_LINE)
        cm.check_java_test_naming()
        self.assertIn("缺少 Java 测试规范文件", self.error_texts())

    def test_dropped_suffix_reports(self):
        # 反例：规范侧删掉某一类后缀（如 BootTests）
        self.write("specs/stack/java-testing.adoc",
                   "= t\n\n== 测试类命名\n后缀：`Tests`、`PerfTests`、`IT`（被测类名 + 后缀、常规）\n")
        self.write("AGENTS_COMMON.adoc", self.JAVA_LINE)
        cm.check_java_test_naming()
        self.assertIn("BootTests", self.error_texts())

    def test_dispatcher_missing_suffix_reports(self):
        # 反例：调度器只写一半后缀 → 与规范命名契约口径漂移
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "  ** Java 项目 → link:specs/stack/java-testing.adoc[]（含 `Tests` 后缀）")
        cm.check_java_test_naming()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())
        self.assertIn("PerfTests", self.error_texts())

    def test_not_registered_in_dispatcher_reports(self):
        # 反例：文件存在但未登记调度器 → 永不被加载
        self.write("specs/stack/java-testing.adoc",
                   "= t\n\n== 测试类命名\n`Tests` `BootTests` `PerfTests` `IT`（被测类名 + 后缀、常规）")
        self.write("AGENTS_COMMON.adoc", "= t")
        cm.check_java_test_naming()
        self.assertIn("未在加载调度器登记", self.error_texts())

    def test_split_ruling_partial_reports(self):
        # 反例：拆分裁决只剩"合并"那一半（退回"一个被测类一个测试类"）——即本次调整要修掉的口径
        self.write("specs/stack/java-testing.adoc",
                   "= t\n\n== 测试类命名\n`Tests` `BootTests` `PerfTests` `IT`"
                   "（被测类名 + 后缀、常规）\n批量测试同一被测类不同场景时仍合并为一个测试类。\n")
        self.write("AGENTS_COMMON.adoc", self.JAVA_LINE)
        cm.check_java_test_naming()
        self.assertIn("缺失拆分裁决", self.error_texts())

    def test_split_ruling_only_allow_split_reports(self):
        # 反例：只留"可拆"、不留"同分类须归一类 + 禁止滥拆"（放任每个场景一个类）
        self.write("specs/stack/java-testing.adoc",
                   "= t\n\n== 测试类命名\n`Tests` `BootTests` `PerfTests` `IT`"
                   "（被测类名 + 后缀、常规）\n一个被测类可按需求/分类可拆成多个测试类。\n")
        self.write("AGENTS_COMMON.adoc", self.JAVA_LINE)
        cm.check_java_test_naming()
        self.assertIn("缺失拆分裁决", self.error_texts())

    def test_split_ruling_valid_passes(self):
        # 正例：三段判据齐备（可拆 + 同分类同属性须归一类 + 禁止滥拆）
        self._write_valid()
        cm.check_java_test_naming()
        self.assertEqual(cm.errors, [])

    def test_dispatcher_without_split_ruling_reports(self):
        # 反例：调度器只传达后缀、不传达拆分裁决 → 引用方把"一个被测类一个测试类"当硬规定
        self.write("specs/stack/java-testing.adoc",
                   "= t\n\n== 测试类命名（L1 强制）\n"
                   "测试类名为「被测类名 + 测试类型后缀」：`Tests` 常规、`BootTests` 启动型、"
                   "`PerfTests` 性能、`IT` 端到端；后者独立于常规测试执行。\n"
                   "一个被测类可按需求/分类可拆成多个测试类；分类或属性相同的用例必须"
                   "归入同一个测试类；不得为每个场景一个类而拆，禁止滥拆。\n")
        self.write("AGENTS_COMMON.adoc",
                   "  ** Java 项目 → link:specs/stack/java-testing.adoc[]"
                   "（测试类命名契约：`Tests` 常规、`BootTests` 启动型、`PerfTests` 性能、`IT` 端到端）")
        cm.check_java_test_naming()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())
        self.assertIn("滥拆", self.error_texts())


class TestCheckLineEndingGuard(CheckSpecsTestCase):
    """钉住跨平台换行符规则（LF 基准 + Windows 批处理 CRLF）。

    行尾错配是"跨平台直接执行失败"（`.bat` 在 LF 下不可执行），且"统一换行符"式的
    精简最易把它删成一句空话，故机械钉住判据与配套栈文件。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_enc = cm.ENCODING_FILE
        self._orig_stack = cm.LINE_ENDING_STACK_FILES
        cm.ENCODING_FILE = os.path.join(self.root, "specs", "general", "encoding.adoc")
        cm.LINE_ENDING_STACK_FILES = tuple(
            os.path.join(self.root, "specs", "stack", f)
            for f in ("bash.adoc", "python.adoc", "powershell.adoc"))

    def tearDown(self) -> None:
        cm.ENCODING_FILE = self._orig_enc
        cm.LINE_ENDING_STACK_FILES = self._orig_stack
        super().tearDown()

    def _write_valid(self):
        self.write("specs/general/encoding.adoc",
                   "= 编码与语言无关\n\n"
                   "== 换行符（行尾）\n"
                   "内容以 LF 为基准；`.bat`/`.cmd` 必须 CRLF；`.ps1` 用 CRLF；"
                   "由 `.gitattributes`（行尾）与 `.editorconfig` 固定，"
                   "`core.autocrlf` 交给仓库配置、不靠人工手动调整。\n")
        for f in ("bash.adoc", "python.adoc", "powershell.adoc"):
            self.write(f"specs/stack/{f}", "行尾：按本栈要求（LF 或 CRLF）\n")
        self.write("AGENTS_COMMON.adoc", "登记 `specs/general/encoding.adoc`")

    def test_valid_line_ending_rules_pass(self):
        self._write_valid()
        cm.check_line_ending_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_encoding_file_reports(self):
        # 反例：编码规范文件整体被删 → 行尾判据失去集中落点
        self.write("AGENTS_COMMON.adoc", "= t")
        cm.check_line_ending_guard()
        self.assertIn("缺少编码与语言无关规范文件", self.error_texts())

    def test_dropped_windows_batch_crlf_reports(self):
        # 反例：删掉 `.bat` 必须 CRLF（这正是"BAT 用 Linux 换行符"的失效源头）
        self.write("specs/general/encoding.adoc",
                   "= t\n\n== 换行符（行尾）\n内容以 LF 为基准；`.ps1` 用 CRLF；"
                   "由 `.gitattributes` 固定，`core.autocrlf` 交给仓库配置、不靠人工手动调整。\n")
        for f in ("bash.adoc", "python.adoc", "powershell.adoc"):
            self.write(f"specs/stack/{f}", "行尾：LF\n")
        self.write("AGENTS_COMMON.adoc", "登记 `specs/general/encoding.adoc`")
        cm.check_line_ending_guard()
        self.assertIn(".bat", self.error_texts())

    def test_dropped_checkout_normalization_reports(self):
        # 反例：删掉"不靠人工手动调整"的检出归一依据（core.autocrlf/.gitattributes）
        self.write("specs/general/encoding.adoc",
                   "= t\n\n== 换行符（行尾）\n内容以 LF 为基准；`.bat`/`.cmd` 必须 CRLF。\n")
        for f in ("bash.adoc", "python.adoc", "powershell.adoc"):
            self.write(f"specs/stack/{f}", "行尾：LF\n")
        self.write("AGENTS_COMMON.adoc", "登记 `specs/general/encoding.adoc`")
        cm.check_line_ending_guard()
        self.assertIn(".gitattributes", self.error_texts())

    def test_dropped_editorconfig_reports(self):
        # 反例：删掉 `.editorconfig` 落盘口 → 编辑器侧的行尾无人固定
        self.write("specs/general/encoding.adoc",
                   "= t\n\n== 换行符（行尾）\n内容以 LF 为基准；"
                   "`.bat`/`.cmd` 必须 CRLF；"
                   "由 `.gitattributes` 固定，`core.autocrlf` 交给仓库配置、不靠人工手动调整。\n")
        for f in ("bash.adoc", "python.adoc", "powershell.adoc"):
            self.write(f"specs/stack/{f}", "行尾：LF\n")
        self.write("AGENTS_COMMON.adoc", "登记 `specs/general/encoding.adoc`")
        cm.check_line_ending_guard()
        self.assertIn(".editorconfig", self.error_texts())

    def test_stack_file_without_line_ending_reports(self):
        # 反例：脚本栈文件未写明行尾要求 → 引用方按该栈文件学习学不到
        self._write_valid()
        self.write("specs/stack/python.adoc", "= Python 脚本规范\n")
        cm.check_line_ending_guard()
        self.assertIn("specs/stack/python.adoc", self.error_texts())

    def test_not_registered_in_dispatcher_reports(self):
        # 反例：文件存在但未登记调度器 → 永不被加载
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "= t")
        cm.check_line_ending_guard()
        self.assertIn("未在加载调度器登记", self.error_texts())


class TestCheckPromptsPrimary(CheckSpecsTestCase):
    """钉住提示词的「主侧重（方向前提）」与「优先级规则（L1/L2/L3）」。

    侧重是方向性内容、错了后面全做错，故与最高关注项一样加机械防线：登记表、正文
    侧重声明、公共片段注入、分级与业界依据缺一即报。
    """

    COMMON = (
        "提示词公共片段\n"
        "// tag::priority-rules[]\n"
        "优先级规则：按 RFC 2119 与 ISO/IEC Directives Part 2 执行——"
        "必须/严禁 = L1 强制、应当 = L2 建议、可以 = L3 允许；不可降级。\n"
        "// end::priority-rules[]\n")

    def setUp(self) -> None:
        super().setUp()
        self._orig_prompts = (cm.PROMPTS_FILE, cm.PROMPTS_DIR, cm.COMMON_PROMPT_FILE)
        cm.PROMPTS_FILE = os.path.join(self.root, "PROMPTS.adoc")
        cm.PROMPTS_DIR = os.path.join(self.root, "prompts")
        cm.COMMON_PROMPT_FILE = os.path.join(self.root, "prompts", "_common.txt")

    def tearDown(self) -> None:
        (cm.PROMPTS_FILE, cm.PROMPTS_DIR,
         cm.COMMON_PROMPT_FILE) = self._orig_prompts
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("prompts/_common.txt", self.COMMON)
        self.write("PROMPTS.adoc",
                   "| link:prompts/review.adoc[] | **检查修复问题** | 主侧重片段 `primary` |\n"
                   "| link:prompts/refactor.adoc[] | **重构** | 主侧重片段 `primary` |\n")
        self.write("prompts/review.adoc",
                   "**主侧重（方向性前提）**：**检查修复问题**——方向错了后面全做错。\n"
                   "include::_common.txt[tag=primary]\n"
                   "include::_common.txt[tag=priority-rules]\n")
        self.write("prompts/refactor.adoc",
                   "**主侧重（方向性前提）**：**\"重构\"**——方向错了后面全做错。\n"
                   "include::_common.txt[tag=primary]\n"
                   "include::_common.txt[tag=priority-rules]\n")

    def test_valid_prompts_pass(self):
        self._write_valid()
        cm.check_prompts_primary()
        self.assertEqual(cm.errors, [])

    def test_missing_registry_reports(self):
        # 反例：登记入口整体被删（侧重无处登记）
        self._write_valid()
        os.remove(cm.PROMPTS_FILE)
        cm.check_prompts_primary()
        self.assertIn("缺少提示词登记入口", self.error_texts())

    def test_registry_without_primary_column_reports(self):
        # 反例：登记表丢了主侧重列（只登记用途，方向信息消失）
        self._write_valid()
        self.write("PROMPTS.adoc",
                   "| link:prompts/review.adoc[] | 检查修复问题 |\n"
                   "| link:prompts/refactor.adoc[] | 重构 |\n")
        cm.check_prompts_primary()
        self.assertIn("主侧重", self.error_texts())

    def test_prompt_without_primary_direction_reports(self):
        # 反例：提示词未声明主侧重（删掉方向性前提）→ 方向丢失
        self._write_valid()
        self.write("prompts/refactor.adoc",
                   "对本项目执行一次全量重构。\n"
                   "include::_common.txt[tag=primary]\n")
        cm.check_prompts_primary()
        self.assertIn("未显式声明", self.error_texts())
        self.assertIn("priority-rules", self.error_texts())

    def test_primary_not_in_registry_reports(self):
        # 反例：正文侧重与登记表不一致（侧重未登记 = 方向不明）
        self._write_valid()
        self.write("prompts/refactor.adoc",
                   "**主侧重（方向性前提）**：**重写架构**——方向错了后面全做错。\n"
                   "include::_common.txt[tag=primary]\n"
                   "include::_common.txt[tag=priority-rules]\n")
        cm.check_prompts_primary()
        self.assertIn("未在", self.error_texts())

    def test_same_primary_for_both_prompts_reports(self):
        # 反例：两个提示词侧重被复制成同一个（方向混用）
        self._write_valid()
        self.write("prompts/refactor.adoc",
                   "**主侧重（方向性前提）**：**检查修复问题**——方向错了后面全做错。\n"
                   "include::_common.txt[tag=primary]\n"
                   "include::_common.txt[tag=priority-rules]\n")
        cm.check_prompts_primary()
        self.assertIn("侧重出现重复", self.error_texts())

    def test_priority_rules_missing_level_reports(self):
        # 反例：优先级分级被删（只剩 L1）→ 无法判断哪里是重点
        self._write_valid()
        self.write("prompts/_common.txt",
                   "// tag::priority-rules[]\n必须 = L1 强制；按 RFC 2119 与 ISO 执行。\n"
                   "// end::priority-rules[]\n")
        cm.check_prompts_primary()
        self.assertIn("L2 建议", self.error_texts())
        self.assertIn("L3 允许", self.error_texts())

    def test_priority_rules_missing_industry_basis_reports(self):
        # 反例：去掉业界共识依据（要求"按业界共识加载优先级"就失去出处）
        self._write_valid()
        self.write("prompts/_common.txt",
                   "// tag::priority-rules[]\n"
                   "必须 = L1 强制、应当 = L2 建议、可以 = L3 允许；不可降级。\n"
                   "// end::priority-rules[]\n")
        cm.check_prompts_primary()
        self.assertIn("RFC 2119", self.error_texts())

    def test_priority_rules_without_non_downgrade_reports(self):
        # 反例：去掉"不可降级"= 允许 L1 被降为建议
        self._write_valid()
        self.write("prompts/_common.txt",
                   "// tag::priority-rules[]\n"
                   "按 RFC 2119 与 ISO 执行：必须 = L1 强制、应当 = L2 建议、可以 = L3 允许。\n"
                   "// end::priority-rules[]\n")
        cm.check_prompts_primary()
        self.assertIn("不可降级", self.error_texts())

    def test_conflicting_primary_within_prompt_reports(self):
        # 反例：同一提示词内两处侧重写法不一致（方向自相矛盾）
        self._write_valid()
        self.write("prompts/refactor.adoc",
                   "**主侧重（方向性前提）**：**重构**——方向错了后面全做错。\n"
                   "**主侧重（方向性前提）**：**检查修复问题**——方向错了后面全做错。\n"
                   "include::_common.txt[tag=primary]\n"
                   "include::_common.txt[tag=priority-rules]\n")
        cm.check_prompts_primary()
        self.assertIn("写法不一致", self.error_texts())

    def test_primary_fragment_injected(self):
        # 正例：代码块内须注入 primary 片段本身（防只留说明段、片段被删）
        self._write_valid()
        cm.check_prompts_primary()
        self.assertEqual(cm.errors, [])


class TestCheckDevFlowGuard(CheckSpecsTestCase):
    """钉住『开发流程防线』（用户提出的开发流程要求，本项目实测失效）。

    失效形态：不摸现状直接动手（按想象改）；绕开既有实现另写一套（留下两套实现/配置/文档，
    达不到最佳实践）；重构后把老用例改掉让它"通过"（既有行为的规格被改动方单方面改判）；
    兼容不了就自行取舍（老旧废弃流程的处置被执行者自行认定）。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_prompts = (cm.PROMPTS_DIR, cm.PROMPTS_FILE, cm.README_FILE,
                              cm.COMMON_PROMPT_FILE)
        cm.PROMPTS_DIR = os.path.join(self.root, "prompts")
        cm.PROMPTS_FILE = os.path.join(self.root, "PROMPTS.adoc")
        cm.README_FILE = os.path.join(self.root, "README.adoc")
        cm.COMMON_PROMPT_FILE = os.path.join(self.root, "prompts", "_common.txt")

    def tearDown(self) -> None:
        (cm.PROMPTS_DIR, cm.PROMPTS_FILE, cm.README_FILE,
         cm.COMMON_PROMPT_FILE) = self._orig_prompts
        super().tearDown()

    def _write_valid(self):
        self.write("specs/core/execution.adoc",
                   "= 执行原则\n\n== 先规划后执行\n\n"
                   "* **动手前先摸清现状与最佳方案（L1）**：先搞清现状，再**先调研最佳实践、再定方案**。\n"
                   "* 不得绕开既有体系另写一套（L1）：默认改在既有实现上；"
                   "**允许另写一套的条件只有三个**：确实无法承载 / 已被用户确认废弃 / 已被证明优于，**不留两套并存**。\n"
                   "* 大范围改动先确认（L1）：**不得替用户判定某段既有流程\"已废弃\"**。\n"
                   "* 改动前先定基线（L1）：**扫描项目声明的全部校验手段**，**完整可用时必须先跑通**，"
                   "并**落盘留证**，改动完成后**复跑同一套校验**；**扫出的清单还要先核\"够不够用\"（L2）**："
                   "须**先按用例设计判据 review 既有用例**，**本次改动的直接相关面**先补全、**不阻断动手**。\n\n== 任务生命周期与节点自查\n\n"
                   "| **方案** | **基线是否已定**\n"
                   "| **验证** | **是否与基线逐项比对**\n\n== 下节\n")
        self.write("specs/general/planning.adoc",
                   "= 任务规划\n\n== 动手前：现状与最佳方案\n\n"
                   "* **先查现状（L1）**：**不得凭印象或标题推断**，并列出**核实方式**。\n"
                   "* **先调研最佳方案（L1）**：列出**备选方案与取舍依据**，不得只给\"能交差\"的写法。\n\n"
                   "== 不得绕开既有体系另写一套\n\n* **默认改在既有实现上（L1）**："
                   "**确实无法承载** / **已被用户确认废弃** / **已被证明优于**；**不留两套并存**。\n\n"
                   "== 大范围改动先确认\n\n* **大动之前先确认（L1）**：**保持原状**；"
                   "**是否废弃只能由用户认定**。\n\n== 动手前先定基线\n\n"
                   "* **扫描既有验证手段（L1）**\n* **能跑通即跑通、并落盘留证（L1）**\n"
                   "* **留证的形态按项目自身的交付约定**：**留证不等于「必须提交」**。\n"
                   "* **不完整或本来就红时怎么办（L1，防把基线变成硬性前置）**："
                   "**没有任何校验手段**时记录即可开工；**红的还是红的**。\n"
                   "* **基线用于改完复跑（L1）**：**既有用例不得为迁就改动而改判**。\n"
                   "* **基线的完整性：手段与用例够不够用（L2）**：**先按这些判据 review 既有用例**，"
                   "给出**复核了哪些角度与样本**；按**正常路径**/边界/异常路径/**正反例成对**/步骤与前置核对，"
                   "**用例设计**与**测试有效性**判据见 testing.adoc；**本次改动的直接相关面**先补全，"
                   "**无关的存量缺口**如实记录、**不阻断**。\n\n"
                   "=== 依据（标准名/编号）\n\n* **ISO 10007**（配置管理）。\n")
        self.write("specs/general/verify.adoc",
                   "= 验证\n\n* **验证须覆盖项目的全部既定校验手段（L1）**：**存在测试**≠**测试被执行**；"
                   "手段与其用例**本身可能不完整**，须**先按 link:testing.adoc[]「用例设计」review**、"
                   "说明\"哪些未覆盖\"，**本次改动的直接相关面**先补全。\n")
        self.write("specs/general/testing.adoc",
                   "= 测试\n\n* 重构后须**同时满足既有用例与新用例**（L1）："
                   "**既有用例不得为迁就重构而改判**（除**相关功能被显式移除**）、**前后完整兼容**"
                   "（参考 **Semantic Versioning**）。\n"
                   "* 兼容性无法满足时先确认（L1）：**兼容不了**先停下确认，"
                   "**老旧废弃流程**是否废弃由用户认定、**不得自行取舍**。\n")
        self.write("prompts/_common.txt",
                   "// tag::baseline-and-compat[]\n"
                   "**动手前：先定基线 + 先查现状 + 先调研最佳方案（L1，方向性前提）**\n"
                   "  - **先查现状、再谈方案**\n  - **先定基线**\n  - **大动之前先确认**\n"
                   "  - **不得绕开既有实现另写一套**\n"
                   "  - **基线清单还要核\"够不够用\"（L2）**：**review 既有用例**、"
                   "**无关的存量缺口**如实记录。\n"
                   "  - **没有校验手段、环境跑不起来，都不是不动手的理由**\n"
                   "// end::baseline-and-compat[]\n\n// tag::compat[]\n"
                   "**改动后：老用例与新用例必须同时成立（L1）**\n"
                   "  - **既有用例不得为迁就改动而改判**\n"
                   "  - **新老用例在同一套校验里同时全绿**\n  - **兼容不了就停下确认**\n"
                   "  - **验证须与基线比对**\n// end::compat[]\n")
        for name in ("review.adoc", "refactor.adoc"):
            self.write(f"prompts/{name}",
                       "= 提示词\n\ninclude::_common.txt[tag=baseline]\n"
                       "include::_common.txt[tag=baseline-and-compat]\n"
                       "include::_common.txt[tag=compat]\n")
        self.write("AGENTS_COMMON.adoc",
                   "= 入口\n\n  ** 动手前的现状与方案、基线 → link:specs/general/planning.adoc[]\n")
        self.write("PROMPTS.adoc",
                   "= 提示词入口\n\n公共约定：**先定基线**、`baseline-and-compat`、`compat`。\n")
        self.write("README.adoc",
                   "= 说明\n\n**先定基线**；**既有用例不得为迁就改动而改判**。\n")

    def test_valid_dev_flow_guard_passes(self):
        self._write_valid()
        cm.check_dev_flow_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_baseline_clause_reports(self):
        # 反例：基线条被删（"改完有没有破坏既有行为"失去尺子）
        self._write_valid()
        self.write("specs/core/execution.adoc", "= 执行原则\n\n== 先规划后执行\n\n动手前先规划。\n")
        cm.check_dev_flow_guard()
        self.assertIn("改动前先定基线", self.error_texts())

    def test_missing_planning_file_reports(self):
        # 反例：通用层展开文件被删（必加载层只剩底线，条件判据无处可查）
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "general", "planning.adoc"))
        cm.check_dev_flow_guard()
        self.assertIn("planning.adoc", self.error_texts())

    def test_old_cases_may_be_rewritten_clause_removed_reports(self):
        # 反例：「既有用例不得为迁就重构而改判」被删（改老用例变绿重成默认做法）
        self._write_valid()
        self.write("specs/general/testing.adoc", "= 测试\n\n修改代码后须确保既有用例全部通过。\n")
        cm.check_dev_flow_guard()
        self.assertIn("testing.adoc", self.error_texts())

    def test_missing_prompt_fragment_reports(self):
        # 反例：公共片段被删（提示词复制到未知项目后这条边界整条丢失）
        self._write_valid()
        self.write("prompts/_common.txt", "// tag::baseline[]\n1. 规范与基线。\n// end::baseline[]\n")
        cm.check_dev_flow_guard()
        self.assertIn("baseline-and-compat", self.error_texts())

    def test_prompt_missing_include_reports(self):
        # 反例：提示词代码块少一个 include（题面未装配该边界）
        self._write_valid()
        self.write("prompts/review.adoc",
                   "= 提示词\n\ninclude::_common.txt[tag=baseline-and-compat]\n")
        cm.check_dev_flow_guard()
        self.assertIn("compat", self.error_texts())

    def test_baseline_has_no_fallback_branch_reports(self):
        # 反例：基线条缺"无手段/红测试不阻断"的降级分支
        # （会把基线变成引用方的硬性前置：没有测试的项目从此动不了手）
        self._write_valid()
        self.write("specs/general/planning.adoc",
                   "= 任务规划\n\n== 动手前先定基线\n\n"
                   "* **扫描既有验证手段（L1）**\n* **能跑通即跑通、并落盘留证（L1）**\n"
                   "* **基线用于改完复跑（L1）**\n")
        cm.check_dev_flow_guard()
        self.assertIn("降级分支", self.error_texts())

    def test_baseline_without_completeness_clause_reports(self):
        # 反例：基线只要求"扫一遍声明的命令"，缺"清单够不够用"（手段/用例本身可能不全）
        self._write_valid()
        self.write("specs/general/planning.adoc",
                   "= 任务规划\n\n== 动手前先定基线\n\n"
                   "* **扫描既有验证手段（L1）**\n* **能跑通即跑通、并落盘留证（L1）**\n"
                   "* **留证的形态按项目自身的交付约定**：**留证不等于「必须提交」**。\n"
                   "* **不完整或本来就红时怎么办（L1，防把基线变成硬性前置）**："
                   "**没有任何校验手段**时记录即可开工；**红的还是红的**。\n"
                   "* **基线用于改完复跑（L1）**：**既有用例不得为迁就改动而改判**。\n")
        cm.check_dev_flow_guard()
        self.assertIn("基线完整性", self.error_texts())

    def test_baseline_completeness_without_scope_boundary_reports(self):
        # 反例：基线完整性条缺"只补本次直接相关面 / 无关存量缺口不阻断"
        # （会把"先补齐所有用例"读成动手的硬性前置——基线变硬性前置的第二种形态）
        self._write_valid()
        pl = os.path.join(self.root, "specs", "general", "planning.adoc")
        text = open(pl, encoding="utf-8").read().replace(
            "**本次改动的直接相关面**先补全，**无关的存量缺口**如实记录、**不阻断**。",
            "须把发现的缺口全部补全。")
        open(pl, "w", encoding="utf-8").write(text)
        cm.check_dev_flow_guard()
        self.assertIn("直接相关面", self.error_texts())

    def test_verify_side_without_completeness_reports(self):
        # 反例：验证侧只说"须覆盖全部既定校验手段"、不说"跑的那套够不够用"
        self._write_valid()
        self.write("specs/general/verify.adoc",
                   "= 验证\n\n* **验证须覆盖项目的全部既定校验手段（L1）**：存在测试≠测试被执行。\n")
        cm.check_dev_flow_guard()
        self.assertIn("verify.adoc", self.error_texts())

    def test_prompt_fragment_without_completeness_reports(self):
        # 反例：公共片段缺"清单还要核够不够用"（复制到未知项目后这条边界整条丢失）
        self._write_valid()
        cf = os.path.join(self.root, "prompts", "_common.txt")
        text = open(cf, encoding="utf-8").read().replace(
            "  - **基线清单还要核\"够不够用\"（L2）**：**review 既有用例**、"
            "**无关的存量缺口**如实记录。\n", "")
        open(cf, "w", encoding="utf-8").write(text)
        cm.check_dev_flow_guard()
        self.assertIn("够不够用", self.error_texts())

    def test_prompt_fragment_without_fallback_reports(self):
        # 反例：公共片段缺"没手段/红测试也不是不动手的理由"
        self._write_valid()
        cf = os.path.join(self.root, "prompts", "_common.txt")
        text = open(cf, encoding="utf-8").read().replace(
            "  - **没有校验手段、环境跑不起来，都不是不动手的理由**\n", "")
        open(cf, "w", encoding="utf-8").write(text)
        cm.check_dev_flow_guard()
        self.assertIn("都不是不动手的理由", self.error_texts())

    def test_dispatcher_not_registered_reports(self):
        # 反例：调度器未登记（该文件不会被加载，其中规则实际失效）
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "= 入口\n\n  ** 自检 → link:specs/general/self-check.adoc[]\n")
        cm.check_dev_flow_guard()
        self.assertIn("未登记", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例：公开面未同步（公开面读不到这条边界）
        self._write_valid()
        self.write("README.adoc", "= 说明\n\n普通说明。\n")
        cm.check_dev_flow_guard()
        self.assertIn("README.adoc", self.error_texts())


class TestCheckChangelogTimingGuard(CheckSpecsTestCase):
    """钉住『变更日志声明优先防线』（用户明确提出：除非主动声明否则不新增、不修改）。

    两类失效形态（本项目实证，分别对应两次收紧）：
      * ①执行者把"我改动了东西"与"该记一条 changelog"画等号，每轮改动都自行追加条目；
      * ②用户只说"调整一下项目规范"、并未提到 changelog，执行者把"改文档"扩大成
        "改 changelog"，顺手新增了条目——旧条文只写正向（何时可以写），没写这条越界形态。
    """

    def _write_valid(self):
        self.write("AGENTS.adoc",
                   "= 项目入口\n\n* 登记时机（**主动声明**才算）：**除非用户主动声明，否则一律不新增、不修改本文件**"
                   "——「主动声明」指用户**本次明确要求**新增、修改、整理或压缩 changelog；"
                   "**其余一切情形按\"未声明\"处理**：未提到该文件、**只要求更新文档或 README**、只说\"改动了什么\"，"
                   "均**不得**新增条目（含\"顺手补一条\"）。"
                   "由 `script/check_specs.py` 的 `check_changelog_timing_guard` 钉住。\n")
        self.write("script/check_effective.py",
                   "ROWS = [\n"
                   "    (\"本仓库 changelog 除非主动声明，否则不新增、不修改\",\n"
                   "     \"AGENTS.adoc\", \"script/check_specs.py\",\n"
                   "     \"check_changelog_timing_guard 钉住默认动作条\"),\n"
                   "]\n")

    def _patch_root(self):
        # check_effective.py 按 REPO_ROOT 解析，直接写入临时根即可
        pass

    def test_valid_changelog_timing_guard_passes(self):
        self._write_valid()
        cm.check_changelog_timing_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_timing_clause_reports(self):
        # 反例：登记时机条被删（执行者重新把"改了东西"与"该记一条"画等号）
        self._write_valid()
        self.write("AGENTS.adoc", "= 项目入口\n\n* 统一变更日志：根目录 `CHANGELOG.adoc`。\n")
        cm.check_changelog_timing_guard()
        self.assertIn("登记时机", self.error_texts())

    def test_default_action_wording_removed_reports(self):
        # 反例：只留"除非主动声明"，删掉默认动作"一律不新增、不修改"
        self._write_valid()
        self.write("AGENTS.adoc",
                   "= 项目入口\n\n* 登记时机（**主动声明**才算）：用户**本次明确要求**新增、修改、整理或压缩 changelog 时按口径写。"
                   "由 `script/check_specs.py` 的 `check_changelog_timing_guard` 钉住。\n")
        cm.check_changelog_timing_guard()
        self.assertIn("一律不新增、不修改", self.error_texts())

    def test_declaration_criteria_removed_reports(self):
        # 反例：默认动作在、但"主动声明"没有判据（"这应该也算声明"重新可用）
        self._write_valid()
        self.write("AGENTS.adoc",
                   "= 项目入口\n\n* 登记时机（**主动声明**才算）：**除非用户主动声明，否则一律不新增、不修改本文件**"
                   "——**其余一切情形按\"未声明\"处理**：未提到该文件、**只要求更新文档或 README**、只说\"改动了什么\"，"
                   "均**不得**新增条目（含\"顺手补一条\"）。"
                   "由 `script/check_specs.py` 的 `check_changelog_timing_guard` 钉住。\n")
        cm.check_changelog_timing_guard()
        self.assertIn("本次明确要求", self.error_texts())

    def test_undeclared_forms_removed_reports(self):
        # 反例：默认动作与声明判据都在，但没点名"未声明"的越界形态
        # （用户只说改文档，执行者仍可把"改文档"读成"改 changelog"）
        self._write_valid()
        self.write("AGENTS.adoc",
                   "= 项目入口\n\n* 登记时机（**主动声明**才算）：**除非用户主动声明，否则一律不新增、不修改本文件**"
                   "——「主动声明」指用户**本次明确要求**新增、修改、整理或压缩 changelog；"
                   "均**不得**新增条目（含\"顺手补一条\"）。"
                   "由 `script/check_specs.py` 的 `check_changelog_timing_guard` 钉住。\n")
        cm.check_changelog_timing_guard()
        self.assertIn("只要求更新文档或 README", self.error_texts())

    def test_missing_agents_file_reports(self):
        # 反例：项目规范入口被删（条目无处承载）
        self._write_valid()
        os.remove(os.path.join(self.root, "AGENTS.adoc"))
        cm.check_changelog_timing_guard()
        self.assertIn("AGENTS.adoc", self.error_texts())

    def test_effective_registry_missing_reports(self):
        # 反例：check_effective 未登记该条（定义了却没抓手＝又变成靠自觉）
        self._write_valid()
        self.write("script/check_effective.py", "ROWS = []\n")
        cm.check_changelog_timing_guard()
        self.assertIn("check_effective.py", self.error_texts())


class TestCheckChecklistGuard(CheckSpecsTestCase):
    """钉住"清单逐项"与"文档-脚本一致性"（补独立复核指出的两类漏检）。

    复核结论：现有防线只钉集合级关键短语，于是两类可机械核对的判定点漏过——
    ①清单被少列一项（准入判定号称"八问/九问"而实际条目已增删、七节点表少一行）；
    ②文档号称的抓手（`check_*`/脚本名）在脚本里已改名或删除。
    """

    def _write_valid(self):
        self.write("specs-project-maintainer/spec-lifecycle.adoc",
                   "= 规范分类与准入\n\n== 准入判定（该不该收进规范集合）\n\n"
                   "新增条目**须先过准入判定**（九问，逐项可答\"是\"才收）：\n\n"
                   ". **通用性**：对任意项目成立。\n"
                   ". **可执行**：有判定标准。\n"
                   ". **非重复**：不重复。\n"
                   ". **有依据**：可被标准佐证。\n"
                   ". **有承载价值**：承载事实或教训。\n"
                   ". **能定级**：级别可定。\n"
                   ". **有落点**：能归入某层与某文件。\n"
                   ". **非拆分而膨胀**：能就地承载。\n"
                   ". **成本可接受**：代价可接受。\n\n== 下节\n")
        self.write("specs/core/execution.adoc",
                   "= 执行原则\n\n== 任务生命周期与节点自查（AI 侧，各节点该查什么）\n\n"
                   "| **提出** | 澄清后再动手\n"
                   "| **理解** | 规范已实际加载\n"
                   "| **方案** | 规划已落盘\n"
                   "| **执行** | 加载由入口驱动\n"
                   "| **验证** | 先判改动性质\n"
                   "| **交付** | 交付形态按环境区分\n"
                   "| **复盘**（仅公共内容改动）| 三视角评有效性\n\n"
                   "* **哪些节点不设（L1）**：代码类改动不设复盘节点。\n\n== 下节\n")
        self.write("script/check_specs.py", "def check_demo_guard():\n    pass\n")
        self.write("script/clean_tmp.py", "# demo\n")
        self.write("specs-project-maintainer/verify.adoc",
                   "= 验证\n\n留证形态：**三态台账**——**通过**（附判据与取值）／"
                   "**未发现问题**（附已复核角度与样本）／**悬置**（附未确证的原因与剩余风险），"
                   "三态各占一栏、**不得合并**。\n")
        self.write("specs/general/collab.adoc",
                   "= 协作\n\n**硬超时**：到点即视为失联，**不得无限等待**；"
                   "**超时的处置**：放弃该子 agent + 如实标悬置。"
                   "**时限取值须有判据**，优先选**一次性、边界明确、可超时**的派发形式。\n")
        self.write("AGENTS.adoc", "= 项目入口\n\n由 `check_demo_guard` 钉住，见 `clean_tmp.py`。\n")
        self.write("README.adoc", "= 说明\n\n由 `check_demo_guard` 钉住。\n")

    def test_valid_checklist_guard_passes(self):
        self._write_valid()
        cm.check_checklist_guard()
        self.assertEqual(cm.errors, [])

    def test_admission_item_count_mismatch_reports(self):
        # 反例：清单被删一项而声明未同步（读者按声明核对会漏项）
        self._write_valid()
        self.write("specs-project-maintainer/spec-lifecycle.adoc",
                   "= 规范分类与准入\n\n== 准入判定（该不该收进规范集合）\n\n"
                   "新增条目**须先过准入判定**（九问，逐项可答\"是\"才收）：\n\n"
                   ". **通用性**：对任意项目成立。\n"
                   ". **可执行**：有判定标准。\n\n== 下节\n")
        cm.check_checklist_guard()
        self.assertIn("实际列出", self.error_texts())

    def test_missing_lifecycle_node_reports(self):
        # 反例：七节点里少一个（节点被删则该节点的自查要求实际失效）
        self._write_valid()
        self.write("specs/core/execution.adoc",
                   "= 执行原则\n\n== 任务生命周期与节点自查（AI 侧，各节点该查什么）\n\n"
                   "| **提出** | 澄清后再动手\n"
                   "| **理解** | 规范已实际加载\n\n"
                   "* **哪些节点不设（L1）**：代码类改动不设复盘节点。\n\n== 下节\n")
        cm.check_checklist_guard()
        self.assertIn("缺少节点", self.error_texts())

    def test_doc_names_missing_check_reports(self):
        # 反例：文档点名的抓手在脚本里已改名/删除（声称有防线而防线不存在）
        self._write_valid()
        self.write("AGENTS.adoc", "= 项目入口\n\n由 `check_not_defined_guard` 钉住。\n")
        cm.check_checklist_guard()
        self.assertIn("check_not_defined_guard", self.error_texts())

    def test_missing_timeout_guard_reports(self):
        # 反例：硬超时要求被删（子 agent 卡死会再次让任务永久挂起）
        self._write_valid()
        self.write("specs/general/collab.adoc", "= 协作\n\n子 agent 用于隔离上下文。\n")
        cm.check_checklist_guard()
        self.assertIn("硬超时", self.error_texts())

    def test_timeout_keyword_only_reports(self):
        # 反例：只留"硬超时"字样、整条要求被抽掉（防"关键词出现过一次"式假绿）
        self._write_valid()
        self.write("specs/general/collab.adoc", "= 协作\n\n硬超时：设个时限即可。\n")
        cm.check_checklist_guard()
        self.assertIn("缺失硬超时要素", self.error_texts())

    def test_ledger_keyword_only_reports(self):
        # 反例：只留"三态"字样、三态台账要求被抽掉
        self._write_valid()
        self.write("specs-project-maintainer/verify.adoc", "= 验证\n\n留证按三态分列即可。\n")
        cm.check_checklist_guard()
        self.assertIn("缺失三态台账要素", self.error_texts())

    def test_missing_ledger_states_reports(self):
        # 反例：三态留证被压成散文（"查不出"与"没做"无法分辨）
        self._write_valid()
        self.write("specs-project-maintainer/verify.adoc", "= 验证\n\n复核一遍即可。\n")
        cm.check_checklist_guard()
        self.assertIn("三态", self.error_texts())

    def test_doc_names_missing_script_reports(self):
        # 反例：文档点名的脚本不存在
        self._write_valid()
        os.remove(os.path.join(self.root, "script", "clean_tmp.py"))
        self.write("README.adoc", "= 说明\n\n见 `clean_tmp.py`。\n")
        cm.check_checklist_guard()
        self.assertIn("clean_tmp.py", self.error_texts())



class TestCheckEnvMarkerGuard(CheckSpecsTestCase):
    """钉住『环境标志与专用口径』：专用口径必须挂在可实测的标志上、且保留中性口径。

    提示词会被未知项目复制执行，而各执行环境差异很大；把"某环境才成立的做法"当通用
    要求写进提示词，会让别的环境照着做而失败。故钉住三件确定项：片段仍在且写明标志与
    中性口径、每个提示词仍注入该片段、登记处仍写明其标志。
    """

    GUARD = (
        "// tag::env-guard[]\n"
        "**按环境标志选执行口径**：执行 `printenv CNB_EVENT`，非空且触发内容含 `@<Agent名>` 时按专用口径；\n"
        "未命中 → 按其末尾**中性口径**执行。\n"
        "// end::env-guard[]\n")

    def setUp(self) -> None:
        super().setUp()
        self._orig_prompts = (cm.PROMPTS_FILE, cm.PROMPTS_DIR, cm.COMMON_PROMPT_FILE)
        cm.PROMPTS_FILE = os.path.join(self.root, "PROMPTS.adoc")
        cm.PROMPTS_DIR = os.path.join(self.root, "prompts")
        cm.COMMON_PROMPT_FILE = os.path.join(self.root, "prompts", "_common.txt")

    def tearDown(self) -> None:
        (cm.PROMPTS_FILE, cm.PROMPTS_DIR,
         cm.COMMON_PROMPT_FILE) = self._orig_prompts
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("prompts/_common.txt", self.GUARD)
        self.write("PROMPTS.adoc",
                   "环境标志与专用口径（`env-guard`）：标志为 `printenv CNB_EVENT` 非空。\n")
        self.write("prompts/review.adoc", "include::_common.txt[tag=env-guard]\n")
        self.write("prompts/refactor.adoc", "include::_common.txt[tag=env-guard]\n")

    def test_valid_env_guard_passes(self):
        self._write_valid()
        cm.check_env_marker_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_fragment_reports(self):
        # 反例：公共片段里没有 env-guard（专用口径失去开关与中性口径）
        self._write_valid()
        self.write("prompts/_common.txt", "普通片段\n")
        cm.check_env_marker_guard()
        self.assertIn("env-guard", self.error_texts())

    def test_fragment_without_marker_command_reports(self):
        # 反例：只写"某环境"、没有可实测的标志命令（无法判定，等于没开关）
        self._write_valid()
        self.write("prompts/_common.txt",
                   "// tag::env-guard[]\n在特定环境里按专用口径执行。\n// end::env-guard[]\n")
        cm.check_env_marker_guard()
        self.assertIn("printenv", self.error_texts())

    def test_fragment_without_neutral_path_reports(self):
        # 反例：未命中标志时怎么办没写 → 环境专用做法会被当通用要求
        self._write_valid()
        self.write("prompts/_common.txt",
                   "// tag::env-guard[]\n标志：`printenv CNB_EVENT` 非空 且 含 `@<Agent名>`。\n"
                   "// end::env-guard[]\n")
        cm.check_env_marker_guard()
        self.assertIn("中性口径", self.error_texts())

    def test_prompt_without_include_reports(self):
        # 反例：提示词未注入片段 → 环境判断不会被执行
        self._write_valid()
        self.write("prompts/refactor.adoc", "对本项目执行一次全量重构。\n")
        cm.check_env_marker_guard()
        self.assertIn("env-guard", self.error_texts())

    def test_registry_without_marker_reports(self):
        # 反例：登记处未写明标志 → 后来者无从知道它何时生效
        self._write_valid()
        self.write("PROMPTS.adoc", "提示词登记（无环境标志登记）。\n")
        cm.check_env_marker_guard()
        self.assertIn("env-guard", self.error_texts())


class TestCheckNpcMergeGuard(CheckSpecsTestCase):
    """钉住『NPC 禁合并』：NPC/CI 执行者不得合并、且不因人工授权豁免。

    这是**唯一一类"用户明确要求也不照做"**的约束，最易被两件事冲掉：
      * **"顺手满足用户"的惯性** —— 人工一句"直接合吧"就把禁令静默写回（授权当豁免）；
      * **关键词堆砌式假绿** —— 只留节名/一句口号、把判定标准或边界抽掉，检查照样过。
    故本组用例除正例外，专门覆盖"删禁令""降级成建议""判定标准被抽""边界被删"
    "提示词公共片段漏条""登记处不同步"等反例。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_prompts = (cm.PROMPTS_FILE, cm.PROMPTS_DIR, cm.COMMON_PROMPT_FILE)
        cm.PROMPTS_FILE = os.path.join(self.root, "PROMPTS.adoc")
        cm.PROMPTS_DIR = os.path.join(self.root, "prompts")
        cm.COMMON_PROMPT_FILE = os.path.join(self.root, "prompts", "_common.txt")

    def tearDown(self) -> None:
        (cm.PROMPTS_FILE, cm.PROMPTS_DIR,
         cm.COMMON_PROMPT_FILE) = self._orig_prompts
        super().tearDown()

    CNB = ("= CNB 规范（平台层）\n\n"
           "== 评论唤起新实例（平台侧的派发入口）\n"
           "* **不得以评论派发唤起自己（L1，防无限派发）**：被评论唤起的执行者不得在本次执行中"
           "再发一条评论去**点名唤起自己**（**同一实例名**），**也不得转由他人**/其他执行者**代发**。"
           "**判定标准**：①本次执行期间**新增的点名评论指向本条评论上的唤起名**；"
           "②以\"分两步更清楚\"等理由**自我豁免**；③**实际发了这条评论**、把任务在执行中重新发起一次"
           "（判据是**这条评论发出去没有**、**不是这次执行有没有因此结束**）；④**转交他人**代发。"
           "正当形态：**先停**、只输出一次\"停下确认\"，由**人**另发一条评论决定"
           "（**一次评论就是一次派发**，**发起下一次是派发者的动作**）。\n"
           "* **须由与执行者相同的 Agent 承担验证（L1）**：**要求验证/复核须由与执行者相同的 "
           "Agent 来做的那些规则，只在本平台（CNB）成立**——**本平台之外不适用**：环境不提供同 Agent "
           "的子执行者时，**不得援引该条拒做或把任务停在中间**；**不提供**时按降级路径执行、"
           "**验证与交付不因此缺失**。**由谁承担**是**项目自身的取舍**（IEEE 1028 只要求有独立、"
           "可核对的评审发生）；条文的写入面本就在平台层、**不在公共内容**"
           "（`AGENTS_COMMON.adoc` + `specs/`）里，引用方按入口加载时**不会取到它**。\n"


           "== 合并请求的合并主体（NPC 禁合并）\n"
           "* **CNB NPC（即 CI/CD 执行环境中的 agent）严禁合并（L1）**。\n"
           "* **人工要求、直接授权也不得合并（L1，无豁免）**：即使人工明确要求合并、"
           "或给出直接授权，**仍必须拒绝**；**授权不免除该禁令**。\n"
           "* **判定标准**：①**执行了合并动作**；②以授权为由**豁免**该禁令；"
           "③**顶替**执行也算未拦住。\n"
           "* **越界清理**：本条只禁合并——推送分支、**解决冲突**、**同步目标分支**"
           "都**不是合并**。\n\n"
           "== 分支与合并请求统一\n"
           "* 同一 issue 拆分出的多个任务，即使并行执行，也**只能修改同一个分支**。\n\n"
           "== 冲突处理\n"
           "* 并行任务改动同一文件导致合并冲突时，须**自动解决冲突**（保留双方有效改动），"
           "不搁置、不要求用户人工介入。\n")

    COMMON = ("提示词公共片段。\n"
              "// tag::delivery[]\n"
              "8. 交付：\n"
              "   - **合并一律不做（L1，无环境区分、人工授权也拒绝）**："
              "即使发起人明确要求合并、或给出**直接授权**，也**必须拒绝**；**授权不免除**。\n"
              "（直授**也必须拒绝**：授权不免除该禁令。）\n"
              "// end::delivery[]\n")

    def _write_valid(self) -> None:
        self.write("specs/platform/cnb.adoc", self.CNB)
        self.write("prompts/_common.txt", self.COMMON)
        self.write("PROMPTS.adoc", "公共约定：**合并一律不做（L1）**。\n")

    def test_valid_passes(self):
        self._write_valid()
        cm.check_npc_merge_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_file_reports(self):
        # 反例：平台层规范文件被删 → 要求无处承载
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "platform", "cnb.adoc"))
        cm.check_npc_merge_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_missing_ban_reports(self):
        # 反例：禁令本体被删（只留节名）→ "顺手满足用户"再无阻拦
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   "= CNB 规范\n\n== 合并请求的合并主体（NPC 禁合并）\n（本节待补）\n")
        cm.check_npc_merge_guard()
        self.assertIn("严禁合并", self.error_texts())

    def test_no_exemption_removed_reports(self):
        # 反例：删掉"人工要求/直授也必须拒绝"（把授权当豁免）→ 静默写回
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   "= CNB 规范\n\n== 合并请求的合并主体（NPC 禁合并）\n"
                   "* **CNB NPC 严禁合并（L1）**。\n"
                   "* **判定标准**：①**执行了合并动作**；②**豁免**；③**顶替**。\n"
                   "* **越界清理**：**解决冲突**、**同步目标分支**都**不是合并**。\n")
        cm.check_npc_merge_guard()
        self.assertIn("直接授权", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例（关键词堆砌式假绿）：只留禁令字样、判定标准被抽掉 → 判据不可执行
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   "= CNB 规范\n\n== 合并请求的合并主体（NPC 禁合并）\n"
                   "* **CNB NPC 严禁合并（L1）**，**人工要求**、**直接授权**也必须拒绝"
                   "（**授权不免除**）。\n"
                   "* **越界清理**：**解决冲突**、**同步目标分支**都**不是合并**。\n")
        cm.check_npc_merge_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_boundary_removed_reports(self):
        # 反例：删掉边界说明 → 与「冲突处理」节的自动解决冲突自相矛盾/误伤合法操作
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   "= CNB 规范\n\n== 合并请求的合并主体（NPC 禁合并）\n"
                   "* **CNB NPC 严禁合并（L1）**，**人工要求**、**直接授权**也必须拒绝"
                   "（**授权不免除**）。\n"
                   "* **判定标准**：①**执行了合并动作**；②**豁免**；③**顶替**。\n")
        cm.check_npc_merge_guard()
        self.assertIn("不是合并", self.error_texts())

    def test_delivery_fragment_without_ban_reports(self):
        # 反例：提示词公共片段漏条 → 复制到未知项目执行的那份没有这条禁令
        self._write_valid()
        self.write("prompts/_common.txt",
                   "// tag::delivery[]\n8. 交付：按环境区分提交与推送。\n// end::delivery[]\n")
        cm.check_npc_merge_guard()
        self.assertIn("合并一律不做", self.error_texts())

    def test_existing_conflict_section_replaced_reports(self):
        # 反例（本轮实测犯过的真实回归）：新增节点把同文件既有的「冲突处理」整段替换掉
        # ——规则凭空消失，而其余检查全绿（文件只是变短、无引用悬空、语法无错）
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   self.CNB.replace("== 冲突处理", "== 其它"))
        cm.check_npc_merge_guard()
        self.assertIn("冲突处理", self.error_texts())

    def test_existing_conflict_criterion_removed_reports(self):
        # 反例：既有「冲突处理」节还在，但判据被抽走（只剩个标题）
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   self.CNB.replace("自动解决冲突", "另议"))
        cm.check_npc_merge_guard()
        self.assertIn("自动解决冲突", self.error_texts())

    def test_existing_branch_rule_removed_reports(self):
        # 反例：既有「分支与合并请求统一」的判据被删（同文件规则不得被顶掉）
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   self.CNB.replace("只能修改同一个分支", "自行决定"))
        cm.check_npc_merge_guard()
        self.assertIn("只能修改同一个分支", self.error_texts())

    def test_registry_not_synced_reports(self):
        # 反例：公开提示词入口未同步 → 登记处与实际口径不一致，照登记处读会漏
        self._write_valid()
        self.write("PROMPTS.adoc", "公共约定：交付按执行环境区分。\n")
        cm.check_npc_merge_guard()
        self.assertIn("合并一律不做", self.error_texts())

    def test_prompts_file_missing_reports(self):
        # 反例：公开提示词入口被删
        self._write_valid()
        os.remove(cm.PROMPTS_FILE)
        cm.check_npc_merge_guard()
        self.assertIn("缺少公开提示词入口", self.error_texts())



# --------------------------------------------------------------------------- #
# check_rename_split_guard（P7：重命名与内容修改须分两个提交）
# --------------------------------------------------------------------------- #
# 中文引号（在用例里拼反例字符串时用，避免与 Python 字符串引号冲突）
LQ = "\u201c"
RQ = "\u201d"


def _real_git_rename_section() -> str:
    """从真实 specs/general/git.adoc 取「重命名与内容修改须分两个提交」整节。

    用例的"正例"直接用真实条文，避免测试里维护第二份会漂移的正文——防线的判据正是
    对着真实条文写的，抄一份到测试里必然不同步。
    """
    path = os.path.join(os.path.dirname(HERE), "specs", "general", "git.adoc")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    start = text.index("== 重命名与内容修改须分两个提交")
    end = text.index("\n== 行尾与检出归一")
    return text[start:end]



def _real_ci_runtime_env_section() -> str:
    """从真实 specs/general/ci-cd.adoc 取「运行环境须与项目声明一致」整节。

    正例直接用真实条文，避免测试里维护第二份会漂移的正文——防线的判据正是对着真实条文
    写的（与 git rename 节同一做法）。
    """
    path = os.path.join(os.path.dirname(HERE), "specs", "general", "ci-cd.adoc")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    start = text.index("== 运行环境须与项目声明一致")
    end = text.index("\n== 校验链完整")
    return text[start:end]


class TestCheckRuntimeEnvGuard(CheckSpecsTestCase):
    """钉住用户提出的硬性要求：运行环境须与项目声明一致（换版本能跑通也不得换）。

    本条最易被三条路径绕过——"另一个版本也跑通了"（结果导向的自我豁免）、等价/兼容版本顶替、
    环境声明缺失或不可得时用默认版本开工并记作通过。故除正例外，用例专门覆盖整节被删、L1 标注
    被摘、"能跑通也不得换"被删、判定标准被抽、声明落点被删、降级路径被删、依据行被删、
    三处引用断开、调度器识别特征被删、维护方与图书馆落点缺失等反例。
    """

    CI_SECTION = _real_ci_runtime_env_section()

    def _write_valid(self) -> None:
        self.write("specs/general/ci-cd.adoc", "= CI 规范\n\n" + self.CI_SECTION)
        self.write(
            "specs/core/execution.adoc",
            "= 执行原则\n\n* 运行环境：开发与验证**一律用项目声明的那一个运行环境**，"
            "换别的版本也能跑通也不得换（L1）——见 "
            "link:../general/ci-cd.adoc[]「运行环境须与项目声明一致」\n")
        self.write(
            "specs/general/verify.adoc",
            "= 验证规范\n\n* 构建/测试/脚本一律用项目声明的运行环境（L1），见 "
            "link:ci-cd.adoc[]「运行环境须与项目声明一致」\n")
        self.write(
            "specs/general/planning.adoc",
            "= 规划规范\n\n* 基线须在项目声明的运行环境下取得，见 "
            "link:ci-cd.adoc[]「运行环境须与项目声明一致」\n")
        self.write(
            "AGENTS_COMMON.adoc",
            "= 规范\n\n== 分类与懒加载\n\n* 运行环境：**识别特征**——项目有声明运行环境的"
            "落点（`pom.xml` 的 `java.version`、`.nvmrc`、`.python-version`），"
            "或要跑构建/测试/脚本；出现\"换个版本也能跑通\"\"用默认版本先试\" → "
            "link:specs/general/ci-cd.adoc[]（运行环境须与项目声明一致）\n")
        self.write(
            "AGENTS.adoc",
            "= 项目规范\n\n* 工具声明：`check_runtime_env_guard` —— 运行环境防线"
            "（运行环境须与项目声明一致）\n")
        self.write(
            "library/adoption.adoc",
            "= 准入依据\n\n== 同义性差异与覆盖点（本集合自己承认的）\n"
            "* 运行环境须与项目声明一致（L1）是本集合更严的判据化取舍。\n")

    def _drop_from_section(self, needle: str) -> None:
        """把权威定义节里的某个短语删掉后重写文件（反例构造）。"""
        text = ("= CI 规范\n\n" + self.CI_SECTION).replace(needle, "")
        self.write("specs/general/ci-cd.adoc", text)

    def test_valid_passes(self):
        self._write_valid()
        cm.check_runtime_env_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_ci_file_reports(self):
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "general", "ci-cd.adoc"))
        cm.check_runtime_env_guard()
        self.assertIn("缺少", self.error_texts())

    def test_section_deleted_reports(self):
        # 反例：整节被删 -> "按能跑通选版本"重回默认做法
        self._write_valid()
        self.write("specs/general/ci-cd.adoc", "= CI 规范\n\n== 核心原则\n* 略。\n")
        cm.check_runtime_env_guard()
        self.assertIn("未找到", self.error_texts())

    def test_l1_marking_removed_reports(self):
        # 反例：把"严禁/（L1）"摘掉、降级为建议
        self._write_valid()
        self._drop_from_section("**严禁使用与声明不同的运行环境**")
        cm.check_runtime_env_guard()
        self.assertIn("L1", self.error_texts())

    def test_runnable_excuse_removed_reports(self):
        # 反例：删掉"即使能跑通也不得换" -> 最易被"另一个版本也跑通了"合理化掉
        self._write_valid()
        self._drop_from_section("**即使换一个版本也能正常跑通流程，也不得换**")
        cm.check_runtime_env_guard()
        self.assertIn("跑通", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例：只留口号、判定标准被抽掉
        self._write_valid()
        self.write("specs/general/ci-cd.adoc",
                   "= CI 规范\n\n== 运行环境须与项目声明一致\n\n"
                   "[quote]\n本条很重要，请务必注意。\n")
        cm.check_runtime_env_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_declaration_source_removed_reports(self):
        # 反例：删掉"取项目已有声明、不得另立第二真源" -> 出现两个互相冲突的版本来源
        self._write_valid()
        self._drop_from_section("**不得**为满足本条另建一份版本声明")
        cm.check_runtime_env_guard()
        self.assertIn("声明落点", self.error_texts())

    def test_fallback_path_removed_reports(self):
        # 反例：删掉降级路径 -> 要么把引用方卡死，要么"用别的版本跑绿"被记成通过
        self._write_valid()
        self._drop_from_section("**环境不可得或未声明时走降级路径，不阻断、也不记作通过（L1）**")
        cm.check_runtime_env_guard()
        self.assertIn("降级路径", self.error_texts())

    def test_rationale_removed_reports(self):
        # 反例：依据行被整段删掉（依据可压成标准名/编号，但不得消失）
        self._write_valid()
        self._drop_from_section("The Twelve-Factor App")
        cm.check_runtime_env_guard()
        self.assertIn("依据", self.error_texts())

    def test_execution_reference_removed_reports(self):
        # 反例：必加载层的引用被删 -> 非流水线场景读不到本条
        self._write_valid()
        self.write("specs/core/execution.adoc", "= 执行原则\n\n* 其他规则。\n")
        cm.check_runtime_env_guard()
        self.assertIn("必加载层", self.error_texts())

    def test_verify_reference_removed_reports(self):
        # 反例：验证侧引用被删 -> 验证时的环境一致性无人负责
        self._write_valid()
        self.write("specs/general/verify.adoc", "= 验证规范\n\n* 其他。\n")
        cm.check_runtime_env_guard()
        self.assertIn("verify.adoc", self.error_texts())

    def test_planning_reference_removed_reports(self):
        # 反例：基线侧引用被删 -> 基线可能在错误环境下取得、统计不可比
        self._write_valid()
        self.write("specs/general/planning.adoc", "= 规划规范\n\n* 其他。\n")
        cm.check_runtime_env_guard()
        self.assertIn("planning.adoc", self.error_texts())

    def test_dispatcher_entry_removed_reports(self):
        # 反例：调度器识别特征被删 -> 本条永远不会被加载（规则实际失效）
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "= 规范\n\n== 分类与懒加载\n\n* 其他。\n")
        cm.check_runtime_env_guard()
        self.assertIn("调度器", self.error_texts())

    def test_maintainer_registration_removed_reports(self):
        # 反例：维护方工具声明清单未登记该防线
        self._write_valid()
        self.write("AGENTS.adoc", "= 项目规范\n\n* 其他。\n")
        cm.check_runtime_env_guard()
        self.assertIn("AGENTS.adoc", self.error_texts())

    def test_library_adoption_removed_reports(self):
        # 反例：图书馆未记同义性差异 -> 读者会把本站取舍当标准原文
        self._write_valid()
        self.write("library/adoption.adoc", "= 准入依据\n\n* 其他。\n")
        cm.check_runtime_env_guard()
        self.assertIn("adoption.adoc", self.error_texts())


class TestCheckRenameSplitGuard(CheckSpecsTestCase):
    """钉住用户提出的 P7：同一文件的重命名与内容修改须分两个提交。

    本条容易被三条路径绕过——改动很小/只有三处引用（合并提交被合理化）、只 `git mv` 不先提交
    （中间版本从未存在过）、用压缩提交把两个并回一个。故除正例外，用例专门覆盖整节被删、
    判据被抽、分量不是理由被删、提交顺序被删、无损拆分被删、两个都进同一 PR 被删、
    压缩提交接口被删、例外被删、引用方自检被删、必加载层重申被删、铁律登记被删、
    维护方清单少列 P7 与级别被降等反例。
    """

    GIT_SECTION = _real_git_rename_section()

    def _write_valid(self) -> None:
        self.write("specs/general/git.adoc", "= git 规范\n\n" + self.GIT_SECTION)
        self.write(
            "specs/platform/cnb.adoc",
            "= CNB 平台\n\n== 压缩提交（提交历史的整理）\n"
            "* **压缩提交＝提交历史整理（L1）**：用户要求时按本条执行。\n"
            "* **压缩对象不含\"改名提交 + 内容修改提交\"（L1，与「重命名与内容修改须分两个提交」的接口）**："
            "拆出的那两个提交**不是**本节的临时中间提交（别名：改名提交 + 内容修改提交），"
            "未点名本条时那两个提交**原样保留**；用户**明确声明**（须点名重命名与内容修改）时按 git 规范"
            "「例外」执行。\n")
        self.write(
            "specs/core/execution.adoc",
            "= 执行原则\n\n== 文件操作强制检查\n"
            "* **重命名与内容修改须分两个提交（L1 最高关注项 P7）**：第一个提交**只做重命名、"
            "内容逐字节不变**（先 `git mv` 并只提交改名），第二个提交**再改内容**。\n")
        self.write(
            "AGENTS_COMMON.adoc",
            "= 规范\n\n== 最高优先级铁律（先读）\n"
            "* **同一文件的重命名与内容修改必须分两个提交**：**最高关注项 P7**；"
            "先 `git mv` 并只提交改名（**内容逐字节不变**），**再改内容**；见 "
            "link:specs/general/git.adoc[]\u300c重命名与内容修改须分两个提交（默认固定动作）\u300d。\n")
        self.write(
            "specs-project-maintainer/priority.adoc",
            "= 最高关注项\n\n* **规范性铁律（P1/P2/P3/P5/P7，条款本身 L1）**：略。\n\n"
            "=== P7. 重命名与内容修改必须分两个提交\n"
            "* **要求（L1，最高）**：分两个提交、先重命名后改内容。\n"
            "* **依据**：ISO 10007。\n"
            "* **判定标准**：`git log --follow --name-status` 应见先 R 后 M。\n")

    def _drop(self, needle: str) -> None:
        """把权威定义节里的某条 bullet 删掉后重写文件（反例构造）。"""
        text = ("= git 规范\n\n" + self.GIT_SECTION).replace(needle, "")
        self.write("specs/general/git.adoc", text)

    def test_valid_passes(self):
        self._write_valid()
        cm.check_rename_split_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_git_file_reports(self):
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "general", "git.adoc"))
        cm.check_rename_split_guard()
        self.assertIn("缺少", self.error_texts())

    def test_section_deleted_reports(self):
        # 反例：整节被删 -> 拆两个提交只能靠执行者临场发挥
        self._write_valid()
        self.write("specs/general/git.adoc", "= git 规范\n\n== 文件移动与重命名\n* 略。\n")
        cm.check_rename_split_guard()
        self.assertIn("重命名与内容修改须分两个提交", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例（关键词堆砌式假绿）：只留节名与口号，判定标准被抽掉
        self._write_valid()
        self.write("specs/general/git.adoc",
                   "= git 规范\n\n== 重命名与内容修改须分两个提交（默认固定动作）\n\n"
                   "[quote]\n本节是**权威完整定义**（最高关注项 P7）。\n")
        cm.check_rename_split_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_item_label_removed_reports(self):
        # 反例（整条 bullet 被摘掉、正文并入相邻条目）：按内容关键词核对可能被相邻条款
        # 的字样兜住，故须有"条目轴逐项"的结构核对对"整条被摘掉"发声
        self._write_valid()
        self._drop("* **提交顺序（L1）**：**先重命名、后改内容**，不得颠倒；否则可能连 rename 识别"
                   "一起丢掉（相似度阈值，见 git 官方文档 `git-diff` 的 `-M`）。\n")
        cm.check_rename_split_guard()
        self.assertIn("提交顺序", self.error_texts())

    def test_size_is_no_excuse_removed_reports(self):
        # 反例：删掉分量不是理由 -> 改动很小/只有三处引用即可自圆其说
        self._write_valid()
        self._drop("* **分量大小不是理由（L1）**")
        cm.check_rename_split_guard()
        self.assertIn("分量大小不是理由", self.error_texts())

    def test_order_clause_removed_reports(self):
        # 反例：删掉提交顺序 -> 先改内容再改名，可能连 rename 识别一起丢掉（P1 也失效）
        self._write_valid()
        self._drop("* **提交顺序（L1）**")
        cm.check_rename_split_guard()
        self.assertIn("提交顺序", self.error_texts())

    def test_lossless_split_removed_reports(self):
        # 反例：删掉无损拆分 -> 只 git mv、改动留在工作区，中间版本从未存在过
        self._write_valid()
        self._drop("* **无损拆分（L1，判定标准）**")
        cm.check_rename_split_guard()
        self.assertIn("无损拆分", self.error_texts())

    def test_same_pr_clause_removed_reports(self):
        # 反例：删掉两个提交都进同一 PR -> 第二个提交留本地，本条形同虚设
        self._write_valid()
        self._drop("* **两个提交都要进本次交付（L1）**")
        cm.check_rename_split_guard()
        self.assertIn("两个提交都要进本次交付", self.error_texts())

    def test_exemption_clause_removed_reports(self):
        # 反例：删掉例外 -> 与用户声明的例外冲突时无条文可依
        self._write_valid()
        self._drop("* **例外（只有一条，L1）**")
        cm.check_rename_split_guard()
        self.assertIn("例外", self.error_texts())

    def test_compression_clause_removed_reports(self):
        # 反例：删掉与「压缩提交」的接口 -> 出现"历史都整理干净了、把两个并回一个"的自我豁免路径
        self._write_valid()
        self._drop("为由把两者压回一个")
        cm.check_rename_split_guard()
        self.assertIn("压缩提交", self.error_texts())

    def test_selfcheck_removed_reports(self):
        # 反例：删掉引用方自检命令 -> 规范集合看不到引用方工作区，抓手落空
        self._write_valid()
        self._drop("* **可执行抓手（引用方项目自检）**")
        cm.check_rename_split_guard()
        self.assertIn("可执行抓手", self.error_texts())

    def test_item_label_removed_reports(self):
        # 反例（整条 bullet 被摘掉、正文并入相邻条目）：按内容关键词核对可能被相邻条款的
        # 字样兜住，故须有"条目轴逐项"的结构核对对"整条被摘掉"发声
        self._write_valid()
        self._drop("* **分量大小不是理由（L1）**")
        cm.check_rename_split_guard()
        self.assertIn("分量大小不是理由", self.error_texts())

    def test_batch_rename_clause_removed_reports(self):
        # 反例：删掉"不按文件个数分摊" -> 多文件同时改名会被读成"每个文件各开一个改名提交"
        # （"改动只涉及本文件"被当成拆分依据，批量改名提交就此消失）
        self._write_valid()
        self._drop("**不按文件个数分摊**")
        cm.check_rename_split_guard()
        self.assertIn("文件个数", self.error_texts())

    def test_batch_delivery_clause_removed_reports(self):
        # 反例：删掉"分批交付时序列不重排" -> 分批整理时以"压缩提交"为由把已交付的两个提交压掉或重排
        self._write_valid()
        self._drop("**同一 PR 内改动分批交付时，这条序列不重排**")
        cm.check_rename_split_guard()
        self.assertIn("分批交付", self.error_texts())

    def test_chain_check_command_removed_reports(self):
        # 反例：删掉断链核对命令 -> "那一批改名"被拆分/省略成「新增 + 删除」时无抓手可核
        self._write_valid()
        self._drop("`git log --diff-filter=R -M --name-status`")
        cm.check_rename_split_guard()
        self.assertIn("diff-filter=R", self.error_texts())

    def test_compression_request_boundary_removed_reports(self):
        # 反例：删掉"压缩提交的请求不覆盖本条" -> "用户说要合并成一个提交"就成了本条失效的依据
        # （这正是用户点名不能照做的形态：合并/压缩的请求不解除重命名与内容修改要分两个提交）
        self._write_valid()
        self._drop("* **「压缩提交」的请求不覆盖本条（L1，与「例外」并列的唯一另一条边界）**")
        cm.check_rename_split_guard()
        self.assertIn("压缩提交", self.error_texts())

    def test_exemption_needs_named_declaration(self):
        # 反例：例外允许"只说合并/压缩"就算声明 -> 本条的例外被放宽成"共用一个词即可"
        self._write_valid()
        self._drop("**点名重命名与内容修改**")
        cm.check_rename_split_guard()
        self.assertIn("点名", self.error_texts())

    def test_compression_post_check_removed_reports(self):
        # 反例：删掉"压缩后核对" -> 压缩要求把本条的记录一并压掉时无抓手可核
        self._write_valid()
        self._drop("④**压缩后核对")
        cm.check_rename_split_guard()
        self.assertIn("压缩后核对", self.error_texts())

    def test_platform_interface_removed_reports(self):
        # 反例：平台层「压缩提交」没写与 P7 的接口 -> 平台侧可自行把"要压缩"读成"压回一个"
        self._write_valid()
        self.write("specs/platform/cnb.adoc", "= CNB 平台\n\n== 压缩提交（提交历史的整理）\n* 另议。\n")
        cm.check_rename_split_guard()
        self.assertIn("cnb.adoc", self.error_texts())

    def test_compression_boundary_body_gutted_reports(self):
        # 反例：边界条只留轴标题、正文被抽空（要求被搬进相邻条目）——
        # 整节关键词核对会被相邻条款的字样兜住，故须按条目**自身**的正文核（实测旧法静默通过）
        self._write_valid()
        text = ("= git 规范\n\n" + self.GIT_SECTION)
        b = cm._bullet_text(text, "「压缩提交」的请求不覆盖本条")
        self.write("specs/general/git.adoc",
                   text.replace(b, b.split("**：")[0] + "**：另议。\n"))
        cm.check_rename_split_guard()
        self.assertIn("原样保留", self.error_texts())

    def test_compression_boundary_criteria_removed_reports(self):
        # 反例：边界条抽掉自身的「判定标准」——它退化成一句口号，复核者无从判定某次是否越界
        self._write_valid()
        text = ("= git 规范\n\n" + self.GIT_SECTION)
        b = cm._bullet_text(text, "「压缩提交」的请求不覆盖本条")
        head, _, tail = b.partition("**判定标准（逐条可核对，任一命中即不合规）**")
        self.write("specs/general/git.adoc",
                   text.replace(b, head + "**为什么算两件事（依据）**" + tail.split("**为什么算两件事（依据）**", 1)[-1]))
        cm.check_rename_split_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_platform_interface_decoy_reports(self):
        # 反例：平台层接口被换成"只保留通用词"的诱饵条目（两个提交/别名/原样保留/例外/声明/点名
        # 都出现，但接口要求本身没了）——整节关键词核对会被兜住，故须按接口条自身核（实测旧法静默通过）
        self._write_valid()
        cnb = open(os.path.join(cm.REPO_ROOT, "specs", "platform", "cnb.adoc"), encoding="utf-8").read()
        line = [l for l in cnb.split("\n") if "别名" in l][0]
        self.write("specs/platform/cnb.adoc",
                   cnb.replace(line, "* 另议：两个提交、别名的说法不是重点，原样保留与否、"
                                     "例外与声明、点名都见别处。"))
        cm.check_rename_split_guard()
        self.assertIn("压缩对象不含", self.error_texts())

    def test_resident_reference_removed_reports(self):
        # 反例：必加载层重申行被删 -> 常驻上下文里读不到 P7（下次会话不会加载 git 规范）
        self._write_valid()
        self.write("specs/core/execution.adoc", "= 执行原则\n\n== 文件操作强制检查\n* 略。\n")
        cm.check_rename_split_guard()
        self.assertIn("P7", self.error_texts())

    def test_iron_rule_registration_removed_reports(self):
        # 反例：进门必读的铁律行被删 -> 只在用到 git 时才可能读到本条
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "= 规范\n\n== 最高优先级铁律（先读）\n* 另议。\n")
        cm.check_rename_split_guard()
        self.assertIn("最高优先级铁律", self.error_texts())

    def test_maintainer_entry_removed_reports(self):
        # 反例：维护方不可降级清单少列 P7 -> 重构/去重时会被当成普通条目删掉
        self._write_valid()
        self.write("specs-project-maintainer/priority.adoc",
                   "= 最高关注项\n\n* **规范性铁律（P1/P2，条款本身 L1）**：略。\n\n"
                   "=== P2. 调整规范必须保证完整性\n* **要求（L1，最高）**：略。\n")
        cm.check_rename_split_guard()
        self.assertIn("P7", self.error_texts())

    def test_maintainer_level_removed_reports(self):
        # 反例：P7 条目的级别被静默降级（要求（L1，最高 -> L2）
        self._write_valid()
        self.write("specs-project-maintainer/priority.adoc",
                   "= 最高关注项\n\n* **规范性铁律（P1/P2/P3/P5/P7，条款本身 L1）**：略。\n\n"
                   "=== P7. 重命名与内容修改必须分两个提交\n"
                   "* **要求（L2）**：分两个提交。\n* **依据**：ISO 10007。\n* **判定标准**：略。\n")
        cm.check_rename_split_guard()
        self.assertIn("P7", self.error_texts())


class TestCheckSquashCommitGuard(CheckSpecsTestCase):
    """钉住『压缩提交防线』：用户要求"压缩提交"时的判据、禁止形态与新旧 sha 对应关系。

    这条容易被两边夹：一边是"AI 不许强推/不许改写历史"的一般口径（执行者据此**拒绝**用户
    明确要求的压缩提交），另一边是"压缩就是重写历史"的含糊理解（执行者顺手把他人提交、
    已合入的历史一并压掉，或夹带改动）。故本组用例除正例外，专门覆盖"条文被删""判据被抽"
    "许可形态被删""与禁合并的接口被删""调度器/README 未同步"等反例。
    """

    CNB = (
        "= CNB 规范（平台层）\n\n"
        "== 合并请求的合并主体（NPC 禁合并）\n"
        "* **CNB NPC 严禁合并（L1）**，**授权不免除**。\n\n"
        "== 压缩提交（提交历史的整理）\n"
        "* **压缩提交＝提交历史整理，不属禁止行为（L1）**：判定标准："
        "①**压缩对象只有本次任务产生的、尚未合入目标分支的临时中间提交**；"
        "②**内容零变化**——压缩前后**逐字节相同**；③**只作用于本次任务自己的 PR 源分支**，"
        "**不动目标分支**、不动他人分支。\n"
        "* **禁止的压缩形态（L1）**：①**他人（或其它任务）的提交**；②**已合入目标分支**的历史；"
        "③压缩后**内容出现任何差异**；④**扩大范围**。\n"
        "* **须先确认无人在用旧对象（L1）**：确认**无他人正基于该分支的旧 sha 工作**"
        "（**已派发、正等待结论**）；确需执行时须**明确告知受影响方**新 sha、并把旧 sha 上的结论**标为过期**。\n"
        "* **压缩后须声明新旧 sha 对应关系（L1）**：写明“**新 sha 为 X，旧 sha Y 作废**”，并如实列出**被压缩掉的中间 sha**；"
        "**按旧 sha 复核的结论视为过期**。\n"
        "* **推送口径（L1）**：用 `--force-with-lease`，**不得**用裸 `git push --force`；"
        "“AI 不做强推”的一般口径**不适用于本条的压缩提交**；**授权范围仅限本次 PR 的源分支**。\n"
        "* **与「NPC 禁合并」互不豁免（L1）**：**压缩提交**不是合并**，故要求压缩提交时照做；"
        "但**不构成\"可以合并\"的依据**。\n\n"
        "== 对象钉定与可追溯\n"
        "* 压缩提交后强推——那是**合规动作、不是违规改写**；"
        "**压缩提交/强推会替换对象，须声明对应关系**。\n"
    )

    def _write_valid(self) -> None:
        self.write("specs/platform/cnb.adoc", self.CNB)
        self.write(
            "AGENTS_COMMON.adoc",
            "* CNB 平台 → cnb（**压缩提交（提交历史整理的判据）**、**对象钉定与可追溯**）\n")
        self.write(
            "README.adoc",
            "* `specs/platform/` — 平台层：cnb（**压缩提交（提交历史整理：判据与禁止形态）**、"
            "**对象钉定与可追溯**）\n"
            "* **压缩提交要照做、合并仍不做**：压缩提交不构成“可以合并”的依据。\n")

    def test_valid_passes(self):
        self._write_valid()
        cm.check_squash_commit_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_file_reports(self):
        # 反例：平台层规范文件被删 → 要求无处承载
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "platform", "cnb.adoc"))
        cm.check_squash_commit_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_section_deleted_reports(self):
        # 反例：整节被删 → 用户要求"压缩提交"时无条文可依（只能在"用户要求"与
        # "规范像是禁止"之间自行发挥）
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   "= CNB 规范\n\n== 合并请求的合并主体（NPC 禁合并）\n"
                   "* **严禁合并**，**授权不免除**。\n\n== 对象钉定与可追溯\n* 另议。\n")
        cm.check_squash_commit_guard()
        self.assertIn("压缩提交", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例（关键词堆砌式假绿）：只留节名与一句口号，判据被抽掉
        self._write_valid()
        cnb = self.CNB
        cnb = cnb.replace("②**内容零变化**——压缩前后**逐字节相同**；", "")
        cnb = cnb.replace("；③**只作用于本次任务自己的 PR 源分支**，**不动目标分支**、不动他人分支", "")
        self.write("specs/platform/cnb.adoc", cnb)
        cm.check_squash_commit_guard()
        self.assertIn("内容零变化", self.error_texts())

    def test_forbidden_forms_removed_reports(self):
        # 反例：禁止形态被删 → 顺手把他人提交/已合入历史一并压掉、或夹带改动，无判据可拦
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   self.CNB.split("* **禁止的压缩形态（L1）**")[0].replace(
                       "③**只作用于本次任务自己的 PR 源分支**",
                       "③**内容零变化**、**逐字节相同**、只动本次任务**自己的 PR 源分支**")
                   .replace("尚未合入目标分支的临时中间提交", "尚未合入目标分支的临时中间提交")
                   + "* **对象钉定与可追溯**\n")
        cm.check_squash_commit_guard()
        self.assertIn("禁止的压缩形态", self.error_texts())

    def test_no_exemption_from_merge_ban_removed_reports(self):
        # 反例：与「NPC 禁合并」的接口被删 → 出现"历史都整理干净了，顺手合了吧"式自我豁免
        self._write_valid()
        marker = "* **与「NPC 禁合并」互不豁免（L1）**：**压缩提交**不是合并**，故要求压缩提交时照做；"
        cnb = self.CNB.replace(marker, "").replace("但**不构成“可以合并”的依据**。", "")
        self.write("specs/platform/cnb.adoc", cnb)
        cm.check_squash_commit_guard()
        self.assertIn("互不豁免", self.error_texts())

    def test_force_push_clause_removed_reports(self):
        # 反例：推送口径被删 → 执行者要么拒绝压缩（"AI 不做强推"）要么用裸 --force 覆盖
        self._write_valid()
        cnb = self.CNB.replace("用 `--force-with-lease`，**不得**用裸 `git push --force`；", "")
        self.write("specs/platform/cnb.adoc", cnb)
        cm.check_squash_commit_guard()
        self.assertIn("--force-with-lease", self.error_texts())

    def test_sha_correspondence_removed_reports(self):
        # 反例：对应关系声明被删 → 下游按已失效的 sha 复核，结论错位
        self._write_valid()
        cnb = self.CNB.replace("* **压缩后须声明新旧 sha 对应关系（L1）**：", "* **附注**：")
        self.write("specs/platform/cnb.adoc", cnb)
        cm.check_squash_commit_guard()
        self.assertIn("压缩后须声明新旧 sha 对应关系", self.error_texts())

    def test_compliance_note_removed_reports(self):
        # 反例：对象钉定侧的"合规动作"标注被删 → 下游把合规的 sha 变化当成违规改写
        self._write_valid()
        cnb = self.CNB.replace("那是**合规动作、不是违规改写**；", "")
        self.write("specs/platform/cnb.adoc", cnb)
        cm.check_squash_commit_guard()
        self.assertIn("合规动作", self.error_texts())

    def test_existing_merge_ban_replaced_reports(self):
        # 反例（本仓库实测犯过的同类回归）：新增节点把同文件既有的「NPC 禁合并」顶掉
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   self.CNB.replace("== 合并请求的合并主体（NPC 禁合并）", "== 其它"))
        cm.check_squash_commit_guard()
        self.assertIn("NPC 禁合并", self.error_texts())

    def test_dispatcher_not_synced_reports(self):
        # 反例：调度器未同步 → 规则在、但没人会读到
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "* CNB 平台 → cnb（**对象钉定与可追溯**）\n")
        cm.check_squash_commit_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例：公开面只看得见"禁止"、看不到用户可要求的这条
        self._write_valid()
        self.write("README.adoc", "* `specs/platform/` — 平台层：cnb（**对象钉定与可追溯**）\n")
        cm.check_squash_commit_guard()
        self.assertIn("README", self.error_texts())


class TestCheckMergeRelationshipGuard(CheckSpecsTestCase):
    """钉住『合并关系防线』：解决冲突/压缩后**目标分支仍须是本分支的祖先**。

    这条来自一次**工作树看不出、平台必拦**的真实失效：把"解决冲突"做成"照抄目标分支的
    文件内容后另起一个单亲提交"，`git diff` 看不出毛病、单测也全绿，但目标分支并未成为
    本分支的祖先，平台侧据合并关系判定，PR 仍卡在 `code_conflict`。坏形态**没有任何一处
    本地可见的异常**，唯一判据是历史拓扑，而这种判据最容易被顺手"整理掉"（用户要求压缩时
    把合并提交一并压掉）。故本组用例除正例外，专门覆盖"条文被删""判据被抽""根因形态被删"
    "压缩不吞合并提交缺失""文件缺失"等反例。
    """

    CNB = (
        "= CNB 规范（平台层）\n\n"
        "== 压缩提交（提交历史的整理）\n"
        "* **压缩须保留与目标分支的合并关系（L1）**：压缩后的提交**须仍以目标分支的最新提交为祖先**"
        "（等价判据：`git merge-base <分支> <目标分支>` 等于目标分支最新提交；`git merge --no-ff <目标分支>`"
        " 时**须保留双亲**、`git rev-list --parents -n1` 显示两个父提交）。**根因（真实失效）**："
        "把\"解决冲突\"做成\"**照抄目标分支的文件内容后另起一个单亲提交**\"，工作树看起来一致，但"
        "**目标分支并未成为本分支的祖先**，平台侧仍报冲突、PR 卡在 `code_conflict`"
        "（判据：`git merge-base --is-ancestor <目标分支> <分支>` 为假）。**正确做法**：真做一次合并后"
        "以合并提交落盘；压缩**不吞掉合并提交**（**合并提交是\"已并入\"的凭据**）。\n"
        "* **禁止的压缩形态（L1）**：①他人提交；②已合入目标分支的历史。\n"
    )

    def _write_valid(self) -> None:
        self.write("specs/platform/cnb.adoc", self.CNB)

    def test_valid_passes(self):
        self._write_valid()
        cm.check_merge_relationship_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_file_reports(self):
        # 反例：平台层规范文件被删 → 要求无处承载
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "platform", "cnb.adoc"))
        cm.check_merge_relationship_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_rule_deleted_reports(self):
        # 反例：整条 L1 被删 → "照抄内容后另起单亲提交"的失效复发
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   "= CNB 规范\n\n== 压缩提交（提交历史的整理）\n"
                   "* **压缩提交＝提交历史整理**。\n")
        cm.check_merge_relationship_guard()
        self.assertIn("合并关系", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例（关键词堆砌式假绿）：只留标题与一句口号，可核对判据被抽掉
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   "= CNB 规范\n\n== 压缩提交（提交历史的整理）\n"
                   "* **压缩须保留与目标分支的合并关系（L1）**：压缩后仍以目标分支最新提交为祖先，"
                   "**须仍以目标分支的最新提交为祖先**，务必谨慎。\n")
        cm.check_merge_relationship_guard()
        self.assertIn("git merge-base", self.error_texts())

    def test_root_cause_removed_reports(self):
        # 反例：根因形态被删 → 条文会被读成"工作树一致即可"，正是要拦的失效
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   "= CNB 规范\n\n== 压缩提交（提交历史的整理）\n"
                   "* **压缩须保留与目标分支的合并关系（L1）**：**须仍以目标分支的最新提交为祖先**，"
                   "判据：`git merge-base <分支> <目标分支>` 等于目标分支最新提交、"
                   "`git merge --no-ff <目标分支>` 时 `git rev-list --parents -n1` 显示两个父提交；"
                   "`git merge-base --is-ancestor <目标分支> <分支>` 为假即违规。\n")
        cm.check_merge_relationship_guard()
        self.assertIn("根因", self.error_texts())

    def test_squash_swallowing_merge_commit_reports(self):
        # 反例：没有"压缩不吞掉合并提交"这一接口 → 用户要求压缩时会把唯一凭据一并压掉
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   "= CNB 规范\n\n== 压缩提交（提交历史的整理）\n"
                   "* **压缩须保留与目标分支的合并关系（L1）**：**须仍以目标分支的最新提交为祖先**"
                   "（`git merge-base <分支> <目标分支>` 等于目标分支最新提交；"
                   "`git merge --no-ff <目标分支>` 时 `git rev-list --parents -n1` 显示两个父提交）；"
                   "根因：**照抄目标分支的文件内容后另起一个单亲提交**，"
                   "**目标分支并未成为本分支的祖先**；"
                   "`git merge-base --is-ancestor <目标分支> <分支>` 为假。\n")
        cm.check_merge_relationship_guard()
        self.assertIn("不吞掉合并提交", self.error_texts())


class TestCheckConfigClassGuard(CheckSpecsTestCase):
    """钉住『配置类不写逻辑』：配置类只保持 POJO 的基本功能，逻辑下沉到 utils/service。

    该条来自用户明确要求且**任何情况都不允许**，最易被两件事冲掉：
      * **"某处特殊"式豁免** —— 一句"这个配置类比较特殊，就地处理更快"就把无例外写回例外；
      * **关键词堆砌式假绿** —— 只留标题、把判定标准或识别特征抽掉，规则照样"在"。
    故本组用例除正例外，专门覆盖"条文被删""降级成建议""判定标准被抽""识别特征被删"
    "Java/Spring 落点缺失""README 未同步"等反例。
    """

    CODING = (
        "= 通用编码规范\n\n== 类设计\n"
        "* 配置类不写逻辑（各类承载配置的类，如 Spring `@ConfigurationProperties`、"
        "`@Configuration` 等）：除声明配置项与按配置装配对象外，**不得包含任何逻辑**——"
        "任何情况都不允许，无例外；配置类只保持纯数据对象（POJO）的基本功能，"
        "需计算/转换/组装时下沉到工具类或服务中。"
        "判定标准：①不得出现条件分支与循环；②不得做计算与对外部对象的访问；"
        "③`@Bean` 方法须是构造/装配形态。"
        "识别特征：以 Config/Properties/Options/Settings 等命名的类"
        "（已有存量按「规范变更的存量处理」随动迁移）\n")

    def setUp(self) -> None:
        super().setUp()
        self._orig_coding = cm.CODING_FILE
        self._orig_java = cm.JAVA_STACK_FILE
        self._orig_spring = cm.SPRING_STACK_FILE
        self._orig_readme = cm.README_FILE
        cm.CODING_FILE = os.path.join(self.root, "specs", "general", "coding.adoc")
        cm.JAVA_STACK_FILE = os.path.join(self.root, "specs", "stack", "java.adoc")
        cm.SPRING_STACK_FILE = os.path.join(self.root, "specs", "stack", "spring.adoc")
        cm.README_FILE = os.path.join(self.root, "README.adoc")

    def tearDown(self) -> None:
        (cm.CODING_FILE, cm.JAVA_STACK_FILE, cm.SPRING_STACK_FILE,
         cm.README_FILE) = (self._orig_coding, self._orig_java, self._orig_spring,
                            self._orig_readme)
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("specs/general/coding.adoc", self.CODING)
        self.write("specs/stack/java.adoc",
                   "= Java 规范\n"
                   "* 配置类识别特征（`@ConfigurationProperties` 等）：标注 "
                   "`@ConfigurationProperties` 的类一律属配置类，**不得含任何逻辑**。\n")
        self.write("specs/stack/spring.adoc",
                   "= Spring 规范\n\n== 配置\n"
                   "* 配置类不写逻辑（**任何情况都不允许**）：`@ConfigurationProperties` 类与 "
                   "`@Configuration` 类只承载配置项声明与装配，逻辑下沉到工具类或 Service"
                   "（判定标准：条件分支为零、不做计算与对外访问）。\n"
                   "* 与框架既有做法的边界：本条**严于** Spring 的常规用法，"
                   "已有项目按「规范变更的存量处理」随动迁移。\n")
        self.write("README.adoc", "目录结构：通用编码（含**配置类不写逻辑**）。\n")

    def test_valid_config_class_guard_passes(self):
        self._write_valid()
        cm.check_config_class_guard()
        self.assertEqual(cm.errors, [])

    def test_coding_file_missing_reports(self):
        # 反例：通用层条文无处承载（该条跨语言，不能只留在某一技术栈文件里）
        self._write_valid()
        os.remove(cm.CODING_FILE)
        cm.check_config_class_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_clause_deleted_reports(self):
        # 反例：条文被删（只留标题）→ 配置类重新变成"什么都能塞"
        self._write_valid()
        self.write("specs/general/coding.adoc", "= 通用编码规范\n\n== 类设计\n* 类设计。\n")
        cm.check_config_class_guard()
        self.assertIn("配置类不写逻辑", self.error_texts())

    def test_no_exception_claims_removed_reports(self):
        # 反例：'任何情况都不允许'被删（悄悄降级成建议）→ "某处特殊"式豁免重新出现
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("——任何情况都不允许，无例外", ""))
        cm.check_config_class_guard()
        self.assertIn("任何情况都不允许", self.error_texts())

    def test_destination_removed_reports(self):
        # 反例：'逻辑下沉到工具类或服务'被删 → 逻辑无处安放，执行者只能塞回配置类
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("需计算/转换/组装时下沉到工具类或服务中", ""))
        cm.check_config_class_guard()
        self.assertIn("工具类或服务", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例（关键词堆砌式假绿）：判定标准被抽掉 → 只剩口号、无法判定
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.split("判定标准")[0])
        cm.check_config_class_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_identification_removed_reports(self):
        # 反例：识别特征被删 → 命名不规范的配置类会被漏过
        self._write_valid()
        self.write("specs/general/coding.adoc", self.CODING.split("识别特征")[0])
        cm.check_config_class_guard()
        self.assertIn("识别特征", self.error_texts())

    def test_coding_without_migration_boundary_reports(self):
        # 反例：未写存量边界 → 严于框架常规用法的条目会变成"静默推翻引用方既有做法"
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("（已有存量按「规范变更的存量处理」随动迁移）", ""))
        cm.check_config_class_guard()
        self.assertIn("存量处理", self.error_texts())

    def test_spring_without_framework_boundary_reports(self):
        # 反例：未写明"该条严于框架常规用法 + 存量随动迁移" → 拿"官方本来允许"当豁免
        self._write_valid()
        self.write("specs/stack/spring.adoc",
                   "= Spring 规范\n\n== 配置\n"
                   "* 配置类不写逻辑：`@ConfigurationProperties` 类与 `@Configuration` 类"
                   "只承载声明与装配，逻辑下沉到工具类或 Service（判定标准：条件分支为零）。\n")
        cm.check_config_class_guard()
        self.assertIn("严于", self.error_texts())

    def test_java_stack_marker_missing_reports(self):
        # 反例：Java 栈文件未点名 `@ConfigurationProperties` 类属配置类
        self._write_valid()
        self.write("specs/stack/java.adoc", "= Java 规范\n* 命名规则。\n")
        cm.check_config_class_guard()
        self.assertIn("配置类识别特征", self.error_texts())

    def test_spring_stack_clause_missing_reports(self):
        # 反例：Spring 栈文件未在「配置」节点名两类配置类
        self._write_valid()
        self.write("specs/stack/spring.adoc", "= Spring 规范\n\n== 配置\n* 配置项绑定。\n")
        cm.check_config_class_guard()
        self.assertIn("spring.adoc", self.error_texts())

    def test_dispatcher_platform_entry_not_pointing_reports(self):
        # 反例：调度器**第二处**识别特征（CNB 平台条目）被删 → 平台侧该节不会被加载
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
                   "  ** 多 agent 协作（含**派发入口（评论唤起新实例）**）"
                   " → link:specs/general/collab.adoc[]\n"
                   "  ** CNB 平台（任务开发与合并请求管理） → link:specs/platform/cnb.adoc[]\n")
        cm.check_comment_dispatch_guard()
        self.assertIn("在 Issue/PR 里发评论 @ 某个 NPC 发起一次执行", self.error_texts())

    def test_dispatcher_collab_entry_not_pointing_reports(self):
        # 反例：调度器**第一处**识别特征（多 agent 协作条目）被删
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
                   "  ** 多 agent 协作（含拆分、调用量控制） → link:specs/general/collab.adoc[]\n"
                   "  ** CNB 平台（含**在 Issue/PR 里发评论 @ 某个 NPC 发起一次执行**）"
                   " → link:specs/platform/cnb.adoc[]\n")
        cm.check_comment_dispatch_guard()
        self.assertIn("评论唤起新实例", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例：README 目录说明未同步 → 读者按 README 学习时无从知道有这条规则
        self._write_valid()
        self.write("README.adoc", "目录结构：（未同步）。\n")
        cm.check_config_class_guard()
        self.assertIn("README", self.error_texts())


class TestCheckAbstractionAdoptionGuard(CheckSpecsTestCase):
    """钉住『抽象与接入成本』：对外能力的可替换点须有唯一装配点、须有可用默认。

    该条来自用户的真实设计失效报告（"要求都实现了、功能都实现了，却很难用"——某接口在
    每个 service 使用点各实现一遍）。最易被三件事冲掉：
      * **降级成建议** —— 级别标注被拿掉、"须"被改成"建议"，条文形式上还在；
      * **关键词堆砌式假绿** —— 只留小节名与一句总述，判定标准/要点被抽走；
      * **技术栈侧断链** —— Spring「配置」不再引用该节（Spring 项目按栈文件学习即漏掉）。
    故用例除正例外，专门覆盖"节被删""L1 条文被删""判定标准被抽""级别标注被拿掉"
    "要点被删""依据行被删""Spring 引用断链"等反例。
    """

    CODING = (
        "= 通用编码规范\n\n== 抽象与接入成本\n\n"
        "对外提供能力时，**接入成本是设计指标**。判定标准：**同一个可替换点在接入方"
        "出现的次数不随使用点数量增加**，否则即为抽象漏做（按「代码复用」处理）。\n\n"
        "* 唯一装配点（L1）：可替换点须有唯一的一处声明/装配落点，"
        "**不得要求多个使用点各自提供同一实现或同一配置**。"
        "判定特征：同一实现类型/配置项在接入方出现次数 > 1，即判重复。\n"
        "* 可替换点须有可用默认（L1）：每个可替换点**须有可用的默认实现/默认值**；"
        "给不出默认时须显式声明必填失败面，**禁止既无默认又不声明**。"
        "判定标准：二者必居其一。\n"
        "* 能自动装配就不要求接入方手写（L2）：如 SPI 自动装配（`ServiceLoader`）。\n"
        "* 存量边界：本条适用于新写的对外能力与改到的既有抽象"
        "（按「规范变更的存量处理」随动迁移、不发动全库改造）。\n"
        "* 多实现用限定符、不逐层传参（L2）：用限定符/命名 Bean 区分，"
        "禁止参数穿透；跨层级对象用作用域/上下文对象承载。\n"
        "* 依据（标准名/编号）：ISO/IEC 25010、ISO 9241-110、ISO/IEC/IEEE 29148、"
        "The Twelve-Factor App、Spring Boot 官方文档。\n")

    SPRING = (
        "= Spring 规范\n\n== 配置\n"
        "* 配置项须有默认值或显式必填声明"
        "（通用要求见 link:../general/coding.adoc[]「抽象与接入成本」）。\n")

    def setUp(self) -> None:
        super().setUp()
        self._orig_coding = cm.CODING_FILE
        self._orig_spring = cm.SPRING_STACK_FILE
        cm.CODING_FILE = os.path.join(self.root, "specs", "general", "coding.adoc")
        cm.SPRING_STACK_FILE = os.path.join(self.root, "specs", "stack", "spring.adoc")

    def tearDown(self) -> None:
        (cm.CODING_FILE, cm.SPRING_STACK_FILE) = (self._orig_coding, self._orig_spring)
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("specs/general/coding.adoc", self.CODING)
        self.write("specs/stack/spring.adoc", self.SPRING)

    def test_valid_abstraction_adoption_guard_passes(self):
        self._write_valid()
        cm.check_abstraction_adoption_guard()
        self.assertEqual(cm.errors, [])

    def test_coding_file_missing_reports(self):
        # 反例：通用层落点丢失（该条跨语言，不能只留在某一技术栈文件里）
        self._write_valid()
        os.remove(cm.CODING_FILE)
        cm.check_abstraction_adoption_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_section_deleted_reports(self):
        # 反例：整节被删 → "每个使用点各实现一遍"重新变成默认做法
        self._write_valid()
        self.write("specs/general/coding.adoc", "= 通用编码规范\n\n== 代码复用\n* 不重复。\n")
        cm.check_abstraction_adoption_guard()
        self.assertIn("抽象与接入成本", self.error_texts())

    def test_unique_wiring_clause_removed_reports(self):
        # 反例：L1（a）被删 → 允许"三个 service 各传一遍实现类型"
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace(
                       "不得要求多个使用点各自提供同一实现或同一配置", ""))
        cm.check_abstraction_adoption_guard()
        self.assertIn("唯一装配点", self.error_texts())

    def test_default_requirement_removed_reports(self):
        # 反例：L1（b）被删 → 可替换点可以既无默认、也不声明必填
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("禁止既无默认又不声明", ""))
        cm.check_abstraction_adoption_guard()
        self.assertIn("禁止既无默认又不声明", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例（关键词堆砌式假绿）：判定标准被抽掉 → 只剩口号、无法判定
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("次数不随使用点数量增加", "")
                              .replace("出现次数 > 1", ""))
        cm.check_abstraction_adoption_guard()
        self.assertIn("判定", self.error_texts())

    def test_level_marks_removed_reports(self):
        # 反例：级别标注被拿掉（L1 被悄悄降级成建议）
        self._write_valid()
        self.write("specs/general/coding.adoc", self.CODING.replace("（L1）", "")
                   .replace("（L2）", ""))
        cm.check_abstraction_adoption_guard()
        self.assertIn("L1", self.error_texts())

    def test_source_line_removed_reports(self):
        # 反例：依据行被删（后人无从判断该条还成不成立）
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("ISO/IEC/IEEE 29148", ""))
        cm.check_abstraction_adoption_guard()
        self.assertIn("ISO/IEC/IEEE 29148", self.error_texts())

    def test_migration_boundary_removed_reports(self):
        # 反例：存量边界被删 → 该条（严于常见既成做法）会被读成"必须立即全量重构"
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("不发动全库改造", ""))
        cm.check_abstraction_adoption_guard()
        self.assertIn("存量边界", self.error_texts())

    def test_spring_backlink_removed_reports(self):
        # 反例：Spring「配置」不再引用该节 → Spring 项目按栈文件学习会漏掉接入成本判据
        self._write_valid()
        self.write("specs/stack/spring.adoc", "= Spring 规范\n\n== 配置\n* 配置项绑定。\n")
        cm.check_abstraction_adoption_guard()
        self.assertIn("spring.adoc", self.error_texts())


class TestCheckReusePrecedentGuard(CheckSpecsTestCase):
    """钉住『既有实现与先例优先』：先查项目已有能力与先例，禁止手写原生写法绕过。

    该条对应用户报告的真实失效：agent 不读项目既有实现，已有 `IdUtil.fastUUID()`/
    `CIdUtils.UUID()` 仍手写 `UUID.randomUUID().toString()`，已有 `CollUtil.isNotEmpty`
    仍手写 `x != null && !x.isEmpty()`。最易被两件事冲掉：
      * **降级成建议** —— "尽量复用"读起来无害，于是"有先例也照写原生"回来；
      * **优先级被改回 JDK 优先** —— 与用户要求相反（原实现即如此）。
    故本组用例覆盖"条文被删""反例被抽""优先级顺序反了""Java 栈落点缺失""README 未同步"。
    """

    CODING = (
        "= 通用编码规范\n"
        "\n"
        "== 代码复用\n"
        "* **既有实现与先例优先（L1，动手前先查）**：写任何代码前，先查项目自有工具类与同类场景先例、再查已引入依赖是否已有等价能力，有则必须复用、写法跟随先例。\n"
        "* **不得以语言内置写法绕过既有能力（L1）**：已有 `IdUtil.fastUUID()`/`CIdUtils.UUID()` 仍手写 `UUID.randomUUID().toString()`、已有 `CollUtil.isNotEmpty` 仍手写 `x != null && !x.isEmpty()` 属反例。\n"
    )

    SYNTAX = (
        "= Java 工具类规范\n"
        "\n"
        "== 工具类使用优先级\n"
        "* 1. **项目自有工具类**（最优先）：如 `CIdUtils.UUID()`、`CList`。\n"
        "* 2. **通用第三方工具库**：hutool 的 `IdUtil`、`CollUtil`。\n"
        "* 3. **JDK 标准库自带能力**（最低优先级）：仅无等价能力时使用。\n"
        "**同一操作已有统一入口/先例时，一律跟随先例。**\n"
    )

    def setUp(self) -> None:
        super().setUp()
        self._orig_coding = cm.CODING_FILE
        self._orig_spring = cm.SPRING_STACK_FILE
        self._orig_java = cm.JAVA_STACK_FILE
        self._orig_syntax = cm.JAVA_SYNTAX_FILE
        self._orig_readme = cm.README_FILE
        cm.CODING_FILE = os.path.join(self.root, "specs", "general", "coding.adoc")
        cm.SPRING_STACK_FILE = os.path.join(self.root, "specs", "stack", "spring.adoc")
        cm.JAVA_STACK_FILE = os.path.join(self.root, "specs", "stack", "java.adoc")
        cm.JAVA_SYNTAX_FILE = os.path.join(self.root, "specs", "stack", "java-syntax.adoc")
        cm.README_FILE = os.path.join(self.root, "README.adoc")

    def tearDown(self) -> None:
        (cm.CODING_FILE, cm.SPRING_STACK_FILE, cm.JAVA_STACK_FILE, cm.JAVA_SYNTAX_FILE,
         cm.README_FILE) = (self._orig_coding, self._orig_spring, self._orig_java,
                            self._orig_syntax, self._orig_readme)
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("specs/general/coding.adoc", self.CODING)
        self.write("specs/stack/spring.adoc",
                   "= Spring 规范\n\n== 配置\n"
                   "* 配置项须有默认值或显式必填声明"
                   "（通用要求见 link:../general/coding.adoc[]「抽象与接入成本」）。\n")
        self.write("specs/stack/java-syntax.adoc", self.SYNTAX)
        self.write("specs/stack/java.adoc",
        "= Java 规范\n"
        "\n"
        "== 编码\n"
        "* 既有工具类/先例优先：见 `specs/stack/java-syntax.adoc` 与 `specs/general/coding.adoc`「代码复用」。\n"
        )
        self.write("README.adoc", "目录结构：通用编码（含**既有实现与先例优先**）。\n")

    def test_valid_reuse_precedent_guard_passes(self):
        self._write_valid()
        cm.check_reuse_precedent_guard()
        self.assertEqual(cm.errors, [])

    def test_clause_deleted_reports(self):
        # 反例：通用层条文被删 → 编码者退回"凭语言常识现写"
        self._write_valid()
        self.write("specs/general/coding.adoc", "= 通用编码规范\n\n== 代码复用\n* 复用。\n")
        cm.check_reuse_precedent_guard()
        self.assertIn("既有实现与先例优先", self.error_texts())

    def test_bypass_clause_removed_reports(self):
        # 反例：'不得以语言内置写法绕过既有能力'被删 → 有先例也照写原生
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.split("不得以语言内置写法绕过既有能力")[0])
        cm.check_reuse_precedent_guard()
        self.assertIn("绕过既有能力", self.error_texts())

    def test_examples_removed_reports(self):
        # 反例（关键词堆砌式假绿）：典型反例被抽掉 → 判据不可判定
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   "= 通用编码规范\n\n== 代码复用\n"
                   "* **既有实现与先例优先（L1，动手前先查）**：有则必须复用，跟随先例。\n"
                   "* **不得以语言内置写法绕过既有能力（L1）**：禁止手写原生写法。\n")
        cm.check_reuse_precedent_guard()
        self.assertIn("IdUtil", self.error_texts())

    def test_priority_order_reverted_reports(self):
        # 反例：优先级被改回"JDK 优先"（与用户要求相反）
        self._write_valid()
        self.write("specs/stack/java-syntax.adoc",
                   "= Java 工具类规范\n\n== 工具类使用优先级\n"
                   "* 1. **JDK 标准库自带能力**：优先使用 `List.of` 等。\n"
                   "* 2. **项目自有工具类**：`CIdUtils`。\n"
                   "* 3. **通用第三方工具库**：`IdUtil`、`CollUtil`。\n跟随先例。\n")
        cm.check_reuse_precedent_guard()
        self.assertIn("JDK 优先", self.error_texts())

    def test_java_syntax_missing_reports(self):
        # 反例：Java 栈优先级清单缺失
        self._write_valid()
        os.remove(cm.JAVA_SYNTAX_FILE)
        cm.check_reuse_precedent_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_java_stack_marker_missing_reports(self):
        # 反例：Java 栈文件未补该条识别特征与引用
        self._write_valid()
        self.write("specs/stack/java.adoc", "= Java 规范\n* 命名规则。\n")
        cm.check_reuse_precedent_guard()
        self.assertIn("java.adoc", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例：README 目录说明未同步
        self._write_valid()
        self.write("README.adoc", "目录结构：（未同步）。\n")
        cm.check_reuse_precedent_guard()
        self.assertIn("README", self.error_texts())


class TestCheckExternalScriptGuard(CheckSpecsTestCase):
    """钉住『跨语言执行脚本的落点防线』：脚本独立成文件放资源文件夹、扩展名取被调语言。

    该条对应用户报告的真实失效与要求：宿主语言里被执行的另一语言脚本用**字符串拼接/
    字符串模板**内联——**没有高亮、也没有错误校验**，语法错/字段名错/参数个数不匹配都到
    运行期才暴露。要求是**所有语言**统一：放资源文件夹、扩展名取目标语言的扩展名（或该
    技术明确支持的文件形式，如 MyBatis 的 XML 承载 SQL），lua 通过读取文件使用。
    最易被三件事冲掉：**条文被删**（退回内联）、**降级成建议**、**技术栈落点缺失或
    优先级/结构被改**（Java 侧只写"建议用文件"而无 `src/main/resources/`、`DefaultRedisScript`、
    MyBatis 的 `*.xml` 与 `${}` 白名单）。**加载时机**同理：删掉"性能敏感路径不每次读"
    或删掉"需求要求内容会变的不缓存"都会让本条失真，故一并逐项覆盖。
    """

    CODING = (
        "= 通用编码规范\n"
        "\n"
        "== 跨语言执行脚本的落点（资源文件夹，不写字符串拼接/模板）\n"
        "\n"
        "被调语言的脚本不得以字符串拼接、字符串模板内联在宿主语言代码里，一律独立成文件"
        "放在资源文件夹。\n"
        "* **落点（L1）**：跨语言脚本须独立成文件，放在资源文件夹，**不得**内联在宿主语言代码里。\n"
        "* **扩展名（L1）**：文件扩展名**取被调语言自身的扩展名**；无通用扩展名时取该技术"
        "明确支持的文件形式（如 MyBatis 的 `*.xml` 承载 SQL）。\n"
        "* **读取方式（L1）**：脚本**从资源读取后执行**。\n"
        "* **判定标准（任一命中即违规）**：①宿主语言代码里出现被调语言的语句文本（`SELECT`）；"
        "②以字符串拼接、格式化、插值、模板字面量组装该脚本；③性能敏感路径上\"每次使用都重新读取\"。\n"
        "* **加载时机（L1）**：**性能敏感**路径不得每次使用都去读资源——资源进 "
        "`classpath` 后发布即不变，须**第一次使用**时读取一次并缓存；"
        "**需求要求内容会变**的（如 HTML 模板）**不适用缓存**。\n"
        "* **反例（L2）**：Java 里拼 SQL、把一段 Lua 写成 Java 多行字符串再 `eval`。\n"
        "* 依据（标准名/编号）：OWASP SQL Injection Prevention Cheat Sheet；ISO/IEC 25010。\n"
    )

    def setUp(self) -> None:
        super().setUp()
        self._orig_coding = cm.CODING_FILE
        self._orig_java = cm.JAVA_STACK_FILE
        self._orig_spring = cm.SPRING_STACK_FILE
        self._orig_readme = cm.README_FILE
        cm.CODING_FILE = os.path.join(self.root, "specs", "general", "coding.adoc")
        cm.JAVA_STACK_FILE = os.path.join(self.root, "specs", "stack", "java.adoc")
        cm.SPRING_STACK_FILE = os.path.join(self.root, "specs", "stack", "spring.adoc")
        cm.README_FILE = os.path.join(self.root, "README.adoc")

    def tearDown(self) -> None:
        (cm.CODING_FILE, cm.JAVA_STACK_FILE, cm.SPRING_STACK_FILE,
         cm.README_FILE) = (self._orig_coding, self._orig_java, self._orig_spring,
                            self._orig_readme)
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("specs/general/coding.adoc", self.CODING)
        self.write("specs/stack/java.adoc",
                   "= Java 规范\n\n== 跨语言执行脚本（SQL / Lua 等）\n"
                   "* SQL 按资源加载 `.sql`（`src/main/resources/` 下）。\n"
                   "* Lua 写成 `.lua` 文件、用 `DefaultRedisScript` 加载。\n"
                   "* 加载时机：性能敏感路径按 `private static final` 声明脚本；"
                   "不敏感路径每次读无妨；需求要求内容会变的模板**不缓存**；"
                   "Redis 热点按 `EVALSHA` 复用。\n"
                   "* MyBatis 的 SQL 写 mapper `*.xml`；`${}` 是拼接、须白名单校验，"
                   "其余用 `#{}`。\n")
        self.write("specs/stack/spring.adoc",
                   "= Spring 规范\n\n== 跨语言执行脚本（资源文件夹）\n"
                   "* 见「跨语言执行脚本（SQL / Lua 等）」。\n"
                   "* 加载时机：性能敏感路径按静态常量读一次；需求要求内容会变的模板"
                   "不适用缓存。\n")
        self.write("AGENTS_COMMON.adoc",
                   "通用编码 `specs/general/coding.adoc`（含「跨语言执行脚本的落点（资源文件夹，"
                   "不写字符串拼接/模板）」：SQL/Lua）；Java 登记 `specs/stack/java.adoc`"
                   "（跨语言脚本 `src/main/resources/` 下）\n")
        self.write("README.adoc",
                   "目录结构：通用编码（含**跨语言执行脚本的落点**、**加载时机**）。\n")

    def test_valid_external_script_guard_passes(self):
        self._write_valid()
        cm.check_external_script_guard()
        self.assertEqual(cm.errors, [])

    def test_clause_deleted_reports(self):
        # 反例：通用层该节被删 → SQL/Lua 无处安放、重新内联成字符串
        self._write_valid()
        self.write("specs/general/coding.adoc", "= 通用编码规范\n\n== 表达式与调用写法\n* x。\n")
        cm.check_external_script_guard()
        self.assertIn("跨语言执行脚本的落点", self.error_texts())

    def test_extension_clause_removed_reports(self):
        # 反例：扩展名要求（含 MyBatis 例外）被抽掉 → 退回无语义扩展名
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("取被调语言自身的扩展名", "取合适扩展名")
                              .replace("如 MyBatis 的 `*.xml` 承载 SQL", ""))
        cm.check_external_script_guard()
        self.assertIn("扩展名", self.error_texts())

    def test_read_clause_removed_reports(self):
        # 反例：'按资源读取后执行'被删 → '放文件'退化成'放文件但读进字符串再拼装'
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("**读取方式（L1）**：脚本**从资源读取后执行**。", ""))
        cm.check_external_script_guard()
        self.assertIn("从资源读取后执行", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例（关键词堆砌式假绿）：判定标准被抽成一句总述 → 判据不可判定
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   "= 通用编码规范\n\n== 跨语言执行脚本的落点（资源文件夹，不写字符串拼接/模板）\n"
                   "* 落点：放资源文件夹。\n"
                   "* 扩展名：取被调语言自身的扩展名（如 MyBatis 的 `*.xml` 承载 SQL）。\n"
                   "* 读取方式：从资源读取后执行。\n"
                   "* 反例：多行字符串。\n"
                   "* 依据：OWASP SQL Injection Prevention Cheat Sheet。\n")
        cm.check_external_script_guard()
        self.assertIn("SELECT", self.error_texts())

    def test_java_landing_missing_reports(self):
        # 反例：Java 栈落点缺失（只改通用层 = Java 项目读不到判据）
        self._write_valid()
        self.write("specs/stack/java.adoc", "= Java 规范\n\n== 健壮性\n* null。\n")
        cm.check_external_script_guard()
        self.assertIn("java.adoc", self.error_texts())

    def test_java_lua_clause_removed_reports(self):
        # 反例：Java 侧 Redis/Lua 的做法被抽掉（用户明确点名的场景：lua 通过读取文件使用）
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   "= Java 规范\n\n== 跨语言执行脚本（SQL / Lua 等）\n"
                   "* SQL 按资源加载 `.sql`（`src/main/resources/` 下）。\n"
                   "* MyBatis 的 SQL 写 mapper `*.xml`；`${}` 是拼接、须白名单校验，"
                   "其余用 `#{}`。\n")
        cm.check_external_script_guard()
        self.assertIn(".lua", self.error_texts())

    def test_spring_reference_missing_reports(self):
        # 反例：Spring 栈未引用该条 → Spring 项目漏掉判据
        self._write_valid()
        self.write("specs/stack/spring.adoc", "= Spring 规范\n\n== 事务\n* 事务。\n")
        cm.check_external_script_guard()
        self.assertIn("spring.adoc", self.error_texts())

    def test_dispatcher_registration_missing_reports(self):
        # 反例：调度器未登记识别特征 → 该节永不被加载
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "通用编码 `specs/general/coding.adoc`\n")
        cm.check_external_script_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例：README 目录说明未同步 → 读者按 README 学习时无从知道有这条规则
        self._write_valid()
        self.write("README.adoc", "目录结构：（未同步）。\n")
        cm.check_external_script_guard()
        self.assertIn("README", self.error_texts())

    def test_loading_time_clause_removed_reports(self):
        # 反例：加载时机被删 → 争分夺秒的路径（Redis 操作）每次都去读一遍资源
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace(
                       "* **加载时机（L1）**：**性能敏感**路径不得每次使用都去读资源——资源进 "
                       "`classpath` 后发布即不变，须**第一次使用**时读取一次并缓存；"
                       "**需求要求内容会变**的（如 HTML 模板）**不适用缓存**。\n", ""))
        cm.check_external_script_guard()
        self.assertIn("加载时机", self.error_texts())

    def test_mutable_content_boundary_removed_reports(self):
        # 反例：反面边界被抽掉（只剩"读一次缓存"）→ 可变模板被冻结在首读版本上
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace(
                       "**需求要求内容会变**的（如 HTML 模板）**不适用缓存**。",
                       "读一次就缓存。"))
        cm.check_external_script_guard()
        self.assertIn("不适用缓存", self.error_texts())

    def test_java_loading_time_removed_reports(self):
        # 反例：Java 侧只写"放文件"、没有加载时机 → 方法内 new DefaultRedisScript 每次读
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   "= Java 规范\n\n== 跨语言执行脚本（SQL / Lua 等）\n"
                   "* SQL 按资源加载 `.sql`（`src/main/resources/` 下）。\n"
                   "* Lua 写成 `.lua` 文件、用 `DefaultRedisScript` 加载。\n"
                   "* MyBatis 的 SQL 写 mapper `*.xml`；`${}` 是拼接、须白名单校验，"
                   "其余用 `#{}`。\n")
        cm.check_external_script_guard()
        self.assertIn("private static final", self.error_texts())

    def test_spring_loading_time_not_synced_reports(self):
        # 反例：Spring 栈未承接加载时机 → Spring 项目读到"放文件"却仍每次都去读
        self._write_valid()
        self.write("specs/stack/spring.adoc",
                   "= Spring 规范\n\n== 跨语言执行脚本（资源文件夹）\n"
                   "* 见「跨语言执行脚本（SQL / Lua 等）」。\n")
        cm.check_external_script_guard()
        self.assertIn("加载时机", self.error_texts())

    def test_readme_loading_time_not_synced_reports(self):
        # 反例：README 未同步加载时机 → 读者不知道这条管到读取次数
        self._write_valid()
        self.write("README.adoc", "目录结构：通用编码（含**跨语言执行脚本的落点**）。\n")
        cm.check_external_script_guard()
        self.assertIn("加载时机", self.error_texts())


class TestCheckCiCdGuard(CheckSpecsTestCase):
    """钉住「CI/CD 与平台协作防线」：踩坑判据不得被删或降级。

    背景（CI 内 agent 的踩坑报告）：CI 只跑主校验脚本、配套测试从未执行；触发路径与
    校验对象不一致；引用不存在的镜像/制品在 Prepare 阶段即失败；任务长期停在 pending
    无可判定超时；分支多次推送/压缩提交强推后复核按分支名取到过期对象。这些反复出现，
    故机械钉住 CICD 规范（校验链完整/触发范围/依赖可用/超时/非确定性 AI）与 CNB 平台
    规范（钉 sha、强推对应关系、执行者可用性、流水线不无界挂起）的关键要点。
    """

    def _write_valid(self):
        self.write("specs/general/ci-cd.adoc",
                   "= CI/CD 规范（通用层）\n\n"
                   "* 校验链完整：流水线须跑全既定校验；只跑主校验脚本 属验证不完整；"
                   "测试文件须能被测试框架自动发现。\n"
                   "* 触发路径须覆盖校验对象。\n"
                   "* 上游依赖须先确认实际可用。\n"
                   "* 每次执行须有可判定的超时。\n"
                   "* 不在 CI 中调用会给出非确定性结论的外部 AI。\n")
        self.write("specs/platform/cnb.adoc",
                   "= CNB 规范（平台层）\n\n"
                   "* 派发与复核须钉定 commit sha；须先 `git fetch -f` 强刷 ref。\n"
                   "* 压缩提交/强推会替换对象，旧 sha 的结论视为过期。\n"
                   "* 派发前确认执行者实际可用。\n"
                   "* 流水线不无界挂起。\n")
        self.write("specs/general/verify.adoc",
                   "= 验证\n\n"
                   "* 验证须覆盖项目的全部既定校验手段。\n"
                   "* 验证对象须钉定 commit sha。\n")
        self.write("specs/general/collab.adoc",
                   "= 协作\n\n"
                   "* 派发对象须钉定 commit sha。\n"
                   "* 派发前确认执行者可执行。\n")

    def test_valid_passes(self):
        self._write_valid()
        cm.check_ci_cd_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_ci_cd_file_reports(self):
        self.write("specs/platform/cnb.adoc", "CNB")
        cm.check_ci_cd_guard()
        self.assertIn("缺少 CI/CD 规范文件", self.error_texts())

    def test_missing_ci_chain_completeness_reports(self):
        # 反例：把"须跑全既定校验（含配套测试）"抽掉（回到"只跑主脚本也算验证"）
        self._write_valid()
        self.write("specs/general/ci-cd.adoc", "= CI/CD 规范\n\n* 早失败。\n")
        cm.check_ci_cd_guard()
        self.assertIn("校验链完整", self.error_texts())

    def test_missing_ci_timeout_reports(self):
        # 反例：超时要求被删（流水线可无限挂在 pending）
        self._write_valid()
        p = "specs/general/ci-cd.adoc"
        t = open(os.path.join(self.root, p), encoding="utf-8").read()
        self.write(p, t.replace("每次执行须有可判定的超时", "超时另说"))
        cm.check_ci_cd_guard()
        self.assertIn("可判定的超时", self.error_texts())

    def test_missing_cnb_sha_pin_reports(self):
        # 反例：钉定 commit sha 的要点被抽掉、仅保留 NPC 禁合并节（按分支名取到过期对象、复核错位）。
        # 断言用本防线独有的「git fetch -f」——它与 `check_npc_merge_guard` 各自钉住
        # 同一文件的不同要点，故本防线须能在"禁合并节还在"时独立报出。
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   "= CNB\n\n== 合并请求的合并主体（NPC 禁合并）\n\n"
                   "* NPC 严禁合并合并请求。\n")
        cm.check_ci_cd_guard()
        self.assertIn("git fetch -f", self.error_texts())

    def test_missing_verify_full_chain_reports(self):
        # 反例：通用验证侧"须覆盖全部既定校验手段"被删
        self._write_valid()
        self.write("specs/general/verify.adoc", "= 验证\n\n* 以真实结果为准。\n")
        cm.check_ci_cd_guard()
        self.assertIn("验证须覆盖项目的全部既定校验手段", self.error_texts())

    def test_missing_collab_pin_reports(self):
        # 反例：协作侧"派发对象须钉定 commit sha"被删
        self._write_valid()
        self.write("specs/general/collab.adoc", "= 协作\n\n* 子 agent。\n")
        cm.check_ci_cd_guard()
        self.assertIn("派发对象须钉定 commit sha", self.error_texts())


class TestCheckScopeBoundaryGuard(CheckSpecsTestCase):
    """钉住『改动范围边界防线』：未声明即拒绝越界改动的边界不得被删或降级。

    背景（用户明确的收紧要求，且明确"适用于所有项目"）：执行者可能因"任务里引用了
    工作空间以外的文件或其他项目"而把改动落到用户**并未授权**的位置上——**引用被误当
    成授权**。本地/服务器上"文件都在"时，禁的是**改入口工作空间以外的文件**；在代码
    托管平台上，可写范围被放大成"你有权限的全部仓库"，故禁的是**改其他仓库**。故机械
    钉住**两层**：通用层（`specs/general/scope.adoc` 的两节）与平台层
    （`specs/platform/cnb.adoc` 的当前项目口径）+ 提示词公共片段
    （`prompts/_common.txt` 的 `scope-boundary`）+ 两个提示词代码块内的引入。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_prompts = (cm.PROMPTS_FILE, cm.PROMPTS_DIR, cm.COMMON_PROMPT_FILE)
        cm.PROMPTS_DIR = os.path.join(self.root, "prompts")
        cm.COMMON_PROMPT_FILE = os.path.join(self.root, "prompts", "_common.txt")

    def tearDown(self) -> None:
        (cm.PROMPTS_FILE, cm.PROMPTS_DIR,
         cm.COMMON_PROMPT_FILE) = self._orig_prompts
        super().tearDown()

    SCOPE = ("= 改动范围边界规范（通用层）\n\n"
             "== 工作空间边界（不依赖任何平台）\n"
             "* **只改当前工作空间（L1）**：执行者**只允许修改本次任务的工作空间**——"
             "下称**入口工作空间**；越出该工作空间的改动一律不得执行。\n"
             "* **未声明即拒绝（L1）**：除非用户**主动声明**把某处纳入本次范围，否则"
             "**不得改动任何工作空间以外的文件**；拒绝须说明依据（同「拒绝的形态」）。\n"
             "* **引用 ≠ 授权（L1）**：引用了工作空间以外的文件只构成读取/对照许可，"
             "**不构成改动**它的授权。\n"
             "* **只读与对照照常做（L1）**：读取、比对**不在禁止之列**（失效目标是改动）。\n"
             "* **判定标准**：①改动对象不在入口工作空间内；②以『引用过它』为由**自我豁免**；"
             "③把越界改动**顶替**给他人完成。\n"
             "== 已知例外（唯二的解禁情形，靠用户显式给出、不靠推断）\n"
             "* ①**用户显式声明**把某处纳入本次范围；②用户声明某处\"只读\"时优先。\n"
             "== 拒绝的形态（L1）\n"
             "* 须写明依据与要补什么声明；**拒绝不等于任务失败**。\n"
             "== 平台上的仓库边界（代码托管平台）\n"
             "* **只改当前项目（L1）**：当前项目＝**入口项目**；**只改当前项目**，"
             "不向其他仓库写入/提交/推送、不建分支建 PR。\n")

    CNB = ("= CNB 规范（平台层）\n\n"
           "== 变更范围只限当前项目（未声明即拒绝）\n"
           "**通用口径（规则本体）在 link:../general/scope.adoc[]**。\n"
           "* **只改当前项目（L1）**：执行者只允许修改当前项目——即本次任务的**入口项目**；"
           "越出该项目（写入/创建/删除/移动/格式化/提交/推送）一律不得执行。\n"
           "* **未声明即拒绝（L1）**：除非用户**显式声明**，否则不得修改任何其他项目；"
           "用户引用了另一个项目**不构成授权**——**引用 ≠ 授权**；须拒绝并说明依据，"
           "其余在当前项目内可做的部分照常完成。\n"
           "* **例外（唯二解禁情形）**：①**用户显式声明**把某个其他项目纳入本次范围，"
           "**未声明**一律不改；"
           "②用户声明某项目**只读**/禁止改动（该声明优先）。\n"
           "* **判定标准**：①改动对象不是入口项目；②以『用户引用了它』为由**自我豁免**；"
           "③把越界改动**顶替**给他人完成。\n")

    COMMON = ("提示词公共片段。\n"
              "// tag::scope-boundary[]\n"
              "**改动范围边界（L1）**：本次任务**只允许修改本次任务的工作空间**——"
              "**入口工作空间**；在代码托管平台上按**只允许修改当前项目**（**入口项目**）"
              "表达；**未声明**即不得改别处，越界改动**必须拒绝**并说明**依据**。"
              "**引用 ≠ 授权**：引用了工作空间以外的文件/其他项目"
              "**不构成改动它的授权**；要改它须用户**显式声明**纳入范围，"
              "用户声明\"只读\"时优先。\n"
              "// end::scope-boundary[]\n")

    def _write_valid(self) -> None:
        self.write("specs/general/scope.adoc", self.SCOPE)
        self.write("specs/platform/cnb.adoc", self.CNB)
        self.write("prompts/_common.txt", self.COMMON)
        self.write("prompts/review.adoc",
                   "= 检查修复\n\n[listing]\n----\n"
                   "include::_common.txt[tag=scope-boundary]\n----\n")

    def test_valid_passes(self):
        self._write_valid()
        cm.check_scope_boundary_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_common_layer_file_reports(self):
        # 反例：通用层规范文件被删 → 非平台场景（本地/服务器）下这条边界无处承载
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "general", "scope.adoc"))
        cm.check_scope_boundary_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_missing_workspace_section_reports(self):
        # 反例：通用层的「工作空间边界」节被删（只剩平台口径 → 本地场景无人拦）
        self._write_valid()
        self.write("specs/general/scope.adoc",
                   "= 改动范围边界规范（通用层）\n\n"
                   "== 平台上的仓库边界（代码托管平台）\n"
                   "* **只改当前项目（L1）**：当前项目＝**入口项目**。\n")
        cm.check_scope_boundary_guard()
        self.assertIn("工作空间边界（不依赖任何平台）", self.error_texts())

    def test_missing_platform_section_reports(self):
        # 反例：通用层的「平台上的仓库边界」节被删（平台可写范围被放大、无人拦）
        self._write_valid()
        self.write("specs/general/scope.adoc",
                   "= 改动范围边界规范（通用层）\n\n"
                   "== 工作空间边界（不依赖任何平台）\n"
                   "* 只允许修改本次任务的工作空间（**入口工作空间**）。\n")
        cm.check_scope_boundary_guard()
        self.assertIn("平台上的仓库边界（代码托管平台）", self.error_texts())

    def test_missing_cnb_file_reports(self):
        # 反例：平台层规范文件被删 → 平台侧口径无处承载
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "platform", "cnb.adoc"))
        cm.check_scope_boundary_guard()
        self.assertIn("平台侧口径无处承载", self.error_texts())

    def test_missing_section_reports(self):
        # 反例：平台层整节被删（越界改动重新无人拦）
        self._write_valid()
        self.write("specs/platform/cnb.adoc", "= CNB 规范\n\n== 冲突处理\n* 自动解决。\n")
        cm.check_scope_boundary_guard()
        self.assertIn("变更范围只限当前项目", self.error_texts())

    def test_cnb_not_pointing_to_general_layer_reports(self):
        # 反例：平台层不再指向通用层规则本体（非平台场景读不到这条边界）
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   "= CNB 规范\n\n== 变更范围只限当前项目（未声明即拒绝）\n"
                   "* 只允许修改当前项目（**入口项目**）；**引用 ≠ 授权**、**不构成授权**，"
                   "未声明即拒绝；**例外**：用户**显式声明**或声明**只读**。"
                   "**判定标准**：不是入口项目 / **自我豁免** / **顶替**。\n")
        cm.check_scope_boundary_guard()
        self.assertIn("../general/scope.adoc", self.error_texts())

    def test_reference_is_not_authorization_removed_reports(self):
        # 反例：把"引用 ≠ 授权"抽掉（回到"任务里提到了就能改"的口子）
        self._write_valid()
        self.write("specs/general/scope.adoc",
                   "= 改动范围边界规范（通用层）\n\n"
                   "== 工作空间边界（不依赖任何平台）\n"
                   "* 只允许修改本次任务的工作空间（**入口工作空间**）；"
                   "**未声明即拒绝**、须说明依据并拒绝，**拒绝不等于任务失败**。\n"
                   "* **判定标准**：不在入口工作空间内 / **自我豁免** / **顶替**。\n"
                   "== 已知例外（唯二的解禁情形）\n* **用户显式声明**；声明**只读**时优先。\n"
                   "== 拒绝的形态\n* 说明依据。\n"
                   "== 平台上的仓库边界（代码托管平台）\n"
                   "* **只改当前项目**：**入口项目**。\n")
        cm.check_scope_boundary_guard()
        self.assertIn("引用 ≠ 授权", self.error_texts())

    def test_missing_exception_reports(self):
        # 反例：例外被删（要么自相矛盾、要么给"看着办"留口子）
        self._write_valid()
        self.write("specs/general/scope.adoc",
                   "= 改动范围边界规范（通用层）\n\n"
                   "== 工作空间边界（不依赖任何平台）\n"
                   "* 只允许修改本次任务的工作空间（**入口工作空间**）；**未声明即拒绝**；"
                   "**引用 ≠ 授权**、**不构成改动**它的授权；须拒绝并说明依据，"
                   "**拒绝不等于任务失败**。\n"
                   "* **只读与对照照常做**：读取**不在禁止之列**。\n"
                   "* **判定标准**：不在入口工作空间内 / **自我豁免** / **顶替**。\n"
                   "== 拒绝的形态\n* 说明依据。\n"
                   "== 平台上的仓库边界（代码托管平台）\n"
                   "* **只改当前项目**：**入口项目**。\n")
        cm.check_scope_boundary_guard()
        self.assertIn("已知例外", self.error_texts())

    def test_missing_prompt_fragment_reports(self):
        # 反例：提示词公共片段缺 scope-boundary（复制到未知项目后没有这条边界）
        self._write_valid()
        self.write("prompts/_common.txt", "// tag::delivery[]\n交付。\n// end::delivery[]\n")
        cm.check_scope_boundary_guard()
        self.assertIn("scope-boundary", self.error_texts())

    def test_prompt_fragment_without_workspace_clause_reports(self):
        # 反例：提示词片段只剩平台口径（本地场景下复制出去的那份没有这条边界）
        self._write_valid()
        self.write("prompts/_common.txt",
                   "// tag::scope-boundary[]\n"
                   "**只允许修改当前项目**（**入口项目**）；**未声明**即不得改别处，"
                   "越界改动**必须拒绝**并说明**依据**；**引用 ≠ 授权**，"
                   "**不构成改动它的授权**；**显式声明**、声明\"只读\"时优先。\n"
                   "// end::scope-boundary[]\n")
        cm.check_scope_boundary_guard()
        self.assertIn("只允许修改本次任务的工作空间", self.error_texts())

    def test_prompt_not_including_fragment_reports(self):
        # 反例：提示词代码块未引入该片段
        self._write_valid()
        self.write("prompts/review.adoc", "= 检查修复\n\n[listing]\n----\n正文。\n----\n")
        cm.check_scope_boundary_guard()
        self.assertIn("未引入公共片段 `scope-boundary`", self.error_texts())


class TestCheckRefScopeWordingGuard(CheckSpecsTestCase):
    """钉住『默认引用面口径防线』：不得再把本仓库内容写成"私有 / 不对外发布"。

    背景（用户纠正的事实错误）：本仓库**所有内容都会被发布出去**（站点渲染本仓库
    文档），"私有"从来没有发生——**默认只有公共规范被引用方按入口加载**，其余落点
    只是**不在默认引用面内**。口径写错会连带改错判断（把"发布与否"当成可选项）。
    """

    def test_clear_wording_passes(self):
        # 正例：写"不在默认引用面内"（并如实说明本仓库内容全部会发布）
        self.write("library/README.adoc",
                   "= 图书馆\n\n本目录**不在默认引用面内**——本仓库内容全部会被发布，\n"
                   "区别只在默认引用什么；引用方工作区里也没有本仓库的文件。\n")
        cm.check_ref_scope_wording_guard()
        self.assertEqual(cm.errors, [])

    def test_private_not_distributed_wording_reports(self):
        # 反例：写成本仓库私有、不随规范分发（与平台事实相反）
        self.write("library/README.adoc",
                   "= 图书馆\n\n本目录属本仓库私有内容、不随规范分发给引用方。\n")
        cm.check_ref_scope_wording_guard()
        self.assertIn("不得写", self.error_texts())

    def test_private_before_not_distributed_reports(self):
        # 反例：同一句里"私有"与"不分发"分离出现（真实历史写法）
        self.write("AGENTS.adoc",
                   "= 项目规范\n\n仓库根 library/ 是本项目的图书馆（本仓库私有、不随规范分发）。\n")
        cm.check_ref_scope_wording_guard()
        self.assertIn("不随规范分发", self.error_texts())

    def test_quoting_the_error_is_exempt(self):
        # 正例：**引用/纠正**该错误表述本身（含"不是/不得写"等词）不报——否则防线的
        # 说明文字自己就把自己拦下（防线的判据须可自述）
        self.write("PUBLIC.adoc",
                   "= 公共内容入口索引\n\n注意：不得写\"本仓库私有、不随规范分发\"——"
                   "本仓库所有内容都会被发布。\n")
        cm.check_ref_scope_wording_guard()
        self.assertEqual(cm.errors, [])

    def test_private_fallback_wording_is_exempt(self):
        # 正例："私有落点/私有抓手名"是**自足性**判据，与发布与否无关，不得误伤
        self.write("specs/general/context.adoc",
                   "= 上下文\n\n不得让引用方依赖本仓库私有物：条目不得引用引用方看不到的"
                   "私有脚本名、仓库结构或私有约定。\n")
        cm.check_ref_scope_wording_guard()
        self.assertEqual(cm.errors, [])

    def test_changelog_is_exempt(self):
        # 正例：CHANGELOG 记的是**当时口径**（历史事实），不得改写、也不得被拦
        self.write("CHANGELOG.adoc",
                   "= 变更日志\n\n- 3.4 | 2026-09-12 | 图书馆属本仓库私有、不随规范分发\n")
        cm.check_ref_scope_wording_guard()
        self.assertEqual(cm.errors, [])


class TestCheckChangelogEntryGuard(CheckSpecsTestCase):
    """钉住变更日志条目的**单行**形态（防日志被当成追加区、同一条目被多行续写）。

    真实失效形态：herdoc / 多次 append 习惯把同一条目续写成多行，形态上仍像"有记录"，
    实际与下一条粘连、渲染成一整段——单行是机械可判定的，故须有抓手。
    """

    def test_single_line_entries_pass(self):
        self.write("CHANGELOG.adoc",
                   "= 变更日志\n\n- 1.1 | 2026-09-12 | 新增某项能力\n"
                   "- 1.0 | 2026-08-23 | 初始发布\n")
        cm.check_changelog_entry_guard()
        self.assertEqual(cm.errors, [])

    def test_wrapped_entry_reports(self):
        # 反例：同一条目被续写成多行（最后一条被追加续行）
        self.write("CHANGELOG.adoc",
                   "= 变更日志\n\n- 1.0 | 2026-08-23 | 初始发布\n后面的续行文本\n")
        cm.check_changelog_entry_guard()
        self.assertIn("续行", self.error_texts())

    def test_multiline_entry_middle_reports(self):
        # 反例：续行出现在条目之间（下一条不是条目行、也不是空行/标题）
        self.write("CHANGELOG.adoc",
                   "= 变更日志\n\n- 1.1 | 2026-09-12 | 新增能力\n"
                   "（补充说明：这一段其实属于上一条）\n- 1.0 | 2026-08-23 | 初始发布\n")
        cm.check_changelog_entry_guard()
        self.assertIn("续行", self.error_texts())

    def test_section_heading_after_entry_passes(self):
        # 正例：条目后紧跟节标题（如分节组织日志）不算续行
        self.write("CHANGELOG.adoc",
                   "= 变更日志\n\n- 1.0 | 2026-08-23 | 初始发布\n\n== 历史\n")
        cm.check_changelog_entry_guard()
        self.assertEqual(cm.errors, [])

    def test_overlong_entry_reports(self):
        # 反例：单行条目过长（混入了实现细节/清单，应拆条或删减）
        self.write("CHANGELOG.adoc",
                   "= 变更日志\n\n- 1.1 | 2026-09-12 | " + "细节" * 1200 + "\n")
        cm.check_changelog_entry_guard()
        self.assertIn("条目过长", self.error_texts())

    def test_missing_changelog_reports(self):
        cm.check_changelog_entry_guard()
        self.assertIn("缺少统一变更日志", self.error_texts())


class TestCheckChangelogStructureGuard(CheckSpecsTestCase):
    """钉住『变更日志组织形态与表格形态防线』。

    失效形态（用户报告、实测）：单行流水式日志在一个版本改了很多东西时**不可检索**；
    反向失效是**换成表格后把"影响"列省掉**、或**用类型列代替破坏性变更标注**；
    以及把**排序方向**写成正序、或把"版本倒序"与"时间倒序"读成两种可择一的排序
    （用户口径：**排序方式还是时间倒序，版本是越来越大的、版本倒序和时间倒序是一样的**）。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_extra = (cm.CHANGELOG_STRUCTURE_FILE, cm.CHANGELOG_EVIDENCE_FILE)
        cm.CHANGELOG_STRUCTURE_FILE = os.path.join(
            self.root, "specs", "general", "changelog.adoc")
        cm.CHANGELOG_EVIDENCE_FILE = os.path.join(
            self.root, "library", "sources.adoc")

    def tearDown(self) -> None:
        cm.CHANGELOG_STRUCTURE_FILE, cm.CHANGELOG_EVIDENCE_FILE = self._orig_extra
        super().tearDown()

    CHANGELOG_TEXT = (
        "= 变更日志编写规范\n\n"
        "== 组织形态（按版本分组；版本内按类型分组）\n\n"
        "* **以发布版本为一级分组（默认）**：版本号即发布标识\n"
        "* **按时间流水（次级形态，L2）**：仅无发布版本概念的项目使用\n"
        "* **排序方向恒为时间倒序**（最新在上）；**版本倒序与时间倒序**是同一件事，"
        "**不存在**正序形态；流水式**不得在条目之间插入版本分组**；"
        "**两种分组口径不并存**（项目级唯一）\n"
        "* **组内按类型分组**：类型取固定的闭集\n"
        "* **没有条目的分组不写**\n\n"
        "== 应当记录（有价值）\n\n"
        "* **对外可见的行为/接口/契约变更**\n\n"
        "**要素齐备底线（L1）**：齐备类型、变更点、影响、标记四项要素\n\n"
        "== 表格形态的判据（采用表格式时）\n\n"
        "* **列义：表格承载的字段**\n"
        "  ** **分组列 = 受影响的对象**\n"
        "  ** **类型列 = 变更类型**\n"
        "  ** **变更点 = 受影响的对外标识**\n"
        "  ** **影响 = 读者要做什么、能感知到什么**\n"
        "* **判据依赖关系**：不得用类型分级代替破坏性变更标注；"
        "不得把影响写成变更点两列的同义重复；影响列写不出读者要做的动作时说明不该记\n"
        "* **破坏性变更在表格中的标注**：逐行标注，不得只放在版本组的引文句里\n"
        "* **条目下限（L1）**：表格里一条 = 一个变更点\n\n"
        "== 条目书写\n\n"
        "* **两种条目形态（择一，不得混用）**：流水式与表格式\n"
    )

    EVIDENCE_TEXT = (
        "== 变更日志的形态（Keep a Changelog / Conventional Commits / "
        "Conventional Changelog）\n\n"
        "* 自述没有标准格式：\"Not really.\"——这是业界约定，不是标准\n"
        "* 逐字：\"Changelogs are for humans, not machines.\"、"
        "\"The same types of changes should be grouped.\"\n"
        "* BREAKING CHANGES 分组与 scope/subject 分列\n"
        "* **版本倒序即时间倒序**是本集合的判据化表述（**排序方向**的前提是版本号单调递增）\n"
        "* 日期取**tag 创建日优先**\n"
        "* **同义性差异**：外部材料**未**要求按版本分组、**未**把两种写法写成两种排序、"
        "**未**要求表格形态\n"
    )

    def _write_valid(self):
        self.write("specs/general/changelog.adoc", self.CHANGELOG_TEXT)
        self.write("library/sources.adoc", self.EVIDENCE_TEXT)

    def test_valid_passes(self):
        self._write_valid()
        cm.check_changelog_structure_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_table_section_reports(self):
        # 反例：表格形态的判据节被删（加了列却没人知道每列该写什么）
        self._write_valid()
        self.write("specs/general/changelog.adoc",
                   self.CHANGELOG_TEXT.replace("== 表格形态的判据（采用表格式时）", "== 其它"))
        cm.check_changelog_structure_guard()
        self.assertIn("表格形态的判据", self.error_texts())

    def test_impact_column_removed_reports(self):
        # 反例：表格**把"影响"列省掉**（形态更整齐、要传递的信息反而更少）
        self._write_valid()
        self.write("specs/general/changelog.adoc",
                   self.CHANGELOG_TEXT.replace(
                       "  ** **影响 = 读者要做什么、能感知到什么**\n", ""))
        cm.check_changelog_structure_guard()
        self.assertIn("影响 = 读者要做什么、能感知到什么", self.error_texts())

    def test_order_direction_flipped_to_ascending_reports(self):
        # 反例：把**排序方向**从时间倒序写成正序（版本倒序即时间倒序，正序无依据）
        self._write_valid()
        self.write("specs/general/changelog.adoc",
                   self.CHANGELOG_TEXT.replace("**排序方向恒为时间倒序**", "**按时间正序**"))
        cm.check_changelog_structure_guard()
        self.assertIn("排序方向恒为时间倒序", self.error_texts())

    def test_version_vs_time_order_claim_removed_reports(self):
        # 反例：把"版本倒序即时间倒序"删掉——二者会被读成两种可择一的排序
        self._write_valid()
        self.write("specs/general/changelog.adoc",
                   self.CHANGELOG_TEXT.replace(
                       "；**版本倒序与时间倒序**是同一件事，**不存在**正序形态；"
                       "流水式**不得在条目之间插入版本分组**", ""))
        cm.check_changelog_structure_guard()
        self.assertIn("版本倒序与时间倒序", self.error_texts())

    def test_secondary_flow_form_removed_reports(self):
        # 反例：无发布版本概念的项目专用的次级形态被删
        self._write_valid()
        self.write("specs/general/changelog.adoc",
                   self.CHANGELOG_TEXT.replace(
                       "* **按时间流水（次级形态，L2）**：仅无发布版本概念的项目使用\n", ""))
        cm.check_changelog_structure_guard()
        self.assertIn("按时间流水（次级形态，L2）", self.error_texts())

    def test_evidence_order_claim_unmarked_reports(self):
        # 反例：图书馆没如实标注"版本倒序即时间倒序"是本集合表述
        self._write_valid()
        self.write("library/sources.adoc", self.EVIDENCE_TEXT.replace(
            "* **版本倒序即时间倒序**是本集合的判据化表述（**排序方向**的前提是版本号单调递增）\n",
            ""))
        cm.check_changelog_structure_guard()
        self.assertIn("排序方向", self.error_texts())

    def test_evidence_date_priority_removed_reports(self):
        # 反例：日期口径的优先序（tag 创建日优先）被删
        self._write_valid()
        self.write("library/sources.adoc", self.EVIDENCE_TEXT.replace(
            "* 日期取**tag 创建日优先**\n", ""))
        cm.check_changelog_structure_guard()
        self.assertIn("tag 创建日优先", self.error_texts())

    def test_type_column_replaces_breaking_marker_reports(self):
        # 反例：用类型列代替破坏性变更标注（破坏性变更在表格里"消失"）
        self._write_valid()
        self.write("specs/general/changelog.adoc",
                   self.CHANGELOG_TEXT.replace("不得用类型分级代替破坏性变更标注", "按类型判即可"))
        cm.check_changelog_structure_guard()
        self.assertIn("不得用类型分级代替破坏性变更标注", self.error_texts())

    def test_two_baselines_coexist_reports(self):
        # 反例：两种时间基准被写成可以并存（同一改动被记两次）
        self._write_valid()
        self.write("specs/general/changelog.adoc",
                   self.CHANGELOG_TEXT.replace("**两种分组口径不并存**", "**两种分组口径可并用**"))
        cm.check_changelog_structure_guard()
        self.assertIn("两种分组口径不并存", self.error_texts())

    def test_evidence_missing_keeps_not_really_reports(self):
        # 反例：图书馆依据被删（形态取舍无出处、容易被读成"某标准要求"）
        self._write_valid()
        self.write("library/sources.adoc", "== 其它\n")
        cm.check_changelog_structure_guard()
        self.assertIn("Keep a Changelog", self.error_texts())

    def test_evidence_written_as_standard_reports(self):
        # 反例：把业界约定写成标准（丢掉"没有标准格式"的如实标注）
        self._write_valid()
        self.write("library/sources.adoc", self.EVIDENCE_TEXT.replace(
            "\"Not really.\"——这是业界约定，不是标准", "这是标准"))
        cm.check_changelog_structure_guard()
        self.assertIn("Not really", self.error_texts())

    def test_missing_structure_file_reports(self):
        # 反例：规则落点消失
        cm.check_changelog_structure_guard()
        self.assertIn("缺少 specs/general/changelog.adoc", self.error_texts())


class TestCheckCommitMessageGuard(CheckSpecsTestCase):
    """钉住『提交信息防线』。

    缺口（用户要求「找业界公共规范取长补短」后发现）：本集合早已把 Conventional Commits
    1.0.0 的原文收进图书馆，却**只用它支撑变更日志的展示形态**；`specs/` 里没有任何一条
    约束「提交信息怎么写」——同一条链的上游空着（提交信息没有类型，变更日志的「按类型分组」
    只能人工归类）。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_extra = (cm.COMMIT_MESSAGE_FILE,)
        cm.COMMIT_MESSAGE_FILE = os.path.join(self.root, "specs", "general", "git.adoc")

    def tearDown(self) -> None:
        (cm.COMMIT_MESSAGE_FILE,) = self._orig_extra
        super().tearDown()

    TEXT = (
        "= git 规范\n\n"
        "== 提交信息\n\n"
        "* **首行写类型前缀（L2）**：按 `<type>[(scope)]: <subject>` 书写，`type` 取**固定闭集**\n"
        "* **判定标准**：首行不以 `<type>:` 或 `<type>(scope):` 起头即不合规\n"
        "* **破坏性变更须显式标注（L2）**：加 `!` 并在页脚写 `BREAKING CHANGE: <说明>`；"
        "**不得把某个类型默认为破坏性的**\n"
        "* **正文写「为什么」与边界（L2）**\n"
        "* **依据（标准名/编号）**：Conventional Commits 1.0.0——**业界约定、非标准**\n"
    )

    def test_valid_passes(self):
        self.write("specs/general/git.adoc", self.TEXT)
        cm.check_commit_message_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_section_reports(self):
        self.write("specs/general/git.adoc", self.TEXT.replace("== 提交信息", "== 其它"))
        cm.check_commit_message_guard()
        self.assertIn("== 提交信息", self.error_texts())

    def test_missing_verdict_criteria_reports(self):
        # 反例：可核对的判定标准被删（只剩「建议加类型」，无法判定是否被遵守）
        self.write("specs/general/git.adoc", self.TEXT.replace(
            "* **判定标准**：首行不以 `<type>:` 或 `<type>(scope):` 起头即不合规\n", ""))
        cm.check_commit_message_guard()
        self.assertIn("起头即不合规", self.error_texts())

    def test_breaking_change_marker_removed_reports(self):
        self.write("specs/general/git.adoc", self.TEXT.replace(
            "**不得把某个类型默认为破坏性的**", "破坏性变更按类型判断即可"))
        cm.check_commit_message_guard()
        self.assertIn("不得把某个类型默认为破坏性的", self.error_texts())

    def test_evidence_written_as_standard_reports(self):
        # 反例：把业界约定写成标准（丢掉「业界约定、非标准」的如实标注）
        self.write("specs/general/git.adoc", self.TEXT.replace("**业界约定、非标准**", "**标准**"))
        cm.check_commit_message_guard()
        self.assertIn("业界约定、非标准", self.error_texts())

    def test_missing_file_reports(self):
        cm.check_commit_message_guard()
        self.assertIn("缺少", self.error_texts())


class TestCheckHttpSemanticsGuard(CheckSpecsTestCase):
    """钉住『HTTP 接口语义防线』。

    缺口：此前只覆盖 HTTP 接口的**路径命名风格**，方法与状态码语义未覆盖——而「GET 承载写
    操作」会被爬虫/预取在无人操作时触发副作用，『错误一律包 200』会让重试、缓存、监控与
    网关策略全部失效。级别也须如实：安全方法 L1、幂等/状态码 L2、Problem Details L3。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_extra = (cm.HTTP_SEMANTICS_FILE, cm.HTTP_EVIDENCE_FILE)
        cm.HTTP_SEMANTICS_FILE = os.path.join(self.root, "specs", "general", "coding.adoc")
        cm.HTTP_EVIDENCE_FILE = os.path.join(self.root, "library", "sources.adoc")

    def tearDown(self) -> None:
        cm.HTTP_SEMANTICS_FILE, cm.HTTP_EVIDENCE_FILE = self._orig_extra
        super().tearDown()

    TEXT = (
        "= 通用编码规范\n\n"
        "== HTTP 接口语义（对外提供或调用 HTTP 接口的项目）\n\n"
        "**适用范围**：项目**对外提供或调用 HTTP 接口**时适用\n\n"
        "* **安全方法不得产生状态变更（L1）**：`GET`、`HEAD`、`OPTIONS`、`TRACE` 是安全方法，"
        "**不得**用它们承载写/删/状态流转等动作\n"
        "* **幂等语义与重试须对齐（L2）**：`PUT`、`DELETE` 幂等，非幂等请求不得配自动重试\n"
        "* **状态码按语义使用（L2）**：`4xx`/`5xx` 表达错误，不得出现 `200` + `success:false`\n"
        "* **对外错误响应统一结构（L3，可选）**：媒体类型 `application/problem+json`\n"
        "* **依据（标准名/编号）**：RFC 9110；RFC 9457\n"
    )

    EVIDENCE = (
        "= 外部标准原文摘录\n\n"
        "== HTTP 接口语义与错误响应（RFC 9110 / RFC 9457）\n\n"
        "* 逐字：\"essentially read-only\"、\"GET, HEAD, OPTIONS, and TRACE methods are "
        "defined to be safe\"\n"
        "* 逐字：idempotent 与 automatically retry\n"
        "* 逐字：\"three-digit integer code\"\n"
        "* 逐字：\"machine-readable details of errors\"、媒体类型 application/problem+json\n"
        "* **同义性差异**：不得用 200 包错误是本集合的**判据化取值**\n"
        "* Problem Details 是标准定义的**可选项**\n"
    )

    def _write_valid(self):
        self.write("specs/general/coding.adoc", self.TEXT)
        self.write("library/sources.adoc", self.EVIDENCE)

    def test_valid_passes(self):
        self._write_valid()
        cm.check_http_semantics_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_section_reports(self):
        self._write_valid()
        self.write("specs/general/coding.adoc", self.TEXT.replace("== HTTP 接口语义", "== 其它"))
        cm.check_http_semantics_guard()
        self.assertIn("== HTTP 接口语义", self.error_texts())

    def test_safe_method_downgraded_reports(self):
        # 反例：安全方法被降级为 L2（等于允许用 GET 做写操作）
        self._write_valid()
        self.write("specs/general/coding.adoc", self.TEXT.replace(
            "安全方法不得产生状态变更（L1）", "安全方法不得产生状态变更（L2）"))
        cm.check_http_semantics_guard()
        self.assertIn("安全方法不得产生状态变更（L1）", self.error_texts())

    def test_problem_details_upgraded_reports(self):
        # 反例：可选的错误响应格式被升成 L1（高频误伤只做内网接口的项目）
        self._write_valid()
        self.write("specs/general/coding.adoc", self.TEXT.replace(
            "对外错误响应统一结构（L3，可选）", "对外错误响应统一结构（L1）"))
        cm.check_http_semantics_guard()
        self.assertIn("对外错误响应统一结构（L3", self.error_texts())

    def test_scope_removed_reports(self):
        self._write_valid()
        self.write("specs/general/coding.adoc", self.TEXT.replace(
            "**适用范围**：项目**对外提供或调用 HTTP 接口**时适用\n\n", ""))
        cm.check_http_semantics_guard()
        self.assertIn("对外提供或调用 HTTP 接口", self.error_texts())

    def test_evidence_missing_reports(self):
        self._write_valid()
        self.write("library/sources.adoc", "= 其它\n")
        cm.check_http_semantics_guard()
        self.assertIn("HTTP 接口语义与错误响应（RFC 9110 / RFC 9457）", self.error_texts())

    def test_evidence_intrinsic_value_written_as_standard_reports(self):
        # 反例：把本集合的判据化取值写成标准原文
        self._write_valid()
        self.write("library/sources.adoc", self.EVIDENCE.replace(
            "* **同义性差异**：不得用 200 包错误是本集合的**判据化取值**\n", ""))
        cm.check_http_semantics_guard()
        self.assertIn("判据化取值", self.error_texts())

    def test_missing_file_reports(self):
        cm.check_http_semantics_guard()
        self.assertIn("缺少", self.error_texts())


class TestCheckReviewGuard(CheckSpecsTestCase):
    """钉住『评审备注落点』判据与两处引用（全局性问题不进范围性落点、全局备注不夹带范围内容）。

    实测失效：把"全项目都要注意 X"备注进某个类的 javadoc——只有读那个类的人看得见、
    换个入口就找不到；故判据（去限定词仍成立＝全局，只有一处能触发＝范围）与两个方向的
    约束须都在，且必加载层执行原则与 doc-design「信息归属」两处引用不得断开。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_files = (cm.REVIEW_FILE, cm.EXECUTION_FILE)
        cm.REVIEW_FILE = os.path.join(self.root, "specs", "general", "review.adoc")
        cm.EXECUTION_FILE = os.path.join(self.root, "specs", "core", "execution.adoc")

    def tearDown(self) -> None:
        (cm.REVIEW_FILE, cm.EXECUTION_FILE) = self._orig_files
        super().tearDown()

    def _write_valid(self):
        self.write("specs/general/review.adoc",
                   "= code review 规范\n\n== 问题记录\n\n"
                   "* **备注落点按事项的适用范围判定（L1）**：判定标准："
                   "①去掉具体类名/模块名后该结论是否仍成立；②是否只有某一处能触发或违反。\n"
                   "  ** 全局性 → 全局落点，**不得**写进范围性落点；"
                   "**全局备注里也不出现范围性内容**。\n"
                   "  ** 范围性 → 范围内落点，不上升为全局规范。\n")
        self.write("specs/core/execution.adoc",
                   "* 临时文档只做问题记录、不写备注（备注写入持久文档，"
                   "**落点按事项的适用范围判定**，见 link:../general/review.adoc[]「问题记录」）\n")
        self.write("specs/general/doc-design.adoc",
                   '* **发现的问题/事项的备注落点同样按"范围"判定**'
                   '（见 link:../general/review.adoc[]「问题记录」）。\n')

    def test_valid_rule_passes(self):
        self._write_valid()
        cm.check_review_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_review_file_reports(self):
        cm.check_review_guard()
        self.assertIn("缺少 code review 规范文件", self.error_texts())

    def test_dropped_global_note_ban_reports(self):
        # 反例：删掉"全局备注里也不出现范围性内容" → 全局落点里写具体类/方法细节又变成默许
        self._write_valid()
        p = os.path.join(self.root, "specs", "general", "review.adoc")
        with open(p, encoding="utf-8") as fh:
            t = fh.read()
        self.write("specs/general/review.adoc",
                   t.replace("全局备注里也不出现范围性内容", "备注要简洁"))
        cm.check_review_guard()
        self.assertIn("全局备注里也不出现范围性内容", self.error_texts())

    def test_dropped_reference_reports(self):
        # 反例：必加载层不再指向 review 规范 → 不按 review 规范加载的执行者学不到该判据
        self._write_valid()
        self.write("specs/core/execution.adoc", "* 临时文档只做问题记录。\n")
        cm.check_review_guard()
        self.assertIn("specs/core/execution.adoc", self.error_texts())


class TestCheckPromptDeliverySurfaceGuard(CheckSpecsTestCase):
    """钉住『提示词取值路径与装配状态』：不得退回与实测不符的印象式说法。

    用户指出的既有偏差：提示词与 `PROMPTS.adoc` 长期写"渲染视图下 `include::` 已展开"，
    但**实测**站点**原始文件地址**直出的是**仓库字节**（与工作区逐字节一致、指令仍在），
    站点上装配过的只有 `index.html` **页面内**渲染出的 HTML；而"把原始文件地址当渲染视图"
    正是上一轮实证过的失效。本组用例把"按取值路径判断 + 实证字样 + 禁止式表述"钉住。
    """

    COMMON = ("提示词公共片段\n"
              "查看与复制方式（**按取值路径判断，不按\"渲染视图\"这个印象**）："
              "`include::` **只在 AsciiDoc 处理器解析时**才展开，"
              "**判定依据是\"当前内容是被谁加工的\"、不是\"看起来像不像渲染过的页面\"**：\n"
              "- **经处理器装配过的内容**（IDE 预览、`asciidoctor` 渲染、站点页面内渲染的正文区）"
              "——未见指令即已装配；\n"
              "- **未经处理器装配的内容**：远程**原始文件**地址与本地读取都属此类，"
              "站点对非 HTML 文件**直出**仓库字节、与工作区**逐字节一致**，指令仍在；"
              "**本地读本文件**与远程取它**等价**；\n"
              "- **不得**把\"站点/渲染视图已展开\"**当成取用时的事实**——"
              "**原始文件地址与本地文件都不会装配**。\n")

    PROMPT = ("= 检查修复\n\n**给 AI 的读取说明（保证内容完整，先做）**："
              "判据是\"内容有没有被 AsciiDoc 处理器装配过\"——取到**原始文件**时指令"
              "**不会被展开**，请先读取片段**补齐**；**不得**以\"这是站点的**渲染视图**\"为由"
              "**跳过补齐**。\n")

    REGISTRY = ("=== 取值路径与装配状态（判据，不靠印象）\n\n"
                "| 取值路径 | 已装配？ |\n"
                "| IDE 预览 / 站点页面内渲染 | 是 |\n"
                "| 远程原始文件地址（**未装配**） | 否 |\n"
                "- **站点直链 = 仓库字节**：非 HTML 文件**直出原文**、与站点发布分支的同名文件逐字节一致；"
                "站点上存在装配形态的只有 `index.html` 自己的正文区。\n"
                "- **配图与判据一致**：三类是**不同取值路径**，**不是三种**版本的提示词。\n"
                "- **实证与话术（L1）**：**不得**留下与路径绑不上的笼统说法；"
                "须与实际抽样一致。\n")

    def setUp(self) -> None:
        super().setUp()
        self._prompts_orig = (cm.PROMPTS_FILE, cm.PROMPTS_DIR, cm.COMMON_PROMPT_FILE)
        cm.PROMPTS_FILE = os.path.join(self.root, "PROMPTS.adoc")
        cm.PROMPTS_DIR = os.path.join(self.root, "prompts")
        cm.COMMON_PROMPT_FILE = os.path.join(self.root, "prompts", "_common.txt")
        self._repo_root_orig = cm.REPO_ROOT
        cm.REPO_ROOT = self.root

    def tearDown(self) -> None:
        (cm.PROMPTS_FILE, cm.PROMPTS_DIR, cm.COMMON_PROMPT_FILE) = self._prompts_orig
        cm.REPO_ROOT = self._repo_root_orig
        super().tearDown()

    LIB_README = ("图书馆入口的取值形态：站点直链取到的是**未经处理器装配的仓库字节**——"
                  "站点对非 HTML 文件直出原文，页面内装配只发生在 `index.html` 自己的**正文区**。\n")
    LIB_USAGE = ("入口：`https` 直接可达（实测返回纯文本，即**未经装配的仓库字节**）。\n")
    LIB_SOURCES = ("取用侧实测：站点直链 → `text/plain`、**未经处理器装配的仓库字节**、"
                   "与站点发布分支的同名文件**逐字节一致**。\n")

    def _write_valid(self) -> None:
        self.write("prompts/_common.txt", self.COMMON)
        for name in ("review.adoc", "refactor.adoc"):
            self.write("prompts/" + name, self.PROMPT)
        self.write("PROMPTS.adoc", self.REGISTRY)
        self.write("AGENTS.adoc", "提示词条的**取值路径**须与实际一致；"
                                  "由 `check_prompt_delivery_surface_guard` 钉住。\n")
        self.write("library/README.adoc", self.LIB_README)
        self.write("library/usage.adoc", self.LIB_USAGE)
        self.write("library/sources.adoc", self.LIB_SOURCES)

    def test_valid_surface_passes(self):
        self._write_valid()
        cm.check_prompt_delivery_surface_guard()
        self.assertEqual(cm.errors, [])

    def test_fragment_missing_judgement_reports(self):
        # 反例：片段没写"按取值路径判断" → 执行者只能靠印象推断
        self._write_valid()
        self.write("prompts/_common.txt",
                   "查看与复制方式：渲染视图下已展开、内容完整。\n")
        cm.check_prompt_delivery_surface_guard()
        self.assertIn("按取值路径判断", self.error_texts())

    def test_fragment_missing_evidence_reports(self):
        # 反例：抽掉实证（逐字节一致/直出） → 后来者仍按"站点=渲染视图"推断
        self._write_valid()
        self.write("prompts/_common.txt",
                   self.COMMON.replace("**逐字节一致**", "内容相同")
                               .replace("**直出**", "按原样返回"))
        cm.check_prompt_delivery_surface_guard()
        self.assertIn("逐字节一致", self.error_texts())

    def test_prompt_note_not_updated_reports(self):
        # 反例：提示词读取说明仍按"渲染视图"陈述（题面侧没跟上）
        self._write_valid()
        self.write("prompts/review.adoc",
                   "= 检查修复\n\n**给 AI 的读取说明**：渲染视图下片段已展开、内容完整。\n")
        cm.check_prompt_delivery_surface_guard()
        self.assertIn("内容有没有被 AsciiDoc 处理器装配过", self.error_texts())

    def test_registry_table_removed_reports(self):
        # 反例：入口没有判据表 → 三类取值路径与两类状态无处可查
        self._write_valid()
        self.write("PROMPTS.adoc", "* 公共片段与 AI 读取：取到原始文件时须补齐。\n")
        cm.check_prompt_delivery_surface_guard()
        self.assertIn("取值路径与装配状态", self.error_texts())

    def test_not_three_versions_clause_removed_reports(self):
        # 反例：抽掉"不是三种版本" → 未展开会被读成内容缺失/旧版
        self._write_valid()
        self.write("PROMPTS.adoc", self.REGISTRY.replace("**不是三种**", "可与"))
        cm.check_prompt_delivery_surface_guard()
        self.assertIn("不是三种", self.error_texts())

    def test_wording_rule_removed_reports(self):
        # 反例：抽掉 L1 话术条 → "渲染视图下已展开"这类说法可以再写回来
        self._write_valid()
        self.write("PROMPTS.adoc",
                   self.REGISTRY.replace("**实证与话术（L1）**",
                                         "**补充说明**"))
        cm.check_prompt_delivery_surface_guard()
        self.assertIn("实证与话术", self.error_texts())

    def test_maintainer_entry_not_synced_reports(self):
        # 反例：维护方入口未登记该口径与抓手 → 后来者无从知道这条存在
        self._write_valid()
        self.write("AGENTS.adoc", "普通项目规范说明。\n")
        cm.check_prompt_delivery_surface_guard()
        self.assertIn("check_prompt_delivery_surface_guard", self.error_texts())


class TestCheckQuoteLineGuard(CheckSpecsTestCase):
    """钉住『引文段落防线』：引文段落不得用裸 `>` 起头（会被解析成 callout list 而中断编译）。

    真实失效（本项目实测）：文档里"引文/说明"段落长期写作 `> 说明：…`，页面侧
    （`index.html` 用 Asciidoctor.js）渲染成引用块、看不出问题；但旧式 AsciiDoc
    （Python `asciidoc`）的 `[listdef-callout]` 正则 `^<?(?P<index>\d*)> +(?P<text>.+)$`
    把单 `>` 起头者吃掉后 `index` 取到空串，随即 `List.calc_style()` 里 `assert False`，
    **整个文件编译失败**——实测一次性打死 6 个文件。该形态纯文本可判定，故须有抓手
    （`check_asciidoctor_syntax` 只在环境里真有 asciidoctor 时才跑，拦不住）。
    """

    def test_quote_marker_passes(self):
        # 正例：用 [quote] + 正文行（两代解析器都渲染成引用块）
        self.write("A.adoc", "= A\n\n[quote]\n说明：正文\n")
        cm.check_quote_line_guard()
        self.assertEqual(cm.errors, [])

    def test_bare_gt_line_reports(self):
        # 反例：裸 `>` 起头（本仓库此前的写法）——会被当成 callout list
        self.write("A.adoc", "= A\n\n> 说明：正文\n")
        cm.check_quote_line_guard()
        self.assertIn("裸 `>` 起头", self.error_texts())

    def test_bare_gt_reports_file_and_line(self):
        # 反例：须报出**文件与行号**（否则一堆文档里无从下手）
        self.write("library/README.adoc", "= 图书馆\n\n正文\n> 依据：RFC 2119\n")
        cm.check_quote_line_guard()
        self.assertIn("library/README.adoc", self.error_texts())
        self.assertIn(":4", self.error_texts())

    def test_inline_gt_not_reported(self):
        # 正例：行内 `>`（比较运算符、shell 重定向、`<commit>:<path>`）不在判定面内
        self.write("A.adoc",
                   "= A\n\nshell 重定向用 `cmd > log`；比较写作 `a > b`；"
                   "定位写作 `<commit>:<path>`\n")
        cm.check_quote_line_guard()
        self.assertEqual(cm.errors, [])

    def test_nested_list_marker_not_reported(self):
        # 正例：列表里的 `** ` 与 `* ` 不误报（只判行首 `> `）
        self.write("A.adoc", "= A\n\n* 一\n** 二\n")
        cm.check_quote_line_guard()
        self.assertEqual(cm.errors, [])


class TestCheckDependencyViewGuard(CheckSpecsTestCase):
    """钉住『依赖关系文档』：模块间依赖的唯一视图（完整、UML、可直达、不过期、不重复声明）。

    该条对应用户报告的真实失效：AI 编辑代码时**加重复依赖**——模块已经（直接或间接）
    依赖了某库，却又在它的依赖清单里声明一次。根因不是"忘了"，而是**没有一份完整依赖
    关系的视图**，只能临场重建依赖树。最易被两件事冲掉：
      * **降级成一句口号** —— "要注意依赖关系"读起来无害，于是重复依赖照旧；
      * **入口不指向它** —— 规则写在被引用的文件里、加载调度器/依赖规范都不指向它，
        多模块项目与"增删依赖"场景根本不会加载到（写了等于没写）。
    故本组用例覆盖"节被删""UML 优先被删""先查本文档被删""缺失即新增被删""不重复声明被删"
    "调度器未指向""依赖规范未指向"。
    """

    SECTION = (
        "== 依赖关系文档（模块间依赖的唯一视图）\n"
        "\n"
        "**识别特征**：多模块结构，或动手增删依赖。\n"
        "\n"
        "* **完整依赖关系文档即唯一视图（L1）**：多模块项目须维护一份**完整依赖关系文档**"
        "（`<项目根>/doc/dependency.adoc`，单模块项目放 `<模块>/doc/dependency.adoc`）——"
        "**完整**指列出**当前项目全部模块之间**的依赖关系（谁依赖谁、方向；**不列第三方库清单**）。\n"
        "* **优先用 UML 表述（L1）**：依赖关系**以 UML 图为主**，模块用组件/包、依赖用依赖箭头；"
        "**不得只写一段文字描述**。\n"
        "* **位置须让 AI 直接处理（L1）**：文档须放在多模块项目的**文档根目录**"
        "（项目根 `doc/dependency.adoc`）。\n"
        "* **查依赖关系优先查本文档（L1）**：涉及依赖判断时**先读本视图**；"
        "**回答完即止，不重启依赖树解析**。\n"
        "* **文档缺失则新增，不跳过（L1）**：多模块项目**没有本视图时**，须在本次任务内"
        "**新增**；**存在但不完整**时补全后再用。\n"
        "* **依赖关系变更须与构建文件同一提交内同步（L1）**：**同一提交内**更新本视图。\n"
        "* **模块内外部依赖不重复声明（L1）**：**不得再在它的依赖清单里重复声明同一依赖**；"
        "**新增依赖前先读本视图**。\n"
        "* **文档与工具各司其职（L2）**：不替代构建工具（依赖树只描述**第三方库**）。\n"
        "* 依据（标准名/编号）：ISO/IEC/IEEE 42010、UML、ISO/IEC/IEEE 29148\n"
    )
    GENERIC = (
        "= 入口\n\n== 分类与懒加载（加载调度器）\n"
        "  ** 设计文档 → link:specs/general/doc-design.adoc[]"
        "（**含模块间依赖关系文档**，见其「依赖关系文档（模块间依赖的唯一视图）」）\n"
        "== 规范文件登记完整性\n"
    )
    DEPENDENCY = (
        "= 依赖管理规范\n\n== 引入依赖\n"
        "* **传递依赖不直接使用（L2）**：确需使用时须显式声明并说明理由。"
        "**多模块项目的模块间依赖不在本条范围**——模块已被（直接或间接）依赖时"
        "**不得重复声明同一依赖**，判定前先读模块间依赖的唯一视图"
        "（见 link:../general/doc-design.adoc[]「依赖关系文档（模块间依赖的唯一视图）」）。\n"
    )

    def setUp(self) -> None:
        super().setUp()
        self._orig_view = cm.DEPENDENCY_VIEW_FILE
        cm.DEPENDENCY_VIEW_FILE = os.path.join(
            self.root, "specs", "general", "doc-design.adoc")

    def tearDown(self) -> None:
        cm.DEPENDENCY_VIEW_FILE = self._orig_view
        CheckSpecsTestCase.tearDown(self)

    def _write_valid(self) -> None:
        self.write("specs/general/doc-design.adoc", "= 设计文档规范\n\n" + self.SECTION)
        self.write("AGENTS_COMMON.adoc", self.GENERIC)
        self.write("specs/general/dependency.adoc", self.DEPENDENCY)

    def test_valid_passes(self):
        self._write_valid()
        cm.check_dependency_view_guard()
        self.assertEqual(cm.errors, [])

    def test_section_deleted_reports(self):
        # 反例：整节被删 → 依赖视图无处承载，重复依赖照旧
        self._write_valid()
        self.write("specs/general/doc-design.adoc", "= 设计文档规范\n\n== 设计文档\n")
        cm.check_dependency_view_guard()
        self.assertIn("依赖关系文档（模块间依赖的唯一视图）", self.error_texts())

    def test_uml_priority_removed_reports(self):
        # 反例（关键词堆砌式假绿）：UML 优先被删、只剩"要有依赖文档" → 判据不可判定
        self._write_valid()
        self.write("specs/general/doc-design.adoc",
                   "= 设计文档规范\n\n" + self.SECTION.replace(
                       "* **优先用 UML 表述（L1）**：依赖关系**以 UML 图为主**，模块用组件/包、"
                       "依赖用依赖箭头；**不得只写一段文字描述**。\n", ""))
        cm.check_dependency_view_guard()
        self.assertIn("UML", self.error_texts())

    def test_read_first_rule_removed_reports(self):
        # 反例："先读本文档"被删 → 规则不会被使用（仍去解析依赖树）
        self._write_valid()
        self.write("specs/general/doc-design.adoc",
                   "= 设计文档规范\n\n" + self.SECTION.replace(
                       "* **查依赖关系优先查本文档（L1）**：涉及依赖判断时**先读本视图**；"
                       "**回答完即止，不重启依赖树解析**。\n", ""))
        cm.check_dependency_view_guard()
        self.assertIn("先读本视图", self.error_texts())

    def test_missing_then_add_removed_reports(self):
        # 反例："缺失则新增"被删 → 规则只对已合规项目生效
        self._write_valid()
        self.write("specs/general/doc-design.adoc",
                   "= 设计文档规范\n\n" + self.SECTION.replace(
                       "* **文档缺失则新增，不跳过（L1）**：多模块项目**没有本视图时**，"
                       "须在本次任务内**新增**；**存在但不完整**时补全后再用。\n", ""))
        cm.check_dependency_view_guard()
        self.assertIn("没有本视图时", self.error_texts())

    def test_no_duplicate_declare_removed_reports(self):
        # 反例："不重复声明"被删 → 本条要消灭的失效本身不再被约束
        self._write_valid()
        self.write("specs/general/doc-design.adoc",
                   "= 设计文档规范\n\n" + self.SECTION.replace(
                       "* **模块内外部依赖不重复声明（L1）**：**不得再在它的依赖清单里重复声明同一依赖**；"
                       "**新增依赖前先读本视图**。\n", ""))
        cm.check_dependency_view_guard()
        self.assertIn("不得再在它的依赖清单里重复声明", self.error_texts())

    def test_dispatcher_not_pointing_reports(self):
        # 反例：加载调度器未指向该节 → 多模块/增删依赖场景不会加载到它
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", self.GENERIC.replace(
            "（**含模块间依赖关系文档**，见其「依赖关系文档（模块间依赖的唯一视图）」）", ""))
        cm.check_dependency_view_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_dependency_spec_not_pointing_reports(self):
        # 反例：依赖规范未指向该视图 → 按依赖规范学习时漏掉这条
        self._write_valid()
        self.write("specs/general/dependency.adoc", "= 依赖管理规范\n\n== 引入依赖\n* 先查再用。\n")
        cm.check_dependency_view_guard()
        self.assertIn("dependency.adoc", self.error_texts())

    def test_missing_file_reports(self):
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "general", "doc-design.adoc"))
        cm.check_dependency_view_guard()
        self.assertIn("缺少文件", self.error_texts())


class TestCheckCommentDispatchGuard(CheckSpecsTestCase):
    """钉住『评论唤起新实例防线』：评论即派发入口的要点不得被删或降级。

    背景（用户提出的机制）：CNB 平台下**在 Issue/PR 里新增一条评论、@ 某个 NPC、说清要求**
    即发起一次执行，且**可以要求它使用干净的上下文**。高风险点在于被读成"@ 一下就能绕过
    派发规则"——故机械钉住"入口形态 / 不放宽任何派发约束 / 一次评论 = 一次派发 / 干净上下文
    须显式要求且不是保证 / 仅点名不构成派发"这几处要点，以及调度器识别特征与 README 同步。
    """

    CNB = ("= CNB 规范（平台层）\n\n"
           "== 评论唤起新实例（平台侧的派发入口）\n"
           "* **评论唤起是平台侧的派发方式，不改变派发判据（L1）**：在 Issue 或 PR 下"
           "**新增一条评论**、@ 某个 NPC（如 `@CodeBuddy`）、并在评论里**说清要求**，"
           "即新增一次执行；本条**只把『往哪派』说清楚，不放宽任何派发约束**"
           "（一律按 link:../general/collab.adoc[] 执行，也不构成『可以点名外部 Agent』的例外）。\n"
           "* **一次评论 = 一次派发，任务边界由评论正文界定（L1）**：要求须在**评论里写清**"
           "（做什么、边界、产物形态、验证口径）；**未写清的不得自行假定后开工**。\n"
           "* **要求『用干净上下文』是派发选项，须在评论里显式要求（L1）**：默认**沿用该 Issue/PR 的既有上下文**；"
           "显式要求时当作全新任务、**规范仍须按入口重新加载**（『上下文干净』只清历史对话、**不清约束**）；"
           "**该要求属降低风险的措施、要求不是保证**，须**如实说明本次实际读到的上下文范围**。\n"
           "* **唤起不等于自动开工（L3）**：单条评论**只有寒暄**/只 @ 一下时不构成派发，不得自行开工。\n"
           "* 正文里的具体实例名 `@CodeBuddy`（**仅作举例**）——其余口径见通用层。\n"
           "* **缺项**时须回复拒绝并**列出缺失项**；该要求**不豁免任何派发判据**。\n")

    COLLAB = ("= agent 协作规范（通用层）\n\n"
              "== 派发入口（往哪派、派什么）\n"
              "* **评论唤起是『评论即派发入口』的一种形态（L1）**：在 Issue / PR 下新增一条评论、"
              "在评论里点名 `@` 起某个 NPC 并在评论里说清要求，即在该任务单下新增一次执行；"
              "该入口**不豁免本文件的任何派发判据**。\n"
              "* **一次评论 = 一次派发，任务边界由评论正文界定（L1）**：要求须在评论里写清、"
              "**未写清的不得自行假定后开工**。\n"
              "* **可要求『用干净上下文』，但这是要求不是保证（L1）**：须先自评**环境能力**；"
              "**『上下文干净』只清历史对话、不清约束**；"
              "**不豁免本文件任何派发判据**，也**不意味着**连本次对象钉定都要另取一套。\n"
              "* **评论是『派发者』的入口，不是\"执行者\"的手段（L1）**：执行者"
              "**不得自行发一条评论**去唤起另一个 Agent/NPC 接手自己的活。\n"
              "* **要求未写清或判据不满足时的形态（L1）**：须在原评论下回复拒绝并列出**缺项**、"
              "**不得开工**，也不得拿『他没写清』当擅自扩大范围的挡箭牌；"
              "**留证落点**即该条**评论下的回复**。\n"
              "* **计数口径（L2）**：**一条评论 = 一次派发**；一条评论点名多个对象按 **N 次派发**计。\n"
              "* **本入口与文件操作的边界（L1）**：**评论不是交付**，改动仍按 link:../core/execution.adoc[]"
              "「文件操作强制检查」判。\n")

    GENERIC = ("= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
               "  ** 多 agent 协作（含**派发入口（评论唤起新实例：一次评论 = 一次派发）**）"
               " → link:specs/general/collab.adoc[]\n"
               "  ** CNB 平台（含**在 Issue/PR 里发评论 @ 某个 NPC 发起一次执行**）"
               " → link:specs/platform/cnb.adoc[]\n")

    def setUp(self) -> None:
        super().setUp()
        self._orig_readme = cm.README_FILE
        cm.README_FILE = os.path.join(self.root, "README.adoc")

    def tearDown(self) -> None:
        cm.README_FILE = self._orig_readme
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("specs/platform/cnb.adoc", self.CNB)
        self.write("specs/general/collab.adoc", self.COLLAB)
        self.write("AGENTS_COMMON.adoc", self.GENERIC)
        self.write("README.adoc", "# README\n\n## 目录结构\n* 平台层：cnb（含**评论唤起**口径）\n")

    def test_valid_passes(self):
        self._write_valid()
        cm.check_comment_dispatch_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_cnb_section_reports(self):
        # 反例：平台层该节被删 → 平台上的派发入口无人说清
        self._write_valid()
        self.write("specs/platform/cnb.adoc", "= CNB 规范（平台层）\n\n== 冲突处理\n* 自动解决。\n")
        cm.check_comment_dispatch_guard()
        self.assertIn("评论唤起新实例（平台侧的派发入口）", self.error_texts())

    def test_relaxed_dispatch_rule_reports(self):
        # 反例（最危险的一种）：把该入口写成"可以不按派发判据"（点名外部 Agent 的例外）
        self._write_valid()
        self.write("specs/platform/cnb.adoc", self.CNB.replace(
            "不放宽任何派发约束", "可按需放宽派发约束").replace(
            "也不构成『可以点名外部 Agent』的例外", "必要时可点名外部 Agent 顶替"))
        cm.check_comment_dispatch_guard()
        self.assertIn("不放宽任何派发约束", self.error_texts())

    def test_clean_context_as_default_reports(self):
        # 反例：把"干净上下文"写成默认（不再需要评论里显式要求）→ 读者按错的默认预期派活
        self._write_valid()
        self.write("specs/platform/cnb.adoc", self.CNB.replace(
            "默认**沿用该 Issue/PR 的既有上下文**", "默认即为干净上下文"))
        cm.check_comment_dispatch_guard()
        self.assertIn("沿用该 Issue/PR 的既有上下文", self.error_texts())

    def test_clean_context_carrying_constraints_reports(self):
        # 反例："不清约束"被删 → 会被执行成"上下文干净了所以不用再读规范"
        self._write_valid()
        self.write("specs/general/collab.adoc", self.COLLAB.replace("、不清约束", ""))
        cm.check_comment_dispatch_guard()
        self.assertIn("不清约束", self.error_texts())

    def test_missing_general_section_reports(self):
        # 反例：通用层「派发入口」节被删 → 非 CNB 场景下该入口无人说清
        self._write_valid()
        self.write("specs/general/collab.adoc", "= agent 协作规范（通用层）\n\n== 资源限制与感知\n* 硬超时。\n")
        cm.check_comment_dispatch_guard()
        self.assertIn("派发入口（往哪派、派什么）", self.error_texts())

    def test_dispatcher_not_pointing_reports(self):
        # 反例：调度器识别特征被删 → 该节永远不会被加载（写了等于没写）
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
                                          "  ** 多 agent 协作 → link:specs/general/collab.adoc[]\n")
        cm.check_comment_dispatch_guard()
        self.assertIn("评论唤起新实例", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例：README 目录说明未同步 → 读者按 README 学习时不知道有这个入口
        self._write_valid()
        self.write("README.adoc", "# README\n\n## 目录结构\n* 平台层：cnb\n")
        cm.check_comment_dispatch_guard()
        self.assertIn("评论唤起", self.error_texts())


class TestCheckSelfDispatchGuard(CheckSpecsTestCase):
    """钉住『不得自行发评论唤起自己防线』：执行者不得把任务在执行中重新发起一次。

    用户提出的收紧要求（"不能艾特自己"）。这条最容易被"分两步更清楚""换个节点更专注"
    合理化成自动动作——而每次唤起都要重新按入口加载规范、重新建上下文并付一次调用与等待，
    **跨轮分步该由人决定**。故本组用例把平台层/通用层/题面侧/登记处/调度器五处一并钉住。
    """

    CNB = (
        "= CNB 规范（平台层）\n\n"
        "== 评论唤起新实例（平台侧的派发入口）\n"
        "* **评论唤起是平台侧的派发方式（L1）**：在 Issue 或 PR 下**新增一条评论**、"
        "@ 某个 NPC（**仅作举例**）、并在评论里**说清要求**，即新增一次执行。\n"
        "* **不得以评论派发唤起自己（L1，防无限派发）**：被评论唤起的执行者**不得在本次执行中"
        "再发一条评论去点名唤起自己**（同一点名、**同一实例名**），"
        "**也不得转由他人**/其他执行者**代发**。判定标准：①本次执行期间新增的点名评论"
        "指向本条评论上的唤起名；②以\"分两步更清楚\"等理由**自我豁免**；"
        "③**实际发了这条评论**、把任务在执行中重新发起一次（判据是**这条评论发出去没有**、"
        "**不是这次执行有没有因此结束**）；④**转交他人**代发。"
        "**为什么**：**一次评论就是一次派发**，**发起下一次是派发者的动作**、不是执行者的动作。"
        "**正当形态**：**先停**、只输出一次\"**停下确认**\"，由**人**另发一条评论决定是否再来一次。\n"
        "* **须由与执行者相同的 Agent 承担验证（L1）**：**要求验证/复核须由与执行者相同的 "
        "Agent 来做的那些规则，只在本平台（CNB）成立**——**本平台之外不适用**：环境不提供同 Agent "
        "的子执行者时，**不得援引该条拒做或把任务停在中间**；**不提供**时按降级路径执行、"
        "**验证与交付不因此缺失**。判定标准：平台层未写明时不得援引本条拒做。"
        "**由谁承担**是**项目自身的取舍**（IEEE 1028 只要求有独立、可核对的评审发生）；"
        "条文的写入面本就在平台层、**不在公共内容**（`AGENTS_COMMON.adoc` + `specs/`）里，"
        "引用方按入口加载时**不会取到它**。\n"
        "* **复核者的来源：\"谁发起的\"与\"谁承担\"的区分（L1）**：**\"须由与执行者相同的 "
        "Agent 承担\"说的是复核者的来源要求，**不是复核的发起方式**、**各自独立**。"
        "故**执行者不得用**\"为了满足同 Agent 复核\"**去 @ 自己**（不因目的是复核而放宽）。"
        "**能不能拿到，在动手前判定**（`printenv CNB_EVENT` 实测）；"
        "**一个任务只由**人**决定起几次执行**，缺的复核**在本次执行内**按降级路径补。"
        "**该情形下的交付形态**：**照常交付**，结论里**如实写明可信的独立复核不可得**；"
        "**\"已交付 + 校验全绿 + 复核缺口如实标出\"不得混写**成\"已复核通过\"。"
        "判定标准：①用 @ 自己换取一次新执行来做复核 "
        "②把\"拿不到独立复核\"写成\"已复核通过\" ③以\"等下一轮复核\"为由**停在中间**不交付。\n"
    )

    COLLAB = (
        "= agent 协作规范（通用层）\n\n"
        "== 派发入口（往哪派、派什么）\n"
        "* **评论唤起是『评论即派发入口』的一种形态（L1）**：在 Issue / PR 下新增一条评论、"
        "点名并说清要求，即在该任务单下新增一次执行。\n"
        "* **执行者不得自行发评论唤起自己（L1，防无限派发）**：执行者不得在本次执行中"
        "自行发一条评论点名唤起自己（也不得转由他人代发）——**发起下一次是\"派发者\"的动作**，"
        "故**执行者\"想分步\"不是派发的依据**；**先停**、由**人**另发一条评论；"
        "**跨轮分步由人决定**。平台侧同口径条见 link:../platform/cnb.adoc[]。\n"
        "* **同 Agent 的适用面（L1，先定条件再谈强制）**：**不是无条件成立的规则**——"
        "以**平台层写明该前提成立**为前提；**平台层未写明**时不得援引本条拒做、照做该职责。"
        "**由谁承担**是**项目自身的取舍**，标准**未规定复核者须是同一产品**。\n"
        "* **\"复核者的来源\"与\"复核的发起\"是两件事（L1）**：不得把\"满足同 Agent\"读成"
        "\"必须再发一条评论叫一个 Agent 来\"——**一个任务只由人决定起几次执行**；"
        "**拿不到同 Agent 子执行者时**按降级路径**在本次执行内**补；**交付照常**、缺口如实写明。\n"
    )

    def setUp(self) -> None:
        super().setUp()
        self._orig_prompts = (cm.PROMPTS_FILE, cm.PROMPTS_DIR, cm.COMMON_PROMPT_FILE,
                              cm.README_FILE)
        cm.PROMPTS_FILE = os.path.join(self.root, "PROMPTS.adoc")
        cm.PROMPTS_DIR = os.path.join(self.root, "prompts")
        cm.COMMON_PROMPT_FILE = os.path.join(self.root, "prompts", "_common.txt")
        cm.README_FILE = os.path.join(self.root, "README.adoc")

    def tearDown(self) -> None:
        (cm.PROMPTS_FILE, cm.PROMPTS_DIR, cm.COMMON_PROMPT_FILE,
         cm.README_FILE) = self._orig_prompts
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("specs/platform/cnb.adoc", self.CNB)
        self.write("specs/general/collab.adoc", self.COLLAB)
        self.write("specs/general/verify.adoc",
                   "= 验证\n\n* **执行者选择：强制同 Agent（L1，其适用面由平台层限定）**："
                   "『由与执行者相同的 Agent 承担』**不是平台无关的强制前提**——"
                   "**平台层写明该前提成立**时按强制判；平台不提供同 Agent 子执行者时"
                   "**不得援引本条跳过复核**或把任务停在中间。\n")
        self.write("prompts/_common.txt", "// tag::delivery[]\n8. 交付\n// end::delivery[]\n")
        self.write("AGENTS_COMMON.adoc",
                   "* 多 agent 协作（派发入口；**执行者不得自行发评论唤起自己**）\n"
                   "* CNB 平台（评论唤起新实例；**执行者不得自行发评论唤起自己**）\n")
        self.write("prompts/review.adoc",
                   "= 检查修复\n\n[listing]\n----\n"
                   "10. **不得自行发评论唤起自己（L1，防无限派发）**："
                   "**一次评论 = 一次派发**；想分步就**先停**、**由**人**另发一条评论**。\n"
                   "include::_common.txt[tag=delivery]\n----\n")
        self.write("prompts/refactor.adoc",
                   "= 重构\n\n[listing]\n----\n"
                   "10. **不得自行发评论唤起自己（L1，防无限派发）**："
                   "**一次评论 = 一次派发**；想分步就**先停**、**由**人**另发一条评论**。\n"
                   "include::_common.txt[tag=delivery]\n----\n")
        self.write("PROMPTS.adoc",
                   "* 公共约定：**不得自行发评论唤起自己**——\"分两步更清楚\"不构成理由。\n")
        self.write("README.adoc",
                   "# README\n\n**执行者不得在本次执行中自行发评论点名唤起自己**"
                   "（想分步就**先停**、由**人**另发一条评论；\"分两步更清楚\"不构成理由）。\n")

    def test_valid_passes(self):
        self._write_valid()
        cm.check_self_dispatch_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_platform_file_reports(self):
        # 反例：平台层文件被删 → 自派禁令无处承载
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "platform", "cnb.adoc"))
        cm.check_self_dispatch_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_platform_clause_removed_reports(self):
        # 反例（最危险的一种）：平台层那条 L1 被整条删掉 → "再派一次"重新变成可选动作
        self._write_valid()
        cnb = self.CNB.replace(
            "* **不得以评论派发唤起自己（L1，防无限派发）**", "* **附注**")
        self.write("specs/platform/cnb.adoc", cnb)
        cm.check_self_dispatch_guard()
        self.assertIn("不得以评论派发唤起自己", self.error_texts())

    def test_platform_rule_relaxed_reports(self):
        # 反例：把禁令降级成建议（L1 被抽掉）→ 强制点没了
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   self.CNB.replace("（L1，防无限派发）**：被评论唤起的执行者",
                                    "**：原则上被评论唤起的执行者"))
        cm.check_self_dispatch_guard()
        self.assertIn("L1", self.error_texts())

    def test_relay_to_others_clause_removed_reports(self):
        # 反例："转由他人代发"被删 → 把自派外包出去就绕过了
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   self.CNB.replace("**也不得转由他人**/其他执行者**代发**。", "。"))
        cm.check_self_dispatch_guard()
        self.assertIn("代发", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例：判定标准被抽空（只留一句口号）→ 争议时无法判断是否被遵守
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   self.CNB.replace("①本次执行期间新增的点名评论"
                                    "指向本条评论上的唤起名；", "")
                   .replace("**实际发了这条评论**、把任务在执行中重新发起一次（判据是**这条评论发出去没有**、"
                            "**不是这次执行有没有因此结束**）；", "")
                   .replace("**转交他人**代发。", ""))
        cm.check_self_dispatch_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_process_boundary_clause_removed_reports(self):
        # 反例："判据是这条评论发出去没有"被删 → "不在同一进程内所以不算"成为新借口
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   self.CNB.replace("（判据是**这条评论发出去没有**、"
                                    "**不是这次执行有没有因此结束**）", ""))
        cm.check_self_dispatch_guard()
        self.assertIn("这条评论发出去没有", self.error_texts())

    def test_general_layer_clause_removed_reports(self):
        # 反例：通用层同口径条被删 → 非 CNB 场景下"想分步就自动再派"无人拦
        self._write_valid()
        self.write("specs/general/collab.adoc",
                   "= agent 协作规范（通用层）\n\n== 派发入口（往哪派、派什么）\n"
                   "* 评论即派发入口。\n")
        cm.check_self_dispatch_guard()
        self.assertIn("执行者不得自行发评论唤起自己", self.error_texts())

    def test_prompt_step_removed_reports(self):
        # 反例：题面侧步骤被删（片段在、流程里却没有这一步）→ 执行者按流程走即漏
        self._write_valid()
        self.write("prompts/refactor.adoc",
                   "= 重构\n\ninclude::_common.txt[tag=delivery]\n")
        cm.check_self_dispatch_guard()
        self.assertIn("不得自行发评论唤起自己", self.error_texts())

    def test_dispatcher_not_synced_reports(self):
        # 反例：调度器识别特征被删 → 该 L1 永远不会被加载（写了等于没写）
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "* 多 agent 协作（派发入口）\n* CNB 平台（评论唤起新实例）\n")
        cm.check_self_dispatch_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_registry_not_synced_reports(self):
        # 反例：登记处未同步 → 提示词被复制到未知项目后公开面看不到这条禁令
        self._write_valid()
        self.write("PROMPTS.adoc", "* 公共约定：改动范围边界。\n")
        cm.check_self_dispatch_guard()
        self.assertIn("PROMPTS.adoc", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例：README 使用要点未同步 → 公开面只看得见"可以评论派活"
        self._write_valid()
        self.write("README.adoc", "# README\n\n普通说明。\n")
        cm.check_self_dispatch_guard()
        self.assertIn("README", self.error_texts())

    def test_platform_applicability_removed_reports(self):
        # 反例（用户后续澄清的那一条）：平台层把"只适用于 CNB"的适用面删掉
        # → 该要求被外推成平台无关的强制前提，非 CNB 环境会把"没有同 Agent 子执行者"
        # 读成"所以不能验证/不能交付"。
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   self.CNB.replace("**只在本平台（CNB）成立**", "**一律成立**")
                   .replace("**本平台之外不适用**", "**各处一律适用**")
                   .replace("**不得援引该条拒做或把任务停在中间**", "**照常执行**"))
        cm.check_self_dispatch_guard()
        self.assertIn("本平台之外不适用", self.error_texts())

    def test_platform_not_public_content_clause_removed_reports(self):
        # 反例：把"写入面不在公共内容里"删掉 → 引用方会以为该前提随公共入口一起下发
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   self.CNB.replace("不在公共内容", "在公共内容"))
        cm.check_self_dispatch_guard()
        self.assertIn("不在公共内容", self.error_texts())

    def test_general_applicability_removed_reports(self):
        # 反例：通用层把"不是无条件成立的规则 / 以平台层写明为前提"删掉
        # → 通用层被当成平台无关的强制前提。
        self._write_valid()
        self.write("specs/general/collab.adoc",
                   self.COLLAB.replace("**不是无条件成立的规则**——"
                                       "以**平台层写明该前提成立**为前提；", ""))
        cm.check_self_dispatch_guard()
        self.assertIn("不是无条件成立的规则", self.error_texts())

    def test_self_mention_for_review_clause_removed_reports(self):
        # 反例：把"不得用为了复核去 @ 自己"删掉 → "再要一个干净上下文来复核"成为自派的正当理由
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   self.CNB.replace(
                       '故**执行者不得用**\"为了满足同 Agent 复核\"**去 @ 自己**'
                       '（不因目的是复核而放宽）。', "。"))
        cm.check_self_dispatch_guard()
        self.assertIn("去 @ 自己", self.error_texts())

    def test_deliver_without_review_not_confused_clause_removed_reports(self):
        # 反例：把"已交付 + 校验全绿 + 复核缺口如实标出不得混写成已复核通过"删掉
        # → 缺复核被悄悄记成"已复核通过"。
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   self.CNB.replace(
                       '**\"已交付 + 校验全绿 + 复核缺口如实标出\"不得混写**成'
                       '\"已复核通过\"。', "。"))
        cm.check_self_dispatch_guard()
        self.assertIn("已复核通过", self.error_texts())

    def test_general_layer_source_vs_dispatch_clause_removed_reports(self):
        # 反例：通用层把"来源要求 ≠ 发起方式"这条配套判据删掉
        # → 非 CNB 场景下会被读成"必须自派"或"不许复核"。
        self._write_valid()
        self.write("specs/general/collab.adoc",
                   self.COLLAB.replace('* **"复核者的来源"与"复核的发起"是两件事（L1）**：'
                                       '不得把"满足同 Agent"读成'
                                       '"必须再发一条评论叫一个 Agent 来"——'
                                       '**一个任务只由人决定起几次执行**；'
                                       '**拿不到同 Agent 子执行者时**按降级路径'
                                       '**在本次执行内**补；**交付照常**、缺口如实写明。\n', ""))
        cm.check_self_dispatch_guard()
        self.assertIn("复核的发起", self.error_texts())

    def test_verify_applicability_removed_reports(self):
        # 反例：三视角落点把适用面标注删掉 → 不同口径的平台被同一条强判。
        self._write_valid()
        self.write("specs/general/verify.adoc",
                   "= 验证\n\n* 执行者选择：强制同 Agent（L1）：一律由与执行者相同的 Agent 承担。\n")
        cm.check_self_dispatch_guard()
        self.assertIn("其适用面由平台层限定", self.error_texts())


class TestCheckApiNamingGuard(CheckSpecsTestCase):
    """钉住『Feign 接口命名带所属域/项目前缀防线』。

    该条对应用户提出的真实失效：写 Feign 接口时接口名不带所归属的前缀，同域多个服务的同类
    Feign 接口**同名碰名**（`UserApi` 到处都是），只能靠包名区分。
    用户要求：`api` 前加一个前缀，**优先考虑已有的固定前缀**；没有先例则取项目名称单词的
    词首再组合（`user-center` → `UcUserApi`、`open-user-center` → `OucUserApi`）。
    用户同时限定范围：**目前只需要考虑 feign，不需要考虑其他对外接口**。

    最易被四件事冲掉：
      * **条文被删或降级成建议** —— "随手取个不碰名的"重回默认做法；
      * **范围被自行放大** —— 写回"对外提供或跨服务/跨项目调用的接口"，把用户明确排除的
        REST Controller / RPC 契约接口卷进来；
      * **技术栈落点缺失** —— Java 执行者按栈文件学，通用层有、栈层没有等于没写；
      * **调度器识别特征被删** —— 该条永远不会被触发加载（写了等于没写）。
    故本组用例覆盖：条文被删 / L1 被降级 / 范围限定被删 / 范围被写宽 / 判据被抽（先例优先、
    实例）/ 栈落点缺失 / 栈层不指向通用条 / 调度器未登记 / README 未同步 / 图书馆依据缺失。
    """

    CODING = (
        "= 通用编码规范\n"
        "\n"
        "== 命名与代码质量\n"
        "* Feign 接口命名带所属域/项目前缀（L1）：**Feign 声明式 HTTP 客户端接口**"
        "（跨服务远程调用接口；本次**只此一类**，其他对外接口如 REST Controller、RPC 服务契约接口"
        "暂不在本约束内，不按本条改名，也不得据此扩张判定）命名须为「**前缀 + 接口业务名 + `Api`**」，"
        "前缀由**接口所属的域/项目**决定——**先取该域已存在的固定前缀（先例优先），没有先例才按项目名"
        "取词首字母组合**（`user-center` → `Uc`、`open-user-center` → `Ouc`，即 `UcUserApi`、"
        "`OucUserApi`）。判定：①所属域已有固定前缀却另取一套；②同类接口有的带前缀有的不带"
        "（同一项目内不一致）；③把业务名或所属服务的全名当接口名前缀（如 `UserCenterUserApi` "
        "一类**拼全名**的写法）。\n"
    )

    JAVA = (
        "= Java 规范（技术栈层）\n"
        "\n"
        "== 命名\n"
        "* Feign 接口命名带所属域前缀（L1，Java 落点，本条唯一适用面）：**Feign 声明式 HTTP "
        "客户端接口**按「**前缀 + 接口业务名 + `Api`**」命名——`user-center` → `UcUserApi`、"
        "`open-user-center` → `OucUserApi`；**只约束 Feign 接口**，REST Controller、RPC 服务契约"
        "等其他对外接口不适用。判据见 link:../general/coding.adoc[]「命名与代码质量」的"
        "「Feign 接口命名带所属域/项目前缀」。\n"
    )

    GENERIC = (
        "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
        "  ** 编写代码 → link:specs/general/coding.adoc[]（含**「Feign 接口命名带所属域/项目前缀」**："
        "**只此一类**接口适用）\n"
        "  ** Java 项目（存在 `.java`）→ link:specs/stack/java.adoc[]（**Feign 接口命名**："
        "前缀 + 接口业务名 + `Api`，只约束 Feign 接口）\n"
    )

    SOURCES = (
        "= 图书馆依据\n\n== Feign 接口命名带所属域前缀（Spring Cloud）\n"
        "* 说明：此条为要点转述、非逐字摘录；本仓库**未逐字取回**，故不引用任何加引号的字句。\n"
        "* 适用范围：用户明确「目前只需要考虑 feign，不需要考虑其他对外接口」，故只取 Feign 这一类。\n"
    )

    def setUp(self) -> None:
        super().setUp()
        self._orig_coding = cm.CODING_FILE
        self._orig_java = cm.JAVA_STACK_FILE
        self._orig_generic = cm.GENERIC_FILE
        self._orig_readme = cm.README_FILE
        cm.CODING_FILE = os.path.join(self.root, "specs", "general", "coding.adoc")
        cm.JAVA_STACK_FILE = os.path.join(self.root, "specs", "stack", "java.adoc")
        cm.GENERIC_FILE = os.path.join(self.root, "AGENTS_COMMON.adoc")
        cm.README_FILE = os.path.join(self.root, "README.adoc")

    def tearDown(self) -> None:
        (cm.CODING_FILE, cm.JAVA_STACK_FILE, cm.GENERIC_FILE,
         cm.README_FILE) = (self._orig_coding, self._orig_java, self._orig_generic,
                            self._orig_readme)
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("specs/general/coding.adoc", self.CODING)
        self.write("specs/stack/java.adoc", self.JAVA)
        self.write("AGENTS_COMMON.adoc", self.GENERIC)
        self.write("README.adoc", "# README\n\n## 目录结构\n* 技术栈层：java（含**Feign 接口命名**）\n")
        self.write("library/sources.adoc", self.SOURCES)

    def test_valid_api_naming_guard_passes(self):
        self._write_valid()
        cm.check_api_naming_guard()
        self.assertEqual(cm.errors, [])

    def test_clause_deleted_reports(self):
        # 反例：通用层条文被删 → "随手取个不碰名的"重回默认做法
        self._write_valid()
        self.write("specs/general/coding.adoc", "= 通用编码规范\n\n== 命名与代码质量\n* 命名要清晰。\n")
        cm.check_api_naming_guard()
        self.assertIn("Feign 接口命名带所属域/项目前缀", self.error_texts())

    def test_level_downgraded_reports(self):
        # 反例：L1 被降级成建议（读起来无害，于是"项目小可以不加"重新成立）
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("（L1）", "（L2，建议）"))
        cm.check_api_naming_guard()
        self.assertIn("L1", self.error_texts())

    def test_scope_narrowing_removed_reports(self):
        # 反例：范围限定（只此一类接口）被删 → 判定面可被自行放大
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("（跨服务远程调用接口；本次**只此一类**，其他对外接口如 REST Controller、"
                                       "RPC 服务契约接口暂不在本约束内，不按本条改名，也不得据此扩张判定）", ""))
        cm.check_api_naming_guard()
        self.assertIn("只此一类", self.error_texts())

    def test_scope_widened_reports(self):
        # 反例：范围被写宽（用户明确排除的其他对外接口被卷进来）
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("（跨服务远程调用接口；本次**只此一类**，其他对外接口如 REST Controller、"
                                       "RPC 服务契约接口暂不在本约束内，不按本条改名，也不得据此扩张判定）",
                                       "（RPC/服务契约接口等其他对外接口同样适用）"))
        cm.check_api_naming_guard()
        self.assertIn("RPC/服务契约接口", self.error_texts())

    def test_precedent_priority_removed_reports(self):
        # 反例：'优先用已有的固定前缀'（先例优先）被抽掉 → 等于要求每个接口现场发明一套前缀
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("**先取该域已有的固定前缀（先例优先），", "")
                   .replace("先例优先", ""))
        cm.check_api_naming_guard()
        self.assertIn("先例优先", self.error_texts())

    def test_examples_removed_reports(self):
        # 反例（关键词堆砌式假绿）：实例被抽掉 → 读者无法判断自己是否命中
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   "= 通用编码规范\n\n== 命名与代码质量\n"
                   "* Feign 接口命名带所属域/项目前缀（L1）：只此一类，其他对外接口不适用。"
                   "前缀取已有固定前缀、先例优先；判定：同一项目内不一致属违规。"
                   "Feign 接口固定后缀 `Api`。\n")
        cm.check_api_naming_guard()
        self.assertIn("UcUserApi", self.error_texts())

    def test_java_stack_missing_reports(self):
        # 反例：Java 栈落点缺失 → Java 执行者按栈文件学仍会随手取名
        self._write_valid()
        os.remove(cm.JAVA_STACK_FILE)
        cm.check_api_naming_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_java_stack_not_pointing_general_reports(self):
        # 反例：栈层只写实例、不指向通用条 → 判据与反例在栈层读不到
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   "= Java 规范\n\n== 命名\n* Feign 接口：`UcUserApi`、`OucUserApi`。\n")
        cm.check_api_naming_guard()
        self.assertIn("coding.adoc", self.error_texts())

    def test_dispatcher_not_registered_reports(self):
        # 反例：调度器两处识别特征被删 → 该条永远不会被触发加载（写了等于没写）
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
                   "  ** 编写代码 → link:specs/general/coding.adoc[]\n")
        cm.check_api_naming_guard()
        self.assertIn("Feign 接口命名", self.error_texts())

    def test_dispatcher_scope_marker_removed_reports(self):
        # 反例：调度器只剩条名、范围标注被删 → 会被读成适用于所有接口
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
                   "  ** 编写代码 → link:specs/general/coding.adoc[]"
                   "（含**「Feign 接口命名带所属域/项目前缀」**）\n"
                   "  ** Java 项目 → link:specs/stack/java.adoc[]（**Feign 接口命名**）\n")
        cm.check_api_naming_guard()
        self.assertIn("只此一类", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例：README 目录说明未同步 → 公开面看不到这条
        self._write_valid()
        self.write("README.adoc", "# README\n\n## 目录结构\n* 技术栈层：java\n")
        cm.check_api_naming_guard()
        self.assertIn("接口命名", self.error_texts())

    def test_library_basis_missing_reports(self):
        # 反例：图书馆依据落点缺该条（依据只剩名称）
        self._write_valid()
        self.write("library/sources.adoc", "= 图书馆依据\n\n== 别的主题\n* 略。\n")
        cm.check_api_naming_guard()
        self.assertIn("library/sources.adoc", self.error_texts())

    def test_library_scope_note_removed_reports(self):
        # 反例：图书馆依据未写明只取 Feign 这一类 → 依据被读成通用命名规则
        self._write_valid()
        self.write("library/sources.adoc",
                   "= 图书馆依据\n\n== Feign 接口命名带所属域前缀（Spring Cloud）\n"
                   "* 说明：要点转述、非逐字摘录；本仓库**未逐字取回**。\n")
        cm.check_api_naming_guard()
        self.assertIn("只需要考虑 feign", self.error_texts())


class TestCheckApiContractReuseGuard(CheckSpecsTestCase):
    """钉住『请求/响应类优先移动复用 + HTTP 接口路径优先中划线』防线。

    两条都来自用户的一次要求：给已有接口加 Feign 内部接口时**优先移动请求/响应类、不新建**（例外只有
    数据库实体类与"类里引用了第三方类型"，且**本项目自身的依赖不算三方依赖**）；**feign 接口地址优先使用中划线**。

    最易被四件事冲掉：
      * **条文被删或降级成建议** —— "另建一套更省事"重回默认做法；
      * **例外与边界被写宽/抽掉** —— 尤其"本项目自身的依赖不算三方依赖"这条边界，缺位即等于给出一个
        随时可套用的豁免口（"它依赖本项目别的模块"就能另建一套）；
      * **路径条被删或退回下划线/驼峰** —— 同一项目两种风格并存；
      * **路径条被搬到通用层** —— 通用层会出现只在 Web 框架语境下有定义的判据（协议/框架专名污染）。
    故本组用例覆盖：条文缺失 / L1 降级 / 边界字句被抽 / 移动动作被抽 / 判定标准被抽 / 路径条缺失或降级 /
    两处照旧被删 / 路径条被写进通用层 / 调度器两处识别特征缺失 / README 未同步 / 图书馆依据缺失。
    """

    CODING = (
        "= 通用编码规范\n\n== 代码复用\n"
        "* **跨服务/对外调用的请求响应类优先移动复用，不新建（L1）**：给**已有的接口**增加**新的内部调用接口**"
        "（如 Feign 等声明式 HTTP 客户端）时，**优先把**该接口所需的**请求/响应类移动**到新接口所属的位置并**沿用**，"
        "**不得**为它另写一套同名同构的类。**移动而非复制**：移动后同步更新全部引用；"
        "**不得**一处移动、一处留副本。**两种例外**：①**数据库实体类**——除用户明确声明允许外一律**不移动**；"
        "②**引用了第三方类型**的类。**边界：本项目自身的依赖不算三方依赖**——由本项目自己的**其他模块**提供的类型"
        "仍属可一起移动。**判定标准（任一命中即违规）**：①另建新建的请求/响应类而项目内已有等价同类；"
        "②该新建类与既有类**同名或仅差包名**；③只**复制**既有类而不改原引用；"
        "④以「它依赖本项目的其他模块」为由拒绝移动；⑤**移动了数据库实体类**而没有用户声明。"
        "存量随动迁移（不发动全库改造）。依据：ISO/IEC 25010 可维护性。\n"
    )

    SPRING = (
        "= Spring 规范（技术栈层）\n\n== 分层与职责\n"
        "* **HTTP 接口路径优先用中划线（kebab-case）（L1）**：路由路径的**路径片段**须用小写 + 中划线（`-`），"
        "**不得**用下划线（`_`）或驼峰/大写。**两处照旧**：①**服务路由前缀/网关前缀**；"
        "②**已发布、外部依赖的对外路径**。**判定标准**：①路径里出现 `_`；②路径片段用驼峰/大写；"
        "③同一接口内两种风格混用。存量路径按「规范变更的存量处理」随动迁移。"
        "**与命名规则的分工**：本条只管**路径字符串**，类名命名按 link:java.adoc[]「命名」。"
        "依据：RFC 3986。\n"
    )

    GENERIC = (
        "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
        "  ** 编写代码 → link:specs/general/coding.adoc[]（含**「跨服务调用的请求响应类优先移动复用」**："
        "给已有接口加内部调用接口（如 Feign）时，请求/响应类**优先移动沿用、不新建**"
        "（例外只两类：数据库实体类除声明外不移动、类里引用了第三方类型；**本项目自身的依赖不算三方依赖**）；"
        "检测特征：加接口时另建请求/响应类）\n"
        "  ** Spring 项目 → link:specs/stack/spring.adoc[]（**HTTP 接口路径优先用中划线**："
        "路由路径片段用小写 + `-`，不得用 `_` 或驼峰；检测特征：写/改路由路径）\n"
    )

    README = "# README\n\n## 目录结构\n* 通用层：请求响应类优先移动复用\n* 技术栈层：接口路径优先用中划线\n"

    SOURCES = (
        "= 图书馆依据\n\n== HTTP 接口路径的命名风格（RFC 3986）\n"
        "* **须注意的语义差异（同义性）**：标准只给方向与下限，判据化取值属本集合取舍。\n"
        "\n== 请求/响应类的复用与跨模块移动（ISO/IEC 25010 可维护性）\n"
        "* **须注意的语义差异（同义性）**：例外清单属本集合自己的取舍。\n"
    )

    ADOPTION = (
        "= 图书馆：本集合自身取舍\n\n== 同义性差异与覆盖点\n"
        "* **请求/响应类优先移动复用、HTTP 接口路径优先中划线（L1）两条均为本集合自己的判据化取舍**：略。\n"
    )

    def setUp(self) -> None:
        super().setUp()
        self._orig_coding = cm.CODING_FILE
        self._orig_spring = cm.SPRING_STACK_FILE
        self._orig_generic = cm.GENERIC_FILE
        self._orig_readme = cm.README_FILE
        cm.CODING_FILE = os.path.join(self.root, "specs", "general", "coding.adoc")
        cm.SPRING_STACK_FILE = os.path.join(self.root, "specs", "stack", "spring.adoc")
        cm.GENERIC_FILE = os.path.join(self.root, "AGENTS_COMMON.adoc")
        cm.README_FILE = os.path.join(self.root, "README.adoc")

    def tearDown(self) -> None:
        (cm.CODING_FILE, cm.SPRING_STACK_FILE, cm.GENERIC_FILE,
         cm.README_FILE) = (self._orig_coding, self._orig_spring, self._orig_generic,
                            self._orig_readme)
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("specs/general/coding.adoc", self.CODING)
        self.write("specs/stack/spring.adoc", self.SPRING)
        self.write("AGENTS_COMMON.adoc", self.GENERIC)
        self.write("README.adoc", self.README)
        self.write("library/sources.adoc", self.SOURCES)
        self.write("library/adoption.adoc", self.ADOPTION)

    def test_valid_guard_passes(self):
        self._write_valid()
        cm.check_api_contract_reuse_guard()
        self.assertEqual(cm.errors, [])

    def test_clause_deleted_reports(self):
        # 反例：通用层条文被删 → "另建一套更省事"重回默认做法
        self._write_valid()
        self.write("specs/general/coding.adoc", "= 通用编码规范\n\n== 代码复用\n* 复用。\n")
        cm.check_api_contract_reuse_guard()
        self.assertIn("跨服务/对外调用的请求响应类优先移动复用", self.error_texts())

    def test_level_downgraded_reports(self):
        # 反例：L1 被降级成建议
        self._write_valid()
        self.write("specs/general/coding.adoc", self.CODING.replace("（L1）", "（L2，建议）"))
        cm.check_api_contract_reuse_guard()
        self.assertIn("L1", self.error_texts())

    def test_dependency_boundary_removed_reports(self):
        # 反例：'本项目自身的依赖不算三方依赖'被抽掉 → 给出一个随时可套用的豁免口
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("**边界：本项目自身的依赖不算三方依赖**——", "")
                   .replace("本项目自身的依赖不算三方依赖", ""))
        cm.check_api_contract_reuse_guard()
        self.assertIn("本项目自身的依赖不算三方依赖", self.error_texts())

    def test_move_action_removed_reports(self):
        # 反例：'移动而非复制、同步更新全部引用'被抽 → 只剩"别新增"一句口号
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("**移动而非复制**：移动后同步更新全部引用；", ""))
        cm.check_api_contract_reuse_guard()
        self.assertIn("移动而非复制", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例（关键词堆砌式假绿）：判定标准被抽掉 → 无法判定是否命中
        self._write_valid()
        self.write("specs/general/coding.adoc", self.CODING.split("**判定标准")[0])
        cm.check_api_contract_reuse_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_spring_clause_deleted_reports(self):
        # 反例：路径条被删 → 下划线与驼峰混用重回默认做法
        self._write_valid()
        self.write("specs/stack/spring.adoc", "= Spring 规范\n\n== 分层与职责\n* 分层。\n")
        cm.check_api_contract_reuse_guard()
        self.assertIn("HTTP 接口路径优先用中划线（kebab-case）", self.error_texts())

    def test_spring_existing_paths_exception_removed_reports(self):
        # 反例：两处照旧（服务路由前缀、已发布对外路径）被抽掉 → 会被读成"所有路径都要改名"
        self._write_valid()
        self.write("specs/stack/spring.adoc",
                   self.SPRING.replace("**两处照旧**：①**服务路由前缀/网关前缀**；"
                                       "②**已发布、外部依赖的对外路径**。", ""))
        cm.check_api_contract_reuse_guard()
        self.assertIn("服务路由", self.error_texts())

    def test_path_clause_in_general_layer_reports(self):
        # 反例：路径条被放进通用层 → 只在 Web 框架语境下有定义的判据污染非 Web 项目
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING + "* HTTP 接口路径优先用中划线：路径片段用小写 + `-`。\n")
        cm.check_api_contract_reuse_guard()
        self.assertIn("coding.adoc", self.error_texts())

    def test_dispatcher_general_entry_not_pointing_reports(self):
        # 反例：调度器通用层识别特征被删 → 该条永远不会被触发加载
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
                   "  ** 编写代码 → link:specs/general/coding.adoc[]\n"
                   "  ** Spring 项目 → link:specs/stack/spring.adoc[]（**HTTP 接口路径优先用中划线**："
                   "路由路径片段用小写 + `-`）\n")
        cm.check_api_contract_reuse_guard()
        self.assertIn("请求响应类优先移动复用", self.error_texts())

    def test_dispatcher_spring_entry_not_pointing_reports(self):
        # 反例：调度器 Spring 条目识别特征被删 → Spring 执行者读不到该条
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
                   "  ** 编写代码 → link:specs/general/coding.adoc[]（含**「跨服务调用的请求响应类优先移动复用」**："
                   "请求/响应类**优先移动沿用、不新建**；**本项目自身的依赖不算三方依赖**）\n"
                   "  ** Spring 项目 → link:specs/stack/spring.adoc[]\n")
        cm.check_api_contract_reuse_guard()
        self.assertIn("接口路径优先用中划线", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例：README 目录说明未同步 → 公开面看不到这两条
        self._write_valid()
        self.write("README.adoc", "# README\n\n## 目录结构\n* 通用层\n")
        cm.check_api_contract_reuse_guard()
        self.assertIn("README", self.error_texts())

    def test_library_basis_missing_reports(self):
        # 反例：图书馆依据落点缺这两条（依据只剩名称）
        self._write_valid()
        self.write("library/sources.adoc", "= 图书馆依据\n\n== 别的主题\n* 略。\n")
        cm.check_api_contract_reuse_guard()
        self.assertIn("library/sources.adoc", self.error_texts())

    def test_adoption_tradeoff_missing_reports(self):
        # 反例：'本集合自己承认的更严取舍'未登记 → 读者会把两条读成标准规定
        self._write_valid()
        self.write("library/adoption.adoc", "= 图书馆：本集合自身取舍\n\n== 同义性差异与覆盖点\n* 别的取舍。\n")
        cm.check_api_contract_reuse_guard()
        self.assertIn("library/adoption.adoc", self.error_texts())


class TestCheckPersistenceAccessGuard(CheckSpecsTestCase):
    """钉住『持久化访问防线』（通用层抽象 / 技术栈层框架专名）。

    该条对应用户明确提出的硬性要求：**强制使用 `IService` 的成员方法
    `lambdaQuery()`/`lambdaUpdate()`/`ktQuery()`/`ktUpdate()`，除非无法替代，否则禁止
    `new QueryWrapper` 及其子类**。用户报告的失效形态：Service 已经
    `extends ServiceImpl<XxxMapper, Xxx>`，业务代码里却仍 `new QueryWrapper<>()` /
    `new LambdaQueryWrapper<>()` 拼条件——同一项目并存两套写法；非 Lambda 形态还用
    **字符串写列名**（`eq("user_name", ...)`），编译期查不出、改名即静默失效。

    分层口径（用户追加要求"coding.adoc 是通用规范，不应写入 mybatis plus"）：通用层只留
    **跨语言抽象**（三条 L1 + 抽象判定标准 + 例外 + 存量），**框架专名与禁止清单的唯一落点**
    是 `specs/stack/java.adoc`（不新开 `mybatis.adoc`）。

    最易被五件事冲掉（故本组用例逐一覆盖）：
      * **条文被删或降级成建议** —— `new` 构造器重回默认做法；
      * **禁止面被放宽** —— 只禁非 Lambda 形态、漏掉"同样类型安全但仍绕过入口"的
        `new LambdaQueryWrapper`（用户要求是"及其子类"）；
      * **技术栈落点缺失** —— Java 执行者按栈文件学，通用层有、栈层没有等于没写；
      * **通用层被框架专名污染** —— `coding.adoc` 里点名 `IService`/`QueryWrapper`，
        对非 Java 项目不成立、又白占其上下文；
      * **调度器识别特征被删或未去专名** —— 该条永远不会被触发加载（写了等于没写），
        或非 Java 项目也被带入 MyBatis-Plus 术语。
    """

    CODING = (
        "= 通用编码规范\n\n"
        "== 持久化访问（数据库/缓存等）\n"
        "访问数据库、缓存等持久化存储时，一律走所属技术已提供的类型安全/声明式查询构造 API"
        "与其统一入口。\n"
        "* **统一入口（L1）**：持久化操作须经该技术约定的统一访问入口调用（该技术承载"
        "查询/更新的既有抽象），不自建构造器。\n"
        "* **优先用类型安全/声明式查询构造 API（L1）**：以方法引用/属性名引用表达列名、"
        "以声明式方法名表达查询（`findByXxx` 一类）；禁止用字符串写列名表名的构造方式。\n"
        "* **替代优先（L1）**：技术自带替代写法时强制使用，只在该形态表达不了所需语义时才退回"
        "通用构造器，且须写明理由。\n"
        "* **判定标准（任一命中即违规）**：①出现技术自带构造器的直接 `new`；②列名以字符串写进"
        "查询构造；③绕过统一入口自建查询构造。\n"
        "* **例外与边界（L2）**：不禁止「跨语言执行脚本的落点」所指的映射文件承载。\n"
        "* **存量边界**：按「规范变更的存量处理」随动迁移。\n"
        "* 依据（标准名/编号）：ISO/IEC 25010、ISO/IEC/IEEE 29148。\n"
        "\n== 跨语言执行脚本的落点（资源文件夹，不写字符串拼接/模板）\n"
        "* 略。\n"
    )

    JAVA = (
        "= Java 规范（技术栈层）\n\n"
        "== 持久化访问（MyBatis-Plus / JPA 等）\n"
        "持久化访问按通用编码规范的「持久化访问（数据库/缓存等）」执行（见 "
        "link:../general/coding.adoc[]）；框架专名与禁止清单如下：\n"
        "* **MyBatis-Plus 强制使用 `IService` 的成员方法（L1）**：查询/更新一律走 `lambdaQuery()`、"
        "`lambdaUpdate()`、`ktQuery()`、`ktUpdate()`；禁止 `new QueryWrapper<>()`、"
        "`new UpdateWrapper<>()` 及其子类（含 `new LambdaQueryWrapper<>()`）。\n"
        "* **`IService` 之外的落点（L1）**：用 `Wrappers` 的 lambda 静态方法或 Mapper 接口上的"
        "注解/映射文件声明。\n"
        "* **例外（L2，须写清理由）**：确需 Wrapper 子类时在 Mapper 接口封装一次，业务侧不 new。\n"
        "* **判定标准（任一命中即违规）**：①构造器 `new`；②列名以字符串写进查询构造"
        "（可用方法引用表达时）；③绕过 `IService` 另起一套访问写法。\n"
        "* **存量**按 link:../core/execution.adoc[]「规范变更的存量处理」随动迁移。\n"
    )

    GENERIC = (
        "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
        "  ** 编写代码 → link:specs/general/coding.adoc[]（含**「持久化访问（数据库/缓存等）」**："
        "走该技术给定的**统一入口**，禁止字符串写列名表名的构造方式；具体技术的入口与"
        "禁止清单见 link:specs/stack/java.adoc[] 等栈文件）\n"
        "  ** Java 项目（存在 `.java`）→ link:specs/stack/java.adoc[]（**MyBatis-Plus 持久化访问**："
        "强制走 `IService` 的 `lambdaQuery()`/`ktQuery()`，禁止 `new QueryWrapper` 及其子类）\n"
    )

    def setUp(self) -> None:
        super().setUp()
        self._orig_coding = cm.CODING_FILE
        self._orig_java = cm.JAVA_STACK_FILE
        self._orig_generic = cm.GENERIC_FILE
        self._orig_readme = cm.README_FILE
        cm.CODING_FILE = os.path.join(self.root, "specs", "general", "coding.adoc")
        cm.JAVA_STACK_FILE = os.path.join(self.root, "specs", "stack", "java.adoc")
        cm.GENERIC_FILE = os.path.join(self.root, "AGENTS_COMMON.adoc")
        cm.README_FILE = os.path.join(self.root, "README.adoc")

    def tearDown(self) -> None:
        (cm.CODING_FILE, cm.JAVA_STACK_FILE, cm.GENERIC_FILE,
         cm.README_FILE) = (self._orig_coding, self._orig_java, self._orig_generic,
                            self._orig_readme)
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("specs/general/coding.adoc", self.CODING)
        self.write("specs/stack/java.adoc", self.JAVA)
        self.write("AGENTS_COMMON.adoc", self.GENERIC)
        self.write("README.adoc", "# README\n\n## 目录结构\n* 通用层：含**持久化访问**：统一入口 + 类型安全构造\n")

    def test_valid_persistence_guard_passes(self):
        self._write_valid()
        cm.check_persistence_access_guard()
        self.assertEqual(cm.errors, [])

    def test_clause_deleted_reports(self):
        # 反例：通用层条文被删 → "随手 new 构造器"重回默认做法
        self._write_valid()
        self.write("specs/general/coding.adoc", "= 通用编码规范\n\n== 代码复用\n* 略。\n")
        cm.check_persistence_access_guard()
        self.assertIn("持久化访问（数据库/缓存等）", self.error_texts())

    def test_level_downgraded_reports(self):
        # 反例：统一入口被降级成建议（读起来无害，于是"偶尔 new 一下"重新成立）
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("**统一入口（L1）**", "**统一入口（L2，建议）**"))
        cm.check_persistence_access_guard()
        self.assertIn("统一入口（L1）", self.error_texts())

    def test_alternative_priority_removed_reports(self):
        # 反例：'替代优先'条被删 → "无法替代"的边界无处可判、禁止面可以被读成"看情况"
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("**替代优先（L1）**", "**补充说明**")
                   .replace("替代优先（L1）", "补充说明"))
        cm.check_persistence_access_guard()
        self.assertIn("替代优先（L1）", self.error_texts())

    def test_judgement_standard_removed_reports(self):
        # 反例：判定标准被删 → 只剩一句口径、无法判定是否命中
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("* **判定标准（任一命中即违规）**：①出现技术自带构造器的直接 "
                                       "`new`；②列名以字符串写进"
                                       "查询构造；③绕过统一入口自建查询构造。\n", ""))
        cm.check_persistence_access_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_general_layer_framework_name_reports(self):
        # 反例：通用层点名框架专名 → 对非 Java 项目不成立（替换主语测试失败）、白占其上下文
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("**优先用类型安全/声明式查询构造 API（L1）**：以方法引用/属性名引用表达列名、",
                                       "**优先用类型安全/声明式查询构造 API（L1）**：优先用 `IService` 的 `lambdaQuery()`、"))
        cm.check_persistence_access_guard()
        self.assertIn("IService", self.error_texts())

    def test_general_layer_wrapper_name_reports(self):
        # 反例：通用层把具体禁止清单（Wrapper 类名）写进来 → 专名归技术栈层
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("③绕过统一入口自建查询构造。",
                                       "③出现 `new QueryWrapper` 或 `new LambdaQueryWrapper`。"))
        cm.check_persistence_access_guard()
        self.assertIn("QueryWrapper", self.error_texts())

    def test_java_stack_missing_reports(self):
        # 反例：Java 栈落点缺失 → Java 执行者按栈文件学仍会随手 new
        self._write_valid()
        os.remove(cm.JAVA_STACK_FILE)
        cm.check_persistence_access_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_kt_methods_removed_reports(self):
        # 反例：Kotlin 的 kt* 成员方法被漏掉 → Kotlin 项目学不全、更新侧无落点
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   self.JAVA.replace("`lambdaUpdate()`、`ktQuery()`、`ktUpdate()`", "`lambdaUpdate()`"))
        cm.check_persistence_access_guard()
        self.assertIn("ktQuery", self.error_texts())

    def test_lambda_wrapper_subclass_allowed_reports(self):
        # 反例：禁止面被放宽成"只禁非 Lambda 形态" → 用户明确要求的"及其子类"被丢掉
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   self.JAVA.replace("、`new UpdateWrapper<>()` 及其子类（含 `new LambdaQueryWrapper<>()`）", ""))
        cm.check_persistence_access_guard()
        self.assertIn("子类", self.error_texts())

    def test_exception_clause_removed_reports(self):
        # 反例：例外条被删 → "无法替代"时执行者无处可去，只能继续 new
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   self.JAVA.replace("* **例外（L2，须写清理由）**：确需 Wrapper 子类时在 Mapper 接口"
                                     "封装一次，业务侧不 new。\n", ""))
        cm.check_persistence_access_guard()
        self.assertIn("例外（L2", self.error_texts())

    def test_iservice_alternative_removed_reports(self):
        # 反例：IService 之外的落点（Wrappers / mapper 注解）被删 → 无可替代时无路可走
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   self.JAVA.replace("`Wrappers` 的 lambda 静态方法或 Mapper 接口上的", "框架提供的方法或"))
        cm.check_persistence_access_guard()
        self.assertIn("Wrappers", self.error_texts())

    def test_dispatcher_registration_removed_reports(self):
        # 反例：调度器识别特征被删 → 该条永远不会被触发加载
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
                   "  ** 编写代码 → link:specs/general/coding.adoc[]\n"
                   "  ** Java 项目 → link:specs/stack/java.adoc[]\n")
        cm.check_persistence_access_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_dispatcher_java_entry_marker_removed_reports(self):
        # 反例：Java 栈登记只剩条名、成员方法与禁止面被删 → Java 项目看不到判据
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
                   "  ** 编写代码 → link:specs/general/coding.adoc[]（含**「持久化访问（数据库/缓存等）」**："
                   "走该技术给定的**统一入口**）\n"
                   "  ** Java 项目（存在 `.java`）→ link:specs/stack/java.adoc[]（**MyBatis-Plus 持久化访问**）\n")
        cm.check_persistence_access_guard()
        self.assertIn("lambdaQuery", self.error_texts())

    def test_dispatcher_general_entry_framework_name_reports(self):
        # 反例：通用层调度条目仍带框架专名 → 非 Java 项目也被带入 MyBatis-Plus 术语、与归属层冲突
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
                   "  ** 编写代码 → link:specs/general/coding.adoc[]（含**「持久化访问（数据库/缓存等）」**："
                   "走该技术给定的**统一入口**，强制走 `IService` 的 `lambdaQuery()`）\n"
                   "  ** Java 项目（存在 `.java`）→ link:specs/stack/java.adoc[]（**MyBatis-Plus 持久化访问**："
                   "强制走 `IService` 的 `lambdaQuery()`/`ktQuery()`，禁止 `new QueryWrapper` 及其子类）\n")
        cm.check_persistence_access_guard()
        self.assertIn("IService", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例：README 目录说明未同步 → 公开面看不到这条
        self._write_valid()
        self.write("README.adoc", "# README\n\n## 目录结构\n* 通用层：通用编码\n")
        cm.check_persistence_access_guard()
        self.assertIn("持久化访问", self.error_texts())


class TestCheckConversionGuard(CheckSpecsTestCase):
    """钉住『对象转换防线』（通用层抽象 / 技术栈层框架专名 / **建议层口径**）。

    该条对应用户提出的规范建议：**多层嵌套对象转换时，优先使用 mapstruct（jvm 下），
    不允许手写转换代码——不是强制，但是建议**。用户报告的失效形态：对象含对象、集合含对象时
    **手写逐字段搬运**（一层层 `new` + 逐个 `set`/`get`）——没有编译期保障，模型加字段后只在
    运行期表现为"某个字段一直是空"。

    分层口径（与「持久化访问」同一套）：通用层只留**跨语言抽象**（优先声明式映射、目标式判据、
    范围、例外、存量），**框架专名与写法的唯一落点**是 `specs/stack/java.adoc`「对象转换
    （MapStruct）」（就地承载，不新开 `mapstruct.adoc`）。

    本防线**按建议层口径钉住**（不是强制面）——用户明确要求不做强制性限制，故最易被五件事冲掉：
      * **优先路径被删** —— 退回"怎么顺手怎么写"；
      * **被写成强制面** —— "不允许手写转换代码""一律"重新出现，与用户口径相抵；
      * **范围被抄窄或抽掉** —— 无嵌套（单层）不管被抄成"两三字段以内不管"；
      * **备注原因 / 等价路径合规被删** —— "手写须写理由"丢失、"必须用某个库"复辟；
      * **通用层被框架专名污染** —— `coding.adoc` 里点名 `MapStruct`/`@Mapper`，
        对非 JVM 项目不成立、又白占其上下文。
    """

    CODING = (
        "= 通用编码规范\n\n"
        "== 对象转换（多层嵌套对象的转换）\n"
        "多层嵌套对象的转换，**首选声明式映射完成的转换**；**无嵌套（单层）的转换不在本条范围内**。\n"
        "* **首选声明式映射（L2）**：转换**优先**由转换库的映射声明完成。**优先路径不是唯一解**："
        "深拷贝/结构复制工具、序列化（如 JSON）中转、手工构建器等等价路径同样合规，判据按下条。\n"
        "* **达标判据（本条判定的是结果，不是手段）**：同一份转换**只有一处来源**；该结构增删字段、"
        "改字段时，转换处**不会静默漏字段**。手写逐字段搬运在多层嵌套下达不到该判据。\n"
        "* **除主动声明外，优先声明式映射；确需手写时须备注原因（L2）**：人来主动声明允许手写的按声明写；"
        "否则优先走声明式映射，确需手写时在**代码注释写明原因**。本条**不设强制面**。\n"
        "* **映射声明的落点**：映射声明与转换方法独立成文件、不塞进纯数据结构类。\n"
        "* **例外与边界（L2）**：①映射声明表达不了的语义不在本条适用，可在映射声明内以自定义方法承接；"
        "②**无嵌套（单层）的转换不在本条范围内**（与字段数量无关）。\n"
        "* **存量边界**：按「规范变更的存量处理」随动迁移。\n"
        "* 依据（标准名/编号）：ISO/IEC 25010、ISO/IEC/IEEE 29148。\n"
        "\n== 代码复用\n* 略。\n"
    )

    JAVA = (
        "= Java 规范（技术栈层）\n\n"
        "== 对象转换（MapStruct）\n"
        "对象转换按通用编码规范的「对象转换（多层嵌套对象的转换）」执行"
        "（见 link:../general/coding.adoc[]）——JVM 下**优先用 MapStruct**、**建议不手写转换代码**。\n"
        "* **多层嵌套对象转换优先用 MapStruct（L2，建议）**：用 MapStruct 的 `@Mapper` 映射接口声明完成；"
        "**建议不手写转换代码**。**不做强制性限制**——深拷贝/结构复制工具、序列化中转等等价路径同样合规。\n"
        "* **嵌套结构由映射声明表达（写法建议，非强制）**：对象含对象、集合含对象由**映射方法自动调用**"
        "或集合映射方法表达；手写循环不构成违规。\n"
        "* **不并存两套写法（先例优先）**：项目已有转换工具/既有 Converter 先例时跟随先例并在其基础上扩展。\n"
        "* **例外与边界（L2）**：**无嵌套（单层）的转换不在本条范围内**；确需手写时在**代码注释备注原因**。\n"
        "* **存量**按 link:../core/execution.adoc[]「规范变更的存量处理」随动迁移。\n"
    )

    GENERIC = (
        "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
        "  ** 编写代码 → link:specs/general/coding.adoc[]（含**「对象转换（多层嵌套对象的转换）」**："
        "多层嵌套对象之间的转换（对象含对象/集合含对象的字段搬运、逐层 `new` 组装、手写循环转换））\n"
        "  ** Java 项目（存在 `.java`）→ link:specs/stack/java.adoc[]（**对象转换**："
        "多层嵌套对象转换**优先用 MapStruct**、**建议不手写转换代码**）\n"
    )

    README = ("# README\n\n## 目录结构\n* 通用层：含**对象转换**：多层嵌套对象转换优先用声明式映射、"
              "建议不手写逐字段搬运\n* 技术栈层：java（含**对象转换**：优先 MapStruct、建议不手写）\n")

    SOURCES = (
        "= 图书馆依据\n\n== 多层嵌套对象转换用声明式映射（MapStruct）\n"
        "* 说明：此条为要点转述、非逐字摘录；本仓库**未逐字取回**官方原文。\n"
        "* **须注意的语义差异（同义性）**：材料未规定必须用某库、也未规定禁止手写转换；"
        "判据化取值属本集合的取向。\n"
    )

    ADOPTION = (
        "= 规范准入与自身取舍\n\n== 同义性差异与覆盖点（本集合自己承认的）\n"
        "* **多层嵌套对象转换优先声明式映射、JVM 下优先 MapStruct**是本集合自己的取向（**建议、非强制**）："
        "用户要求「优先使用 mapstruct（jvm下），不允许手动写转换代码——不是强制，但是建议」。\n"
    )

    def setUp(self) -> None:
        super().setUp()
        self._orig_coding = cm.CODING_FILE
        self._orig_java = cm.JAVA_STACK_FILE
        self._orig_generic = cm.GENERIC_FILE
        self._orig_readme = cm.README_FILE
        cm.CODING_FILE = os.path.join(self.root, "specs", "general", "coding.adoc")
        cm.JAVA_STACK_FILE = os.path.join(self.root, "specs", "stack", "java.adoc")
        cm.GENERIC_FILE = os.path.join(self.root, "AGENTS_COMMON.adoc")
        cm.README_FILE = os.path.join(self.root, "README.adoc")

    def tearDown(self) -> None:
        (cm.CODING_FILE, cm.JAVA_STACK_FILE, cm.GENERIC_FILE,
         cm.README_FILE) = (self._orig_coding, self._orig_java, self._orig_generic,
                            self._orig_readme)
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("specs/general/coding.adoc", self.CODING)
        self.write("specs/stack/java.adoc", self.JAVA)
        self.write("AGENTS_COMMON.adoc", self.GENERIC)
        self.write("README.adoc", self.README)
        self.write("library/sources.adoc", self.SOURCES)
        self.write("library/adoption.adoc", self.ADOPTION)

    def test_valid_conversion_guard_passes(self):
        self._write_valid()
        cm.check_conversion_guard()
        self.assertEqual(cm.errors, [])

    def test_clause_deleted_reports(self):
        # 反例①：通用层条文被删 → 退回"怎么顺手怎么写"
        self._write_valid()
        self.write("specs/general/coding.adoc", "= 通用编码规范\n\n== 代码复用\n* 略。\n")
        cm.check_conversion_guard()
        self.assertIn("对象转换（多层嵌套对象的转换）", self.error_texts())

    def test_preferred_path_removed_reports(self):
        # 反例②：优先路径被抽掉（只剩范围与例外）→ 该条失去取向
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("**首选声明式映射完成的转换**",
                                       "**由映射声明完成的转换**")
                   .replace("* **首选声明式映射（L2）**", "* **声明式映射（L2）**"))
        cm.check_conversion_guard()
        self.assertIn("首选声明式映射", self.error_texts())

    def test_forced_wording_reports(self):
        # 反例③：条文被写成强制面（用户口径是"不是强制，但是建议"）
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("**首选声明式映射完成的转换**",
                                       "**一律用既有转换库的声明式映射完成，不允许手写转换代码**"))
        cm.check_conversion_guard()
        self.assertIn("不允许手写转换代码", self.error_texts())

    def test_goal_judgement_removed_reports(self):
        # 反例④：目标式判据被删 → 判据退回"用没用某个库"
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("* **达标判据（本条判定的是结果，不是手段）**：同一份转换**只有一处来源**；"
                                       "该结构增删字段、改字段时，转换处**不会静默漏字段**。"
                                       "手写逐字段搬运在多层嵌套下达不到该判据。\n", ""))
        cm.check_conversion_guard()
        self.assertIn("达标判据", self.error_texts())

    def test_comment_reason_removed_reports(self):
        # 反例⑤：备注原因被删 → "手写须写理由"这一动作丢失
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("* **除主动声明外，优先声明式映射；确需手写时须备注原因（L2）**："
                                       "人来主动声明允许手写的按声明写；"
                                       "否则优先走声明式映射，确需手写时在**代码注释写明原因**。"
                                       "本条**不设强制面**。\n", ""))
        cm.check_conversion_guard()
        self.assertIn("备注原因", self.error_texts())

    def test_equivalent_path_removed_reports(self):
        # 反例⑥：等价路径合规被删 → 该条易被读成"必须用某个库"
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("**优先路径不是唯一解**："
                                       "深拷贝/结构复制工具、序列化（如 JSON）中转、手工构建器等等价路径同样合规，"
                                       "判据按下条。", ""))
        cm.check_conversion_guard()
        self.assertIn("等价路径同样合规", self.error_texts())

    def test_scope_by_field_count_reports(self):
        # 反例⑦：范围被抄窄成按字段数判（用户口径是"无嵌套（单层）不管"）
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("**无嵌套（单层）的转换不在本条范围内**",
                                       "**单层、两三个字段的转换不在本条强制面**"))
        cm.check_conversion_guard()
        self.assertIn("字段", self.error_texts())

    def test_exception_clause_removed_reports(self):
        # 反例⑧：例外条被删 → 既有做法被一刀切
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("* **例外与边界（L2）**：①映射声明表达不了的语义不在本条适用，"
                                       "可在映射声明内以自定义方法承接；"
                                       "②**无嵌套（单层）的转换不在本条范围内**（与字段数量无关）。\n", ""))
        cm.check_conversion_guard()
        self.assertIn("例外与边界（L2", self.error_texts())

    def test_general_layer_framework_name_reports(self):
        # 反例⑨：通用层点名 MapStruct → 对非 JVM 项目不成立（替换主语测试失败）
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("由转换库的映射声明完成。", "由 MapStruct 的 `@Mapper` 映射声明完成。"))
        cm.check_conversion_guard()
        self.assertIn("MapStruct", self.error_texts())

    def test_java_stack_missing_reports(self):
        # 反例⑩：Java 栈落点缺失 → Java 执行者按栈文件学仍会手写转换
        self._write_valid()
        os.remove(cm.JAVA_STACK_FILE)
        cm.check_conversion_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_java_stack_not_pointing_general_reports(self):
        # 反例⑪：栈层不指向通用条 → 通用层判据与例外在栈层读不到
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   "= Java 规范\n\n== 对象转换（MapStruct）\n"
                   "* 多层嵌套对象转换优先用 MapStruct、建议不手写转换代码。\n")
        cm.check_conversion_guard()
        self.assertIn("coding.adoc", self.error_texts())

    def test_java_stack_forced_wording_reports(self):
        # 反例⑫：栈层回退成强制面（"不允许手写转换代码"）→ 与用户口径相抵
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   self.JAVA.replace("**建议不手写转换代码**。**不做强制性限制**",
                                     "**不允许手写转换代码**"))
        cm.check_conversion_guard()
        self.assertIn("不允许手写转换代码", self.error_texts())

    def test_java_stack_nesting_clause_removed_reports(self):
        # 反例⑬：嵌套/集合由映射方法表达的推荐写法被删 → 多层嵌套靶心无处落
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   self.JAVA.replace("* **嵌套结构由映射声明表达（写法建议，非强制）**：对象含对象、"
                                     "集合含对象由**映射方法自动调用**或集合映射方法表达；手写循环不构成违规。\n",
                                     ""))
        cm.check_conversion_guard()
        self.assertIn("映射方法自动调用", self.error_texts())

    def test_dispatcher_registration_removed_reports(self):
        # 反例⑭：调度器识别特征被删 → 该条永远不会被触发加载（写了等于没写）
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
                   "  ** 编写代码 → link:specs/general/coding.adoc[]\n"
                   "  ** Java 项目 → link:specs/stack/java.adoc[]\n")
        cm.check_conversion_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_dispatcher_general_entry_framework_name_reports(self):
        # 反例⑮：通用层调度条目带框架专名 → 非 JVM 项目也被带入该库术语、与归属层冲突
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
                   "  ** 编写代码 → link:specs/general/coding.adoc[]（含**「对象转换（多层嵌套对象的转换）」**："
                   "多层嵌套对象之间的转换用 `MapStruct` 的 `@Mapper` 映射接口）\n"
                   "  ** Java 项目（存在 `.java`）→ link:specs/stack/java.adoc[]（**对象转换**："
                   "多层嵌套对象转换**优先用 MapStruct**、**建议不手写转换代码**）\n")
        cm.check_conversion_guard()
        self.assertIn("MapStruct", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例⑯：README 目录说明未同步（或仍写"不允许手写"）→ 公开面口径与条文不一致
        self._write_valid()
        self.write("README.adoc", "# README\n\n## 目录结构\n* 通用层：通用编码\n")
        cm.check_conversion_guard()
        self.assertIn("对象转换", self.error_texts())

    def test_library_basis_missing_reports(self):
        # 反例⑰：图书馆依据落点缺该条（依据只剩名称）
        self._write_valid()
        self.write("library/sources.adoc", "= 图书馆依据\n\n== 别的主题\n* 略。\n")
        cm.check_conversion_guard()
        self.assertIn("library/sources.adoc", self.error_texts())

    def test_library_adoption_note_removed_reports(self):
        # 反例⑱：本集合取向未登记 → 读者会把本集合的建议读成标准规定
        self._write_valid()
        self.write("library/adoption.adoc", "= 规范准入与自身取舍\n\n== 同义性差异\n* 略。\n")
        cm.check_conversion_guard()
        self.assertIn("library/adoption.adoc", self.error_texts())


class TestCheckWiringGuard(CheckSpecsTestCase):
    """钉住『防线接线完整性』：每个 `check_*` 都必须被 main() 真正调用。

    本仓库的实测失效（2026-09 复核 PR #89 时用探针复现）：把任一道防线从 main() 的调用
    序列里摘掉，或新增防线却忘记接线，**check_specs.py 与全部配套测试仍全绿**——
    既有用例都是逐个函数直接调用被测防线，从不经过 main() 的接线路径。本防线把该失效
    变成机械可拦项，此处钉住它自己的正例与两类反例（防它本身失效）。
    """

    def _write_valid(self):
        """造一份"定义了且被 main() 调用"的最小脚本 + 一个合法仓库根。"""
        self.write("script/check_specs.py",
                   "def check_alpha():\n"
                   "    \"\"\"A.\"\"\"\n"
                   "    pass\n\n\n"
                   "def check_beta():\n"
                   "    \"\"\"B.\"\"\"\n"
                   "    pass\n\n\n"
                   "def main(argv=None):\n"
                   "    check_alpha()\n"
                   "    check_beta()\n"
                   "    return 0\n")

    def test_all_wired_passes(self):
        # 正例：定义的防线全部被 main() 调用 → 不报错
        self._write_valid()
        cm.check_wiring_guard()
        self.assertEqual(self.error_texts(), "")

    def test_defined_but_not_wired_reports(self):
        # 反例①：定义了却没在 main() 里调用（"定义了却不执行"）→ 必须报错
        self._write_valid()
        self.write("script/check_specs.py",
                   "def check_alpha():\n"
                   "    \"\"\"A.\"\"\"\n"
                   "    pass\n\n\n"
                   "def check_beta():\n"
                   "    \"\"\"B.\"\"\"\n"
                   "    pass\n\n\n"
                   "def main(argv=None):\n"
                   "    check_alpha()\n"
                   "    return 0\n")
        cm.check_wiring_guard()
        self.assertIn("check_beta", self.error_texts())

    def test_wired_but_undefined_reports(self):
        # 反例②：main() 调用了不存在的防线（接线与实现不一致）→ 必须报错
        self._write_valid()
        self.write("script/check_specs.py",
                   "def check_alpha():\n"
                   "    \"\"\"A.\"\"\"\n"
                   "    pass\n\n\n"
                   "def main(argv=None):\n"
                   "    check_alpha()\n"
                   "    check_gamma()\n"
                   "    return 0\n")
        cm.check_wiring_guard()
        self.assertIn("check_gamma", self.error_texts())

    def test_comment_mention_is_not_wiring(self):
        # 反例③：只有在注释里提到防线名，不构成接线（防"注释里写一句就算接上了"）
        self._write_valid()
        self.write("script/check_specs.py",
                   "def check_alpha():\n"
                   "    \"\"\"A.\"\"\"\n"
                   "    pass\n\n\n"
                   "def check_beta():\n"
                   "    \"\"\"B.\"\"\"\n"
                   "    pass\n\n\n"
                   "def main(argv=None):\n"
                   "    check_alpha()\n"
                   "    # check_beta()\n"
                   "    return 0\n")
        cm.check_wiring_guard()
        self.assertIn("check_beta", self.error_texts())

    def test_nested_wiring_counts(self):
        # 正例：被 main() 直接调用的防线，其体内再调用别的防线也算"被执行到"
        self.write("script/check_specs.py",
                   "def check_alpha():\n"
                   "    \"\"\"A.\"\"\"\n"
                   "    check_beta()\n\n\n"
                   "def check_beta():\n"
                   "    \"\"\"B.\"\"\"\n"
                   "    pass\n\n\n"
                   "def main(argv=None):\n"
                   "    check_alpha()\n"
                   "    return 0\n")
        cm.check_wiring_guard()
        self.assertEqual(self.error_texts(), "")

    def test_missing_script_reports(self):
        # 反例④：连脚本都找不到 → 必须报错，不得静默通过
        cm.check_wiring_guard()
        self.assertIn("check_specs.py", self.error_texts())

    def test_missing_main_reports(self):
        # 反例⑤：脚本没有 main() → 无统一入口，接线无从核对，必须报错
        self.write("script/check_specs.py",
                   "def check_alpha():\n"
                   "    \"\"\"A.\"\"\"\n"
                   "    pass\n")
        cm.check_wiring_guard()
        self.assertIn("main()", self.error_texts())



class TestCheckPromptsIndexGuard(CheckSpecsTestCase):
    """钉住『提示词登记处索引形态』防线（本轮重构新增）。

    背景：`PROMPTS.adoc` 的公共约定原先把 `prompts/_common.txt` 各片段的要点**逐条复述**
    一遍——同一约束两份正文，片段一改这里就漂移。本轮改为**索引**（只写"有哪几个片段、
    每个片段管哪条边界、正文唯一落点在片段里"）。但索引也有反向失效：把某条边界从索引里
    **整条删掉**，复制提示词的人就再也看不到它。

    用例覆盖：①正例（索引形态 + 指向语 + 各片段名齐备）通过；②某条边界的片段名被整条删掉 →
    报错；③没写明"此处只作索引、正文在片段里" → 报错（会被读成全文）；④入口缺失 → 报错。
    """

    INDEX = (
        "= 公共任务提示词（入口）\n\n"
        "== 登记\n"
        "* 公共约定（**展开见 link:prompts/_common.txt[] 的对应片段——此处只作索引，不复述正文**）：\n"
        "** `baseline-and-compat` / `compat`：动手前与改动后的边界。\n"
        "** `scope-boundary`：改动范围边界。\n"
        "** `delivery`：交付边界。\n"
        "** `self-dispatch`：不得自行发评论唤起自己。\n"
        "** 各片段的正文只写在 link:prompts/_common.txt[]（一处维护、两处生效）。\n"
    )

    def setUp(self) -> None:
        super().setUp()
        self._orig_prompts = cm.PROMPTS_FILE
        cm.PROMPTS_FILE = os.path.join(self.root, "PROMPTS.adoc")

    def tearDown(self) -> None:
        cm.PROMPTS_FILE = self._orig_prompts
        super().tearDown()

    def test_valid_index_passes(self):
        self.write("PROMPTS.adoc", self.INDEX)
        cm.check_prompts_index_guard()
        self.assertEqual(cm.errors, [])

    def test_entry_deleted_reports(self):
        # 反例①：把 `self-dispatch`（不得自行发评论唤起自己）整条从登记处删掉 →
        # 复制提示词的人彻底看不到这条边界
        self.write("PROMPTS.adoc", self.INDEX.replace("** `self-dispatch`：不得自行发评论唤起自己。\n", ""))
        cm.check_prompts_index_guard()
        self.assertIn("self-dispatch", self.error_texts())

    def test_scope_entry_deleted_reports(self):
        # 反例②：把 `scope-boundary`（改动范围边界）整条删掉
        self.write("PROMPTS.adoc", self.INDEX.replace("** `scope-boundary`：改动范围边界。\n", ""))
        cm.check_prompts_index_guard()
        self.assertIn("scope-boundary", self.error_texts())

    def test_no_pointer_reports(self):
        # 反例③：只列片段名、没说"正文在片段里、此处只作索引" → 会被读成全文
        self.write("PROMPTS.adoc", self.INDEX.replace("——此处只作索引，不复述正文", "")
                   .replace("** 各片段的正文只写在 link:prompts/_common.txt[]（一处维护、两处生效）。\n", ""))
        cm.check_prompts_index_guard()
        self.assertIn("索引", self.error_texts())

    def test_missing_entry_file_reports(self):
        # 反例④：入口缺失 → 公共约定无处登记，必须报错、不得静默通过
        cm.check_prompts_index_guard()
        self.assertIn("PROMPTS.adoc", self.error_texts())


class TestCheckLombokConstructorGuard(CheckSpecsTestCase):
    """钉住『无参/必参/全参构造优先用 lombok、不手写』（用户提出的规范调整）。

    该条对应"顺手手写构造方法"这一真实失效：类上已标 `@Data`，仍另写无参/全参构造——
    同一构造出现两个来源（字段增删时改一处、另一处静默过期），样板代码遮蔽真实差异。
    最易被三件事冲掉：
      * **降级成建议** —— "尽量用 lombok"读起来无害，于是"手写更直观"重新成立；
      * **三种构造注解只留一半** —— 漏掉 `@RequiredArgsConstructor`（用户明确要求的"必参"
        这一档）后，执行者遇到必参构造无处可依、只能手写；
      * **例外被写宽** —— "注解表达不了"不限定在构造期校验/规范化/防御性拷贝上，
        就变成随时可套用的豁免口。
    故本组用例覆盖"条文被删""降级成建议""注解缺失""例外被抽""调度器/README 未同步"。
    """

    JAVA = (
        "= Java 规范\n"
        "\n"
        "== 编码\n"
        "* **无参 / 必参 / 全参构造优先用 lombok、不手写（L1）**：构造方法一律由 lombok 注解生成，"
        "**不得手写**任何构造方法体或参数列表——\n"
        "** **无参构造**：用 `@NoArgsConstructor`；\n"
        "** **必参构造**：用 `@RequiredArgsConstructor`；\n"
        "** **全参构造**：用 `@AllArgsConstructor`；\n"
        "** **同时需要多个**：**同时标多个构造注解**，各自生成一个。\n"
        "** **判定标准（任一命中即违规）**：①类中出现手写的构造方法，而该构造可由注解表达；"
        "②同一类里手写与 lombok 生成的构造方法并存；③以「lombok 表达不了」为由手写而未写原因。\n"
        "** 例外（L2，须写清理由）**：构造期需要注解表达不了的动作（校验/规范化/防御性拷贝）时，"
        "可手写该构造方法，须在代码**注释**写明原因。**存量**按 link:../core/execution.adoc[]"
        "「规范变更的存量处理」随动迁移。\n"
        "** 依据（标准名/编号）：ISO/IEC 25010（可维护性）；ISO/IEC/IEEE 29148（判定须可验证）。\n"
    )

    def setUp(self) -> None:
        super().setUp()
        self._orig_java = cm.JAVA_STACK_FILE
        self._orig_common = cm.GENERIC_FILE
        self._orig_readme = cm.README_FILE
        cm.JAVA_STACK_FILE = os.path.join(self.root, "specs", "stack", "java.adoc")
        cm.GENERIC_FILE = os.path.join(self.root, "AGENTS_COMMON.adoc")
        cm.README_FILE = os.path.join(self.root, "README.adoc")

    def tearDown(self) -> None:
        (cm.JAVA_STACK_FILE, cm.GENERIC_FILE, cm.README_FILE) = (
            self._orig_java, self._orig_common, self._orig_readme)
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("specs/stack/java.adoc", self.JAVA)
        self.write("AGENTS_COMMON.adoc",
                   "** 构造方法不手写**：无参/必参/全参构造用 lombok 注解"
                   "（`@NoArgsConstructor`/`@RequiredArgsConstructor`/`@AllArgsConstructor`）。\n")
        self.write("README.adoc", "技术栈层：java（含**构造方法不手写**）。\n")

    def test_valid_guard_passes(self):
        self._write_valid()
        cm.check_lombok_constructor_guard()
        self.assertEqual(cm.errors, [])

    def test_clause_deleted_reports(self):
        # 反例：条文被删 → "手写更直观"重回默认做法
        self._write_valid()
        self.write("specs/stack/java.adoc", "= Java 规范\n\n== 编码\n* 强制优先使用 lombok。\n")
        cm.check_lombok_constructor_guard()
        self.assertIn("无参 / 必参 / 全参构造优先用 lombok、不手写", self.error_texts())

    def test_level_downgraded_reports(self):
        # 反例：L1 被降级成建议 → "尽量用 lombok"读起来无害
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   self.JAVA.replace("不手写（L1）", "不手写（L2，建议）"))
        cm.check_lombok_constructor_guard()
        self.assertIn("L1", self.error_texts())

    def test_required_args_annotation_removed_reports(self):
        # 反例：必参构造注解被抽掉（用户明确要求的"必参"这一档）→ 必参构造仍手写
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   self.JAVA.replace("@RequiredArgsConstructor", "省略"))
        cm.check_lombok_constructor_guard()
        self.assertIn("RequiredArgsConstructor", self.error_texts())

    def test_judgement_standard_removed_reports(self):
        # 反例：判定标准被删 → 只剩一句口径、读者无法判断是否命中
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   self.JAVA.replace("** **判定标准（任一命中即违规）**：①类中出现手写的构造方法，"
                                     "而该构造可由注解表达；"
                                     "②同一类里手写与 lombok 生成的构造方法并存；"
                                     "③以「lombok 表达不了」为由手写而未写原因。\n", ""))
        cm.check_lombok_constructor_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_exception_clause_removed_reports(self):
        # 反例：例外条被删 → 既有正当做法（构造期校验）被一刀切
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   self.JAVA.replace("** 例外（L2，须写清理由）**", "** 说明**"))
        cm.check_lombok_constructor_guard()
        self.assertIn("例外", self.error_texts())

    def test_softening_wording_reports(self):
        # 反例（关键词堆砌式假绿）：条文还在，但措辞回退成"尽量/可手写"
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   self.JAVA.replace("**不得手写**任何构造方法体或参数列表",
                                     "尽量用 lombok，可手写构造方法"))
        cm.check_lombok_constructor_guard()
        self.assertIn("回退措辞", self.error_texts())

    def test_java_stack_missing_reports(self):
        # 反例：Java 栈落点缺失 → Java 执行者按栈文件学仍会手写
        self._write_valid()
        os.remove(cm.JAVA_STACK_FILE)
        cm.check_lombok_constructor_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_dispatcher_not_synced_reports(self):
        # 反例：调度器未同步识别特征 → Java 项目按栈登记加载时看不到这条
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "= 入口\n\nJava 项目 → java.adoc\n")
        cm.check_lombok_constructor_guard()
        self.assertIn("AGENTS_COMMON", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例：README 目录说明未同步 → 读者从目录说明看不到这条存在
        self._write_valid()
        self.write("README.adoc", "目录结构：（未同步）。\n")
        cm.check_lombok_constructor_guard()
        self.assertIn("README", self.error_texts())


class TestCheckDocTypeNotationGuard(CheckSpecsTestCase):
    """钉住『文档中提及类型优先写类名 + import，不写类全名』（用户提出的规范要求）。

    该条为 **L2**、且判据是语义的（`java.util.UUID` 一类外部类型全限定属合规），故防线
    **不扫存量文档**，只钉"条文与判据仍在、边界没被删"。最易被四件事冲掉：
      * **"如果有必要"被读成"想写就写"** —— 三个必要情形（同名类冲突 / 无代码示例可承载
        import / 外部或他仓类型）被抽掉后，禁则就交回执行者自裁；
      * **被读成本条禁止一切全限定** —— 例外边界（路径与坐标不是类型名、字符串与配置里必须
        全限定的场合、`{@link}`/`@see` 成员引用）被删，反而会写出不合法的 javadoc 标签；
      * **存量口径被扩成全库改** —— "不做一次性替换、随动调整"被删，会被扩成"扫全库改全限定"；
      * **调度器无识别特征** —— 规则写了却永不被触发加载（实际失效）。
    故本组用例除正例外，逐条覆盖上述反例。
    """

    DOC = (
        "= 文档规范\n\n== 注释与文档\n"
        "* **文档中提及类型优先写类名 + import，不写类全名（L2）**：文档提到某个类型时，"
        "**一律先直接写它的类名**（`CUnauthorizedException`），需要解析时在**就近的代码示例**里"
        "写一条 `import com.c332030.ctool4j.core.exception.CUnauthorizedException;`——"
        "**不得**用**类全名**充当标识。**\"如果有必要\"的判据**：①**同名类冲突**；"
        "②**无代码示例可承载 import**（纯文档通篇没有代码块）；"
        "③**该类型不在本仓库的 classpath 内**（不在本仓库依赖树里）。"
        "\"classpath\"取\"本仓库的依赖/可解析范围\"。"
        "**三个例外的边界**：①**路径与坐标**（文档里的链接与 `@see` 标签所引的文件路径）"
        "**不是类型名**，照常写全；②**字符串与配置**里必须全限定的场合（Spring 的 "
        "`@ConditionalOnClass`、`application.yml` 的 `main-class`、反射按名加载、`import` "
        "语句本身）属逻辑实现；③**文档自身的文本引用**仍按上条的引用写法。"
        "**本集合的自身取舍，属 L2**：**不做存量一次性替换、随动调整**。\n")

    JAVA = (
        "= Java 规范\n\n== javadoc\n"
        "* 类型指代写短类名 + import、不写全限定类名：javadoc 里提到某个类时**先写短类名**"
        "，需要解析时在**代码示例**里写一条 `import com.c332030.ctool4j.core.exception."
        "CUnauthorizedException;`；**不得**写全限定类名（**除非该类型不在本仓库的 classpath "
        "内**）。`{@link ...}` / `@see` 里按类全名做的"
        "**成员引用**（javadoc 标签要求合法引用，须全限定）照常。\n")

    COMMON = (
        "= 通用规范\n"
        "** 写注释/文档/格式（**文档里提到某个类型时优先写类名 + `import`、"
        "不写类全名**（识别特征：文中出现\"包名 + 类名\"形态的指代））\n"
        "** Java 项目（**类型指代**：javadoc/文档里写类名 + `import`、不写全限定类名"
        "（除非该类型不在本仓库的 classpath 内；`{@link}` 成员引用与配置/反射按名加载"
        "照旧全限定））\n")

    def setUp(self) -> None:
        super().setUp()
        self._orig_doc = cm.DOC_FILE
        self._orig_java = cm.JAVA_STACK_FILE
        cm.DOC_FILE = os.path.join(self.root, "specs", "general", "doc.adoc")
        cm.JAVA_STACK_FILE = os.path.join(self.root, "specs", "stack", "java.adoc")
        self.write("specs/general/doc.adoc", self.DOC)
        self.write("specs/stack/java.adoc", self.JAVA)
        self.write("AGENTS_COMMON.adoc", self.COMMON)

    def tearDown(self) -> None:
        (cm.DOC_FILE, cm.JAVA_STACK_FILE) = (self._orig_doc, self._orig_java)
        super().tearDown()

    def test_positive_passes(self):
        cm.check_doc_type_notation_guard()
        self.assertEqual([], cm.errors)

    def test_rule_deleted_reports(self):
        # 反例①：整条被删（最简单的冲掉方式）
        self.write("specs/general/doc.adoc", "= 文档规范\n\n== 注释与文档\n* 别的条目\n")
        cm.check_doc_type_notation_guard()
        self.assertIn("文档类型指代防线被破坏", self.error_texts())

    def test_level_downgraded_reports(self):
        # 反例②：级别被摘（L2 去掉后写类全名会重新变成个人选择）
        self.write("specs/general/doc.adoc", self.DOC.replace("不写类全名（L2）", "不写类全名"))
        cm.check_doc_type_notation_guard()
        self.assertIn("文档类型指代防线被破坏", self.error_texts())

    def test_necessary_cases_removed_reports(self):
        # 反例③：三个必要情形被抽掉 → "如果有必要"变成想写就写
        self.write("specs/general/doc.adoc",
                   self.DOC.replace("①**同名类冲突**；", "①……；"))
        cm.check_doc_type_notation_guard()
        self.assertIn("同名类冲突", self.error_texts())

    def test_exception_boundary_removed_reports(self):
        # 反例④：例外边界（路径不是类型名）被删 → 会被读成本条禁止一切全限定
        self.write("specs/general/doc.adoc",
                   self.DOC.replace("**不是类型名**，照常写全", "也照常写全"))
        cm.check_doc_type_notation_guard()
        self.assertIn("路径与坐标", self.error_texts())

    def test_conditional_on_class_boundary_removed_reports(self):
        # 反例⑤：字符串/配置里必须全限定的边界被删
        self.write("specs/general/doc.adoc",
                   self.DOC.replace("@ConditionalOnClass", "某些注解"))
        cm.check_doc_type_notation_guard()
        self.assertIn("@ConditionalOnClass", self.error_texts())

    def test_outside_classpath_case_hardened_reports(self):
        # 反例⑥：第三条判据被写成"不在本仓库/本项目内"（把"不在 classpath"偏严成"不在本仓库"，
        # 用户口径的后半句"除非不在 classpath 才能写类全名"失效）
        self.write("specs/general/doc.adoc",
                   self.DOC.replace("③**该类型不在本仓库的 classpath 内**（不在本仓库依赖树里）。",
                                    "③**该类型不在本仓库/本项目内**。"))
        cm.check_doc_type_notation_guard()
        self.assertIn("classpath", self.error_texts())

    def test_java_stock_scope_hardened_reports(self):
        # 反例⑦：Java 落点的同一判据被写成"外部依赖或他仓类型"（不含 classpath 口径）
        self.write("specs/stack/java.adoc",
                   self.JAVA.replace("（**除非该类型不在本仓库的 classpath 内**）", ""))
        cm.check_doc_type_notation_guard()
        self.assertIn("不在本仓库的 classpath 内", self.error_texts())

    def test_stock_scope_removed_reports(self):
        # 反例⑥：存量口径被删 → 会被扩成"扫全库改全限定"
        self.write("specs/general/doc.adoc",
                   self.DOC.replace("**不做存量一次性替换、随动调整**", "一律改齐"))
        cm.check_doc_type_notation_guard()
        self.assertIn("存量", self.error_texts())

    def test_java_landing_removed_reports(self):
        # 反例⑦：Java 落点被删（接口/import 的具体写法只在栈层说得清）
        self.write("specs/stack/java.adoc", "= Java 规范\n\n== javadoc\n* 别的要求\n")
        cm.check_doc_type_notation_guard()
        self.assertIn("全限定类名", self.error_texts())

    def test_java_member_ref_boundary_removed_reports(self):
        # 反例⑧：{@link}/@see 成员引用须全限定这条边界被删
        self.write("specs/stack/java.adoc", self.JAVA.replace("{@link", "链接"))
        cm.check_doc_type_notation_guard()
        self.assertIn("Java 栈", self.error_texts())

    def test_dispatcher_trigger_removed_reports(self):
        # 反例⑨：调度器没有识别特征 → 规则永不被触发加载（实际失效）
        self.write("AGENTS_COMMON.adoc", "= 通用规范\n** 写注释/文档/格式\n")
        cm.check_doc_type_notation_guard()
        self.assertIn("包名 + 类名", self.error_texts())

    def test_java_trigger_removed_reports(self):
        # 反例⑩：Java 栈条目的识别特征被删
        self.write("AGENTS_COMMON.adoc",
                   self.COMMON.replace("（**类型指代**：javadoc/文档里写类名 + `import`、"
                                       "不写全限定类名"
                                       "（除非该类型不在本仓库的 classpath 内；"
                                       "`{@link}` 成员引用与配置/反射按名加载"
                                       "照旧全限定））", ""))
        cm.check_doc_type_notation_guard()
        self.assertIn("类型指代", self.error_texts())

    def test_missing_doc_file_reports(self):
        # 反例⑪：通用层落点文件缺失 → 必须报错、不得静默通过
        os.remove(os.path.join(self.root, "specs", "general", "doc.adoc"))
        cm.check_doc_type_notation_guard()
        self.assertIn("specs/general/doc.adoc", self.error_texts())


class TestCheckMavenMirrorGuard(CheckSpecsTestCase):
    """钉住 Maven「仓库与镜像」节：指定仓库、两条触发前提与换源边界不得被删改。

    该条规则的全部内容就是「用哪个仓库、什么前提下用」，故反例逐条对应"最易被精简掉"
    的字句：前提只剩一半、地址被换、优先次序被抹平、换源被读宽、换源出境内、既有配置被重配。
    正例含容差：节标题带括号补充、仓库地址改写成 `link:` 形态，均不报错。
    """

    SECTION = (
        "= Maven 规范\n\n== 仓库与镜像\n"
        "* 未配置过 Maven 仓库/镜像、且外网出口 IP 在中国大陆时（L1）："
        "必须先用这个仓库 `https://mirrors.cloud.tencent.com/nexus/repository/maven-public/`；"
        "仅当它不可用才允许改用其他在境内的镜像站；已配置过即不做，不覆盖既有配置。\n")

    def setUp(self) -> None:
        super().setUp()
        self.write("specs/stack/maven.adoc", self.SECTION)

    def test_positive_passes(self):
        cm.check_maven_mirror_guard()
        self.assertEqual([], cm.errors)

    def test_missing_file_reports(self):
        os.remove(os.path.join(self.root, "specs", "stack", "maven.adoc"))
        cm.check_maven_mirror_guard()
        self.assertIn("specs/stack/maven.adoc", self.error_texts())

    def test_section_deleted_reports(self):
        self.write("specs/stack/maven.adoc", "= Maven 规范\n\n== 依赖\n* 别的\n")
        cm.check_maven_mirror_guard()
        self.assertIn("仓库与镜像", self.error_texts())

    def test_section_title_extra_words_tolerated(self):
        # 节标题带括号补充属排版，不得因此报"缺少节"
        self.write("specs/stack/maven.adoc",
                   self.SECTION.replace("== 仓库与镜像",
                                        "== 仓库与镜像（公有仓库在国内的初始化）"))
        cm.check_maven_mirror_guard()
        self.assertEqual([], cm.errors)

    def test_designated_repo_removed_reports(self):
        self.write("specs/stack/maven.adoc",
                   self.SECTION.replace(
                       "https://mirrors.cloud.tencent.com/nexus/repository/maven-public/",
                       "https://example.invalid/repository/maven-public/"))
        cm.check_maven_mirror_guard()
        self.assertIn("mirrors.cloud.tencent.com", self.error_texts())

    def test_designated_repo_link_notation_tolerated(self):
        # 地址改写成 link: 形态（AsciiDoc 惯用写法）不得被误报为缺失
        self.write("specs/stack/maven.adoc",
                   self.SECTION.replace(
                       "`https://mirrors.cloud.tencent.com/nexus/repository/maven-public/`",
                       "link:https://mirrors.cloud.tencent.com/nexus/repository/maven-public/"
                       "[`https://mirrors.cloud.tencent.com/nexus/repository/maven-public/`]"))
        cm.check_maven_mirror_guard()
        self.assertEqual([], cm.errors)

    def test_forced_repo_wording_removed_reports(self):
        self.write("specs/stack/maven.adoc",
                   self.SECTION.replace("必须先用这个仓库", "可选其一"))
        cm.check_maven_mirror_guard()
        self.assertIn("必须先", self.error_texts())

    def test_trigger_condition_removed_reports(self):
        self.write("specs/stack/maven.adoc",
                   self.SECTION.replace("外网出口 IP 在中国大陆", "任何环境"))
        cm.check_maven_mirror_guard()
        self.assertIn("中国大陆", self.error_texts())

    def test_precondition_removed_reports(self):
        self.write("specs/stack/maven.adoc",
                   self.SECTION.replace("未配置过 Maven 仓库/镜像、且", "总是"))
        cm.check_maven_mirror_guard()
        self.assertIn("未配置过 Maven 仓库/镜像", self.error_texts())

    def test_existing_config_skip_removed_reports(self):
        self.write("specs/stack/maven.adoc",
                   self.SECTION.replace("已配置过即不做", "每次构建前都重配一遍"))
        cm.check_maven_mirror_guard()
        self.assertIn("已配置过即不做", self.error_texts())

    def test_fallback_condition_removed_reports(self):
        # "仅当它不可用才可换源"被放宽成"可自行另挑"即被拦下
        self.write("specs/stack/maven.adoc",
                   self.SECTION.replace("仅当它不可用才允许", "也可自行"))
        cm.check_maven_mirror_guard()
        self.assertIn("仅当它不可用", self.error_texts())

    def test_fallback_must_stay_in_china_reports(self):
        # 换源限定"在境内"被抹掉即被拦下（换到境外源等于没换）
        self.write("specs/stack/maven.adoc",
                   self.SECTION.replace("其他在境内的镜像站", "其他镜像站"))
        cm.check_maven_mirror_guard()
        self.assertIn("在境内的镜像站", self.error_texts())



class TestCheckRegistryMirrorGuard(CheckSpecsTestCase):
    """钉住『包源与镜像源』防线：推荐次序、降级边界与"先实测再启用"不得被删或降级。

    背景（本次用户要求 + 本项目实测）：换源此前只有 Maven 一栈的一条硬要求；其余语言/工具
    （npm、pip、Cargo、Go、RubyGems、容器镜像、系统包、运行时二进制）没有次序与边界，
    容易"凭感觉挑一个""直接跳到境外源"，或把**实测不存在**的目录（如"TUNA 的 npm 源"）
    照抄进配置。故反例逐条对应"最易被精简掉"的字句：次序被抹平、跳级、不先实测、
    覆盖引用方既有配置、把推荐读成强制。

    正例含容差：条目措辞与顺序可变（只认关键判据），源地址可增删（不钉名单）。
    """

    SECTION = (
        "= 依赖管理规范\n\n"
        "== 包源（包仓库/镜像站）的选用\n"
        "* 按次序选源、逐级降级，不得跳级（L1）：①就近/平台内已优化的源；②主流公共源；"
        "③地理上邻近的其他境外源；④更远的境外源站；只有当上一级实测取不到内容才降级；"
        "未配置过任何源时才动手配置。\n"
        "* 先实测可用再启用、一次配置到位（L1）：先对候选源做一次**真实请求**；"
        "不得**在每一轮里反复重试**同一个源。\n"
        "* 不得覆盖引用方既有配置（L1）：已配置过**包源时**一律沿用；只有在\"未配置过任何源\"时才动手配置；"
        "**推荐源不是强制源**，用户/项目声明的源永远优先。\n"
        "* 结果须可复核（L2）：给结论时带**取值与条件**。\n")

    def setUp(self) -> None:
        super().setUp()
        self.write("specs/general/dependency.adoc", self.SECTION)
        self.write("specs/stack/maven.adoc", "见 mirrors.cloud.tencent.com/nexus/repository/maven-public/\n")
        self.write("specs/stack/python.adoc", "pip 源见 https://mirrors.cloud.tencent.com/pypi/simple/\n")
        self.write("specs/stack/java.adoc", "Clojars（clojars）构件另加源\n")
        self.write("specs/general/ci-cd.adoc", "取源按 link:dependency.adoc[]「包源（包仓库/镜像站）的选用」\n")
        self.write("specs/platform/cnb.adoc", "== 包源与镜像源（平台侧优先口径）\n* 优先用平台内源\n")
        self.write("library/README.adoc", "| link:mirrors.adoc[] | 包源依据 |\n")
        self.write("library/mirrors.adoc",
                   "= 包源\n外部材料**未**规定源站的优先级次序；本集合据此推出次序；"
                   "**取样条件**见下；复核实测见下；**判可用性要取确定存在的包、不要只请求站点/目录根**；"
                   "单次采样不构成\"某源更快\"的结论。\n== 实测记录\n")

    def test_positive_passes(self):
        cm.check_registry_mirror_guard()
        self.assertEqual([], cm.errors)

    def test_missing_dependency_file_reports(self):
        os.remove(os.path.join(self.root, "specs", "general", "dependency.adoc"))
        cm.check_registry_mirror_guard()
        self.assertIn("specs/general/dependency.adoc", self.error_texts())

    def test_early_return_paths_still_return_normally(self):
        # 回归：缺文件/缺节这两条**最早命中**的路径必须是"报错并返回"，不得继续往下走
        # （否则后面的常量解包会抛异常，防线从"报错"变成"崩掉"，而既有用例只断言错误文本、
        # 崩了也照样绿）。判据：正常返回 + 错误清单已写。
        os.remove(os.path.join(self.root, "specs", "general", "dependency.adoc"))
        cm.check_registry_mirror_guard()          # 不抛异常即为通过
        self.assertIn("specs/general/dependency.adoc", self.error_texts())

        cm.errors.clear()
        self.write("specs/general/dependency.adoc", "= 依赖\n\n== 别的\n")
        cm.check_registry_mirror_guard()
        self.assertIn("包源（包仓库/镜像站）的选用", self.error_texts())

    def test_topic_file_not_registered_in_index_reports(self):
        # 反例：主题文件在磁盘上、却漏登记到入口表——读者按入口找不到它
        # （既有 `quality.adoc` 就不在下限常量里，故完整性只能靠入口表核对，不能靠常量）
        self.write("library/extra.adoc", "= 另一个主题\n\n内容。\n")
        cm.check_registry_mirror_guard()
        self.assertIn("extra.adoc", self.error_texts())

    def test_weak_anchor_no_longer_passes_on_loose_tokens(self):
        # 反例：只留"已配置过**"这类任何措辞都会命中的片段、把边界句删掉 → 必须报错
        self.write("specs/general/dependency.adoc",
                   self.SECTION.replace("只有在\"未配置过任何源\"时才动手配置；", "已配置过**就跳过；")
                   .replace("**推荐源不是强制源**，用户/项目声明的源永远优先。", "必须用推荐源。"))
        cm.check_registry_mirror_guard()
        self.assertIn("不覆盖引用方既有配置", self.error_texts())

    def test_section_deleted_reports(self):
        self.write("specs/general/dependency.adoc", "= 依赖\n\n== 引入依赖\n* 别的\n")
        cm.check_registry_mirror_guard()
        self.assertIn("包源（包仓库/镜像站）的选用", self.error_texts())

    def test_order_terms_removed_reports(self):
        # 次序被压成"用国内源"时，跳级与境外分档就无从判断
        self.write("specs/general/dependency.adoc",
                   self.SECTION.replace("地理上邻近的其他境外源", "国外源"))
        cm.check_registry_mirror_guard()
        self.assertIn("邻近", self.error_texts())

    def test_probe_before_use_removed_reports(self):
        self.write("specs/general/dependency.adoc",
                   self.SECTION.replace("先对候选源做一次**真实请求**", "按文档描述直接配置"))
        cm.check_registry_mirror_guard()
        self.assertIn("真实请求", self.error_texts())

    def test_existing_config_keep_removed_reports(self):
        self.write("specs/general/dependency.adoc",
                   self.SECTION.replace("已配置过**包源时**一律沿用", "每次都用推荐源覆盖"))
        cm.check_registry_mirror_guard()
        self.assertIn("沿用", self.error_texts())

    def test_recommend_not_force_removed_reports(self):
        self.write("specs/general/dependency.adoc",
                   self.SECTION.replace("**推荐源不是强制源**", "必须使用本规范指定的源"))
        cm.check_registry_mirror_guard()
        self.assertIn("强制源", self.error_texts())

    def test_stack_landing_missing_reports(self):
        # 栈侧落点被删 → 具体源地址无处承载（本条要防的正是"只有通用层、落不到现场"）
        self.write("specs/stack/python.adoc", "= Python\n")
        cm.check_registry_mirror_guard()
        self.assertIn("specs/stack/python.adoc", self.error_texts())

    def test_library_not_registered_reports(self):
        self.write("library/README.adoc", "| link:sources.adoc[] | 别的 |\n")
        cm.check_registry_mirror_guard()
        self.assertIn("mirrors.adoc", self.error_texts())

    def test_library_without_measured_record_reports(self):
        self.write("library/mirrors.adoc", "= 包源\n本处只写推荐名单。\n")
        cm.check_registry_mirror_guard()
        self.assertIn("library/mirrors.adoc", self.error_texts())


class TestCheckThroughputGuard(CheckSpecsTestCase):
    """钉住「执行吞吐」条：判据要点、常驻层引用与调度器登记不得被删。

    实证：Agent 慢的主因是**轮次**——实测一次任务 180 次模型请求 / 175 万 token 输入 /
    1659 s 运行，其中模型生成仅 580 s（约 65% 的墙钟花在轮次之间的工具执行与等待）。
    故反例逐条对应"最易被当废话砍掉"的字句：合并调用、构建输出一次取到、不重复读、
    往返成本入规划、凭据一次固化、镜像不重配、长流程不空转；另钉常驻层引用与调度器
    识别特征（缺则规则不可达、不加载）。
    """

    PLATFORM_SECTION = (
        "= CNB 平台相关\n\n== 执行吞吐（平台侧的两处特有代价）\n"
        "* 一次唤起 = 一次完整加载 + 一轮往返（L1）。\n"
        "* 状态查询按先取汇总、再按需下钻（L2）。\n"
        "* 不要用零信息的往返等长流程。\n"
        "* AI 用量汇总与 AI 请求明细是可观测面（L2）。\n")

    SECTION = (
        "= 上下文与读取范围规范\n\n== 执行吞吐（逐条判据）\n"
        "* 独立调用必须合并，禁止试探式往返（L1）：不得为了先看一步再决定下一步拆成多轮。\n"
        "* 构建与校验的输出须一次取到（L1）：执行 + 取统计 + 取失败明细一次完成。\n"
        "* 读到的内容一次沉淀、不重复读（L2）。\n"
        "* 往返成本也要算（L2）：规划时估出预计要几轮往返。\n"
        "* 执行环境凭据须固化为可复用形态（L2）：开始时固化一次。\n"
        "* 本地缓存与镜像就近取用（L2）：已配置过即沿用、不覆盖、不重配。\n"
        "* 长流程不留零信息等待（L1）：在跑与卡住须可分辨。\n")

    def _write_all(self, context=None, core=None, common=None):
        self.write("specs/platform/cnb.adoc", self.PLATFORM_SECTION)
        self.write("specs/general/context.adoc", context if context is not None else self.SECTION)
        self.write("specs/core/execution.adoc",
                   core if core is not None else "= 执行原则\n执行轮次须合并（少绕）\n执行吞吐\n")
        self.write("AGENTS_COMMON.adoc",
                   common if common is not None else
                   "= 入口\n== 分类与懒加载（加载调度器）\n"
                   "  ** 执行吞吐（识别特征：预计需多次往返） → link:specs/general/context.adoc[]\n")

    def test_positive_passes(self):
        self._write_all()
        cm.check_throughput_guard()
        self.assertEqual([], cm.errors)

    def test_missing_file_reports(self):
        self._write_all()
        os.remove(os.path.join(self.root, "specs", "general", "context.adoc"))
        cm.check_throughput_guard()
        self.assertIn("specs/general/context.adoc", self.error_texts())

    def test_section_deleted_reports(self):
        self._write_all(context="= 上下文与读取范围规范\n\n== 读取范围\n* 别的\n")
        cm.check_throughput_guard()
        self.assertIn("执行吞吐", self.error_texts())

    def test_merge_rule_removed_reports(self):
        self._write_all(context=self.SECTION.replace("独立调用必须合并", "调用可分散"))
        cm.check_throughput_guard()
        self.assertIn("独立调用必须合并", self.error_texts())

    def test_probe_roundtrip_removed_reports(self):
        self._write_all(context=self.SECTION.replace("试探式往返", "多轮"))
        cm.check_throughput_guard()
        self.assertIn("试探式往返", self.error_texts())

    def test_build_output_rule_removed_reports(self):
        self._write_all(context=self.SECTION.replace("构建与校验的输出须一次取到", "构建输出稍后再说"))
        cm.check_throughput_guard()
        self.assertIn("构建与校验的输出须一次取到", self.error_texts())

    def test_no_repeat_read_removed_reports(self):
        self._write_all(context=self.SECTION.replace("不重复读", "可再确认"))
        cm.check_throughput_guard()
        self.assertIn("不重复读", self.error_texts())

    def test_roundtrip_cost_removed_reports(self):
        self._write_all(context=self.SECTION.replace("往返成本也要算", "只管跑"))
        cm.check_throughput_guard()
        self.assertIn("往返成本也要算", self.error_texts())

    def test_credential_rule_removed_reports(self):
        self._write_all(context=self.SECTION.replace("固化为可复用形态", "每次都重新登录"))
        cm.check_throughput_guard()
        self.assertIn("固化为可复用形态", self.error_texts())

    def test_mirror_no_reconfigure_removed_reports(self):
        # "已配置过即沿用不重配"被抹掉即被拦下（与 Maven 侧同向：反复重配本身就是往返）
        self._write_all(context=self.SECTION.replace("不覆盖、不重配", "每次重建配置"))
        cm.check_throughput_guard()
        self.assertIn("不覆盖、不重配", self.error_texts())

    def test_zero_info_wait_removed_reports(self):
        self._write_all(context=self.SECTION.replace("零信息等待", "等待期间可轮询"))
        cm.check_throughput_guard()
        self.assertIn("零信息等待", self.error_texts())

    def test_resident_reference_removed_reports(self):
        # 常驻层未点到执行吞吐：每次会话加载的常驻层里没有这条纪律
        self._write_all(core="= 执行原则\n无关内容\n")
        cm.check_throughput_guard()
        self.assertIn("specs/core/execution.adoc", self.error_texts())

    def test_dispatcher_registration_removed_reports(self):
        # 调度器无本条的加载项与识别特征：规则永远不会被触发加载
        self._write_all(common="= 入口\n== 分类与懒加载（加载调度器）\n  ** 别的 → link:x[]\n")
        cm.check_throughput_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_section_title_extra_words_tolerated(self):
        # 节标题带括号补充属排版，不得因此报"缺少节"
        self._write_all(context=self.SECTION.replace("== 执行吞吐（逐条判据）",
                                                     "== 执行吞吐（逐条判据，少绕）"))
        cm.check_throughput_guard()
        self.assertEqual([], cm.errors)

    def _write_platform(self, content=None):
        self.write("specs/platform/cnb.adoc",
                   content if content is not None else self.PLATFORM_SECTION)

    def test_platform_section_positive(self):
        self._write_all()
        self._write_platform()
        cm.check_throughput_guard()
        self.assertEqual([], cm.errors)

    def test_platform_section_deleted_reports(self):
        self._write_all()
        self._write_platform("= CNB 平台相关\n\n== 冲突处理\n* 别的\n")
        cm.check_throughput_guard()
        self.assertIn("specs/platform/cnb.adoc", self.error_texts())

    def test_platform_wakeup_cost_removed_reports(self):
        self._write_all()
        self._write_platform(self.PLATFORM_SECTION.replace("一次唤起 = 一次完整加载 + 一轮往返", "唤起即执行"))
        cm.check_throughput_guard()
        self.assertIn("一次唤起", self.error_texts())

    def test_platform_summary_first_removed_reports(self):
        self._write_all()
        self._write_platform(self.PLATFORM_SECTION.replace("先取汇总、再按需下钻", "逐个查"))
        cm.check_throughput_guard()
        self.assertIn("先取汇总", self.error_texts())

    def test_platform_observability_removed_reports(self):
        self._write_all()
        self._write_platform(self.PLATFORM_SECTION.replace("AI 用量汇总", "用量信息"))
        cm.check_throughput_guard()
        self.assertIn("AI 用量汇总", self.error_texts())


class TestCheckPerformanceGuard(CheckSpecsTestCase):
    """钉住「性能测试」防线：测量那一半与记录那一半的要点、两处落点与依据主题。

    实证（用户提出）：旧判据只有四条粗规则（独立性/对比测试/排除初始化干扰/结果分析），
    "跑一次看看谁快"即可交差——成绩是单次采样、没有离散度与可比基线，结论只有一句
    "快了 X 倍"；优化停在"改一版跑一次"，瓶颈不复测、失败方向不落盘，后来的人重踩同一个坑。
    故反例逐条对应"最易被当废话砍掉"的字句：基准那一类、离散度与样本量、公平比较、
    计时区间与消费结果、测量口径、必留证据、取数与组合矩阵、优化日志、闭环迭代、
    瓶颈归因与方向、结论落点与时效、优化不得改变行为。
    """

    SECTION = (
        "= 测试规范（通用层，跨语言）\n\n== 性能测试\n\n"
        "=== 承载与触发\n"
        "* 独立性（L1）：性能测试独立于单元测试。\n"
        "* 何时需要性能测试（L1）：按性能敏感度判定，命中任一特征才做，"
        "不得一律加、也不得漏掉真敏感点；多方案选型需要数据佐证。\n\n"
        "=== 对比与测量\n"
        "* 对比测试（L1）：类别至少 3 类，并含当前项目使用的那一类作基准。\n"
        "* 排除初始化干扰（L1）：须测两次、第二次在全部初始化完成后。\n"
        "* 测量口径须可核对（L1）：预热轮次、测量轮次、批量、计时口径、运行环境须写明。\n"
        "* 离散度与样本量（L1）：至少 3 次有效采样并报离散度；差异小于离散度视为无显著差异。\n"
        "* 公平比较（L1）：同一进程内交替测量、各自预热与迭代、同一份输入数据。\n"
        "* 计时区间界定（L1）：只计被测逻辑，测完必须消费结果。\n\n"
        "=== 记录（成绩与依据落在哪、记到什么程度）\n"
        "* 落点（L1）：跨类级进独立性能测试文档，用例级进测试代码文档注释。\n"
        "* 每次运行的必留证据（L1，四项缺一即不算测过）：测量口径、各方案成绩、结论、"
        "未选方案为什么不选。\n"
        "* 成绩怎么取数（L1）：每组方案记终值（均值或中位数）+ 离散度。\n"
        "* 方案组合矩阵（L2）：`方案编号 | 组合 | 终值 | 离散度 | 与基线之比 | 结论`。\n"
        "* 优化日志（L2）：每轮记改了什么与是否保留；不保留的改动也必须留一行。\n"
        "* 只记结果不记过程（L1）：只留取值 + 来源 + 结论。\n\n"
        "=== 迭代与收敛\n"
        "* 闭环迭代（L1）：测出瓶颈后继续优化并复测，直至收敛。\n"
        "* 收益判定用实测、不用估计（L1）。\n"
        "* 瓶颈归因与方向（L1）：写明瓶颈判断、依据与下一步方向。\n"
        "* 优化方向与思路（L1）：已试过的方向（含失败的）与尚未尝试的方向都须落盘。\n"
        "* 结论的落点（L1）：选型理由进代码文档注释/设计文档。\n"
        "* 结论的时效（L2）：环境或规模变化须重新核对。\n"
        "* 结果分析须给出原因与对策（L1）：差异由哪些原因引起，并给出对应的解决方案。\n"
        "* 优化不得改变行为（L1）：既有功能用例全绿。\n"
        "* 结果反哺基线（L2）：新取值成为此后比对的基线。\n")

    JAVA = (
        "= Java 测试规范\n\n== 启动型与端到端测试\n"
        "* **`PerfTests`（性能）**：测量与记录要求统一见 link:../general/testing.adoc[]"
        "「性能测试」；不混入常规 `test` 阶段、仅显式触发。\n")

    LIBRARY = (
        "= 性能测试判据的依据（测量与记录）\n\n"
        "== 当初要解决的失效（本项目实证）\n本项目实证。\n\n"
        "== 外部材料：JMH 官方文档（OpenJDK，微基准的行业事实标准）\n"
        "https://github.com/openjdk/jmh 未逐字取回（要点转述、非逐字摘录）。\n\n"
        "== 同义性差异与覆盖点（本集合自己承认的）\n"
        "ISO/IEC/IEEE 25010 / ISO/IEC/IEEE 29119-4；本集合自己的判据化取舍。\n")

    def _write_all(self, section=None, java=None, common=None, library=None):
        self.write("specs/general/testing.adoc",
                   section if section is not None else self.SECTION)
        self.write("specs/stack/java-testing.adoc",
                   java if java is not None else self.JAVA)
        self.write("library/performance.adoc",
                   library if library is not None else self.LIBRARY)
        self.write("AGENTS_COMMON.adoc",
                   common if common is not None else
                   "= 入口\n== 分类与懒加载（加载调度器）\n"
                   "  ** 跑测试/补测试，或做性能测试/性能优化（识别特征：判定某处是否需要性能测试、"
                   "性能敏感场景、多方案选型需数据佐证） → link:specs/general/testing.adoc[]"
                   "（性能测试的测量与记录判据、方案组合与成绩）\n")

    def test_positive_passes(self):
        self._write_all()
        cm.check_performance_guard()
        self.assertEqual([], cm.errors)

    def test_missing_spec_reports(self):
        self._write_all()
        os.remove(os.path.join(self.root, "specs", "general", "testing.adoc"))
        cm.check_performance_guard()
        self.assertIn("specs/general/testing.adoc", self.error_texts())

    def test_section_deleted_reports(self):
        self._write_all(section="= 测试规范\n\n== 单元测试\n* 别的\n")
        cm.check_performance_guard()
        self.assertIn("性能测试", self.error_texts())

    def test_baseline_member_removed_reports(self):
        # 缺"当前实现作基准"那一类：只剩候选方案之间的相对比较，"要不要换"无从判起
        self._write_all(section=self.SECTION.replace(
            "并含当前项目使用的那一类作基准", "并覆盖多种实现"))
        cm.check_performance_guard()
        self.assertIn("含当前项目使用的那一类作基准", self.error_texts())

    def test_dispersion_removed_reports(self):
        self._write_all(section=self.SECTION.replace(
            "至少 3 次有效采样并报离散度；差异小于离散度视为无显著差异",
            "跑几次取平均即可"))
        cm.check_performance_guard()
        self.assertIn("至少 3 次有效采样", self.error_texts())

    def test_fair_comparison_removed_reports(self):
        self._write_all(section=self.SECTION.replace(
            "同一进程内交替测量、各自预热与迭代、同一份输入数据", "各自跑即可"))
        cm.check_performance_guard()
        self.assertIn("同一进程", self.error_texts())

    def test_consume_result_removed_reports(self):
        self._write_all(section=self.SECTION.replace(
            "测完必须消费结果", "不必管结果"))
        cm.check_performance_guard()
        self.assertIn("消费结果", self.error_texts())

    def test_evidence_member_removed_reports(self):
        # 必留证据被削成三项（少了"未选方案为什么不选"）即被拦下
        self._write_all(section=self.SECTION.replace("、未选方案为什么不选", ""))
        cm.check_performance_guard()
        self.assertIn("未选方案为什么不选", self.error_texts())

    def test_cause_analysis_removed_reports(self):
        # 旧"结果分析"条（差异由哪些原因引起 + 给出解决方案）被整条抽掉即被拦下
        self._write_all(section=self.SECTION.replace(
            "* 结果分析须给出原因与对策（L1）：差异由哪些原因引起，并给出对应的解决方案。\n", ""))
        cm.check_performance_guard()
        self.assertIn("结果分析须给出原因与对策（L1）", self.error_texts())

    def test_cause_analysis_removed_reports(self):
        # 旧"结果分析"条（差异由哪些原因引起 + 给出解决方案）被整条抽掉即被拦下
        self._write_all(section=self.SECTION.replace(
            "* 结果分析须给出原因与对策（L1）：差异由哪些原因引起，并给出对应的解决方案。\n", ""))
        cm.check_performance_guard()
        self.assertIn("结果分析须给出原因与对策（L1）", self.error_texts())

    def test_iteration_loop_removed_reports(self):
        self._write_all(section=self.SECTION.replace(
            "闭环迭代（L1）：测出瓶颈后继续优化并复测，直至收敛。",
            "跑一次即可。"))
        cm.check_performance_guard()
        self.assertIn("闭环迭代（L1）", self.error_texts())

    def test_behavior_unchanged_removed_reports(self):
        self._write_all(section=self.SECTION.replace(
            "优化不得改变行为（L1）：既有功能用例全绿。", "优化可顺手改行为。"))
        cm.check_performance_guard()
        self.assertIn("优化不得改变行为（L1）", self.error_texts())

    def test_dispatcher_entry_removed_reports(self):
        # 调度器无本条加载项：规则永远不会被触发加载
        self._write_all(common="= 入口\n== 分类与懒加载（加载调度器）\n  ** 别的 → link:x[]\n")
        cm.check_performance_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_java_carrier_removed_reports(self):
        self._write_all(java="= Java 测试规范\n\n== 断言\n* 别的\n")
        cm.check_performance_guard()
        self.assertIn("specs/stack/java-testing.adoc", self.error_texts())

    def test_library_missing_reports(self):
        self._write_all()
        os.remove(os.path.join(self.root, "library", "performance.adoc"))
        cm.check_performance_guard()
        self.assertIn("library/performance.adoc", self.error_texts())

    def test_library_anchor_removed_reports(self):
        # 同义性差异被删：读者会把"至少 3 次采样"读成某标准的规定
        self._write_all(library="= 性能测试判据的依据\n\n* JMH 见官方文档\n")
        cm.check_performance_guard()
        self.assertIn("同义性差异与覆盖点（本集合自己承认的）", self.error_texts())


class TestCheckQualityGuard(CheckSpecsTestCase):
    """钉住「代码质量（新产出即高质）」防线：十项下限、判定标准、依据与调度器登记。

    实证（用户报告）：有的时候功能是写出来了、但代码质量比较低——此前规范只覆盖形式类要求，
    新产出即高质的整体下限没有成文判据，执行者按"能跑就行"收敛。故反例逐条对应"最易被当
    废话砍掉"的字句：坏味道清单、嵌套上限、命名一致、不吞异常、资源成对释放、共享状态同步、
    可预见的性能退化、测试与文档、交付前逐条自查、依据行；另钉调度器识别特征与依据主题
    （缺则规则不加载、或依据只剩名称）。
    """

    SECTION = (
        "= 通用编码规范\n\n== 代码质量（新产出即高质）\n"
        "* 适用面：**新写的内容**与**本次改到的内容**适用；**存量**随动迁移。\n"
        "* **新代码不得引入坏味道（L1）**：重复代码、过长函数、依恋情结、注释代替澄清。\n"
        "* **职责单一、结构清晰（L1）**：能不能**一句话说清**它做什么；嵌套**三层以内**。\n"
        "* **命名表意、不用缩写（L1）**：同一概念在项目中只有一个叫法；禁缩写与拼音。\n"
        "* **可读性优先（L1）**：不用**魔法值**；同一表达式不重复求值。\n"
        "* **显式处理失败与边界（L1）**：**不得吞异常**；**边界条件必须显式处理**。\n"
        "* **无资源泄漏（L1）**：一律用**确定性释放**机制、成对释放。\n"
        "* **无并发隐患（L1）**：**共享可变状态**须有明确同步策略；锁范围与顺序写清。\n"
        "* **性能不写退化写法（L2）**：**循环内** IO 与查询、**N+1** 查询。\n"
        "* **测试与文档跟得上（L1）**：**新功能**必配用例；契约写进**文档注释**。\n"
        "* **交付前质量自检（L1）**：**逐条自查**本节十项；**能过机械判据**是下限。\n"
        "* 依据（标准名/编号）：ISO/IEC 25010、ISO/IEC/IEEE 12207、"
        "Martin Fowler《Refactoring》、Clean Code、SEI CERT。\n")

    LIBRARY = (
        "= 代码质量与生成开销的依据\n\n"
        "== 当初要解决的失效（本项目实证）\n文字。\n\n"
        "== 外部材料与逐字依据（业界事实标准与标准编号）\n"
        "ISO/IEC 25010、Martin Fowler《Refactoring》、Clean Code、"
        "SEI CERT Coding Standards、**未逐字取回**。\n\n"
        "== 同义性差异与覆盖点（本集合自己承认的）\n文字。\n")

    def _write_all(self, section=None, common=None, library=None):
        self.write("specs/general/coding.adoc",
                   section if section is not None else self.SECTION)
        self.write("library/quality.adoc",
                   library if library is not None else self.LIBRARY)
        self.write("AGENTS_COMMON.adoc",
                   common if common is not None else
                   "= 入口\n== 分类与懒加载（加载调度器）\n"
                   "  ** 编写代码（识别特征：**写任何新代码、改任何既有代码**（含**代码评审**）)"
                   " → link:specs/general/coding.adoc[]（代码质量（新产出即高质））\n")

    def test_positive_passes(self):
        self._write_all()
        cm.check_quality_guard()
        self.assertEqual([], cm.errors)

    def test_missing_spec_reports(self):
        self._write_all()
        os.remove(os.path.join(self.root, "specs", "general", "coding.adoc"))
        cm.check_quality_guard()
        self.assertIn("specs/general/coding.adoc", self.error_texts())

    def test_section_deleted_reports(self):
        self._write_all(section="= 通用编码规范\n\n== 代码复用\n* 别的\n")
        cm.check_quality_guard()
        self.assertIn("代码质量（新产出即高质）", self.error_texts())

    def test_smell_list_removed_reports(self):
        self._write_all(section=self.SECTION.replace("重复代码、过长函数、依恋情结、注释代替澄清",
                                                     "注意代码质量"))
        cm.check_quality_guard()
        self.assertIn("重复代码", self.error_texts())

    def test_nesting_limit_removed_reports(self):
        self._write_all(section=self.SECTION.replace("嵌套**三层以内**", "嵌套尽量少"))
        cm.check_quality_guard()
        self.assertIn("三层以内", self.error_texts())

    def test_naming_consistency_removed_reports(self):
        self._write_all(section=self.SECTION.replace("同一概念在项目中只有一个叫法", "命名要清晰"))
        cm.check_quality_guard()
        self.assertIn("同一概念在项目中只有一个叫法", self.error_texts())

    def test_swallow_exception_removed_reports(self):
        self._write_all(section=self.SECTION.replace("**不得吞异常**；", ""))
        cm.check_quality_guard()
        self.assertIn("不得吞异常", self.error_texts())

    def test_resource_release_removed_reports(self):
        self._write_all(section=self.SECTION.replace("一律用**确定性释放**机制、成对释放",
                                                     "注意释放资源"))
        cm.check_quality_guard()
        self.assertIn("确定性释放", self.error_texts())

    def test_concurrency_removed_reports(self):
        self._write_all(section=self.SECTION.replace("**共享可变状态**须有明确同步策略",
                                                     "注意并发"))
        cm.check_quality_guard()
        self.assertIn("共享可变状态", self.error_texts())

    def test_selfcheck_removed_reports(self):
        self._write_all(section=self.SECTION.replace("**逐条自查**本节十项", "自查即可"))
        cm.check_quality_guard()
        self.assertIn("逐条自查", self.error_texts())

    def test_basis_line_removed_reports(self):
        self._write_all(section=self.SECTION.replace(
            "ISO/IEC 25010、ISO/IEC/IEEE 12207、Martin Fowler《Refactoring》、Clean Code、SEI CERT。",
            "为业界共识。"))
        cm.check_quality_guard()
        self.assertIn("ISO/IEC 25010", self.error_texts())

    def test_dispatcher_entry_removed_reports(self):
        self._write_all(common="= 入口\n== 分类与懒加载（加载调度器）\n  ** 别的 → link:x[]\n")
        cm.check_quality_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_library_missing_reports(self):
        self._write_all()
        os.remove(os.path.join(self.root, "library", "quality.adoc"))
        cm.check_quality_guard()
        self.assertIn("library/quality.adoc", self.error_texts())

    def test_library_anchor_removed_reports(self):
        self._write_all(library="= 依据\n\n* 见业界材料\n")
        cm.check_quality_guard()
        self.assertIn("同义性差异与覆盖点（本集合自己承认的）", self.error_texts())


class TestCheckGenerationEfficiencyGuard(CheckSpecsTestCase):
    """钉住「生成效率 / token 纪律」防线：判据、边界条与调度器登记。

    实证（用户提出）：要"提高生成效率的规范"与"不影响功能完整性和代码质量的前提下提高 token
    利用率"，并追问"是一回事吗"。此前只有「执行吞吐」管调用形态，不管"这件事该做几轮"，
    也没有 token 维度的判据。故反例除逐条要点外，**重点钉两条边界**——"效率不得越过质量"与
    "三件事不得为省 token 让步"（缺位即等于允许以省为名跳过校验/复核/留证）。
    """

    GEN = (
        "== 生成效率（同等质量下最少往返）\n"
        "* **先定完成判据，再动手（L1）**：把**什么算做完**写成判据（**返工**根因）。\n"
        "* **一次做对一次做完（L1）**：**一次改到位**；不得**碎片推进**；"
        "判据：**本轮交付之后是否需要再改同一批文件**。\n"
        "* **延后验证、一次到位（L1）**：**攒到一处**；不得**重启一次构建**；"
        "**存在真实依赖**才逐步验证。\n"
        "* **失败一次就查根因，不靠重试撞对（L1）**：**反复重启同一构建**即违规；"
        "**第二遍**无新认识即违规。\n"
        "* **按需读取、不全量预处理（L1）**：**全量预读**即违规；**低信号**内容会降准确率。\n"
        "* **批量化同类操作（L2）**：**一次做完**、能**脚本化**就脚本化。\n"
        "* **任务边界一次说清（L2）**：避免**两段式**；不得**先做一版看看**。\n"
        "* **依据名代替复述（L2）**：复述制造**第二真源**。\n"
        "* **不重做已做完的事（L2）**：不得**再确认一次**、**再跑一遍看看**。\n"
        "* **收尾一次收敛（L2）**：汇报**一次写完**；不得**再补一条**。\n"
        "* **效率不得越过质量（L1，本节的边界）**：都**不得用于减少**必要工作；"
        "效率不是**更少的质量**。\n"
        "* 依据（标准名/编号）：ISO/IEC/IEEE 25010、Anthropic 工程博客 context engineering、"
        "progressive disclosure。\n")

    TOKEN = (
        "== token 纪律（提高利用率与节省开销）\n"
        "* **先把两个概念分开**：**不是一回事**、但**手段大幅重叠**——"
        "**提高 token 利用率**是「每份输入产生的有效产出」，**节省 token** 是减少总量。\n"
        "* **利用率判据：输入须「用到了」（L1）**：**答不出用途**的即**无效输入**。\n"
        "* **约束放在外部、不进上下文（L1）**：能**落成文件**就不要复述；"
        "写在对话里每次请求都要重发。\n"
        "* **少复述、多引用（L1）**：不得**复述**已知内容，写**依据名**。\n"
        "* **不重复读、不重复贴（L1）**：**只读一次**；不得**再确认一次**。\n"
        "* **只记结论与取值、不带原始日志（L1）**：不夹带**原始日志**；写**取值 + 来源**。\n"
        "* **三件事不得为省 token 让步（L1，本条的边界）**：**功能完整性**、**代码质量**、"
        "**验证完整**一件都不能省。\n"
        "* **成本须可说明、不得以「不贵」带过（L2）**：须说出换来什么判断。\n"
        "* **不设「必须量化 token」的要求**：**判据是**输入有没有被用上。\n"
        "* 依据（标准名/编号）：ISO/IEC/IEEE 25010、ISO/IEC Directives Part 2。\n")

    def _write_all(self, gen=None, token=None, common=None):
        body = ("= 上下文与读取范围规范\n\n"
                + (gen if gen is not None else self.GEN) + "\n"
                + (token if token is not None else self.TOKEN))
        self.write("specs/general/context.adoc", body)
        self.write("AGENTS_COMMON.adoc",
                   common if common is not None else
                   "= 入口\n== 分类与懒加载（加载调度器）\n"
                   "  ** 读取范围、生成效率（同等质量下最少往返）、token 纪律（提高利用率与"
                   "节省开销）、执行吞吐（识别特征：预计需多次往返、出现安排取舍）"
                   " → link:specs/general/context.adoc[]\n")

    def test_positive_passes(self):
        self._write_all()
        cm.check_generation_efficiency_guard()
        self.assertEqual([], cm.errors)

    def test_gen_section_deleted_reports(self):
        self._write_all(gen="== 别的东西\n* x")
        cm.check_generation_efficiency_guard()
        self.assertIn("生成效率", self.error_texts())

    def test_token_section_deleted_reports(self):
        self._write_all(token="== 别的东西\n* x")
        cm.check_generation_efficiency_guard()
        self.assertIn("token 纪律", self.error_texts())

    def test_utilization_judgement_removed_reports(self):
        self._write_all(token=self.TOKEN.replace("**答不出用途**的即**无效输入**", "尽量少读"))
        cm.check_generation_efficiency_guard()
        self.assertIn("无效输入", self.error_texts())

    def test_token_boundary_removed_reports(self):
        self._write_all(token=self.TOKEN.replace("**功能完整性**", "一切"))
        cm.check_generation_efficiency_guard()
        self.assertIn("功能完整性", self.error_texts())

    def test_efficiency_boundary_removed_reports(self):
        self._write_all(gen=self.GEN.replace("都**不得用于减少**必要工作", "尽量快"))
        cm.check_generation_efficiency_guard()
        self.assertIn("不得用于减少", self.error_texts())

    def test_not_same_thing_removed_reports(self):
        self._write_all(token=self.TOKEN.replace("**不是一回事**、但**手段大幅重叠**", "是一回事"))
        cm.check_generation_efficiency_guard()
        self.assertIn("不是一回事", self.error_texts())

    def test_retry_rule_removed_reports(self):
        self._write_all(gen=self.GEN.replace("**反复重启同一构建**即违规", "可反复试"))
        cm.check_generation_efficiency_guard()
        self.assertIn("反复重启同一构建", self.error_texts())

    def test_dispatcher_entry_removed_reports(self):
        self._write_all(common="= 入口\n== 分类与懒加载（加载调度器）\n  ** 别的 → link:x[]\n")
        cm.check_generation_efficiency_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())


class TestCheckAfterChangeReviewGuard(CheckSpecsTestCase):
    """钉住「改动后复核」防线：五件事、干净子 agent、三态台账与维护方登记。

    实证（用户要求）：每次加完规范之后都必须 review，机械手段一定要跑，干净的子 agent 也
    不能漏（有了就忽略、没有就加）。此前"改完规范要做什么"散在多节、没有固定动作清单，
    实测形态是只跑一遍主校验脚本、语义复核被"改动小"顺手跳过、台账写成散文结论。
    """

    VERIFY = (
        "= 验证规范\n\n== 改完规范必做的五件事（机械手段必跑，干净子 agent 复核不可漏）\n"
        "* **① 机械手段必须先跑、且跑全（L1，不可省）**：**全量扫描**；**报红就地修复**。\n"
        "* **② 干净子 agent 的语义复核不可漏（L1，有了就忽略、没有就加）**：项目规范已有就按"
        "已有那份执行；**没有就加**，补在**项目自身规范**里。\n"
        "* **③ 三视角一并回答、一次读取分栏列（L1）**：完整性、有效性与认知质量、接纳面。\n"
        "* **④ 复核要走三态台账**：通过 / 未发现问题 / **悬置**；**三态各占一栏、"
        "**不得合并**。\n"
        "* **⑤ 子 agent 不可用时的降级与留证（L1）**：**不得跳过复核**；不得换**外部来源**；"
        "**标注独立性边界**。\n"
        "* **本节的边界（L1）**：**只对规范类改动（B 类）**成立；**代码类改动不做三视角**。\n")

    REVIEW = (
        "= code review 规范\n\n== 改动后的 review（每次改完都得复核一次）\n"
        "* **每次改动后的常规 review（L1）**：范围＝**本次改动的全部产物**；"
        "动作＝**按改动性质取值**。\n"
        "* **改完即审的固定动作（L1）**：①**跑**机械手段；②**比**基线；③**核**原话；"
        "④**留**证。\n"
        "* **规范类改动不得只跑机械手段（L1）**：**跑绿了** **不等于**判据没被压成口号。\n"
        "* **复核者不可用时（L1）**：**不跳过复核**；或**如实标悬置**。\n"
        "* 依据（标准名/编号）：IEEE 1028、ISO 10007。\n")

    def _write_all(self, verify=None, review=None, maint=None, entry=None):
        self.write("specs/general/verify.adoc",
                   verify if verify is not None else self.VERIFY)
        self.write("specs/general/review.adoc",
                   review if review is not None else self.REVIEW)
        self.write("specs-project-maintainer/verify.adoc",
                   maint if maint is not None else
                   "= 维护方验证\n* 见「改完规范必做的五件事（机械手段必跑，干净子 agent 复核不可漏）」；"
                   "运行 check_specs_test.py 与 check_effective_test.py；"
                   "**有了就忽略、没有就加**。\n")
        self.write("AGENTS.adoc",
                   entry if entry is not None else
                   "= 项目规范\n* 见「改完规范必做的五件事（机械手段必跑，"
                   "干净子 agent 复核不可漏）」；机械手段须跑全；子 agent 复核不可漏。\n")

    def test_positive_passes(self):
        self._write_all()
        cm.check_after_change_review_guard()
        self.assertEqual([], cm.errors)

    def test_verify_section_deleted_reports(self):
        self._write_all(verify="= 验证规范\n\n== 别的\n* x\n")
        cm.check_after_change_review_guard()
        self.assertIn("改完规范必做的五件事", self.error_texts())

    def test_mechanical_first_removed_reports(self):
        self._write_all(verify=self.VERIFY.replace("**全量扫描**", "查一下"))
        cm.check_after_change_review_guard()
        self.assertIn("全量扫描", self.error_texts())

    def test_clean_agent_rule_removed_reports(self):
        self._write_all(verify=self.VERIFY.replace(
            "**没有就加**，补在**项目自身规范**里。", "。"))
        cm.check_after_change_review_guard()
        self.assertIn("没有就加", self.error_texts())

    def test_three_state_ledger_removed_reports(self):
        self._write_all(verify=self.VERIFY.replace("**不得合并**", "可合并"))
        cm.check_after_change_review_guard()
        self.assertIn("不得合并", self.error_texts())

    def test_downgrade_path_removed_reports(self):
        self._write_all(verify=self.VERIFY.replace(
            "**不得跳过复核**；不得换**外部来源**；", ""))
        cm.check_after_change_review_guard()
        self.assertIn("不得跳过复核", self.error_texts())

    def test_scope_boundary_removed_reports(self):
        self._write_all(verify=self.VERIFY.replace("**代码类改动不做三视角**", "都要做三视角"))
        cm.check_after_change_review_guard()
        self.assertIn("代码类改动不做三视角", self.error_texts())

    def test_change_review_section_deleted_reports(self):
        self._write_all(review="= code review 规范\n\n== 问题修复\n* x\n")
        cm.check_after_change_review_guard()
        self.assertIn("改动后的 review", self.error_texts())

    def test_every_change_removed_reports(self):
        self._write_all(review=self.REVIEW.replace("**本次改动的全部产物**", "大改动"))
        cm.check_after_change_review_guard()
        self.assertIn("本次改动的全部产物", self.error_texts())

    def test_mechanical_only_removed_reports(self):
        self._write_all(review=self.REVIEW.replace(
            "**跑绿了** **不等于**判据没被压成口号。", "跑绿就行。"))
        cm.check_after_change_review_guard()
        self.assertIn("跑绿了", self.error_texts())

    def test_maintainer_landing_removed_reports(self):
        self._write_all(maint="= 维护方验证\n* 别的\n")
        cm.check_after_change_review_guard()
        self.assertIn("specs-project-maintainer/verify.adoc", self.error_texts())

    def test_entry_landing_removed_reports(self):
        self._write_all(entry="= 项目规范\n* 别的\n")
        cm.check_after_change_review_guard()
        self.assertIn("AGENTS.adoc", self.error_texts())

if __name__ == "__main__":
    unittest.main(verbosity=2)
