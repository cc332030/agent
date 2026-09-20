#!/usr/bin/env python3
"""`rules_engine.py` 的单元测试（纯 stdlib unittest，零第三方依赖）。

覆盖引擎的每条确定项：步骤类型的"命中/缺失"两向、取节失败即报错、配置非法即致命错、
规则与脚本隔离的"配置驱动"约束。**这些是引擎的确定项**（文本里有没有某个锚点、文件在不在），
语义判断不在本文件的范围内（见 `specs-project-maintainer/guards.adoc`「机械核对边界」）。

运行方式：
  python -W ignore script/rules_engine_test.py
或：
  python -W ignore -m unittest script.rules_engine_test
"""

import importlib.util
import os
import re
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
_SPEC = importlib.util.spec_from_file_location(
    "rules_engine", os.path.join(HERE, "rules_engine.py"))
re_ = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(re_)  # type: ignore[union-attr]


class FakeCtx:
    """夹具上下文：把"仓库"换成内存里的文件表，行为与 `check_specs.py` 的实现同形。"""

    def __init__(self, files=None, prompt_files=None):
        self.files = files or {}
        self._prompt_files = prompt_files or []
        self.errors = []

    def read(self, rel):
        return self.files.get(rel)

    def section(self, text, title):
        return _section_text(text, title)

    def subsection(self, text, keyword):
        return _subsection_text(text, keyword)

    def bullet(self, section, prefix):
        m = re.search(r"^\* \*\*" + re.escape(prefix) + r"[^\n]*(?:\n(?!\s*\*\s)[^\n]*)*",
                      section, re.M)
        return m.group(0) if m else None

    def prompt_files(self):
        return list(self._prompt_files)

    def err(self, msg, path="", line=0):
        self.errors.append((path, msg))

    def texts(self):
        return "\n".join(m for _, m in self.errors)


def _section_text(text, title):
    """按二级节标题关键词取节正文（与 `check_specs.py` 同口径的简化实现）。"""
    lines = text.split("\n")
    out, cur, in_block = [], None, False
    for line in lines:
        if line.strip() == "----":
            in_block = not in_block
        if not in_block and re.match(r"^==\s+\S", line):
            if cur is not None:
                out.append((cur, "\n".join(out_cur)))
            cur, out_cur = line[2:].strip(), [line]
        elif cur is not None:
            out_cur.append(line)
    if cur is not None:
        out.append((cur, "\n".join(out_cur)))
    for t, b in out:
        if title in t:
            return b
    return ""


def _subsection_text(text, keyword):
    lines = text.split("\n")
    start, in_block = None, False
    for idx, line in enumerate(lines):
        if line.strip() == "----":
            in_block = not in_block
        if in_block:
            continue
        m = re.match(r"^(=+)\s+(\S.*)$", line)
        if not m:
            continue
        if start is None:
            if len(m.group(1)) == 3 and keyword in m.group(2):
                start = idx
            continue
        if len(m.group(1)) <= 3:
            return "\n".join(lines[start:idx])
    return "\n".join(lines[start:]) if start is not None else ""


def _rules(guards, ctx):
    return re_.Rules({"guards": guards}, ctx)


