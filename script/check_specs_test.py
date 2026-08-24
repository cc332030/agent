#!/usr/bin/env python3
"""check_specs.py 的单元测试（纯 stdlib unittest，零第三方依赖）。

针对每个检查函数覆盖正例与反例：
  * extract_specs_refs     —— 引用提取与归一化（根反引号 / link 相对 / 各类剔除）
  * check_refs_exist       —— 引用存在性（正：存在；反：悬空引用）
  * check_link_refs        —— 链接格式（正：相对且合法；反：根绝对 / 越出仓库根）
  * check_stack_consistency—— 技术栈双向一致（正：登记且存在；反：漏登记 / 登记不存在）
  * check_forbidden_patterns—— 私有约定误导入（正：无命中；反：命中）

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
        self._orig = (cm.REPO_ROOT, cm.GENERIC_FILE, cm.SPECS_DIR)
        self.root = tempfile.mkdtemp()
        cm.REPO_ROOT = self.root
        cm.GENERIC_FILE = os.path.join(self.root, "AGENTS_COMMON.adoc")
        cm.SPECS_DIR = os.path.join(self.root, "specs")

    def tearDown(self) -> None:
        cm.errors.clear()
        cm.REPO_ROOT, cm.GENERIC_FILE, cm.SPECS_DIR = self._orig
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
