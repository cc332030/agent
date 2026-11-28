#!/usr/bin/env python3
"""check_line_ending.py 的单元测试（纯 stdlib，零 git 依赖地核解析逻辑）。

覆盖：索引侧 CRLF/mixed 必报、工作区与声明不符/混用必报、正确形态与空文件/二进制放行；
scan() 的前置条件（非 git 目录）与退出码由真实仓库的端到端在 CI 里覆盖。
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import check_line_ending as cle  # noqa: E402


class TestExpectedEol(unittest.TestCase):
    def test_lf_and_crlf_attrs(self):
        self.assertEqual(cle.expected_eol("text eol=crlf"), "crlf")
        self.assertEqual(cle.expected_eol("text eol=lf"), "lf")
        self.assertEqual(cle.expected_eol("text"), "lf")

    def test_binary_and_untext_skipped(self):
        self.assertIsNone(cle.expected_eol("binary"))
        self.assertIsNone(cle.expected_eol("-text"))
        self.assertIsNone(cle.expected_eol(""))


class TestEolViolations(unittest.TestCase):
    def test_index_crlf_reports(self):
        v = cle.eol_violations(["i/crlf    w/crlf  attr/text eol=lf\tREADME.adoc"])
        self.assertTrue(any("索引" in x and "README.adoc" in x for x in v))

    def test_index_mixed_reports(self):
        v = cle.eol_violations(["i/mixed   w/mixed  attr/text eol=lf\tREADME.adoc"])
        self.assertTrue(any("索引" in x for x in v))
        self.assertTrue(any("混用" in x for x in v))

    def test_worktree_mismatch_and_mixed_report(self):
        v = cle.eol_violations([
            "i/lf    w/crlf  attr/text eol=lf\tscript/a.py",
            "i/lf    w/mixed  attr/text eol=crlf\tscript/fetch.bat",
        ])
        self.assertTrue(any("script/a.py" in x and "不一致" in x for x in v))
        self.assertTrue(any("script/fetch.bat" in x and "mixed" in x for x in v))

    def test_correct_and_none_pass(self):
        v = cle.eol_violations([
            "i/lf    w/lf    attr/text eol=lf\tscript/a.py",
            "i/lf    w/crlf  attr/text eol=crlf\tscript/fetch.bat",
            "i/none  w/none  attr/text eol=lf\tscript/empty.adoc",
        ])
        self.assertEqual(v, [])

    def test_binary_and_untext_skipped(self):
        v = cle.eol_violations([
            "i/none  w/none  attr/binary\timg.png",
            "i/crlf  w/crlf  attr/-text\tvendor.bin",
        ])
        self.assertEqual(v, [])

    def test_unparseable_lines_skipped(self):
        v = cle.eol_violations(["warning: some git hint without tab"])
        self.assertEqual(v, [])


class TestScanPreconditions(unittest.TestCase):
    def test_non_git_dir_raises(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):
                cle.scan(d)

    def test_git_worktree_dotgit_file_is_accepted(self):
        # git worktree 的 .git 是一行 "gitdir: ..." 文件而非目录，仍须认可为工作区。
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, ".git"), "w", encoding="utf-8") as f:
                f.write("gitdir: /somewhere/.git/worktrees/x\n")
            with mock.patch.object(cle.subprocess, "run") as run:
                run.return_value = type("R", (), {
                    "returncode": 0,
                    "stdout": "i/lf    w/lf    attr/text eol=lf\ta.py\n",
                    "stderr": "",
                })()
                count, violations = cle.scan(d)
            self.assertEqual(count, 1)
            self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