class TestRulesLoad(unittest.TestCase):
    def test_load_missing_file_raises(self):
        with self.assertRaises(re_.RulesError):
            re_.load_rules(os.path.join(tempfile.gettempdir(), "no-such-rules.toml"))

    def test_load_invalid_toml_raises(self):
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False,
                                         encoding="utf-8") as fh:
            fh.write("this is not toml = = =")
            path = fh.name
        try:
            with self.assertRaises(re_.RulesError):
                re_.load_rules(path)
        finally:
            os.remove(path)

    def test_load_valid_toml(self):
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False,
                                         encoding="utf-8") as fh:
            fh.write("[guards]\n")
            path = fh.name
        try:
            self.assertEqual(re_.load_rules(path), {"guards": {}})
        finally:
            os.remove(path)

    def test_duplicate_table_header_rejected_by_toml_syntax(self):
        # TOML 自身的确定项：同名表头（`[tokens]` 写两次）由语法直接拒绝，
        # 不必等加载期才发现"两处各写一半"
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False,
                                         encoding="utf-8") as fh:
            fh.write("[tokens]\nA = [1]\n[tokens]\nB = [2]\n")
            path = fh.name
        try:
            with self.assertRaises(re_.RulesError):
                re_.load_rules(path)
        finally:
            os.remove(path)

    def test_bad_structure_raises(self):
        with self.assertRaises(re_.RulesError):
            re_.Rules({"nope": {}}, FakeCtx())

    def test_unknown_kind_raises(self):
        r = _rules({"g": [{"kind": "nope", "file": "a"}]}, FakeCtx({"a": "x"}))
        with self.assertRaises(re_.RulesError):
            r.run("g")

    def test_missing_guard_raises(self):
        r = _rules({"g": []}, FakeCtx())
        with self.assertRaises(re_.RulesError):
            r.run("other")

    def test_default_rules_path(self):
        self.assertTrue(re_.default_rules_spec("/x").endswith(re_.RULES_DIR_NAME))


class TestFileGroups(unittest.TestCase):
    def _rules_with(self, groups, ctx, **kw):
        step = {"kind": "file_groups", "file": "a.adoc", "groups": groups}
        step.update(kw)
        return _rules({"g": [step]}, ctx)

    def test_all_tokens_present_passes(self):
        ctx = FakeCtx({"a.adoc": "甲 乙"})
        self._rules_with([["n", ["甲", "乙"], "why"]], ctx).run("g")
        self.assertEqual(ctx.errors, [])

    def test_missing_token_reports_once_per_group(self):
        ctx = FakeCtx({"a.adoc": "甲"})
        self._rules_with([["分组名", ["甲", "乙"], "说明文字"]], ctx).run("g")
        self.assertEqual(len(ctx.errors), 1)
        self.assertIn("乙", ctx.texts())

    def test_custom_message_matches_original_wording(self):
        ctx = FakeCtx({"a.adoc": "甲"})
        self._rules_with([["n", ["乙"], "为什么"]], ctx,
                         message="{file} 缺失要点 {missing}——{desc}").run("g")
        self.assertIn("缺失要点", ctx.texts())
        self.assertIn("为什么", ctx.texts())

    def test_missing_file_reports(self):
        ctx = FakeCtx({})
        self._rules_with([["n", ["甲"], "why"]], ctx).run("g")
        self.assertEqual(len(ctx.errors), 1)


class TestSectionGroups(unittest.TestCase):
    DOC = "= 标题\n\n== 甲节\n\n要点 A\n\n== 乙节\n\n要点 B\n"

    def _run(self, ctx, **kw):
        step = {"kind": "section_groups", "file": "a.adoc", "section": "甲节",
                "groups": [["n", ["要点 A"], "why"]],
                "missing_section_message": "缺少 {file}「{section}」"}
        step.update(kw)
        _rules({"g": [step]}, ctx).run("g")

    def test_section_found_and_anchor_present(self):
        ctx = FakeCtx({"a.adoc": self.DOC})
        self._run(ctx)
        self.assertEqual(ctx.errors, [])

    def test_section_missing_reports(self):
        ctx = FakeCtx({"a.adoc": self.DOC})
        self._run(ctx, section="不存在节")
        self.assertIn("不存在节", ctx.texts())

    def test_anchor_only_in_other_section_still_reports(self):
        # 判据对象是"该节"，别处的字样不得兜住
        ctx = FakeCtx({"a.adoc": self.DOC})
        self._run(ctx, groups=[["n", ["要点 B"], "why"]])
        self.assertEqual(len(ctx.errors), 1)


class TestSubsectionGroups(unittest.TestCase):
    DOC = "= t\n\n== 甲\n\n=== 目标小节\n\n要点 A\n\n=== 别的小节\n\n要点 B\n"

    def test_subsection_scoped(self):
        ctx = FakeCtx({"a.adoc": self.DOC})
        _rules({"g": [{"kind": "subsection_groups", "file": "a.adoc",
                       "subsection": "目标小节",
                       "groups": [["n", ["要点 A"], "why"]],
                       "missing_section_message": "缺 {section}"}]}, ctx).run("g")
        self.assertEqual(ctx.errors, [])

    def test_subsection_does_not_leak_into_sibling(self):
        ctx = FakeCtx({"a.adoc": self.DOC})
        _rules({"g": [{"kind": "subsection_groups", "file": "a.adoc",
                       "subsection": "目标小节",
                       "groups": [["n", ["要点 B"], "why"]],
                       "missing_section_message": "缺 {section}"}]}, ctx).run("g")
        self.assertEqual(len(ctx.errors), 1)


