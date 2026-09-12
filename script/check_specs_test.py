#!/usr/bin/env python3
"""check_specs.py 的单元测试（纯 stdlib unittest，零第三方依赖）。

针对每个检查函数覆盖正例与反例：
  * extract_specs_refs     —— 引用提取与归一化（根反引号 / link 相对 / 各类剔除）
  * check_refs_exist       —— 引用存在性（正：存在；反：悬空引用）
  * check_link_refs        —— 链接格式（正：相对且合法；反：根绝对 / 越出仓库根）
  * check_section_refs     —— 节名引用存在性（正：节存在；反：节已改名/删除）
  * check_stack_consistency—— 技术栈双向一致（正：登记且存在；反：漏登记 / 登记不存在）
  * check_forbidden_patterns—— 私有约定误导入（正：无命中；反：命中）
  * check_filler_docs      —— 文档注水兜底（正：简短条目/标题词+内容/纯格式行不误报；反：占位段/完全重复段）
  * check_self_check_guard —— 自检防线（正：自检规范+落点+登记齐备；反：文件被删/要点缺失/落点缺失/未登记）
  * check_source_guard     —— 来源防线（正：来源规范要点齐备；反：文件被删/要点缺失/未登记）
  * check_java_test_naming —— Java 测试类命名防线（正：两侧四类后缀判据齐备；反：后缀被删/调度器口径漂移）
  * check_line_ending_guard —— 换行符防线（正：LF 基准 + `.bat`/`.cmd` CRLF + `.gitattributes` 齐备；反：文件被删/判据缺失/栈文件未写行尾/未登记）
  * check_verify_guard   —— 规范验证防线（正：两问定式化节 + P2 + 本仓库落点三处一致；
                             反：文件被删/节改名/第二问被删/P2 或本仓库口径未同步/未登记）
  * check_priority_guard 另钉『怎么走』形态声明与各最高关注项的『依据』行（反：形态声明被删/依据被整段删）
  * check_spec_admission_guard 另钉读法形态与重构后的有效性核对（反：两节被删）

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
        self.write("specs/general/testing.adoc",
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
                   "=== P4. 读取按最小必要\n\n"
                   "* **要求（L2 建议，最高关注项）**：只读最小必要信息集。\n"
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
                "* **要求（L2 建议，最高关注项）**：只读最小必要信息集。",
                "* **要求（L1，最高）**：只读最小必要信息集。")
        self.write("specs-project-maintainer/priority.adoc", text)
        cm.check_priority_guard()
        self.assertIn("P4", self.error_texts())

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



def _valid_adoption_body() -> str:
    """生成一份含全部要点锚点的『规范准入与自身取舍』主题正文（正例基准）。

    与 `cm._LIBRARY_ADOPTION_ANCHORS` 同源：锚点即判据句，缺一即"同义性差异未写明"。
    """
    head = "= 规范准入与自身取舍的依据（依据图书馆）\n\n本文件是依据图书馆的主题之一。\n\n"
    return head + "\n".join("- " + q for q in cm._LIBRARY_ADOPTION_ANCHORS) + "\n"


class TestCheckLibraryGuard(CheckSpecsTestCase):
    """钉住『图书馆防线』：依据须查得到、对得上、引用不悬空（本仓库私有内容）。

    依据不能只存在名称——规则执行久了就退化成"只记得是这么做的"，无法判断它还成不
    成立、无法据以取舍（specs/general/verify.adoc「验证总纲」的"防慢慢脱离初衷"）。
    图书馆（**仓库根 `library/`**，本仓库私有、不随规范分发）是依据的落点，故其
    存在性、入口登记、逐字引文与引用可解析性都由本条机械钉住；**不再核对"自足性/
    是否夹带私有落点"**——那是对公共内容的要求（私有内容本来就可以引用自己仓库的
    任何落点），图书馆搬出 `specs/` 后该约束自然不再适用。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_lib = (cm.LIBRARY_DIR, cm.LIBRARY_INDEX, cm.LIBRARY_TOPICS)
        self._orig_project = cm.PROJECT_FILE
        cm.LIBRARY_DIR = os.path.join(self.root, "library")
        cm.LIBRARY_INDEX = os.path.join(cm.LIBRARY_DIR, "README.adoc")
        cm.LIBRARY_TOPICS = ("sources.adoc", "adoption.adoc")
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
                   "| link:adoption.adoc[] | 规范准入与自身取舍的依据——同义性差异与覆盖点\n")
        self.write("library/sources.adoc",
                   "= 外部标准原文摘录\n\n"
                   + "\n".join("- " + q for q in cm.LIBRARY_QUOTE_ANCHORS)
                   + "\n")
        self.write("library/adoption.adoc", _valid_adoption_body())

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
                   "= 图书馆\n\n| link:sources.adoc[] | 见 `PROMPTS.adoc`\n")
        cm.check_library_guard()
        self.assertIn("指向不存在的文件", self.error_texts())

    def test_root_level_file_ref_resolvable_passes(self):
        # 正例：根级文件名写法命中真实文件 → 不报
        self._write_valid()
        self.write("PROMPTS.adoc", "= 提示词\n")
        self.write("library/README.adoc",
                   "= 图书馆\n\n| link:sources.adoc[] | 见 `PROMPTS.adoc` 与 `AGENTS.adoc`\n"
                   "| link:adoption.adoc[] | 规范准入与自身取舍的依据——同义性差异与覆盖点\n")
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


