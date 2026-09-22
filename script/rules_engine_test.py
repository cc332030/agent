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
        # 与 `check_specs._bullet_text` 同口径：bullet 的**续行**（`** ...`，AsciiDoc 的列表项
        # 延续）收进同一条；只有遇到**另一条 bullet**（行首 `* ` 且其后不是 `* `）才截断。
        m = re.search(r"^\* \*\*" + re.escape(prefix) + r"[^\n]*(?:\n(?!\s*\*(?!\*)\s)[^\n]*)*",
                      section, re.M)
        return m.group(0) if m else None

    def prompt_files(self):
        return list(self._prompt_files)

    def list_files(self, prefix, suffix=""):
        return sorted(r for r in self.files if r.startswith(prefix) and r.endswith(suffix))

    def log(self, msg):
        pass

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
        # 自定义文案里不得写 `{section}`（加载期拦住）——缺的是哪一节由引擎自己填进
        # 默认模板，自定义文案只补"为什么失效"
        step = {"kind": "section_groups", "file": "a.adoc", "section": "甲节",
                "groups": [["n", ["要点 A"], "why"]]}
        step.update(kw)
        _rules({"g": [step]}, ctx).run("g")

    def test_section_found_and_anchor_present(self):
        ctx = FakeCtx({"a.adoc": self.DOC})
        self._run(ctx)
        self.assertEqual(ctx.errors, [])

    def test_section_missing_reports(self):
        ctx = FakeCtx({"a.adoc": self.DOC})
        self._run(ctx, section="不存在节")
        # 报错正文里须给出**缺的是哪一节**（占位符由引擎填入，不靠自定义文案）
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
                       "missing_section_message": "缺对应节"}]}, ctx).run("g")
        self.assertEqual(ctx.errors, [])

    def test_subsection_does_not_leak_into_sibling(self):
        ctx = FakeCtx({"a.adoc": self.DOC})
        _rules({"g": [{"kind": "subsection_groups", "file": "a.adoc",
                       "subsection": "目标小节",
                       "groups": [["n", ["要点 B"], "why"]],
                       "missing_section_message": "缺对应节"}]}, ctx).run("g")
        self.assertEqual(len(ctx.errors), 1)


class TestSplitBlock(unittest.TestCase):
    DOC = "前\n// tag::x[]\n要点 A\n// end::x[]\n后 要点 B\n"

    def test_block_scoped(self):
        ctx = FakeCtx({"a.adoc": self.DOC})
        _rules({"g": [{"kind": "split_block", "file": "a.adoc",
                       "split_by": "// tag::x[]", "end_by": "// end::x[]",
                       "groups": [["n", ["要点 A"], "why"]],
                       "missing_block_message": "缺对应片段"}]}, ctx).run("g")
        self.assertEqual(ctx.errors, [])

    def test_block_marker_missing_reports(self):
        ctx = FakeCtx({"a.adoc": self.DOC})
        _rules({"g": [{"kind": "split_block", "file": "a.adoc",
                       "split_by": "// tag::absent[]",
                       "groups": [["n", ["要点 A"], "why"]],
                       "missing_block_message": "缺对应片段"}]}, ctx).run("g")
        self.assertEqual(len(ctx.errors), 1)

    def test_outside_block_not_counted(self):
        ctx = FakeCtx({"a.adoc": self.DOC})
        _rules({"g": [{"kind": "split_block", "file": "a.adoc",
                       "split_by": "// tag::x[]", "end_by": "// end::x[]",
                       "groups": [["n", ["要点 B"], "why"]],
                       "missing_block_message": "缺对应片段"}]}, ctx).run("g")
        self.assertEqual(len(ctx.errors), 1)


