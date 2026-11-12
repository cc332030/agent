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

**两个薄壳都真跑**：`.sh` 在 POSIX 上直接跑；`.bat` 在 Windows 上直接用 cmd 跑，
其余平台**借 Wine 跑 `cmd /c`**（用户口径：Wine 上跑得起来就算数）——`.bat` 是纯 ASCII +
CRLF + `for`/`call`/标签的一串东西，静态判据核得出"长什么样"，核不出"cmd 解不解析得动"。
本机没有 wine、或 wine 自己跑不起来时**如实跳过并写明理由**（那种失败不是 `.bat` 的问题）。

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

    def test_self_update_temp_name_is_fixed_without_pid(self):
        # 中转件名**不带 pid**（用户口径：临时文件名要固定，带 pid 的名字每轮一个、
        # 换成功后谁也不认，只会攒下一堆 `.fetch-specs.py.<pid>.update`）
        module = self._module()
        real = _stage(self.mkdir("realdir"))
        module._real_script = lambda: real
        out_dir = self.mkdir("slot")
        cwd = self.mkdir("cwd")
        target, _ = list(module._self_update_candidates(out_dir, cwd))[0]
        self.assertEqual(".fetch-specs.py.update", os.path.basename(target))
        self.assertNotIn(str(os.getpid()), os.path.basename(target))


