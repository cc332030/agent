#!/usr/bin/env python3
"""『请求落点须被断言限制在本机』的用例（本机跑，不连任何外部服务）。

判据分两半，两半都在这里跑：

* **断言件本身**（`assert_loopback`）——`127.0.0.1`、`::1`、IPv4-mapped 的回环放行；
  `localhost` 按**解析结果**判（本机 hosts 必然指向回环）、`10.0.0.5.nip.io` 这类**名字**
  解析到内网 IP 时判红——名字不是判据，落点才是（这正是"配置里写了 localhost 不算断言"
  要治的形态）；解析不出地址时**判红**、不静默跳过。
* **现场自检**（`check_repository`）——发出请求却没有回环断言的用例被报出；有断言的不报；
  只出现请求客户端字样、没有发起动作的校验脚本不误伤。

外部材料只给方向（RFC 6890 界定 127.0.0.0/8、::1 及 IPv4-mapped 形式属回环），
用例是与它一致的判据化取舍。全部解析只走本机 hosts 与字面量，不发任何网络请求。
"""

import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import local_service_assert as m  # noqa: E402


class TestLoopbackAssertion(unittest.TestCase):
    """断言件：判的是**解析后的落点**，不是配置里的字面量。"""

    def test_ipv4_loopback_passes(self):
        self.assertEqual(["127.0.0.1"], m.assert_loopback("127.0.0.1"))

    def test_loopback_range_passes(self):
        # 127.0.0.0/8 整段都是回环（RFC 6890），不只是 127.0.0.1
        self.assertEqual(["127.0.0.53"], m.assert_loopback("127.0.0.53"))

    def test_ipv6_loopback_passes(self):
        self.assertEqual(["::1"], m.assert_loopback("::1"))

    def test_localhost_name_passes(self):
        # 名字不是判据，解析结果才是；本机 hosts 必然把 localhost 解析到回环
        self.assertTrue(all(m._is_loopback(a) for a in m.assert_loopback("localhost")))

    def test_ipv4_mapped_loopback_passes(self):
        # ::ffff:127.0.0.1 按地址族看是 IPv6，实际落点是 IPv4 回环
        self.assertTrue(m._is_loopback("::ffff:127.0.0.1"))

    def test_name_resolving_outside_fails(self):
        # "配置里写了名字"不构成限制：名字解析到内网 IP 就该红。
        # 夹具取一个**必然**解析成非回环的名字（本地 hosts 只会把 `localhost` 指到回环，
        # 用它当反例时用例在某些环境里会假通过）。
        with mock.patch.object(m, "resolve_addresses", return_value=["10.0.0.5"]):
            with self.assertRaises(m.LocalServiceViolation) as ctx:
                m.assert_loopback("db.internal")
        self.assertIn("不在本机（回环）范围内", str(ctx.exception))

    def test_public_address_fails(self):
        with self.assertRaises(m.LocalServiceViolation):
            m.assert_loopback("8.8.8.8")

    def test_unresolvable_fails_not_skipped(self):
        # 解析不出地址时**按失败处理**：静默跳过等于这条断言从来没拦过东西
        with self.assertRaises(m.LocalServiceViolation) as ctx:
            m.assert_loopback("no-such-host.invalid")
        self.assertIn("不得静默跳过", str(ctx.exception))

    def test_private_address_fails(self):
        # 内网 IP 也不是本机（规范判定标准①点名内网 IP）
        with self.assertRaises(m.LocalServiceViolation):
            m.assert_loopback("192.168.1.10")