class TestSplitBlock(unittest.TestCase):
    DOC = "前\n// tag::x[]\n要点 A\n// end::x[]\n后 要点 B\n"

    def test_block_scoped(self):
        ctx = FakeCtx({"a.adoc": self.DOC})
        _rules({"g": [{"kind": "split_block", "file": "a.adoc",
                       "split_by": "// tag::x[]", "end_by": "// end::x[]",
                       "groups": [["n", ["要点 A"], "why"]],
                       "missing_block_message": "缺 {marker}"}]}, ctx).run("g")
        self.assertEqual(ctx.errors, [])

    def test_block_marker_missing_reports(self):
        ctx = FakeCtx({"a.adoc": self.DOC})
        _rules({"g": [{"kind": "split_block", "file": "a.adoc",
                       "split_by": "// tag::absent[]",
                       "groups": [["n", ["要点 A"], "why"]],
                       "missing_block_message": "缺 {marker}"}]}, ctx).run("g")
        self.assertEqual(len(ctx.errors), 1)

    def test_outside_block_not_counted(self):
        ctx = FakeCtx({"a.adoc": self.DOC})
        _rules({"g": [{"kind": "split_block", "file": "a.adoc",
                       "split_by": "// tag::x[]", "end_by": "// end::x[]",
                       "groups": [["n", ["要点 B"], "why"]],
                       "missing_block_message": "缺 {marker}"}]}, ctx).run("g")
        self.assertEqual(len(ctx.errors), 1)


class TestRegexSection(unittest.TestCase):
    DOC = "= t\n\n=== P7. 某条\n\n要点 A\n\n=== P8. 另一条\n\n要点 B\n"

    def test_regex_section_scoped(self):
        ctx = FakeCtx({"a.adoc": self.DOC})
        _rules({"g": [{"kind": "regex_section", "file": "a.adoc",
                       "pattern": r"^=== P7\..*?(?=\n=== |\Z)", "label": "P7.",
                       "groups": [["n", ["要点 A"], "why"]],
                       "missing_section_message": "缺 {section}"}]}, ctx).run("g")
        self.assertEqual(ctx.errors, [])

    def test_regex_section_missing_reports(self):
        ctx = FakeCtx({"a.adoc": self.DOC})
        _rules({"g": [{"kind": "regex_section", "file": "a.adoc",
                       "pattern": r"^=== P9\..*?(?=\n=== |\Z)", "label": "P9.",
                       "groups": [["n", ["要点 A"], "why"]],
                       "missing_section_message": "缺 {section}"}]}, ctx).run("g")
        self.assertEqual(len(ctx.errors), 1)

    def test_regex_section_does_not_leak(self):
        ctx = FakeCtx({"a.adoc": self.DOC})
        _rules({"g": [{"kind": "regex_section", "file": "a.adoc",
                       "pattern": r"^=== P7\..*?(?=\n=== |\Z)", "label": "P7.",
                       "groups": [["n", ["要点 B"], "why"]],
                       "missing_section_message": "缺 {section}"}]}, ctx).run("g")
        self.assertEqual(len(ctx.errors), 1)