class TestRegexSection(unittest.TestCase):
    DOC = "= t\n\n=== P7. 某条\n\n要点 A\n\n=== P8. 另一条\n\n要点 B\n"

    def test_regex_section_scoped(self):
        ctx = FakeCtx({"a.adoc": self.DOC})
        _rules({"g": [{"kind": "regex_section", "file": "a.adoc",
                       "pattern": r"^=== P7\..*?(?=\n=== |\Z)", "label": "P7.",
                       "groups": [["n", ["要点 A"], "why"]],
                       "missing_section_message": "缺对应节"}]}, ctx).run("g")
        self.assertEqual(ctx.errors, [])

    def test_regex_section_missing_reports(self):
        ctx = FakeCtx({"a.adoc": self.DOC})
        _rules({"g": [{"kind": "regex_section", "file": "a.adoc",
                       "pattern": r"^=== P9\..*?(?=\n=== |\Z)", "label": "P9.",
                       "groups": [["n", ["要点 A"], "why"]],
                       "missing_section_message": "缺对应节"}]}, ctx).run("g")
        self.assertEqual(len(ctx.errors), 1)

    def test_regex_section_does_not_leak(self):
        ctx = FakeCtx({"a.adoc": self.DOC})
        _rules({"g": [{"kind": "regex_section", "file": "a.adoc",
                       "pattern": r"^=== P7\..*?(?=\n=== |\Z)", "label": "P7.",
                       "groups": [["n", ["要点 B"], "why"]],
                       "missing_section_message": "缺对应节"}]}, ctx).run("g")
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
                       "missing_bullet_message": "缺条目 X",
                       "missing_section_message": "缺节"}]}, ctx).run("g")
        self.assertIn("缺条目 X", ctx.texts())

    # 下面三条是 `until` / `anchor` 两个新选项的确定项：同一 bullet 的后半句会兜住前半句的
    # 缺项（本仓库实测形态：条目正文的清单句缺一项，而同一 bullet 末尾的依据行同样罗列那些名字）。
    # 与真实文件同形：清单句与"依据行"分处**同一个 bullet 的两行**
    # （bullet 的续行以 `** ` 起头，`_bullet_text` 会把它们收进同一条）。
    DOC_SCOPE = ("= t\n\n== 节\n\n"
                 "* **目标条目**：清单句只提 `A`。\n"
                 "** 其后说明句。\n"
                 "** 依据：末句再提 `B`（依据行会复现同一批名字）。\n")

    def test_until_cuts_off_tail_that_would_back_the_missing_token(self):
        # 加了 `until`：核对对象截到「其后说明句」之前，`B` 只剩依据行里有 → 如实报红。
        ctx = FakeCtx({"a.adoc": self.DOC_SCOPE})
        _rules({"g": [{"kind": "bullet_tokens", "file": "a.adoc", "section": "节",
                       "bullet": "目标条目", "until": "其后说明句",
                       "tokens": ["A", "B"],
                       "message": "缺 {missing}",
                       "missing_bullet_message": "缺条目",
                       "missing_section_message": "缺节"}]}, ctx).run("g")
        self.assertEqual(len(ctx.errors), 1)
        self.assertIn("B", ctx.errors[0][1])

    def test_without_until_tail_tokens_are_backed_up(self):
        # 反证：不截断时依据行把 `B` 兜住、防线全绿——这正是"必须能截断"的理由（本仓库实测形态）。
        ctx = FakeCtx({"a.adoc": self.DOC_SCOPE})
        _rules({"g": [{"kind": "bullet_tokens", "file": "a.adoc", "section": "节",
                       "bullet": "目标条目",
                       "tokens": ["A", "B"],
                       "message": "缺 {missing}",
                       "missing_bullet_message": "缺条目",
                       "missing_section_message": "缺节"}]}, ctx).run("g")
        self.assertEqual([], ctx.errors)

    def test_anchor_starts_after_given_string(self):
        # `anchor` 起算：核对对象从该串之后取——该串**之前**出现的字样不参与核对。
        ctx = FakeCtx({"a.adoc": self.DOC_SCOPE})
        _rules({"g": [{"kind": "bullet_tokens", "file": "a.adoc", "section": "节",
                       "bullet": "目标条目", "anchor": "其后说明句。",
                       "tokens": ["A"],
                       "message": "缺 {missing}",
                       "missing_bullet_message": "缺条目",
                       "missing_section_message": "缺节"}]}, ctx).run("g")
        # `A` 只在 anchor **之前**出现（清单句里），故按 anchor 起算后缺失 → 报红
        self.assertEqual(len(ctx.errors), 1)
        self.assertIn("A", ctx.errors[0][1])

    def test_anchor_absent_reports(self):
        ctx = FakeCtx({"a.adoc": self.DOC_SCOPE})
        _rules({"g": [{"kind": "bullet_tokens", "file": "a.adoc", "section": "节",
                       "bullet": "目标条目", "anchor": "不存在的串",
                       "tokens": ["A"],
                       "message": "缺 {missing}",
                       "missing_bullet_message": "缺条目",
                       "missing_section_message": "缺节"}]}, ctx).run("g")
        self.assertEqual(len(ctx.errors), 1)


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