class TestRepositoryScan(unittest.TestCase):
    """现场自检：发出请求却没有回环断言的用例被报出。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        # 扫描面收窄到夹具：夹具按 `src/` 落盘（换成仓库根时，夹具命不中任何文件、
        # 判据会退化成"核不到"，用例就白跑了）。
        rules = dict(m._rules())
        rules["scan_prefixes"] = ["src/"]
        rules["scan_suffixes"] = [".py", ".java"]
        rules["guard_prefixes"] = ["script/"]
        rules["guard_suffixes"] = ["_test.py"]
        patcher = mock.patch.object(m, "_rules", return_value=rules)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write(self, rel, text):
        path = os.path.join(self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def test_request_without_assertion_reports(self):
        self._write("src/test/ApiTest.java",
                    "import org.springframework.web.client.RestTemplate;\n"
                    "// RestTemplate rt = new RestTemplate();\n"
                    "class ApiTest {\n"
                    "  void call() { restTemplate.getForObject(\"http://10.0.0.5/x\", String.class); }\n"
                    "}\n")
        problems = m.check_repository(self.root)
        self.assertEqual(1, len(problems))
        self.assertIn("没有一条会失败的本机（回环）断言", problems[0][1])

    def test_request_with_assertion_passes(self):
        self._write("src/test/ApiTest.java",
                    "import org.springframework.web.client.RestTemplate;\n"
                    "// RestTemplate rt = new RestTemplate();\n"
                    "class ApiTest {\n"
                    "  void call() {\n"
                    "    assertTrue(InetAddress.getByName(base).isLoopbackAddress());\n"
                    "    restTemplate.getForObject(base, String.class);\n"
                    "  }\n"
                    "}\n")
        self.assertEqual([], m.check_repository(self.root))

    def test_python_assertion_passes(self):
        self._write("src/tests/api_test.py",
                    "import requests\n"
                    "from guard.local_service_assert import assert_loopback\n"
                    "def test_api():\n"
                    "    assert_loopback(cfg.base)\n"
                    "    requests.get(cfg.base)\n")
        self.assertEqual([], m.check_repository(self.root))

    def test_file_without_request_not_reported(self):
        self._write("src/tests/math_test.py", "def test_sum():\n    assert 1 + 1 == 2\n")
        self.assertEqual([], m.check_repository(self.root))

    def test_client_name_without_call_not_reported(self):
        # 校验脚本里提到请求客户端（它核的正是别人的用例），自己并不发请求——不得误伤
        self._write("src/check_test.py",
                    "MARKERS = [\"HttpClient\", \"RestTemplate\"]\nprint(MARKERS)\n")
        self.assertEqual([], m.check_repository(self.root))

    def test_literal_comparison_is_not_assertion(self):
        # 只比字面量的"断言"不构成限制：换个解析结果照样通过
        self._write("src/test/ApiTest.java",
                    "import org.springframework.web.client.RestTemplate;\n"
                    "// RestTemplate rt = new RestTemplate();\n"
                    "class ApiTest {\n"
                    "  void call() {\n"
                    "    org.junit.Assert.assertEquals(\"localhost\", host);\n"
                    "    client.execute(req);\n"
                    "  }\n"
                    "}\n")
        self.assertEqual(1, len(m.check_repository(self.root)))

    def test_guard_surface_scanned_without_src(self):
        # 本仓库的用例落在 `script/` 下、`src/` 一片空着：两片都要收，否则本仓库那一片
        # 一份都没核到、却仍是绿的（新建的断言件正是要跳过的那种形态）。
        rules = dict(m._rules())
        self._write("script/api_test.py",
                    "import requests\n"
                    "def test_api():\n"
                    "    r = requests.get(\"http://10.0.0.5/x\")\n"
                    "    print(r.text)\n")
        with mock.patch.object(m, "_rules", return_value=rules):
            problems = m.check_repository(self.root)
        self.assertEqual(["script/api_test.py"], [rel for rel, _ in problems])

    def test_nothing_scanned_is_error_not_pass(self):
        # 两片都收不到文件时按错误退出：'核不到'不得记作'核过且通过'
        rules = dict(m._rules())
        rules["scan_prefixes"] = ["src/"]
        rules["guard_prefixes"] = ["nowhere/"]
        os.makedirs(os.path.join(self.root, "src"), exist_ok=True)
        with mock.patch.object(m, "_rules", return_value=rules):
            with self.assertRaises(SystemExit):
                m.check_repository(self.root)

    def test_prefix_substring_not_counted(self):
        # `_run_fetch(` 不是 `fetch(`：拼接串与自建函数不应把文件判成请求类用例
        self._write("src/tests/run_test.py",
                    "def _run_fetch(base):\n    return base\n"
                    "def test_it():\n    assert _run_fetch('x') == 'x'\n")
        self.assertEqual([], m.check_repository(self.root))


class TestAssertionsRunOnThisMachine(unittest.TestCase):
    """**这条判据在本机之所以成立**：用例自己就在本机跑绿（不连任何外部服务）。"""

    def test_repo_scan_runs_locally(self):
        repo_root = os.path.dirname(os.path.dirname(HERE))
        rules = m._rules()
        # 本仓库那一片（`guard_*`）确实收得到用例文件——"一份都没核到"不得记作通过。
        # 本仓库的用例是 `script/` 下的 `*_test.py`，只落在这一片；`scan_*` 那是给
        # 引用方项目测试源码树的常见落点。
        files = [rel for name, surfaced in m._scan_surfaces(repo_root, rules)
                 for rel in surfaced if name == "guard"]
        self.assertTrue(files, "本仓库那一片扫描面（`guard_*`）下没有收得到用例文件"
                               "——这条判据在本机跑不起来")
        self.assertIn("script/guard/local_service_assert_test.py", files)
        # 与官方 CLI 同一路径真跑一遍：子进程要求**本机装齐、且全程不连外部服务**
        proc = subprocess.run([sys.executable, os.path.join(HERE, "local_service_assert.py"),
                               "--repo", repo_root], capture_output=True, text=True)
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("OK", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