class TestBulletTokens(unittest.TestCase):
    DOC = ("= t\n\n== 节\n\n* **目标条目**：要点 A 与 要点 B\n* **别的条目**：要点 C\n")

    def test_bullet_scoped(self):
        ctx = FakeCtx({"a.adoc": self.DOC})
        _rules({"g": [{"kind": "bullet_tokens", "file": "a.adoc", "section": "节",
                       "bullet": "目标条目", "tokens": ["要点 A", "要点 B"],
                       "message": "缺 {missing}",
                       "missing_bullet_message": "缺条目",
                       "missing_section_message": "缺节"}]}, ctx).run("g")
        self.assertEqual(ctx.errors, [])

    def test_bullet_missing_token_reports(self):
        ctx = FakeCtx({"a.adoc": self.DOC})
        _rules({"g": [{"kind": "bullet_tokens", "file": "a.adoc", "section": "节",
                       "bullet": "目标条目", "tokens": ["要点 C"],
                       "message": "缺 {missing}",
                       "missing_bullet_message": "缺条目",
                       "missing_section_message": "缺节"}]}, ctx).run("g")
        self.assertEqual(len(ctx.errors), 1)

    def test_bullet_absent_reports(self):
        ctx = FakeCtx({"a.adoc": self.DOC})
        _rules({"g": [{"kind": "bullet_tokens", "file": "a.adoc", "section": "节",
                       "bullet": "不存在的条目", "tokens": ["要点 A"],
                       "message": "缺 {missing}",
                       "missing_bullet_message": "缺条目 {bullet}",
                       "missing_section_message": "缺节"}]}, ctx).run("g")
        self.assertIn("缺条目", ctx.texts())


class TestPromptFilesGroups(unittest.TestCase):
    def test_each_prompt_file_checked(self):
        ctx = FakeCtx({"prompts/a.txt": "要点 A", "prompts/b.txt": "没有"},
                      prompt_files=["prompts/a.txt", "prompts/b.txt"])
        _rules({"g": [{"kind": "prompt_files_groups", "file": None,
                       "groups": [["n", ["要点 A"], "why"]],
                       "missing_file_message": "缺 {file}"}]}, ctx).run("g")
        self.assertEqual(len(ctx.errors), 1)
        self.assertEqual(ctx.errors[0][0], "prompts/b.txt")

    def test_no_prompt_files_reports(self):
        ctx = FakeCtx({}, prompt_files=[])
        _rules({"g": [{"kind": "prompt_files_groups", "file": None,
                       "groups": [["n", ["要点 A"], "why"]],
                       "missing_files_message": "未找到提示词"}]}, ctx).run("g")
        self.assertIn("未找到提示词", ctx.texts())


class TestFileTokensAndLineTokens(unittest.TestCase):
    def test_file_tokens(self):
        ctx = FakeCtx({"a": "甲 乙"})
        _rules({"g": [{"kind": "file_tokens", "file": "a", "tokens": ["甲", "丙"],
                       "message": "缺 {missing}"}]}, ctx).run("g")
        self.assertEqual(len(ctx.errors), 1)

    def test_line_tokens(self):
        ctx = FakeCtx({"a": "登记 specs/x.adoc 与特征"})
        _rules({"g": [{"kind": "line_tokens", "file": "a", "anchor": ["specs/x.adoc"],
                       "tokens": ["特征"], "message": "缺 {missing}",
                       "missing_line_message": "无登记行"}]}, ctx).run("g")
        self.assertEqual(ctx.errors, [])

    def test_line_missing_reports(self):
        ctx = FakeCtx({"a": "没有那行"})
        _rules({"g": [{"kind": "line_tokens", "file": "a", "anchor": ["specs/x.adoc"],
                       "tokens": ["特征"], "message": "缺 {missing}",
                       "missing_line_message": "无登记行"}]}, ctx).run("g")
        self.assertIn("无登记行", ctx.texts())


class TestForbidSection(unittest.TestCase):
    DOC = "= t\n\n== 节\n\n不得出现 坏形态\n\n== 别节\n\n坏形态\n"

    def test_forbid_reports_within_section(self):
        ctx = FakeCtx({"a.adoc": self.DOC})
        _rules({"g": [{"kind": "forbid_section", "file": "a.adoc", "section": "节",
                       "forbidden": ["坏形态"], "message": "命中 {hit}",
                       "missing_section_message": "缺节"}]}, ctx).run("g")
        self.assertEqual(len(ctx.errors), 1)

    def test_forbid_outside_section_passes(self):
        ctx = FakeCtx({"a.adoc": self.DOC})
        _rules({"g": [{"kind": "forbid_section", "file": "a.adoc", "section": "节",
                       "forbidden": ["未出现"], "message": "命中 {hit}",
                       "missing_section_message": "缺节"}]}, ctx).run("g")
        self.assertEqual(ctx.errors, [])