class TestSelfUpdateHousekeeping(_TmpDirCase):
    """自更新中转件与落点根的**残留清扫**（用户口径：临时文件名固定、落点下没有多余文件）。"""

    def _module(self):
        landing = self.mkdir("landing")
        _stage(landing)
        return _load_module(landing)

    def test_sweep_removes_stale_temps_without_note(self):
        # 固定名残件（进程死在落盘与换上之间）与历史带 pid 的旧名都清
        module = self._module()
        directory = self.mkdir("realdir")
        fixed = os.path.join(directory, ".fetch-specs.py.update")
        legacy = os.path.join(directory, ".fetch-specs.py.10600.update")
        for path in (fixed, legacy):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("stale = True\n")
        module._sweep_self_update_stale(directory)
        self.assertFalse(os.path.exists(fixed))
        self.assertFalse(os.path.exists(legacy))

    def test_sweep_keeps_temp_pointed_by_live_note(self):
        # 有活着的待换标记指着的那份**不清**（真身下一轮要消费它），没被指着的旧名照清
        module = self._module()
        directory = self.mkdir("realdir")
        pointed = os.path.join(directory, ".fetch-specs.py.update")
        unpointed = os.path.join(directory, ".fetch-specs.py.10600.update")
        for path in (pointed, unpointed):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("fresh = True\n")
        note = os.path.join(directory, "fetch-specs.py.handoff")
        with open(note, "w", encoding="utf-8") as fh:
            fh.write(pointed + "\n")
        module._sweep_self_update_stale(directory)
        self.assertTrue(os.path.exists(pointed), "标记指着的中转件被清了")
        self.assertFalse(os.path.exists(unpointed))
        self.assertTrue(os.path.exists(note), "标记本身被清了")

    def test_landing_root_sweep_removes_extras_keeps_layout(self):
        # 落点根只该有：安装脚本、配置、附随文件、口令入口、来源槽目录；
        # `__pycache__` 与排布外的散文件清掉，别的目录（可能是别的来源槽）不碰
        module = self._module()
        root = self.mkdir("cacheroot")
        keep_files = ["fetch-specs.py", "fetch-specs.sh", "fetch-specs.bat",
                      "pathconfig.py", "specs-config.toml", "index.html",
                      "use-prompt.sh", "use-prompt.bat"]
        for name in keep_files:
            with open(os.path.join(root, name), "w", encoding="utf-8") as fh:
                fh.write("# placeholder\n")
        os.makedirs(os.path.join(root, "prompts"))
        with open(os.path.join(root, "prompts", "_common.txt"), "w",
                  encoding="utf-8") as fh:
            fh.write("include::\n")
        os.makedirs(os.path.join(root, "agent.example.com"))
        os.makedirs(os.path.join(root, "__pycache__"))
        with open(os.path.join(root, "__pycache__", "pathconfig.cpython-314.pyc"),
                  "wb") as fh:
            fh.write(b"\x00")
        stray = os.path.join(root, "leftover.txt")
        with open(stray, "w", encoding="utf-8") as fh:
            fh.write("stale\n")
        module._sweep_landing_root(root)
        for name in keep_files:
            self.assertTrue(os.path.isfile(os.path.join(root, name)), f"{name} 被误清")
        self.assertTrue(os.path.isfile(os.path.join(root, "prompts", "_common.txt")))
        self.assertTrue(os.path.isdir(os.path.join(root, "agent.example.com")),
                        "来源槽目录被误清")
        self.assertFalse(os.path.exists(os.path.join(root, "__pycache__")))
        self.assertFalse(os.path.exists(stray))

    def test_landing_root_sweep_removes_readonly_pycache(self):
        # 本仓库实测：`__pycache__` 里的 .pyc 带只读位（落点收紧过）时，
        # `rmtree(ignore_errors=True)` 整树静默失败——清了一轮它还在，看着清了其实没清。
        # 故须逐节点补写位再删（`_self_update_discard_dir`）。
        module = self._module()
        root = self.mkdir("cacheroot")
        with open(os.path.join(root, "fetch-specs.py"), "w", encoding="utf-8") as fh:
            fh.write("# placeholder\n")
        pycache = os.path.join(root, "__pycache__")
        os.makedirs(pycache)
        pyc = os.path.join(pycache, "pathconfig.cpython-314.pyc")
        with open(pyc, "wb") as fh:
            fh.write(b"\x00")
        os.chmod(pyc, 0o444)
        os.chmod(pycache, 0o555)
        module._sweep_landing_root(root)
        self.assertFalse(os.path.exists(pycache),
                         "只读位没补、整树静默留下了（本仓库实测的假清形态）")

    def test_landing_root_sweep_keeps_temp_pointed_by_live_note(self):
        # 落点根下的中转件同样受"活着的标记"保护（真身就在落点根下、换不动时留标记）
        module = self._module()
        root = self.mkdir("cacheroot")
        pointed = os.path.join(root, ".fetch-specs.py.update")
        with open(pointed, "w", encoding="utf-8") as fh:
            fh.write("fresh = True\n")
        note = os.path.join(root, "fetch-specs.py.handoff")
        with open(note, "w", encoding="utf-8") as fh:
            fh.write(pointed + "\n")
        module._sweep_landing_root(root)
        self.assertTrue(os.path.exists(pointed))
        self.assertTrue(os.path.exists(note))


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


class _EntryShellCase(unittest.TestCase):
    """入口薄壳的公共夹具：三样安装脚本摆一处，壳原样同处。"""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="fetch-specs-shell-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def _stage_group(self, *keep):
        """把三样安装脚本摆进落点；`keep` 给定时只摆这几样（缺组的形态）。"""
        wanted = set(keep) or {"script", "pathconfig", "config"}
        for name, src in (("script", SCRIPT), ("pathconfig", PATHCONFIG), ("config", CONFIG)):
            if name in wanted:
                shutil.copyfile(src, os.path.join(self.root, os.path.basename(src)))

    def _shell(self, name):
        path = shutil.copyfile(os.path.join(HERE, name), os.path.join(self.root, name))
        os.chmod(path, 0o755)
        return path


