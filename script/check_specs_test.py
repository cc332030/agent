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
        self._orig = (cm.REPO_ROOT, cm.GENERIC_FILE, cm.SPECS_DIR, cm.INSTALL_FILE,
                      cm.PROJECT_FILE)
        self.root = tempfile.mkdtemp()
        cm.REPO_ROOT = self.root
        cm.GENERIC_FILE = os.path.join(self.root, "AGENTS_COMMON.adoc")
        cm.SPECS_DIR = os.path.join(self.root, "specs")
        cm.INSTALL_FILE = os.path.join(self.root, "INSTALL.adoc")
        cm.PROJECT_FILE = os.path.join(self.root, "AGENTS.adoc")

    def tearDown(self) -> None:
        cm.errors.clear()
        (cm.REPO_ROOT, cm.GENERIC_FILE, cm.SPECS_DIR, cm.INSTALL_FILE,
         cm.PROJECT_FILE) = self._orig
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, relpath: str, content: str) -> None:
        """在临时根下按相对路径写文件（自动建父目录）。"""
        p = os.path.join(self.root, relpath)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)

    def error_texts(self) -> str:
        return "\n".join(cm.errors)


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

    def test_placeholder_and_dir_excluded(self):
        text = ("`specs/...` `specs/stack/` `specs/stack/<语言>-testing.adoc` "
                "link:../stack/<语言>-testing.adoc[]")
        self.assertEqual(cm.extract_specs_refs(text, base_dir="specs/core"), [])

    def test_dedupe_preserve_order(self):
        text = "`specs/stack/java.adoc` `specs/stack/java.adoc` link:../stack/java.adoc[]"
        self.assertEqual(cm.extract_specs_refs(text, base_dir="specs/general"),
                         ["specs/stack/java.adoc"])


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

    def test_wellformed_template_passes(self):
        self.write("INSTALL.adoc", self.TEMPLATE)
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
    """钉住 L1/L2/L3 分级与最高关注项 P1/P2/P3/P4 的存在性与级别。"""

    def _write_valid(self):
        # 五个最高关注项各自级别（P1/P2/P3/P5 条款本身 L1、P4 条款本身 L2 但同列最高关注项）；
        # 定级口径与自身重构已归位通用层 spec-lifecycle.adoc（由准入防线钉住），
        # 故必加载层不再出现这些方法论节。
        self.write("specs/core/priority.adoc",
                   "= 规范优先级\n\n"
                   "**L1 强制**/**L2 建议**/**L3 允许**\n\n"
                   "常驻层只给\"怎么走\"（规则 + 判定标准 + 依据名），不铺开原因与取舍。\n\n"
                   "== 分级定义（L1 / L2 / L3）\n\n"
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
                   "* **依据**：ISO 10007。\n")
        self.write("specs/core/execution.adoc",
                   "文件移动必须使用 `git mv`，禁止 delete+create\n"
                   "读取范围与长会话上下文治理见 `specs/general/context.adoc`。\n"
                   "== 破坏性操作\n不可逆操作先确认；不得编造见 `specs/general/source.adoc`。\n")

    def test_valid_priority_file_passes(self):
        self._write_valid()
        cm.check_priority_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_priority_file_reports(self):
        # 反例：优先级文件整体被删
        self.write("specs/core/execution.adoc", "git mv context.adoc")
        cm.check_priority_guard()
        self.assertIn("缺少规范优先级文件", self.error_texts())

    def test_missing_level_definition_reports(self):
        # 反例：L2/L3 分级被删（只剩 L1）
        self.write("specs/core/priority.adoc",
                   "= t\n**L1 强制**\n不可降级 P1 git mv P2 完整性 P3 内容不得减少\n")
        self.write("specs/core/execution.adoc", "git mv context.adoc")
        cm.check_priority_guard()
        self.assertIn("L2 建议", self.error_texts())
        self.assertIn("L3 允许", self.error_texts())

    def test_dropped_top_priority_item_reports(self):
        # 反例：最高关注项 P1 被删（重构/去重最危险的误删）
        self.write("specs/core/priority.adoc",
                   "= t\n**L1 强制**/**L2 建议**/**L3 允许**\n"
                   "不可降级 P2 完整性 P3 内容不得减少 P4 读取按最小必要 P5 不可逆操作\n")
        self.write("specs/core/execution.adoc",
                   "git mv context.adoc 破坏性操作 source.adoc")
        cm.check_priority_guard()
        self.assertIn("P1", self.error_texts())

    def test_dropped_non_downgrade_declaration_reports(self):
        # 反例：去掉"不可降级"声明 = 允许最高关注项被降级
        self._write_valid()
        path = os.path.join(self.root, "specs", "core", "priority.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace("最高关注项**不可降级**：", "最高关注项：")
        self.write("specs/core/priority.adoc", text)
        cm.check_priority_guard()
        self.assertIn("不可降级", self.error_texts())

    def test_execution_missing_git_mv_reports(self):
        # 反例：最高关注项 P1 的必加载层落点被改写
        self._write_valid()
        self.write("specs/core/execution.adoc", "文件操作见相关规范\n")
        cm.check_priority_guard()
        self.assertIn("git mv", self.error_texts())

    def test_leveling_method_moved_back_to_always_on_reports(self):
        # 反例：定级方法论（属通用层、"写规范时"才用）又涨回必加载层 → 每次会话都为它付上下文
        self._write_valid()
        path = os.path.join(self.root, "specs", "core", "priority.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.write("specs/core/priority.adoc",
                   text + "\n== 设级别（定级口径四问）\n违反后果/豁免性/可验证性\n")
        cm.check_priority_guard()
        self.assertIn("设级别", self.error_texts())

    def test_dropped_how_to_walk_declaration_reports(self):
        # 反例：常驻层"只给怎么走"的形态声明被删 → 常驻层又会把原因与取舍铺回每个条目
        self._write_valid()
        path = os.path.join(self.root, "specs", "core", "priority.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace(
                "常驻层只给\"怎么走\"（规则 + 判定标准 + 依据名），不铺开原因与取舍。\n", "")
        self.write("specs/core/priority.adoc", text)
        cm.check_priority_guard()
        self.assertIn("怎么走", self.error_texts())

    def test_dropped_basis_line_reports(self):
        # 反例：某最高关注项的『依据』行被整段删掉（依据可压成标准名/编号，但不能消失）
        self._write_valid()
        path = os.path.join(self.root, "specs", "core", "priority.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace("* **依据**：ISO 10007。\n", "")
        self.write("specs/core/priority.adoc", text)
        cm.check_priority_guard()
        self.assertIn("依据", self.error_texts())

    def test_silently_downgraded_p1_reports(self):
        # 反例：P1-P3 被静默从 L1 降级为 L2（最高关注项条款本身即 L1 铁律）
        self._write_valid()
        path = os.path.join(self.root, "specs", "core", "priority.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace(
                "**要求（L1，最高）**：不得用 delete+create 代替。",
                "**要求（L2 建议）**：不得用 delete+create 代替。")
        self.write("specs/core/priority.adoc", text)
        cm.check_priority_guard()
        self.assertIn("P1", self.error_texts())

    def test_silently_promoted_p4_reports(self):
        # 反例：P4 被静默从 L2 改标为 L1（级别不得顺手改写，须按定级口径判定）
        self._write_valid()
        path = os.path.join(self.root, "specs", "core", "priority.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace(
                "* **要求（L2 建议，最高关注项）**：只读最小必要信息集。",
                "* **要求（L1，最高）**：只读最小必要信息集。")
        self.write("specs/core/priority.adoc", text)
        cm.check_priority_guard()
        self.assertIn("P4", self.error_texts())

    def test_silently_downgraded_p5_reports(self):
        # 反例：P5 被静默从 L1 降级为 L2（不可逆操作与来源真实性属无裁量余地的底线）
        self._write_valid()
        path = os.path.join(self.root, "specs", "core", "priority.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace(
                "**要求（L1，最高）**：不可逆操作先确认；不得编造事实与来源。",
                "**要求（L2 建议）**：不可逆操作先确认；不得编造事实与来源。")
        self.write("specs/core/priority.adoc", text)
        cm.check_priority_guard()
        self.assertIn("P5", self.error_texts())

    def test_dropped_context_read_item_reports(self):
        # 反例：最高关注项 P4（读取按最小必要/长会话上下文治理）被删
        self.write("specs/core/priority.adoc",
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
        self.assertIn("context.adoc", self.error_texts())

    def test_dropped_destructive_op_item_reports(self):
        # 反例：最高关注项 P5（不可逆操作先确认 + 不得编造）被删
        self.write("specs/core/priority.adoc",
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
        # 反例：P5 的专项落点（来源真实性规范引用）被删
        self._write_valid()
        self.write("specs/core/execution.adoc",
                   "git mv context.adoc 破坏性操作\n")
        cm.check_priority_guard()
        self.assertIn("source.adoc", self.error_texts())


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
        cm.ADMISSION_FILE = os.path.join(self.root, "specs", "general",
                                         "spec-lifecycle.adoc")

    def tearDown(self) -> None:
        cm.ADMISSION_FILE = self._orig_admission
        super().tearDown()

    def _write_valid(self):
        # 实现用「仓库根相对路径」登记/引用（与调度器口径一致），测试文件写在临时根下
        self.write("specs/general/spec-lifecycle.adoc",
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
                   "通用层登记 `specs/general/spec-lifecycle.adoc`")
        self.write("AGENTS.adoc", "见 `specs/general/spec-lifecycle.adoc`")

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
        self.write("specs/general/spec-lifecycle.adoc",
                   "= t\n\n== 公共规范还是项目规范\n\n== 提案校验\n\n"
                   "检查是否已有标准；检查是否已有本项目条目；升级与举一反三。\n")
        self.write("AGENTS_COMMON.adoc", "登记 `specs/general/spec-lifecycle.adoc`")
        self.write("AGENTS.adoc", "见 `specs/general/spec-lifecycle.adoc`")
        cm.check_spec_admission_guard()
        self.assertIn("准入判定", self.error_texts())

    def test_dropped_escalation_point_reports(self):
        # 反例：举一反三（升级要求）被删 → 新增只会照抄用户原话
        self.write("specs/general/spec-lifecycle.adoc",
                   "= t\n\n== 公共规范还是项目规范\n\n== 准入判定\n\n"
                   "== 提案校验\n\n检查是否已有标准；检查是否已有本项目条目。\n")
        self.write("AGENTS_COMMON.adoc", "登记 `specs/general/spec-lifecycle.adoc`")
        self.write("AGENTS.adoc", "见 `specs/general/spec-lifecycle.adoc`")
        cm.check_spec_admission_guard()
        self.assertIn("举一反三", self.error_texts())

    def test_dropped_leveling_criteria_reports(self):
        # 反例：定级口径（四问/判定表等）被删 → 条目级别再无判定依据、级别会重新混乱
        self._write_valid()
        path = os.path.join(self.root, "specs", "general", "spec-lifecycle.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        text = text.split("== 如何给一条规范定级")[0] + "== 新增规范的提案校验\n\n" + \
            text.split("== 新增规范的提案校验")[1]
        self.write("specs/general/spec-lifecycle.adoc", text)
        cm.check_spec_admission_guard()
        self.assertIn("如何给一条规范定级", self.error_texts())

    def test_dropped_refactor_order_reports(self):
        # 反例：规范自身重构的判断顺序被删 → 会先删后想，把放错位置的内容直接删掉
        self._write_valid()
        path = os.path.join(self.root, "specs", "general", "spec-lifecycle.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.write("specs/general/spec-lifecycle.adoc",
                   text.replace("先判归属 → 再判层级 → 再判重复 → 最后压缩表述。", "重构一下。"))
        cm.check_spec_admission_guard()
        self.assertIn("先判归属", self.error_texts())

    def test_dropped_reading_shape_reports(self):
        # 反例：读法形态判据被删 → "执行侧只给怎么走、依据归决策侧"的口径丢失，
        # 规范重新变成"给执行者一堆解释"或"为简洁把依据删掉"两个极端
        self._write_valid()
        path = os.path.join(self.root, "specs", "general", "spec-lifecycle.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        text = text.split("== 同一条规则有两种读法")[0] + "== 规范集合的自身重构" + \
            text.split("== 规范集合的自身重构")[1]
        self.write("specs/general/spec-lifecycle.adoc", text)
        cm.check_spec_admission_guard()
        self.assertIn("同一条规则有两种读法", self.error_texts())

    def test_dropped_effectiveness_check_reports(self):
        # 反例：重构后的有效性核对被删 → 只查"内容丢没丢"，判据被压成口号/依据被删无人拦
        self._write_valid()
        path = os.path.join(self.root, "specs", "general", "spec-lifecycle.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace(
                "重构后须核对规范有效性（两形态分离 / 可执行性不降级 / 可见性不丢）。\n", "")
        self.write("specs/general/spec-lifecycle.adoc", text)
        cm.check_spec_admission_guard()
        self.assertIn("重构后须核对规范有效性", self.error_texts())

    def test_not_registered_in_dispatcher_reports(self):
        # 反例：文件存在但未登记调度器 → 永不被加载、规则实际失效
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "= t")
        cm.check_spec_admission_guard()
        self.assertIn("未在加载调度器登记", self.error_texts())

    def test_missing_project_landing_point_reports(self):
        # 反例：AGENTS.adoc 未指向准入规范 → 本仓库新增规范时不按其执行
        self._write_valid()
        self.write("AGENTS.adoc", "= 项目自身规范\n")
        cm.check_spec_admission_guard()
        self.assertIn("维护落点", self.error_texts())


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
    加约束，故不得再引入：如曾短暂加入的 `check_git_mv_usage`（读取 git status /
    diff --cached / show HEAD:path 判断 delete+create）。本用例钉住这一边界。
    """

    def test_no_git_state_checks(self):
        # 判据是"是否读取 git 状态"，不是"是否出现 git 字样"——规范正文/注释里出现
        # `git mv` 属正常（它本身就是通用规范的铁律），故只钉住对 git 的调用与取值。
        src = open(os.path.join(HERE, "check_specs.py"), encoding="utf-8").read()
        for bad in ('"git",', "'git'", "git diff", "git status", "HEAD:{", "diff --cached"):
            self.assertNotIn(bad, src,
                             f"check_specs.py 不得读取 git 工作区状态（发现 {bad!r}）："
                             "本仓库内容主要给其他项目用，引用方工作区操作不可见")

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


if __name__ == "__main__":
    unittest.main(verbosity=2)


# --------------------------------------------------------------------------- #
# check_prompts_primary（提示词主侧重与优先级防线：方向不得被删/降级）
# --------------------------------------------------------------------------- #
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
        self.assertIn("self-check.adoc", self.error_texts())

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
