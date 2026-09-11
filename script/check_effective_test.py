#!/usr/bin/env python3
"""check_effective.py 的单元测试（纯 stdlib unittest）。

覆盖 evaluate() 的抓手判定（正例/反例）与机制清单的完整性。注入临时 root，
不依赖真实仓库。
"""

import importlib.util
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))

_SPEC = importlib.util.spec_from_file_location(
    "check_effective", os.path.join(HERE, "check_effective.py"))
eff = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(eff)  # type: ignore[union-attr]


class TestEvaluate(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def _mk(self, rel: str) -> None:
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write("")

    def test_mechanisms_are_unique_and_nonempty(self):
        names = [m[0] for m in eff.MECHANISMS]
        self.assertEqual(len(names), len(set(names)))
        self.assertGreaterEqual(len(names), 5)

    def test_grip_file_present_is_has_grip(self):
        self._mk("script/check_specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(statuses["内部链接须用相对路径、禁根绝对"], "has-grip")

    def test_grip_file_missing_is_grip_missing(self):
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(statuses["内部链接须用相对路径、禁根绝对"], "grip-missing")

    def test_none_grip_is_no_grip(self):
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(statuses["测试文件后缀式命名（禁 test_ 前戳）"], "no-grip")

    def test_git_mv_has_no_mechanical_grip(self):
        # git mv 铁律作用于**引用方项目**的工作区，本仓库看不到其操作，故如实记为"无机械抓手"
        # （不得用只在本地工作区才有效的检查冒充抓手）
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(statuses["文件移动/重命名必须 git mv（防历史断裂）"], "no-grip")

    def test_scope_guard_has_mechanical_grip(self):
        # "校验范围只限公共内容与本仓库工具"由 check_specs_test 的用例钉住
        self._mk("script/check_specs_test.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(
            statuses["校验范围只限公共内容与本仓库工具（不检查引用方项目工作区）"], "has-grip")


if __name__ == "__main__":
    unittest.main(verbosity=2)