class TestPosixShell(_EntryShellCase):
    """Linux/macOS 薄壳：**不假定有 python**、探到不等于跑得起来、退出码原样传回。

    只在 POSIX 上真跑（`.sh` 在 Windows 上没有能真跑它的默认壳——Windows 上真正会跑的是
    `.bat`，那一侧在 `TestBatchShell`）。

    用例目录：
     * 1 `test_shell_passes_probe_through` — 探针通过（`--probe` 退出 0）
     * 2 `test_shell_returns_exit_code_unchanged` — 缺整组时原样传回 2
    """

    @unittest.skipIf(os.name == "nt", "POSIX 薄壳只在 POSIX 上真跑")
    def test_shell_passes_probe_through(self):
        self._stage_group()
        shell = self._shell("fetch-specs.sh")
        proc = subprocess.run([shell, "--probe"], capture_output=True, text=True, timeout=120)
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("探针通过", proc.stdout)

    @unittest.skipIf(os.name == "nt", "POSIX 薄壳只在 POSIX 上真跑")
    def test_shell_returns_exit_code_unchanged(self):
        # 缺整组时脚本自己给 2：薄壳不得把它抹成 0（"被当成取到了"）
        self._stage_group("script")
        shell = self._shell("fetch-specs.sh")
        proc = subprocess.run([shell, "--probe"], capture_output=True, text=True, timeout=120)
        self.assertEqual(2, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("整组", proc.stderr)


# ── Windows 薄壳那一路：借 Wine 也真跑一遍 ──────────────────────────────────
# `.sh` 原先有两条 POSIX 用例，`.bat` 一行真跑都没有——而它是纯 ASCII + CRLF + `for`/`call`/
# 标签的一串东西：静态判据核得出"长什么样"，核不出 "cmd.exe 到底解不解析得动"。故这里把
# `.bat` 放进真跑的射程：Windows 上直接用 cmd 跑，其余平台借 Wine 跑 `cmd /c`。
WINE_ENV = "FETCH_SPECS_TEST_WINE"     # 显式指定 wine 可执行文件（镜像里未必叫 wine）
WINE_TIMEOUT = 120                     # Wine 首次要建前缀、起 wineserver，比本机跑慢得多


def _wine_program():
    """用哪个 `wine`：先看 `FETCH_SPECS_TEST_WINE`，再看 PATH；都没有时返回 None。

    留这条显式开关是因为镜像里的 wine 未必就叫 `wine`（`wine64`、自建前缀的包装脚本），
    名字不该写死在用例里。
    """
    explicit = os.environ.get(WINE_ENV)
    if explicit:
        return explicit
    return shutil.which("wine")


def _wine(args, env_extra=None):
    """在 Wine 里跑一条命令，返回 (退出码, stdout, stderr)。

    `WINEDEBUG=-all`：Wine 每次都往 stderr 打一大段 `fixme:`／`warn:`（缺字体、缺 mono），
    混进被测输出里就分不清"这句错是谁说的"。stderr 仍单独返回——被测脚本写的那几句在里面。
    """
    env = dict(os.environ)
    env["WINEDEBUG"] = "-all"
    env.update(env_extra or {})
    proc = subprocess.run([_wine_program(), *args], capture_output=True, text=True,
                          env=env, timeout=WINE_TIMEOUT, errors="replace")
    return proc.returncode, proc.stdout, proc.stderr


def _wine_selftest():
    """Wine 在这台机器上**跑不跑得动 cmd.exe**：返回 `(能不能, 为什么不能)`。

    判据只有一条：`cmd /c exit 7` 的退出码原样是 7。装了 wine 不等于跑得动（前缀还没建、
    容器里缺库）：那种失败与"`.bat` 解不解析得动"是两件事，混在一起时人查的是脚本、错在
    环境。故先证这一条，证不过就如实跳过。
    """
    if _wine_program() is None:
        return False, (f"本机没有 wine（可用 {WINE_ENV} 指定）——`.bat` 那一路要真跑一遍 "
                       "cmd.exe 才看得见")
    try:
        code, out, err = _wine(["cmd", "/c", "exit", "7"])
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"wine 起不来：{e}"
    if code != 7:
        return False, (f"wine cmd /c exit 7 的退出码是 {code}（应 7），不是 `.bat` 的问题："
                       f"{(err or out).strip()[:300]}")
    return True, ""


def _wine_dos_path(path):
    """POSIX 路径 → Wine 里的 DOS 路径（默认前缀把 `/` 映到 `Z:`）。"""
    return "Z:" + os.path.abspath(path).replace("/", "\\")


class TestBatchShell(_EntryShellCase):
    """Windows 薄壳：**两边都真跑**（Windows 直接跑，其余平台借 Wine 跑）。

    跑不跑得动分成两层判：先证"这台机器的 wine 真能跑 cmd.exe"（`_wine_selftest`），
    证不过就跳过并写明理由——那种失败与"`.bat` 解不解析得动"是两件事，混在一起时
    人查的是脚本、错在环境。证得过才按退出码与被测输出断言。

    入口口径是"按 PATH 取第一个、不先用 `--probe` 试跑"（`.bat` 上判"跑不跑得起来"这类
    预检正是 #390 那两句误报的来源），故这里钉的是它能起得来、退出码原样传回、字节合规；
    解释器挑哪一个、挑不挑得到，由 `check_specs` 的静态判据与 PATH 裁剪过的反例来核。

    用例目录：
     * 1 `test_batch_runs_logic_code` — 整组齐全时跑起来、退出码 0
     * 2 `test_batch_returns_exit_code_unchanged` — 缺整组时经 `cmd /c … & pause` 仍原样传回 2
     * 3 `test_batch_is_pure_ascii_and_crlf` — 纯 ASCII + 整份 CRLF（cmd.exe 的两条硬要求）
    """

    def _bat(self):
        bat = self._shell("fetch-specs.bat")
        if os.name == "nt":
            return bat
        ok, why = _wine_selftest()
        if not ok:
            self.skipTest(why)
        return bat

    def _run_bat(self, bat, *args, env_extra=None):
        if os.name == "nt":
            proc = subprocess.run([bat, *args], capture_output=True, text=True,
                                  timeout=120, errors="replace",
                                  env=dict(os.environ, **(env_extra or {})))
            return proc.returncode, proc.stdout, proc.stderr
        return _wine(["cmd", "/c", _wine_dos_path(bat), *args], env_extra=env_extra)

    def test_batch_runs_logic_code(self):
        # 整组齐全、PATH 上有解释器时它得**真跑起来**：入口不再预检候选（#390 那两句误报正是
        # 预检判"跑不跑得起来"判出来的），跑得起来与否交给逻辑代码自己说话
        self._stage_group()
        bat = self._bat()
        code, out, err = self._run_bat(bat, "--probe")
        self.assertEqual(0, code, f"stdout={out!r}\nstderr={err!r}")
        self.assertIn("探针通过", out)

    def test_batch_returns_exit_code_unchanged(self):
        # 缺整组时逻辑代码给 2。这一条钉的正是 `cmd /c ""…" %* & pause"` 后面那句 `set`：
        # `&` 之后 `%errorlevel%` 是 pause 的，漏了 `set` 就永远传不回 2
        self._stage_group("script")
        bat = self._bat()
        code, out, err = self._run_bat(bat, "--probe")
        self.assertEqual(2, code, f"stdout={out!r}\nstderr={err!r}")
        self.assertIn("整组", err)

    def test_batch_is_pure_ascii_and_crlf(self):
        # `cmd.exe` 的两条硬要求（按系统 ANSI 代码页解析、按字节认行尾）：不必跑一遍才看得见，
        # 就地按字节核；与上面几条"真跑一遍"互为补集（跑起来时它们已经是乱码/执行失败了）
        with open(os.path.join(HERE, "fetch-specs.bat"), "rb") as fh:
            raw = fh.read()
        self.assertEqual([], [b for b in raw if b > 0x7F][:8],
                         "`.bat` 必须是纯 ASCII（cmd.exe 按系统 ANSI 代码页解析）")
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""), "`.bat` 必须整份 CRLF")

if __name__ == "__main__":
    unittest.main()