class TestFileForbidden(unittest.TestCase):
    """整份文件内的**反向**核对（与 `file_tokens` 方向相反）。

    用途是"某处不得再抄一遍"这类要求：正向锚点只能证明"该写的还在"，证明不了"不该抄的没抄"。
    """

    def test_forbidden_absent_passes(self):
        ctx = FakeCtx({"a.adoc": "= t\n\n只有照抄约定与回指。\n"})
        _rules({"g": [{"kind": "file_forbidden", "file": "a.adoc",
                       "forbidden": ["机制原文"], "message": "{file} 出现 {hit}"}]}, ctx).run("g")
        self.assertEqual(ctx.errors, [])

    def test_forbidden_present_reports_with_hit(self):
        ctx = FakeCtx({"a.adoc": "= t\n\n这里抄了机制原文。\n"})
        _rules({"g": [{"kind": "file_forbidden", "file": "a.adoc",
                       "forbidden": ["机制原文"], "message": "{file} 出现 {hit}"}]}, ctx).run("g")
        self.assertEqual(len(ctx.errors), 1)
        self.assertIn("机制原文", ctx.errors[0][1])

    def test_missing_file_reports(self):
        ctx = FakeCtx({})
        _rules({"g": [{"kind": "file_forbidden", "file": "a.adoc",
                       "forbidden": ["x"], "message": "{file} 出现 {hit}"}]}, ctx).run("g")
        self.assertEqual(len(ctx.errors), 1)


class TestDispatcherNoVerbatim(unittest.TestCase):
    """调度器守卫：加载项与**被引文件**正文逐字重合超阈值即报红。

    用途是"调度器只登记、不抄条目本体"这类要求：细节词标记（`判定标准`/`任一命中`）只能拦
    **措辞标记**，拦不住把**取值**成串抄进来（`@NoArgsConstructor` 一族、四类测试后缀、
    `src/main/resources/`、`kebab-case`……）。本原语按"逐字重合"补上这一半。
    """

    DISPATCHER = (
        "* **Java 项目** → `specs/stack/java.adoc`（识别特征：要写 javadoc、要写测试类）\n"
        "* **写/改 SQL** → `specs/general/sql.adoc`（识别特征：ALTER TABLE、INSERT 一类语句）\n"
    )

    def _run(self, dispatcher, spec_body, **extra):
        step = {"kind": "dispatcher_no_verbatim", "file": "AGENTS_COMMON.adoc",
                "min_overlap": extra.pop("min_overlap", 14),
                "message": "{file}:{line} 与 {ref} 重合 {overlap} 字：{frag}"}
        step.update(extra)
        ctx = FakeCtx({"AGENTS_COMMON.adoc": dispatcher, "specs/stack/java.adoc": spec_body,
                       "specs/general/sql.adoc": spec_body})
        _rules({"g": [step]}, ctx).run("g")
        return ctx.errors

    def test_short_overlap_passes(self):
        # 只写触发特征、不与本体逐字重合 → 通过
        body = "= Java 规范\n\n* **类型指代**：写 javadoc 时优先写短类名。\n"
        self.assertEqual(self._run(self.DISPATCHER, body), [])

    def test_long_verbatim_reports(self):
        # 把本体的取值成串抄进调度器 → 报红（阈值 14）
        body = "= Java 规范\n\n该注解清单含 @NoArgsConstructor 与 @AllArgsConstructor 两项。\n"
        d = ("* **Java 项目** → `specs/stack/java.adoc`（识别特征：清单含 "
             "@NoArgsConstructor 与 @AllArgsConstructor 两项）\n")
        errs = self._run(d, body)
        self.assertEqual(len(errs), 1)
        self.assertIn("重合", errs[0][1])

    def test_threshold_configurable(self):
        # 提高阈值后同一处不再报（阈值是可配的口径，不是硬编码）
        body = "= Java 规范\n\n该注解清单含 @NoArgsConstructor 与 @AllArgsConstructor 两项。\n"
        d = ("* **Java 项目** → `specs/stack/java.adoc`（识别特征：清单含 "
             "@NoArgsConstructor 与 @AllArgsConstructor 两项）\n")
        self.assertEqual(self._run(d, body, min_overlap=80), [])

    def test_scope_limits_to_section(self):
        # 只核指定节：节前的内容即使逐字重合也不报（入口的「铁律」是刻意写的摘要，不应误伤）
        body = "= Java 规范\n\n该注解清单含 @NoArgsConstructor 与 @AllArgsConstructor 两项。\n"
        d = ("* **铁律** → `specs/stack/java.adoc`（清单含 "
             "@NoArgsConstructor 与 @AllArgsConstructor 两项）\n"
             "== 加载调度器\n"
             "* **Java 项目** → `specs/stack/java.adoc`（识别特征：要写 javadoc）\n")
        errs = self._run(d, body, scope_after="== 加载调度器", scope_until="== 尾部")
        self.assertEqual(errs, [])

    def test_scope_missing_marker_reports(self):
        # 指定的起始标记不存在 → 报错（不静默跳过）
        body = "= Java 规范\n\n* x。\n"
        errs = self._run(self.DISPATCHER, body, scope_after="== 不存在的节")
        self.assertEqual(len(errs), 1)

    def test_missing_file_reports(self):
        ctx = FakeCtx({})
        _rules({"g": [{"kind": "dispatcher_no_verbatim", "file": "AGENTS_COMMON.adoc",
                       "message": "{file} 缺文件"}]}, ctx).run("g")
        self.assertEqual(len(ctx.errors), 1)


