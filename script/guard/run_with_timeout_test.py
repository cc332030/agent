#!/usr/bin/env python3
"""`run_with_timeout` 的单元测试（纯 stdlib unittest）。

覆盖三件事：① 正常命令的退出码**原样透传**（不得被本工具改写）；② 卡住的命令**到点被终止**
且退出码是约定的 `TIMEOUT_EXIT_CODE`；③ 超时时**已产出的输出被保留**（那是排查"停在哪一步"
的依据，丢了就等于没做处置）。
"""

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
_SPEC = importlib.util.spec_from_file_location(
    "run_with_timeout", os.path.join(HERE, "run_with_timeout.py"))
rwt = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rwt)  # type: ignore[union-attr]

PY = sys.executable


class TestRunWithTimeout(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_exit_code_passthrough(self):
        code = rwt.run([PY, "-c", "import sys; sys.exit(3)"], timeout=30, quiet=True)
        self.assertEqual(3, code)

    def test_success_is_zero(self):
        code = rwt.run([PY, "-c", "print('ok')"], timeout=30, quiet=True)
        self.assertEqual(0, code)

    def test_timeout_kills_and_reports(self):
        code = rwt.run([PY, "-c", "import time; time.sleep(60)"], timeout=1.5, quiet=True)
        self.assertEqual(rwt.TIMEOUT_EXIT_CODE, code)

    def test_timeout_keeps_partial_output(self):
        out = os.path.join(self.tmp, "out.txt")
        code = rwt.run([PY, "-c",
                        "import time; print('stopped-here', flush=True); time.sleep(60)"],
                       timeout=1.5, stdout_path=out, quiet=True)
        self.assertEqual(rwt.TIMEOUT_EXIT_CODE, code)
        with open(out, encoding="utf-8") as fh:
            self.assertIn("stopped-here", fh.read())

    def test_missing_command_is_not_silent(self):
        code = rwt.run(["definitely-not-a-command-xyz"], timeout=5, quiet=True)
        self.assertEqual(127, code)

    def test_cli_usage_error(self):
        code = rwt.main(["--timeout", "5", "--"])
        self.assertEqual(2, code)

    def test_default_timeout_from_env(self):
        env = dict(os.environ, OPERATION_TIMEOUT="1")
        proc = subprocess.run(
            [PY, os.path.join(HERE, "run_with_timeout.py"), "--quiet", "--",
             PY, "-c", "import time; time.sleep(60)"],
            env=env, capture_output=True, text=True)
        self.assertEqual(rwt.TIMEOUT_EXIT_CODE, proc.returncode)


if __name__ == "__main__":
    unittest.main(verbosity=2)
