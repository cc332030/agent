#!/usr/bin/env python3
"""`fetch-specs.py` 的单元测试（纯 stdlib unittest）。

为什么单列这一份：这个脚本**天天在别人机器上跑**，而它的失效形态从来不是"某一行算错了"，
是"报出来的是另一件事"——`'Config' object has no attribute 'prompt_command_name'`
（看着像配置缺了一节，实际是半份源码被换到真身上）、
`no working python interpreter found`（机器上明明有 python，实际是整组安装脚本缺了一样、
脚本在 import 阶段就退出了）。这两条都不在"跑一遍看结果对不对"的射程里：前者的现场是
一个正在被覆盖的文件，后者要连薄壳一起跑才看得见。

故这里的用例按**失效形态**组织，不按函数组织：
  * 起得来（缺整组时仍要说清缺什么、别把方向指错）；
  * 自更新（半份源码不得换上、候选的 `is_real` 与真身一致）；
  * 取回契约（失败的形态一律归一成 `OSError`，不让 `HTTPException` 穿掉收尾）；
  * 入口/探针（`--probe` 不写盘、不换自身；退出码仍按 0/1/2 分）。

**只跑本机的解释器与文件系统，不联网**：需要远端的地方一律把 `fetch_text` 换掉。
"""
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "fetch-specs.py")
PATHCONFIG = os.path.join(HERE, "pathconfig.py")
CONFIG = os.path.join(HERE, "specs-config.toml")


def _stage(directory, with_pathconfig=True, with_config=True):
    """把脚本与（可选的）读取层/配置摆到 `directory` 下，返回脚本路径。

    **三样分开开关**：缺组这件事本身就是要测的失效形态——三样永远一起摆时，
    "缺了会说不清"那条路一次都走不到。
    """
    for src, keep in ((SCRIPT, True), (PATHCONFIG, with_pathconfig), (CONFIG, with_config)):
        if keep:
            shutil.copyfile(src, os.path.join(directory, os.path.basename(src)))
    return os.path.join(directory, os.path.basename(SCRIPT))


def _run(script, *args, env=None):
    """在子进程里真跑一遍脚本（import 期的副作用只能这样测）。返回 (退出码, stdout, stderr)。"""
    full_env = dict(os.environ)
    full_env.pop("AGENT_SPECS_BASE", None)
    full_env.update(env or {})
    proc = subprocess.run([sys.executable, script, *args],
                          capture_output=True, text=True, env=full_env, timeout=120)
    return proc.returncode, proc.stdout, proc.stderr


