#!/usr/bin/env python3
"""`yaml_min` 的单元测试（纯 stdlib unittest）。

覆盖：本子集内的写法逐项对照预期、以及**不支持/不合法写法必须报错**（不得静默取到 None）。
对照参照实现（装了 PyYAML 时）用同一份样本再核一遍——参照缺失时跳过该组、不算失败。
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import yaml_min  # noqa: E402

try:
    import yaml as _ref
except ImportError:  # 参照实现缺失：只在装得出来时才做对照
    _ref = None


SAMPLES = {
    "块映射与序列": "a: 1\nb:\n  - x\n  - y\nc:\n  d: true\n",
    "键下直接跟序列": "on:\n  push:\n    paths: &spec-paths\n      - 'a/**'\n      - 'b/**'\n",
    "映射项的键下跟序列": "jobs:\n  j:\n    - key:\n        - 1\n        - 2\n      other: 3\n",
    "行内序列": "a: [1, 2, x]\nb: []\n",
    "标量与空值": "a: ~\nb:\nc: null\nd: 'q: q'\ne: 12\nf: -3\n",
    "注释与空行": "a: 1  # 尾注释\n\n# 整行注释\nb: 'x#y'\n",
    "序列项即映射": "steps:\n  - name: n\n    run: r\n  - uses: u@v\n",
    "块标量（值不进判据、但读得懂）": "jobs:\n  j:\n    steps:\n      - name: n\n        run: |\n          a\n          b\n",
    "井号在标量中": "a: b#c\nb: '#d'\n",
    # 序列项**与其父键同缩进**是 YAML 合法且手写配置里最常见的写法之一
    # （`steps:` 下一行直接写顶格的 `- run: x`）。解成"读不出来"会把整份配置判红，
    # 拦掉真正该核的执行单位——故逐条对照。
    "序列项与父键同缩进": "jobs:\n  j:\n    steps:\n    - run: x\n    - run: y\n",
    "序列项与父键同缩进的嵌套": "menu:\n  items:\n  - name: a\n    args: [1, 2]\n",
    "键下直接跟同缩进序列": "a:\n- 1\n- 2\n",
    # 含冒号的标量不得被判成"读不出来"（两种写法 PyYAML 都判为合法）
    "含冒号的标量": "a: 'echo x: y'\nb: \"p: q\"\n",
}


def _normalize_ref(node):
    """把参照实现里的布尔键还原成字面键名（见 `test_matches_reference_implementation`）。"""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key is True:
                key = "on"
            elif key is False:
                key = "off"
            out[key] = _normalize_ref(value)
        return out
    if isinstance(node, list):
        return [_normalize_ref(item) for item in node]
    return node


class TestSubset(unittest.TestCase):
    def test_samples(self):
        for name, text in SAMPLES.items():
            with self.subTest(name=name):
                self.assertIsInstance(yaml_min.load(text), (dict, list))

    def test_jobs_steps_extraction(self):
        node = yaml_min.load("jobs:\n  j:\n    steps:\n      - name: a\n        run: b\n"
                             "      - uses: x@v1\n")
        steps = yaml_min.get_path(node, "jobs.j.steps")
        self.assertEqual(["a", None], [s.get("name") for s in steps])

    def test_alias_is_kept_as_text_not_reference(self):
        # `&x` 当标量文本读（本子集不解析引用）；其下序列仍归该键
        node = yaml_min.load("a: &x\n  - 1\nb: *x\n")
        self.assertEqual([1], node["a"])
        self.assertEqual("*x", node["b"])

    def test_get_path_missing_is_none(self):
        node = yaml_min.load("a:\n  b: 1\n")
        self.assertIsNone(yaml_min.get_path(node, "a.c"))
        self.assertIsNone(yaml_min.get_path(node, "a.b.c"))
        self.assertEqual(1, yaml_min.get_path(node, "a.b"))

    def test_tab_indent_is_rejected(self):
        with self.assertRaises(yaml_min.YamlSubsetError):
            yaml_min.load("a:\n\tb: 1\n")

    def test_error_not_silently_none(self):
        # 不支持的写法必须报错——静默返回 None 会让"读不出来"与"没有该键"分不开
        # （`a:\n  b: c: d` **不在**此列：它是合法 YAML，按字符串值读入即可，
        #  见 test_colon_in_bare_scalar_is_not_an_error）
        for bad in ("a:\n  - b\n   c: 1\n", "a: {b: 1}\n", "a:\n\tb: 1\n", "a:\n  b: 1\n  c\n"):
            with self.subTest(bad=bad):
                with self.assertRaises(yaml_min.YamlSubsetError):
                    yaml_min.load(bad)

    def test_colon_in_bare_scalar_is_not_an_error(self):
        # 含冒号的标量按**字符串**读入，不报错：判红会把整份配置算成"读不出来"，
        # 连真正该核的执行单位一起拦掉。值不进判据（"这一步有没有时限"只看键）。
        # 注：裸串 `a: echo x: y` 属 YAML 的内联复合结构（PyYAML 亦拒收），
        # 本子集不实现该形态，一律按字符串读——差异方向是"多读进值、不误报读不出来"。
        self.assertEqual({"a": "echo x: y"}, yaml_min.load("a: echo x: y\n"))
        self.assertEqual({"a": {"b": "c: d"}}, yaml_min.load("a:\n  b: c: d\n"))
        self.assertEqual("echo x: y", yaml_min.load("a: 'echo x: y'\n")["a"])

    def test_sequence_indented_like_parent_key(self):
        # YAML 合法且手写配置最常见的写法：序列项与父键同缩进
        node = yaml_min.load("jobs:\n  j:\n    steps:\n    - run: x\n    - run: y\n")
        steps = yaml_min.get_path(node, "jobs.j.steps")
        self.assertEqual(["x", "y"], [step["run"] for step in steps])

    @unittest.skipIf(_ref is None, "装了 PyYAML 才做对照")
    def test_matches_reference_implementation(self):
        """与参照实现（PyYAML）逐样本对照。

        **已知且刻意的差异只有一处**：键名一律按字符串取，不做 YAML 1.1 的隐式类型推断。
        PyYAML 把键 `on:` 读成布尔 `True`（`yes`/`no`/`on`/`off` 同理），而流水线配置里的
        `on:` 是**键名**（触发条件），按字符串取才与配置语义一致——故对照时把参照侧的
        布尔键还原成它的字面写法再比。
        """
        for name, text in SAMPLES.items():
            with self.subTest(name=name):
                refs = _ref.safe_load(text)
                self.assertEqual(_normalize_ref(refs), yaml_min.load(text))


if __name__ == "__main__":
    unittest.main(verbosity=2)