if __name__ == "__main__":

    unittest.main(verbosity=2)


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

    验证的**规则**属公共内容（落 `specs/general/testing.adoc`「验证与运行契约」）——
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
        return os.path.join(self.root, "specs", "general", "testing.adoc")

    def _write_valid(self):
        self.write("specs/general/testing.adoc",
                   "= 测试规范（通用层，跨语言）\n\n"
                   "== 验证与运行契约\n\n"
                   "* 以真实结果为准。\n\n"
                   "=== 判准维度：严格执行 / 尽力而为\n\n严格执行与尽力而为两档，都须留证。\n\n"
                   "=== 验证的适用边界\n\n先判改动性质；代码类改动 / 规范类改动；"
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
        self.write("specs/general/testing.adoc",
                   t.replace("=== 验证总纲（回答\"验证什么、怎么算过\"）", "=== 随便什么节"))
        cm.check_verify_guard()
        self.assertIn("验证总纲", self.error_texts())

    def test_missing_adoption_lens_reports(self):
        # 反例：删掉③接纳面（回到"只面对方规范本体与本仓库"的旧口径）
        self._write_valid()
        p = self._pub()
        t = open(p, encoding="utf-8").read()
        self.write("specs/general/testing.adoc", t.replace("③接纳面", "某某面"))
        cm.check_verify_guard()
        self.assertIn("③接纳面", self.error_texts())

    def test_missing_effectiveness_grades_section_reports(self):
        # 反例：删掉「验证的效力等级」节（回到"把复核结论当依据、把找不到问题当交付前提"）
        self._write_valid()
        p = self._pub()
        t = open(p, encoding="utf-8").read()
        self.write("specs/general/testing.adoc",
                   t.replace("=== 验证的效力等级", "=== 随便什么节"))
        cm.check_verify_guard()
        self.assertIn("效力等级", self.error_texts())

    def test_missing_concept_grade_boundary_reports(self):
        # 反例：去掉"不得阻断交付"这条边界（把复核当交付前置条件）
        self._write_valid()
        p = self._pub()
        t = open(p, encoding="utf-8").read()
        self.write("specs/general/testing.adoc", t.replace("不得当作阻断交付的条件", "另说"))
        cm.check_verify_guard()
        self.assertIn("不得当作阻断交付的条件", self.error_texts())

    def test_missing_standard_sources_reports(self):
        # 反例：标准出处被删（验证退化成"把脚本跑绿"、无从核对判据出自哪里）
        self._write_valid()
        p = self._pub()
        t = open(p, encoding="utf-8").read()
        self.write("specs/general/testing.adoc", t.replace("ISO/IEC Directives Part 2", "某标准"))
        cm.check_verify_guard()
        self.assertIn("ISO/IEC Directives Part 2", self.error_texts())

    def test_missing_runtime_contract_section_reports(self):
        # 反例：③只在文字上出现、却指不到判据（「运行契约」节被删）
        self._write_valid()
        p = self._pub()
        t = open(p, encoding="utf-8").read()
        self.write("specs/general/testing.adoc",
                   t.replace("=== 运行契约（公共内容被未知项目加载时的可控性）", "=== 别的节"))
        cm.check_verify_guard()
        self.assertIn("运行契约", self.error_texts())

    def test_dropped_criterion_reports(self):
        # 反例：重构时把②的判据中的「读的形态」静默删掉（内容减少，不是等价改写）
        self._write_valid()
        p = self._pub()
        t = open(p, encoding="utf-8").read()
        self.write("specs/general/testing.adoc", t.replace("读的形态", "某某形态"))
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
        self.write("specs/general/testing.adoc", "= 测试规范\n\n== 单元测试\n\n只测必要。\n")
        cm.check_adoption_guard()
        self.assertIn("运行契约", self.error_texts())

    def test_adoption_guard_missing_dimension_reports(self):
        # 反例：三维中少一维（如可控性被删）= 判据不完整
        self.write("specs/general/testing.adoc",
                   "= 测试规范\n\n== 运行契约（未知项目加载）\n\n"
                   "① 影响面；② 成本；降级路径；不得让引用方依赖本仓库私有物；"
                   "依据 ISO 9241-110；接纳面须留证。\n")
        self.write("specs-project-maintainer/context.adoc",
                   "= 维护方清单\n\n运行契约：影响面 / 成本 / 可控性三维。\n")
        cm.check_adoption_guard()
        self.assertIn("③ 可控性", self.error_texts())

    def test_adoption_guard_missing_maintainer_list_reports(self):
        # 反例：维护方承接清单被删（维护方在新增公共内容时的核对职责无人承载）
        self.write("specs/general/testing.adoc",
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
        return ("== 验证的适用范围\n\n见 `specs/general/testing.adoc`「验证与运行契约」之"
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
        self.write("specs/general/testing.adoc",
                   "= 测试规范\n\n== 验证与运行契约\n\n=== 验证的适用边界\n\n"
                   "先判改动性质：代码类改动按机械判据判过不过、规范类改动做三视角；"
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
        self.write("specs/general/testing.adoc", "= 测试规范\n\n== 单元测试\n\n跑。\n")
        self.write("AGENTS.adoc", "== 验证的适用范围\n\n见 `specs/general/testing.adoc`"
                   + "「验证与运行契约」；拆分判据见「一条规范何时该拆分」。\n")
        cm.check_lifecycle_guard()
        self.assertIn("验证的适用边界", self.error_texts())

    def test_missing_fresh_context_requirement_reports(self):
        # 反例：删掉"每次验证换一个干净上下文"（复用上下文等于自己复核自己）
        self._write_valid()
        self.write("specs/general/testing.adoc",
                   "= 测试规范\n\n== 验证与运行契约\n\n=== 验证的适用边界\n\n"
                   "先判改动性质：代码类改动按机械判据判过不过、规范类改动做三视角；"
                   "判据是「会不会被未知项目加载」；不得互串；取**更严的一侧**。\n")
        self.write("AGENTS.adoc", self._own_text())
        cm.check_lifecycle_guard()
        self.assertIn("干净上下文", self.error_texts())

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
                 "（测试类命名契约：`Tests` 常规、`BootTests` 启动型、`PerfTests` 性能、`IT` 端到端）")

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
                   "`PerfTests` 性能、`IT` 端到端；后者独立于常规测试执行。\n")
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
                   "由 `.gitattributes` 固定，`core.autocrlf` 交给仓库配置、不靠人工手动调整。\n")
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