def _load_module(directory):
    """按文件路径加载模块（与执行侧同一种加载方式），供直接调函数的用例使用。"""
    import importlib.util
    path = os.path.join(directory, os.path.basename(SCRIPT))
    spec = importlib.util.spec_from_file_location("_fetch_specs_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _TmpDirCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="fetch-specs-test-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def mkdir(self, name):
        path = os.path.join(self.root, name)
        os.makedirs(path, exist_ok=True)
        return path


class TestStartsUp(_TmpDirCase):
    """**起得来那一段**：三样摆在旁边就跑得起来；缺哪样都要说清缺的是整组。"""

    def test_runs_with_group_beside_script(self):
        landing = self.mkdir("landing")
        script = _stage(landing)
        code, out, err = _run(script, "--probe")
        self.assertEqual(0, code, err)
        self.assertIn("探针通过", out)

    def test_probe_does_not_touch_disk(self):
        # `--probe` 是入口每探一个解释器就跑一次的那一步：它写盘就是"探一遍顺手改了落点"
        landing = self.mkdir("landing")
        script = _stage(landing)
        before = sorted(os.listdir(landing))
        code, _, err = _run(script, "--probe")
        self.assertEqual(0, code, err)
        # 一个字节都不多：加载读取层时开着的 `__pycache__` 曾让每次探针都在落点根下留一份目录
        # （落点收紧成只读之后那一步还会静默失败，"只读"从此多一条看不见的例外）
        self.assertEqual(before, sorted(os.listdir(landing)))

    def test_missing_config_names_the_whole_group(self):
        # 本机实测的失效形态：落点里没有配置，薄壳把"脚本 import 期退出"统统报成
        # "no working python interpreter found"——查的方向整条是错的。故这里要的
        # 不是"退出码非 0"，而是**报错里说的是整组、且给出补齐的路**。
        landing = self.mkdir("landing")
        script = _stage(landing, with_config=False)
        code, _, err = _run(script, "--probe")
        self.assertEqual(2, code, err)
        self.assertIn("specs-config.toml", err)
        self.assertIn("整组", err)
        self.assertIn("取一次安装脚本", err)
        self.assertNotIn("Traceback", err)

    def test_missing_pathconfig_names_the_whole_group(self):
        landing = self.mkdir("landing")
        script = _stage(landing, with_pathconfig=False)
        code, _, err = _run(script, "--probe")
        self.assertEqual(2, code, err)
        self.assertIn("pathconfig.py", err)
        self.assertIn("整组", err)
        self.assertNotIn("Traceback", err)

    def test_missing_group_message_written_once(self):
        # 同一件事的文案只有一处：读取层与执行侧各写一份时，读者得对着两句各自猜缺的是哪一层
        with open(PATHCONFIG, encoding="utf-8") as fh:
            pathconfig_text = fh.read()
        with open(SCRIPT, encoding="utf-8") as fh:
            script_text = fh.read()
        self.assertIn("def missing_config_message", pathconfig_text)
        self.assertIn("missing_config_message", script_text)
        for shared in ("不得退回各自写死的默认值，那就是第二份来源",):
            self.assertEqual(1, pathconfig_text.count(shared),
                             "这句该在读取层里有且只有一份")
            self.assertEqual(0, script_text.count(shared),
                             "执行侧不该再抄一遍——抄了就是两处文案、读者得对着两句各自猜")


class TestThisFile(_TmpDirCase):
    """`_this_file`：`__file__` 不给时不得 `NameError`（`python3 - < x.py` 那类跑法）。"""

    def test_falls_back_to_argv0(self):
        landing = self.mkdir("landing")
        _stage(landing)
        module = _load_module(landing)
        # 模拟 `exec(compile(...))`：模块里没有 `__file__`
        saved = module.__dict__.pop("__file__")
        saved_argv = sys.argv
        try:
            sys.argv = [os.path.join(landing, "fetch-specs.py")]
            self.assertTrue(module._this_file().endswith("fetch-specs.py"))
        finally:
            sys.argv = saved_argv
            module.__dict__["__file__"] = saved

    def test_returns_empty_string_when_nothing_known(self):
        landing = self.mkdir("landing")
        _stage(landing)
        module = _load_module(landing)
        saved = module.__dict__.pop("__file__")
        saved_argv = sys.argv
        try:
            sys.argv = []
            self.assertEqual("", module._this_file())
        finally:
            sys.argv = saved_argv
            module.__dict__["__file__"] = saved

    def test_exec_without_file_global_still_imports(self):
        # 端到端：把脚本当"一段代码"编译执行一遍，不让模块里出现 `__file__`
        landing = self.mkdir("landing")
        _stage(landing)
        probe = os.path.join(landing, "run_without_file.py")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write(
                "import sys\n"
                f"code = compile(open({os.path.join(landing, 'fetch-specs.py')!r}, "
                "encoding='utf-8').read(), 'fetch-specs.py', 'exec')\n"
                "globs = {'__name__': 'not_main'}\n"
                "exec(code, globs)\n"
                "print('OK', 'Config' in dir(globs['_PATHCONFIG'].__class__))\n")
        proc = subprocess.run([sys.executable, probe], capture_output=True, text=True,
                              cwd=landing, timeout=120)
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("OK", proc.stdout)


class TestSelfUpdateGuard(_TmpDirCase):
    """**半份源码不得换到真身上**——`AttributeError` 那条报错的根因。"""

    def _module(self):
        landing = self.mkdir("landing")
        _stage(landing)
        return _load_module(landing)

    def test_readable_as_script_accepts_complete_file(self):
        module = self._module()
        self.assertTrue(module._readable_as_script(module._this_file()))

    def test_readable_as_script_rejects_truncated_file(self):
        # 真实的截断是**写到一半**（上一轮落盘还在写、盘上被截断），不是"写了一句半截的属性访问"
        # ——后者语法合法、编译得过去，用它会把这个用例测成一句空话。故这里按字节截。
        #
        # **切点由"截出来确实编译不过"决定**：整行截断时，末尾若恰好是某个块最后一个完整
        # 语句（或一个刚开的 `def`），截出来的仍是一份合法模块，用例就测成了空话。故从中间
        # 往后找**第一个编译不过**的行边界，并当场核一遍——用例自己要能证明它截的是半份。
        module = self._module()
        with open(SCRIPT, encoding="utf-8") as fh:
            lines = fh.read().split("\n")
        truncated = os.path.join(self.root, "half.py")
        cut = None
        for candidate in range(len(lines) // 2, len(lines) - 1):
            with open(truncated, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines[:candidate]) + "\n")
            if not module._readable_as_script(truncated):
                cut = candidate
                break
        self.assertIsNotNone(cut, "没找到编译不过的截断点")
        with self.assertRaises(SyntaxError):
            compile("\n".join(lines[:cut]) + "\n", truncated, "exec")

    def test_readable_as_script_rejects_missing_and_binary(self):
        module = self._module()
        self.assertFalse(module._readable_as_script(os.path.join(self.root, "nope.py")))
        binary = os.path.join(self.root, "bin.py")
        with open(binary, "wb") as fh:
            fh.write(b"\xff\xfe\x00\x00not utf-8")
        self.assertFalse(module._readable_as_script(binary))

    def test_readable_as_script_accepts_bom_file(self):
        # 带 BOM 的 `.py` 解释器照样跑得起来：这里按字节读、交给 `compile` 判，
        # 文本模式 utf-8 会 `UnicodeDecodeError`——那样这里说"读不成"、`execv` 却跑得起来
        module = self._module()
        bom = os.path.join(self.root, "bom.py")
        with open(bom, "wb") as fh:
            fh.write(b"\xef\xbb\xbfX = 1\r\n")
        self.assertTrue(module._readable_as_script(bom))

    def test_empty_file_is_still_readable(self):
        # 空文件编译得过去（语法上合法的空模块）：判据是"读得成一整份"，不是"有内容"
        module = self._module()
        empty = os.path.join(self.root, "empty.py")
        open(empty, "w", encoding="utf-8").close()
        self.assertTrue(module._readable_as_script(empty))

    def test_take_over_self_refuses_truncated_source(self):
        # 真身就是本轮这个文件、要拷过去的那份是半份 → **必须不换**，且要说清"读不成一整份"
        module = self._module()
        local = module._this_file()
        with open(local, "rb") as fh:
            original = fh.read()
        def restore():
            with open(local, "wb") as fh:
                fh.write(original)

        self.addCleanup(restore)
        target = os.path.join(self.root, "half-update.py")
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("def a():\n    return\nhalf = ")
        module._real_script = lambda: local
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            module._take_over_self(local, target)
        self.assertIn("读不成一份完整的脚本", buf.getvalue())
        with open(local, "rb") as fh:
            self.assertEqual(original, fh.read(), "半份源码被换到真身上了")

    def test_hand_off_self_refuses_truncated_note(self):
        # 兜底路径（上一轮留下的标记）与常规路径是同一道闸：标记指向的那份读不成一整份时
        # 不得换到真身上——它同样是"写到一半"的那一份
        module = self._module()
        local = module._this_file()
        with open(local, "rb") as fh:
            original = fh.read()
        def restore():
            with open(local, "wb") as fh:
                fh.write(original)

        self.addCleanup(restore)
        half = os.path.join(self.root, "half-update.py")
        with open(half, "w", encoding="utf-8") as fh:
            fh.write("half = ")
        note = f"{local}{module.SELF_HANDOFF_SUFFIX}"
        with open(note, "w", encoding="utf-8") as fh:
            fh.write(half + "\n")
        saved_argv = sys.argv
        sys.argv = [local]
        module._real_script = lambda: local
        buf = io.StringIO()
        try:
            with contextlib.redirect_stderr(buf):
                module.hand_off_self()
        finally:
            sys.argv = saved_argv
            if os.path.isfile(note):
                os.remove(note)
        self.assertIn("读不成一份完整的脚本", buf.getvalue())
        with open(local, "rb") as fh:
            self.assertEqual(original, fh.read(), "半份源码被换到真身上了")

    def test_self_update_candidates_marks_root_as_real_when_no_self(self):
        # 读不到真身时，落点根下那份**就是**真身：标错时它会用原样文件名覆盖正在跑的脚本
        module = self._module()
        module._real_script = lambda: None
        out_dir = self.mkdir("slot")
        cwd = self.mkdir("cwd")
        candidates = list(module._self_update_candidates(out_dir, cwd))
        self.assertTrue(candidates)
        target, where = candidates[0]
        self.assertIn("= 真身", where)
        self.assertTrue(os.path.basename(target).startswith("."))
        self.assertTrue(target.endswith(module.SELF_UPDATE_SUFFIX))


class TestFetchContract(_TmpDirCase):
    """`fetch_text` 的契约：失败一律 `OSError`（`HTTPException` 不得穿到 `main`）。"""

    def _module(self):
        landing = self.mkdir("landing")
        _stage(landing)
        return _load_module(landing)

    def test_http_exception_becomes_oserror(self):
        import http.client
        module = self._module()

        def boom(*_a, **_kw):
            raise http.client.IncompleteRead(b"partial")

        module.urllib.request.urlopen = boom
        with self.assertRaises(OSError):
            module.fetch_text("https://example.invalid", "specs/x.adoc")

    def test_non_utf8_is_oserror(self):
        module = self._module()

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def read(self):
                return b"\xff\xfe\x00binary"

        module.urllib.request.urlopen = lambda *_a, **_kw: Response()
        with self.assertRaises(OSError):
            module.fetch_text("https://example.invalid", "specs/x.adoc")

    def test_site_index_is_not_a_spec(self):
        # 站点对未命中的路径回落成首页 HTML + 200：只判状态码会把"不存在"当成取到了
        module = self._module()

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def read(self):
                return b"<!DOCTYPE html><html><title>x</title></html>"

        module.urllib.request.urlopen = lambda *_a, **_kw: Response()
        with self.assertRaises(OSError):
            module.fetch_text("https://example.invalid", "specs/nope.adoc")

    def test_site_index_is_accepted_when_named(self):
        # 索引页本身就是首页 HTML 那一份：由调用方点名要它（`FOLLOWUP_FILES`）
        module = self._module()

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def read(self):
                return b"<!DOCTYPE html><html><title>x</title></html>"

        module.urllib.request.urlopen = lambda *_a, **_kw: Response()
        text = module.fetch_text("https://example.invalid", "index.html", missing_ok=True)
        self.assertIn("<!DOCTYPE html>", text)


class TestManifestParsing(_TmpDirCase):
    """清单解析：**登记在哪就取哪些**，扫目录会把草稿与素材一并取到调用方手里。"""

    def _module(self):
        landing = self.mkdir("landing")
        _stage(landing)
        return _load_module(landing)

    def test_prompt_targets_from_index(self):
        module = self._module()
        index = ("* link:prompts/review.adoc[评审]\n"
                 "* link:prompts/_common.txt[公共片段]\n"
                 "* link:prompts/refactor.adoc[重构]\n")
        self.assertEqual(["prompts/refactor.adoc", "prompts/review.adoc"],
                         module.prompt_targets(index))

    def test_prompt_targets_ignores_underscore_files(self):
        module = self._module()
        self.assertEqual([], module.prompt_targets("link:prompts/_common.txt[x]\n"))

    def test_prompt_index_target_absent_is_not_an_error(self):
        module = self._module()

        def boom(*_a, **_kw):
            raise AssertionError("认不出登记处时不该联网取它")

        module.fetch_text = boom
        self.assertEqual((None, ""), module.prompt_index_target("https://x.invalid", "无关正文"))

    def test_manifest_without_specs_is_an_error(self):
        module = self._module()
        module.fetch_text = lambda *_a, **_kw: "一份 specs/ 都没有"
        with self.assertRaises(OSError):
            module.manifest_targets("https://x.invalid")


class TestLayout(_TmpDirCase):
    """落点与清单路径：**只有一处**、且按内容分槽（换 `--base` 不互相覆盖）。"""

    def _module(self):
        landing = self.mkdir("landing")
        _stage(landing)
        return _load_module(landing)

    def test_cache_slot_dir_is_stable_across_trailing_slash(self):
        module = self._module()
        home = self.mkdir("home")
        a = module.cache_slot_dir(home, "https://agent.example.com")
        b = module.cache_slot_dir(home, "https://agent.example.com/")
        self.assertEqual(a, b)

    def test_cache_slot_dir_differs_across_sources(self):
        module = self._module()
        home = self.mkdir("home")
        self.assertNotEqual(module.cache_slot_dir(home, "https://a.example.com"),
                            module.cache_slot_dir(home, "https://b.example.com"))

    def test_target_path_strips_source_dir_for_install_scripts(self):
        # 落点根下只放文件名：带 `script/` 那一层时，"下次重装直接跑落点里的入口"会找不到它
        module = self._module()
        out_dir = self.mkdir("out")
        for rel in module.INSTALL_SCRIPTS:
            dest = module.target_path(out_dir, rel)
            self.assertEqual(out_dir, os.path.dirname(dest))
        self.assertEqual(os.path.join(out_dir, *"specs/stack/python.adoc".split("/")),
                         module.target_path(out_dir, "specs/stack/python.adoc"))

    def test_shared_cache_dir_rejects_root(self):
        # `HOME` 为空串时 `expanduser` 返回根目录：只判空串会让副本静默落到根下
        module = self._module()
        module._user_home_dir = lambda: os.sep
        with self.assertRaises(ValueError):
            module.shared_cache_dir()

    def test_shared_cache_dir_rejects_missing(self):
        module = self._module()
        module._user_home_dir = lambda: os.path.join(self.root, "不存在的家")
        with self.assertRaises(ValueError):
            module.shared_cache_dir()


class TestEntryShells(unittest.TestCase):
    """两个薄壳：**不假定有 python**、探到不等于跑得起来、退出码原样传回。

    只在本机是 POSIX 时真跑 `.sh`（Windows 上 `.bat` 的行为由它自己的注释与
    `check_specs` 的静态判据守，单测里不假装能跑 cmd）。
    """

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="fetch-specs-shell-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def _stage_group(self):
        for src in (SCRIPT, PATHCONFIG, CONFIG):
            shutil.copyfile(src, os.path.join(self.root, os.path.basename(src)))
        return shutil.copyfile(os.path.join(HERE, "fetch-specs.sh"),
                               os.path.join(self.root, "fetch-specs.sh"))

    @unittest.skipIf(os.name == "nt", "POSIX 薄壳只在 POSIX 上真跑")
    def test_shell_passes_probe_through(self):
        shell = self._stage_group()
        os.chmod(shell, 0o755)
        proc = subprocess.run([shell, "--probe"], capture_output=True, text=True, timeout=120)
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("探针通过", proc.stdout)

    @unittest.skipIf(os.name == "nt", "POSIX 薄壳只在 POSIX 上真跑")
    def test_shell_returns_exit_code_unchanged(self):
        # 缺整组时脚本自己给 2：薄壳不得把它抹成 0（"被当成取到了"）
        for src in (SCRIPT,):
            shutil.copyfile(src, os.path.join(self.root, os.path.basename(src)))
        shell = shutil.copyfile(os.path.join(HERE, "fetch-specs.sh"),
                                os.path.join(self.root, "fetch-specs.sh"))
        os.chmod(shell, 0o755)
        proc = subprocess.run([shell, "--probe"], capture_output=True, text=True, timeout=120)
        self.assertEqual(2, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("整组", proc.stderr)


if __name__ == "__main__":
    unittest.main()
