#!/usr/bin/env python3
"""install-line-ending-hook.py 的单元测试（纯 stdlib，临时 git 仓库）。"""

import importlib.util
import os
import stat
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))

_SPEC = importlib.util.spec_from_file_location(
    "install_line_ending_hook", os.path.join(HERE, "install-line-ending-hook.py"))
inst = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(inst)


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


class TestInstall(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.src = os.path.join(self.root, "landing")
        self.repo = os.path.join(self.root, "project")
        os.makedirs(self.src, exist_ok=True)
        # 落点里 `[scripts].all` 按文件名拍平到根（见 fetch-specs 的 `target_path`）。
        with open(os.path.join(self.src, inst.SCAN_NAME), "w", encoding="utf-8") as f:
            f.write("#!/usr/bin/env python3\nprint('scan')\n")
        os.makedirs(self.repo, exist_ok=True)
        _git(self.repo, "init", "-q")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def test_install_writes_hook_and_sets_hooks_path(self):
        summary = inst.install(self.repo, self.src)
        self.assertIn("core.hooksPath=.githooks", summary)
        hook = os.path.join(self.repo, ".githooks", "pre-commit")
        self.assertTrue(os.path.isfile(hook))
        self.assertTrue(os.stat(hook).st_mode & stat.S_IXUSR)
        self.assertTrue(os.path.isfile(os.path.join(self.repo, "script", "guard", inst.SCAN_NAME)))
        out = _git(self.repo, "config", "--local", "core.hooksPath")
        self.assertEqual(out.stdout.strip(), ".githooks")

    def test_non_git_dir_raises(self):
        target = os.path.join(self.root, "not-a-repo")
        os.makedirs(target)
        with self.assertRaises(RuntimeError):
            inst.install(target, self.src)

    def test_structured_source_layout_also_works(self):
        # 兼容带 script/guard/ 结构的源目录（如直接指向仓库 script/ 时）。
        os.remove(os.path.join(self.src, inst.SCAN_NAME))
        os.makedirs(os.path.join(self.src, "script", "guard"), exist_ok=True)
        with open(os.path.join(self.src, "script", "guard", inst.SCAN_NAME), "w", encoding="utf-8") as f:
            f.write("#!/usr/bin/env python3\nprint('scan')\n")
        inst.install(self.repo, self.src)
        self.assertTrue(os.path.isfile(os.path.join(self.repo, "script", "guard", inst.SCAN_NAME)))

    def test_missing_scan_source_raises(self):
        os.remove(os.path.join(self.src, inst.SCAN_NAME))
        with self.assertRaises(RuntimeError):
            inst.install(self.repo, self.src)


if __name__ == "__main__":
    unittest.main()