class TestDuplicateScan(unittest.TestCase):
    """『逐字重复扫描』原语：同一件事在两处逐字重复即报红（判据见
    `specs/general/review.adoc`「精炼性（同一描述只写一处）」）。

    本条只核**逐字**重合——阈值以下、或换了说法的重复核不出来，那是语义复核的事；
    用例覆盖的正是"能逐字判定"的那一半：整条重合、**折叠 vs 展开**（换行处不同）、
    例外清单、自配对、历史留痕与短实体不误伤。
    """

    def _run(self, files, **extra):
        step = {"kind": "duplicate_scan", "file": None, "sources": sorted(files),
                "min_overlap": extra.pop("min_overlap", 24),
                "message": "{a}:{line_a} 与 {b}:{line_b} 重合 {overlap} 字：{frag}"}
        step.update(extra)
        ctx = FakeCtx(files)
        _rules({"g": [step]}, ctx).run("g")
        return ctx.errors

    def test_verbatim_bullet_reports(self):
        # 同一条判据在两个文件里逐字各存一份 → 报红
        body = ("* **运行契约（L1）**：加载与遵守的代价是否说得清——加载面体积、时延与依赖要求"
                "（含版本要求，且须给出不可用时的降级路径）。\n")
        errs = self._run({"a.adoc": body, "b.adoc": body})
        self.assertEqual(len(errs), 1)
        self.assertIn("重合", errs[0][1])

    def test_folded_vs_expanded_reports(self):
        # 一处折叠成一行、另一处铺成多行（换行处不同）：整条公共子串被换行打断，
        # 须靠**逐句**那一遍补上（这一形态在真实仓库里出现过）
        sentences = ("**① 影响面（L1）**：这条规则会改变引用方的哪些既有行为？"
                     "**与引用方自身规范的冲突次序**是否写明（以引用方项目自身规范为准）。")
        a = "* " + sentences + "\n"
        b = "* **① 影响面（L1）**：这条规则会改变引用方的哪些既有行为？\n"
        b += "** **与引用方自身规范的冲突次序**是否写明（以引用方项目自身规范为准）。\n"
        errs = self._run({"a.adoc": a, "b.adoc": b})
        self.assertEqual(len(errs), 1)

    def test_short_entity_does_not_report(self):
        # 实体短于阈值不参与（惯用语、主题名本来就该一样）
        errs = self._run({"a.adoc": "* 要写测试类。\n", "b.adoc": "* 要写测试类。\n"})
        self.assertEqual(errs, [])

    def test_same_entity_not_reported(self):
        # 同一份实体自身与自身不算重复（粗筛会把一个实体的多个 n-gram 桶聚成自配对）——
        # 故"只有一个文件、里面只有一条实体"时必须零报错，而不是自己跟自己比出一处重复
        body = "* **运行契约（L1）**：加载与遵守的代价是否说得清——加载面体积、时延与依赖要求。\n"
        errs = self._run({"a.adoc": body, "b.adoc": "* 这一条与上一条讲的是两件不同的事，措辞也不同。\n"})
        self.assertEqual(errs, [])

    def test_exclude_skips_history(self):
        # 历史留痕文件（CHANGELOG）的职责就是逐字保留，不参与（否则会把它的角色判成违规）
        body = ("* **运行契约（L1）**：加载与遵守的代价是否说得清——加载面体积、时延与依赖要求"
                "（含版本要求，且须给出不可用时的降级路径）。\n")
        other = "* **另一条**：与上面讲的是不同的事，措辞也不一样、不会逐字重合。\n"
        ctx = FakeCtx({"a.adoc": body, "b.adoc": other, "CHANGELOG.adoc": body})
        _rules({"g": [{"kind": "duplicate_scan", "file": None,
                       "sources": ["a.adoc", "b.adoc", "CHANGELOG.adoc"],
                       "exclude": ["CHANGELOG.adoc"], "min_overlap": 24,
                       "message": "{a}:{line_a} 与 {b}:{line_b}"}]}, ctx).run("g")
        self.assertEqual(ctx.errors, [], "被 exclude 的文件不得把同内容判成重复")

    def test_ignore_units_exempts_quotes(self):
        # 例外清单（图书馆的逐字引文、带出处的用户原话）不参与——理由写在规则数据里
        body = ("* **逐字摘**：**运行契约（L1）** 加载与遵守的代价是否说得清——加载面体积、"
                "时延与依赖要求（含版本要求，且须给出不可用时的降级路径）。\n")
        other = ("* **运行契约（L1）**：加载与遵守的代价是否说得清——加载面体积、时延与依赖要求"
                 "（含版本要求，且须给出不可用时的降级路径）。\n")
        errs = self._run({"a.adoc": body, "b.adoc": other}, ignore_units=["逐字摘"])
        self.assertEqual(errs, [])

    def test_threshold_configurable(self):
        body = "* 甲：加载与遵守的代价是否说得清——加载面体积、时延与依赖要求。\n"
        self.assertEqual(self._run({"a.adoc": body, "b.adoc": body}, min_overlap=200), [])

    def test_directory_source_expands(self):
        # `sources` 里的目录型落点按目录展开；同目录两个文件逐字重合也要报
        body = "* **运行契约（L1）**：加载与遵守的代价是否说得清——加载面体积、时延与依赖要求。\n"
        errs = self._run({"specs/a.adoc": body, "specs/b.adoc": body})
        ctx = FakeCtx({"specs/a.adoc": body, "specs/b.adoc": body})
        _rules({"g": [{"kind": "duplicate_scan", "file": None, "sources": ["specs/"],
                       "min_overlap": 24,
                       "message": "{a}:{line_a} 与 {b}:{line_b}"}]}, ctx).run("g")
        self.assertEqual(len(ctx.errors), 1)
        self.assertEqual(len(errs), 1)

    def test_same_file_two_sections_reports(self):
        # 本轮实证形态：**同一份文件的两节**把同一条判据各写一遍（「执行吞吐」与
        # 「token 纪律」都写了"不重复读"的判定标准与三种例外）——按行切、按实体切都
        # 得报，不能因为"在同一个文件里"就放过（同文件同样是第二真源）。
        body = ("* **读到的判据（L1）**：同一路径在一次任务里被读第二次，而两次之间"
                "**没有新的事实、也没有新结论产生**——命中即违规；三种例外须写明理由。\n"
                "\n== 另一节\n\n"
                "* **不重复读（L1）**：同一路径在一次任务里被读第二次，而两次之间"
                "**没有新的事实、也没有新结论产生**——命中即违规；须标明例外的三种情形。\n")
        errs = self._run({"a.adoc": body, "b.adoc": "* 与上面讲的是不同的事，措辞也不同。\n"})
        self.assertEqual(len(errs), 1)

    def test_common_prefix_phrase_reports(self):
        # 本轮实证形态：同一句**回指句**在三个栈文件里逐字复用（"……只写入口自己：判据属
        # 通用层、唯一落点＝……本文件不重复"）——回指本身不构成第二真源，但**逐字复制
        # 的回指句**是一处会各自漂移的共用文本，须报。
        body = ("* **`.sh` 的头部注释只写入口自己**：判据属通用层、唯一落点＝"
                "「脚本头部注释（文档头）」下的「入口的注释边界（L1）」，本文件不重复。\n")
        other = ("* **`.bat` 的头部注释只写入口自己**：判据属通用层、唯一落点＝"
                 "「脚本头部注释（文档头）」下的「入口的注释边界（L1）」，本文件不重复。\n")
        errs = self._run({"a.adoc": body, "b.adoc": other})
        self.assertEqual(len(errs), 1)

    def test_inline_code_not_counted(self):
        # 行内代码（路径/命令/标识符）本就该在两处一致——算重合只会刷出假命中，
        # 故 `_norm_dup` 把它们剥掉：「命令字面量相同、实义文字不同」不得报红。
        a = "* 核对命令是 `git merge-base <分支> <目标分支>` 与 `git rev-list --parents -n1`。\n"
        b = ("* **平台侧的真实失效**：照抄目标分支的文件内容后另起一个单亲提交——"
             "工作树一致，但目标分支不是祖先，平台仍报冲突。\n")
        errs = self._run({"a.adoc": a, "b.adoc": b}, min_overlap=24)
        self.assertEqual(errs, [])

    def test_ieee_std_annotation_ignored(self):
        # 标准名的括注（`IEEE Std 1003.1 …`）逐字一致才是可核对的前提——规则数据的
        # `ignore` 把它排除在本条之外（否则同一批标准的正当重合会被反复报红）
        a = "* 标准名：POSIX（IEEE Std 1003.1 / The Open Group Base Specifications）。\n"
        b = "* **POSIX**（IEEE Std 1003.1 / The Open Group Base Specifications）："
        b += "文本行以 `\\n` 分隔、shebang 行解析。\n"
        errs = self._run({"a.adoc": a, "b.adoc": b}, min_overlap=24, ignore=["IEEE Std"])
        self.assertEqual(errs, [])

    def test_too_few_sources_reports(self):
        # 少于两个可核对文档 → 报错（不静默跳过：该防线会空转）
        ctx = FakeCtx({"a.adoc": "* 一条足够长的判据文本，长到超过阈值用来占位。\n"})
        _rules({"g": [{"kind": "duplicate_scan", "file": None, "sources": ["a.adoc"],
                       "dup_missing_files_message": "落点不足 {file}"}]}, ctx).run("g")
        self.assertIn("落点不足", ctx.texts())


