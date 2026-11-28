#!/usr/bin/env python3
"""check_precommit_guard.py 与 install_git_hooks.py 的单元测试（纯 stdlib）。

覆盖：钩子齐备且调用实扫 → 全绿；钩子被删/不可执行/掏空、安装脚本被删/不指向
.githooks → 各自报缺口；安装脚本在缺 .git 的目录里拒绝安装。
"""

import os
import stat
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import check_precommit_guard as cpg  # noqa: E402
import install_git_hooks as igh  # noqa: E402


def _fixture(root):
    """造一份最小齐备的落点。"""
    os.makedirs(os.path.join(root, ".githooks"), exist_ok=True)
    os.makedirs(os.path.join(root, "script", "guard"), exist_ok=True)
    hook = os.path.join(root, ".githooks", "pre-commit")
    with open(hook, "w", encoding="utf-8") as f:
        f.write("#!/bin/sh\nexec python3 script/guard/check_line_ending.py --repo .\n")
    os.chmod(hook, os.stat(hook).st_mode | stat.S_IXUSR)
    with open(os.path.join(root, "script", "guard", "install_git_hooks.py"), "w", encoding="utf-8") as f:
        f.write('git config --local core.hooksPath .githooks\n')


class TestPrecommitGuard(unittest.TestCase):
    def test_complete_fixture_passes(self):
        with tempfile.TemporaryDirectory() as d:
            _fixture(d)
            self.assertEqual(cpg.check(d), [])

    def test_missing_hook_reports(self):
        with tempfile.TemporaryDirectory() as d:
            _fixture(d)
            os.remove(os.path.join(d, ".githooks", "pre-commit"))
            self.assertTrue(any("没有落点" in p for p in cpg.check(d)))

    def test_non_executable_hook_reports(self):
        with tempfile.TemporaryDirectory() as d:
            _fixture(d)
            hook = os.path.join(d, ".githooks", "pre-commit")
            os.chmod(hook, os.stat(hook).st_mode & ~stat.S_IXUSR)
            self.assertTrue(any("不可执行" in p for p in cpg.check(d)))

    def test_hook_not_calling_scan_reports(self):
        with tempfile.TemporaryDirectory() as d:
            _fixture(d)
            with open(os.path.join(d, ".githooks", "pre-commit"), "w", encoding="utf-8") as f:
                f.write("#!/bin/sh\necho hi\n")
            self.assertTrue(any("没有调用" in p for p in cpg.check(d)))

    def test_installer_not_pointing_to_hooks_reports(self):
        with tempfile.TemporaryDirectory() as d:
            _fixture(d)
            with open(os.path.join(d, "script", "guard", "install_git_hooks.py"), "w", encoding="utf-8") as f:
                f.write("print('nothing')\n")
            self.assertTrue(any("core.hooksPath" in p for p in cpg.check(d)))


class TestInstallPreconditions(unittest.TestCase):
    def test_non_git_dir_raises(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):
                igh.install(d)


if __name__ == "__main__":
    unittest.main()