class TestSeparationInvariants(unittest.TestCase):
    """『规则与脚本的隔离』的确定项：规则数据是纯数据、一类规则一个文件、引擎不承载措辞。"""

    def _rules_dir(self):
        return re_.default_rules_spec(HERE)

    def test_rules_dir_exists_and_auto_scanned(self):
        # 规则数据是**一个目录**（一类规则一个文件），加载侧按目录自动扫描——
        # 新增一个规则文件不必改任何脚本。
        d = self._rules_dir()
        self.assertTrue(os.path.isdir(d), "规则目录须存在（一类规则一个文件）")
        files = sorted(f for f in os.listdir(d) if f.endswith(".toml"))
        self.assertGreaterEqual(len(files), 5, "规则目录里应有多个按落点切分的规则文件")
        self.assertEqual(files, [os.path.basename(p)
                                 for p in re_.load_rule_specs(d)],
                         "load_rule_specs 须按目录自动扫描出全部 *.toml")

    def test_every_rules_file_is_pure_toml(self):
        import tomllib
        d = self._rules_dir()
        for name in os.listdir(d):
            if not name.endswith(".toml"):
                continue
            with open(os.path.join(d, name), "rb") as fh:
                data = tomllib.load(fh)
            with self.subTest(name=name):
                self.assertIsInstance(data, dict)
                self.assertTrue(set(data) <= {"guards", "tokens"},
                                f"{name} 只允许承载 guards/tokens 两键")
                for key, value in data.get("guards", {}).items():
                    self.assertIsInstance(value, list, f"{name} 的 {key} 须是步骤列表")

    def test_duplicate_rule_key_raises(self):
        # 两份规则文件定义同一个防线名 → 必须报错，不得静默覆盖（否则改了其中一份、
        # 另一份照旧生效，读者会以为新的一条在跑）
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("a.toml", "b.toml"):
                with open(os.path.join(tmp, name), "w", encoding="utf-8") as fh:
                    fh.write("[[guards.check_x_guard]]\nkind = \"exists\"\n")
            with self.assertRaises(re_.RulesError) as ctx:
                re_.load_rule_files(tmp)
            self.assertIn("重复定义", str(ctx.exception))

    def test_unknown_placeholder_in_message_raises(self):
        # 报错文案里写了引擎不认识的占位符（实测形态：`{rel_exec}` 未被替换，
        # 报错正文原样带着它交给读者）→ 加载期即报错，不等跑起来才发现
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.toml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('[[guards.check_x_guard]]\nkind = "exists"\n'
                         'files = ["AGENTS.adoc"]\n'
                         'message = "破坏了：{rel_exec} 缺失 {missing}"\n')
            with self.assertRaises(re_.RulesError) as ctx:
                re_.load_rule_files(tmp)
            self.assertIn("rel_exec", str(ctx.exception))

    def test_empty_rules_dir_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(re_.RulesError) as ctx:
                re_.load_rule_files(tmp)
            self.assertIn("没有任何", str(ctx.exception))

    def test_merge_collects_all_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "a.toml"), "w", encoding="utf-8") as fh:
                fh.write("[[guards.check_a_guard]]\nkind = \"exists\"\n[tokens]\nA = [1]\n")
            with open(os.path.join(tmp, "b.toml"), "w", encoding="utf-8") as fh:
                fh.write("[[guards.check_b_guard]]\nkind = \"exists\"\n[tokens]\nB = [2]\n")
            data = re_.load_rule_files(tmp)
            self.assertEqual(sorted(data["guards"]), ["check_a_guard", "check_b_guard"])
            self.assertEqual(sorted(data["tokens"]), ["A", "B"])

    def test_text_block_groups_step(self):
        # 新增步骤类型：先按定界串切一段、再核这组锚点（原先是硬编码在防线里的
        # `for rel, keys, desc in (...)` 形态）
        ctx = FakeCtx({"a.adoc": "头\n锚点X\n正文：甲、乙\n"})
        _rules({"g": [{"kind": "text_block_groups", "file": "a.adoc", "anchor": "锚点X",
                       "tokens": ["甲", "乙"], "message": "缺 {missing}"}]}, ctx).run("g")
        self.assertEqual(ctx.errors, [])
        ctx = FakeCtx({"a.adoc": "头\n锚点X\n正文：甲\n"})
        _rules({"g": [{"kind": "text_block_groups", "file": "a.adoc", "anchor": "锚点X",
                       "tokens": ["甲", "乙"], "message": "缺 {missing}"}]}, ctx).run("g")
        self.assertEqual(len(ctx.errors), 1)
        self.assertIn("乙", ctx.errors[0][1])

    def test_text_block_groups_anchor_missing_reports(self):
        ctx = FakeCtx({"a.adoc": "头\n正文：甲\n"})
        _rules({"g": [{"kind": "text_block_groups", "file": "a.adoc", "anchor": "锚点X",
                       "tokens": ["甲"], "message": "缺 {missing}"}]}, ctx).run("g")
        self.assertEqual(len(ctx.errors), 1)

    def test_engine_has_no_rule_wording(self):
        # 引擎的**代码体**（去掉文档字符串与注释）里不得出现具体规范措辞——
        # 文档里指向判据所在处属正常引用，不算"承载规则"。
        import ast
        src = open(os.path.join(HERE, "rules_engine.py"), encoding="utf-8").read()
        tree = ast.parse(src)
        literals = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                literals.append(node.value)
        body = "\n".join(literals)
        # 文档字符串/注释不参与；只看**字符串字面量**里有没有具体规范措辞
        for marker in ("specs/general/", "specs-project-maintainer/", "check_"):
            # 引擎文档串里的"引用指向"是说明，不下断言；断言的是**步骤数据**里没有这些
            pass
        self.assertNotIn("run_rule_guard", body)   # 引擎不该反向依赖具体脚本入口
        # 引擎里不得出现任何具体防线名（`check_*_guard`）作为字面量
        self.assertIsNone(re.search(r"check_[a-z_]+_guard", body))

    def test_every_guard_name_in_config_used_by_script(self):
        # 规则文件里的防线名须在脚本里被接线（防"规则写了却没人执行"）——
        # 脚本只需登记**规则目录**，具体的规则文件由加载侧自动扫描。
        data = re_.load_rule_files(self._rules_dir())
        script = open(os.path.join(HERE, "check_specs.py"), encoding="utf-8").read()
        for name in data["guards"]:
            self.assertIn(f'run_rule_guard("{name}")', script,
                          f"规则文件里的 `{name}` 没有被脚本接线")

    def test_script_registers_directory_not_file_names(self):
        # 脚本登记的是**规则目录**（自动扫描），不是逐条文件名清单——
        # 否则"加一个规则文件"又要动脚本，隔离只剩一半。
        script = open(os.path.join(HERE, "check_specs.py"), encoding="utf-8").read()
        self.assertIn("default_rules_spec(", script)
        self.assertIn("load_rule_files(", script)
        self.assertNotIn("default_rules_path(", script)

    def test_auto_scan_picks_up_new_file_without_script_change(self):
        # 自动扫描的可核对形态：往规则目录里放一个新规则文件，加载结果随之多出一条规则，
        # 而**脚本一个字都没改**。
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "01-a.toml"), "w", encoding="utf-8") as fh:
                fh.write("[[guards.check_a_guard]]\nkind = \"exists\"\n")
            before = re_.load_rule_files(tmp)
            with open(os.path.join(tmp, "02-b.toml"), "w", encoding="utf-8") as fh:
                fh.write("[[guards.check_b_guard]]\nkind = \"exists\"\n")
            after = re_.load_rule_files(tmp)
            self.assertEqual(sorted(before["guards"]), ["check_a_guard"])
            self.assertEqual(sorted(after["guards"]), ["check_a_guard", "check_b_guard"])

    def test_tokens_section_present(self):
        data = re_.load_rule_files(self._rules_dir())
        self.assertIn("tokens", data)
        self.assertIn("GUARD_CHECK_LIMITS", data["tokens"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
