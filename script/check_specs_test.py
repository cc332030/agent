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
        self._orig = (cm.REPO_ROOT, cm.GENERIC_FILE, cm.SPECS_DIR, cm.INSTALL_FILE)
        self.root = tempfile.mkdtemp()
        cm.REPO_ROOT = self.root
        cm.GENERIC_FILE = os.path.join(self.root, "AGENTS_COMMON.adoc")
        cm.SPECS_DIR = os.path.join(self.root, "specs")
        cm.INSTALL_FILE = os.path.join(self.root, "INSTALL.adoc")

    def tearDown(self) -> None:
        cm.errors.clear()
        cm.REPO_ROOT, cm.GENERIC_FILE, cm.SPECS_DIR, cm.INSTALL_FILE = self._orig
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
    """钉住 L1/L2/L3 分级与最高关注项 P1/P2/P3 的存在性与级别。"""

    def _write_valid(self):
        self.write("specs/core/priority.adoc",
                   "= 规范优先级\n\n"
                   "**L1 强制**/**L2 建议**/**L3 允许**\n\n"
                   "最高关注项**不可降级**：P1 git mv、P2 完整性、P3 内容不得减少\n")
        self.write("specs/core/execution.adoc",
                   "文件移动必须使用 `git mv`，禁止 delete+create\n")

    def test_valid_priority_file_passes(self):
        self._write_valid()
        cm.check_priority_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_priority_file_reports(self):
        # 反例：优先级文件整体被删
        self.write("specs/core/execution.adoc", "git mv")
        cm.check_priority_guard()
        self.assertIn("缺少规范优先级文件", self.error_texts())

    def test_missing_level_definition_reports(self):
        # 反例：L2/L3 分级被删（只剩 L1）
        self.write("specs/core/priority.adoc",
                   "= t\n**L1 强制**\n不可降级 P1 git mv P2 完整性 P3 内容不得减少\n")
        self.write("specs/core/execution.adoc", "git mv")
        cm.check_priority_guard()
        self.assertIn("L2 建议", self.error_texts())
        self.assertIn("L3 允许", self.error_texts())

    def test_dropped_top_priority_item_reports(self):
        # 反例：最高关注项 P1 被删（重构/去重最危险的误删）
        self.write("specs/core/priority.adoc",
                   "= t\n**L1 强制**/**L2 建议**/**L3 允许**\n不可降级 P2 完整性 P3 内容不得减少\n")
        self.write("specs/core/execution.adoc", "git mv")
        cm.check_priority_guard()
        self.assertIn("P1", self.error_texts())

    def test_dropped_non_downgrade_declaration_reports(self):
        # 反例：去掉"不可降级"声明 = 允许最高关注项被降级
        self.write("specs/core/priority.adoc",
                   "= t\n**L1 强制**/**L2 建议**/**L3 允许**\nP1 git mv P2 完整性 P3 内容不得减少\n")
        self.write("specs/core/execution.adoc", "git mv")
        cm.check_priority_guard()
        self.assertIn("不可降级", self.error_texts())

    def test_execution_missing_git_mv_reports(self):
        # 反例：最高关注项 P1 的必加载层落点被改写
        self._write_valid()
        self.write("specs/core/execution.adoc", "文件操作见相关规范\n")
        cm.check_priority_guard()
        self.assertIn("git mv", self.error_texts())


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
