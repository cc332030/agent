#!/usr/bin/env python3
"""`check_pipeline_timeout` 的单元测试（纯 stdlib unittest）。

**正例**：每一步都有可判定的时限（含"时限设在 job 级、steps 不再逐个设"的合法形态）→ 全绿。
**反例（任一命中即须报红）**：
* 某个 step 没有时限；
* 整个 job 没有时限、steps 也没有；
* 配置解析不了（不得当成"没有该键"而放过）；
* 一份配置都没有（"核不到"不得当成"核过且通过"）。
"""

import importlib.util
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
_SPEC = importlib.util.spec_from_file_location(
    "check_pipeline_timeout", os.path.join(HERE, "check_pipeline_timeout.py"))
cpt = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cpt)  # type: ignore[union-attr]

WF_OK = """
name: ci
on:
  push:
    paths: &p
      - 'a/**'
  pull_request:
    paths: *p
jobs:
  lint:
    timeout-minutes: 10
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - name: run
        run: |
          echo hi
          echo there
"""

WF_STEP_MISSING = """
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - name: slow
        run: python3 long.py
"""

WF_JOB_MISSING = """
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - name: only
        run: echo hi
"""

WF_REUSABLE = """
jobs:
  mirror:
    if: github.event_name == 'push'
    uses: org/repo/.github/workflows/mirror.yml@master
    secrets:
      TOKEN: ${{ secrets.TOKEN }}
"""


class TestCheck(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _write(self, rel, text):
        path = os.path.join(self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def _check(self, rel, text, kind="github-workflow"):
        errors = []
        cpt.check_yaml(rel, kind, text, cpt.DEFAULT_TIMEOUT_KEYS, errors)
        return errors

    def test_job_level_timeout_is_enough(self):
        self.assertEqual([], self._check("wf.yml", WF_OK))

    def test_reusable_workflow_job_is_not_checked(self):
        # 可复用工作流没有 steps、本文件也不可挂时限：核它就是假红
        self.assertEqual([], self._check("wf.yml", WF_REUSABLE))

    def test_missing_step_timeout_is_red(self):
        errors = self._check("wf.yml", WF_STEP_MISSING)
        self.assertTrue(any("slow" in e for e in errors), errors)

    def test_missing_everything_is_red(self):
        self.assertTrue(self._check("wf.yml", WF_JOB_MISSING))

    def test_unparsable_config_is_red_not_silent(self):
        errors = self._check("wf.yml", "jobs:\n  - a\n   b: 1\n")
        self.assertTrue(any("解析失败" in e for e in errors), errors)

    def test_no_config_at_all_is_red(self):
        code = cpt.main(["--repo", self.root, "--quiet"])
        self.assertEqual(1, code)

    def test_all_green_exits_zero(self):
        self._write(".github/workflows/ci.yml", WF_OK)
        self.assertEqual(0, cpt.main(["--repo", self.root, "--quiet"]))

    def test_config_block_is_not_reported_as_a_unit(self):
        # 与执行无关的配置块（`values:` / `stages:` 一类）不是执行单位，报它就是假红
        errs = self._check(".gitlab-ci.yml",
                           "stages: [build]\nvalues:\n  image: alpine:3.20\n",
                           kind="gitlab")
        self.assertEqual([], errs)

    def test_gitlab_job_without_timeout_is_red(self):
        errs = self._check(".gitlab-ci.yml",
                           "stages: [build]\nbuild:\n  stage: build\n  script: [make]\n",
                           kind="gitlab")
        self.assertTrue(any("build" in e for e in errs), errs)

    def test_reporting_is_not_the_placeholder(self):
        # 报出来的路径要能定位到那一步（不是一句"配置有问题"）
        self._write(".github/workflows/ci.yml", WF_STEP_MISSING)
        errors = []
        node = cpt.yaml_min.load(WF_STEP_MISSING)
        cpt._check_github_workflow(".github/workflows/ci.yml", node,
                                   cpt.DEFAULT_TIMEOUT_KEYS, errors)
        self.assertTrue(any("jobs.lint.steps[1]" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main(verbosity=2)