class TestPointerNoVerbatim(unittest.TestCase):
    """『自称回指的行不得复述取值』原语（`pointer_no_verbatim`）。

    补 `duplicate_scan` 的**下界**：阈值 40 只报"长度极显著"的重合，而"回指句 + 顺手把
    取值抄一遍"的公共子串常只有二十几字（本轮实证：`library/mirrors.adoc` 自称"本文件只给
    实测记录、取舍本体见 `adoption.adoc`"，却仍逐字写下「每级先实测可用、不跳级、不覆盖
    既有配置」21 字，`duplicate_scan` 核不出来）。判据见 `specs/general/review.adoc`
    「精炼性（同一描述只写一处）」。
    """

    def _run(self, files, **extra):
        step = {"kind": "pointer_no_verbatim", "file": None, "files": sorted(files),
                "min_overlap": extra.pop("min_overlap", 20),
                "message": "{file}:{line} 与 `{ref}` 重合 {overlap} 字：{frag}"}
        step.update(extra)
        ctx = FakeCtx(files)
        _rules({"g": [step]}, ctx).run("g")
        return ctx.errors

    def test_pointer_restating_value_reports(self):
        # 本轮实证形态：同一行里既说"取舍本体见别处"、又把别处的取值写了一遍
        a = ("* **库源次序**：每级先实测可用、不跳级、不覆盖既有配置，且不覆盖引用方配置。\n")
        b = ("* **须注意的语义差异**：本集合据此推出的是自己的判据化取舍；取舍本体见 "
             "`a.adoc`，本文件只给实测记录——但每级先实测可用、不跳级、不覆盖既有配置，"
             "且不覆盖引用方配置。\n")
        errs = self._run({"a.adoc": a, "b.adoc": b})
        self.assertEqual(len(errs), 1)
        self.assertIn("重合", errs[0][1])

    def test_pure_pointer_does_not_report(self):
        # 正例：只写"本集合据此推出 + 回指"，不复述取值 → 全绿
        a = "* **库源次序**：每级先实测可用、不跳级、不覆盖既有配置是本集合自己的取舍。\n"
        b = ("* **须注意的语义差异**：本集合据此推出的是自己的判据化取舍（**取值见 "
             "`a.adoc`**，本文件只给实测记录）。\n")
        self.assertEqual(self._run({"a.adoc": a, "b.adoc": b}), [])

    def test_line_without_pointer_marker_not_checked(self):
        # 只核**含回指标记**的行：没自称"见别处"的行不在本条的核对面内
        # （它们属 `duplicate_scan` 的阈值口径）
        a = "* 每级先实测可用、不跳级、不覆盖既有配置是本集合自己的取舍。\n"
        b = "* 每级先实测可用、不跳级、不覆盖既有配置是本集合自己的取舍。\n"
        self.assertEqual(self._run({"a.adoc": a, "b.adoc": b}), [])

    def test_ignore_exempts_standard_names(self):
        # 标准名/材料名本就该逐字一致（`source.adoc`「外部引用」）——按 `ignore` 排除，
        # 否则同一批标准名会被反复判红（本轮实测的假命中：
        # `The Twelve-Factor App（依赖显式声明）` 去空白后与 `adoption.adoc` 逐字相同）
        a = "* 依据：The Twelve-Factor App（依赖须显式声明）。\n"
        b = "* **同义性**：本集合据此推出的取舍见 `a.adoc`、本文件只给实测记录；"
        b += "外部材料含 The Twelve-Factor App（依赖显式声明）一类方向。\n"
        self.assertEqual(self._run({"a.adoc": a, "b.adoc": b},
                                   ignore=["The Twelve-Factor App"]), [])

    def test_threshold_configurable(self):
        a = "* 每级先实测可用、不跳级、不覆盖既有配置，且不覆盖引用方配置。\n"
        b = "* 本集合据此推出、取舍本体见 `a.adoc`：每级先实测可用、不跳级、不覆盖既有配置，且不覆盖引用方配置。\n"
        self.assertEqual(self._run({"a.adoc": a, "b.adoc": b}, min_overlap=200), [])

    def test_missing_file_reports(self):
        ctx = FakeCtx({})
        _rules({"g": [{"kind": "pointer_no_verbatim", "files": ["a.adoc"],
                       "missing_file_message": "缺少 {file}"}]}, ctx).run("g")
        self.assertIn("缺少 a.adoc", ctx.texts())


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
                # `_tokens.toml` 另承载"要给模块级常量用"的纯数据段
                # （`merge_state_guard` 的措辞表：提交说明里哪些话术算"合并动作的痕迹"、
                # 哪些算"记录禁令的放行标记"）——**仍是纯数据**，只是不必包在 `tokens` 里。
                self.assertTrue(set(data) <= {"guards", "tokens", "merge_state_guard"},
                                f"{name} 只允许承载 guards/tokens/merge_state_guard 三类键")
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
