#!/usr/bin/env python3
"""check-effective.py 的单元测试（纯 stdlib unittest）。

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
    "check_effective", os.path.join(HERE, "check-effective.py"))
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
        self._mk("script/check-specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(statuses["内部链接须用相对路径、禁根绝对"], "has-grip")

    def test_grip_file_missing_is_grip_missing(self):
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(statuses["内部链接须用相对路径、禁根绝对"], "grip-missing")

    def test_none_grip_is_no_grip(self):
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(statuses["文件移动/重命名必须 git mv（防历史断裂）"], "no-grip")


if __name__ == "__main__":
    unittest.main(verbosity=2)