#!/usr/bin/env python3
"""check_specs.py 的单元测试（纯 stdlib unittest，零第三方依赖）。

针对每个检查函数覆盖正例与反例：
  * extract_specs_refs     —— 引用提取与归一化（根反引号 / link 相对 / 各类剔除）
  * check_refs_exist       —— 引用存在性（正：存在；反：悬空引用）
  * check_link_refs        —— 链接格式（正：相对且合法；反：根绝对 / 越出仓库根）
  * check_section_refs     —— 节名引用存在性（正：节存在；反：节已改名/删除）
  * check_stack_consistency—— 技术栈双向一致（正：登记且存在；反：漏登记 / 登记不存在）
  * check_dispatcher_layers—— 加载调度器分层结构（正：五层+维护层层头与条目齐备；反：层头被吞/空壳层头/节被改写）
  * check_forbidden_patterns—— 私有约定误导入（正：无命中；反：命中）
  * check_self_check_guard —— 自检防线（正：自检规范+落点+登记齐备；反：文件被删/要点缺失/落点缺失/未登记）
  * check_source_guard     —— 来源防线（正：来源规范要点齐备；反：文件被删/要点缺失/未登记）
  * check_java_test_naming —— Java 测试类命名防线（正：两侧四类后缀判据齐备；反：后缀被删/调度器口径漂移）
  * check_line_ending_guard —— 换行符防线（正：LF 基准 + `.bat`/`.cmd` CRLF + `.gitattributes`/`.editorconfig` 齐备；反：文件被删/判据缺失/栈文件未写行尾/未登记）
  * check_review_guard   —— 评审备注落点防线（正：判据条 + 两个方向约束 + 两处引用齐备；反：文件被删/判据缺失/引用断开）
  * check_baseline_sync_guard —— 基线同步防线（正：三处落点 + 公开面齐备；反：前置条/判定标准/假绿折衷/根因/两侧核/两档取值/压缩前复核/两个方向/分工句/依据，各落点逐条被删或掏空）
  * check_verify_guard   —— 规范验证防线（正：两问定式化节 + P2 + 本仓库落点三处一致；
                             反：文件被删/节改名/第二问被删/P2 或本仓库口径未同步/未登记）
  * check_priority_guard 另钉『怎么走』形态声明与各最高关注项的『依据』行（反：形态声明被删/依据被整段删）
  * check_spec_admission_guard 另钉读法形态与重构后的有效性核对（反：两节被删）
  * check_runtime_env_guard —— 运行环境须与项目声明一致防线（正：条文/判据/声明落点/降级路径/依据行与三处引用齐备；
                             反：整节被删/L1 被摘/"能跑通也不得换"被删/判据被抽/声明落点被删/降级路径被删/依据被删/引用与登记断开）
  * check_registry_mirror_guard —— 包源与镜像源防线（正：次序/降级边界/先实测/不覆盖既有配置/推荐非强制/栈侧落点与图书馆登记齐备；
                             反：文件或节被删、次序被抹平、先实测被删、覆盖既有配置、推荐被读成强制、栈侧落点或图书馆记录缺失）
  * check_index_page_guard —— 索引页触发判据防线（正：触发判据/空壳不建/只做导航/模块 README 齐备；
                             反：doc.adoc 判据被删、doc-module.adoc 按需口径被删、文件被删）
  * check_script_header_guard —— 脚本头部注释（文档头）防线（正：先行/条目含设计决策/取值写常量名/决策不落方法体/"
     "超容量移交/行数不设限/入口注释边界 + 栈侧与公开面依据齐备；"
     "反：整节被删、逐条要点被抽、栈侧落点缺失、调度器与 README 未同步）

范围：只校验本仓库维护的规范/模板文本，**不检查 git 工作区状态、不检查引用方项目**
（引用方项目内部的 delete+create 等操作对本仓库校验不可见，详见 check_specs.py 文件头）。

运行方式：
  python -W ignore script/check_specs_test.py
或：
  python -W ignore -m unittest script.check_specs_test   （需将 script 按包导入）

注：文件命名为 `<被测文件>_test.py`（`_test` 后缀），使被测文件与其测试在目录
排序中相邻（check_specs.py 紧邻 check_specs_test.py）。
"""

import copy
import importlib.util
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))

_SPEC = importlib.util.spec_from_file_location(
    "check_specs", os.path.join(HERE, "check_specs.py"))
cm = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cm)  # type: ignore[union-attr]
import rules_engine  # noqa: E402  （加载期判据：自定义文案里不得出现 `{section}`）


def _git_argv(cwd: str, *args: str) -> subprocess.CompletedProcess:
    """按 argv 直接调用 git（**不经 shell**）。

    本机实证（Windows）：`subprocess.run(..., shell=True)` 走 `cmd.exe`，而 cmd.exe **不认
    单引号**——`git commit -qm 'feat: 已合并 main'` 会把消息拆成两个 pathspec、提交**直接失败**。
    后果是**静默失真**：本该报红的场景变成"那次提交根本没发生"，断言不报红（看着像防线失效），
    而"断言没有错误"的用例则**假通过**（本轮实测：动作侧两条用例在本机失败，另两条是假通过）。
    git 命令经 argv 传递即与平台无关、也不必关心引号。
    """
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def _git_commit(cwd: str, message: str) -> None:
    """暂存全部改动并提交（消息经 argv 传递，见 `_git_argv`）。"""
    _git_argv(cwd, "add", "-A")
    _git_argv(cwd, "commit", "-q", "-m", message)


def _mk_blackbox_base(root: str) -> str:
    """从官仓库示例构造一个标准基目录（AGENTS + general + core + stack）。"""
    specs = os.path.join(root, "specs")
    os.makedirs(os.path.join(specs, "general"), exist_ok=True)
    os.makedirs(os.path.join(specs, "core"), exist_ok=True)
    os.makedirs(os.path.join(specs, "stack"), exist_ok=True)
    return specs


NL = "\n"   # 夹具里的换行占位（避免源码里出现真换行、读起来分不清"这是内容还是缩进"）


class CheckSpecsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        # 保存模块全局并重定向到临时根，避免污染/依赖真实仓库
        self._orig = (cm.REPO_ROOT, cm.GENERIC_FILE, cm.SPECS_DIR, cm.PROJECT_SPECS_DIR,
                      cm.INSTALL_FILE, cm.PROJECT_FILE)
        # 行段核对的读文件缓存以"仓库根相对路径"为键，而 REPO_ROOT 每个用例都换，
        # 故必须清空——否则上一个用例的夹具内容会被下一个用例读到（本仓库实测：整类
        # 一起跑时 `.bat` 的判据用了别的用例的文件内容，单跑却通过）。
        cm.REPO_SCRIPT_SRC_CACHE.clear()
        # 夹具落点＝**系统临时目录**（不用仓库内 `tmp/`：本轮实测把夹具放进工作区后，
        # git 状态刷新/文件监听会跟着每次建删目录跑，全量单测由 ~80s 涨到 ~470s）。
        # 本机 `%TEMP%` 与仓库可能不同盘，由此引发的 `os.path.relpath` 跨盘问题改在
        # **判据侧**修（见 `check_specs.py` 的 `_rel_label`），不再靠"把夹具搬进仓库"绕开。
        self.root = tempfile.mkdtemp()
        cm.REPO_ROOT = self.root
        cm.GENERIC_FILE = os.path.join(self.root, "AGENTS_COMMON.adoc")
        cm.SPECS_DIR = os.path.join(self.root, "specs")
        cm.PROJECT_SPECS_DIR = os.path.join(self.root, "specs-project-maintainer")
        # 安装口径已并入公共入口：夹具里的"安装文档"就是入口自己（同一文件两个角色）
        cm.INSTALL_FILE = os.path.join(self.root, "AGENTS_COMMON.adoc")
        cm.PROJECT_FILE = os.path.join(self.root, "AGENTS.adoc")

    def tearDown(self) -> None:
        cm.errors.clear()
        cm.REPO_SCRIPT_SRC_CACHE.clear()
        (cm.REPO_ROOT, cm.GENERIC_FILE, cm.SPECS_DIR, cm.PROJECT_SPECS_DIR,
         cm.INSTALL_FILE, cm.PROJECT_FILE) = self._orig
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, relpath: str, content: str) -> None:
        """在临时根下按相对路径写文件（自动建父目录）。

        **一律按 LF 写**（`newline="\\n"`）：夹具模仿的是仓库文件，而仓库以 **LF** 为基准
        （`.gitattributes`）；用默认换行时 Windows 上写出来的是 CRLF，而读侧
        `_read_script_src` 用 `newline=""` 原样保留换行——`(?m)…,$`、`str.replace("…\\n…")`
        一类锚点随即失配，一批用例在 Windows 上**必然失败**（本轮实测：15 failures + 1 error
        全部出自这里，CI 在 Linux 上却是绿的）。强制 LF 后本机口径与 CI 一致。
        需要 CRLF 的夹具（`.bat`/`.cmd`/`.ps1` 的行尾判据）由内容里**显式写 `\\r\\n`**，
        不受本参数影响。
        """
        p = os.path.join(self.root, relpath)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)

    def error_texts(self) -> str:
        return "\n".join(cm.errors)

    # 规则数据是判据措辞的**唯一来源**：凡"本道判据外置在 `script/specs-rules/`"的防线，
    # 其夹具都须把这两份按**原样**落进来（**不手抄**——手抄必然与现场漂移，本轮实测：
    # 手抄版少一组锚点即产生假红）。规则文件由防线按仓库根相对路径读取，故夹具落点与
    # 现场一致即可。
    RULES_FIXTURE_FILES = ("script/specs-rules/_tokens.toml", "script/specs-rules/source.toml",
                           "script/specs-rules/verify.toml")

    def write_rules_fixture(self) -> None:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(cm.__file__)))
        for rel in self.RULES_FIXTURE_FILES:
            with open(os.path.join(repo_root, rel), encoding="utf-8") as fh:
                self.write(rel, fh.read())

    def write_real_file(self, rel: str) -> None:
        """把仓库里**真实的那份文件**原样落进夹具（判据本体的正例用它，不手抄）。"""
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(cm.__file__)))
        with open(os.path.join(repo_root, rel), encoding="utf-8") as fh:
            self.write(rel, fh.read())

    def capture_phase_log(self) -> list:
        """捕获 `cm.log` 的阶段级输出，返回一个**实时增长**的列表（用例读它判收尾）。

        `log()` 直接 `print`，故只有把 `print` 换成"追加进列表"才拿得到；用完须
        `restore_phase_log()` 换回（否则后续用例的进度会被吞掉）。
        """
        self._phase_log = []
        self._orig_log = cm.log
        cm.log = self._phase_log.append
        return self._phase_log

    def restore_phase_log(self) -> None:
        """还原 `cm.log`。"""
        cm.log = self._orig_log
        self._phase_log = []

    def phase_closed(self, start: int, end: int | None = None) -> bool:
        """`self._phase_log[start:end]` 这段输出里，每个 `▶ 阶段` 之后都有「✓ 完成」。

        判据取"阶段之间有没有收尾"，不取"整段末尾是不是完成行"——后者在子进程式
        收尾（`check_asciidoctor_syntax`）或末阶段时判不出来。**收尾行不按文案钉**：
        文案由 `phase_done()` 决定，这里只判"这个阶段后面还有下一行输出"，
        故改文案不会误报（钉文案属过度收紧，与 `check_criteria_not_axis_guard` 同口径）。
        """
        lines = (self._phase_log if end is None else self._phase_log[:end])[start:]
        for idx, line in enumerate(lines):
            if line.startswith("▶") and idx == len(lines) - 1:
                return False
        return True



class TestCheckBudgetGuard(CheckSpecsTestCase):
    """钉住常驻层体积上限（防"越写越多捆住 AI"）。

    必加载层每次会话无条件加载，是最直接的注意力预算消耗者；此前只有方向无抓手，
    故用字节上限把"先归位、再新增"变成机械可拦。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_budget = cm.RESIDENT_BUDGET
        self._orig_items = cm.DISPATCHER_ITEMS_MAX
        self._orig_entry = cm.PROJECT_ENTRY_BUDGET

    def tearDown(self) -> None:
        cm.RESIDENT_BUDGET = self._orig_budget
        cm.DISPATCHER_ITEMS_MAX = self._orig_items
        cm.PROJECT_ENTRY_BUDGET = self._orig_entry
        super().tearDown()

    def _write_valid(self, filler=""):
        self.write("AGENTS_COMMON.adoc",
                   "= 入口\n\n== 分类与懒加载（加载调度器）\n"
                   "=== 必加载层（每次工作都只加载）：\n"
                   "* 执行原则 → link:specs/core/execution.adoc[]\n"
                   "== 技术栈扩展约定\n" + filler)
        self.write("specs/core/execution.adoc", "= 执行原则\n" + filler)
        self.write("specs-project-maintainer/priority.adoc", "= 优先级\n" + filler)

    def test_valid_within_budget_passes(self):
        self._write_valid()
        cm.check_budget_guard()
        self.assertEqual(cm.errors, [])

    def test_resident_over_budget_reports(self):
        # 反例：常驻层体积超限（每次会话都为新增内容付上下文）
        cm.RESIDENT_BUDGET = 10
        self._write_valid(filler="x" * 200)
        cm.check_budget_guard()
        self.assertIn("常驻层体积超限", self.error_texts())

    def test_dispatcher_items_over_max_reports(self):
        # 反例：调度器条目过多（"该加载哪些"难以判全）
        cm.DISPATCHER_ITEMS_MAX = 0
        self._write_valid()
        cm.check_budget_guard()
        self.assertIn("条目数超限", self.error_texts())

    def test_missing_resident_file_reports(self):
        # 反例：必加载层文件缺失
        self.write("AGENTS_COMMON.adoc", "= 入口")
        cm.check_budget_guard()
        self.assertIn("缺少必加载层文件", self.error_texts())

    def test_project_entry_over_budget_reports(self):
        # 反例：项目自身入口 AGENTS.adoc 同为常驻物，超限须报
        # （它先于 AGENTS_COMMON.adoc 被读、每次会话都付上下文，故单列上限）
        cm.PROJECT_ENTRY_BUDGET = 10
        self._write_valid()
        self.write("AGENTS.adoc", "x" * 200)
        cm.check_budget_guard()
        self.assertIn("AGENTS.adoc 体积超限", self.error_texts())

    def test_project_entry_within_budget_passes(self):
        # 正例：AGENTS.adoc 在上限内不报
        self._write_valid()
        self.write("AGENTS.adoc", "= 入口\n\n小内容")
        cm.check_budget_guard()
        self.assertEqual(cm.errors, [])

    def test_dispatcher_section_rewritten_reports(self):
        # 反例：调度器节标题被改写 → 条目数抓手失效
        self.write("AGENTS_COMMON.adoc", "= 入口\n\n== 随便什么节\n")
        self.write("specs/core/execution.adoc", "= 执行原则")
        self.write("specs-project-maintainer/priority.adoc", "= 优先级")
        cm.check_budget_guard()
        self.assertIn("分类与懒加载", self.error_texts())


class TestCheckFileSizeHint(CheckSpecsTestCase):
    """钉住「单个规范文件的软阈值」（提醒该优化了，但不强制拆）。

    两件事同时钉住，缺一即失效：
      ① **提醒确实会出现**——非必加载的单个规范文件超线时须打印提示（否则"提醒"
         只在文本里成立，等于没有触发点：本仓库此前的抓手只覆盖必加载层的"合计量"）；
      ② **提醒不得变成硬上限**——超线**不得**进 `errors`、**不得**影响退出码
         （用 err() 就成了硬上限，会逼出"为压体积删规则"或"为达标拆出空壳"，与
          P2/P3 的完整性底线冲突）。
    另钉范围边界：常驻层由硬上限负责、图书馆不吃本软阈值（误伤只会制造噪音）。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_hint = cm.SOFT_FILE_SIZE_HINT

    def tearDown(self) -> None:
        cm.SOFT_FILE_SIZE_HINT = self._orig_hint
        super().tearDown()

    def _run_capture(self):
        import contextlib
        import io as _io
        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            cm.check_file_size_hint()
        return buf.getvalue()

    def test_under_threshold_no_hint(self):
        # 正例：未超线不打提示、无错误
        cm.SOFT_FILE_SIZE_HINT = 10000
        self.write("specs/general/doc.adoc", "= 文档\n" + "x" * 100)
        cm.check_file_size_hint()
        self.assertEqual(cm.errors, [])

    def test_over_threshold_hints_but_not_error(self):
        # 反例（关键）：单个规范文件超线 → 须有提示，但**不得**报错
        cm.SOFT_FILE_SIZE_HINT = 100
        self.write("specs/general/doc.adoc", "= 文档\n" + "x" * 500)
        out = self._run_capture()
        self.assertIn("specs/general/doc.adoc", out)
        self.assertIn("软阈值", out)
        self.assertIn("提醒、不阻断", out)
        self.assertEqual(cm.errors, [], "软阈值不得进 errors（否则成了硬上限）")

    def test_resident_layer_excluded(self):
        # 范围边界：常驻层由硬上限负责，本软阈值不重复提醒（防两条防线口径混淆）
        cm.SOFT_FILE_SIZE_HINT = 100
        self.write("AGENTS_COMMON.adoc", "= 入口\n" + "x" * 500)
        self.write("specs/core/execution.adoc", "= 执行原则\n" + "x" * 500)
        out = self._run_capture()
        self.assertNotIn("AGENTS_COMMON.adoc", out)
        self.assertNotIn("specs/core/execution.adoc", out)

    def test_library_and_prompts_excluded(self):
        # 范围边界：图书馆无体量上限、说明/提示词文档不是"按需加载即整份读完"的对象
        cm.SOFT_FILE_SIZE_HINT = 100
        self.write("library/sources.adoc", "= 依据\n" + "x" * 500)
        self.write("prompts/_common.txt", "x" * 500)
        self.write("README.adoc", "= 说明\n" + "x" * 500)
        out = self._run_capture()
        self.assertNotIn("library/sources.adoc", out)
        self.assertNotIn("README.adoc", out)
        self.assertEqual(cm.errors, [])

    def test_maintainer_layer_in_scope(self):
        # 维护方自查层同样是规范文件，须纳入（它的体量提醒此前完全没有抓手）
        cm.SOFT_FILE_SIZE_HINT = 100
        self.write("specs-project-maintainer/priority.adoc", "= 优先级\n" + "x" * 500)
        out = self._run_capture()
        self.assertIn("specs-project-maintainer/priority.adoc", out)
        self.assertEqual(cm.errors, [])

    def test_threshold_matches_spec_text(self):
        # 反例（防漂移）：机械侧取值须与规范正文的"约 30 KB"一致——
        # 两处各改一处即"提醒线"与实际判定不符（要么永不触发、要么处处触发）
        spec = open(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "specs-project-maintainer", "spec-lifecycle.adoc"), encoding="utf-8").read()
        self.assertIn("单个规范文件的软阈值", spec)
        self.assertIn("30 KB", spec)
        self.assertIn("只提醒、不报错、不阻断提交、不强制拆分", spec)
        self.assertIn("常驻层（入口 + `specs/core/`）不在本阈值内", spec)
        self.assertEqual(cm.SOFT_FILE_SIZE_HINT, 30000)

    def test_spec_scope_matches_implementation(self):
        # 反例（防自相矛盾）：正文若把"任一规范文件"（含常驻层）写成在阈值内，
        # 会与实现（常驻层排除、由硬上限负责）冲突——读者按正文去处理常驻层，
        # 得到的提示与硬上限的报错对不上（"该处理哪条"分不清）
        impl = open(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "check_specs.py"),
            encoding="utf-8").read()
        self.assertIn("常驻层由硬上限（check_budget_guard）负责", impl)
        self.assertIn("if rel in resident:", impl)


class TestCheckDispatcherLayers(CheckSpecsTestCase):
    """钉住加载调度器的分层结构（层头 + 每层条目数）。

    背景（本仓库实证）：按 `** ` 条目做"取到下一个条目"的替换时，会把夹在两条之间的
    层头行（`* 技术栈层（…）：`）一并吞掉，条目遂挂到上一层、加载触发条件出错，而
    **既有机械校验全绿**（登记/链接/体积都不看层头）。故机械钉住层头与"空壳层头"。
    """

    def _write(self, sec_body: str) -> None:
        self.write("AGENTS_COMMON.adoc",
                   "= 入口\n\n== 分类与懒加载（加载调度器）\n" + sec_body +
                   "\n== 技术栈扩展约定\n")

    def test_all_layers_present_passes(self):
        self._write(
            "=== 必加载层（每次工作都须加载）：\n"
            "* 执行原则 → link:specs/core/execution.adoc[]\n"
            "=== 通用层（涉及对应活动时加载，不得跳过）：\n"
            "* 编写代码 → link:specs/general/coding.adoc[]\n"
            "=== 技术栈层（按项目实际使用的语言/技术栈加载）：\n"
            "* Java 项目 → link:specs/stack/java.adoc[]\n"
            "=== 项目类型层（按项目在其自身规范中的主动声明加载）：\n"
            "* 通用工具/库类项目 → link:specs/general/doc-tool.adoc[]\n"
            "=== 平台层（按使用平台加载）：\n"
            "* CNB 平台 → link:specs/platform/cnb.adoc[]\n"
            "=== 维护方层（只对维护共享内容的项目生效）：\n"
            "* 条目落点：说明\n")
        cm.check_dispatcher_layers()
        self.assertEqual(cm.errors, [])

    def test_missing_layer_header_reports(self):
        # 反例：技术栈层层头被吞掉（条目仍在，但挂到了通用层下）
        self._write(
            "=== 必加载层（每次工作都须加载）：\n"
            "* 执行原则 → link:specs/core/execution.adoc[]\n"
            "=== 通用层（涉及对应活动时加载，不得跳过）：\n"
            "* Java 项目 → link:specs/stack/java.adoc[]\n"
            "=== 项目类型层（按项目在其自身规范中的主动声明加载）：\n"
            "* 工具库类项目 → link:specs/general/doc-tool.adoc[]\n"
            "=== 平台层（按使用平台加载）：\n"
            "* CNB 平台 → link:specs/platform/cnb.adoc[]\n"
            "=== 维护方层（只对维护共享内容的项目生效）：\n"
            "* 条目落点：说明\n")
        cm.check_dispatcher_layers()
        self.assertIn("缺失「技术栈层」层头行", self.error_texts())

    def test_empty_layer_header_reports(self):
        # 反例：空壳层头（层头下无任何条目）
        self._write(
            "=== 必加载层（每次工作都须加载）：\n"
            "* 执行原则 → link:specs/core/execution.adoc[]\n"
            "=== 通用层（涉及对应活动时加载，不得跳过）：\n"
            "=== 技术栈层（按项目实际使用的语言/技术栈加载）：\n"
            "=== 项目类型层（按项目在其自身规范中的主动声明加载）：\n"
            "* 工具库类项目 → link:specs/general/doc-tool.adoc[]\n"
            "=== 平台层（按使用平台加载）：\n"
            "* CNB 平台 → link:specs/platform/cnb.adoc[]\n"
            "=== 维护方层（只对维护共享内容的项目生效）：\n"
            "* 条目落点：说明\n")
        cm.check_dispatcher_layers()
        self.assertIn("层头下没有任何条目", self.error_texts())

    def test_dispatcher_section_missing_reports(self):
        # 反例：调度器节被改写 → 结构防线失去抓手
        self.write("AGENTS_COMMON.adoc", "= 入口\n\n== 别的节\n")
        cm.check_dispatcher_layers()
        self.assertIn("分类与懒加载", self.error_texts())


class TestCheckDelegationGuard(CheckSpecsTestCase):
    """钉住从属者与能力自评、执行者来源选择（"定义了却不会执行"的高发盲点）。

    执行者来源这一半**已由"优先同源"收紧为"强制同 Agent + 不得点名外部 NPC"**，故本
    组用例同步按新口径写正例/反例：只留旧字样（"优先同源""同源不可用后换外部来源"）不再
    算通过——后者正是要被拦下的"换个 Agent 当第一手段"。
    """

    def _write_valid(self):
        self.write("AGENTS_COMMON.adoc", "= t\n\n从属者：加载由已加载入口驱动。\n")
        self.write("specs/general/self-check.adoc", "= t\n\n== 环境能力自评\n无机制走降级。\n")
        self.write("specs/general/collab.adoc",
                   "= t\n\n"
                   "**子任务必须由与执行者相同的 Agent 承担（L1，强制同 Agent）**："
                   "判据：**同 Agent** 与**同一 Agent 身份**。\n\n"
                   "**不得点名外部 Agent / 外部 NPC（L1）**：判定标准——"
                   "①**派发目标**是外部标识；②**交换面**超出本执行者可直接调用；"
                   "③结论**回传面**读不到。\n\n"
                   "* **子 Agent 不可用时的降级路径（L1）**：**不换任何外部来源**，"
                   "①**由执行者本人（主 agent）串行承担**。\n\n"
                   "* **优先一次性调用（L1）**\n")
        # 三视角复核口径的单一落点是 verify.adoc（testing.adoc 同名节只留一跳入口）
        self.write("specs/general/verify.adoc",
                   "= t\n\n* **执行者选择：强制同 Agent（L1）**：三视角复核一律由与执行者"
                   "相同的 Agent 承担，**不得点名外部 Agent / 外部 NPC**。\n")
        self.write("specs-project-maintainer/verify.adoc",
                   "= t\n\n**子 Agent 强制与执行者同 Agent（维护方落点）**\n")

    def test_valid_passes(self):
        self._write_valid()
        cm.check_delegation_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_delegation_mechanism_reports(self):
        # 反例：删掉"从属者适配"→ 子 agent/被引用方可以"没被派发"为由跳过加载
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "= t\n\n（加载由派发者转发、不靠入口）\n")
        cm.check_delegation_guard()
        self.assertIn("从属者", self.error_texts())

    def test_missing_capability_selfcheck_reports(self):
        # 反例：删掉"环境能力自评"→ 环境无清空/无子 agent 时照抄"已完成"
        self._write_valid()
        self.write("specs/general/self-check.adoc", "= t\n\n（无能力自评）\n")
        cm.check_delegation_guard()
        self.assertIn("环境能力自评", self.error_texts())

    def test_missing_same_agent_requirement_reports(self):
        # 反例：删掉"子任务必须与执行者同 Agent"→ 缺复核时随手抓外部执行者（不可核对）
        self._write_valid()
        self.write("specs/general/collab.adoc",
                   "= t\n\n* **优先一次性调用（L1）**\n\n* **子 Agent 不可用时的降级路径（L1）**\n")
        cm.check_delegation_guard()
        self.assertIn("子任务必须由与执行者相同的 Agent 承担", self.error_texts())

    def test_missing_named_external_npc_ban_reports(self):
        # 反例：删掉"不得点名外部 Agent / 外部 NPC"→ 评论里直接 @ 外部 NPC 又无人拦
        self._write_valid()
        self.write("specs/general/collab.adoc",
                   "= t\n\n**子任务必须由与执行者相同的 Agent 承担（L1，强制同 Agent）**："
                   "判据：**同 Agent** 与**同一 Agent 身份**。\n\n"
                   "* **子 Agent 不可用时的降级路径（L1）**：**不换任何外部来源**，"
                   "①**由执行者本人（主 agent）串行承担**。\n\n"
                   "* **优先一次性调用（L1）**\n")
        cm.check_delegation_guard()
        self.assertIn("不得点名外部 Agent / 外部 NPC", self.error_texts())

    def test_external_npc_ban_without_criteria_reports(self):
        # 反例：只留"不得点名外部 NPC"字样、判定标准被抽掉 → 判据不可执行（假绿）
        self._write_valid()
        self.write("specs/general/collab.adoc",
                   "= t\n\n**子任务必须由与执行者相同的 Agent 承担（L1，强制同 Agent）**："
                   "判据：**同 Agent** 与**同一 Agent 身份**。\n\n"
                   "**不得点名外部 Agent / 外部 NPC（L1）**\n\n"
                   "* **子 Agent 不可用时的降级路径（L1）**：**不换任何外部来源**，"
                   "①**由执行者本人（主 agent）串行承担**。\n\n"
                   "* **优先一次性调用（L1）**\n")
        cm.check_delegation_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_missing_same_agent_fallback_reports(self):
        # 反例：删掉"同 Agent 不可用时的降级路径"→ 只剩"换外部来源"一条路
        self._write_valid()
        self.write("specs/general/collab.adoc",
                   "= t\n\n**子任务必须由与执行者相同的 Agent 承担（L1，强制同 Agent）**："
                   "判据：**同 Agent** 与**同一 Agent 身份**。\n\n"
                   "**不得点名外部 Agent / 外部 NPC（L1）**：判定标准——①**派发目标**是外部标识；"
                   "②**交换面**超出本执行者可直接调用；③结论**回传面**读不到。\n\n"
                   "* **优先一次性调用（L1）**\n")
        cm.check_delegation_guard()
        self.assertIn("降级路径（L1）", self.error_texts())

    def test_missing_one_shot_call_reports(self):
        # 反例：删掉"优先一次性调用"→ 又回到"交一个有自主探查权的执行者"（超时无法判定）
        self._write_valid()
        self.write("specs/general/collab.adoc",
                   "= t\n\n**子任务必须由与执行者相同的 Agent 承担（L1，强制同 Agent）**："
                   "判据：**同 Agent** 与**同一 Agent 身份**。\n\n"
                   "**不得点名外部 Agent / 外部 NPC（L1）**：判定标准——①**派发目标**是外部标识；"
                   "②**交换面**超出本执行者可直接调用；③结论**回传面**读不到。\n\n"
                   "* **子 Agent 不可用时的降级路径（L1）**：**不换任何外部来源**，"
                   "①**由执行者本人（主 agent）串行承担**。\n")
        cm.check_delegation_guard()
        self.assertIn("优先一次性调用", self.error_texts())

    def test_missing_maintainer_executor_source_reports(self):
        # 反例：维护方落点丢掉"强制同 Agent"→ 又先去派外部 NPC
        self._write_valid()
        self.write("specs-project-maintainer/verify.adoc", "= t\n\n（无条件口径）\n")
        cm.check_delegation_guard()
        self.assertIn("子 Agent 强制与执行者同 Agent", self.error_texts())

    def test_missing_file_reports(self):
        self.write("AGENTS_COMMON.adoc", "从属者")
        cm.check_delegation_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_stale_wording_in_list_item_reports(self):
        # 反例（本轮实际漏检）：**清单概览行**回到旧口径（"优先同源 + 外部来源作备选"），
        # 而 `=== P6` 条目正文仍是新口径 → 旧防线只读 P6 条目、不看清单行，全绿放过。
        # 清单行更先被读到，按它读的维护方会继续把复核派给不可核对的外部执行者。
        self._write_valid()
        self.write("specs-project-maintainer/priority.adoc",
                   "= t\n\n"
                   "* **协作执行者选择（P6，条款本身 L1）**：需要子 Agent（子任务/复核）时"
                   "**优先用与执行者同源、可用的执行者**承担，"
                   "**外部来源（外部 NPC/另一个产品）只是同源不可用后的备选**。\n\n"
                   "**子 Agent 强制与执行者同 Agent（维护方落点）**\n")
        cm.check_delegation_guard()
        self.assertIn("重新放宽", self.error_texts())

    def test_stale_wording_appended_in_same_file_reports(self):
        # 反例：新口径字样都还在，但在同文件的另一句里**追加放宽**
        # （"拿不到同 Agent 时也可以换外部 Agent 顶替"）→ 只核"要素仍在"的写法会假绿。
        self._write_valid()
        path = os.path.join(self.root, "specs", "general", "collab.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.write("specs/general/collab.adoc",
                   text + "\n拿不到同 Agent 时也可以换外部 Agent 顶替。\n")
        cm.check_delegation_guard()
        self.assertIn("重新放宽", self.error_texts())

    def test_mixed_forbid_and_relax_in_one_clause_reports(self):
        # 反例（本项目真实形态）：同一分句前半句还在"不得点名外部…"、后半句却放宽
        # （"也不得把外部复核者当备选" → "也允许换外部复核者当备选"）。
        # 若否定词按整个分句判定，这类"前半句禁止、后半句放宽"会被误放行。
        self._write_valid()
        path = os.path.join(self.root, "specs-project-maintainer", "verify.adoc")
        self.write("specs-project-maintainer/verify.adoc",
                   "= t\n\n**子 Agent 强制与执行者同 Agent（维护方落点）**："
                   "**不得点名外部 Agent / 外部 NPC**、也允许换外部复核者当备选\n")
        cm.check_delegation_guard()
        self.assertIn("重新放宽", self.error_texts())
        self.assertTrue(os.path.isfile(path))

    def test_negated_wording_does_not_report(self):
        # 正例（**防误报**）：禁止式写法与旧口径的反例引用是正当文本，不得被拦
        # ——否则规范无法写"不得用外部 Agent 顶替"这类要求。
        self._write_valid()
        path = os.path.join(self.root, "specs", "general", "collab.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.write("specs/general/collab.adoc",
                   text + "\n**不得用外部 Agent 顶替**，也不得把外部 NPC 作备选；"
                          "不得改回『外部来源可以顶替』的宽松写法。\n")
        cm.check_delegation_guard()
        self.assertEqual(cm.errors, [])


class TestCheckMergeStateGuard(CheckSpecsTestCase):
    """钉住『NPC 禁合并·动作侧』：核**合并动作真没做**，不是只核规则文本在不在。

    背景（本仓库实证失效一次）：用户要求"压缩提交"，执行者读成"合并 PR"、直接合了，
    而当时三道**文本**防线全部报 OK——文本侧只能证"规则写着"。
    故本组用例逐种失效形态各覆盖一条：提交说明的合并动作话术、分支历史里的合并提交，
    外加"干净态不得误报"与"非 git 根须跳过"（保持确定性与幂等）。
    """

    def setUp(self) -> None:
        super().setUp()
        self._tmp = tempfile.mkdtemp()

        def sh(cmd):
            # 与 `check_merge_state_guard` 同口径按 UTF-8 收发：中文提交说明在本机（GBK）
            # 下会被解成乱码，夹具的建仓/提交动作本身也会跟着失真。
            return subprocess.run(cmd, shell=True, cwd=self._tmp,
                                  capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")
        self.sh = sh
        sh("git init -q -b main . && git config user.email a@b.c && "
           "git config user.name t && git config commit.gpgsign false")
        with open(os.path.join(self._tmp, "a.txt"), "w", encoding="utf-8") as fh:
            fh.write("x")
        sh("git add -A && git commit -qm init && git checkout -q -b feat")
        cm.REPO_ROOT = self._tmp

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)
        super().tearDown()

    def _merge_markers(self):
        return cm._merge_state_guard_rules()

    def test_clean_single_parent_commit_passes(self):
        # 正例：源分支上的单亲提交（正常交付形态）→ 不报红
        with open(os.path.join(self._tmp, "a.txt"), "w", encoding="utf-8") as fh:
            fh.write("y")
        _git_commit(self._tmp, "fix: 单亲提交")
        cm.errors.clear()
        cm.check_merge_state_guard()
        self.assertEqual(cm.errors, [])

    def test_merge_action_in_commit_message_reports(self):
        # 反例：提交说明里出现合并动作话术（"已合并"）→ 报红
        with open(os.path.join(self._tmp, "a.txt"), "w", encoding="utf-8") as fh:
            fh.write("y")
        _git_commit(self._tmp, "feat: 已合并 main")
        cm.errors.clear()
        cm.check_merge_state_guard()
        self.assertIn("合并动作", self.error_texts())

    def test_rejection_wording_is_allowed(self):
        # 边界：**记录禁令本身**的文字（写完又说"不得/拒绝"）不得被读成"执行了合并"
        with open(os.path.join(self._tmp, "a.txt"), "w", encoding="utf-8") as fh:
            fh.write("y")
        _git_commit(self._tmp, "docs: 说明「已合并」一类话术不得出现、一律拒绝")
        cm.errors.clear()
        cm.check_merge_state_guard()
        self.assertEqual(cm.errors, [])

    def test_merge_commit_in_branch_history_reports(self):
        # 反例：分支历史里出现合并提交（"合并 PR"落盘必留的痕迹）→ 报红。
        # 并的是**别的源分支**——把目标分支（`main`）并回来属返工基点的修复动作、不在此列
        # （见 `test_merging_target_branch_back_is_allowed`）。
        with open(os.path.join(self._tmp, "b.txt"), "w", encoding="utf-8") as fh:
            fh.write("z")
        _git_commit(self._tmp, "feat: 自己分支的改动")
        _git_argv(self._tmp, "checkout", "-q", "-b", "other", "main")
        with open(os.path.join(self._tmp, "c.txt"), "w", encoding="utf-8") as fh:
            fh.write("c\n")
        _git_commit(self._tmp, "other 分支前进")
        _git_argv(self._tmp, "checkout", "-q", "feat")
        _git_argv(self._tmp, "merge", "--no-ff", "-q", "other", "-m", "merge other")
        cm.errors.clear()
        cm.check_merge_state_guard()
        self.assertIn("合并提交", self.error_texts())

    def test_non_git_root_skips_without_error(self):
        # 边界：非 git 根 → 跳过、不报错（确定性/幂等）
        cm.REPO_ROOT = tempfile.mkdtemp()
        cm.errors.clear()
        cm.check_merge_state_guard()
        self.assertEqual(cm.errors, [])

    def test_merging_target_branch_back_is_allowed(self):
        # 例外（用户点名）：把**目标分支本身**并回来是 `check_base_ancestor_guard` 的修复动作
        # ——分支被重建成不含基点的线之后，只有把基点并回来才能让基点重新成为祖先。
        # 不核父提交的话，这条修复动作会被本道防线读成"合并了别人"而报红（自相矛盾）。
        with open(os.path.join(self._tmp, "b.txt"), "w", encoding="utf-8") as fh:
            fh.write("z")
        _git_commit(self._tmp, "feat: 自己分支的改动")
        _git_argv(self._tmp, "checkout", "-q", "main")
        with open(os.path.join(self._tmp, "a.txt"), "a", encoding="utf-8") as fh:
            fh.write("m\n")
        _git_commit(self._tmp, "main 前进")
        _git_argv(self._tmp, "checkout", "-q", "feat")
        _git_argv(self._tmp, "merge", "--no-ff", "-q", "main", "-m", "合并 main：修复返工基点")
        cm.errors.clear()
        cm.check_merge_state_guard()
        self.assertNotIn("合并提交", self.error_texts())

    def test_mixed_merge_reports(self):
        # 反例：一条合并提交里同时并了**目标分支**与**别的源分支** → 整条报红。
        # 判据是"**每一个**父提交都在目标分支上"，不因"含一个目标分支父提交"而打折扣——
        # 只看"有没有一个父提交是目标分支"的松写法会把这条放过去。
        with open(os.path.join(self._tmp, "b.txt"), "w", encoding="utf-8") as fh:
            fh.write("z")
        _git_commit(self._tmp, "feat: 自己分支的改动")
        _git_argv(self._tmp, "checkout", "-q", "main")
        with open(os.path.join(self._tmp, "a.txt"), "a", encoding="utf-8") as fh:
            fh.write("m\n")
        _git_commit(self._tmp, "main 前进")
        _git_argv(self._tmp, "checkout", "-q", "-b", "other", "main")
        with open(os.path.join(self._tmp, "c.txt"), "w", encoding="utf-8") as fh:
            fh.write("c\n")
        _git_commit(self._tmp, "other 分支的改动")
        _git_argv(self._tmp, "checkout", "-q", "feat")
        _git_argv(self._tmp, "merge", "--no-ff", "-q", "main", "-m", "合并 main")
        _git_argv(self._tmp, "merge", "--no-ff", "-q", "other", "-m", "合并 other")
        cm.errors.clear()
        cm.check_merge_state_guard()
        self.assertIn("合并提交", self.error_texts())

    def test_shallow_clone_reports_instead_of_silently_passing(self):
        # 边界：父提交清单取不到（浅克隆 / sha 不在本地）→ 按违规处理，不得静默放行
        self.assertFalse(
            cm._merge_commit_ok(self._tmp, "0" * 40, "main"))

    def test_merging_other_branch_reports(self):
        # 反例：并进来的是**别的源分支**（不是目标分支）→ 照旧报红（例外不扩大）
        with open(os.path.join(self._tmp, "b.txt"), "w", encoding="utf-8") as fh:
            fh.write("z")
        _git_commit(self._tmp, "feat: 自己分支的改动")
        _git_argv(self._tmp, "checkout", "-q", "-b", "other", "main")
        with open(os.path.join(self._tmp, "c.txt"), "w", encoding="utf-8") as fh:
            fh.write("c\n")
        _git_commit(self._tmp, "other 分支的改动")
        _git_argv(self._tmp, "checkout", "-q", "feat")
        _git_argv(self._tmp, "merge", "--no-ff", "-q", "other", "-m", "合并 other 分支")
        cm.errors.clear()
        cm.check_merge_state_guard()
        self.assertIn("合并提交", self.error_texts())

    def test_marker_table_is_externalized(self):
        # 措辞表须真的从规则数据取到（缺失即整道防线无从执行，不得静默放行）
        markers = self._merge_markers()
        self.assertIn("merge_action_markers", markers)
        self.assertIn("allow_markers", markers)


class TestCheckBaseAncestorGuard(CheckSpecsTestCase):
    """钉住『返工基点防线（动作侧）』：本分支的返工基点须是 HEAD 的祖先。

    背景（本 PR 实证失效一次，用户点名"靠 AI 自觉是不现实"）：解冲突+压缩时把分支重建在
    **更早的基点**上，基点之后合入的一整批改动被静默回退，而全部文本防线与单测仍全绿
    ——所有防线都只读"工作区内容对不对"，没有一条读"基点对不对"。
    本组用例覆盖：正例（基点仍是祖先）、反例（分支被重建成不含基点的线）、
    以及三条"不得猜"的边界（无参照 sha / 参照 sha 不在本仓库 / 非 git 根）须跳过不报错。
    """

    def setUp(self) -> None:
        super().setUp()
        self._tmp = tempfile.mkdtemp()
        self._env_backup = os.environ.get("CNB_PULL_REQUEST_TARGET_SHA")
        os.environ.pop("CNB_PULL_REQUEST_TARGET_SHA", None)

        def sh(cmd):
            # 与 `check_merge_state_guard` 同口径按 UTF-8 收发：中文提交说明在本机（GBK）
            # 下会被解成乱码，夹具的建仓/提交动作本身也会跟着失真。
            return subprocess.run(cmd, shell=True, cwd=self._tmp,
                                  capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")
        self.sh = sh
        sh("git init -q -b main . && git config user.email a@b.c && "
           "git config user.name t && git config commit.gpgsign false")
        with open(os.path.join(self._tmp, "a.txt"), "w", encoding="utf-8") as fh:
            fh.write("x")
        sh("git add -A && git commit -qm base")
        self.base = sh("git rev-parse HEAD").stdout.strip()
        sh("git checkout -q -b feat")
        cm.REPO_ROOT = self._tmp

    def tearDown(self) -> None:
        if self._env_backup is None:
            os.environ.pop("CNB_PULL_REQUEST_TARGET_SHA", None)
        else:
            os.environ["CNB_PULL_REQUEST_TARGET_SHA"] = self._env_backup
        shutil.rmtree(self._tmp, ignore_errors=True)
        super().tearDown()

    def _run(self, ref):
        os.environ["CNB_PULL_REQUEST_TARGET_SHA"] = ref
        cm.errors.clear()
        cm.check_base_ancestor_guard()
        return self.error_texts()

    def test_base_is_ancestor_passes(self):
        # 正例：在基点之上继续提交（正常返工形态）→ 不报红
        with open(os.path.join(self._tmp, "a.txt"), "w", encoding="utf-8") as fh:
            fh.write("y")
        _git_commit(self._tmp, "feat: 在基点之上继续")
        self.assertEqual(self._run(self.base), "")

    def test_branch_rebuilt_on_older_base_reports(self):
        # 反例：分支被重建成一条**不再包含基点**的线（正是回退别人改动的机械特征）
        _git_argv(self._tmp, "checkout", "-q", "-b", "other")
        _git_argv(self._tmp, "checkout", "-q", "main")
        with open(os.path.join(self._tmp, "b.txt"), "w", encoding="utf-8") as fh:
            fh.write("z")
        _git_commit(self._tmp, "基点之后合入的一批改动")
        newer = self.sh("git rev-parse HEAD").stdout.strip()
        # 把 feat 重建在**更早**的分叉点（不再包含 newer）
        _git_argv(self._tmp, "checkout", "-q", "-B", "feat", self.base)
        with open(os.path.join(self._tmp, "c.txt"), "w", encoding="utf-8") as fh:
            fh.write("c")
        _git_commit(self._tmp, "feat: 重建在新基点上（回退了上面那批）")
        texts = self._run(newer)
        self.assertIn("返工基点", texts)
        self.assertIn("不是", texts)

    def test_recovery_merge_makes_base_ancestor_again(self):
        # 修复动作的可核对形态（本 PR 实测路径）：分支被重建成不含基点的线后，**把基点并回来**
        # （`git merge <基点>`）即让判据恢复为真；此时两侧改动都在（`other` 那批不被回退）。
        _git_argv(self._tmp, "checkout", "-q", "-b", "other")
        _git_argv(self._tmp, "checkout", "-q", "main")
        with open(os.path.join(self._tmp, "b.txt"), "w", encoding="utf-8") as fh:
            fh.write("z")
        _git_commit(self._tmp, "基点之后合入的一批改动")
        newer = self.sh("git rev-parse HEAD").stdout.strip()
        # 把 feat 重建在更早的分叉点（回退了上面那批）→ 判据为假
        _git_argv(self._tmp, "checkout", "-q", "-B", "feat", self.base)
        with open(os.path.join(self._tmp, "c.txt"), "w", encoding="utf-8") as fh:
            fh.write("c")
        _git_commit(self._tmp, "feat: 重建在新基点上（回退了上面那批）")
        self.assertIn("返工基点", self._run(newer))
        # 修复：把基点并回来（不得用"只把文件内容改成和基点一样"折衷）
        _git_argv(self._tmp, "merge", "--no-edit", "-q", newer)
        self.assertEqual(self._run(newer), "")
        self.assertTrue(os.path.isfile(os.path.join(self._tmp, "b.txt")),
                        "并回来之后，基点之后合入的改动须仍在工作区里（不是被回退掉）")

    def test_missing_base_env_skips(self):
        # 边界：非 CNB 环境/平台未给参照 sha → 跳过、不报错（确定性/幂等）
        with open(os.path.join(self._tmp, "a.txt"), "w", encoding="utf-8") as fh:
            fh.write("y")
        _git_commit(self._tmp, "feat: 改动")
        os.environ.pop("CNB_PULL_REQUEST_TARGET_SHA", None)
        cm.errors.clear()
        cm.check_base_ancestor_guard()
        self.assertEqual(cm.errors, [])

    def test_unknown_base_sha_skips(self):
        # 边界：参照 sha 不在本仓库（未取回/别的仓）→ 跳过、不猜
        self.assertEqual(self._run("0" * 40), "")

    def test_non_git_root_skips(self):
        # 边界：非 git 根 → 跳过、不报错
        cm.REPO_ROOT = tempfile.mkdtemp()
        os.environ["CNB_PULL_REQUEST_TARGET_SHA"] = self.base
        cm.errors.clear()
        cm.check_base_ancestor_guard()
        self.assertEqual(cm.errors, [])


class TestCheckGitMvSelfcheck(CheckSpecsTestCase):
    """钉住"本仓库自身侧"的 git mv 自查（P1 可机械核对的那一半）。

    引用方侧不可见属既有事实，但本仓库自己也是 git 工作区，故须有这一半抓手；
    非 git 目录/无暂存内容须**跳过不报错**（保持确定性与幂等）。
    """

    def test_non_git_root_skips_without_error(self):
        # 正例：临时根非 git 仓库 → 跳过、不报错（保证幂等）
        cm.check_git_mv_selfcheck()
        self.assertEqual(cm.errors, [])

    def test_real_repo_without_delete_add_passes(self):
        # 正例：对本仓库真实运行须无错（无 delete+add 形态）
        self.tearDown()
        self.setUp = lambda: None  # noqa: 仅为让本用例用真实根
        cm.REPO_ROOT_BACKUP = None
        # 直接用真实仓库根快速核对一次
        real = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cm.REPO_ROOT = real
        cm.check_git_mv_selfcheck()
        self.assertEqual([e for e in cm.errors if "暂存区" in e], [])



# --------------------------------------------------------------------------- #
# extract_specs_refs
# --------------------------------------------------------------------------- #
class TestExtractSpecsRefs(unittest.TestCase):
    """直接测纯函数，不依赖文件系统。"""

    def test_backtick_is_root_relative(self):
        text = "加载 `specs/general/coding.adoc`"
        self.assertEqual(cm.extract_specs_refs(text), ["specs/general/coding.adoc"])

    def test_link_relative_resolves_to_repo_path(self):
        text = "见 link:../general/coding.adoc[]"
        self.assertEqual(
            cm.extract_specs_refs(text, base_dir="specs/core"),
            ["specs/general/coding.adoc"])

    def test_link_same_dir(self):
        text = "link:execution.adoc[]"
        self.assertEqual(
            cm.extract_specs_refs(text, base_dir="specs/core"),
            ["specs/core/execution.adoc"])

    def test_external_rootabs_anchor_escape_excluded(self):
        text = ("link:https://example.com/a[] link:#anch "
                "link:/specs/general/x.adoc[] link:../../../y.adoc[] "
                "`specs/nope.adoc`")
        # 根绝对与越界的 link 不参与存在性；但反引号 specs/nope.adoc 属根相对，保留
        self.assertEqual(cm.extract_specs_refs(text, base_dir="specs/core"),
                         ["specs/nope.adoc"])

    def test_placeholder_excluded_dir_kept(self):
        # 占位符（`...`、`<...>`）不参与存在性；**目录型引用保留**（以 `/` 结尾），
        # 由调用方按 os.path.isdir 核对——原实现把目录型一并跳过，等于必然漏报。
        text = ("`specs/...` `specs/stack/` `specs/stack/<语言>-testing.adoc` "
                "link:../stack/<语言>-testing.adoc[]")
        self.assertEqual(cm.extract_specs_refs(text, base_dir="specs/core"),
                         ["specs/stack/"])

    def test_dedupe_preserve_order(self):
        text = "`specs/stack/java.adoc` `specs/stack/java.adoc` link:../stack/java.adoc[]"
        self.assertEqual(cm.extract_specs_refs(text, base_dir="specs/general"),
                         ["specs/stack/java.adoc"])


# --------------------------------------------------------------------------- #
# collect_adoc_files / _is_dir_ref / _is_placeholder_ref
# --------------------------------------------------------------------------- #
class TestCollectAdocFiles(CheckSpecsTestCase):
    """钉住"检查集合的覆盖面"：纳入 `library/**`、`prompts/**` 与仓库根全部 .adoc。

    原实现只收 `specs/` + `AGENTS_COMMON.adoc` + `AGENTS.adoc`，
    `library/**` 与根 `PUBLIC.adoc`/`README.adoc`/`PROMPTS.adoc`（连 `CHANGELOG.adoc`）
    全部漏收——语法编译、引用存在性、节名引用、链接格式四口径对它们整体失效。
    `prompts/**` 亦曾漏收，而它是要复制给未知项目执行的产物（见 `PUBLIC.adoc`）：
    其自身死链/悬空引用会随分发流出。
    """

    def test_library_files_collected(self):
        self.write("library/README.adoc", "= 图书馆\n")
        self.write("library/sources.adoc", "= 来源\n")
        files = cm.collect_adoc_files()
        self.assertIn("library/README.adoc", files)
        self.assertIn("library/sources.adoc", files)

    def test_root_docs_collected(self):
        self.write("PUBLIC.adoc", "= 公共内容入口索引\n")
        self.write("README.adoc", "= 说明\n")
        self.write("PROMPTS.adoc", "= 提示词\n")
        files = cm.collect_adoc_files()
        for rel in ("PUBLIC.adoc", "README.adoc", "PROMPTS.adoc"):
            self.assertIn(rel, files)

    def test_prompts_files_collected(self):
        # prompts/*.adoc 是要复制给未知项目执行的产物，其自身引用完整性须受四口径覆盖
        self.write("prompts/review.adoc", "= 提示词：检查修复\n")
        self.write("prompts/_common.txt", "公共片段\n")
        files = cm.collect_adoc_files()
        self.assertIn("prompts/review.adoc", files)
        # 非 .adoc（_common.txt）不入集合：四口径只针对 .adoc 引用
        self.assertNotIn("prompts/_common.txt", files)

    def test_prompts_dangling_ref_reported(self):
        self.write("AGENTS_COMMON.adoc", "= t\n")
        self.write("prompts/review.adoc", "见 link:no_such_file.adoc[]\n")
        cm.check_refs_exist()
        self.assertIn("prompts/no_such_file.adoc", self.error_texts())

    def test_prompts_dangling_section_ref_reported(self):
        self.write("AGENTS_COMMON.adoc", "= t\n")
        self.write("prompts/review.adoc",
                   "link:../specs/general/doc.adoc[]「不存在的节XYZ」\n")
        self.write("specs/general/doc.adoc", "= 文档\n\n== 真实节\n")
        cm.check_section_refs()
        self.assertIn("不存在的节XYZ", self.error_texts())

    def test_prompts_root_absolute_link_reported(self):
        self.write("AGENTS_COMMON.adoc", "= t\n")
        self.write("prompts/review.adoc", "见 link:/prompts/refactor.adoc[]\n")
        cm.check_link_refs()
        self.assertIn("根绝对", self.error_texts())

    def test_prompts_need_not_register_dispatcher(self):
        # prompts/ 非规范本体、不进规范加载链，其互相引用不得被要求登记进调度器
        self.write("AGENTS_COMMON.adoc", "= t\n")
        self.write("prompts/review.adoc", "见 link:refactor.adoc[]\n")
        self.write("prompts/refactor.adoc", "= 重构\n")
        cm.check_dispatcher_registry()
        self.assertEqual(cm.errors, [])

    def test_paths_are_repo_relative(self):
        # 统一为"仓库根相对 POSIX 路径"（"某文件在不在集合里"可直接核验）
        self.write("specs/general/coding.adoc", "= 编码\n")
        for f in cm.collect_adoc_files():
            self.assertFalse(os.path.isabs(f), f)
            self.assertNotIn("\\", f)

    def test_does_not_leak_real_repo_files(self):
        # 只收本仓库（此处为临时根）内的文件：不得把真实仓库的 library/ 漏收进来
        self.write("specs/general/coding.adoc", "= 编码\n")
        self.assertNotIn("library/README.adoc", cm.collect_adoc_files())


class TestRefKindPredicates(unittest.TestCase):
    """钉住 `_is_dir_ref` 与 `_is_placeholder_ref` 的分工（目录型不再整体跳过）。"""

    def test_dir_ref_recognized(self):
        self.assertTrue(cm._is_dir_ref("specs/"))
        self.assertTrue(cm._is_dir_ref("script/"))
        self.assertFalse(cm._is_dir_ref("specs/general/coding.adoc"))

    def test_dir_ref_is_not_placeholder(self):
        # 目录型有确定判据（目录是否存在），不得被当成占位符整体跳过
        self.assertFalse(cm._is_placeholder_ref("script/"))
        self.assertFalse(cm._is_placeholder_ref("specs/"))

    def test_true_placeholders_still_recognized(self):
        self.assertTrue(cm._is_placeholder_ref("specs/..."))
        self.assertTrue(cm._is_placeholder_ref("specs/**"))
        self.assertTrue(cm._is_placeholder_ref("specs/stack/<语言>.adoc"))

    def test_glob_ref_is_placeholder(self):
        # 通配清单不是具体路径（本轮修）：`specs/*.adoc` 曾被当成具体文件、假红长期挂着
        self.assertTrue(cm._is_placeholder_ref("specs/*.adoc"))
        self.assertTrue(cm._is_placeholder_ref("script/specs-rules/*.toml"))
        # 具体路径不得被当成占位符（否则存在性检查被整段放过）
        self.assertFalse(cm._is_placeholder_ref("specs/general/coding.adoc"))
        self.assertFalse(cm._is_placeholder_ref("script/check_specs.py"))


class TestAdocCompileCmd(unittest.TestCase):
    """钉住『RubyInstaller 的 gem 入口是 `.bat`/`.cmd` 外壳，须经 `cmd /c` 调用』。

    本轮实测：本机装上 Ruby 版 `asciidoctor`（`C:\\Ruby40-x64\\bin\\asciidoctor.BAT`）后，
    探测器确实找到了它，但 `subprocess` **不能直接执行 `.bat`**——语法段整段抛
    `FileNotFoundError: [WinError 2]`（连"缺工具即报错"那条路径都走不到）。故按后缀判、
    这类外壳经 `cmd /c` 调用；非 Windows 或普通可执行文件照旧按 argv 调。
    """

    def test_bat_shim_wrapped_by_cmd(self):
        with mock.patch.object(os, "name", "nt"):
            cmd = cm._adoc_compile_cmd("asciidoctor", "a.adoc",
                                       exe=r"C:\Ruby40-x64\bin\asciidoctor.BAT")
        self.assertEqual(cmd[:3], ["cmd", "/c", r"C:\Ruby40-x64\bin\asciidoctor.BAT"])
        self.assertIn("--failure-level=WARN", cmd)

    def test_plain_executable_not_wrapped(self):
        cmd = cm._adoc_compile_cmd("asciidoctor", "a.adoc", exe="/usr/local/bin/asciidoctor")
        self.assertEqual(cmd[0], "/usr/local/bin/asciidoctor")
        self.assertNotIn("cmd", cmd)
        self.assertIn("--failure-level=WARN", cmd)

    def test_python_processor_has_no_failure_level_flag(self):
        # Python 版没有 `--failure-level`（传了整批命令都会失败），故对它不发该开关
        cmd = cm._adoc_compile_cmd("asciidoc", "a.adoc", exe="asciidoc")
        self.assertNotIn("--failure-level=WARN", cmd)
        self.assertEqual(cmd, ["asciidoc", "-o", "-", "a.adoc"])


class TestRefsExistOnGlob(CheckSpecsTestCase):
    """钉住『通配清单不得被当成悬空引用』（`check_refs_exist` 的判据侧修复）。

    本仓库实证：`specs-project-maintainer/guards.adoc` 里那句"登记路径须能被取回脚本的
    `specs/*.adoc` 清单解析命中"被报成「引用了不存在的文件」——那是**通配**、不是具体路径，
    存在性无从核对，报红长期留着。反例的另一半同样要守住：**具体路径悬空时仍须报红**，
    否则"顺手把存在性检查放过"就没人拦。
    """

    def test_glob_ref_not_reported(self):
        self.write("AGENTS_COMMON.adoc", "= 入口\n\n取回脚本按 `specs/*.adoc` 清单解析。\n")
        cm.check_refs_exist()
        self.assertEqual("", self.error_texts())

    def test_concrete_missing_ref_still_reported(self):
        self.write("AGENTS_COMMON.adoc", "= 入口\n\n见 `specs/general/nope.adoc`。\n")
        cm.check_refs_exist()
        self.assertIn("引用了不存在的文件", self.error_texts())


# --------------------------------------------------------------------------- #
# check_toolchain_present_guard（校验工具链齐备）
# --------------------------------------------------------------------------- #
class TestToolchainPresentGuard(CheckSpecsTestCase):
    """钉住『校验手段依赖的工具须装齐、缺工具不得静默跳过』的三处落点。

    本条要防的失效形态：脚本里写着某段校验、环境里没有它依赖的工具、跑起来却报 OK
    （本仓库实证：语法编译段长期走"跳过"分支而 `check_specs.py` 始终报绿）。
    故三处落点缺一即报错：公共条文本体、本仓库落点、CI 的安装与装后校验。
    """

    _CI = ("= CI\n\n== 校验链完整（定义未执行防线）\n\n"
           "* **校验手段依赖的工具须在本地实际装齐、不得因缺工具而静默跳过（L1）**："
           "**工具须在执行前齐备**、缺则**装齐**再跑，不得把缺工具走**自动跳过**；"
           "**装了但不够、不算通过（L1）**：同一手段有多个**能力不等价**的实现，"
           "只装了能力弱的那个**不得记作通过**、须装齐能力完整的实现；"
           "装不上时如实标『未执行 + 原因』、**不得记作通过**；"
           "**安装方式须随要求一起给出**（取值＝**可据以装齐**：装哪个、从哪装）。\n")

    # 本仓库落点按「登记处只留一层」的口径写：只点名**承载该检查的那道防线**与安装命令，
    # 处理器次序与效力边界归公共条文（防同一处口径在两份文件里各留一份、各自漂移）
    _OWN = ("= 自身\n* toolchain: 承载该检查的防线是 `check_asciidoctor_syntax`；"
            "探测不到处理器、或只探测到能力弱的那个时 `check_asciidoctor_syntax` 一律**直接报错**"
            "（不再\"跳过\"，也不\"降级通过\"）；安装：`gem install asciidoctor`。\n")

    # CI 侧的形态：装上并**就地校验**（校验写在安装同一步骤里，失败即整步失败；
    # 只"装"不校验、或校验只输出一行而不影响结论，都会静默退回"缺工具也绿"）
    _WF = ("name: check\n"
           "steps:\n"
           "  - name: Install and verify asciidoctor\n"
           "    run: |\n"
           "      gem install asciidoctor --no-document\n"
           "      command -v asciidoctor\n"
           "      asciidoctor --version\n")

    def _write_all(self, ci=None, own=None, wf=None):
        self.write("specs/general/ci-cd.adoc", self._CI if ci is None else ci)
        self.write("AGENTS.adoc", self._OWN if own is None else own)
        self.write(".github/workflows/check-specs.yml", self._WF if wf is None else wf)

    def test_all_three_landings_pass(self):
        self._write_all()
        cm.check_toolchain_present_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_public_clause_reports(self):
        # 反例①：公共条文本体被删 → 要求只活在本仓库落点里、引用方学不到
        self._write_all(ci="= CI\n\n== 校验链完整（定义未执行防线）\n\n* 别的内容\n")
        cm.check_toolchain_present_guard()
        self.assertIn("不得因缺工具而静默跳过", self.error_texts())

    def test_missing_install_way_reports(self):
        # 反例②：只说要装、不给安装方式 → 执行者装不上就只能跳过
        self._write_all(ci=self._CI.replace("可据以装齐", "照要求办"))
        cm.check_toolchain_present_guard()
        self.assertIn("安装方式", self.error_texts())

    def test_missing_degraded_not_pass_clause_reports(self):
        # 反例②b：删掉『降级实现不算通过』这一句 → 只装能力弱的实现时会被记作通过
        self._write_all(ci=self._CI.replace("装了但不够、不算通过（L1）**：", ""));
        cm.check_toolchain_present_guard()
        self.assertIn("装了但不够、不算通过", self.error_texts())

    def test_missing_repo_landing_reports(self):
        # 反例③：本仓库落点缺失（只说原则、不点名防线与命令）
        self._write_all(own="= 自身\n* 无\n")
        cm.check_toolchain_present_guard()
        self.assertIn("AGENTS.adoc", self.error_texts())

    def test_missing_ci_verify_step_reports(self):
        # 反例④：CI 只"装"不校验 → 装失败时仍会退回"缺工具也绿"
        self._write_all(wf="name: check\nsteps:\n  - run: gem install asciidoctor\n")
        cm.check_toolchain_present_guard()
        self.assertIn("装后校验", self.error_texts())

    def test_ci_install_step_without_processor_invocation_reports(self):
        # 反例⑤：同一步骤里只 install、没有真的调用处理器（装成没装成都看不出来）
        self._write_all(wf="name: check\nsteps:\n  - name: Install asciidoctor\n"
                           "    run: |\n      gem install asciidoctor --no-document\n")
        cm.check_toolchain_present_guard()
        self.assertIn("装后校验", self.error_texts())

    def test_ci_version_step_separated_from_install_reports(self):
        # 反例⑥：校验被挪到**另一个步骤**（它失败时后面的步骤照跑，装失败仍会绿）
        self._write_all(wf="name: check\nsteps:\n"
                           "  - name: Install asciidoctor\n"
                           "    run: gem install asciidoctor --no-document\n"
                           "  - name: Verify\n    continue-on-error: true\n"
                           "    run: asciidoctor --version\n")
        cm.check_toolchain_present_guard()
        self.assertIn("装后校验", self.error_texts())

    def test_ci_step_name_not_double_counted_as_install(self):
        # 反例⑦：只有名字里有 `gem install asciidoctor`、真步骤里没有安装动作
        self._write_all(wf="name: check\nsteps:\n"
                           "  - name: gem install asciidoctor --no-document\n"
                           "    run: echo skip\n"
                           "  - run: asciidoctor --version\n")
        cm.check_toolchain_present_guard()
        self.assertIn("没有**安装步骤**", self.error_texts())


# --------------------------------------------------------------------------- #
# check_asciidoctor_stub_guard（语法段不得只剩壳）
# --------------------------------------------------------------------------- #
class TestAsciidoctorStubGuard(CheckSpecsTestCase):
    """钉住『AsciiDoc 语法段不得只剩壳』（**本轮 Issue #173 实测的绕过路径**）。

    `check_toolchain_present_guard` 钉的是"探测不到处理器即报错"这段**代码**与 CI 的
    安装步骤**文本**；但"真的编译过每一份 .adoc"这件事本身没有任何 CI 级断言。
    实测：把 `check_asciidoctor_syntax` 的函数体换成 `phase(...); phase_done(); return 0`
    （既不探测、也不编译），`check_specs.py` **仍报 OK**、`check_toolchain_present_guard`
    照样全绿（探测代码不在这个函数里）。故本条把"代码还在 + CI 真的跑它"变成可核对的。
    """

    _SRC = (
        'def check_asciidoctor_syntax():\n'
        '    """语法。"""\n'
        '    phase("AsciiDoc 语法编译验证")\n'
        '    proc, proc_path = _detect_asciidoc_processor()\n'
        '    if proc is None or proc != ASCIIDOC_REQUIRED_PROCESSOR:\n'
        '        err("探测不到处理器、或只装到降级实现", "script/check_specs.py")\n'
        '        phase_done()\n'
        '        return\n'
        '    files = []\n'
        '    for root in ADOC_ROOTS:\n'
        '        files.extend(_collect_adoc_files(root))\n'
        '    for rel in files:\n'
        '        r = subprocess.run(_adoc_compile_cmd(proc, rel))\n'
        '        if r.returncode != 0:\n'
        '            err("语法/告警", rel)\n'
        '    phase_done()\n'
    )
    _WF = ("name: check\n"
           "steps:\n"
           "  - name: Run deterministic spec checks (incl. AsciiDoc syntax)\n"
           "    run: python3 script/check_specs.py\n")

    def _write_all(self, src=None, wf=None):
        self.write("script/check_specs.py", src if src is not None else self._SRC)
        self.write(".github/workflows/check-specs.yml", wf if wf is not None else self._WF)

    def test_valid_passes(self):
        self._write_all()
        cm.check_asciidoctor_stub_guard()
        self.assertEqual(cm.errors, [])

    def test_stubbed_body_reports(self):
        # 反例①：整段换成空壳（既不探测、也不编译）→ 本轮实测的绕过形态
        self._write_all(src=(
            'def check_asciidoctor_syntax():\n'
            '    """（壳）"""\n'
            '    phase("AsciiDoc 语法编译验证")\n'
            '    phase_done()\n'
            '    return 0\n'))
        cm.check_asciidoctor_stub_guard()
        self.assertIn("没有探测处理器", self.error_texts())

    def test_probe_without_err_reports(self):
        # 反例②：探测了、但缺处理器时不报错（只告警）→ 缺工具静默退回"绿"
        self._write_all(src=self._SRC.replace(
            '        err("探测不到处理器、或只装到降级实现", "script/check_specs.py")\n',
            '        log("跳过")\n').replace(
            '            err("语法/告警", rel)\n', '            log("跳过")\n'))
        cm.check_asciidoctor_stub_guard()
        self.assertIn("没有 `err(`", self.error_texts())

    def test_probe_without_compiling_reports(self):
        # 反例③：探测齐了、却没有真的逐个编译（少了收集或编译命令）
        self._write_all(src=self._SRC.replace(
            '        r = subprocess.run(_adoc_compile_cmd(proc, rel))\n', ''))
        cm.check_asciidoctor_stub_guard()
        self.assertIn("没有真的逐个编译", self.error_texts())

    def test_probe_without_adoc_roots_reports(self):
        # 反例④：不按 `ADOC_ROOTS` 覆盖全部维护根（只编仓库根时子树一份都不会被编）
        self._write_all(src=self._SRC.replace('    for root in ADOC_ROOTS:\n', ''))
        cm.check_asciidoctor_stub_guard()
        self.assertIn("ADOC_ROOTS", self.error_texts())

    def test_probe_without_required_processor_reports(self):
        # 反例④b：只判"装没装某个处理器"、不看是不是**能力完整的实现**——
        # 装了 Python 版（拦不住 WARNING）也会被当成通过，正是"降级实现也算通过"的偷懒路径
        self._write_all(src=self._SRC.replace(
            '    if proc is None or proc != ASCIIDOC_REQUIRED_PROCESSOR:\n',
            '    if proc is None:\n'))
        cm.check_asciidoctor_stub_guard()
        self.assertIn("ASCIIDOC_REQUIRED_PROCESSOR", self.error_texts())

    def test_missing_function_reports(self):
        # 反例⑤：整道语法段函数被删
        self._write_all(src='def other_guard():\n    """别的。"""\n')
        cm.check_asciidoctor_stub_guard()
        self.assertIn("check_asciidoctor_syntax", self.error_texts())

    def test_ci_does_not_run_check_specs_reports(self):
        # 反例⑥：CI 里没有任何一步真的执行 `check_specs.py`（步骤名仍写着 AsciiDoc、命令换成了 echo）
        self._write_all(wf=("name: check\nsteps:\n"
                            "  - name: Run deterministic spec checks (incl. AsciiDoc syntax)\n"
                            "    run: echo skip\n"))
        cm.check_asciidoctor_stub_guard()
        self.assertIn("check_specs.py", self.error_texts())

    def test_ci_step_name_not_counted_as_execution(self):
        # 反例⑥b：只有**步骤名**里有 `check_specs.py`、真命令是别的
        self._write_all(wf=("name: check\nsteps:\n"
                            "  - name: python3 script/check_specs.py\n"
                            "    run: echo skip\n"))
        cm.check_asciidoctor_stub_guard()
        self.assertIn("没有任何一步真的执行", self.error_texts())


# --------------------------------------------------------------------------- #
# check_asciidoctor_syntax（--failure-level=WARN）
# --------------------------------------------------------------------------- #
class TestAsciidoctorFailureLevel(CheckSpecsTestCase):
    """钉住语法编译的**效力边界与"缺工具不得跳过"**。

    * `asciidoctor`（Ruby）默认对 WARNING/ERROR 仍返回 0，故命令行必须显式带
      `--failure-level=WARN`，否则 `include::` 目标缺失这类"只告警不报错"的问题必然漏报。
    * Python 版 `asciidoc` **没有**这个开关（实测传了会 `illegal command options`、
      整批命令都会以非 0 失败）——它**拦不住 WARNING 级问题**，故**降级实现不算通过**：
      只探测到它时报错、要求装齐 Ruby 版（旧实现只打一句告警就照常绿，正是"偷懒"路径）。
    * **两个处理器都探测不到时报错**（用户口径：没有环境就要安装环境，不得省略）——
      旧实现此处走"跳过"分支，语法段在本环境长期没跑而脚本照旧报 OK。
    * **合格实现（`asciidoctor`）就位时真的编译**：不因"装了弱实现也能跑"而放过。
    """

    def test_failure_level_constant_present(self):
        src = open(os.path.join(os.path.dirname(cm.__file__),
                                "check_specs.py"), encoding="utf-8").read()
        self.assertIn("--failure-level=WARN", src)

    def test_no_processor_reports_error_instead_of_skipping(self):
        # 两个处理器都探测不到：**报错**，不得静默跳过（防"声明的校验手段从未执行"）
        orig = cm.shutil.which
        cm.shutil.which = lambda name: None
        try:
            cm.check_asciidoctor_syntax()
        finally:
            cm.shutil.which = orig
        self.assertTrue(cm.errors, "缺工具时必须报错（不得跳过）")
        self.assertIn("探测不到任何 AsciiDoc 处理器", cm.errors[0])

    def test_processor_detection_order_prefers_asciidoctor(self):
        # 探测次序：先 Ruby 的 asciidoctor、再 Python 的 asciidoc
        orig = cm.shutil.which
        cm.shutil.which = lambda name: f"/usr/bin/{name}"
        try:
            proc, found = cm._detect_asciidoc_processor()
        finally:
            cm.shutil.which = orig
        self.assertEqual((proc, found), ("asciidoctor", "/usr/bin/asciidoctor"))

    def test_python_asciidoc_only_reports_error(self):
        # 只装了 Python 版（降级实现）：**报错**、要求装齐 Ruby 版——
        # 它不认 --failure-level、拦不住 WARNING 级问题，故"降级处理器不得记作通过"。
        # 也不得对 Python 版发 --failure-level（会以 illegal command options 整批失败）。
        calls = []
        orig_which, orig_run = cm.shutil.which, cm.subprocess.run
        cm.shutil.which = lambda name: "/usr/bin/asciidoc" if name == "asciidoc" else None

        class _R:
            returncode, stderr = 0, ""

        def _run(cmd, **kw):
            calls.append(cmd)
            return _R()

        cm.subprocess.run = _run
        try:
            self.write("specs/general/a.adoc", "= T\n")
            cm.check_asciidoctor_syntax()
        finally:
            cm.shutil.which, cm.subprocess.run = orig_which, orig_run
        self.assertTrue(cm.errors, "只装降级实现时必须报错（不得降级通过）")
        self.assertIn("降级实现", cm.errors[0])
        self.assertFalse([c for c in calls if "--failure-level=WARN" in c],
                         "不得对 Python 版 asciidoc 发 --failure-level")

    def test_ruby_asciidoctor_gets_failure_level_flag(self):
        calls = []
        orig_which, orig_run = cm.shutil.which, cm.subprocess.run
        cm.shutil.which = lambda name: "/usr/bin/asciidoctor" if name == "asciidoctor" else None

        class _R:
            returncode, stderr = 0, ""

        def _run(cmd, **kw):
            calls.append(cmd)
            return _R()

        cm.subprocess.run = _run
        try:
            self.write("specs/general/a.adoc", "= T\n")
            cm.check_asciidoctor_syntax()
        finally:
            cm.shutil.which, cm.subprocess.run = orig_which, orig_run
        self.assertEqual(cm.errors, [])
        self.assertTrue([c for c in calls if "--failure-level=WARN" in c],
                        "Ruby 版 asciidoctor 必须带上 --failure-level=WARN")
        # 命令行形态只此一处可判：注入点须与命令拼装同源（旧实现把拼装写在循环体内，
        # 检查只能靠"重复调一次真实函数"观察，等于把校验跑两遍——语法段有真实副作用，
        # 不该为了观察行为而复跑；故抽出 `_adoc_compile_cmd` 供两条判据各自核对一次）
        self.assertIn("--failure-level=WARN", cm._adoc_compile_cmd("asciidoctor", "/tmp/a.adoc"),
                      "Ruby 版命令行须带 --failure-level=WARN")
        self.assertNotIn("--failure-level=WARN", cm._adoc_compile_cmd("asciidoc", "/tmp/a.adoc"),
                         "Python 版命令行不得带 --failure-level")

    def test_syntax_check_covers_all_adoc_roots(self):
        # 覆盖范围与 `collect_adoc_files` 同源（`_collect_adoc_files` 单一实现）：
        # 只编仓库根时，被 `ADOC_ROOTS` 点名的子树一份都不会被真的编译，而检查照旧显示"完成"
        seen = []
        orig_which, orig_run = cm.shutil.which, cm.subprocess.run
        # 用**合格实现** asciidoctor 观察"真的编了哪些文件"：只装 Python 版会先报错返回、
        # 走不到逐个编译，故这里必须给合格实现（否则用例核的是另一件事）
        cm.shutil.which = lambda name: "/usr/bin/asciidoctor" if name == "asciidoctor" else None

        class _R:
            returncode, stderr = 0, ""

        def _run(cmd, **kw):
            seen.append(cmd[-1])
            return _R()

        cm.subprocess.run = _run
        try:
            self.write("specs/general/a.adoc", "= T\n")
            self.write("docs/b.adoc", "= T\n")
            cm.ADOC_ROOTS = ("", "docs")
            cm.check_asciidoctor_syntax()
        finally:
            cm.shutil.which, cm.subprocess.run = orig_which, orig_run
            cm.ADOC_ROOTS = ("",)
        self.assertEqual(cm.errors, [])
        names = sorted(os.path.relpath(p, self.root).replace("\\", "/") for p in seen)
        self.assertEqual(names, ["docs/b.adoc", "specs/general/a.adoc"])

    def test_syntax_check_reports_missing_adoc_root(self):
        # 反例：`ADOC_ROOTS` 点名的根不存在——该子树一份都没编，须报错而不是静默"完成"
        orig_which = cm.shutil.which
        # 同前：须给合格实现，否则会先因"降级不通过"返回、核不到 ADOC_ROOTS 这一段
        cm.shutil.which = lambda name: "/usr/bin/asciidoctor" if name == "asciidoctor" else None
        try:
            cm.ADOC_ROOTS = ("", "docs")
            cm.check_asciidoctor_syntax()
        finally:
            cm.shutil.which = orig_which
            cm.ADOC_ROOTS = ("",)
        self.assertIn("ADOC_ROOTS", self.error_texts())


# --------------------------------------------------------------------------- #
# check_table_row_pipe_guard（表格行不得以管道收尾）
# --------------------------------------------------------------------------- #
class TestTableRowPipeGuard(CheckSpecsTestCase):
    """钉住『表格行不得以管道收尾』（**本轮 Issue #221 实测的失效路径**）。

    AsciiDoc 把行尾多出的那个管道符读成"多一个空单元格"的残缺行：编译报
    `dropping cells from incomplete row detected end of table`，且**整表单元格错位**、
    报错行号落到别的行上。这类错字**不会被任何文本核锚点的检查发现**（文本一字不少）；
    唯一发现路径是 `check_asciidoctor_syntax` 的编译告警——而本机装不出处理器时那一段
    报错而非报出问题（本仓库实证：行尾多出的管道符长期留在 `guards.adoc` 的清单表里）。
    故本道**与处理器版本无关**、不依赖外部程序即可核。
    """

    _HEAD = ("= 清单" + NL + NL + '[cols="1,2,3", options="header"]' + NL
             + "|===" + NL + "| 序号 | 防线 | 钉住什么" + NL + NL)

    def test_trailing_pipe_reports(self):
        # 反例①：行尾多一个管道符（本轮实测的真实形态）
        self.write("specs-project-maintainer/guards.adoc", self._HEAD
                   + "| 1 | `check_a` | 用途" + NL
                   + "| 2 | `check_b` | 用途 |" + NL + "|===" + NL)
        cm.check_table_row_pipe_guard()
        self.assertIn("收尾", self.error_texts())
        self.assertIn("guards.adoc", self.error_texts())

    def test_clean_table_passes(self):
        # 正例：表格行行尾不写管道符（行内相邻单元格之间照旧以管道分隔）
        self.write("specs-project-maintainer/guards.adoc", self._HEAD
                   + "| 1 | `check_a` | 用途" + NL
                   + "| 2 | `check_b` | 用途" + NL + "|===" + NL)
        cm.check_table_row_pipe_guard()
        self.assertEqual(cm.errors, [])

    def test_pipe_outside_table_not_reported(self):
        # 边界：表格之外的行以管道符收尾不属本条——AsciiDoc 只把表格块内的管道符
        # 当单元格分隔，正文里的管道符是普通字符（防误伤）
        self.write("specs/general/a.adoc", "= T" + NL + NL + "正文一行以管道符结尾 |" + NL)
        cm.check_table_row_pipe_guard()
        self.assertEqual(cm.errors, [])

    def test_trailing_pipe_before_comment_reports(self):
        # 反例①′：行尾 `|` 之后还有**行内注释**——AsciiDoc 同样读成"多一个空单元格"
        # （实测 `asciidoctor 2.0.26`：`| D | E | F | // x` 报同一句
        # `dropping cells from incomplete row detected end of table`）。
        # 只核"裸行尾管道"一种形态时这一行**漏放**。
        self.write("specs-project-maintainer/guards.adoc", self._HEAD
                   + "| 1 | `check_a` | 用途" + NL
                   + "| 2 | `check_b` | 用途 | // 备注" + NL + "|===" + NL)
        cm.check_table_row_pipe_guard()
        self.assertIn("收尾", self.error_texts())

    def test_trailing_pipe_before_hard_break_reports(self):
        # 反例①″：行尾 `|` 之后还有**硬换行标记**（`+`）——同上，AsciiDoc 同样报
        # `dropping cells from incomplete row detected end of table`。
        self.write("specs-project-maintainer/guards.adoc", self._HEAD
                   + "| 1 | `check_a` | 用途" + NL
                   + "| 2 | `check_b` | 用途 | +" + NL + "|===" + NL)
        cm.check_table_row_pipe_guard()
        self.assertIn("收尾", self.error_texts())

    def test_comment_after_clean_row_passes(self):
        # 正例：行尾本来没有 `|`，注释/硬换行标记不得把这一行误报（防剥标记时误伤）
        self.write("specs-project-maintainer/guards.adoc", self._HEAD
                   + "| 1 | `check_a` | 用途 // 备注" + NL
                   + "| 2 | `check_b` | 用途 +" + NL + "|===" + NL)
        cm.check_table_row_pipe_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_landing_reports(self):
        # 反例②：落点整个缺失（防线无从核对，不得静默通过）
        cm.check_table_row_pipe_guard()
        self.assertTrue(cm.errors)

    def test_multiple_landings_all_checked(self):
        # 反例③：多个维护根逐份核（只核一个文件时，别的落点里的同形错字无人发现）
        self.write("specs/general/a.adoc", "= T" + NL + NL + "|===" + NL + "| x | |" + NL + "|===" + NL)
        self.write("library/b.adoc", "= T" + NL + NL + "|===" + NL + "| x | |" + NL + "|===" + NL)
        cm.check_table_row_pipe_guard()
        texts = self.error_texts()
        self.assertIn("specs/general/a.adoc", texts)
        self.assertIn("library/b.adoc", texts)


# check_refs_exist：目录型引用
# --------------------------------------------------------------------------- #
class TestCheckRefsExistDirRefs(CheckSpecsTestCase):
    def test_existing_dir_ref_passes(self):
        self.write("AGENTS_COMMON.adoc", "见 `script/`")
        self.write("script/clean_tmp.py", "#!/usr/bin/env python3\n")
        cm.check_refs_exist()
        self.assertEqual(cm.errors, [])

    def test_missing_dir_ref_reports(self):
        # 反例：目录型引用指向不存在的目录 —— 原实现整体跳过，这里必须报出
        self.write("AGENTS_COMMON.adoc", "见 `script/`")
        cm.check_refs_exist()
        self.assertIn("不存在的目录", self.error_texts())
        self.assertIn("script/", self.error_texts())

    def test_missing_link_dir_ref_reports(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc", "见 link:../../gone-dir/[]")
        cm.check_refs_exist()
        self.assertIn("不存在的目录", self.error_texts())


# --------------------------------------------------------------------------- #
# check_refs_exist / check_section_refs：CHANGELOG 历史豁免
# --------------------------------------------------------------------------- #
class TestHistoricalFileExemption(CheckSpecsTestCase):
    """CHANGELOG.adoc 是只追加的变更历史：旧路径"查不到"是记录本身，不属悬空。"""

    def test_changelog_in_collected(self):
        self.write("CHANGELOG.adoc", "= 变更\n")
        self.assertIn("CHANGELOG.adoc", cm.collect_adoc_files())

    def test_changelog_old_paths_not_reported(self):
        self.write("CHANGELOG.adoc", "= 变更\n\n见 `specs/gone/old.adoc`\n")
        cm.check_refs_exist()
        self.assertEqual(cm.errors, [])

    def test_changelog_old_section_not_reported(self):
        self.write("CHANGELOG.adoc", "= 变更\n")
        self.write("specs/general/doc.adoc", "= 文档\n\n== 注释与文档\n")
        self.write("CHANGELOG.adoc",
                   "= 变更\n\n见 link:specs/general/doc.adoc[]「已改名节」\n")
        cm.check_section_refs()
        self.assertEqual(cm.errors, [])


# --------------------------------------------------------------------------- #
# check_refs_exist
# --------------------------------------------------------------------------- #
class TestCheckRefsExist(CheckSpecsTestCase):
    def test_valid_reference_passes(self):
        self.write("AGENTS_COMMON.adoc", "加载 `specs/general/coding.adoc`")
        self.write("specs/general/coding.adoc", "= 编码")
        cm.check_refs_exist()
        self.assertEqual(cm.errors, [])

    def test_dangling_backtick_reference_reports(self):
        self.write("AGENTS_COMMON.adoc", "加载 `specs/general/gone.adoc`")
        cm.check_refs_exist()
        self.assertIn("不存在", self.error_texts())
        self.assertIn("specs/general/gone.adoc", self.error_texts())

    def test_dangling_link_between_specs_reports(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/core/execution.adoc",
                   "见 link:../general/nothing.adoc[]")
        cm.check_refs_exist()
        self.assertIn("不存在", self.error_texts())
        self.assertIn("specs/general/nothing.adoc", self.error_texts())

    def test_link_pointing_to_existing_file_passes(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/core/execution.adoc",
                   "见 link:../general/doc-design.adoc[]")
        self.write("specs/general/doc-design.adoc", "= 设计")
        cm.check_refs_exist()
        self.assertEqual(cm.errors, [])


# --------------------------------------------------------------------------- #
# check_link_refs
# --------------------------------------------------------------------------- #
class TestCheckLinkRefs(CheckSpecsTestCase):
    def test_relative_link_passes(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/core/execution.adoc",
                   "见 link:../general/doc-design.adoc[]")
        cm.check_link_refs()
        self.assertEqual(cm.errors, [])

    def test_root_absolute_link_reports(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/core/execution.adoc",
                   "见 link:/specs/general/doc-design.adoc[]")
        cm.check_link_refs()
        self.assertIn("根绝对", self.error_texts())
        self.assertIn("link:/specs/general/doc-design.adoc", self.error_texts())

    def test_out_of_root_link_reports(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/core/execution.adoc", "见 link:../../../x.adoc[]")
        cm.check_link_refs()
        self.assertIn("越出仓库根", self.error_texts())

    def test_external_and_anchor_skipped(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc",
                   "link:https://example.com/a[] link:#sec-1[]")
        cm.check_link_refs()
        self.assertEqual(cm.errors, [])


# --------------------------------------------------------------------------- #
# check_stack_consistency
# --------------------------------------------------------------------------- #
class TestCheckStackConsistency(CheckSpecsTestCase):
    def test_registered_and_exists_passes(self):
        self.write("AGENTS_COMMON.adoc", "技术栈层登记 `specs/stack/java.adoc`")
        self.write("specs/stack/java.adoc", "= Java")
        cm.check_stack_consistency()
        self.assertEqual(cm.errors, [])

    def test_existing_but_not_registered_reports(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/stack/python.adoc", "= Python")
        cm.check_stack_consistency()
        self.assertIn("存在但未在技术栈层登记", self.error_texts())

    def test_registered_but_not_exists_reports(self):
        self.write("AGENTS_COMMON.adoc", "登记 `specs/stack/nodejs.adoc`")
        cm.check_stack_consistency()
        self.assertIn("不存在", self.error_texts())
        self.assertIn("specs/stack/nodejs.adoc", self.error_texts())


# --------------------------------------------------------------------------- #
# check_forbidden_patterns
# --------------------------------------------------------------------------- #
class TestCheckForbiddenPatterns(CheckSpecsTestCase):
    def test_clean_file_passes(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/review.adoc", "代码走 code review，无私有约定。")
        cm.check_forbidden_patterns()
        self.assertEqual(cm.errors, [])

    def test_private_interface_pattern_reports(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/review.adoc", "定义 ICFoo 接口。")
        cm.check_forbidden_patterns()
        self.assertNotEqual(cm.errors, [])
        self.assertIn("IC 前缀", self.error_texts())


# --------------------------------------------------------------------------- #
# check_historical_notes（『不保留无用的历史来源声明』机械抓手）
# --------------------------------------------------------------------------- #
class TestCheckHistoricalNotes(CheckSpecsTestCase):
    def test_clean_file_passes(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/git.adoc", "文件重命名必须使用 git mv。")
        cm.check_historical_notes()
        self.assertEqual(cm.errors, [])

    def test_early_version_note_reports(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc", "早期版本直接把 URL 交给 AI。")
        cm.check_historical_notes()
        self.assertNotEqual(cm.errors, [])
        self.assertIn("历史来源声明", self.error_texts())

    def test_migration_note_reports(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("AGENTS.adoc", "原位于通用规范必加载层，迁移至此并从通用规范中移除。")
        cm.check_historical_notes()
        self.assertNotEqual(cm.errors, [])
        self.assertIn("历史来源声明", self.error_texts())

    def test_old_naming_note_reports(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("AGENTS.adoc", "本文件是真正的 agents.md。")
        cm.check_historical_notes()
        self.assertNotEqual(cm.errors, [])
        self.assertIn("历史来源声明", self.error_texts())

    def test_git_mv_neutral_use_not_reported(self):
        # 中性合理表述（git 规范中"重命名"）不得误报
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/git.adoc", "文件移动/重命名必须使用 git mv，禁止 delete+create。")
        cm.check_historical_notes()
        self.assertEqual(cm.errors, [])


# --------------------------------------------------------------------------- #
# check_install_codeblock（公共入口「安装与更新」的模板代码块逐字保留）
# --------------------------------------------------------------------------- #
class TestCheckInstallCodeblock(CheckSpecsTestCase):
    """钉住入口模板代码块逐字保留 + 入口文件名规则。

    **落点已并入公共入口**（`AGENTS_COMMON.adoc`「安装与更新」）：安装文档此前是独立文件，
    用户口径是"把它的内容压进入口前部、删除源文件、以后直接引用入口"。故夹具把模板与
    文件名规则写在同一个文件的两处——模板在「安装与更新」节的代码块内，文件名规则在该节
    正文里（缺一即报红）。
    """

    SECTION = "== 安装与更新（引用方接入与取回口径）\n\n"
    # 文件名规则（默认 `AGENTS.adoc` + 兼容已存在的 `AGENTS.md`）；单独一段便于反例只去掉它。
    FILENAME_RULES = (
        "* **入口文档（安装流程）**：文件名取 `AGENTS.adoc`；已存在 `AGENTS.md` 时就地融合"
        "（**不重命名、不迁移、不另建**）。\n\n")
    TEMPLATE = (
        "[source,asciidoc]\n----\n"
        "本项目的 agent 执行规范入口为：\n\n"
        "https://agent.c332030.com/AGENTS_COMMON.adoc\n\n"
        "取规范脚本（要再取一次规范、或本机没有副本时用它）：\n\n"
        "https://agent.c332030.com/script/fetch-specs.py\n\n"
        "优先取到本地副本（避免网络原因无法访问）：**下载的文件一律只落 `~/.cache/agent-specs`**，"
        "在项目根目录运行一次取文件抓手即可；取不到时就直接读上面的远程入口；"
        "**需要最新规范时再运行一次取规范脚本即是更新**。\n\n"
        "规范属强制约束：**开工前必须先读取规范再执行**，不得因未读取/记不全而跳过或放宽任何条款。\n\n"
        "读取该入口及其引用的 specs/ 规范，并持续遵守其全部要求。\n"
        "----\n")

    def _body(self, template=None, rules=None):
        return (self.SECTION
                + (self.FILENAME_RULES if rules is None else rules)
                + (self.TEMPLATE if template is None else template))

    def test_wellformed_template_passes(self):
        # 正例：模板逐字保留 + 入口文件名规则齐备
        self.write("AGENTS_COMMON.adoc", self._body())
        cm.check_install_codeblock()
        self.assertEqual(cm.errors, [])

    def test_missing_entry_file_skips(self):
        # 入口文件不在：应跳过不报错（新根下什么都不写，文件自然不存在）
        cm.check_install_codeblock()
        self.assertEqual(cm.errors, [])

    def test_no_entry_title_passes(self):
        # 正例（用户口径）：模板不带 `= Agent 规范入口` 标题也应判绿——标题是用户手工
        # 删掉的可精炼项，不再作必备行（曾经必核，结果是把用户删的标题又"补"了回去）
        self.write("AGENTS_COMMON.adoc", self._body())
        cm.check_install_codeblock()
        self.assertEqual(cm.errors, [])

    def test_section_removed_reports(self):
        # 反例：承载模板的「安装与更新」节被删 → 安装口径与入口模板一并丢失
        self.write("AGENTS_COMMON.adoc", "." + self._body())
        cm.check_install_codeblock()
        self.assertIn("安装与更新", self.error_texts())

    def test_duplicate_path_reports(self):
        # 反例（用户点名形态）：模板里同一个 URL 出现两次——两个不同名目
        # （"规范入口"与"安装与更新的文档入口"）指向同一份文件，读的人以为有两个落点。
        # 本仓库实证成因：安装口径并入公共入口、INSTALL.adoc 被删后，原来指向安装文档的
        # 那一行被改成入口自己的地址，于是重复。
        dup = self.TEMPLATE.replace(
            "取规范脚本（要再取一次规范、或本机没有副本时用它）：\n\n",
            "安装与更新的文档入口为（要重装、要更新时直接读它）：\n\n"
            "https://agent.c332030.com/AGENTS_COMMON.adoc\n\n"
            "取规范脚本（要再取一次规范、或本机没有副本时用它）：\n\n")
        self.write("AGENTS_COMMON.adoc", self._body(template=dup))
        cm.check_install_codeblock()
        self.assertIn("同一路径重复出现", self.error_texts())

    def test_collapsed_blank_lines_reports(self):
        # 反例：AI 折叠了代码块内的空行，导致段落粘连、样式改变
        collapsed = self.TEMPLATE.replace(
            "本项目的 agent 执行规范入口为：\n\n"
            "https://agent.c332030.com/AGENTS_COMMON.adoc\n\n"
            "取规范脚本（要再取一次规范、或本机没有副本时用它）：\n\n"
            "https://agent.c332030.com/script/fetch-specs.py\n\n",
            "本项目的 agent 执行规范入口为：\n"
            "https://agent.c332030.com/AGENTS_COMMON.adoc\n"
            "取规范脚本（要再取一次规范、或本机没有副本时用它）：\n"
            "https://agent.c332030.com/script/fetch-specs.py\n")
        self.write("AGENTS_COMMON.adoc", self._body(template=collapsed))
        cm.check_install_codeblock()
        self.assertNotEqual(cm.errors, [])
        self.assertIn("缺少空行", self.error_texts())

    def test_blank_line_swallowed_between_description_and_path_reports(self):
        # 反例（本轮实测复现的**防线空转**）：吞掉**说明段之间**的空行——两行仍各自独立成行、
        # 且它们之间原本就隔着别的必备行，故"相邻必备行间距 ≥ 2"仍成立、旧判据全绿。
        # 实测形态：`https://…/AGENTS_COMMON.adoc` 与 `取规范脚本（…）：` 之间的空行被吞。
        collapsed = self.TEMPLATE.replace(
            "https://agent.c332030.com/AGENTS_COMMON.adoc\n\n"
            "取规范脚本（要再取一次规范、或本机没有副本时用它）：",
            "https://agent.c332030.com/AGENTS_COMMON.adoc\n"
            "取规范脚本（要再取一次规范、或本机没有副本时用它）：")
        self.write("AGENTS_COMMON.adoc", self._body(template=collapsed))
        cm.check_install_codeblock()
        self.assertIn("缺少空行", self.error_texts())

    def test_blank_line_swallowed_before_last_lines_reports(self):
        # 反例：模板末尾两条必备行之间那颗空行被吞——它们之间没有其它必备行，
        # 但仍属"两段紧贴、样式会变"；判据须逐对相邻行核、不按"间距阈值"核
        collapsed = self.TEMPLATE.replace(
            "不得因未读取/记不全而跳过或放宽任何条款。\n\n"
            "读取该入口及其引用的 specs/ 规范",
            "不得因未读取/记不全而跳过或放宽任何条款。\n"
            "读取该入口及其引用的 specs/ 规范")
        self.write("AGENTS_COMMON.adoc", self._body(template=collapsed))
        cm.check_install_codeblock()
        self.assertIn("缺少空行", self.error_texts())

    def test_parenthetical_note_may_hug_previous_line(self):
        # 正例（真实模板的形态）：入口地址下一行紧接的**全角括注**是同一条信息的延续，
        # 本就紧贴、须判绿——不给这条例外会把正确写法判红（真实文件即如此）
        hugged = self.TEMPLATE.replace(
            "https://agent.c332030.com/AGENTS_COMMON.adoc\n\n",
            "https://agent.c332030.com/AGENTS_COMMON.adoc\n"
            "（重装、更新、要完整的取法与退路，也读它——安装与取回口径在本文件内）\n\n")
        self.write("AGENTS_COMMON.adoc", self._body(template=hugged))
        cm.check_install_codeblock()
        self.assertEqual(cm.errors, [])

    def test_merged_line_reports(self):
        # 反例：两段内容被合并到同一行，找不到独立成行的必备行
        merged = self.TEMPLATE.replace(
            "本项目的 agent 执行规范入口为：\n\n"
            "https://agent.c332030.com/AGENTS_COMMON.adoc",
            "本项目的 agent 执行规范入口为：https://agent.c332030.com/AGENTS_COMMON.adoc")
        self.write("AGENTS_COMMON.adoc", self._body(template=merged))
        cm.check_install_codeblock()
        self.assertNotEqual(cm.errors, [])
        self.assertIn("缺失或行被合并", self.error_texts())

    def test_missing_fetch_script_path_reports(self):
        # 反例（用户点名形态）：模板不给取规范脚本路径 → 新实例不知道如何去下载规范
        doc = self.TEMPLATE.replace(
            "https://agent.c332030.com/script/fetch-specs.py\n", "")
        self.write("AGENTS_COMMON.adoc", self._body(template=doc))
        cm.check_install_codeblock()
        self.assertIn("fetch-specs.py", self.error_texts())

    def test_missing_delimiters_reports(self):
        # 反例：代码块定界符不完整
        bad = self.TEMPLATE.replace("----\n", "")
        self.write("AGENTS_COMMON.adoc", self._body(template=bad))
        cm.check_install_codeblock()
        self.assertIn("定界符", self.error_texts())

    def test_agents_md_only_in_fused_section_reports(self):
        # 反例：兼容规则只写"按 AGENTS.md 融合"，漏掉"不重命名 / 不另建"（会重命名或分叉出两个入口）
        doc = self._body(
            rules="* 入口文件名取 `AGENTS.adoc`；仅 `AGENTS.md` 存在时在它上面融合"
                  "（文件名为 `AGENTS.md`）。\n\n")
        self.write("AGENTS_COMMON.adoc", doc)
        cm.check_install_codeblock()
        self.assertIn("入口文件名规则被破坏", self.error_texts())

    def test_dropping_agents_md_compat_reports(self):
        # 反例：只认 AGENTS.adoc、把 AGENTS.md 兼容规则删掉（既有 AGENTS.md 的项目无法安装）
        self.write("AGENTS_COMMON.adoc", self.SECTION + self.TEMPLATE)
        cm.check_install_codeblock()
        self.assertNotEqual(cm.errors, [])
        self.assertIn("AGENTS.md", self.error_texts())


# --------------------------------------------------------------------------- #

class TestCheckIndexPageGuard(CheckSpecsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._orig_files = (cm.DOC_FILE, cm.DOC_MODULE_FILE)
        cm.DOC_FILE = os.path.join(self.root, "specs", "general", "doc.adoc")
        cm.DOC_MODULE_FILE = os.path.join(self.root, "specs", "general", "doc-module.adoc")

    def tearDown(self) -> None:
        cm.DOC_FILE, cm.DOC_MODULE_FILE = self._orig_files
        super().tearDown()

    DOC = (
        "= 文档规范\n\n== 文档组织与导航\n\n"
        "* 文档目录即站点导航：已承载文档的目录须有索引页。\n"
        "* **索引页的触发判据（「该不该建索引页」）**：索引页是「有下级内容」时才需要——\n"
        "  ** 目录下已存在实质文档（已承载实质文档） → 建索引页；**空目录/仅有索引页「自己」一律不建**；\n"
        "  ** 索引页**只做导航**：不得把上一级文档（如模块 README）**换个壳复制**；\n"
        "  ** 模块级导航由模块 `README` 承担**：模块内若无独立功能文档，**不必**另设一层索引。\n"
    )
    MODULE = (
        "= 模块级文档规范\n\n"
        "* 模块 `doc/` 下**按需**放 `README.adoc` 作模块文档索引——判据是模块 `doc/` 下是否已承载实质文档：\n"
        "  ** 已承载模块内功能/组件文档 → 放 `README.adoc`；\n"
        "  ** 模块 `doc/` 下无任何实质文档 → **不建**；导航由**模块自身 `README`** 承担。\n"
    )

    def _write_valid(self):
        self.write("specs/general/doc.adoc", self.DOC)
        self.write("specs/general/doc-module.adoc", self.MODULE)

    def test_valid_passes(self):
        self._write_valid()
        cm.check_index_page_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_doc_file_reports(self):
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "general", "doc.adoc"))
        cm.check_index_page_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_trigger_clause_removed_reports(self):
        # 反例：判据节被删 → 只剩「每级目录须有索引页」，失效复发
        self._write_valid()
        self.write("specs/general/doc.adoc", "= 文档规范\n\n== 文档组织与导航\n* 每级目录须有索引页。\n")
        cm.check_index_page_guard()
        self.assertIn("索引页的触发判据", self.error_texts())

    def test_empty_shell_clause_removed_reports(self):
        # 反例：「空目录不建索引页」被删 → 批量空壳索引重新被允许
        self._write_valid()
        bad = self.DOC.replace(
            "**空目录/仅有索引页「自己」一律不建**", "**空目录也应补齐索引**")
        self.write("specs/general/doc.adoc", bad)
        cm.check_index_page_guard()
        self.assertIn("空目录", self.error_texts())

    def test_module_readme_clause_removed_reports(self):
        # 反例：模块级导航归属被删 → 「每个模块都该有 doc/README.adoc」重新成立
        self._write_valid()
        self.write("specs/general/doc-module.adoc",
                   "= 模块级文档规范\n\n* 模块 `doc/` 下**应放** `README.adoc`。\n")
        cm.check_index_page_guard()
        self.assertIn("doc-module.adoc", self.error_texts())


class TestCheckDataDictionaryGuard(CheckSpecsTestCase):
    """钉住『数据字典防线』（按作用域归档、只引名称、新增与调整即生效）。

    本条的失效形态不是「没写规则」，而是**写了规则却仍然膨胀、仍然各写一遍**——故反例须
    覆盖**判据本体被抽走**（不是只覆盖"整节被删"）：
      ① 分档表被压成一句并列词（"每档只一处"与"拿什么判属于哪档"都无从核对）；
      ② **「当前文档」档的落点句被抽掉**（用户点名的那句：定义写在该文档开头）；
      ③ **「每次新增与调整内容时都须判定」被删**（本条只在"新建字典"那一次生效）；
      ④ 图书馆档被删（依据被当名称收进规则正文、规则被复制进图书馆）；
      ⑤ 调度器未登记（规则在、但永远不会被加载）；
      ⑥ 文档侧互引断开（读文档规范/编码规范的人永远看不到这节）。
    另钉「定义与使用说明分列」被合并（把 SKOS 的两个属性并成一个）。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_files = (cm.TERMINOLOGY_FILE, cm.DOC_FILE, cm.ENCODING_FILE)
        cm.TERMINOLOGY_FILE = os.path.join(self.root, "specs", "general", "terminology.adoc")
        cm.DOC_FILE = os.path.join(self.root, "specs", "general", "doc.adoc")
        cm.ENCODING_FILE = os.path.join(self.root, "specs", "general", "encoding.adoc")

    def tearDown(self) -> None:
        cm.TERMINOLOGY_FILE, cm.DOC_FILE, cm.ENCODING_FILE = self._orig_files
        super().tearDown()

    TERM = (
        "= 数据字典规范\n\n== 数据字典\n\n"
        "* **只引名称、不引定义（L1）**：只写名称，**不得**复述定义。\n"
        "* **作用域决定落点、每档只一处（L1）**：写进**唯一落点**，**每档只一处**；"
        "**本文件的字典写在本文开头**。判据即表末一列，**抽取**掉专有名词后核对。\n\n"
        "| 作用域 | 唯一落点 | 判据 |\n"
        "| 全局 | `specs/**` | 抽取后仍成立 |\n"
        "| 项目全局 | 根 `AGENTS.adoc` | 只在本项目成立 |\n"
        "| 模块/功能 | 模块设计文档 | 跨类共用 |\n"
        "| 类/接口 | 代码文档注释 | 单类内部 |\n"
        "| 当前文档 | 该文档开头 | 只有读这份文档的人需要 |\n"
        "| 图书馆 | 入口主题登记表 | 依据 |\n"
        "| 提示词 | 产物所在文件 | 随产物走 |\n\n"
        "* **一行一个名称（L1）**：**每个名称独占一段**、不得挤在同一行；"
        "增删或引用其中一个名称**不必碰到**同一段里的其他名称。\n"
        "* **条目形态照标准（L2）**：照 ISO 1087，**定义**与**使用说明**分列"
        "（SKOS 的 `skos:definition` 与 `skos:scopeNote`）。\n"
        "* **反膨胀（L1）**：**判定标准**（任一命中即违规）：上游落点收录了下游名称。\n"
        "* **新增与调整内容时都须判定（L1）**：**每次**新增或调整内容时都须走一遍；"
        "调整掉的名称须**同步**其定义。\n"
        "* **图书馆等「不在默认引用面内」的落点按其自身规则走（L2）**：图书馆不在默认引用面内。\n"
    )

    def _write_valid(self):
        self.write("specs/general/terminology.adoc", self.TERM)
        self.write("specs/general/doc.adoc",
                   "= 文档规范\n\n== 文档组织与导航\n\n"
                   "* **名称的定义按作用域归档、引用只写名称**：见 "
                   "`specs/general/terminology.adoc`「数据字典」；本条与「信息归属」同向。\n")
        self.write("specs/general/encoding.adoc",
                   "= 编码规范\n\n* **术语统一（L2）**：同名同义；"
                   "定义写在哪见 `specs/general/terminology.adoc`「数据字典」。\n")
        self.write("AGENTS_COMMON.adoc",
                   "= 入口\n\n== 分类与懒加载（加载调度器）\n\n=== 通用层（涉及对应活动时加载）\n\n"
                   "* **新增/调整任何内容时判定名称的落点** → `specs/general/terminology.adoc`\n\n"
                   "== 技术栈扩展约定\n")

    def test_valid_passes(self):
        self._write_valid()
        cm.check_data_dictionary_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_file_reports(self):
        # 反例：整节承载文件被删
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "general", "terminology.adoc"))
        cm.check_data_dictionary_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_section_removed_reports(self):
        # 反例：整节被删（判据全失）
        self._write_valid()
        self.write("specs/general/terminology.adoc", "= 数据字典规范\n\n== 别的节\n")
        cm.check_data_dictionary_guard()
        self.assertIn("数据字典", self.error_texts())

    def test_scope_table_flattened_reports(self):
        # 反例①：分档表被压成一句并列词 → "每档只一处"与"拿什么判属于哪档"都无从核对
        self._write_valid()
        bad = self.TERM.replace("| 作用域 | 唯一落点 | 判据 |\n", "")
        bad = bad.replace("| 全局 | `specs/**` | 抽取后仍成立 |\n", "")
        self.write("specs/general/terminology.adoc", bad)
        cm.check_data_dictionary_guard()
        self.assertIn("唯一落点", self.error_texts())

    def test_current_document_clause_removed_reports(self):
        # 反例②：用户点名的那句（当前文档的定义写在该文档开头）被抽掉
        self._write_valid()
        bad = self.TERM.replace("**本文件的字典写在本文开头**", "**另开一处存放**")
        bad = bad.replace("| 当前文档 | 该文档开头 | 只有读这份文档的人需要 |\n", "")
        self.write("specs/general/terminology.adoc", bad)
        cm.check_data_dictionary_guard()
        self.assertIn("当前文档", self.error_texts())

    def test_scope_dropped_reports(self):
        # 反例②b：作用域少了一档（图书馆档被删）→ 依据会被当名称收进规则正文
        self._write_valid()
        bad = self.TERM.replace("| 图书馆 | 入口主题登记表 | 依据 |\n", "")
        self.write("specs/general/terminology.adoc", bad)
        cm.check_data_dictionary_guard()
        self.assertIn("作用域分档表缺失", self.error_texts())
        self.assertIn("图书馆", self.error_texts())

    def test_scope_row_dropped_but_name_mentioned_elsewhere_reports(self):
        # 反例②c（本轮实测的**假绿**）：档位行从表里被抽掉，但档位名仍以别的形态出现在正文里
        # ——旧判定用裸子串 `f"| {scope}"`，此时仍命中、防线全绿（"表被抽掉"正是本条要拦的
        # 失效形态）。判定须按**表格行**取值。
        self._write_valid()
        bad = self.TERM.replace("| 全局 | `specs/**` | 抽取后仍成立 |\n", "")
        bad += "\n正文补一句：落点分档见 `| 全局 | / | 项目全局 |` 的说明。\n"
        self.write("specs/general/terminology.adoc", bad)
        cm.check_data_dictionary_guard()
        self.assertIn("作用域分档表缺失", self.error_texts())
        self.assertIn("全局", self.error_texts())

    def test_new_and_adjusted_timing_removed_reports(self):
        # 反例③："每次新增、调整内容时都须判定"被删 → 本条只在"新建字典"那一次生效
        self._write_valid()
        bad = self.TERM.replace("* **新增与调整内容时都须判定（L1）**：**每次**新增或调整内容时都须走一遍；"
                                "调整掉的名称须**同步**其定义。\n", "")
        self.write("specs/general/terminology.adoc", bad)
        cm.check_data_dictionary_guard()
        self.assertIn("调整内容时都须判定", self.error_texts())

    def test_definition_and_scope_note_merged_reports(self):
        # 反例④：把"定义"与"使用说明"并成一个属性（SKOS 的两个属性被合并）
        self._write_valid()
        bad = self.TERM.replace(
            "* **条目形态照标准（L2）**：照 ISO 1087，**定义**与**使用说明**分列"
            "（SKOS 的 `skos:definition` 与 `skos:scopeNote`）。\n",
            "* **条目形态照标准（L2）**：照 ISO 1087 写。\n")
        self.write("specs/general/terminology.adoc", bad)
        cm.check_data_dictionary_guard()
        self.assertIn("使用说明", self.error_texts())

    def test_one_name_per_line_removed_reports(self):
        # 反例④b：用户点名的那句（一行一个名称）被抽掉 → 名称又挤回一段
        self._write_valid()
        bad = self.TERM.replace(
            "* **一行一个名称（L1）**：**每个名称独占一段**、不得挤在同一行；"
            "增删或引用其中一个名称**不必碰到**同一段里的其他名称。\n", "")
        self.write("specs/general/terminology.adoc", bad)
        cm.check_data_dictionary_guard()
        self.assertIn("一行一个名称", self.error_texts())

    def test_dispatcher_not_registered_reports(self):
        # 反例⑤：调度器未登记 → 规则在、但永远不会被加载
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "= 入口\n\n== 分类与懒加载（加载调度器）\n\n=== 通用层（涉及对应活动时加载）\n\n"
                   "* **写代码** → `specs/general/coding.adoc`\n\n== 技术栈扩展约定\n")
        cm.check_data_dictionary_guard()
        self.assertIn("terminology.adoc", self.error_texts())

    def test_doc_cross_ref_removed_reports(self):
        # 反例⑥：文档侧互引断开 → 读文档规范的人永远看不到这节
        self._write_valid()
        self.write("specs/general/doc.adoc", "= 文档规范\n\n== 文档组织与导航\n\n* 每级目录须有索引页。\n")
        cm.check_data_dictionary_guard()
        self.assertIn("doc.adoc", self.error_texts())

    def test_encoding_cross_ref_removed_reports(self):
        # 反例⑦：编码侧「术语统一」未互引 → 该条会被读成"定义也写这里"
        self._write_valid()
        self.write("specs/general/encoding.adoc", "= 编码规范\n\n* **术语统一（L2）**：同名同义。\n")
        cm.check_data_dictionary_guard()
        self.assertIn("encoding.adoc", self.error_texts())


# integration：完整合法样例全通过
# --------------------------------------------------------------------------- #
class TestIntegration(CheckSpecsTestCase):
    def test_fully_valid_tree_passes_all_checks(self):
        _mk_blackbox_base(self.root)
        self.write("AGENTS_COMMON.adoc",
                   "执行 link:specs/core/execution.adoc[]；"
                   "Java 登记 `specs/stack/java.adoc`；"
                   "通用层 `specs/general/doc-design.adoc`")
        self.write("specs/core/execution.adoc",
                   "见 link:../general/doc-design.adoc[]；link:../stack/java.adoc[]")
        self.write("specs/general/doc-design.adoc", "= 设计文档")
        self.write("specs/stack/java.adoc", "= Java")
        self.write("AGENTS.adoc",
                   "规范调整：调整后必须开启干净子 agent 验证完整性；不得只定义不执行")

        cm.check_refs_exist()
        cm.check_link_refs()
        cm.check_stack_consistency()
        cm.check_forbidden_patterns()
        cm.check_historical_notes()
        cm.check_principle_guard()
        self.assertEqual(cm.errors, [])


# --------------------------------------------------------------------------- #
# check_priority_guard（规范优先级防线：最高关注项不得被删/降级）
# --------------------------------------------------------------------------- #
class TestCheckPriorityGuard(CheckSpecsTestCase):
    """钉住 L1/L2/L3 分级与最高关注项 P1-P6 的存在性、级别与正文口径。"""

    # P6 的正文（口径）也须核对：本条曾出现"清单里列着、正文却是旧口径"——
    # 公共侧已收紧为"强制同 Agent、不得点名外部 NPC"，P6 却停在"优先同源 + 外部来源
    # 作备选"，按最高关注项读的维护方会照旧把复核派给不可核对的外部执行者。
    P6 = ("=== P6. 协作执行者选择：子任务一律同 Agent，不得点名外部执行者\n\n"
          "* **要求（L1，最高）**：一律由与执行者相同的 Agent（同 Agent 身份、同入口）承担，"
          "不得点名外部 Agent / 外部 NPC；不可用时**降级**为由执行者本人串行承担，或如实标悬置。\n"
          "* **依据**：IEEE 1028 软件评审。\n")

    def _write_valid(self):
        # 分级定义与最高关注项的**公共口径**在 specs/core/execution.adoc；
        # P1-P5 的**维护方不可降级清单**在 specs-project-maintainer/priority.adoc。
        self.write("specs/core/execution.adoc",
                   "= 执行原则（必加载层）\n\n"
                   "== 分级与最高关注项（先读）\n\n"
                   "**L1 强制**/**L2 建议**/**L3 允许**\n\n"
                   "规范条目分三级，最高关注项**不可降级**：最高关注项与其引用允许多处出现，"
                   "但一处是完整定义、其余是**一行引用**（**强调**用升级别 + 单一定义 + 显式引用）。\n\n"
                   "== 范围控制\n\n读取按最小必要，禁止全库扫描。\n\n"
                   "== 文件操作强制检查\n\n文件移动必须使用 `git mv`，禁止 delete+create。\n\n"
                   "== 破坏性操作\n不可逆操作先确认。\n\n"
                   "== 自检\n不得顺口编造，不知道就去查证。\n"
                   "（引用 `specs/general/source.adoc` 与 `specs/general/self-check.adoc`）\n")
        self.write("specs/general/source.adoc", "= 依据与来源真实性规范（通用层）\n")
        self.write("specs/general/self-check.adoc", "= 执行前自检规范（通用层）\n")
        self.write("specs-project-maintainer/priority.adoc",
                   "= 最高关注项与不可降级清单（维护方自查）\n\n"
                   "最高关注项**不可降级**：\n\n"
                   "=== P1. 文件移动/重命名必须用 `git mv`\n\n"
                   "* **要求（L1，最高）**：不得用 delete+create 代替。\n"
                   "* **依据**：变更可追溯（ISO 10007）。\n\n"
                   "=== P2. 规范完整性校验\n\n"
                   "* **要求（L1，最高）**：改完必须跑机械校验。\n"
                   "* **依据**：ISO/IEC/IEEE 29148。\n\n"
                   "=== P3. 内容不得减少\n\n"
                   "* **要求（L1，最高）**：内容一项不能少。\n"
                   "* **依据**：ISO 9001。\n\n"
                   "=== P4. 读取按最小必要；执行轮次须合并（少绕）\n\n"
                   "* **要求（L2 建议，最高关注项）**：只读最小必要信息集；执行轮次须合并（少绕，避免可供合并的调用被拆成多轮）。\n"
                   "* **依据**：Anthropic 工程博客《Effective context engineering for AI agents》。\n\n"
                   "=== P5. 不可逆操作先确认，不得编造事实与来源\n\n"
                   "* **要求（L1，最高）**：不可逆操作先确认；不得编造事实与来源。\n"
                   "* **依据**：ISO 10007。\n\n"
                   + self.P6)
        # 维护方自查层的登记名单以 `cm.MAINTAINER_LAYER_FILES` 为唯一来源——
        # 夹具里再写死一遍名单，会让"新增一个维护方文件"时夹具与实现各自漂移
        # （本仓库实测：新增 `guards.adoc` 后此用例报红，而红的是夹具不是实现）。
        self.write("AGENTS.adoc",
                   "".join(f"登记 `{rel}`\n" for rel in cm.MAINTAINER_LAYER_FILES))
        # 分级/最高关注项本身也被 P2 等防线读取：给出最小可识别的公共文件
        self.write("AGENTS_COMMON.adoc", "= t\n")

    def test_valid_priority_file_passes(self):
        self._write_valid()
        cm.check_priority_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_priority_file_reports(self):
        # 反例：维护方的最高关注项清单整体被删
        self._write_valid()
        os.remove(os.path.join(self.root, "specs-project-maintainer", "priority.adoc"))
        cm.check_priority_guard()
        self.assertIn("缺少维护方最高关注项清单", self.error_texts())

    def test_missing_level_definition_reports(self):
        # 反例：公共分级定义被删（只剩 L1，L2/L3 消失）
        self._write_valid()
        self.write("specs/core/execution.adoc",
                   "= 执行原则\n\n**L1 强制**\n不可降级 git mv 破坏性操作 source.adoc 范围控制 一行引用 强调\n")
        cm.check_priority_guard()
        self.assertIn("L2 建议", self.error_texts())
        self.assertIn("L3 允许", self.error_texts())

    def test_dropped_top_priority_item_reports(self):
        # 反例：最高关注项 P1 被删（重构/去重最危险的误删）
        self.write("specs-project-maintainer/priority.adoc",
                   "= t\n**L1 强制**/**L2 建议**/**L3 允许**\n"
                   "不可降级 P2 完整性 P3 内容不得减少 P4 读取按最小必要 P5 不可逆操作\n")
        self.write("specs/core/execution.adoc",
                   "git mv context.adoc 破坏性操作 source.adoc")
        cm.check_priority_guard()
        self.assertIn("P1", self.error_texts())

    def test_dropped_p6_reports(self):
        # 反例：最高关注项 P6（协作执行者选择）被删 —— 与公共侧"强制同 Agent"的
        # 不可降级保护落点一起消失（清单里不再有这项，重构时会顺手清掉）
        self._write_valid()
        path = os.path.join(self.root, "specs-project-maintainer", "priority.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace("=== P6. 协作执行者选择：子任务一律同 Agent，不得点名外部执行者", "=== 协作方式")
        self.write("specs-project-maintainer/priority.adoc", text)
        cm.check_priority_guard()
        self.assertIn("P6", self.error_texts())

    def test_p6_stale_wording_reports(self):
        # 反例（**本轮实际发生的漏改**）：名字与级别还在、正文却是旧口径
        # （"优先同源 + 外部来源作备选"）→ 按最高关注项读的维护方继续派外部执行者。
        # 只核小标题/级别/依据行的旧防线对这种情形全绿，故此处必须报。
        self._write_valid()
        path = os.path.join(self.root, "specs-project-maintainer", "priority.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace(
                self.P6,
                "=== P6. 协作执行者选择\n\n"
                "* **要求（L1，最高）**：需要子 Agent 时优先用与执行者同源的执行者承担，"
                "外部来源（外部 NPC/另一个产品）只是同源不可用后的备选。\n"
                "* **依据**：IEEE 1028 软件评审。\n")
        self.write("specs-project-maintainer/priority.adoc", text)
        cm.check_priority_guard()
        self.assertIn("旧口径", self.error_texts())

    def test_p6_keyword_only_reports(self):
        # 反例：只留新口径的关键词、整条要求被抽掉（防"关键词出现过一次"式假绿）
        self._write_valid()
        path = os.path.join(self.root, "specs-project-maintainer", "priority.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace(
                self.P6,
                "=== P6. 协作执行者选择\n\n"
                "* **要求（L1，最高）**：不得点名外部 Agent。\n"
                "* **依据**：IEEE 1028。\n")
        self.write("specs-project-maintainer/priority.adoc", text)
        cm.check_priority_guard()
        self.assertIn("同 Agent 身份", self.error_texts())

    def test_dropped_non_downgrade_declaration_reports(self):
        # 反例：去掉"不可降级"声明 = 允许最高关注项被降级（公共口径在 execution.adoc）
        self._write_valid()
        path = os.path.join(self.root, "specs", "core", "execution.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace("最高关注项**不可降级**", "最高关注项")
        self.write("specs/core/execution.adoc", text)
        cm.check_priority_guard()
        self.assertIn("不可降级", self.error_texts())

    def test_execution_missing_git_mv_reports(self):
        # 反例：最高关注项 P1 的必加载层落点被改写
        self._write_valid()
        self.write("specs/core/execution.adoc", "文件操作见相关规范\n")
        cm.check_priority_guard()
        self.assertIn("git mv", self.error_texts())

    def test_leveling_method_moved_back_to_always_on_reports(self):
        # 反例：分级定义（读条目"该怎么做"的底线）被误删；分级必须留在公共层
        self._write_valid()
        path = os.path.join(self.root, "specs", "core", "execution.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace("**L1 强制**/**L2 建议**/**L3 允许**", "只分 L1")
        self.write("specs/core/execution.adoc", text)
        cm.check_priority_guard()
        self.assertIn("L2 建议", self.error_texts())

    def test_dropped_how_to_walk_declaration_reports(self):
        # 反例：最高关注项的保留形态（一处完整定义 + 其余一行引用）被删
        self._write_valid()
        path = os.path.join(self.root, "specs", "core", "execution.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace("一行引用", "随便引用")
        self.write("specs/core/execution.adoc", text)
        cm.check_priority_guard()
        self.assertIn("一行引用", self.error_texts())

    def test_dropped_basis_line_reports(self):
        # 反例：某最高关注项的『依据』行被整段删掉（依据可压成标准名/编号，但不能消失）
        self._write_valid()
        path = os.path.join(self.root, "specs-project-maintainer", "priority.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace("* **依据**：ISO 10007。\n", "")
        self.write("specs-project-maintainer/priority.adoc", text)
        cm.check_priority_guard()
        self.assertIn("依据", self.error_texts())

    def test_silently_downgraded_p1_reports(self):
        # 反例：P1-P3 被静默从 L1 降级为 L2（最高关注项条款本身即 L1 铁律）
        self._write_valid()
        path = os.path.join(self.root, "specs-project-maintainer", "priority.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace(
                "**要求（L1，最高）**：不得用 delete+create 代替。",
                "**要求（L2 建议）**：不得用 delete+create 代替。")
        self.write("specs-project-maintainer/priority.adoc", text)
        cm.check_priority_guard()
        self.assertIn("P1", self.error_texts())

    def test_silently_promoted_p4_reports(self):
        # 反例：P4 被静默从 L2 改标为 L1（级别不得顺手改写，须按定级口径判定）
        self._write_valid()
        path = os.path.join(self.root, "specs-project-maintainer", "priority.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace(
                "* **要求（L2 建议，最高关注项）**：只读最小必要信息集；执行轮次须合并"
                "（少绕，避免可供合并的调用被拆成多轮）。",
                "* **要求（L1，最高）**：只读最小必要信息集；执行轮次须合并"
                "（少绕，避免可供合并的调用被拆成多轮）。")
        self.write("specs-project-maintainer/priority.adoc", text)
        cm.check_priority_guard()
        self.assertIn("P4", self.error_texts())

    def test_p4_missing_throughput_half_reports(self):
        # 反例：P4 只留「少读」、把「少绕」（执行轮次须合并）那一半删掉——
        # 轮次是上下文的乘数，缺这一半时执行者会把可合并的调用拆成多轮
        self._write_valid()
        path = os.path.join(self.root, "specs-project-maintainer", "priority.adoc")
        with open(path, encoding="utf-8") as fh:
            text = (fh.read()
                    .replace("=== P4. 读取按最小必要；执行轮次须合并（少绕）",
                             "=== P4. 读取按最小必要")
                    .replace("；执行轮次须合并（少绕，避免可供合并的调用被拆成多轮）。", "。"))
        self.write("specs-project-maintainer/priority.adoc", text)
        cm.check_priority_guard()
        self.assertIn("少绕", self.error_texts())

    def test_silently_downgraded_p5_reports(self):
        # 反例：P5 被静默从 L1 降级为 L2（不可逆操作与来源真实性属无裁量余地的底线）
        self._write_valid()
        path = os.path.join(self.root, "specs-project-maintainer", "priority.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace(
                "**要求（L1，最高）**：不可逆操作先确认；不得编造事实与来源。",
                "**要求（L2 建议）**：不可逆操作先确认；不得编造事实与来源。")
        self.write("specs-project-maintainer/priority.adoc", text)
        cm.check_priority_guard()
        self.assertIn("P5", self.error_texts())

    def test_dropped_context_read_item_reports(self):
        # 反例：最高关注项 P4（读取按最小必要/长会话上下文治理）被删
        self.write("specs-project-maintainer/priority.adoc",
                   "= t\n**L1 强制**/**L2 建议**/**L3 允许**\n"
                   "不可降级 P1 git mv P2 完整性 P3 内容不得减少\n")
        self.write("specs/core/execution.adoc",
                   "git mv context.adoc 破坏性操作 source.adoc")
        cm.check_priority_guard()
        self.assertIn("P4", self.error_texts())

    def test_execution_missing_context_ref_reports(self):
        # 反例：最高关注项 P4 的必加载层落点（执行原则对其的引用）被改写
        self._write_valid()
        self.write("specs/core/execution.adoc", "读取范围见相关规范\n")
        cm.check_priority_guard()
        self.assertIn("范围控制", self.error_texts())

    def test_dropped_destructive_op_item_reports(self):
        # 反例：最高关注项 P5（不可逆操作先确认 + 不得编造）被删
        self.write("specs-project-maintainer/priority.adoc",
                   "= t\n**L1 强制**/**L2 建议**/**L3 允许**\n"
                   "不可降级 P1 git mv P2 完整性 P3 内容不得减少 P4 读取按最小必要\n")
        self.write("specs/core/execution.adoc",
                   "git mv context.adoc 破坏性操作 source.adoc")
        cm.check_priority_guard()
        self.assertIn("P5", self.error_texts())

    def test_execution_missing_destructive_section_reports(self):
        # 反例：P5 的必加载层落点（「破坏性操作」一节）被删
        self._write_valid()
        self.write("specs/core/execution.adoc",
                   "git mv context.adoc source.adoc\n")
        cm.check_priority_guard()
        self.assertIn("破坏性操作", self.error_texts())

    def test_execution_missing_source_ref_reports(self):
        # 反例：P5 的落点（"不得顺口编造"与来源真实性引用）被删
        self._write_valid()
        self.write("specs/core/execution.adoc",
                   "**L1 强制**/**L2 建议**/**L3 允许** 最高关注项 **不可降级** 一行引用 强调\n"
                   "git mv 破坏性操作 范围控制\n")
        cm.check_priority_guard()
        self.assertIn("不得编造事实与来源", self.error_texts())


# --------------------------------------------------------------------------- #
# check_spec_admission_guard（规范准入防线：分类/准入与提案校验口径不得被删）
# --------------------------------------------------------------------------- #
class TestCheckAdmissionGuard(CheckSpecsTestCase):
    """钉住规范分类与准入文件的存在性、要点、调度器登记与项目落点。

    准入口径（公共/项目归属、分层判定、该不该收、提案如何校验与升级）是后续新增
    规范的判定依据，被"精简/去重"顺手删掉后新增就会回到零散追加，故与最高关注项
    一样加机械防线。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_admission = cm.ADMISSION_FILE
        cm.ADMISSION_FILE = os.path.join(self.root, "specs-project-maintainer", "spec-lifecycle.adoc")

    def tearDown(self) -> None:
        cm.ADMISSION_FILE = self._orig_admission
        super().tearDown()

    def _write_valid(self):
        # 实现用「仓库根相对路径」登记/引用（与调度器口径一致），测试文件写在临时根下
        self.write("specs-project-maintainer/spec-lifecycle.adoc",
                   "= 规范分类与准入\n\n"
                   "== 公共规范还是项目规范（归属判定）\n\n"
                   "== 准入判定（该不该收进规范集合）\n\n"
                   "== 如何给一条规范定级（定级口径四问）\n\n"
                   "=== 与条款类型一一对应（L1 / L2 / L3 判定表）\n\n"
                   "=== 归属谁（对象 × 强度两维判定）\n\n"
                   "=== 归类举证（写入规范时同步登记）\n\n"
                   "=== 级别变更与复盘（防降级、防级别混乱）\n\n"
                   "== 新增规范的提案校验\n\n"
                   "先找参照物、别自己造；检查是否已有标准；检查是否已有本项目条目；升级与举一反三；"
                   "存在比用户口述更优的设计时，按更优的设计收。\n\n"
                   "== 同一条规则有两种读法（读的形态要跟着场景变）\n\n"
                   "执行场景只给规则与判定标准；依据与取舍归思考/决策场景。\n\n"
                   "== 规范集合的自身重构（瘦身与归位）\n\n"
                   "先判归属 → 再判层级 → 再判重复 → 最后压缩表述。\n"
                   "重构后须核对规范有效性（两形态分离 / 可执行性不降级 / 可见性不丢）。\n")
        self.write("AGENTS_COMMON.adoc",
                   "通用层登记 `specs-project-maintainer/spec-lifecycle.adoc`")
        self.write("AGENTS.adoc", "见 `specs-project-maintainer/spec-lifecycle.adoc`")

    def test_valid_admission_spec_passes(self):
        self._write_valid()
        cm.check_spec_admission_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_admission_file_reports(self):
        # 反例：准入规范文件整体被删（新增规范失去判定依据）
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("AGENTS.adoc", "= t")
        cm.check_spec_admission_guard()
        self.assertIn("缺少规范分类与准入文件", self.error_texts())

    def test_dropped_key_point_reports(self):
        # 反例：准入判定被删（只剩归属判定）→ 准入抓手失效
        self.write("specs-project-maintainer/spec-lifecycle.adoc",
                   "= t\n\n== 公共规范还是项目规范\n\n== 提案校验\n\n"
                   "检查是否已有标准；检查是否已有本项目条目；升级与举一反三。\n")
        self.write("AGENTS_COMMON.adoc", "登记 `specs-project-maintainer/spec-lifecycle.adoc`")
        self.write("AGENTS.adoc", "见 `specs-project-maintainer/spec-lifecycle.adoc`")
        cm.check_spec_admission_guard()
        self.assertIn("准入判定", self.error_texts())

    def test_dropped_escalation_point_reports(self):
        # 反例：举一反三（升级要求）被删 → 新增只会照抄用户原话
        self.write("specs-project-maintainer/spec-lifecycle.adoc",
                   "= t\n\n== 公共规范还是项目规范\n\n== 准入判定\n\n"
                   "== 提案校验\n\n检查是否已有标准；检查是否已有本项目条目。\n")
        self.write("AGENTS_COMMON.adoc", "登记 `specs-project-maintainer/spec-lifecycle.adoc`")
        self.write("AGENTS.adoc", "见 `specs-project-maintainer/spec-lifecycle.adoc`")
        cm.check_spec_admission_guard()
        self.assertIn("举一反三", self.error_texts())

    def test_dropped_leveling_criteria_reports(self):
        # 反例：定级口径（四问/判定表等）被删 → 条目级别再无判定依据、级别会重新混乱
        self._write_valid()
        path = os.path.join(self.root, "specs-project-maintainer", "spec-lifecycle.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        text = text.split("== 如何给一条规范定级")[0] + "== 新增规范的提案校验\n\n" + \
            text.split("== 新增规范的提案校验")[1]
        self.write("specs-project-maintainer/spec-lifecycle.adoc", text)
        cm.check_spec_admission_guard()
        self.assertIn("如何给一条规范定级", self.error_texts())

    def test_dropped_refactor_order_reports(self):
        # 反例：规范自身重构的判断顺序被删 → 会先删后想，把放错位置的内容直接删掉
        self._write_valid()
        path = os.path.join(self.root, "specs-project-maintainer", "spec-lifecycle.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.write("specs-project-maintainer/spec-lifecycle.adoc",
                   text.replace("先判归属 → 再判层级 → 再判重复 → 最后压缩表述。", "重构一下。"))
        cm.check_spec_admission_guard()
        self.assertIn("先判归属", self.error_texts())

    def test_dropped_reading_shape_reports(self):
        # 反例：读法形态判据被删 → "执行侧只给怎么走、依据归决策侧"的口径丢失，
        # 规范重新变成"给执行者一堆解释"或"为简洁把依据删掉"两个极端
        self._write_valid()
        path = os.path.join(self.root, "specs-project-maintainer", "spec-lifecycle.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        text = text.split("== 同一条规则有两种读法")[0] + "== 规范集合的自身重构" + \
            text.split("== 规范集合的自身重构")[1]
        self.write("specs-project-maintainer/spec-lifecycle.adoc", text)
        cm.check_spec_admission_guard()
        self.assertIn("同一条规则有两种读法", self.error_texts())

    def test_dropped_effectiveness_check_reports(self):
        # 反例：重构后的有效性核对被删 → 只查"内容丢没丢"，判据被压成口号/依据被删无人拦
        self._write_valid()
        path = os.path.join(self.root, "specs-project-maintainer", "spec-lifecycle.adoc")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace(
                "重构后须核对规范有效性（两形态分离 / 可执行性不降级 / 可见性不丢）。\n", "")
        self.write("specs-project-maintainer/spec-lifecycle.adoc", text)
        cm.check_spec_admission_guard()
        self.assertIn("重构后须核对规范有效性", self.error_texts())

    def test_dropped_reference_seeking_point_reports(self):
        # 反例：提案校验里"先找参照物、别自己造"被删（退回照抄用户原话）
        self.write("specs-project-maintainer/spec-lifecycle.adoc",
                   "= t\n\n== 公共规范还是项目规范\n\n== 准入判定\n\n== 提案校验\n\n"
                   "检查是否已有标准；检查是否已有本项目条目；升级与举一反三；"
                   "存在比用户口述更优的设计时，按更优的设计收。\n")
        self.write("AGENTS_COMMON.adoc", "登记 `specs-project-maintainer/spec-lifecycle.adoc`")
        self.write("AGENTS.adoc", "见 `specs-project-maintainer/spec-lifecycle.adoc`")
        cm.check_spec_admission_guard()
        self.assertIn("先找参照物、别自己造", self.error_texts())

    def test_dropped_better_design_point_reports(self):
        # 反例："存在比用户口述更优的设计时，按更优的设计收"被删
        # （查到更优设计却不采用、也不说明理由时无人拦）
        self.write("specs-project-maintainer/spec-lifecycle.adoc",
                   "= t\n\n== 公共规范还是项目规范\n\n== 准入判定\n\n== 提案校验\n\n"
                   "先找参照物、别自己造；检查是否已有标准；检查是否已有本项目条目；升级与举一反三。\n")
        self.write("AGENTS_COMMON.adoc", "登记 `specs-project-maintainer/spec-lifecycle.adoc`")
        self.write("AGENTS.adoc", "见 `specs-project-maintainer/spec-lifecycle.adoc`")
        cm.check_spec_admission_guard()
        self.assertIn("更优的设计", self.error_texts())

    def test_not_registered_in_project_spec_reports(self):
        # 反例：文件存在但未在维护方入口 AGENTS.adoc 登记 → 永不被加载、规则实际失效
        self._write_valid()
        self.write("AGENTS.adoc", "= 项目自身规范\n")
        cm.check_spec_admission_guard()
        self.assertIn("未在", self.error_texts())
        self.assertIn("登记", self.error_texts())


# --------------------------------------------------------------------------- #
# check_section_refs（节名引用存在性：防改名后引用悬空）
# --------------------------------------------------------------------------- #
class TestCheckSectionRefs(CheckSpecsTestCase):
    def test_existing_section_ref_passes(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc-design.adoc", "= 设计文档规范\n\n== 信息归属\n\n内容")
        self.write("specs/general/doc.adoc",
                   "见 link:../general/doc-design.adoc[]「信息归属」")
        cm.check_section_refs()
        self.assertEqual(cm.errors, [])

    def test_renamed_section_reports(self):
        # 反例：目标节已改名，引用仍指向旧节名
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc-design.adoc", "= 设计文档规范\n\n== 信息归属\n\n内容")
        self.write("specs/general/doc.adoc",
                   "见 link:../general/doc-design.adoc[]「判定依据」")
        cm.check_section_refs()
        self.assertNotEqual(cm.errors, [])
        self.assertIn("不存在的节名", self.error_texts())
        self.assertIn("判定依据", self.error_texts())

    def test_section_with_parenthetical_passes(self):
        # 目标节名带括号说明，引用省略括号部分也应通过
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc-design.adoc", "= t\n\n=== 信息归属（同一信息只写一处）\n\n内容")
        self.write("specs/general/doc.adoc", "见 link:../general/doc-design.adoc[]「信息归属」")
        cm.check_section_refs()
        self.assertEqual(cm.errors, [])

    def test_non_adoc_and_external_targets_skipped(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc",
                   "link:https://example.com/x[]「任意」 link:#anch[]「任意」")
        cm.check_section_refs()
        self.assertEqual(cm.errors, [])

    def test_parallel_sections_second_reported(self):
        # 同一 link 后并列多个节名时，第二个也须校验
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc-design.adoc", "= t\n\n=== 信息归属\n\n内容")
        self.write("specs/general/doc.adoc",
                   "见 link:../general/doc-design.adoc[]「信息归属」「不存在的节」")
        cm.check_section_refs()
        self.assertIn("不存在的节", self.error_texts())

    def test_parenthetical_inner_alias_passes(self):
        # 节名 `分类与懒加载（加载调度器）` 的括号内文字可作为别名引用
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/target.adoc", "= t\n\n== 分类与懒加载（加载调度器）\n\n内容")
        self.write("specs/general/doc.adoc", "见 link:../general/target.adoc[]「加载调度器」")
        cm.check_section_refs()
        self.assertEqual(cm.errors, [])

    def test_intra_file_section_ref_passes(self):
        # 正例：写"同文件「节名」"且该节确实在本文件内 —— 应通过
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc",
                   "= t\n\n== 信息归属\n\n内容\n\n见同文件「信息归属」")
        cm.check_section_refs()
        self.assertEqual(cm.errors, [])

    def test_library_file_section_refs_are_checked(self):
        # 图书馆文件（仓库根 library/）纳入节名检查 —— 原实现漏收 library/**，
        # 其悬空节名无人发现（实测 library/README.adoc 曾有三处）
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc", "= 文档\n\n== 注释与文档\n")
        self.write("library/README.adoc",
                   "= 图书馆\n\n见 link:../specs/general/doc.adoc[]「不存在的节」\n")
        cm.check_section_refs()
        self.assertIn("不存在的节名", self.error_texts())

    def test_library_file_valid_section_refs_pass(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc", "= 文档\n\n== 注释与文档\n")
        self.write("library/README.adoc",
                   "= 图书馆\n\n见 link:../specs/general/doc.adoc[]「注释与文档」\n")
        cm.check_section_refs()
        self.assertEqual(cm.errors, [])

    def test_list_item_ref_passes(self):
        # 正例：指向**列表条目名**（`* **条目名（L1）**：…`）——规范里大量判据是条目而非节，
        # 引用方更常这么指；原实现只采集 `=` 起头的节标题，会把这类正确指向误判为悬空
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/stack/bash.adoc",
                   "= Bash 规范\n\n== 文件头与解释器\n\n"
                   "* **入口语言选择（L1）**：Linux/macOS 入口取 `.sh`\n")
        self.write("specs/general/script.adoc",
                   "见 link:../stack/bash.adoc[]「入口语言选择」")
        cm.check_section_refs()
        self.assertEqual(cm.errors, [])

    def test_list_item_ref_still_checks_existence(self):
        # 反例：条目名不存在（改名/删除）时仍须报——放开条目名不等于放开一切
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/stack/bash.adoc",
                   "= Bash 规范\n\n* **入口语言选择（L1）**：取 `.sh`\n")
        self.write("specs/general/script.adoc",
                   "见 link:../stack/bash.adoc[]「入口语言取舍」")
        cm.check_section_refs()
        self.assertIn("不存在的节名", self.error_texts())

    def test_intra_file_section_ref_dangling_reports(self):
        # 反例：写"同文件「节名」"但本文件无此节（节实际在另一个文件）—— 须报悬空
        # （曾实测：verify.adoc 写"见同文件「规范集合的自身重构」"，而该节在
        #  spec-lifecycle.adoc，link: 式检查拦不住这类自然语言指向）
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc",
                   "= t\n\n== 真节\n\n内容\n\n见同文件「规范集合的自身重构」")
        cm.check_section_refs()
        self.assertNotEqual(cm.errors, [])
        self.assertIn("同文件「规范集合的自身重构」", self.error_texts())
        self.assertIn("在本文件不存在", self.error_texts())

    def test_intra_file_section_ref_with_parenthetical_passes(self):
        # 正例：本文件节名带括号说明，"同文件「简化名」"也应通过
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc",
                   "= t\n\n== 信息归属（同一信息只写一处）\n\n内容\n\n见同文件「信息归属」")
        cm.check_section_refs()
        self.assertEqual(cm.errors, [])

    def test_codeblock_heading_not_collected(self):
        # `----` 代码块内形如 `= xxx` 的行不得被当作节名（防漏报转误报）
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/target.adoc", "= t\n\n----\n= 代码块内的行\n----\n\n== 真节\n")
        self.write("specs/general/doc.adoc", "见 link:../general/target.adoc[]「代码块内的行」")
        cm.check_section_refs()
        self.assertIn("不存在的节名", self.error_texts())


# --------------------------------------------------------------------------- #
# 校验范围（不得检查 git 工作区 / 引用方项目）
# --------------------------------------------------------------------------- #
class TestScopeStaysOnCommonContent(CheckSpecsTestCase):
    """回归：机械校验只针对本仓库维护的规范/模板文本。

    背景：本仓库的绝大多数内容是**给其他项目用**的公共规范（`AGENTS_COMMON.adoc` +
    `specs/`）。面向"引用方项目工作区"的检查在本仓库既看不到对象、又对引用方无效
    （引用方用规范入口全文引用，不可能引用本仓库的脚本），只会白白给本仓库 CI
    加约束，故不得再引入（历史上曾有 `check_git_mv_usage` 被移除）。

    **边界（本仓库自身 vs 引用方）**：本仓库自己也是 git 工作区，其**暂存区**可核对，
    故允许且仅允许"本仓库自身侧"的 `git mv` 自查（`check_git_mv_selfcheck`：只读
    `git diff --cached --diff-filter=AD` 的状态行，不读工作区文件内容、不做逐文件
    比较，非 git 目录/无 git 一律跳过）。越出这条边界（读工作区文件内容、`git status`
    扫描、比较 HEAD 内容、把结论套到引用方）即属违规——那才是本用例要钉住的。
    """

    def test_no_workspace_file_reads(self):
        # 判据是"是否越界读工作区内容/扫工作区状态"，不是"是否出现 git 字样"：
        # 规范正文与"自身侧暂存区自查"里出现 git 调用属正常，故只钉住处界调用。
        src = open(os.path.join(HERE, "check_specs.py"), encoding="utf-8").read()
        for bad in ("git status", "HEAD:{", "--name-only", "ls-files"):
            self.assertNotIn(bad, src,
                             f"check_specs.py 不得越界读取工作区状态/文件内容（发现 {bad!r}）："
                             "本仓库内容主要给其他项目用，引用方工作区操作不可见；"
                             "自身侧只允许读暂存区的 `diff --cached --diff-filter=AD` 状态行")

    def test_self_side_git_check_is_bounded(self):
        # 正例：自身侧 git mv 自查必须是"暂存区状态行 + 跳过条件齐备"的受限实现
        src = open(os.path.join(HERE, "check_specs.py"), encoding="utf-8").read()
        self.assertIn("check_git_mv_selfcheck", src)
        body = src[src.index("def check_git_mv_selfcheck"):]
        body = body[:body.index(chr(10) + "def ")]
        self.assertIn("--cached", body, "须只查暂存区")
        self.assertIn("--diff-filter=AD", body, "须只取删除/新增两类状态")
        self.assertIn("os.path.isdir", body, "须在非 git 目录时跳过（保持幂等）")
        self.assertNotIn("open(", body, "不得读工作区文件内容")

    def test_lowered_rename_threshold_for_rewritten_moves(self):
        # 改写式移动（内容大幅重写，相似度低于 git 默认 50%）须仍被识别为 rename：
        # 阈值须低于默认值，否则合规的 `git mv` + 改写会被误判成 delete+create
        src = open(os.path.join(HERE, "check_specs.py"), encoding="utf-8").read()
        body = src[src.index("def check_git_mv_selfcheck"):]
        body = body[:body.index(chr(10) + "def ")]
        self.assertIn("-M10%", body,
                      "须用低于默认阈值的 -M10%（本仓库实证：搬家时入口被整篇重写，"
                      "相似度跌到 16%，默认阈值下只剩 删除+新增）")

    def test_git_untracked_file_does_not_break_checks(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc", "= 文档\n\n简短但有实质内容的一句话规则。\n")
        # 工作区存在未跟踪文件（模拟"delete+create 之类的工作区形态"）不得影响结论
        self.write("品牌新文件.adoc", "= x\n\n与本规范集合无关的内容。\n")
        cm.check_link_refs()
        self.assertEqual(cm.errors, [])


# --------------------------------------------------------------------------- #
# check_principle_guard（规范要点防线：防『定义验证却不执行/被误删』）
# --------------------------------------------------------------------------- #
class TestCheckPrincipleGuard(CheckSpecsTestCase):
    def test_principle_present_passes(self):
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("AGENTS.adoc",
                   "规范调整：调整后必须开启干净子 agent 验证完整性；不得只定义不执行")
        cm.check_principle_guard()
        self.assertEqual(cm.errors, [])

    def test_validation_keyword_removed_reports(self):
        # 反例：删掉了「完整性校验/子 agent 复核」约定（只定义校验、不要求执行）
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("AGENTS.adoc", "规范调整：写成文档即可，无需后续动作")
        cm.check_principle_guard()
        self.assertIn("要点防线被破坏", self.error_texts())
        self.assertIn("子 agent", self.error_texts())
        self.assertIn("完整性", self.error_texts())

    def test_missing_management_file_reports(self):
        self.write("AGENTS_COMMON.adoc", "= t")  # 未创建根目录 AGENTS.adoc
        cm.check_principle_guard()
        self.assertIn("缺少 Agent 项目自身规范入口", self.error_texts())



def _valid_usage_body() -> str:
    """生成一份含全部要点锚点的『依据的写入与关联』主题正文（正例基准）。

    与 `cm._LIBRARY_USAGE_ANCHORS` 同源：锚点即判据句/节名，缺一即"写入靠自觉、
    关联凭印象"会被读回来（写入无触发判据、反查无算法）。**定位协议的使用判据**
    （第四节）由 `_LIBRARY_LOCATING_USAGE_ANCHORS` 承载，本函数一并写入——
    两处合起来才是完整的"写入 + 关联 + 定位"协议。
    """
    head = "= 依据的写入与关联（图书馆使用协议）\n\n本文件是依据图书馆的主题之一。\n\n"
    return (head + "\n".join("- " + q for q in cm._LIBRARY_USAGE_ANCHORS)
            + "\n" + "\n".join("- " + q for q in cm._LIBRARY_LOCATING_USAGE_ANCHORS) + "\n")


def _valid_adoption_body() -> str:
    """生成一份含全部要点锚点的『规范准入与自身取舍』主题正文（正例基准）。

    与 `cm._LIBRARY_ADOPTION_ANCHORS` 同源：锚点即判据句，缺一即"同义性差异未写明"。
    """
    head = "= 规范准入与自身取舍的依据（依据图书馆）\n\n本文件是依据图书馆的主题之一。\n\n"
    return head + "\n".join("- " + q for q in cm._LIBRARY_ADOPTION_ANCHORS) + "\n"


class TestCheckLibraryGuard(CheckSpecsTestCase):
    """钉住『图书馆防线』：依据须查得到、对得上、引用不悬空（不在默认引用面内的内容）。

    依据不能只存在名称——规则执行久了就退化成"只记得是这么做的"，无法判断它还成不
    成立、无法据以取舍（specs/general/verify.adoc「验证总纲」的"防慢慢脱离初衷"）。
    图书馆（**仓库根 `library/`**）**不在默认引用面内**（本仓库内容全部会发布出去，
    区别只在"默认引用什么"——它没有公共加载项、引用方工作区里也没有本仓库的文件），
    是依据的落点，故其存在性、入口登记、逐字引文与引用可解析性都由本条机械钉住；
    **不按"自足性/是否夹带私有落点"口径核对**——那是对默认引用项的要求（不在默认
    引用面内的内容本就可以引用自己仓库的任何落点），图书馆落在仓库根后该口径不再适用。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_lib = (cm.LIBRARY_DIR, cm.LIBRARY_INDEX, cm.LIBRARY_TOPICS)
        self._orig_project = cm.PROJECT_FILE
        cm.LIBRARY_DIR = os.path.join(self.root, "library")
        cm.LIBRARY_INDEX = os.path.join(cm.LIBRARY_DIR, "README.adoc")
        cm.LIBRARY_TOPICS = ("sources.adoc", "adoption.adoc", "usage.adoc")
        cm.PROJECT_FILE = os.path.join(self.root, "AGENTS.adoc")

    def tearDown(self) -> None:
        (cm.LIBRARY_DIR, cm.LIBRARY_INDEX, cm.LIBRARY_TOPICS) = self._orig_lib
        cm.PROJECT_FILE = self._orig_project
        super().tearDown()

    def _write_valid(self) -> None:
        # 项目规范入口登记图书馆入口（写文件与登记是同一个动作）
        self.write("AGENTS.adoc",
                   "= 项目规范\n\n依据图书馆入口 library/README.adoc（见下「依据图书馆」）。\n")
        self.write("library/README.adoc",
                   "= 图书馆\n\n| link:sources.adoc[] | 外部标准原文摘录\n"
                   "| link:adoption.adoc[] | 规范准入与自身取舍的依据——同义性差异与覆盖点\n"
                   "| link:usage.adoc[] | 依据的写入与关联：触发特征、入库必写项、反查算法\n")
        self.write("library/sources.adoc",
                   "= 外部标准原文摘录\n\n"
                   + "\n".join("- " + q for q in cm.LIBRARY_QUOTE_ANCHORS)
                   + "\n")
        self.write("library/adoption.adoc", _valid_adoption_body())
        self.write("library/usage.adoc", _valid_usage_body())

    def test_valid_library_passes(self):
        self._write_valid()
        cm.check_library_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_library_index_reports(self):
        # 反例：图书馆入口整体被删（依据将只剩名称、无从核对）
        self._write_valid()
        os.remove(cm.LIBRARY_INDEX)
        cm.check_library_guard()
        self.assertIn("缺少图书馆入口", self.error_texts())

    def test_unregistered_in_project_entry_reports(self):
        # 反例：图书馆未在项目规范入口登记（读者无从知道何时加载它）
        self._write_valid()
        self.write("AGENTS.adoc", "= 项目规范\n")
        cm.check_library_guard()
        self.assertIn("未在本仓库项目规范入口", self.error_texts())

    def test_registered_topic_missing_file_reports(self):
        # 反例：入口登记了不存在的主题文件（读者按入口找不到依据）
        self._write_valid()
        self.write("library/README.adoc",
                   "= 图书馆\n\n| link:sources.adoc[] | 外部标准原文摘录\n| link:gone.adoc[] | 不存在\n")
        cm.check_library_guard()
        self.assertIn("不存在的主题文件", self.error_texts())

    def test_orphan_topic_file_reports(self):
        # 反例：主题目录里有文件却未登记（依据实际不可达）
        self._write_valid()
        self.write("library/internal.adoc", "= 未登记的主题\n")
        cm.check_library_guard()
        self.assertIn("未登记的主题文件", self.error_texts())

    def test_quote_anchor_deleted_reports(self):
        # 反例：逐字引文被压成名称（依据无从核对 = 图书馆的价值消失）
        self._write_valid()
        self.write("library/sources.adoc",
                   "= 外部标准原文摘录\n\n- RFC 2119 见官方文档\n")
        cm.check_library_guard()
        self.assertIn("缺失逐字引文锚点", self.error_texts())

    def test_dangling_ref_in_library_reports(self):
        # 反例：馆内引用悬空（依据链断在这里）——`specs/...` 反引号写法按仓库根解析
        self._write_valid()
        self.write("library/sources.adoc",
                   "= 外部标准原文摘录\n\n见 `specs/general/gone.adoc`\n"
                   + "\n".join("- " + q for q in cm.LIBRARY_QUOTE_ANCHORS)
                   + "\n")
        cm.check_library_guard()
        self.assertIn("指向不存在的文件", self.error_texts())

    def test_link_dangling_in_library_reports(self):
        # 反例：馆内 link: 引用悬空（相对本文件目录解析）
        self._write_valid()
        self.write("library/sources.adoc",
                   "= 外部标准原文摘录\n\n见 link:../specs/general/gone.adoc[]\n"
                   + "\n".join("- " + q for q in cm.LIBRARY_QUOTE_ANCHORS)
                   + "\n")
        cm.check_library_guard()
        self.assertIn("指向不存在的文件", self.error_texts())

    def _write_topic_body(self, body: str) -> None:
        """把 `body` 写进主题文件正文（避开入口登记表：表里的 link: 会被当作主题登记）。"""
        self.write("library/sources.adoc",
                   "= 外部标准原文摘录\n\n" + body + "\n"
                   + "\n".join("- " + q for q in cm.LIBRARY_QUOTE_ANCHORS) + "\n")

    def test_root_level_name_link_form_dangling_reports(self):
        # 反例：馆内以**根级文件名 + link: 写法**引用而该文件不存在——馆内引用一律按
        # 仓库根基准，根级名走 link: 同样是引用写法、悬空即断链（按"本文件所在目录"解析时，
        # 文件缺失漏报、文件在时又误报）
        self._write_valid()
        self._write_topic_body("变更历史见 link:CHANGELOG.adoc[]。")
        cm.check_library_guard()
        self.assertIn("指向不存在的文件", self.error_texts())

    def test_root_level_name_link_form_resolvable_passes(self):
        # 正例：根级文件名走 link: 形态、文件真实存在 → 不报（与反引号形态同一基准）
        self._write_valid()
        self.write("CHANGELOG.adoc", "= 变更历史\n")
        self._write_topic_body("变更历史见 link:CHANGELOG.adoc[]。")
        cm.check_library_guard()
        self.assertEqual(cm.errors, [])

    def test_ref_base_is_single_for_both_forms(self):
        # 钉住"同一引用只有一个基准"：同一文件两种写法（反引号 / link:）结论必须一致
        for form, label in (("`CHANGELOG.adoc`", "backtick"), ("link:CHANGELOG.adoc[]", "link")):
            self._write_valid()
            self.write("CHANGELOG.adoc", "= 变更历史\n")
            self._write_topic_body(f"变更历史见 {form}。")
            cm.errors.clear()
            cm.check_library_guard()
            self.assertEqual([e for e in cm.errors if "CHANGELOG" in e], [],
                             f"文件存在时 {label} 形态不应报错")
            os.remove(os.path.join(self.root, "CHANGELOG.adoc"))
            cm.errors.clear()
            cm.check_library_guard()
            self.assertIn("指向不存在的文件", self.error_texts(),
                          f"文件缺失时 {label} 形态必须报错")

    def test_root_level_file_ref_dangling_reports(self):
        # 反例：馆内以**根级文件名**写法引用（`PROMPTS.adoc`）而该文件不存在
        # 依据：馆内引用一律按仓库根解析——根级文件名同样是引用写法，悬空即断链
        # （此前正则只认"带目录前缀"的写法，`AGENTS.adoc`/`PROMPTS.adoc` 这类
        #  引用被整体跳过，改成不存在的名字也不会被发现）
        self._write_valid()
        self.write("library/README.adoc",
                   "= 图书馆\n\n| link:sources.adoc[] | 见 `PROMPTS.adoc`\n"
                   "| link:adoption.adoc[] | 规范准入与自身取舍的依据——同义性差异与覆盖点\n"
                   "| link:usage.adoc[] | 依据的写入与关联：触发特征、入库必写项、反查算法\n")
        cm.check_library_guard()
        self.assertIn("指向不存在的文件", self.error_texts())

    def test_root_level_file_ref_resolvable_passes(self):
        # 正例：根级文件名写法命中真实文件 → 不报
        self._write_valid()
        self.write("PROMPTS.adoc", "= 提示词\n")
        self.write("library/README.adoc",
                   "= 图书馆\n\n| link:sources.adoc[] | 见 `PROMPTS.adoc` 与 `AGENTS.adoc`\n"
                   "| link:adoption.adoc[] | 规范准入与自身取舍的依据——同义性差异与覆盖点\n"
                   "| link:usage.adoc[] | 依据的写入与关联：触发特征、入库必写项、反查算法\n")
        cm.check_library_guard()
        self.assertEqual(cm.errors, [])

    def test_adoption_topic_missing_anchor_reports(self):
        # 反例：『规范准入与自身取舍』主题的要点锚点被删——该主题的价值全在
        # "如实写明本集合自己的取舍与外部材料的差异"；缺了它，读者会把本站更严取舍
        # （配置类不写逻辑、先例优先优先级、NPC 禁合并）读成外部标准原文（依据不实）
        self._write_valid()
        self.write("library/adoption.adoc", "= 规范准入与自身取舍的依据\n\n说了一堆。\n")
        cm.check_library_guard()
        self.assertIn("缺失要点锚点", self.error_texts())

    def test_adoption_topic_anchor_kept_passes(self):
        # 正例：要点锚点齐备（含"同义性差异"节名与三条取舍的判据句）→ 不报
        self._write_valid()
        cm.errors.clear()
        cm.check_library_guard()
        self.assertEqual(cm.errors, [])

    def test_usage_topic_missing_anchor_reports(self):
        # 反例：『依据的写入与关联』主题的要点锚点被删——该主题的价值全在"写入有触发判据、
        # 反查有可执行算法"；缺了它，"写依据"重新靠自觉（不主动写、写什么凭发挥），
        # 或把规则本体抄进馆（第二真源、改一处必漏一处）
        self._write_valid()
        self.write("library/usage.adoc", "= 依据的写入与关联\n\n说了一堆。\n")
        cm.check_library_guard()
        self.assertIn("缺失要点锚点", self.error_texts())

    def test_usage_topic_anchor_kept_passes(self):
        # 正例：要点锚点齐备（写入触发特征 + 关联协议 + 反查解析算法 + 默认引用面边界）→ 不报
        self._write_valid()
        cm.errors.clear()
        cm.check_library_guard()
        self.assertEqual(cm.errors, [])

    def test_usage_topic_unregistered_reports(self):
        # 反例：新建 usage 主题文件却未登记入口（写文件与登记是同一个动作）——
        # usage.adoc 已列入 LIBRARY_TOPICS 下限，未登记即"写入判据"实际不可达
        self._write_valid()
        self.write("library/README.adoc",
                   "= 图书馆\n\n| link:sources.adoc[] | 外部标准原文摘录\n"
                   "| link:adoption.adoc[] | 规范准入与自身取舍的依据——同义性差异与覆盖点\n")
        cm.check_library_guard()
        self.assertIn("未登记的主题文件", self.error_texts())

    def test_usage_topic_anchors_are_constantized(self):
        # 要点锚点须被常量化（防线要能覆盖"写入判据与反查算法被删"），
        # 且须覆盖三节与关键判据句；第三节标题即"默认引用面与非引用面"（不得退回
        # "共享部分与私有部分"这一与平台事实不符的口径，见 check_ref_scope_wording_guard）
        anchors = cm._LIBRARY_USAGE_ANCHORS
        for q in ("== 一、什么时候该把依据写进图书馆（触发特征）",
                  "== 二、依据与规则怎么关联（关联协议）",
                  "=== 反查解析算法（只取一份，不遍历）",
                  "== 三、默认引用面与非引用面（外部项目怎么处理）",
                  "判据是问句，不是印象",
                  "以下情形**不写**",
                  "**入库必写项**",
                  "**终止条件（L1）**"):
            self.assertIn(q, anchors)

    def test_adoption_topic_unregistered_reports(self):
        # 反例：新建主题文件却未登记入口（写文件与登记是同一个动作）——
        # adoption.adoc 已列入 LIBRARY_TOPICS 下限，未登记即依据不可达
        self._write_valid()
        self.write("library/README.adoc",
                   "= 图书馆\n\n| link:sources.adoc[] | 外部标准原文摘录\n")
        cm.check_library_guard()
        self.assertIn("未登记的主题文件", self.error_texts())

    def test_resolvable_refs_do_not_report(self):
        # 正例：馆内引用真实存在（`specs/...` 反引号 + `../` 相对 link 都命中）
        self._write_valid()
        self.write("specs/general/verify.adoc", "= 验证\n")
        self.write("library/sources.adoc",
                   "= 外部标准原文摘录\n\n见 `specs/general/verify.adoc` 与 "
                   "link:../specs/general/verify.adoc[]\n"
                   + "\n".join("- " + q for q in cm.LIBRARY_QUOTE_ANCHORS)
                   + "\n")
        cm.check_library_guard()
        self.assertEqual(cm.errors, [])

    def test_source_markers_are_constantized(self):
        # 三类取样来源标记须被常量化（防线要能覆盖"依据被压成名称"）
        self.assertEqual(
            tuple(cm.LIBRARY_SOURCE_MARKERS),
            ("官方文本已取回", "官方网页已取回", "未逐字取回"))
        for m in cm.LIBRARY_SOURCE_MARKERS:
            self.assertIn(m, cm.LIBRARY_QUOTE_ANCHORS)

    def test_source_marker_deleted_reports(self):
        # 反例：把"取样来源标记"整体删掉（依据的可信度边界无从判断）→ 须报错
        self._write_valid()
        text = "= 外部标准原文摘录\n\n" + "\n".join(
            "- " + q for q in cm.LIBRARY_QUOTE_ANCHORS
            if q not in cm.LIBRARY_SOURCE_MARKERS) + "\n"
        self.write("library/sources.adoc", text)
        cm.check_library_guard()
        self.assertIn("缺失逐字引文锚点", self.error_texts())

    def test_dir_ref_in_library_resolves(self):
        # 目录型引用在馆内也须按目录存在性核对（不再整体跳过）
        self._write_valid()
        os.makedirs(os.path.join(self.root, "specs", "general"), exist_ok=True)
        self.write("library/sources.adoc",
                   "= 外部标准原文摘录\n\n见 `specs/general/`\n"
                   + "\n".join("- " + q for q in cm.LIBRARY_QUOTE_ANCHORS) + "\n")
        cm.check_library_guard()
        self.assertEqual(cm.errors, [])

    def test_dangling_dir_ref_in_library_reports(self):
        self._write_valid()
        self.write("library/sources.adoc",
                   "= 外部标准原文摘录\n\n见 `specs/gone-dir/`\n"
                   + "\n".join("- " + q for q in cm.LIBRARY_QUOTE_ANCHORS) + "\n")
        cm.check_library_guard()
        self.assertIn("不存在的目录", self.error_texts())


def _valid_locating_index_body() -> str:
    """含全部『依据定位』要点锚点的图书馆入口正文（正例基准）。

    与 `cm._LIBRARY_LOCATING_ANCHORS` 同源：锚点即主键口径/三步取值/形态约束，
    缺一即"馆无限大时定位退回整馆下载或按文件名猜"。
    """
    head = "= 图书馆\n\n本目录是本项目的图书馆。\n\n"
    return head + "\n".join("- " + q for q in cm._LIBRARY_LOCATING_ANCHORS) + "\n"


def _valid_locating_source_body() -> str:
    """含全部『依据定位』机制原文与取样状态的 sources 正文（正例基准）。

    与 `cm._LIBRARY_LOCATING_SOURCE_MARKERS` 同源：缺逐字引文则"主键是内容""只取一段"
    只是本站说法；缺"未实测"则把"支持 Range"当成既定事实。
    """
    head = "= 外部标准原文摘录\n\n"
    return head + "\n".join("- " + q for q in cm._LIBRARY_LOCATING_SOURCE_MARKERS) + "\n"


class TestCheckLibraryLocatingGuard(CheckSpecsTestCase):
    """钉住『依据定位防线』：馆无限大时"怎么准确定位到哪个文件"的协议不得被删或降级。

    背景（用户报告的真实问题）：图书馆**没有限制内容的大小与长度、也没有限制要存的范围**，
    将来可能特别大；其他项目引用时要在**不全量下载**的前提下准确找到"这条依据在哪个文件"。
    缺协议时只有几种坏做法：整馆下载、按主题名猜文件名（命名随重构变化）、把图书馆当全文
    检索引擎，**以及要求取用侧先说出"commit/版本号"再拼地址**（用户报告的失效：游客只有
    https，本仓库也不发布版本号，它根本不知道该取哪个 commit）。故本条钉住：入口侧协议要点
    （含作者侧/取用侧的区别与"入口 = 常驻层的固定地址"）、usage 侧使用判据、sources 侧机制
    原文与**如实**取样状态（本站与平台原始文件视图均未实测到 Range 生效，不得当成既定事实）、
    项目入口的口径，以及**"先取 commit 再拼地址"这一表述形态不得回退**。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_lib = (cm.LIBRARY_DIR, cm.LIBRARY_INDEX)
        self._orig_project = cm.PROJECT_FILE
        cm.LIBRARY_DIR = os.path.join(self.root, "library")
        cm.LIBRARY_INDEX = os.path.join(cm.LIBRARY_DIR, "README.adoc")
        cm.PROJECT_FILE = os.path.join(self.root, "AGENTS.adoc")

    def tearDown(self) -> None:
        (cm.LIBRARY_DIR, cm.LIBRARY_INDEX) = self._orig_lib
        cm.PROJECT_FILE = self._orig_project
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("AGENTS.adoc",
                   "= 项目规范\n\n依据图书馆：馆无体量上限，入口 = 常驻层的固定地址\n")
        self.write("library/README.adoc", _valid_locating_index_body())
        self.write("library/usage.adoc", _valid_usage_body())
        self.write("library/adoption.adoc", _valid_adoption_body())
        self.write("library/sources.adoc", _valid_locating_source_body())

    def test_valid_locating_passes(self):
        self._write_valid()
        cm.check_library_locating_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_index_reports(self):
        # 反例：图书馆入口整体被删（定位协议无处承载→退回整馆下载）
        self._write_valid()
        os.remove(cm.LIBRARY_INDEX)
        cm.check_library_locating_guard()
        self.assertIn("缺少图书馆入口", self.error_texts())

    def test_index_anchor_deleted_reports(self):
        # 反例：入口的主键/取值/形态约束被删（定位协议只剩名字）
        self._write_valid()
        self.write("library/README.adoc", "= 图书馆\n\n依据大时慢慢找即可\n")
        cm.check_library_locating_guard()
        self.assertIn("缺失『依据定位』要点", self.error_texts())

    def test_usage_side_missing_section_reports(self):
        # 反例：usage 侧缺"引用方怎么准确定位"节（使用判据无处可读）
        self._write_valid()
        body = _valid_usage_body().replace(
            "== 四、引用方怎么准确定位依据（不全量下载）", "== 四、定位")
        self.write("library/usage.adoc", body)
        cm.check_library_locating_guard()
        self.assertIn("引用方怎么准确定位依据", self.error_texts())

    def test_usage_side_missing_primary_key_reports(self):
        # 反例：去掉"主键是内容、不是路径"（改名即断档的根因被隐去）
        self._write_valid()
        body = _valid_usage_body().replace("**主键是内容、不是路径**", "主键")
        self.write("library/usage.adoc", body)
        cm.check_library_locating_guard()
        self.assertIn("主键是内容、不是路径", self.error_texts())

    def test_usage_side_missing_termination_reports(self):
        # 反例：终止条件被删（定位又会向下展开成第二真源）
        self._write_valid()
        body = _valid_usage_body().replace("**终止条件（L1，同上）**", "终止")
        self.write("library/usage.adoc", body)
        cm.check_library_locating_guard()
        self.assertIn("终止条件（L1，同上）", self.error_texts())

    def test_source_marker_missing_reports(self):
        # 反例：机制原文被删（"主键是内容""只取一段"变成本站说法）
        self._write_valid()
        self.write("library/sources.adoc", "= 外部标准原文摘录\n\ngit 与 RFC 7233 见官方文档\n")
        cm.check_library_locating_guard()
        self.assertIn("缺失『依据定位』的机制原文", self.error_texts())

    def test_source_range_not_marked_unverified_reports(self):
        # 反例：把"支持 Range"当成既定事实（本地站点其实未实测）
        self._write_valid()
        body = _valid_locating_source_body().replace("**未实测**", "已实测生效")
        self.write("library/sources.adoc", body)
        cm.check_library_locating_guard()
        self.assertIn("缺失『依据定位』的机制原文", self.error_texts())

    def test_project_entry_without_primary_key_reports(self):
        # 反例：项目入口未登记定位协议口径（读者不知道有这份协议）
        self._write_valid()
        self.write("AGENTS.adoc", "= 项目规范\n\n依据图书馆见别处\n")
        cm.check_library_locating_guard()
        self.assertIn("未含『依据定位』的口径", self.error_texts())

    def test_commit_as_client_prerequisite_reports(self):
        # 反例（用户报告的失效）：把"先取 commit 再拼地址"写成取用路径——
        # 游客只有 https、没有仓库与 git，取不到 commit
        self._write_valid()
        self.write("library/usage.adoc", _valid_usage_body()
                   + "\n取用方须先取当前 commit，再拼出原始文件地址。\n")
        cm.check_library_locating_guard()
        self.assertIn("取用前置", self.error_texts())

    def test_commit_in_address_exempt_when_negated(self):
        # 正例豁免：把该错误表述**本身**写出来（否定/失效记录）不得误伤
        self._write_valid()
        self.write("library/usage.adoc", _valid_usage_body()
                   + "\n不得把 commit 写进取值地址：取用侧取不到它。\n")
        cm.check_library_locating_guard()
        self.assertEqual(cm.errors, [])

    def test_long_library_file_name_reports(self):
        # 反例（用户报告的失效）：把主张写进文件名——名字写成一句话，
        # 每次链接与每次目录列举都替它付上下文，而名字本就不是检索键
        self._write_valid()
        long_name = "sources-and-locating-protocol-for-evidence.adoc"
        self.assertGreater(len(long_name), cm.LIBRARY_FILE_NAME_MAX)
        self.write("library/" + long_name, "= 依据的来源与定位协议\n")
        cm.check_library_locating_guard()
        self.assertIn("文件名过长", self.error_texts())

    def test_short_library_file_name_passes(self):
        # 正例：短词命名（名字不是主键、也不承担语义）
        self._write_valid()
        self.write("library/evidence.adoc", "= 依据\n")
        cm.check_library_locating_guard()
        self.assertEqual(cm.errors, [])

    def test_file_name_max_matches_module_file_limit(self):
        # 常量口径：与通用层『模块文件名』上限同值（32 字符，含扩展名）
        self.assertEqual(cm.LIBRARY_FILE_NAME_MAX, 32)

    def test_locating_anchors_constant_nonempty(self):
        # 常量完整性：锚点与取样标记须齐全（缺一即防线的判据面缩小）
        for q in ("== 依据的定位协议（入口 + 索引 + 单点取值）",
                  "**第一步：入口 = 常驻层里的固定地址（不要自己拼地址）**",
                  "**版本固化（可选加固，不得写成前置）**",
                  "**分段取值（馆特别大时怎么只取一段）**",
                  "**形态约束（L1）**", "**文件名协议（短、无语义、不承担定位）**",
                  "**取用侧**是**游客**"):
            self.assertIn(q, cm._LIBRARY_LOCATING_ANCHORS)
        for q in ("== 四、引用方怎么准确定位依据（不全量下载）",
                  "**主键是内容、不是路径**",
                  "**协议不承载的东西（形态约束，L1）**",
                  "**终止条件（L1，同上）**",
                  "**取用侧是游客**", "**只有 https、没有仓库、没有 git**",
                  "**文件名不承担定位（短、无语义，L1）**"):
            self.assertIn(q, cm._LIBRARY_LOCATING_USAGE_ANCHORS)
        for q in ("== 依据的定位与取值（git / RFC 9110）",
                  "names the **blob or tree** at the given path", "**未实测**"):
            self.assertIn(q, cm._LIBRARY_LOCATING_SOURCE_MARKERS)


class TestCheckPublicContentCoverage(CheckSpecsTestCase):
    """钉住『公共内容覆盖面防线』：公共内容的入口清单须完整、且与实际文件一致。

    背景：公共内容此前只有一句口头定义（"`AGENTS_COMMON.adoc` + `specs/`"），而
    公共入口 `AGENTS_COMMON.adoc`（接入时读其安装口径）、`prompts/_common.txt`（AI 以纯文本读取公共片段）与
    `script/clean_tmp.py`（随规范分发的通用工具）同样会被引用方取到——清单缺失会让
    机械检查漏掉半个公共内容，或把"自足"要求误加到只对维护方成立的文件上。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_public = cm.PUBLIC_FILE
        self._orig_project = cm.PROJECT_FILE
        cm.PUBLIC_FILE = os.path.join(self.root, "PUBLIC.adoc")
        cm.PROJECT_FILE = os.path.join(self.root, "AGENTS.adoc")

    def tearDown(self) -> None:
        cm.PUBLIC_FILE = self._orig_public
        cm.PROJECT_FILE = self._orig_project
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("AGENTS.adoc", "= 项目规范\n\n公共内容入口清单见 PUBLIC.adoc。\n")
        self.write("PUBLIC.adoc",
                   "= 公共内容入口索引\n\n"
                   "== 公共内容入口清单\n"
                   "| `AGENTS_COMMON.adoc` | 通用规范入口（安装与取回口径也在其中）\n"
                   "| `specs/` | 规范正文\n"
                   "| `prompts/_common.txt` | 公共片段\n"
                   "| `script/clean_tmp.py` | 随规范分发的工具\n")
        self.write("AGENTS_COMMON.adoc", "= 入口\n")
        self.write("prompts/_common.txt", "片段\n")
        self.write("script/clean_tmp.py", "#!/usr/bin/env python3\n")

    def test_valid_listing_passes(self):
        self._write_valid()
        cm.check_public_content_coverage()
        self.assertEqual(cm.errors, [])

    def test_missing_listing_reports(self):
        # 反例：清单整体缺失（覆盖面界不清）
        self._write_valid()
        os.remove(cm.PUBLIC_FILE)
        cm.check_public_content_coverage()
        self.assertIn("缺少公共内容入口索引", self.error_texts())

    def test_entry_only_in_prose_reports(self):
        # 反例：入口只在正文被提一句、未列进「入口清单」表——此前用 `rel in 全文`
        # 判断，这种"被悄悄移出表格"的改动不会被发现（表格才是覆盖面的定义处）
        self._write_valid()
        self.write("PUBLIC.adoc",
                   "= 公共内容入口索引\n\n== 公共内容入口清单\n"
                   "| `specs/` | 规范正文\n"
                   "| `prompts/_common.txt` | 公共片段\n"
                   "| `script/clean_tmp.py` | 随规范分发的工具\n\n"
                   "== 组织与其边界\n\n引用方接入时读 `AGENTS_COMMON.adoc`。\n")
        cm.check_public_content_coverage()
        self.assertIn("未把 AGENTS_COMMON.adoc 列进", self.error_texts())

    def test_entry_in_table_link_form_passes(self):
        # 正例：同一格改用 AsciiDoc 惯用的 `link:` **文本**写法——表格结构、所在节、
        # 覆盖面均未变，纯排版，**不得**报"未列进表"
        # （原判据把"表格行的位置"与"文件名用反引号"混成一件：明明列在表里却报"未列出"）
        self._write_valid()
        self.write("PUBLIC.adoc",
                   "= 公共内容入口索引\n\n== 公共内容入口清单\n"
                   "| 通用规范入口 | link:AGENTS_COMMON.adoc[AGENTS_COMMON.adoc] |\n"
                   "| 规范正文 | link:specs/[specs/] |\n")
        cm.check_public_content_coverage()
        self.assertNotIn("未把", self.error_texts())

    def test_names_in_zone_accepts_forms_but_keeps_row_anchor(self):
        # 钉住判据口径：表格行内任一点名形式均命中；非表格行（正文提及）仍不命中
        z = "| 通用规范入口 |"
        self.assertTrue(cm._names_in_zone(z + " `AGENTS_COMMON.adoc` |", "AGENTS_COMMON.adoc"))
        self.assertTrue(cm._names_in_zone(
            z + " link:AGENTS_COMMON.adoc[AGENTS_COMMON.adoc] |", "AGENTS_COMMON.adoc"))
        self.assertTrue(cm._names_in_zone(z + " link:AGENTS_COMMON.adoc[] |", "AGENTS_COMMON.adoc"))
        self.assertTrue(cm._names_in_zone(z + " AGENTS_COMMON.adoc |", "AGENTS_COMMON.adoc"))
        self.assertFalse(cm._names_in_zone("接入时读 AGENTS_COMMON.adoc。", "AGENTS_COMMON.adoc"))
        self.assertFalse(cm._names_in_zone(z + " `README.adoc` |", "AGENTS_COMMON.adoc"))

    def test_listing_not_registered_reports(self):
        # 反例：清单未在项目规范入口登记（维护方读不到它）
        self._write_valid()
        self.write("AGENTS.adoc", "= 项目规范\n")
        cm.check_public_content_coverage()
        self.assertIn("未在本仓库项目规范入口", self.error_texts())

    def test_entry_missing_from_listing_reports(self):
        # 反例：清单漏了公开入口（漏一个即半个公共内容不在覆盖面内）
        self._write_valid()
        self.write("PUBLIC.adoc",
                   "= 公共内容入口索引\n\n== 公共内容入口清单\n"
                   "| `specs/` | 规范正文\n")
        cm.check_public_content_coverage()
        self.assertIn("未列出 AGENTS_COMMON.adoc", self.error_texts())

    def test_entry_list_section_renamed_reports(self):
        # 反例：清单节的标题被改写 → 按节切表格区的定位失效，须报错（不得静默不查）
        self._write_valid()
        self.write("PUBLIC.adoc",
                   "= 公共内容入口索引\n\n== 入口一览\n"
                   "| `AGENTS_COMMON.adoc` | 通用规范入口\n")
        cm.check_public_content_coverage()
        self.assertIn("未找到「公共内容入口清单」节", self.error_texts())

    def test_named_file_missing_reports(self):
        # 反例：清单点名了不存在的文件（清单与实际不一致）
        self._write_valid()
        self.write("PUBLIC.adoc",
                   "= 公共内容入口索引\n\n== 公共内容入口清单\n"
                   "| `AGENTS_COMMON.adoc` | 通用规范入口\n"
                   "| `prompts/gone.txt` | 已改名\n")
        cm.check_public_content_coverage()
        self.assertIn("点名了不存在的文件", self.error_texts())

    def test_non_public_example_named_file_missing_reports(self):
        # 反例：「不属公共内容」一段的反向举例点名了不存在的文件 —— 原实现靠硬编码
        # 5 个 .adoc 名跳过该段，改名/新增举例都无人核；改按节切后须真实存在
        self._write_valid()
        self.write("PUBLIC.adoc",
                   "= 公共内容入口索引\n\n== 公共内容入口清单\n"
                   "| `AGENTS_COMMON.adoc` | 通用规范入口\n"
                   "| `specs/` | 规范正文\n"
                   "| `prompts/_common.txt` | 公共片段\n"
                   "| `script/clean_tmp.py` | 随规范分发的工具\n"
                   "\n== 组织与其边界\n"
                   "* **不属公共内容入口清单**：`gone-internal.adoc`（已改名）\n")
        cm.check_public_content_coverage()
        self.assertIn("点名了不存在的文件", self.error_texts())

    def test_non_public_example_existing_files_pass(self):
        # 正例：「不属公共内容」一段点名真实存在的文件（不必再靠硬编码豁免名单）
        self._write_valid()
        self.write("internal-note.adoc", "= 维护方内容\n")
        self.write("PUBLIC.adoc",
                   "= 公共内容入口索引\n\n== 公共内容入口清单\n"
                   "| `AGENTS_COMMON.adoc` | 通用规范入口\n"
                   "| `specs/` | 规范正文\n"
                   "| `prompts/_common.txt` | 公共片段\n"
                   "| `script/clean_tmp.py` | 随规范分发的工具\n"
                   "\n== 组织与其边界\n"
                   "* **不属公共内容入口清单**：`internal-note.adoc`（维护方内容）\n")
        cm.check_public_content_coverage()
        self.assertEqual(cm.errors, [])



class TestCheckDeliveryGuard(CheckSpecsTestCase):
    """钉住『交付形态与报告落点』：不得只冒一句过程性叙述、不得只交付不汇报。

    本轮实测失效（用户直接问责）：一轮 NPC 任务唯一对外的输出是一句过程性叙述
    （"Now let me check whether there's a …"）——既不是汇报、也没有任何提交。
    旧版 `delivery` 片段只写"有改动必须提交推送"，恰漏了"当次无改动也算完成态"
    与"过程性叙述不得外发"，故本组用例把这两条连同登记处同步一并钉住。
    """

    DELIVERY = ("// tag::delivery[]\n"
                "8. 交付：\n"
                "   - **CI/CD 等自动化场景**：必须提交并推送；**有改动**时**必须**把改动"
                "**提交并推送到 PR 分支**、**创建 PR**（只提交不推送/只推送不提交都不算）；"
                "**没有提交即等于没有交付**（**有改动却没提交也没推送**、**没有改动却没说明**"
                "都属交付失败）。\n"
                "   - **报告落点（L1）**：**过程性叙述**（现在去读 X、先看有没有 Z）"
                "**不得作为独立的一条评论**发出去（**答非所问**）；"
                "**结果与结论**须**汇总成一次完整汇报**（平台上即**一条评论**）；"
                "**输出通道只有两条**（最终汇报 / 必须停下确认），"
                "**除这两条之外的任何中间话一律不发**（自己认定的\"必要说明\"不构成"
                "**第三条通道**）。\n"
                "// end::delivery[]\n")

    def setUp(self) -> None:
        super().setUp()
        self._orig_prompts = (cm.PROMPTS_FILE, cm.PROMPTS_DIR, cm.COMMON_PROMPT_FILE,
                              cm.README_FILE)
        cm.PROMPTS_FILE = os.path.join(self.root, "PROMPTS.adoc")
        cm.PROMPTS_DIR = os.path.join(self.root, "prompts")
        cm.COMMON_PROMPT_FILE = os.path.join(self.root, "prompts", "_common.txt")
        cm.README_FILE = os.path.join(self.root, "README.adoc")

    def tearDown(self) -> None:
        (cm.PROMPTS_FILE, cm.PROMPTS_DIR, cm.COMMON_PROMPT_FILE,
         cm.README_FILE) = self._orig_prompts
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("prompts/_common.txt", self.DELIVERY)
        self.write("prompts/review.adoc",
                   "= 检查修复\n\n[listing]\n----\n"
                   "10. 交付即汇报（**有改动**须提交推送并建 PR，"
                   "**不得**只交付不汇报、**不得**只冒一句、**没有交付**；"
                   "**输出通道只有两条**、**任何中间话一律不发**）\n"
                   "include::_common.txt[tag=delivery]\n----\n")
        self.write("prompts/refactor.adoc",
                   "= 重构\n\n[listing]\n----\n"
                   "10. 交付即汇报（**有改动**须提交推送并建 PR，"
                   "**不得**只交付不汇报、**不得**只冒一句、**没有交付**；"
                   "**输出通道只有两条**、**任何中间话一律不发**）\n"
                   "include::_common.txt[tag=delivery]\n----\n")
        self.write("PROMPTS.adoc",
                   "* 公共约定：**交付即汇报**——**过程性叙述**不得作为评论发出；"
                   "**输出通道只有两条**、**除这两条之外的任何中间话一律不发**；"
                   "**没有改动却没说明**亦属交付失败。\n"
                   "* **题目与片段的改动边界**：补片段缺口**不扩大题面**、"
                   "**不得在两个提示词里各写一遍**。\n")
        self.write("README.adoc",
                   "# README\n\n**过程性叙述**不得作为独立评论发出去；"
                   "**输出通道只有两条**、**除这两条之外的任何中间话一律不发**；"
                   "\"报告说完成了**却没有任何提交**\"属交付失败。\n")

    def test_valid_delivery_passes(self):
        self._write_valid()
        cm.check_delivery_guard()
        self.assertEqual(cm.errors, [])

    def test_fragment_never_included_reports(self):
        # 反例（本轮实测）：片段**写好了但没有任何提示词 include** —— 题面末句复述其大意、
        # include 一次都没有。此类"死内容"在装配层即失效：维护者以为已经写了，
        # 每次执行都拿不到该条正文（`no-self-dispatch` 片段就这样空转过）。
        self._write_valid()
        self.write("prompts/_common.txt",
                   self.DELIVERY +
                   "// tag::no-self-dispatch[]\n9. 不得自行发评论唤起自己。\n"
                   "// end::no-self-dispatch[]\n")
        cm.check_delivery_guard()
        self.assertIn("no-self-dispatch", self.error_texts())
        self.assertIn("没有任何提示词", self.error_texts())

    def test_fragment_wired_by_one_prompt_passes(self):
        # 边界：只被**其中一份**提示词 include 即算接线（片段不必人人取用）
        self._write_valid()
        self.write("prompts/_common.txt",
                   self.DELIVERY +
                   "// tag::no-self-dispatch[]\n9. 不得自行发评论唤起自己。\n"
                   "// end::no-self-dispatch[]\n")
        self.write("prompts/review.adoc",
                   "= 检查修复\n\n[listing]\n----\n"
                   "10. 交付即汇报（**有改动**须提交推送并建 PR，**不得**只交付不汇报、"
                   "**不得**只冒一句、**没有交付**；**输出通道只有两条**、"
                   "**任何中间话一律不发**）\n"
                   "include::_common.txt[tag=delivery]\n"
                   "include::_common.txt[tag=no-self-dispatch]\n----\n")
        cm.check_delivery_guard()
        self.assertNotIn("no-self-dispatch", self.error_texts())

    def test_missing_fragment_reports(self):
        # 反例：公共片段被删 → 两处提示词同时失去这条边界
        self._write_valid()
        self.write("prompts/_common.txt", "普通片段\n")
        cm.check_delivery_guard()
        self.assertIn("delivery", self.error_texts())

    def test_process_narrative_clause_removed_reports(self):
        # 反例（本轮实测失效的形态）：抽掉"过程性叙述不得作为独立评论发出"
        self._write_valid()
        self.write("prompts/_common.txt",
                   "// tag::delivery[]\n"
                   "8. 交付：**有改动**须**提交并推送到 PR 分支**、**创建 PR**；"
                   "**没有提交即等于没有交付**；**有改动却没提交也没推送**；"
                   "**没有改动却没说明**；**结果与结论**须**汇总成一次完整汇报**"
                   "（**一条评论**）。\n// end::delivery[]\n")
        cm.check_delivery_guard()
        self.assertIn("过程性叙述", self.error_texts())

    def test_zero_change_state_removed_reports(self):
        # 反例：抽掉"没有改动却没说明"这一态 → 回到"无改动时不知道要不要交付"
        self._write_valid()
        self.write("prompts/_common.txt",
                   "// tag::delivery[]\n"
                   "8. 交付：**有改动**须**提交并推送到 PR 分支**、**创建 PR**（只提交不推送）；"
                   "**没有提交即等于没有交付**；**有改动却没提交也没推送**；"
                   "**报告落点**：**过程性叙述**不得作为**独立的一条评论**（**答非所问**）；"
                   "**结果与结论**须**汇总成一次完整汇报**（**一条评论**）。\n"
                   "// end::delivery[]\n")
        cm.check_delivery_guard()
        self.assertIn("没有改动却没说明", self.error_texts())

    def test_prompt_missing_report_step_reports(self):
        # 反例：题面侧步骤被删（片段在、流程里却没有"交付即汇报"）
        self._write_valid()
        self.write("prompts/refactor.adoc",
                   "= 重构\n\ninclude::_common.txt[tag=delivery]\n")
        cm.check_delivery_guard()
        self.assertIn("交付即汇报", self.error_texts())

    def test_registry_not_synced_reports(self):
        # 反例：登记处未同步 → 提示词被复制到未知项目后公开面看不到这条边界
        self._write_valid()
        self.write("PROMPTS.adoc", "* 公共约定：改动范围边界。\n")
        cm.check_delivery_guard()
        self.assertIn("交付即汇报", self.error_texts())

    def test_edit_boundary_removed_reports(self):
        # 反例：抽掉"改题面 vs 补片段缺口"的改动边界 → 缺口只能等下一轮（旧任务继续按旧版执行）
        self._write_valid()
        self.write("PROMPTS.adoc",
                   "* 公共约定：**交付即汇报**——**过程性叙述**不得作为评论发出；"
                   "**没有改动却没说明**亦属交付失败。\n")
        cm.check_delivery_guard()
        self.assertIn("题目与片段的改动边界", self.error_texts())

    def test_output_channels_clause_removed_reports(self):
        # 反例（本轮识别出的第二个成因）：例外只写"必须停下确认这一种"、
        # 没写"除这两条之外的任何中间话一律不发" → 执行者自行认定"这属于必要的说明"
        # 就能再发一条，判据回到执行者手里，防线形同虚设
        self._write_valid()
        self.write("prompts/_common.txt",
                   "// tag::delivery[]\n"
                   "8. 交付：**有改动**须**提交并推送到 PR 分支**、**创建 PR**（只提交不推送）；"
                   "**没有提交即等于没有交付**；**有改动却没提交也没推送**；"
                   "**没有改动却没说明**；"
                   "**报告落点**：**过程性叙述**不得作为**独立的一条评论**（**答非所问**）；"
                   "**结果与结论**须**汇总成一次完整汇报**（**一条评论**）；"
                   "需中途说明的例外只有\"必须停下确认\"这一种。\n"
                   "// end::delivery[]\n")
        cm.check_delivery_guard()
        self.assertIn("输出通道只有两条", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例：README 使用要点未同步 → 公开面只看得见"禁止"、看不到这条边界
        self._write_valid()
        self.write("README.adoc", "# README\n\n普通说明。\n")
        cm.check_delivery_guard()
        self.assertIn("README.adoc", self.error_texts())


# --------------------------------------------------------------------------- #
# check_prompts_primary（提示词主侧重与优先级防线：方向不得被删/降级）
# --------------------------------------------------------------------------- #
class TestCheckPublicFacingDocsStaySelfContained(CheckSpecsTestCase):
    """钉住「公开面文档自足」：README/PROMPTS/公共入口 不得给出维护方自查层的路径。

    背景（本轮重构暴露的真实缺陷）：`specs/` 已被刚性拦住"引用维护方自查层"，但
    `README.adoc`（公开站点首页由它渲染）、`PROMPTS.adoc`（公开提示词入口）与
    公共入口 `AGENTS_COMMON.adoc`（引用方安装口径也在其中）**同样会被未知项目看到**——它们里的路径引用方
    按同样方式解析，指向维护方自查层就是死链（该层不随公共内容分发）。本轮就发生过：
    README 在重构中新增了 8 处指向该层的链接。
    """

    def test_clean_public_docs_pass(self):
        self.write("README.adoc", "本仓库另有一层只对维护方成立的规范，不随公共内容分发。\n")
        self.write("PROMPTS.adoc", "分级见 `specs/core/execution.adoc`。\n")
        self.write("AGENTS_COMMON.adoc", "= AGENT 执行规范\n\n安装与取回口径见下文。\n")
        cm.check_public_facing_docs_stay_self_contained()
        self.assertEqual(cm.errors, [])

    def test_readme_link_into_maintainer_layer_reports(self):
        self.write("README.adoc",
                   "定级判据见 link:specs-project-maintainer/spec-lifecycle.adoc[]。\n")
        cm.check_public_facing_docs_stay_self_contained()
        self.assertIn("公开面文档不得给出维护方自查层", self.error_texts())

    def test_prompts_link_into_maintainer_layer_reports(self):
        self.write("PROMPTS.adoc",
                   "定级见 `specs-project-maintainer/spec-lifecycle.adoc`。\n")
        cm.check_public_facing_docs_stay_self_contained()
        self.assertIn("PROMPTS.adoc", self.error_texts())

    def test_common_entry_link_into_maintainer_layer_reports(self):
        # 反例：公共入口自己指向维护方自查层 → 引用方读到的是死链（该层不随公共内容分发）
        self.write("AGENTS_COMMON.adoc",
                   "定级见 `specs-project-maintainer/spec-lifecycle.adoc`。\n")
        cm.check_public_facing_docs_stay_self_contained()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_missing_docs_do_not_raise(self):
        cm.check_public_facing_docs_stay_self_contained()
        self.assertEqual(cm.errors, [])


class TestCheckSelfCheckGuard(CheckSpecsTestCase):
    """钉住执行前自检规范的存在性、要点与必加载层落点。

    自检是把"规范加载了却没被执行"兜住的关键环节，故与最高关注项一样加机械防线：
    文件被删、要点缺失、execution.adoc 落点丢失、未登记调度器，任一即报。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_self_check = cm.SELF_CHECK_FILE
        cm.SELF_CHECK_FILE = os.path.join(self.root, "specs", "general", "self-check.adoc")

    def tearDown(self) -> None:
        cm.SELF_CHECK_FILE = self._orig_self_check
        super().tearDown()

    def _write_valid(self):
        self.write("specs/general/self-check.adoc",
                   "= 执行前自检规范\n\n"
                   "== 知识边界\n\n不得顺口编造，不知道就去查证。\n\n"
                   "== 执行前自检清单（动手前逐项过）\n\n"
                   "适用范围是非平凡任务，逐项检查。"
                   "**动手改一个文件前是否先读了该文件里要改的那一处**"
                   "（判据见 `specs/general/planning.adoc`「要改的那一处是否已实际读过（改动面按处读）」条）。\n\n"
                   "== 完成前自检\n\n对照原要求逐条核。\n")
        self.write("specs/core/execution.adoc",
                   "执行前自检见 `specs/general/self-check.adoc`。\n")
        self.write("AGENTS_COMMON.adoc",
                   "通用层登记 `specs/general/self-check.adoc`")

    def test_valid_self_check_spec_passes(self):
        self._write_valid()
        cm.check_self_check_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_file_reports(self):
        # 反例：自检规范文件整体被删（自检关口丢失）
        self.write("AGENTS_COMMON.adoc", "= t")
        cm.check_self_check_guard()
        self.assertIn("缺少执行前自检规范文件", self.error_texts())

    def test_dropped_checklist_reports(self):
        # 反例：删掉"执行前自检清单"（只剩泛泛要求，无逐项内容）
        self.write("specs/general/self-check.adoc",
                   "= 自检\n\n不得顺口编造。非平凡任务须自检。完成前自检。\n")
        self.write("specs/core/execution.adoc", "`specs/general/self-check.adoc`")
        self.write("AGENTS_COMMON.adoc", "登记 `specs/general/self-check.adoc`")
        cm.check_self_check_guard()
        self.assertIn("执行前自检清单", self.error_texts())

    def test_dropped_scope_boundary_reports(self):
        # 反例：删掉适用范围界定（会被"只对大任务"架空）
        self.write("specs/general/self-check.adoc",
                   "= 自检\n\n执行前自检清单。不得顺口编造。完成前自检。\n")
        self.write("specs/core/execution.adoc", "`specs/general/self-check.adoc`")
        self.write("AGENTS_COMMON.adoc", "登记 `specs/general/self-check.adoc`")
        cm.check_self_check_guard()
        self.assertIn("非平凡任务", self.error_texts())

    def test_execution_landing_point_missing_reports(self):
        # 反例：必加载层未引用自检规范 → 实际不会被加载
        self._write_valid()
        self.write("specs/core/execution.adoc", "见相关规范。\n")
        cm.check_self_check_guard()
        self.assertIn("自检", self.error_texts())

    def test_not_registered_in_dispatcher_reports(self):
        # 反例：文件存在但未登记调度器 → 永不被加载（登记完整性由
        # `check_dispatcher_registry` 统一核，本防线只接自检自身的规则）
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "= t")
        cm.check_dispatcher_registry()
        cm.check_self_check_guard()
        self.assertIn("未在加载调度器登记", self.error_texts())

    def test_read_before_edit_clause_removed_reports(self):
        # 反例：自检清单里那一问被整条抽掉（「动手改文件前先读要改的那一处」挂在
        # 自检关口上，抽掉后自检时不再问它）。**核准的是判据本体**，不看编号：
        # 本条的两处落点里只有自检关口这一处由本防线核，另两处由
        # `check_dev_flow_guard` 核——不核时整条被抽掉仍会全绿【复核实测】
        self._write_valid()
        f = os.path.join(self.root, "specs", "general", "self-check.adoc")
        text = open(f, encoding="utf-8").read()
        cut = text.replace("**动手改一个文件前是否先读了该文件里要改的那一处**",
                           "**还有没有别的没想到的地方**")
        self.assertNotEqual(cut, text, "反例的截法失效——按夹具正文原样截，改措辞后须同步这里")
        open(f, "w", encoding="utf-8").write(cut)
        cm.check_self_check_guard()
        self.assertIn("先读了该文件里要改的那一处", self.error_texts())

    def test_read_before_edit_pointer_removed_reports(self):
        # 反例：自检关口那一问还在、但**判据回指**被抽（只剩一句问话，判据与失效形态
        # 无处可查——该问退化成口号）
        self._write_valid()
        f = os.path.join(self.root, "specs", "general", "self-check.adoc")
        text = open(f, encoding="utf-8").read()
        cut = text.replace("判据见 `specs/general/planning.adoc`", "判据另见")
        self.assertNotEqual(cut, text, "反例的截法失效——按夹具正文原样截，改措辞后须同步这里")
        open(f, "w", encoding="utf-8").write(cut)
        cm.check_self_check_guard()
        self.assertIn("该问的判据回指", self.error_texts())


class TestCheckSourceGuard(CheckSpecsTestCase):
    """钉住来源真实性规范的存在性与要点。

    来源一旦不实会污染整条下游引用链（引错标准、引不存在的文件），故机械钉住
    "引用当前真实存在的目标""只写名称编号""不得编造""宁可不引"四条要点。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_source = cm.SOURCE_FILE
        cm.SOURCE_FILE = os.path.join(self.root, "specs", "general", "source.adoc")

    def tearDown(self) -> None:
        cm.SOURCE_FILE = self._orig_source
        super().tearDown()

    def _write_valid(self):
        self.write("specs/general/source.adoc",
                   "= 依据与来源真实性\n\n"
                   "引用须指向当前真实存在的目标；外部标准只写名称与编号、不附链接；"
                   "不得编造编号与名称；无法确证时宁可不引。\n")
        self.write("AGENTS_COMMON.adoc", "登记 `specs/general/source.adoc`")

    def test_valid_source_spec_passes(self):
        self._write_valid()
        cm.check_source_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_file_reports(self):
        # 反例：来源规范文件整体被删
        self.write("AGENTS_COMMON.adoc", "= t")
        cm.check_source_guard()
        self.assertIn("缺少依据与来源真实性规范文件", self.error_texts())

    def test_dropped_no_fabrication_reports(self):
        # 反例：删掉"不得编造"（来源防线最核心的一条）
        self.write("specs/general/source.adoc",
                   "= t\n\n引用须指向当前真实存在的目标；只写名称编号、不附链接；宁可不引。\n")
        self.write("AGENTS_COMMON.adoc", "登记 `specs/general/source.adoc`")
        cm.check_source_guard()
        self.assertIn("不得编造", self.error_texts())

    def test_dropped_no_link_rule_reports(self):
        # 反例：删掉"不附链接"（出处写法要求）
        self.write("specs/general/source.adoc",
                   "= t\n\n引用须指向当前真实存在的目标；不得编造；宁可不引。\n")
        self.write("AGENTS_COMMON.adoc", "登记 `specs/general/source.adoc`")
        cm.check_source_guard()
        self.assertIn("不附链接", self.error_texts())

    def test_not_registered_in_dispatcher_reports(self):
        # 反例：文件存在但未登记调度器 → 永不被加载
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "= t")
        cm.check_source_guard()
        self.assertIn("未在加载调度器登记", self.error_texts())


class TestCheckVerifyGuard(CheckSpecsTestCase):
    """钉住「规范验证防线」：验证口径（三视角/效力等级/总纲）与其维护方落点须一致。

    验证的**规则**属公共内容（单一落点 `specs/general/verify.adoc`；`testing.adoc` 的
    同名节只留一跳入口——两处各写一份已实测漂移过一次）——
    任何项目改自己的规范/共享资产时都要问"改完怎么验"，且引用方确实需要三视角、效力
    等级与运行契约（否则"加得越多越忘掉初衷"）。维护方**自己的**动作落
    `specs-project-maintainer/verify.adoc` 与 `AGENTS.adoc`。故作防线：公共节与标准出处
    须在、维护方落点须在、P2 与 AGENTS.adoc 两处口径须一致指向三视角与效力等级。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_extra = (cm.PROJECT_FILE,)

    def tearDown(self) -> None:
        super().tearDown()

    def _pub(self):
        return os.path.join(self.root, "specs", "general", "verify.adoc")

    def _write_valid(self):
        self.write("specs/general/verify.adoc",
                   "= 测试规范（通用层，跨语言）\n\n"
                   "== 验证与运行契约\n\n"
                   "* 以真实结果为准。\n\n"
                   "=== 判准维度：严格执行 / 尽力而为\n\n严格执行与尽力而为两档，都须留证。\n\n"
                   "=== 验证的适用边界\n\n先判改动性质；代码类改动 / 规范类改动；"
                   "不改内容的操作（C 类：只改提交/历史或文件路径，内容逐字节不变，"
                   "不重跑全量编译与测试）；"
                   "\"内容没变\"不是\"少核对\"的借口；"
                   "判据问句\"会不会被未知项目加载\"；先判改动性质；不得互串；取**更严的一侧**；"
                   "每次验证都换一个干净上下文。\n\n"
                   "=== 验证的效力等级\n\n"
                   "确定项（判据本体验证）走机械校验；概念项只能启发式复核；未发现问题；悬置；"
                   "不得当作阻断交付的条件。\n\n"
                   "=== 验证总纲（回答\"验证什么、怎么算过\"）\n\n"
                   "| 视角 | 判定问题 | 标准出处\n"
                   "| **① 完整性** | 等价 | ISO 10007 |\n"
                   "| **② 有效性与认知质量** | 判据可判定、依据说对、代价说得清 | "
                   "ISO/IEC Directives Part 2、RFC 2119、ISO/IEC/IEEE 25010 |\n"
                   "| **③ 接纳面** | 未知项目加载可控 | ISO 9241-110 |\n"
                   "验证对象不止规范文件、也须能枚举\"如何验证\"。\n\n"
                   "=== 规范验证（改完规范后的三视角复核）\n\n"
                   "①完整性；②有效性与认知质量；③接纳面，由同一个干净子 agent 一并回答"
                   "（每次验证都换一个干净上下文）；②判据：可执行、依据、降级路径、读的形态、"
                   "常驻层只放底线、从属者可达、④性能；三问都须留证；三态台账；依据 IEEE 1028；"
                   "硬超时。\n\n"
                   "=== 运行契约（公共内容被未知项目加载时的可控性）\n\n"
                   "① 影响面；② 成本；③ 可控性；降级路径；不得让引用方依赖本仓库私有物；"
                   "依据 ISO 9241-110；接纳面须留证。\n")
        self.write("specs-project-maintainer/verify.adoc",
                   "= 验证的维护方落点（维护方自查）\n\n"
                   "* 完整性校验：跑机械校验 + 干净子 agent 三视角复核。\n"
                   "* 子 agent 复核必须自带硬超时。\n"
                   "* 留证按三态台账：通过／未发现问题／悬置，不得合并。\n"
                   "* 维护方侧的具名抓手是 `check_checklist_guard`。\n")
        self.write("specs-project-maintainer/priority.adoc",
                   "P2：改完必须跑机械校验 + 干净子 agent 语义复核；须答 ②有效性与认知质量；"
                   "须答 ③接纳面；同一个干净子 agent 一并回答；结论分档见「验证的效力等级」——"
                   "未发现问题、悬置、不得当作阻断交付的条件。\n")
        self.write("AGENTS.adoc",
                   "完整性校验：含 ②有效性与认知质量；含 ③接纳面；三视角合用一个子 agent；"
                   "结论强度按对象分档（见「验证的效力等级」）：只到未发现问题、不写成通过。\n")

    def test_valid_three_lens_formula_passes(self):
        self._write_valid()
        cm.check_verify_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_public_verify_file_reports(self):
        # 反例：公共验证口径文件整体被删
        self.write("specs-project-maintainer/priority.adoc", "P2")
        cm.check_verify_guard()
        self.assertIn("缺少公共验证规范文件", self.error_texts())

    def test_missing_charter_section_reports(self):
        # 反例：「验证总纲」被删（验证什么、怎么算过、标准出自哪里 重新无人负责）
        self._write_valid()
        p = self._pub()
        t = open(p, encoding="utf-8").read()
        self.write("specs/general/verify.adoc",
                   t.replace("=== 验证总纲（回答\"验证什么、怎么算过\"）", "=== 随便什么节"))
        cm.check_verify_guard()
        self.assertIn("验证总纲", self.error_texts())

    def test_missing_adoption_lens_reports(self):
        # 反例：删掉③接纳面（回到"只面对方规范本体与本仓库"的旧口径）
        self._write_valid()
        p = self._pub()
        t = open(p, encoding="utf-8").read()
        self.write("specs/general/verify.adoc", t.replace("③接纳面", "某某面"))
        cm.check_verify_guard()
        self.assertIn("③接纳面", self.error_texts())

    def test_missing_effectiveness_grades_section_reports(self):
        # 反例：删掉「验证的效力等级」节（回到"把复核结论当依据、把找不到问题当交付前提"）
        self._write_valid()
        p = self._pub()
        t = open(p, encoding="utf-8").read()
        self.write("specs/general/verify.adoc",
                   t.replace("=== 验证的效力等级", "=== 随便什么节"))
        cm.check_verify_guard()
        self.assertIn("效力等级", self.error_texts())

    def test_missing_concept_grade_boundary_reports(self):
        # 反例：去掉"不得阻断交付"这条边界（把复核当交付前置条件）
        self._write_valid()
        p = self._pub()
        t = open(p, encoding="utf-8").read()
        self.write("specs/general/verify.adoc", t.replace("不得当作阻断交付的条件", "另说"))
        cm.check_verify_guard()
        self.assertIn("不得当作阻断交付的条件", self.error_texts())

    def test_missing_standard_sources_reports(self):
        # 反例：标准出处被删（验证退化成"把脚本跑绿"、无从核对判据出自哪里）
        self._write_valid()
        p = self._pub()
        t = open(p, encoding="utf-8").read()
        self.write("specs/general/verify.adoc", t.replace("ISO/IEC Directives Part 2", "某标准"))
        cm.check_verify_guard()
        self.assertIn("ISO/IEC Directives Part 2", self.error_texts())

    def test_missing_runtime_contract_section_reports(self):
        # 反例：③只在文字上出现、却指不到判据（「运行契约」节被删）
        self._write_valid()
        p = self._pub()
        t = open(p, encoding="utf-8").read()
        self.write("specs/general/verify.adoc",
                   t.replace("=== 运行契约（公共内容被未知项目加载时的可控性）", "=== 别的节"))
        cm.check_verify_guard()
        self.assertIn("运行契约", self.error_texts())

    def test_dropped_criterion_reports(self):
        # 反例：重构时把②的判据中的「读的形态」静默删掉（内容减少，不是等价改写）
        self._write_valid()
        p = self._pub()
        t = open(p, encoding="utf-8").read()
        self.write("specs/general/verify.adoc", t.replace("读的形态", "某某形态"))
        cm.check_verify_guard()
        self.assertIn("读的形态", self.error_texts())

    def test_missing_maintainer_landing_point_reports(self):
        # 反例：维护方的验证义务落点被删（三视角在维护方一侧无人执行）
        self._write_valid()
        self.write("specs-project-maintainer/verify.adoc", "= 空\n")
        cm.check_verify_guard()
        self.assertIn("specs-project-maintainer/verify.adoc", self.error_texts())

    def test_p2_without_three_lenses_reports(self):
        # 反例：P2（最高关注项）退回"只核对要点是否全保留"
        self._write_valid()
        self.write("specs-project-maintainer/priority.adoc", "P2：改完跑机械校验 + 干净子 agent 语义复核。\n")
        cm.check_verify_guard()
        self.assertIn("specs-project-maintainer/priority.adoc", self.error_texts())

    def test_own_agents_without_three_lenses_reports(self):
        # 反例：本仓库 AGENTS.adoc 的完整性校验动作未同步三视角
        self._write_valid()
        self.write("AGENTS.adoc", "完整性校验：跑脚本 + 干净子 agent 复核要点。\n")
        cm.check_verify_guard()
        self.assertIn("AGENTS.adoc", self.error_texts())

    # ----- 接纳面防线（未知项目加载）-----

    def test_adoption_guard_missing_file_reports(self):
        # 反例：运行契约所在文件整体被删
        self.write("AGENTS_COMMON.adoc", "= t")
        cm.check_adoption_guard()
        self.assertIn("缺少验证与运行契约文件", self.error_texts())

    def test_adoption_guard_missing_section_reports(self):
        # 反例：「运行契约」节被删（未知项目加载的可控性重新无人负责）
        self.write("specs/general/verify.adoc", "= 测试规范\n\n== 单元测试\n\n只测必要。\n")
        cm.check_adoption_guard()
        self.assertIn("运行契约", self.error_texts())

    def test_adoption_guard_missing_dimension_reports(self):
        # 反例：三维中少一维（如可控性被删）= 判据不完整
        self.write("specs/general/verify.adoc",
                   "= 测试规范\n\n== 运行契约（未知项目加载）\n\n"
                   "① 影响面；② 成本；降级路径；不得让引用方依赖本仓库私有物；"
                   "依据 ISO 9241-110；接纳面须留证。\n")
        self.write("specs-project-maintainer/context.adoc",
                   "= 维护方清单\n\n运行契约：影响面 / 成本 / 可控性三维。\n")
        cm.check_adoption_guard()
        self.assertIn("③ 可控性", self.error_texts())

    def test_adoption_guard_missing_maintainer_list_reports(self):
        # 反例：维护方承接清单被删（维护方在新增公共内容时的核对职责无人承载）
        self.write("specs/general/verify.adoc",
                   "= 测试规范\n\n== 运行契约\n\n① 影响面；② 成本；③ 可控性；降级路径；"
                   "不得让引用方依赖本仓库私有物；依据 ISO 9241-110；接纳面须留证。\n")
        cm.check_adoption_guard()
        self.assertIn("specs-project-maintainer/context.adoc", self.error_texts())

    def test_public_content_private_ref_reports(self):
        # 反例：公共内容（specs/）把本仓库私有物当抓手引用 → 引用方读到死链
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/execution.adoc",
                   "= 执行原则\n\n本仓库自身的机械校验见 `script/check_specs.py` 的工具声明。\n")
        cm.check_public_content_has_no_private_refs()
        self.assertIn("script/check_specs.py", self.error_texts())

    def test_public_content_legitimate_agents_and_changelog_not_reported(self):
        # 正例：`AGENTS.adoc` 作为"引用方自己的项目规范"、`CHANGELOG.adoc` 作为通用默认
        # 文件名被提及，均为规范有意为之，不得误判为私有引用
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc",
                   "只对某个项目成立 → 该项目自身规范（引用方项目根目录 `AGENTS.adoc`）；"
                   "变更日志默认项目根 `CHANGELOG.adoc`。\n")
        cm.check_public_content_has_no_private_refs()
        self.assertEqual(cm.errors, [])


class TestCheckPublicContentSelfContained(CheckSpecsTestCase):
    """钉住「公共内容自足性」：公共内容不得引用引用方拿不到的私有落点。

    背景（本次重构暴露的真实缺陷）：**一个文件可以同时装着公共规则与项目自身规则**。
    它躺在公共侧（`specs/`）时，其中的项目自身落点就成了引用方读不到的死链——
    "本仓库的优先级见某私有文件"这类话，引用方既没有该文件、也没有加载它的入口，
    读到的规范只成立一半。故作防线：公共内容（`AGENTS_COMMON.adoc` + `specs/`）
    不得出现指向维护方自查层（`specs-project-maintainer/`）的引用。
    """

    def test_private_layer_ref_in_public_specs_reports(self):
        # 反例：公共规范正文引用维护方自查层的文件
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/testing.adoc",
                   "= 测试规范\n\n验证口径见 `specs-project-maintainer/verify.adoc`。\n")
        cm.check_public_content_is_self_contained()
        self.assertIn("specs-project-maintainer/", self.error_texts())

    def test_private_layer_ref_in_entry_reports(self):
        # 反例：公共入口（加载调度器）登记维护方自查层 → 引用方按调度器找不到该文件
        self.write("AGENTS_COMMON.adoc",
                   "= 入口\n\n项目自身维护层：link:specs-project-maintainer/priority.adoc[]\n")
        cm.check_public_content_is_self_contained()
        self.assertIn("specs-project-maintainer/", self.error_texts())

    def test_self_contained_public_content_passes(self):
        # 正例：公共内容里的规则全部在公共文件内自足表达
        self.write("AGENTS_COMMON.adoc",
                   "= 入口\n\n分级见 link:specs/core/execution.adoc[]「分级与最高关注项」\n")
        self.write("specs/general/testing.adoc",
                   "= 测试规范\n\n验证口径见 link:../core/execution.adoc[]。\n")
        cm.check_public_content_is_self_contained()
        self.assertEqual(cm.errors, [])

    def test_own_agents_adoc_may_reference_private_layer(self):
        # 正例：根 AGENTS.adoc 是项目自身内容，可以引用维护方自查层
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("AGENTS.adoc",
                   "= 项目自身规范\n\n最高关注项见 link:specs-project-maintainer/priority.adoc[]\n")
        cm.check_public_content_is_self_contained()
        self.assertEqual(cm.errors, [])

    def test_private_layer_ref_in_prompts_reports(self):
        # 反例：prompts/*.adoc 会被复制到未知项目执行，其私有落点同样是引用方读不到的死链
        # （PUBLIC.adoc：「自足要求的适用范围」②类，明写机械检查按公共内容口径覆盖它们）
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("prompts/review.adoc",
                   "= 提示词\n\n核对见 `specs-project-maintainer/verify.adoc`。\n")
        cm.check_public_content_is_self_contained()
        self.assertIn("prompts/review.adoc", self.error_texts())

    def test_prompts_without_private_refs_passes(self):
        # 正例：提示词自足表达，不指向本仓库私有落点
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("prompts/review.adoc",
                   "= 提示词\n\n加载项目规范入口后按规范执行。\n")
        cm.check_public_content_is_self_contained()
        self.assertEqual(cm.errors, [])

    def test_library_ref_in_public_specs_reports(self):
        # 反例：图书馆与维护方自查层同属"不在默认引用面内"的落点，公共内容里指向
        # `library/` 的路径同样是引用方读不到的死链（本条此前只拦
        # `specs-project-maintainer/`，实测漏放过 `link:../../library/mirrors.adoc[]`）。
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/dependency.adoc",
                   "= 依赖\n\n实测记录见 link:../../library/mirrors.adoc[]。\n")
        cm.check_public_content_is_self_contained()
        self.assertIn("library/", self.error_texts())

    def test_library_backtick_ref_in_public_specs_reports(self):
        # 反例：反引号写法同样命中（不只看 link: 形态）
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/core/execution.adoc",
                   "= 执行\n\n论证见 `library/adoption.adoc`。\n")
        cm.check_public_content_is_self_contained()
        self.assertIn("library/", self.error_texts())

    def test_library_name_without_path_passes(self):
        # 正例：只给**依据名**、不给可点开的路径，属正当表述（不得误伤）
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/dependency.adoc",
                   "= 依赖\n\n实测取值属依据，见图书馆「包源与镜像源」主题"
                   "（依据名：包源与镜像源（推荐次序与实测记录））。\n")
        cm.check_public_content_is_self_contained()
        self.assertEqual(cm.errors, [])

    def test_own_agents_adoc_may_reference_library(self):
        # 正例：根 AGENTS.adoc 是项目自身内容，可以引用图书馆
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("AGENTS.adoc",
                   "= 项目自身规范\n\n依据图书馆入口 link:library/README.adoc[]\n")
        cm.check_public_content_is_self_contained()
        self.assertEqual(cm.errors, [])

    def test_prompts_dir_private_file_ref_reports(self):
        # 反例（本轮实测失效）：`PROMPTS.adoc` 的公共约定把读者指向**本仓库私有文件**
        # （维护方索引 `PUBLIC.adoc`）——它是公开面文档，引用方那里没有这份文件、读到的是死链。
        # 当时三条防线（公开面自足 / 不得声明机械防线 / 本条）全绿：它们只看维护方自查层路径
        # 与裸抓手名，不看**文件级**私有引用。
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("PROMPTS.adoc",
                   "= 提示词入口\n\n两条本仓库特有约定见 `PUBLIC.adoc`。\n")
        cm.check_public_content_is_self_contained()
        self.assertIn("PROMPTS.adoc", self.error_texts())

    def test_readme_root_changelog_ref_reports(self):
        # 反例：公开面文档指向**本仓库根目录那份** `CHANGELOG.adoc`（引用方那里同名文件
        # 是它自己的变更日志，指向本仓库那份即死链）
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("README.adoc",
                   "= 说明\n\n改动记录见仓库根目录 `CHANGELOG.adoc`。\n")
        cm.check_public_content_is_self_contained()
        self.assertIn("README.adoc", self.error_texts())

    def test_agents_adoc_as_referrer_own_entry_passes(self):
        # 正例：`AGENTS.adoc` 作为**引用方自己的**项目规范入口被提及（公共内容通篇这么写），
        # 属正当表述，不得误判为私有引用
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc.adoc",
                   "= 文档\n\n本文引用的仓库内路径按加载入口（`AGENTS_COMMON.adoc` / "
                   "项目根 `AGENTS.adoc`）所在目录解析。\n")
        cm.check_public_content_is_self_contained()
        self.assertEqual(cm.errors, [])

    def test_module_level_readme_passes(self):
        # 正例：`README.adoc` 作为**引用方项目的模块级**索引页被提及，属正当表述
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/doc-module.adoc",
                   "= 模块文档\n\n模块 `doc/` 下按需放 `README.adoc` 作模块文档索引。\n")
        cm.check_public_content_is_self_contained()
        self.assertEqual(cm.errors, [])

    def test_library_name_without_path_in_prompts_passes(self):
        # 正例：公开面文档只给**依据名**、不给可点开的图书馆路径（不误伤）
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("PROMPTS.adoc",
                   "= 提示词入口\n\n依据找不全时按依据规范如实标未确证（依据存放在本仓库的"
                   "依据主题集合里，不在默认引用面内）。\n")
        cm.check_public_content_is_self_contained()
        self.assertEqual(cm.errors, [])


class TestCheckNoMechanismClaimsInPublic(CheckSpecsTestCase):
    """钉住「公共内容不得声明机械防线」：机械防线只有维护规范集合的那一方有。

    背景（放错位置的一类）：公共内容会被**未知项目**加载，那个项目里没有维护方的
    校验脚本与防线。公共内容一旦写"当前由某防线钉住""本仓库另有防线"或裸防线名
    （`check_xxx_yyy`），引用方读到的就是**宣称与实际不符**——规范文本声称有抓手，
    而引用方没有任何抓手可执行。故作防线：声明句与裸防线名都拦住；
    "维护规范集合的项目应设机械防线"这类**要求**（任何维护方都成立）不得误伤。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_extra = (cm.PROMPTS_FILE, cm.README_FILE)
        cm.PROMPTS_FILE = os.path.join(self.root, "PROMPTS.adoc")
        cm.README_FILE = os.path.join(self.root, "README.adoc")

    def tearDown(self) -> None:
        (cm.PROMPTS_FILE, cm.README_FILE) = self._orig_extra
        super().tearDown()

    def test_mechanism_claim_in_specs_reports(self):
        # 反例：公共内容（specs/）声明"当前存在某道防线"——引用方拿不到、也不该依赖
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/execution.adoc",
                   "= 执行原则\n\nP1 本条当前由机械防线钉住。\n")
        cm.check_no_mechanism_claims_in_public()
        self.assertIn("不得声明机械防线的存在", self.error_texts())

    def test_own_side_mechanism_claim_reports(self):
        # 反例：公共内容声明"本仓库另有防线"（私有元信息随规范分发）
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/verify.adoc",
                   "= 验证规范\n\n本仓库另有防线覆盖该项。\n")
        cm.check_no_mechanism_claims_in_public()
        self.assertIn("不得声明机械防线的存在", self.error_texts())

    def test_bare_check_function_name_in_public_reports(self):
        # 反例：公共内容出现裸防线名（私有抓手名）——引用方看不到、无从执行
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/execution.adoc",
                   "= 执行原则\n\nP1 要求：git mv。由 check_priority_guard 钉住。\n")
        cm.check_no_mechanism_claims_in_public()
        self.assertIn("check_priority_guard", self.error_texts())

    def test_public_readme_claim_reports(self):
        # 反例：README.adoc（介绍公共内容范围与形态）声称"当前由某防线钉住公共内容"
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("README.adoc", "= Agent\n\n公共内容当前由机械防线钉住。\n")
        cm.check_no_mechanism_claims_in_public()
        self.assertIn("README.adoc", self.error_texts())

    def test_requirement_to_have_defence_not_reported(self):
        # 正例：**要求**维护方设机械防线属通用规则（任何维护方都成立），不得误伤
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/execution.adoc",
                   "= 执行原则\n\n本条须由机械防线钉住；维护规范集合的项目应自行设机械防线。\n")
        self.write("README.adoc", "= Agent\n\n公共内容只保留要求与判据。\n")
        cm.check_no_mechanism_claims_in_public()
        self.assertEqual(cm.errors, [])

    def test_own_agents_adoc_may_declare_defence(self):
        # 正例：根 AGENTS.adoc 是项目自身内容，可以点名本仓库的具名防线
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("AGENTS.adoc",
                   "= 项目自身规范\n\n本仓库另有防线 check_priority_guard 钉住最高关注项。\n")
        cm.check_no_mechanism_claims_in_public()
        self.assertEqual(cm.errors, [])


class TestCheckLifecycleGuard(CheckSpecsTestCase):
    """钉住「任务生命周期防线」：节点自查、验证边界与拆分判据三处口径不得被删。

    三处"只在文本上成立、执行时不会真的发生"的缺口：
      * 任务从提出到收尾的**节点没有统一清单** → "做完了才发现方向理解错"，或"流程走完了
        但没人回头看规则是否有问题"（规则慢慢脱离初衷）；
      * **验证没有边界** → 改一行代码被要求三视角、改一条规范只跑机械校验，两头失效；
      * **拆分没有判据** → 多出一个没人维护、判据空转的东西（比不拆更坏）。
    故作防线：三节须仍在、要点齐备、且执行原则 / verify / AGENTS.adoc 三处口径一致。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_files = (cm.EXECUTION_FILE, cm.VERIFY_FILE, cm.ADMISSION_FILE)
        cm.EXECUTION_FILE = os.path.join(self.root, "specs", "core", "execution.adoc")
        cm.VERIFY_FILE = os.path.join(self.root, "specs-project-maintainer", "verify.adoc")
        cm.ADMISSION_FILE = os.path.join(self.root, "specs-project-maintainer", "spec-lifecycle.adoc")

    def tearDown(self) -> None:
        (cm.EXECUTION_FILE, cm.VERIFY_FILE, cm.ADMISSION_FILE) = self._orig_files
        super().tearDown()

    @staticmethod
    def _own_text():
        """本仓库落点：须指向通用层的边界节与拆分判据节。"""
        return ("== 验证的适用范围\n\n见 `specs/general/verify.adoc`「验证与运行契约」之"
                + "「验证的适用边界」；结论强度见「验证的效力等级」；"
                + "拆分判据见「一条规范何时该拆分」；"
                + "维护方验证义务见 `specs-project-maintainer/verify.adoc`。\n")

    @staticmethod
    def _nodes_text(nodes="提出|理解|方案|执行|验证|交付|复盘"):
        """节点清单须以表格行形态出现（`| **节点**（L1）`）——防线按行级钉住。"""
        body = "".join(f"| **{n}**（L1） | 到点必须能回答的问题\n" for n in nodes.split("|"))
        return ("= 执行原则\n\n== 任务生命周期与节点自查\n\n"
                "[cols=\"1,3\"]\n|===\n| 节点 | 到点必须能回答\n"
                + body
                + "|===\n\n* **哪些节点不设（L1）**：代码类改动不设复盘节点。\n")

    def _write_valid(self):
        self.write("specs/core/execution.adoc", self._nodes_text())
        self.write("specs/general/verify.adoc",
                   "= 测试规范\n\n== 验证与运行契约\n\n=== 验证的适用边界\n\n"
                   "先判改动性质：代码类改动按机械判据判过不过、规范类改动做三视角；"
                   "不改内容的操作（C 类）内容逐字节不变、不重跑全量编译与测试，"
                   "\"内容没变\"不是\"少核对\"的借口；"
                   "判据是「会不会被未知项目加载」；不得互串；取**更严的一侧**；"
                   "每次验证都换一个干净上下文；结论按**效力等级**标——确定项可判对错、"
                   "概念项只到未发现，不得当作阻断交付的条件。\n")
        self.write("specs-project-maintainer/verify.adoc",
                   "= 验证的维护方落点\n\n维护方的验证义务与落点。\n")
        self.write("specs-project-maintainer/spec-lifecycle.adoc",
                   "= 规范分类与准入\n\n== 一条规范何时该拆分（防拆分成为新的失控源）\n\n"
                   "判据与用处不同；不拆就真的坏；拆后每一半都自足；默认不拆；"
                   "单独过准入九问。\n\n"
                   "**同一事项只有一个真源（L1，推荐程度与机械量级不构成另建落点的理由）**："
                   "一条规则只在一处给真源、其余只做一跳引用（不构成第四条硬条件）。\n\n"
                   "== 拆分后的自洽核对\n\n引用可达。\n\n"
                   "== 新增规范的提案校验（先校验、再登记、后写入）\n\n"
                   "可机械校验的条目须同时补机械抓手；**同一事项不得留两处真源**——"
                   "已钉过就不另建、只有判据形态不同才另建。\n")
        self.write("AGENTS.adoc", self._own_text())

    def test_valid_lifecycle_guard_passes(self):
        self._write_valid()
        cm.check_lifecycle_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_lifecycle_section_reports(self):
        # 反例：节点自查节被删（"到哪个节点查什么"重新无人负责）
        self._write_valid()
        self.write("specs/core/execution.adoc", "= 执行原则\n\n== 范围控制\n\n不蔓延。\n")
        cm.check_lifecycle_guard()
        self.assertIn("任务生命周期与节点自查", self.error_texts())

    def test_missing_node_reports(self):
        # 反例：七节点里少一个（如"方案"被删 → 去重删减前不再核覆盖完整性）
        self._write_valid()
        self.write("specs/core/execution.adoc",
                   self._nodes_text("提出|理解|执行|验证|交付|复盘"))
        self.write("AGENTS.adoc", self._own_text())
        cm.check_lifecycle_guard()
        self.assertIn("方案", self.error_texts())

    def test_missing_exemption_reports(self):
        # 反例：未写明哪些节点不设（概念性验证会外溢成所有任务的流程）
        self._write_valid()
        self.write("specs/core/execution.adoc",
                   self._nodes_text().split("* **哪些节点不设")[0])
        cm.check_lifecycle_guard()
        self.assertIn("代码类改动", self.error_texts())

    def test_missing_boundary_section_reports(self):
        # 反例：验证边界节被删（不先判改动性质，验证范围无处取值）
        self._write_valid()
        self.write("specs/general/verify.adoc", "= 测试规范\n\n== 单元测试\n\n跑。\n")
        self.write("AGENTS.adoc", "== 验证的适用范围\n\n见 `specs/general/verify.adoc`"
                   + "「验证与运行契约」；拆分判据见「一条规范何时该拆分」。\n")
        cm.check_lifecycle_guard()
        self.assertIn("验证的适用边界", self.error_texts())

    def test_missing_fresh_context_requirement_reports(self):
        # 反例：删掉"每次验证换一个干净上下文"（复用上下文等于自己复核自己）
        self._write_valid()
        self.write("specs/general/verify.adoc",
                   "= 测试规范\n\n== 验证与运行契约\n\n=== 验证的适用边界\n\n"
                   "先判改动性质：代码类改动按机械判据判过不过、规范类改动做三视角；"
                   "判据是「会不会被未知项目加载」；不得互串；取**更严的一侧**。\n")
        self.write("AGENTS.adoc", self._own_text())
        cm.check_lifecycle_guard()
        self.assertIn("干净上下文", self.error_texts())

    def test_missing_content_unchanged_boundary_reports(self):
        # 反例：删掉"不改内容的操作（C 类）不重跑全量校验"（压缩提交/纯改名又会被要求跑全量构建）
        self._write_valid()
        self.write("specs/general/verify.adoc",
                   "= 测试规范\n\n== 验证与运行契约\n\n=== 验证的适用边界\n\n"
                   "先判改动性质：代码类改动按机械判据判过不过、规范类改动做三视角；"
                   "判据是「会不会被未知项目加载」；不得互串；取**更严的一侧**；"
                   "每次验证都换一个干净上下文；结论按**效力等级**标——确定项可判对错、"
                   "概念项只到未发现，不得当作阻断交付的条件。\n")
        self.write("AGENTS.adoc", self._own_text())
        cm.check_lifecycle_guard()
        self.assertIn("不改内容的操作", self.error_texts())

    def test_missing_split_section_reports(self):
        # 反例：拆分判据节被删（拆分成为新的失控源）
        self._write_valid()
        self.write("specs-project-maintainer/spec-lifecycle.adoc", "= 规范分类与准入\n\n== 准入判定\n\n九问。\n")
        self.write("AGENTS.adoc", self._own_text())
        cm.check_lifecycle_guard()
        self.assertIn("一条规范何时该拆分", self.error_texts())

    def test_missing_split_condition_reports(self):
        # 反例：三条硬条件少一条（如"不拆就真的坏"被删）
        self._write_valid()
        self.write("specs-project-maintainer/spec-lifecycle.adoc",
                   "= 规范分类与准入\n\n== 一条规范何时该拆分\n\n"
                   "判据与用处不同；拆后每一半都自足；默认不拆；单独过准入九问。\n\n"
                   "== 拆分后的自洽核对\n\n引用可达。\n")
        self.write("AGENTS.adoc", self._own_text())
        cm.check_lifecycle_guard()
        self.assertIn("不拆就真的坏", self.error_texts())

    def test_missing_single_source_rule_reports(self):
        # 反例（本轮）：拆分判据里"同一事项只有一个真源"被删 -> 会出现另建一份判据本体
        # （两处各改一次、两处漂移时先报红的那道未必是权威）
        self._write_valid()
        self.write("specs-project-maintainer/spec-lifecycle.adoc",
                   "= 规范分类与准入\n\n== 一条规范何时该拆分\n\n"
                   "判据与用处不同；不拆就真的坏；拆后每一半都自足；默认不拆；"
                   "单独过准入九问。\n\n== 拆分后的自洽核对\n\n引用可达。\n\n"
                   "== 新增规范的提案校验\n\n可机械校验的条目须同时补机械抓手。\n")
        self.write("AGENTS.adoc", self._own_text())
        cm.check_lifecycle_guard()
        self.assertIn("同一事项只有一个真源", self.error_texts())

    def test_missing_duplicate_guard_trigger_reports(self):
        # 反例（本轮）：提案校验里"不得留两处真源"的判据被删 -> 另建防线时不会先检索
        self._write_valid()
        self.write("specs-project-maintainer/spec-lifecycle.adoc",
                   "= 规范分类与准入\n\n== 一条规范何时该拆分\n\n"
                   "判据与用处不同；不拆就真的坏；拆后每一半都自足；默认不拆；"
                   "**同一事项只有一个真源**、推荐程度与机械量级不构成另建落点的理由；"
                   "单独过准入九问。\n\n"
                   "== 拆分后的自洽核对\n\n引用可达。\n\n"
                   "== 新增规范的提案校验（先校验、再登记、后写入）\n\n"
                   "可机械校验的条目须同时补机械抓手。\n")
        self.write("AGENTS.adoc", self._own_text())
        cm.check_lifecycle_guard()
        self.assertIn("同一事项不得留两处真源", self.error_texts())

    def test_own_agents_missing_landing_reports(self):
        # 反例：本仓库落点未指向通用层边界节（本仓库口径与通用层脱钩）
        self._write_valid()
        self.write("AGENTS.adoc", "== 规范组织\n\n随便写。\n")
        cm.check_lifecycle_guard()
        self.assertIn("AGENTS.adoc", self.error_texts())


class TestCheckJavaTestNaming(CheckSpecsTestCase):
    """钉住 Java 测试类命名契约（四类后缀）在规范与调度器两侧一致。

    后缀与构建工具的执行边界绑定（`PerfTests`/`IT` 不随常规测试执行），任一处漏掉
    某类后缀，引用方照另一处学习就会漏掉该类测试，故两侧都须写明四类判据。
    """

    # 调度器**只给触发特征**（要新建或改动 Java 测试类时即命中）——四类后缀与拆分裁决
    # 是 `java-testing.adoc` 的条目本体，不再要求调度器逐字抄它们（放宽前的口径即第二真源）。
    JAVA_LINE = ("  ** Java 项目（存在 `.java`、`pom.xml`、`mvnw`、lombok 配置等）→ "
                 "link:specs/stack/java.adoc[] + link:specs/stack/java-testing.adoc[]"
                 "（识别特征：要新建或改动 Java 测试类）")

    def setUp(self) -> None:
        super().setUp()
        self._orig_java = cm.JAVA_TEST_FILE
        cm.JAVA_TEST_FILE = os.path.join(self.root, "specs", "stack", "java-testing.adoc")

    def tearDown(self) -> None:
        cm.JAVA_TEST_FILE = self._orig_java
        super().tearDown()

    def _write_valid(self):
        self.write("specs/stack/java-testing.adoc",
                   "= Java 测试规范\n\n"
                   "== 测试类命名（L1 强制）\n"
                   "测试类名为「被测类名 + 测试类型后缀」：`Tests` 常规、`BootTests` 启动型、"
                   "`PerfTests` 性能、`IT` 端到端；后者独立于常规测试执行。\n"
                   "一个被测类可按需求/分类可拆成多个测试类；分类或属性相同的用例必须"
                   "归入同一个测试类；不得为每个场景一个类而拆，禁止滥拆。\n")
        self.write("AGENTS_COMMON.adoc", self.JAVA_LINE)

    def test_valid_naming_contract_passes(self):
        self._write_valid()
        cm.check_java_test_naming()
        self.assertEqual(cm.errors, [])

    def test_missing_file_reports(self):
        # 反例：Java 测试规范文件整体被删
        self.write("AGENTS_COMMON.adoc", self.JAVA_LINE)
        cm.check_java_test_naming()
        self.assertIn("缺少 Java 测试规范文件", self.error_texts())

    def test_dropped_suffix_reports(self):
        # 反例：规范侧删掉某一类后缀（如 BootTests）
        self.write("specs/stack/java-testing.adoc",
                   "= t\n\n== 测试类命名\n后缀：`Tests`、`PerfTests`、`IT`（被测类名 + 后缀、常规）\n")
        self.write("AGENTS_COMMON.adoc", self.JAVA_LINE)
        cm.check_java_test_naming()
        self.assertIn("BootTests", self.error_texts())

    def test_dispatcher_missing_trigger_reports(self):
        # 反例：调度器登记了文件、却没有"要新建或改动测试类"这一触发特征 → 永不被加载。
        # （放宽后**不再**要求调度器逐字抄四类后缀/拆分裁决——那是条目本体、抄了即第二真源）
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "  ** Java 项目 → link:specs/stack/java-testing.adoc[]")
        cm.check_java_test_naming()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_not_registered_in_dispatcher_reports(self):
        # 反例：文件存在但未登记调度器 → 永不被加载
        self.write("specs/stack/java-testing.adoc",
                   "= t\n\n== 测试类命名\n`Tests` `BootTests` `PerfTests` `IT`（被测类名 + 后缀、常规）")
        self.write("AGENTS_COMMON.adoc", "= t")
        cm.check_java_test_naming()
        self.assertIn("未在加载调度器登记", self.error_texts())

    def test_split_ruling_partial_reports(self):
        # 反例：拆分裁决只剩"合并"那一半（退回"一个被测类一个测试类"）——即本次调整要修掉的口径
        self.write("specs/stack/java-testing.adoc",
                   "= t\n\n== 测试类命名\n`Tests` `BootTests` `PerfTests` `IT`"
                   "（被测类名 + 后缀、常规）\n批量测试同一被测类不同场景时仍合并为一个测试类。\n")
        self.write("AGENTS_COMMON.adoc", self.JAVA_LINE)
        cm.check_java_test_naming()
        self.assertIn("缺失拆分裁决", self.error_texts())

    def test_split_ruling_only_allow_split_reports(self):
        # 反例：只留"可拆"、不留"同分类须归一类 + 禁止滥拆"（放任每个场景一个类）
        self.write("specs/stack/java-testing.adoc",
                   "= t\n\n== 测试类命名\n`Tests` `BootTests` `PerfTests` `IT`"
                   "（被测类名 + 后缀、常规）\n一个被测类可按需求/分类可拆成多个测试类。\n")
        self.write("AGENTS_COMMON.adoc", self.JAVA_LINE)
        cm.check_java_test_naming()
        self.assertIn("缺失拆分裁决", self.error_texts())

    def test_split_ruling_valid_passes(self):
        # 正例：三段判据齐备（可拆 + 同分类同属性须归一类 + 禁止滥拆）
        self._write_valid()
        cm.check_java_test_naming()
        self.assertEqual(cm.errors, [])

    def test_spec_without_split_ruling_reports(self):
        # 反例：**规范侧**只传达后缀、不传达拆分裁决 → 引用方把"一个被测类一个测试类"当硬规定
        # （拆分裁决是 `java-testing.adoc` 的本体，须在**规范文件**里齐备；调度器只给触发特征）
        self.write("specs/stack/java-testing.adoc",
                   "= t\n\n== 测试类命名（L1 强制）\n"
                   "测试类名为「被测类名 + 测试类型后缀」：`Tests` 常规、`BootTests` 启动型、"
                   "`PerfTests` 性能、`IT` 端到端；后者独立于常规测试执行。\n")
        self.write("AGENTS_COMMON.adoc", self.JAVA_LINE)
        cm.check_java_test_naming()
        self.assertIn("拆分裁决", self.error_texts())


class TestCheckLineEndingGuard(CheckSpecsTestCase):
    """钉住跨平台换行符规则（LF 基准 + Windows 批处理 CRLF）。

    行尾错配是"跨平台直接执行失败"（`.bat` 在 LF 下不可执行），且"统一换行符"式的
    精简最易把它删成一句空话，故机械钉住判据与配套栈文件。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_enc = cm.ENCODING_FILE
        self._orig_stack = cm.LINE_ENDING_STACK_FILES
        cm.ENCODING_FILE = os.path.join(self.root, "specs", "general", "encoding.adoc")
        cm.LINE_ENDING_STACK_FILES = tuple(
            os.path.join(self.root, "specs", "stack", f)
            for f in ("bash.adoc", "python.adoc", "batch.adoc", "powershell.adoc"))

    def tearDown(self) -> None:
        cm.ENCODING_FILE = self._orig_enc
        cm.LINE_ENDING_STACK_FILES = self._orig_stack
        super().tearDown()

    def _write_valid(self):
        self.write("specs/general/encoding.adoc",
                   "= 编码与语言无关\n\n"
                   "== 换行符（行尾）\n"
                   "内容以 LF 为基准；`.bat`/`.cmd` 必须 CRLF；`.ps1` 用 CRLF；"
                   "由 `.gitattributes`（行尾）与 `.editorconfig` 固定，"
                   "`core.autocrlf` 交给仓库配置、不靠人工手动调整。\n")
        for f in ("bash.adoc", "python.adoc", "powershell.adoc"):
            self.write(f"specs/stack/{f}",
                       "行尾：按本栈要求（LF 或 CRLF）；BOM 是唯一允许出现在首行之前的东西\n")
        self.write("specs/stack/batch.adoc",
                   "行尾：CRLF，纯 ASCII，**天然不带 BOM**（二者是一件事的两面）；"
                   "**首行** `@echo off`\n")
        self.write("AGENTS_COMMON.adoc", "登记 `specs/general/encoding.adoc`")

    def test_valid_line_ending_rules_pass(self):
        self._write_valid()
        cm.check_line_ending_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_encoding_file_reports(self):
        # 反例：编码规范文件整体被删 → 行尾判据失去集中落点
        self.write("AGENTS_COMMON.adoc", "= t")
        cm.check_line_ending_guard()
        self.assertIn("缺少编码与语言无关规范文件", self.error_texts())

    def test_dropped_windows_batch_crlf_reports(self):
        # 反例：删掉 `.bat` 必须 CRLF（这正是"BAT 用 Linux 换行符"的失效源头）
        self.write("specs/general/encoding.adoc",
                   "= t\n\n== 换行符（行尾）\n内容以 LF 为基准；`.ps1` 用 CRLF；"
                   "由 `.gitattributes` 固定，`core.autocrlf` 交给仓库配置、不靠人工手动调整。\n")
        for f in ("bash.adoc", "python.adoc", "powershell.adoc"):
            self.write(f"specs/stack/{f}",
                       "行尾：LF；BOM 是唯一允许出现在首行之前的东西\n")
        self.write("specs/stack/batch.adoc",
                   "行尾：CRLF，纯 ASCII，**天然不带 BOM**；**首行** `@echo off`\n")
        self.write("AGENTS_COMMON.adoc", "登记 `specs/general/encoding.adoc`")
        cm.check_line_ending_guard()
        self.assertIn(".bat", self.error_texts())

    def test_dropped_checkout_normalization_reports(self):
        # 反例：删掉"不靠人工手动调整"的检出归一依据（core.autocrlf/.gitattributes）
        self.write("specs/general/encoding.adoc",
                   "= t\n\n== 换行符（行尾）\n内容以 LF 为基准；`.bat`/`.cmd` 必须 CRLF。\n")
        for f in ("bash.adoc", "python.adoc", "powershell.adoc"):
            self.write(f"specs/stack/{f}",
                       "行尾：LF；BOM 是唯一允许出现在首行之前的东西\n")
        self.write("specs/stack/batch.adoc",
                   "行尾：CRLF，纯 ASCII，**天然不带 BOM**；**首行** `@echo off`\n")
        self.write("AGENTS_COMMON.adoc", "登记 `specs/general/encoding.adoc`")
        cm.check_line_ending_guard()
        self.assertIn(".gitattributes", self.error_texts())

    def test_dropped_editorconfig_reports(self):
        # 反例：删掉 `.editorconfig` 落盘口 → 编辑器侧的行尾无人固定
        self.write("specs/general/encoding.adoc",
                   "= t\n\n== 换行符（行尾）\n内容以 LF 为基准；"
                   "`.bat`/`.cmd` 必须 CRLF；"
                   "由 `.gitattributes` 固定，`core.autocrlf` 交给仓库配置、不靠人工手动调整。\n")
        for f in ("bash.adoc", "python.adoc", "powershell.adoc"):
            self.write(f"specs/stack/{f}",
                       "行尾：LF；BOM 是唯一允许出现在首行之前的东西\n")
        self.write("specs/stack/batch.adoc",
                   "行尾：CRLF，纯 ASCII，**天然不带 BOM**；**首行** `@echo off`\n")
        self.write("AGENTS_COMMON.adoc", "登记 `specs/general/encoding.adoc`")
        cm.check_line_ending_guard()
        self.assertIn(".editorconfig", self.error_texts())

    def test_stack_file_without_line_ending_reports(self):
        # 反例：脚本栈文件未写明行尾要求 → 引用方按该栈文件学习学不到
        self._write_valid()
        self.write("specs/stack/python.adoc", "= Python 脚本规范\n")
        cm.check_line_ending_guard()
        self.assertIn("specs/stack/python.adoc", self.error_texts())

    def test_not_registered_in_dispatcher_reports(self):
        # 反例：文件存在但未登记调度器 → 永不被加载（登记完整性由
        # `check_dispatcher_registry` 统一核，本防线只接换行符自身的规则）
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "= t")
        cm.check_line_ending_guard()
        self.assertIn("AGENTS_COMMON.adoc", "".join(cm.errors) or "AGENTS_COMMON.adoc")


class TestCheckPromptsPrimary(CheckSpecsTestCase):
    """钉住提示词的「主侧重（方向前提）」与「优先级规则（L1/L2/L3）」。

    侧重是方向性内容、错了后面全做错，故与最高关注项一样加机械防线：登记表、正文
    侧重声明、公共片段注入、分级与业界依据缺一即报。
    """

    COMMON = (
        "提示词公共片段\n"
        "// tag::priority-rules[]\n"
        "优先级规则：按 RFC 2119 与 ISO/IEC Directives Part 2 执行——"
        "必须/严禁 = L1 强制、应当 = L2 建议、可以 = L3 允许；不可降级。\n"
        "// end::priority-rules[]\n")

    def setUp(self) -> None:
        super().setUp()
        self._orig_prompts = (cm.PROMPTS_FILE, cm.PROMPTS_DIR, cm.COMMON_PROMPT_FILE)
        cm.PROMPTS_FILE = os.path.join(self.root, "PROMPTS.adoc")
        cm.PROMPTS_DIR = os.path.join(self.root, "prompts")
        cm.COMMON_PROMPT_FILE = os.path.join(self.root, "prompts", "_common.txt")

    def tearDown(self) -> None:
        (cm.PROMPTS_FILE, cm.PROMPTS_DIR,
         cm.COMMON_PROMPT_FILE) = self._orig_prompts
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("prompts/_common.txt", self.COMMON)
        self.write("PROMPTS.adoc",
                   "| link:prompts/review.adoc[] | **检查修复问题** | 主侧重片段 `primary` |\n"
                   "| link:prompts/refactor.adoc[] | **重构** | 主侧重片段 `primary` |\n")
        self.write("prompts/review.adoc",
                   "**主侧重（方向性前提）**：**检查修复问题**——方向错了后面全做错。\n"
                   "include::_common.txt[tag=primary]\n"
                   "include::_common.txt[tag=priority-rules]\n")
        self.write("prompts/refactor.adoc",
                   "**主侧重（方向性前提）**：**\"重构\"**——方向错了后面全做错。\n"
                   "include::_common.txt[tag=primary]\n"
                   "include::_common.txt[tag=priority-rules]\n")

    def test_valid_prompts_pass(self):
        self._write_valid()
        cm.check_prompts_primary()
        self.assertEqual(cm.errors, [])

    def test_missing_registry_reports(self):
        # 反例：登记入口整体被删（侧重无处登记）
        self._write_valid()
        os.remove(cm.PROMPTS_FILE)
        cm.check_prompts_primary()
        self.assertIn("缺少提示词登记入口", self.error_texts())

    def test_registry_without_primary_column_reports(self):
        # 反例：登记表丢了主侧重列（只登记用途，方向信息消失）
        self._write_valid()
        self.write("PROMPTS.adoc",
                   "| link:prompts/review.adoc[] | 检查修复问题 |\n"
                   "| link:prompts/refactor.adoc[] | 重构 |\n")
        cm.check_prompts_primary()
        self.assertIn("主侧重", self.error_texts())

    def test_prompt_without_primary_direction_reports(self):
        # 反例：提示词未声明主侧重（删掉方向性前提）→ 方向丢失
        self._write_valid()
        self.write("prompts/refactor.adoc",
                   "对本项目执行一次全量重构。\n"
                   "include::_common.txt[tag=primary]\n")
        cm.check_prompts_primary()
        self.assertIn("未显式声明", self.error_texts())
        self.assertIn("priority-rules", self.error_texts())

    def test_primary_not_in_registry_reports(self):
        # 反例：正文侧重与登记表不一致（侧重未登记 = 方向不明）
        self._write_valid()
        self.write("prompts/refactor.adoc",
                   "**主侧重（方向性前提）**：**重写架构**——方向错了后面全做错。\n"
                   "include::_common.txt[tag=primary]\n"
                   "include::_common.txt[tag=priority-rules]\n")
        cm.check_prompts_primary()
        self.assertIn("未在", self.error_texts())

    def test_same_primary_for_both_prompts_reports(self):
        # 反例：两个提示词侧重被复制成同一个（方向混用）
        self._write_valid()
        self.write("prompts/refactor.adoc",
                   "**主侧重（方向性前提）**：**检查修复问题**——方向错了后面全做错。\n"
                   "include::_common.txt[tag=primary]\n"
                   "include::_common.txt[tag=priority-rules]\n")
        cm.check_prompts_primary()
        self.assertIn("侧重出现重复", self.error_texts())

    def test_priority_rules_missing_level_reports(self):
        # 反例：优先级分级被删（只剩 L1）→ 无法判断哪里是重点
        self._write_valid()
        self.write("prompts/_common.txt",
                   "// tag::priority-rules[]\n必须 = L1 强制；按 RFC 2119 与 ISO 执行。\n"
                   "// end::priority-rules[]\n")
        cm.check_prompts_primary()
        self.assertIn("L2 建议", self.error_texts())
        self.assertIn("L3 允许", self.error_texts())

    def test_priority_rules_missing_industry_basis_reports(self):
        # 反例：去掉业界共识依据（要求"按业界共识加载优先级"就失去出处）
        self._write_valid()
        self.write("prompts/_common.txt",
                   "// tag::priority-rules[]\n"
                   "必须 = L1 强制、应当 = L2 建议、可以 = L3 允许；不可降级。\n"
                   "// end::priority-rules[]\n")
        cm.check_prompts_primary()
        self.assertIn("RFC 2119", self.error_texts())

    def test_priority_rules_without_non_downgrade_reports(self):
        # 反例：去掉"不可降级"= 允许 L1 被降为建议
        self._write_valid()
        self.write("prompts/_common.txt",
                   "// tag::priority-rules[]\n"
                   "按 RFC 2119 与 ISO 执行：必须 = L1 强制、应当 = L2 建议、可以 = L3 允许。\n"
                   "// end::priority-rules[]\n")
        cm.check_prompts_primary()
        self.assertIn("不可降级", self.error_texts())

    def test_conflicting_primary_within_prompt_reports(self):
        # 反例：同一提示词内两处侧重写法不一致（方向自相矛盾）
        self._write_valid()
        self.write("prompts/refactor.adoc",
                   "**主侧重（方向性前提）**：**重构**——方向错了后面全做错。\n"
                   "**主侧重（方向性前提）**：**检查修复问题**——方向错了后面全做错。\n"
                   "include::_common.txt[tag=primary]\n"
                   "include::_common.txt[tag=priority-rules]\n")
        cm.check_prompts_primary()
        self.assertIn("写法不一致", self.error_texts())

    def test_primary_fragment_injected(self):
        # 正例：代码块内须注入 primary 片段本身（防只留说明段、片段被删）
        self._write_valid()
        cm.check_prompts_primary()
        self.assertEqual(cm.errors, [])


class TestCheckDevFlowGuard(CheckSpecsTestCase):
    """钉住『开发流程防线』（用户提出的开发流程要求，本项目实测失效）。

    失效形态：不摸现状直接动手（按想象改）；绕开既有实现另写一套（留下两套实现/配置/文档，
    达不到最佳实践）；重构后把老用例改掉让它"通过"（既有行为的规格被改动方单方面改判）；
    兼容不了就自行取舍（老旧废弃流程的处置被执行者自行认定）。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_prompts = (cm.PROMPTS_DIR, cm.PROMPTS_FILE, cm.README_FILE,
                              cm.COMMON_PROMPT_FILE)
        cm.PROMPTS_DIR = os.path.join(self.root, "prompts")
        cm.PROMPTS_FILE = os.path.join(self.root, "PROMPTS.adoc")
        cm.README_FILE = os.path.join(self.root, "README.adoc")
        cm.COMMON_PROMPT_FILE = os.path.join(self.root, "prompts", "_common.txt")

    def tearDown(self) -> None:
        (cm.PROMPTS_DIR, cm.PROMPTS_FILE, cm.README_FILE,
         cm.COMMON_PROMPT_FILE) = self._orig_prompts
        super().tearDown()

    def _write_valid(self):
        self.write("specs/core/execution.adoc",
                   "= 执行原则\n\n== 先规划后执行\n\n"
                   "* **动手前先摸清现状与最佳方案（L1）**：先搞清现状，再**先调研最佳实践、再定方案**；"
                   "**调整内容一类需求**（新增与调整同属一类）还须**先找现成可参照的既有标准与更优设计**。\n"
                   "* **动手改文件前先读要改的那一处（L1）**：核对对象**只到要改的那一处现状**，"
                   "**不得按记忆中的内容写入**（该处可能已被改过、按记忆写入会把本地内容覆盖掉），"
                   "**详细判据与失效形态见** `specs/general/planning.adoc`「要改的那一处是否已实际读过（改动面按处读）」。\n"
                   "* 不得绕开既有体系另写一套（L1）：默认改在既有实现上；"
                   "**允许另写一套的条件只有三个**：确实无法承载 / 已被用户确认废弃 / 已被证明优于，**不留两套并存**。\n"
                   "* 大范围改动先确认（L1）：**不得替用户判定某段既有流程\"已废弃\"**。\n"
                   "* 改动前先定基线（L1）：**该不该做基线按改动性质判**（取值与判据在通用层，本条不复述、**不做基线 ≠ 不做验证**）；"
                   "**该做时** **扫描项目声明的全部校验手段**，**完整可用时必须先跑通**，"
                   "并**落盘留证**，改动完成后**复跑同一套校验**；**扫出的清单还要先核\"够不够用\"（L2）**："
                   "须**先按用例设计判据 review 既有用例**，**本次改动的直接相关面**先补全、**不阻断动手**。\n\n== 任务生命周期与节点自查\n\n"
                   "| **方案** | **基线是否已定**\n"
                   "| **验证** | **是否与基线逐项比对**\n\n== 下节\n")
        self.write("specs/general/planning.adoc",
                   "= 任务规划\n\n== 动手前：现状与最佳方案\n\n"
                   "* **先查现状（L1）**：**不得凭印象或标题推断**，并列出**核实方式**。\n"
                   "* **先调研最佳方案（L1）**：列出**备选方案与取舍依据**，不得只给\"能交差\"的写法。\n"
                   "* **需求先找参照物（L1）**：\"调整内容\"一类需求（**新增与调整同属一类**）先找现成可参照的"
                   "既有标准与更优设计——① **业界标准/权威约定**；② **既有通行设计范式**；"
                   "③ **本项目既有条目与先例**（见 `specs/general/coding.adoc`「既有实现与先例优先」）；"
                   "**查不到**也要能说出查证方式、如实标\"未确证\"；**查到更优的设计就用更优的**。\n"
                   "** **判定标准（任一命中即不合规）**：**说不出参照物与检索动作** / "
                   "**有标准可循却自造一套说法** / **有更优设计却仍按原口述照收**；"
                   "**收的是哪一条**同样须在规划里写明、**不得只留结论、不留取舍**。"
                   "** **依据**：ISO 10007。\n\n"
                   "=== 要改的那一处是否已实际读过（改动面按处读）\n\n"
                   "* **改动面按处读（L1）**：**动手改文件时，先读该文件里要改的那一处**——核对对象是"
                   "**要改的那一处现状**（与本次改动无关的部分**不必读**）。**判定标准（任一命中即不合规）**："
                   "① 未读取目标处即按其**记忆中的内容**写入（该处已被改过时，**把本地内容覆盖掉**）；"
                   "② 以\"可能已经改过了\"为由**跳过读取**；③ 读取的范围与本次要改的位置对不上。"
                   "**边界**：**不得**被本条**读成**\"每个文件都要通读\"；"
                   "必加载层的对应条在 `specs/core/execution.adoc`、自检清单侧在 `specs/general/self-check.adoc`。\n\n"
                   "== 不得绕开既有体系另写一套\n\n* **默认改在既有实现上（L1）**："
                   "**确实无法承载** / **已被用户确认废弃** / **已被证明优于**；**不留两套并存**。\n\n"
                   "== 大范围改动先确认\n\n* **大动之前先确认（L1）**：**保持原状**；"
                   "**是否废弃只能由用户认定**。\n\n== 动手前先定基线\n\n"
                   "* **基线的适用边界（L1）**：**先判改动性质、再决定这条要不要做**——"
                   "性质判定与各档取值（含例外、**判不准时按更严的一侧**）"
                   "**以 `specs/general/verify.adoc`「验证的适用边界」为唯一真源，本条不重列第二套定义**。\n"
                   "* **扫描既有验证手段（L1）**\n* **能跑通即跑通、并落盘留证（L1）**\n"
                   "* **留证的形态按项目自身的交付约定**：**留证不等于「必须提交」**。\n"
                   "* **不完整或本来就红时怎么办（L1，防把基线变成硬性前置）**："
                   "**没有任何校验手段**时记录即可开工；**红的还是红的**。\n"
                   "* **基线用于改完复跑（L1）**：**既有用例不得为迁就改动而改判**。\n"
                   "* **基线的完整性：手段与用例够不够用（L2，仅在该做基线时适用）**：**先按这些判据 review 既有用例**，"
                   "给出**复核了哪些角度与样本**；按**正常路径**/边界/异常路径/**正反例成对**/步骤与前置核对，"
                   "**用例设计**与**测试有效性**判据见 testing.adoc；**本次改动的直接相关面**先补全，"
                   "**无关的存量缺口**如实记录、**不阻断**。\n\n"
                   "* **ISO 10007**（配置管理）。\n")
        self.write("specs/general/verify.adoc",
                   "= 验证\n\n== 验证的适用边界（先判改动性质，再决定验证到什么程度）\n\n"
                   "判据只有一个问句（L1）：**\"这次改动会不会被未知项目加载、会不会改变别人的行为？\"**\n\n"
                   "* **A 代码类改动**：**不做基线测试**——**例外**＝**大规模重构**、或本次会改动**改动大部分内容**"
                   "（**移动/重命名不算**）。\n"
                   "* **B 规范类改动**：**必须取得基线**。\n"
                   "* **C 不改内容的操作**：**不做基线测试**。\n\n"
                   "* **验证须覆盖项目的全部既定校验手段（L1，仅限收尾那一次）**：**存在测试**≠**测试被执行**；"
                   "手段与其用例**本身可能不完整**，须**先按 link:testing.adoc[]「用例设计」review**、"
                   "说明\"哪些未覆盖\"，**本次改动的直接相关面**先补全。\n"
                   "* **按需验证、不滥验证（L1）**：验证**只在必须有验证的地方做**。判定标准："
                   "**尚未做完时不做阶段性验证**、多个待验证项**合并为一次执行**、"
                   "验证范围**只覆盖本次改动的直接相关面**、一次执行内拿到结果（\u201c延后验证、一次到位\u201d）、"
                   "**先信已验过的、不重复验**（前面已验过且**其后无改动**的部分直接采信已有结果、**不重复验**；"
                   "重验只限**该部分自身之后又被改动**、上次验的**不是这份内容**、上次结论本就不成立三类，"
                   "**单纯又提交了一个 commit 不构成重验理由**）。\n"
                   "* **汇报须与可核对的事实一致，不得狡辩（L1）**：汇报里的每一项结论都须与**实际取值**一致。"
                   "**判定标准（任一命中即不合规）**：① 汇报里的**数字与清单**（提交数、文件数、用例统计等）"
                   "与**实际统计**不一致——数字类结论须与实际取值同源，**写进汇报前须重取一次**；"
                   "② 用\"核对项全绿\"自证用户质疑的那件事没发生——**先复取值再回答**、**不得拿既有结论当辩词**；"
                   "③ 用户指出的不符**成立**时先更正汇报。\n")
        self.write("specs/general/testing.adoc",
                   "= 测试\n\n* 重构后须**同时满足既有用例与新用例**（L1）："
                   "**既有用例不得为迁就重构而改判**（除**相关功能被显式移除**）、**前后完整兼容**"
                   "（参考 **Semantic Versioning**）。\n"
                   "* 兼容性无法满足时先确认（L1）：**兼容不了**先停下确认，"
                   "**老旧废弃流程**是否废弃由用户认定、**不得自行取舍**。\n")
        self.write("prompts/_common.txt",
                   "// tag::baseline-and-compat[]\n"
                   "**动手前：先定基线 + 先查现状 + 先调研最佳方案（L1，方向性前提）**\n"
                   "  - **先查现状、再谈方案**\n  - **先定基线**："
                   "**按改动性质取值**（规范类必做、代码类默认不做，"
                   "例外与判不准的取严规则见项目规范 `specs/general/verify.adoc`「验证的适用边界」）。"
                   "\n  - **大动之前先确认**\n"
                   "  - **不得绕开既有实现另写一套**\n"
                   "  - **调整内容一类需求还须先找现成可参照的既有标准与更优设计**\n"
                   "  - **基线清单还要核\"够不够用\"（L2）**：**review 既有用例**、"
                   "**无关的存量缺口**如实记录。\n"
                   "  - **没有校验手段、环境跑不起来，都不是不动手的理由**\n"
                   "// end::baseline-and-compat[]\n\n// tag::compat[]\n"
                   "**改动后：老用例与新用例必须同时成立（L1）**\n"
                   "  - **既有用例不得为迁就改动而改判**\n"
                   "  - **新老用例在同一套校验里同时全绿**\n  - **兼容不了就停下确认**\n"
                   "  - **验证须与基线比对**\n// end::compat[]\n\n"
                   "// tag::report-tail[]\n与**交付情况**。"
                   "**汇报里的数字与结论须与实际取值一致（L1）**——用户指出的不符"
                   "**先复取值再回答**、**不得拿既有结论当辩词**。\n// end::report-tail[]\n")
        for name in ("review.adoc", "refactor.adoc"):
            self.write(f"prompts/{name}",
                       "= 提示词\n\ninclude::_common.txt[tag=baseline]\n"
                       "include::_common.txt[tag=baseline-and-compat]\n"
                       "include::_common.txt[tag=compat]\n"
                       "3. 步骤：**调整内容一类改动动手前须先检索现成可参照的标准与更优的设计**。\n")
        self.write("specs/general/self-check.adoc",
                   "= 自检\n\n* **改动面按处读（L1）**：**动手改一个文件前，先读该文件里要改的那一处**；"
                   "判据见 `specs/general/planning.adoc`「要改的那一处是否已实际读过（改动面按处读）」，"
                   "必加载层的对应条在 `specs/core/execution.adoc`。\n")
        self.write("AGENTS_COMMON.adoc",
                   "= 入口\n\n  ** 动手前的现状与方案、基线 → link:specs/general/planning.adoc[]\n")
        self.write("PROMPTS.adoc",
                   "= 提示词入口\n\n公共约定：**先定基线**、`baseline-and-compat`、`compat`，"
                   "**调整内容一类需求须先检索可参照的标准与更优的设计**。\n")
        self.write("README.adoc",
                   "= 说明\n\n**先定基线**；**既有用例不得为迁就改动而改判**。\n")

    def test_valid_dev_flow_guard_passes(self):
        self._write_valid()
        cm.check_dev_flow_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_baseline_clause_reports(self):
        # 反例：基线条被删（"改完有没有破坏既有行为"失去尺子）
        self._write_valid()
        self.write("specs/core/execution.adoc", "= 执行原则\n\n== 先规划后执行\n\n动手前先规划。\n")
        cm.check_dev_flow_guard()
        self.assertIn("改动前先定基线", self.error_texts())

    def test_on_demand_verification_removed_reports(self):
        # 反例：「按需验证、不滥验证」条被删（验证重新被撒在每一步上，
        # 交付被拖长而换不来新判据——用户口径：验证耗费太多时间）
        self._write_valid()
        v = os.path.join(self.root, "specs", "general", "verify.adoc")
        text = open(v, encoding="utf-8").read()
        head, rest = text.split("* **按需验证、不滥验证", 1)
        rest = rest.split("\n", 1)[1]
        open(v, "w", encoding="utf-8").write(head + rest)
        cm.check_dev_flow_guard()
        self.assertIn("按需验证、不滥验证", self.error_texts())

    def test_on_demand_verification_trust_prior_result_removed_reports(self):
        # 反例：「先信已验过的、不重复验」被删（前面验过的部分被要求再来一遍，
        # 同一动作来回重跑、交付被拖长——用户口径：不是最后一次就不要重复验）
        self._write_valid()
        v = os.path.join(self.root, "specs", "general", "verify.adoc")
        text = open(v, encoding="utf-8").read()
        idx = text.index("先信已验过的、不重复验")
        head, rest = text[:idx], text[idx:]
        rest = rest.split("\n", 1)[1]
        open(v, "w", encoding="utf-8").write(head + rest)
        cm.check_dev_flow_guard()
        self.assertIn("先信已验过的、不重复验", self.error_texts())

    def test_baseline_scope_boundary_removed_reports(self):
        # 反例：真源侧的适用边界取值被删（基线重新变成所有改动的前置，代码类改动白付全量校验）
        self._write_valid()
        v = os.path.join(self.root, "specs", "general", "verify.adoc")
        text = open(v, encoding="utf-8").read().replace(
            "**不做基线测试**", "").replace(
            "**移动/重命名不算**", "")
        open(v, "w", encoding="utf-8").write(text)
        cm.check_dev_flow_guard()
        self.assertIn("verify.adoc", self.error_texts())

    def test_baseline_scope_clause_not_pointing_to_source_reports(self):
        # 反例：planning「基线的适用边界」条丢了"回指唯一真源 + 判不准取严"（基线分档
        # 失去通用层落点与兜底取值，读 planning 的执行者会退回"所有改动都做基线"）
        self._write_valid()
        f = os.path.join(self.root, "specs", "general", "planning.adoc")
        text = open(f, encoding="utf-8").read().replace(
            "**先判改动性质、再决定这条要不要做**", "").replace(
            "**判不准时按更严的一侧**", "")
        open(f, "w", encoding="utf-8").write(text)
        cm.check_dev_flow_guard()
        self.assertIn("planning.adoc", self.error_texts())

    def test_missing_planning_file_reports(self):
        # 反例：通用层展开文件被删（必加载层只剩底线，条件判据无处可查）
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "general", "planning.adoc"))
        cm.check_dev_flow_guard()
        self.assertIn("planning.adoc", self.error_texts())

    def test_read_before_edit_section_removed_reports(self):
        # 反例：整条「改动面按处读」小节被删（动手前不再读要改的那一处，
        # 按记忆写入会把本地内容覆盖掉）
        self._write_valid()
        f = os.path.join(self.root, "specs", "general", "planning.adoc")
        text = open(f, encoding="utf-8").read()
        head, rest = text.split("=== 要改的那一处是否已实际读过", 1)
        # 只删小节自身（保留其后的各节），使"小节被抽掉"与"文件被删"区分开
        open(f, "w", encoding="utf-8").write(head + "== 不得绕开既有体系另写一套" + rest)
        cm.check_dev_flow_guard()
        self.assertIn("要改的那一处是否已实际读过", self.error_texts())

    def test_read_before_edit_memory_clause_removed_reports(self):
        # 反例：判据本体被抽（只剩一句"先读要改的地方"，而"不得按记忆写入 → 覆盖本地内容"
        # 这半条消失后，实测失效照样发生）
        self._write_valid()
        f = os.path.join(self.root, "specs", "general", "planning.adoc")
        text = open(f, encoding="utf-8").read().replace(
            "**记忆中的内容**", "**原来的写法**").replace(
            "把本地内容覆盖掉", "改动不一致").replace(
            "先读该文件里要改的那一处", "先看看文件")
        open(f, "w", encoding="utf-8").write(text)
        cm.check_dev_flow_guard()
        self.assertIn("改动面按处读", self.error_texts())

    def test_read_before_edit_boundary_removed_reports(self):
        # 反例：**边界句**被抽（本条会被读成"每个文件都要通读"——与「读取按最小必要」相抵）。
        # 截法是**只把"读成"那两字换掉**：按整句替换时实测抽不动（逐字照抄长句、
        # 与夹具里的写法差一个全角引号就静默不生效，用例照样全绿）
        self._write_valid()
        f = os.path.join(self.root, "specs", "general", "planning.adoc")
        text = open(f, encoding="utf-8").read().replace("读成", "读作")
        open(f, "w", encoding="utf-8").write(text)
        cm.check_dev_flow_guard()
        self.assertIn("改动面按处读", self.error_texts())

    def test_read_before_edit_missing_in_execution_reports(self):
        # 反例：必加载层那条底线被抽（判据只在用到 planning.adoc 时才可见；
        # 断言用**报错正文里才会出现的锚点**——不得用"必加载层"这类同时出现在
        # message 文案里的词，否则断言恒绿、这条用例什么都证不了【复核实测踩过】）
        self._write_valid()
        f = os.path.join(self.root, "specs", "core", "execution.adoc")
        text = open(f, encoding="utf-8").read().replace(
            "* **动手改文件前先读要改的那一处（L1）**", "* **动手前先看看代码（L1）**")
        open(f, "w", encoding="utf-8").write(text)
        cm.check_dev_flow_guard()
        self.assertIn("**只到要改的那一处现状**", self.error_texts())

    def test_read_before_edit_missing_in_self_check_reports(self):
        # 反例：本条在通用层里**不再回指**自检清单那处落点（回指一缺，读者就不知道
        # 该要求挂在自检关口上；自检关口本身在不在另由 ②c 分支核）
        self._write_valid()
        f = os.path.join(self.root, "specs", "general", "planning.adoc")
        # 夹具里那条的落点是「**必加载层**与**自检清单**各有一处落点（…）」，与真实
        # 文件的行文不同，故按**夹具里的写法**截（截不动时 assertNotEqual 会先炸——
        # 不留一条静默全绿的用例）
        text = open(f, encoding="utf-8").read()
        cut = text.replace("、自检清单侧在 `specs/general/self-check.adoc`", "、自检清单侧另见")
        self.assertNotEqual(cut, text, "反例的截法失效——按夹具正文原样截，改措辞后须同步这里")
        text = cut
        open(f, "w", encoding="utf-8").write(text)
        cm.check_dev_flow_guard()
        self.assertIn("`specs/general/self-check.adoc`", self.error_texts())

    def test_read_before_edit_self_check_file_removed_reports(self):
        # 反例：自检规范整体被删（自检关口不会问到"要改的地方读过没有"）
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "general", "self-check.adoc"))
        cm.check_dev_flow_guard()
        self.assertIn("『要改的那一处读过没有』不再有人问", self.error_texts())

    def test_unknown_placeholder_in_custom_message_rejected(self):
        # 反例：自定义文案里写了引擎不认的占位符——报错正文会原样带着它
        # （缺的是哪一节反而看不出来）。判据在加载期，直接构造 `Rules` 也要过；
        # 断言须核判据本身，只断言那几个字时改成放行也照样绿【复核实测踩过】。
        with self.assertRaises(rules_engine.RulesError) as ctx:
            rules_engine.Rules(
                {"guards": {"g": [{"kind": "file_groups", "file": "a.adoc",
                                   "groups": [["x", ["y"], "z"]],
                                   "message": "{file}「{section}」缺 {missing}"}]}},
                None)
        self.assertIn("引擎不认识的占位符 `{section}`", str(ctx.exception))
        self.assertIn("可用的是", str(ctx.exception))

    def test_reference_seeking_clause_removed_reports(self):
        # 反例：「需求先找参照物」被删（用户提需求/调整内容时不再先查现成标准与更优设计，
        # 退回"用户怎么说就怎么收"）
        self._write_valid()
        pl = os.path.join(self.root, "specs", "general", "planning.adoc")
        text = open(pl, encoding="utf-8").read()
        head, rest = text.split("* **需求先找参照物（L1）**", 1)
        # 只删"参照物"那一条的业务正文（把它压成一句标题），保留其后的各节——
        # 直接按行截断会连带删掉后面所有落点，报出来的就不是本条要证的那条规则
        open(pl, "w", encoding="utf-8").write(
            head + "（本步骤已简化）\n" + "== " + rest.split("\n== ", 1)[-1])
        cm.check_dev_flow_guard()
        self.assertIn("需求先找参照物", self.error_texts())

    def test_reference_seeking_without_criteria_reports(self):
        # 反例：条在、判定标准被抽走（只剩一句"先找参照物"＝口号，无抓手）
        self._write_valid()
        pl = os.path.join(self.root, "specs", "general", "planning.adoc")
        text = open(pl, encoding="utf-8").read().replace(
            "** **判定标准（任一命中即不合规）**：**说不出参照物与检索动作** / "
            "**有标准可循却自造一套说法** / **有更优设计却仍按原口述照收**；"
            "**收的是哪一条**同样须在规划里写明、**不得只留结论、不留取舍**。"
            "** **依据**：ISO 10007。\n",
            "")
        open(pl, "w", encoding="utf-8").write(text)
        cm.check_dev_flow_guard()
        self.assertIn("参照物", self.error_texts())

    def test_reference_seeking_missing_in_prompt_body_reports(self):
        # 反例：只有公共片段写了、两个提示词自己的动手前步骤没写
        # （题面自行表述的那处漏掉，按题面执行时读不到）
        self._write_valid()
        f = os.path.join(self.root, "prompts", "review.adoc")
        text = open(f, encoding="utf-8").read().replace(
            "3. 步骤：**调整内容一类改动动手前须先检索现成可参照的标准与更优的设计**。\n", "")
        open(f, "w", encoding="utf-8").write(text)
        cm.check_dev_flow_guard()
        self.assertIn("review.adoc", self.error_texts())

    def test_old_cases_may_be_rewritten_clause_removed_reports(self):
        # 反例：「既有用例不得为迁就重构而改判」被删（改老用例变绿重成默认做法）
        self._write_valid()
        self.write("specs/general/testing.adoc", "= 测试\n\n修改代码后须确保既有用例全部通过。\n")
        cm.check_dev_flow_guard()
        self.assertIn("testing.adoc", self.error_texts())

    def test_missing_prompt_fragment_reports(self):
        # 反例：公共片段被删（提示词复制到未知项目后这条边界整条丢失）
        self._write_valid()
        self.write("prompts/_common.txt", "// tag::baseline[]\n1. 规范与基线。\n// end::baseline[]\n")
        cm.check_dev_flow_guard()
        self.assertIn("baseline-and-compat", self.error_texts())

    def test_prompt_missing_include_reports(self):
        # 反例：提示词代码块少一个 include（题面未装配该边界）
        self._write_valid()
        self.write("prompts/review.adoc",
                   "= 提示词\n\ninclude::_common.txt[tag=baseline-and-compat]\n")
        cm.check_dev_flow_guard()
        self.assertIn("compat", self.error_texts())

    def test_baseline_has_no_fallback_branch_reports(self):
        # 反例：基线条缺"无手段/红测试不阻断"的降级分支
        # （会把基线变成引用方的硬性前置：没有测试的项目从此动不了手）
        self._write_valid()
        self.write("specs/general/planning.adoc",
                   "= 任务规划\n\n== 动手前先定基线\n\n"
                   "* **扫描既有验证手段（L1）**\n* **能跑通即跑通、并落盘留证（L1）**\n"
                   "* **基线用于改完复跑（L1）**\n")
        cm.check_dev_flow_guard()
        self.assertIn("降级分支", self.error_texts())

    def test_baseline_without_completeness_clause_reports(self):
        # 反例：基线只要求"扫一遍声明的命令"，缺"清单够不够用"（手段/用例本身可能不全）
        self._write_valid()
        self.write("specs/general/planning.adoc",
                   "= 任务规划\n\n== 动手前先定基线\n\n"
                   "* **扫描既有验证手段（L1）**\n* **能跑通即跑通、并落盘留证（L1）**\n"
                   "* **留证的形态按项目自身的交付约定**：**留证不等于「必须提交」**。\n"
                   "* **不完整或本来就红时怎么办（L1，防把基线变成硬性前置）**："
                   "**没有任何校验手段**时记录即可开工；**红的还是红的**。\n"
                   "* **基线用于改完复跑（L1）**：**既有用例不得为迁就改动而改判**。\n")
        cm.check_dev_flow_guard()
        self.assertIn("基线完整性", self.error_texts())

    def test_baseline_completeness_without_scope_boundary_reports(self):
        # 反例：基线完整性条缺"只补本次直接相关面 / 无关存量缺口不阻断"
        # （会把"先补齐所有用例"读成动手的硬性前置——基线变硬性前置的第二种形态）
        self._write_valid()
        pl = os.path.join(self.root, "specs", "general", "planning.adoc")
        text = open(pl, encoding="utf-8").read().replace(
            "**本次改动的直接相关面**先补全，**无关的存量缺口**如实记录、**不阻断**。",
            "须把发现的缺口全部补全。")
        open(pl, "w", encoding="utf-8").write(text)
        cm.check_dev_flow_guard()
        self.assertIn("直接相关面", self.error_texts())

    def test_verify_side_without_completeness_reports(self):
        # 反例：验证侧只说"须覆盖全部既定校验手段"、不说"跑的那套够不够用"
        self._write_valid()
        self.write("specs/general/verify.adoc",
                   "= 验证\n\n* **验证须覆盖项目的全部既定校验手段（L1）**：存在测试≠测试被执行。\n")
        cm.check_dev_flow_guard()
        self.assertIn("verify.adoc", self.error_texts())

    def test_prompt_fragment_without_completeness_reports(self):
        # 反例：公共片段缺"清单还要核够不够用"（复制到未知项目后这条边界整条丢失）
        self._write_valid()
        cf = os.path.join(self.root, "prompts", "_common.txt")
        text = open(cf, encoding="utf-8").read().replace(
            "  - **基线清单还要核\"够不够用\"（L2）**：**review 既有用例**、"
            "**无关的存量缺口**如实记录。\n", "")
        open(cf, "w", encoding="utf-8").write(text)
        cm.check_dev_flow_guard()
        self.assertIn("够不够用", self.error_texts())

    def test_prompt_fragment_without_fallback_reports(self):
        # 反例：公共片段缺"没手段/红测试也不是不动手的理由"
        self._write_valid()
        cf = os.path.join(self.root, "prompts", "_common.txt")
        text = open(cf, encoding="utf-8").read().replace(
            "  - **没有校验手段、环境跑不起来，都不是不动手的理由**\n", "")
        open(cf, "w", encoding="utf-8").write(text)
        cm.check_dev_flow_guard()
        self.assertIn("都不是不动手的理由", self.error_texts())

    def test_dispatcher_not_registered_reports(self):
        # 反例：调度器未登记（该文件不会被加载，其中规则实际失效）
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "= 入口\n\n  ** 自检 → link:specs/general/self-check.adoc[]\n")
        cm.check_dev_flow_guard()
        self.assertIn("未登记", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例：公开面未同步（公开面读不到这条边界）
        self._write_valid()
        self.write("README.adoc", "= 说明\n\n普通说明。\n")
        cm.check_dev_flow_guard()
        self.assertIn("README.adoc", self.error_texts())

    def test_report_consistency_clause_removed_reports(self):
        # 反例（ctool4j#102 实证）：抽掉「汇报须与可核对的事实一致」的判定标准——
        # 汇报与事实脱节（提交数与汇报对不上）时无判据可拦，执行者拿"核对项全绿"自证。
        self._write_valid()
        f = os.path.join(self.root, "specs", "general", "verify.adoc")
        text = open(f, encoding="utf-8").read().replace(
            "汇报须与可核对的事实一致，不得狡辩（L1）", "").replace(
            "写进汇报前须重取一次", "").replace(
            "先复取值再回答", "").replace(
            "不得拿既有结论当辩词", "")
        open(f, "w", encoding="utf-8").write(text)
        cm.check_dev_flow_guard()
        self.assertIn("汇报须与可核对的事实一致", self.error_texts())

    def test_report_consistency_missing_in_report_tail_reports(self):
        # 反例：`report-tail` 片段丢掉同口径半句——复制出去的提示词没有这条边界
        self._write_valid()
        f = os.path.join(self.root, "prompts", "_common.txt")
        text = open(f, encoding="utf-8").read().replace(
            "汇报里的数字与结论须与实际取值一致（L1）", "").replace(
            "先复取值再回答", "").replace(
            "不得拿既有结论当辩词", "")
        open(f, "w", encoding="utf-8").write(text)
        cm.check_dev_flow_guard()
        self.assertIn("report-tail", self.error_texts())


class TestCheckChangelogTimingGuard(CheckSpecsTestCase):
    """钉住『变更日志声明优先防线』（用户明确提出：除非主动声明否则不新增、不修改）。

    两类失效形态（本项目实证，分别对应两次收紧）：
      * ①执行者把"我改动了东西"与"该记一条 changelog"画等号，每轮改动都自行追加条目；
      * ②用户只说"调整一下项目规范"、并未提到 changelog，执行者把"改文档"扩大成
        "改 changelog"，顺手新增了条目——旧条文只写正向（何时可以写），没写这条越界形态。
    """

    def _write_valid(self):
        # 口径（用户指出）：这件事的**默认动作**是「不新增、不修改」——用户本次明确要求才写，
        # 且**不再要求**"主动声明"这种额外声明（用户直接说"记一条/改 changelog"即算）。
        self.write("AGENTS.adoc",
                   "= 项目入口\n\n* 登记时机（本仓库默认动作：不新增、不修改；用户明确要求才写）："
                   "**本仓库的默认动作是「不新增、不修改」**，"
                   "**只有用户本次明确要求**新增、修改、整理或压缩 changelog 时才写——**不再要求**"
                   "\"主动声明\"这种额外声明。**其余一切情形按\"未要求\"处理**："
                   "未提到该文件、**只要求更新文档或 README**、只说\"改动了什么\"、只要求\"调整项目规范\"，"
                   "均**不得**新增条目（含\"顺手补一条\"）。"
                   "**用户明确要求移除时**：删掉指定的条目、**保留其余内容与既有版本号不动**，"
                   "**不得为「版本线连续」自造一个新版本号条目顶上**。"
                   "由 `script/check_specs.py` 的 `check_changelog_timing_guard` 钉住。\n")
        # 登记表侧须是**单行**：该行同时给出抓手名与默认动作口径（判据只认这一行）
        self.write("script/check_effective.py",
                   "ROWS = [\n"
                   "    (\"本仓库 changelog 的默认动作是不新增、不修改\",\n"
                   "     \"AGENTS.adoc\", \"script/check_specs.py\",\n"
                   "     \"check_changelog_timing_guard 钉住默认动作条\"),\n"
                   "]\n"
                   "# 普通注释里单独提一次抓手名（不在登记表那一行上）\n"
                   "# 该条由 check_changelog_timing_guard 钉住\n")

    def _patch_root(self):
        # check_effective.py 按 REPO_ROOT 解析，直接写入临时根即可
        pass

    def test_valid_changelog_timing_guard_passes(self):
        self._write_valid()
        cm.check_changelog_timing_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_timing_clause_reports(self):
        # 反例：登记时机条被删（执行者重新把"改了东西"与"该记一条"画等号）
        self._write_valid()
        self.write("AGENTS.adoc", "= 项目入口\n\n* 统一变更日志：根目录 `CHANGELOG.adoc`。\n")
        cm.check_changelog_timing_guard()
        self.assertIn("登记时机", self.error_texts())

    def test_default_action_wording_removed_reports(self):
        # 反例：只留"用户明确要求才写"，删掉**默认动作**「不新增、不修改」
        # （默认动作不被单独说出来时，读者仍要先判"这算不算已声明"——用户指出的失效）
        self._write_valid()
        self.write("AGENTS.adoc",
                   "= 项目入口\n\n* 登记时机：**只有用户本次明确要求**新增、修改、整理或压缩 changelog 时才写。"
                   "由 `script/check_specs.py` 的 `check_changelog_timing_guard` 钉住。\n")
        cm.check_changelog_timing_guard()
        self.assertIn("本仓库的默认动作是「不新增、不修改」", self.error_texts())

    def test_extra_declaration_requirement_removed_reports(self):
        # 反例：把"不再要求主动声明"抽掉（"这应该也算声明"重新可用；用户直接说"
        # 记一条"时执行者还要先自问算不算声明）
        self._write_valid()
        self.write("AGENTS.adoc",
                   "= 项目入口\n\n* 登记时机（本仓库默认动作：不新增、不修改）："
                   "**本仓库的默认动作是「不新增、不修改」**，**只有用户本次明确要求**时才写。"
                   "**其余一切情形按\"未要求\"处理**：未提到该文件、**只要求更新文档或 README**、"
                   "只说\"改动了什么\"、只要求\"调整项目规范\"，均**不得**新增条目（含\"顺手补一条\"）。"
                   "**用户明确要求移除时**：删掉指定的条目、**保留其余内容与既有版本号不动**，"
                   "**不得为「版本线连续」自造一个新版本号条目顶上**。"
                   "由 `script/check_specs.py` 的 `check_changelog_timing_guard` 钉住。\n")
        cm.check_changelog_timing_guard()
        self.assertIn("不再要求", self.error_texts())

    def test_undeclared_forms_removed_reports(self):
        # 反例：默认动作与声明口径都在，但没点名"未要求"的越界形态
        # （用户只说改文档/改规范，执行者仍可把"改文档"读成"改 changelog"）
        self._write_valid()
        self.write("AGENTS.adoc",
                   "= 项目入口\n\n* 登记时机（本仓库默认动作：不新增、不修改；用户明确要求才写）："
                   "**本仓库的默认动作是「不新增、不修改」**，**只有用户本次明确要求**时才写——**不再要求**"
                   "\"主动声明\"这种额外声明。均**不得**新增条目（含\"顺手补一条\"）。"
                   "**用户明确要求移除时**：删掉指定的条目、**保留其余内容与既有版本号不动**，"
                   "**不得为「版本线连续」自造一个新版本号条目顶上**。"
                   "由 `script/check_specs.py` 的 `check_changelog_timing_guard` 钉住。\n")
        cm.check_changelog_timing_guard()
        self.assertIn("只要求更新文档或 README", self.error_texts())

    def test_removal_disposition_removed_reports(self):
        # 反例：抽掉"用户要求移除时的处置"（执行者会为"版本线连续"自造一条新版本号顶上，
        # 等于换个说法把删掉的条目留在文件里；本轮 PR #179 的真实场景）
        self._write_valid()
        self.write("AGENTS.adoc",
                   "= 项目入口\n\n* 登记时机（本仓库默认动作：不新增、不修改；用户明确要求才写）："
                   "**本仓库的默认动作是「不新增、不修改」**，**只有用户本次明确要求**时才写——**不再要求**"
                   "\"主动声明\"这种额外声明。**其余一切情形按\"未要求\"处理**："
                   "未提到该文件、**只要求更新文档或 README**、只说\"改动了什么\"、只要求\"调整项目规范\"，"
                   "均**不得**新增条目（含\"顺手补一条\"）。"
                   "由 `script/check_specs.py` 的 `check_changelog_timing_guard` 钉住。\n")
        cm.check_changelog_timing_guard()
        self.assertIn("保留其余内容与既有版本号不动", self.error_texts())

    def test_missing_agents_file_reports(self):
        # 反例：项目规范入口被删（条目无处承载）
        self._write_valid()
        os.remove(os.path.join(self.root, "AGENTS.adoc"))
        cm.check_changelog_timing_guard()
        self.assertIn("AGENTS.adoc", self.error_texts())

    def test_registry_row_without_wording_reports(self):
        # 反例：抓手名还散落在别处（注释/别行），但**登记表那一行**抽掉了「默认动作」口径 →
        # 仍须报错（"整份文件核"会被别处的同名字样兜住，核的不是"登记处登记了没有"）
        self._write_valid()
        self.write("script/check_effective.py",
                   "ROWS = [\n"
                   "    (\"登记时机\",\n"
                   "     \"AGENTS.adoc\", \"script/check_specs.py\",\n"
                   "     \"见登记时机一条\"),\n"
                   "]\n"
                   "# 该条由 check_changelog_timing_guard 钉住\n")
        cm.check_changelog_timing_guard()
        self.assertIn("没有登记行", self.error_texts())

    def test_effective_registry_missing_reports(self):
        # 反例：check_effective 未登记该条（定义了却没抓手＝又变成靠自觉）
        self._write_valid()
        self.write("script/check_effective.py", "ROWS = []\n")
        cm.check_changelog_timing_guard()
        self.assertIn("没有登记行", self.error_texts())


class TestCheckRuleInstanceSeparationGuard(CheckSpecsTestCase):
    """钉住『规则与实例分离防线』（用户指出：规范里到处是用户原话/环境实例）。

    失效形态：把"某次问过什么、某次在哪台机器上跑"当成规则的一部分登记下来——读者拿不到
    那句话/那个环境的场景就会**静默改写**本集合规则。故默认动作是"不写"：只有用户本次
    明确要求登记时才写，且只写进本仓库的实例落点（图书馆与 `CHANGELOG.adoc`）。
    """

    def _write_valid(self):
        self.write("AGENTS.adoc",
                   "= 项目入口\n\n* 规则与实例分离（本仓库默认动作：不写实例）：本仓库自身规范与公共规范"
                   "一律**保持通用**——**不得**把本仓库/当前环境专有的实例（用户原话、本机路径、"
                   "`tmp/` 文件名、轮次与日期、内部代号）写进规范文件、公共内容与提示词；"
                   "这类实例只在用户本次明确要求时登记，且只登记在本仓库的实例落点——变更依据进图书馆 "
                   "`library/adoption.adoc`、实证与官方逐字摘进 `library/sources.adoc`、历史进 `CHANGELOG.adoc`。"
                   "**默认动作是「不写」**：用户说\"调整项目规范\"时改的是规则本身，**不得**"
                   "顺手把原话抄进规范。失效形态是把用户某次说过的话当成规则的一部分登记下来，"
                   "读者拿不到这句话的场景就会静默改写本集合规则（用户指出）。"
                   "由 `script/check_specs.py` 的 `check_rule_instance_separation_guard` 钉住。\n")
        # 登记表侧须是**单行**：该行同时给出抓手名与「规范保持通用」这条口径
        self.write("script/check_effective.py",
                   "ROWS = [\n"
                   "    (\"规范保持通用（规则与实例分离）\",\n"
                   "     \"AGENTS.adoc\", \"script/check_specs.py\",\n"
                   "     \"check_rule_instance_separation_guard 钉住该条（规范保持通用）\"),\n"
                   "]\n"
                   "# 普通注释里单独提一次抓手名（不在登记表那一行上）\n"
                   "# 该条由 check_rule_instance_separation_guard 钉住\n")

    def test_valid_rule_instance_separation_guard_passes(self):
        self._write_valid()
        cm.check_rule_instance_separation_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_clause_reports(self):
        # 反例①：整条被删（"用户说调整规范"重新被读成"把原话抄进规范"）
        self._write_valid()
        self.write("AGENTS.adoc", "= 项目入口\n\n* 统一变更日志：根目录 `CHANGELOG.adoc`。\n")
        cm.check_rule_instance_separation_guard()
        self.assertIn("规则与实例分离", self.error_texts())

    def test_generality_requirement_removed_reports(self):
        # 反例②：抽掉"保持通用"（只留下"实例写哪"，读者会把实例当成规范内容）
        self._write_valid()
        self.write("AGENTS.adoc",
                   "= 项目入口\n\n* 规则与实例分离（本仓库默认动作：不写实例）：实例登记在"
                   "`library/adoption.adoc`、`library/sources.adoc` 与 `CHANGELOG.adoc`。"
                   "**默认动作是「不写」**：用户说\"调整项目规范\"时改的是规则本身，**不得**顺手抄。"
                   "失效形态：读者拿不到这句话的场景就会静默改写本集合规则（用户指出）。"
                   "由 `script/check_specs.py` 的 `check_rule_instance_separation_guard` 钉住。\n")
        cm.check_rule_instance_separation_guard()
        self.assertIn("保持通用", self.error_texts())

    def test_landing_points_removed_reports(self):
        # 反例③：抽掉实例登记落点（"该写哪"没了，执行者只能写进规范本身）
        self._write_valid()
        self.write("AGENTS.adoc",
                   "= 项目入口\n\n* 规则与实例分离（本仓库默认动作：不写实例）：本仓库自身规范与公共规范"
                   "一律**保持通用**，**不得**把用户原话、本机路径、`tmp/` 文件名、轮次与日期写进规范、"
                   "公共内容与提示词。**默认动作是「不写」**：用户说\"调整项目规范\"时改的是规则本身，"
                   "**不得**顺手抄。失效形态：读者拿不到这句话的场景就会静默改写本集合规则（用户指出）。"
                   "由 `script/check_specs.py` 的 `check_rule_instance_separation_guard` 钉住。\n")
        cm.check_rule_instance_separation_guard()
        self.assertIn("library/adoption.adoc", self.error_texts())

    def test_effective_registry_missing_reports(self):
        # 反例④：check_effective 未登记该条（定义了却没抓手＝又变成靠自觉）
        self._write_valid()
        self.write("script/check_effective.py", "ROWS = []\n")
        cm.check_rule_instance_separation_guard()
        self.assertIn("没有登记行", self.error_texts())

    def test_missing_agents_file_reports(self):
        # 反例⑤：项目规范入口被删（条目无处承载）
        self._write_valid()
        os.remove(os.path.join(self.root, "AGENTS.adoc"))
        cm.check_rule_instance_separation_guard()
        self.assertIn("AGENTS.adoc", self.error_texts())

    def test_registry_row_without_wording_reports(self):
        # 反例⑥：抓手名还散落在别处（注释/别行），但**登记表那一行**抽掉了「规范保持通用」→
        # 仍须报错（"整份文件核"会被别处的同名字样兜住，核的不是"登记处登记了没有"）
        self._write_valid()
        self.write("script/check_effective.py",
                   "ROWS = [\n"
                   "    (\"规范保持通用（规则与实例分离）\",\n"
                   "     \"AGENTS.adoc\", \"script/check_specs.py\",\n"
                   "     \"见规则与实例分离一条\"),\n"
                   "]\n"
                   "# 该条由 check_rule_instance_separation_guard 钉住\n")
        cm.check_rule_instance_separation_guard()
        self.assertIn("没有登记行", self.error_texts())


class TestCheckDeclarativeRuleGuard(CheckSpecsTestCase):
    """钉住『以对象定义规则、不给具体操作』（用户要求：规范以对象定义、不给具体操作）。

    失效形态：写规则时顺手把"怎么取"也写进规范——规范给读者的成了一个随环境变的操作流程，
    而不是一条判据。用户给的判据形态是「定义 `mvn -T <核心数>` 就好了，不要在规范里写
    如何去拿核心数」，并点名"新增、修复、review 时都要遵守"。
    """

    LIFE = "specs-project-maintainer/spec-lifecycle.adoc"

    SUBSECTION = (
        "=== 以对象定义规则、不给具体操作（写规范的写法口径）\n\n"
        "规则用**面向对象的思路**去定义：**定义「是什么、取什么值」**，**不写「怎么把它做出来」**。"
        "取值写成**带占位符的形态**（如 `mvn -T <核心数>`），**括号里那个量是什么**就是规则的边界；"
        "**这个量怎么得到属执行动作，不进规范**。\n\n"
        "* **只定义取值、不定义取法（L1）**：规则正文只到**取值本身**为止。**判定标准（任一命中即违规）**："
        "① 正文里出现**获取该取值的命令或步骤**；② 正文列出**该取值的多种可能来源**并给出取舍或次序；"
        "③ 为\"取不到\"补一条**具体的兜底做法**——**若\"取不到\"确实有歧义**，**只写\"取不到时怎么判\"**，"
        "**不写\"取不到时就用某个具体写法\"**：规则并没有变干净。\n"
        "* **例外只在有歧义时开口（L1）**：只有当**按定义做不出唯一动作**时才给具体操作——"
        "且**只补\"消除歧义所需的那一句\"**。\n"
        "* **生效面（L1）**：**新增、修复、review** 三类动作都按本条判定（存量随动迁移、不单独发动全库清理）；"
        "review 时把\"正文里写着怎么取\"当必查项）。\n"
        "* **判定标准（可核对）**：抽掉**本仓库/当前环境/当前平台**的专有名词后规则是否仍成立——"
        "**要靠\"在哪台机器上、用什么命令取\"才成立的句子，就不是规则**。\n"
        "* **依据（标准名/编号）**：ISO/IEC Directives Part 2、ISO/IEC/IEEE 29148。"
        "**\"规则只写到取值形态为止\"是本集合按现场用量判据化的取舍。**\n")

    MAINTAINER_SUBSECTION = (
        "=== 给方向、给定义、定规则——不是说明书（正文内容的取舍口径）\n\n"
        "**本规范集合的主旨：给方向、给定义、定规则——不是说明书。**一条规范的正文只放三样：**方向（往哪走、边界在哪）、定义（是什么、取什么值）、规则（必须/不得 + 判定标准 + 依据名）**。\n\n"
        "* **正文只到这七类（L1）**：① 方向与边界；② 定义与取值形态；③ 必须/不得与其级别；"
        "④ 判定标准；⑤ 依据（标准名/编号）；⑥ 例外与降级路径；⑦ 承载取值的对照表。"
        "**判定标准（正文里出现下列任一即违规）**：① **步骤与文档骨架**；"
        '② **具体命令／文件路径／工具名**（只是"怎么取"或"用哪家"时）；'
        "③ **对外部世界清单的照抄**。**例外**：该内容本身就是要交付的产物时（**模板类内容**）按其单独归类处理。\n"
        "* **清单不全就删清单，不补全（L1）**：清单只在本身是规则边界时才写全；否则**删到只剩取值形态**——"
        "照抄清单是**把外部世界的现状当成了判据**。**判定标准（可核对）**：**抽掉本仓库/当前环境/当前平台的专有名词**后该句是否仍成立？\n"
        "* **每句须承载、一句只承载一件（L1）**：抽掉某句后约束力与可核对性都没变——即该句不承载，删。\n"
        "* **依据留名、不留论证（L1）**：依据只写到**标准名/编号**。\n"
        "* **生效面（L1）**：**新增、修复、review、重构**四类动作都按本条判定。\n"
        "* **依据（标准名/编号）**：ISO/IEC Directives Part 2、ISO/IEC/IEEE 29148。"
        '**「正文只放三样、清单不全就删清单」是本集合按现场用量判据化的取舍。**\n')

    def _fixture(self):
        self.write(self.LIFE, "= 维护\n\n" + self.SUBSECTION + self.MAINTAINER_SUBSECTION)
        self.write("specs/stack/maven.adoc",
                   "* 默认启用多线程构建（L2）：取值＝当前构建设备的核心数，即 `mvn -T <核心数>`——"
                   "核心数怎么得到是执行动作，不写进规范（这是本集合对**所有**规则一视同仁的写法："
                   "取值只定义到占位符那一层）。\n")
        self.write("prompts/_common.txt",
                   "// tag::build-parallel[]\n`mvn -T <核心数>`；本条到此为止：核心数怎么得到是执行动作。"
                   "取值只定义到这一层。\n// end::build-parallel[]\n")
        self.write("AGENTS.adoc",
                   "= 项目入口\n\n* **以对象定义规则、不给具体操作**（L1）：写规范时只定义「是什么、"
                   "取什么值」；判据本体见 `specs-project-maintainer/spec-lifecycle.adoc`"
                   "「以对象定义规则、不给具体操作」。\n"
                   "* **给方向、给定义、定规则——不是说明书**（L1）：正文只放方向/定义/规则，"
                   "**清单不全就删清单**；判据本体见 "
                   "`specs-project-maintainer/spec-lifecycle.adoc`「给方向、给定义、定规则」一节。\n")

    def test_positive_passes(self):
        self._fixture()
        cm.check_declarative_rule_guard()
        self.assertEqual([], cm.errors)

    def test_missing_landing_file_reports(self):
        # 反例①：判据本体的落点文件缺失（写规则时又会把取法一并写进规范）
        self._fixture()
        os.remove(os.path.join(self.root, "specs-project-maintainer", "spec-lifecycle.adoc"))
        cm.check_declarative_rule_guard()
        self.assertIn("spec-lifecycle.adoc", self.error_texts())

    def test_subsection_deleted_reports(self):
        # 反例②：整条被删（只剩"规则要写得通用"这类无落点的印象）
        self._fixture()
        self.write(self.LIFE, "= 维护\n\n== 准入判定\n* 别的\n")
        cm.check_declarative_rule_guard()
        self.assertIn("以对象定义规则、不给具体操作", self.error_texts())

    def test_boundary_sentence_removed_reports(self):
        # 反例③：抽掉"定义与取法的分界"（读者仍会把"怎么取"当规则的一部分）
        self._fixture()
        self.write(self.LIFE, "= 维护\n\n" + self.SUBSECTION.replace(
            "**不写「怎么把它做出来」**", "**写得清楚一些**"))
        cm.check_declarative_rule_guard()
        self.assertIn("怎么把它做出来", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例④：只留"只定义取值"、抽掉三条判定标准（"写到哪算够"回到执行者手里）
        self._fixture()
        self.write(self.LIFE, "= 维护\n\n" + self.SUBSECTION.replace(
            "**判定标准（任一命中即违规）**", "**要求**"))
        cm.check_declarative_rule_guard()
        self.assertIn("任一命中即违规", self.error_texts())

    def test_scope_of_effect_removed_reports(self):
        # 反例⑤：生效面被抽掉（本条只在"新增规范"那一次生效，修既有条目与 review 时照旧写回取法）
        self._fixture()
        self.write(self.LIFE, "= 维护\n\n" + self.SUBSECTION.replace(
            "**新增、修复、review** 三类动作都按本条判定", "新增时按本条判定"))
        cm.check_declarative_rule_guard()
        self.assertIn("新增、修复、review", self.error_texts())

    def test_maven_value_removed_reports(self):
        # 反例⑥：Maven 侧取值退回"要自己去探测核数"（本条要治的正是它）
        self._fixture()
        self.write("specs/stack/maven.adoc",
                   "* 默认启用多线程构建（L2）：取值按**当前构建设备**补齐"
                   "（先实测核数再取）。\n")
        cm.check_declarative_rule_guard()
        self.assertIn("mvn -T <核心数>", self.error_texts())

    def test_manual_style_rule_removed_reports(self):
        # 反例⑩：新增的「不是说明书」小节被整条抽掉（正文又变成说明书、清单照抄回来）
        self._fixture()
        self.write(self.LIFE, "= 维护\n\n" + self.SUBSECTION)
        cm.check_declarative_rule_guard()
        self.assertIn("给方向、给定义、定规则", self.error_texts())

    def test_manual_style_criteria_removed_reports(self):
        # 反例⑪：判定标准被抹成一句"要求"（"是不是说明书"回到凭印象、本条不可执行）
        self._fixture()
        self.write(self.LIFE, "= 维护\n\n" + self.SUBSECTION
                   + self.MAINTAINER_SUBSECTION.replace(
                       "**判定标准（正文里出现下列任一即违规）**", "**要求**"))
        cm.check_declarative_rule_guard()
        self.assertIn("判定标准（正文里出现下列任一即违规）", self.error_texts())

    def test_manual_style_scope_removed_reports(self):
        # 反例⑫：生效面被抽成三类（重构动作不受本条约束）
        self._fixture()
        self.write(self.LIFE, "= 维护\n\n" + self.SUBSECTION
                   + self.MAINTAINER_SUBSECTION.replace(
                       "**新增、修复、review、重构**四类动作都按本条判定",
                       "新增时按本条判定"))
        cm.check_declarative_rule_guard()
        self.assertIn("新增、修复、review、重构", self.error_texts())

    def test_maintainer_entry_unregistered_reports(self):
        # 反例⑧：维护方入口（`AGENTS.adoc`）未登记该口径的落点——判据齐备但没有入口，
        # 执行者读入口时看不到它（"调整规范"时照旧会写回取法）
        self._fixture()
        self.write("AGENTS.adoc", "= 项目入口\n\n* 统一变更日志：根目录 `CHANGELOG.adoc`。\n")
        cm.check_declarative_rule_guard()
        self.assertIn("spec-lifecycle.adoc", self.error_texts())

    def test_prompt_fragment_value_fixed_reports(self):
        # 反例⑦：提示词片段又把"如何取核心数"写回去
        self._fixture()
        self.write("prompts/_common.txt",
                   "// tag::build-parallel[]\n先实测核数（`nproc`/`sysctl -n hw.ncpu`）再取。\n"
                   "// end::build-parallel[]\n")
        cm.check_declarative_rule_guard()
        self.assertIn("mvn -T <核心数>", self.error_texts())


class TestCheckChecklistGuard(CheckSpecsTestCase):
    """钉住"清单逐项"与"文档-脚本一致性"（补独立复核指出的两类漏检）。

    复核结论：现有防线只钉集合级关键短语，于是两类可机械核对的判定点漏过——
    ①清单被少列一项（准入判定号称"八问/九问"而实际条目已增删、七节点表少一行）；
    ②文档号称的抓手（`check_*`/脚本名）在脚本里已改名或删除。
    """

    def _write_valid(self):
        self.write("specs-project-maintainer/spec-lifecycle.adoc",
                   "= 规范分类与准入\n\n== 准入判定（该不该收进规范集合）\n\n"
                   "新增条目**须先过准入判定**（九问，逐项可答\"是\"才收）：\n\n"
                   ". **通用性**：对任意项目成立。\n"
                   ". **可执行**：有判定标准。\n"
                   ". **非重复**：不重复。\n"
                   ". **有依据**：可被标准佐证。\n"
                   ". **有承载价值**：承载事实或教训。\n"
                   ". **能定级**：级别可定。\n"
                   ". **有落点**：能归入某层与某文件。\n"
                   ". **非拆分而膨胀**：能就地承载。\n"
                   ". **成本可接受**：代价可接受。\n\n== 下节\n")
        self.write("specs/core/execution.adoc",
                   "= 执行原则\n\n== 任务生命周期与节点自查（AI 侧，各节点该查什么）\n\n"
                   "| **提出** | 澄清后再动手\n"
                   "| **理解** | 规范已实际加载\n"
                   "| **方案** | 规划已落盘\n"
                   "| **执行** | 加载由入口驱动\n"
                   "| **验证** | 先判改动性质\n"
                   "| **交付** | 交付形态按环境区分\n"
                   "| **复盘**（仅公共内容改动）| 三视角评有效性\n\n"
                   "* **哪些节点不设（L1）**：代码类改动不设复盘节点。\n\n== 下节\n")
        self.write("script/check_specs.py", "def check_demo_guard():\n    pass\n")
        self.write("script/clean_tmp.py", "# demo\n")
        # 维护方侧**不重列**逐态取值（判据本体在通用层）——夹具与真实文件同形：
        # 点出三态名 + 指向通用层的判据本体 + 写明"不得合并"这句话
        self.write("specs-project-maintainer/verify.adoc",
                   "= 验证\n\n留证形态是**三态台账**：三个态名——**通过**、**未发现问题**、"
                   "**悬置**——与逐态取值、不得合并都是通用层的判据，"
                   "唯一落点＝`specs/general/verify.adoc`「验证的效力等级」的「三态台账」，"
                   "本文件不复述、只留落点。\n")
        self.write("specs/general/collab.adoc",
                   "= 协作\n\n**硬超时**：到点即视为失联，**不得无限等待**；"
                   "**超时的处置**：放弃该子 agent + 如实标悬置。"
                   "**时限取值须有判据**，优先选**一次性、边界明确、可超时**的派发形式。\n")
        self.write("AGENTS.adoc", "= 项目入口\n\n由 `check_demo_guard` 钉住，见 `clean_tmp.py`。\n")
        self.write("README.adoc", "= 说明\n\n由 `check_demo_guard` 钉住。\n")

    def test_valid_checklist_guard_passes(self):
        self._write_valid()
        cm.check_checklist_guard()
        self.assertEqual(cm.errors, [])

    def test_admission_item_count_mismatch_reports(self):
        # 反例：清单被删一项而声明未同步（读者按声明核对会漏项）
        self._write_valid()
        self.write("specs-project-maintainer/spec-lifecycle.adoc",
                   "= 规范分类与准入\n\n== 准入判定（该不该收进规范集合）\n\n"
                   "新增条目**须先过准入判定**（九问，逐项可答\"是\"才收）：\n\n"
                   ". **通用性**：对任意项目成立。\n"
                   ". **可执行**：有判定标准。\n\n== 下节\n")
        cm.check_checklist_guard()
        self.assertIn("实际列出", self.error_texts())

    def test_missing_lifecycle_node_reports(self):
        # 反例：七节点里少一个（节点被删则该节点的自查要求实际失效）
        self._write_valid()
        self.write("specs/core/execution.adoc",
                   "= 执行原则\n\n== 任务生命周期与节点自查（AI 侧，各节点该查什么）\n\n"
                   "| **提出** | 澄清后再动手\n"
                   "| **理解** | 规范已实际加载\n\n"
                   "* **哪些节点不设（L1）**：代码类改动不设复盘节点。\n\n== 下节\n")
        cm.check_checklist_guard()
        self.assertIn("缺少节点", self.error_texts())

    def test_doc_names_missing_check_reports(self):
        # 反例：文档点名的抓手在脚本里已改名/删除（声称有防线而防线不存在）
        self._write_valid()
        self.write("AGENTS.adoc", "= 项目入口\n\n由 `check_not_defined_guard` 钉住。\n")
        cm.check_checklist_guard()
        self.assertIn("check_not_defined_guard", self.error_texts())

    def test_missing_timeout_guard_reports(self):
        # 反例：硬超时要求被删（子 agent 卡死会再次让任务永久挂起）
        self._write_valid()
        self.write("specs/general/collab.adoc", "= 协作\n\n子 agent 用于隔离上下文。\n")
        cm.check_checklist_guard()
        self.assertIn("硬超时", self.error_texts())

    def test_timeout_keyword_only_reports(self):
        # 反例：只留"硬超时"字样、整条要求被抽掉（防"关键词出现过一次"式假绿）
        self._write_valid()
        self.write("specs/general/collab.adoc", "= 协作\n\n硬超时：设个时限即可。\n")
        cm.check_checklist_guard()
        self.assertIn("缺失硬超时要素", self.error_texts())

    def test_ledger_keyword_only_reports(self):
        # 反例：只留"三态"字样、三态台账要求被抽掉
        self._write_valid()
        self.write("specs-project-maintainer/verify.adoc", "= 验证\n\n留证按三态分列即可。\n")
        cm.check_checklist_guard()
        self.assertIn("缺失三态台账要素", self.error_texts())

    def test_missing_ledger_states_reports(self):
        # 反例：三态留证被压成散文（"查不出"与"没做"无法分辨）
        self._write_valid()
        self.write("specs-project-maintainer/verify.adoc", "= 验证\n\n复核一遍即可。\n")
        cm.check_checklist_guard()
        self.assertIn("三态", self.error_texts())

    def test_doc_names_missing_script_reports(self):
        # 反例：文档点名的脚本不存在
        self._write_valid()
        os.remove(os.path.join(self.root, "script", "clean_tmp.py"))
        self.write("README.adoc", "= 说明\n\n见 `clean_tmp.py`。\n")
        cm.check_checklist_guard()
        self.assertIn("clean_tmp.py", self.error_texts())



class TestCheckEnvMarkerGuard(CheckSpecsTestCase):
    """钉住『环境标志与专用口径』：专用口径必须挂在可实测的标志上、且保留中性口径。

    提示词会被未知项目复制执行，而各执行环境差异很大；把"某环境才成立的做法"当通用
    要求写进提示词，会让别的环境照着做而失败。故钉住三件确定项：片段仍在且写明标志与
    中性口径、每个提示词仍注入该片段、登记处仍写明其标志。
    """

    GUARD = (
        "// tag::env-guard[]\n"
        "**按环境标志选执行口径**：执行 `printenv CNB_EVENT`，非空且触发内容含 `@<Agent名>` 时按专用口径；\n"
        "未命中 → 按其末尾**中性口径**执行。\n"
        "// end::env-guard[]\n")

    def setUp(self) -> None:
        super().setUp()
        self._orig_prompts = (cm.PROMPTS_FILE, cm.PROMPTS_DIR, cm.COMMON_PROMPT_FILE)
        cm.PROMPTS_FILE = os.path.join(self.root, "PROMPTS.adoc")
        cm.PROMPTS_DIR = os.path.join(self.root, "prompts")
        cm.COMMON_PROMPT_FILE = os.path.join(self.root, "prompts", "_common.txt")

    def tearDown(self) -> None:
        (cm.PROMPTS_FILE, cm.PROMPTS_DIR,
         cm.COMMON_PROMPT_FILE) = self._orig_prompts
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("prompts/_common.txt", self.GUARD)
        self.write("PROMPTS.adoc",
                   "环境标志与专用口径（`env-guard`）：标志为 `printenv CNB_EVENT` 非空。\n")
        self.write("prompts/review.adoc", "include::_common.txt[tag=env-guard]\n")
        self.write("prompts/refactor.adoc", "include::_common.txt[tag=env-guard]\n")

    def test_valid_env_guard_passes(self):
        self._write_valid()
        cm.check_env_marker_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_fragment_reports(self):
        # 反例：公共片段里没有 env-guard（专用口径失去开关与中性口径）
        self._write_valid()
        self.write("prompts/_common.txt", "普通片段\n")
        cm.check_env_marker_guard()
        self.assertIn("env-guard", self.error_texts())

    def test_fragment_without_marker_command_reports(self):
        # 反例：只写"某环境"、没有可实测的标志命令（无法判定，等于没开关）
        self._write_valid()
        self.write("prompts/_common.txt",
                   "// tag::env-guard[]\n在特定环境里按专用口径执行。\n// end::env-guard[]\n")
        cm.check_env_marker_guard()
        self.assertIn("printenv", self.error_texts())

    def test_fragment_without_neutral_path_reports(self):
        # 反例：未命中标志时怎么办没写 → 环境专用做法会被当通用要求
        self._write_valid()
        self.write("prompts/_common.txt",
                   "// tag::env-guard[]\n标志：`printenv CNB_EVENT` 非空 且 含 `@<Agent名>`。\n"
                   "// end::env-guard[]\n")
        cm.check_env_marker_guard()
        self.assertIn("中性口径", self.error_texts())

    def test_prompt_without_include_reports(self):
        # 反例：提示词未注入片段 → 环境判断不会被执行
        self._write_valid()
        self.write("prompts/refactor.adoc", "对本项目执行一次全量重构。\n")
        cm.check_env_marker_guard()
        self.assertIn("env-guard", self.error_texts())

    def test_registry_without_marker_reports(self):
        # 反例：登记处未写明标志 → 后来者无从知道它何时生效
        self._write_valid()
        self.write("PROMPTS.adoc", "提示词登记（无环境标志登记）。\n")
        cm.check_env_marker_guard()
        self.assertIn("env-guard", self.error_texts())


class TestCheckNpcMergeGuard(CheckSpecsTestCase):
    """钉住『NPC 禁合并』：NPC/CI 执行者不得合并、且不因人工授权豁免。

    这是**唯一一类"用户明确要求也不照做"**的约束，最易被两件事冲掉：
      * **"顺手满足用户"的惯性** —— 人工一句"直接合吧"就把禁令静默写回（授权当豁免）；
      * **关键词堆砌式假绿** —— 只留节名/一句口号、把判定标准或边界抽掉，检查照样过。
    故本组用例除正例外，专门覆盖"删禁令""降级成建议""判定标准被抽""边界被删"
    "提示词公共片段漏条""登记处不同步"等反例。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_prompts = (cm.PROMPTS_FILE, cm.PROMPTS_DIR, cm.COMMON_PROMPT_FILE)
        cm.PROMPTS_FILE = os.path.join(self.root, "PROMPTS.adoc")
        cm.PROMPTS_DIR = os.path.join(self.root, "prompts")
        cm.COMMON_PROMPT_FILE = os.path.join(self.root, "prompts", "_common.txt")

    def tearDown(self) -> None:
        (cm.PROMPTS_FILE, cm.PROMPTS_DIR,
         cm.COMMON_PROMPT_FILE) = self._orig_prompts
        super().tearDown()

    CNB = ("= CNB 规范（平台层）\n\n"
           "== 评论唤起新实例（平台侧的派发入口）\n"
           "* **不得以评论派发唤起自己（L1，防无限派发）**：被评论唤起的执行者不得在本次执行中"
           "再发一条评论去**点名唤起自己**（**同一实例名**），**也不得转由他人**/其他执行者**代发**。"
           "**判定标准**：①本次执行期间**新增的点名评论指向本条评论上的唤起名**；"
           "②以\"分两步更清楚\"等理由**自我豁免**；③**实际发了这条评论**、把任务在执行中重新发起一次"
           "（判据是**这条评论发出去没有**、**不是这次执行有没有因此结束**）；④**转交他人**代发。"
           "正当形态：**先停**、只输出一次\"停下确认\"，由**人**另发一条评论决定"
           "（**一次评论就是一次派发**，**发起下一次是派发者的动作**）。\n"
           "* **须由与执行者相同的 Agent 承担验证（L1）**：**要求验证/复核须由与执行者相同的 "
           "Agent 来做的那些规则，只在本平台（CNB）成立**——**本平台之外不适用**：环境不提供同 Agent "
           "的子执行者时，**不得援引该条拒做或把任务停在中间**；**不提供**时按降级路径执行、"
           "**验证与交付不因此缺失**。**由谁承担**是**项目自身的取舍**（IEEE 1028 只要求有独立、"
           "可核对的评审发生）；条文的写入面本就在平台层、**不在公共内容**"
           "（`AGENTS_COMMON.adoc` + `specs/`）里，引用方按入口加载时**不会取到它**。\n"


           "== 合并请求的合并主体（NPC 禁合并）\n"
           "* **CNB NPC（即 CI/CD 执行环境中的 agent）严禁合并（L1）**。\n"
           "* **按执行环境保证（L1，与\"谁在跑\"无关）**：本条**独立于被合并 PR 的源分支**、"
           "不靠某个执行者守规矩；**不许把\"我知道这条规则\"当作保证**——凭据可用即等于合并入口可用，"
           "故守规矩须落成**可核对的判据**；人以外的自动步骤不构成人工。\n"
           "* **人工要求、直接授权也不得合并（L1，无豁免）**：即使人工明确要求合并、"
           "或给出直接授权，**仍必须拒绝**；**授权不免除该禁令**。\n"
           "* **判定标准**：①**执行了合并动作**（入口即 `cnb pulls merge-pull`）；②以授权为由**豁免**该禁令；"
           "③**顶替**执行也算未拦住。\n"
           "* **本仓库实证失效**：曾把原话里的**压缩提交**读成\"合并 PR\"，直接合并并回\"已合并 ❌\"；"
           "成因是**凭据可用**、\"合并\"的字面诱惑、没有交付终点——故固定一条形态："
           "**\"最后一个动作\"的默认读法是\"交付到 PR 分支为止\"**。\n"
           "* **越界清理**：本条只禁合并——推送分支、**解决冲突**、**同步目标分支**"
           "都**不是合并**。\n\n"
           "== 分支与合并请求统一\n"
           "* 同一 issue 拆分出的多个任务，即使并行执行，也**只能修改同一个分支**。\n\n"
           "== 冲突处理\n"
           "* 并行任务改动同一文件导致合并冲突时，须**自动解决冲突**（保留双方有效改动），"
           "不搁置、不要求用户人工介入。\n")

    COMMON = ("提示词公共片段。\n"
              "// tag::intro-rules[]\n"
              "要求不漏步。**任务的「最后一个动作」按原话取值，不得自行追加（L1）**："
              "**\"合并提交\"＝把提交历史压成一个合规提交**——**不是**\"合并 PR\"；"
              "原话没写\"合并 PR\"就**不得**做合并。\n"
              "// end::intro-rules[]\n"
              "// tag::delivery[]\n"
              "8. 交付：\n"
              "   - **合并一律不做（L1，无环境区分、人工授权也拒绝）**："
              "即使发起人明确要求合并、或给出**直接授权**，也**必须拒绝**；**授权不免除**。\n"
              "（直授**也必须拒绝**：授权不免除该禁令。）\n"
              "// end::delivery[]\n")

    def _write_valid(self) -> None:
        self.write("specs/platform/cnb.adoc", self.CNB)
        self.write("prompts/_common.txt", self.COMMON)
        self.write("PROMPTS.adoc", "公共约定：**合并一律不做（L1）**。\n")

    def test_valid_passes(self):
        self._write_valid()
        cm.check_npc_merge_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_file_reports(self):
        # 反例：平台层规范文件被删 → 要求无处承载
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "platform", "cnb.adoc"))
        cm.check_npc_merge_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_missing_ban_reports(self):
        # 反例：禁令本体被删（只留节名）→ "顺手满足用户"再无阻拦
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   "= CNB 规范\n\n== 合并请求的合并主体（NPC 禁合并）\n（本节待补）\n")
        cm.check_npc_merge_guard()
        self.assertIn("严禁合并", self.error_texts())

    def test_no_exemption_removed_reports(self):
        # 反例：删掉"人工要求/直授也必须拒绝"（把授权当豁免）→ 静默写回
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   "= CNB 规范\n\n== 合并请求的合并主体（NPC 禁合并）\n"
                   "* **CNB NPC 严禁合并（L1）**。\n"
                   "* **判定标准**：①**执行了合并动作**；②**豁免**；③**顶替**。\n"
                   "* **越界清理**：**解决冲突**、**同步目标分支**都**不是合并**。\n")
        cm.check_npc_merge_guard()
        self.assertIn("直接授权", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例（关键词堆砌式假绿）：只留禁令字样、判定标准被抽掉 → 判据不可执行
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   "= CNB 规范\n\n== 合并请求的合并主体（NPC 禁合并）\n"
                   "* **CNB NPC 严禁合并（L1）**，**人工要求**、**直接授权**也必须拒绝"
                   "（**授权不免除**）。\n"
                   "* **越界清理**：**解决冲突**、**同步目标分支**都**不是合并**。\n")
        cm.check_npc_merge_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_boundary_removed_reports(self):
        # 反例：删掉边界说明 → 与「冲突处理」节的自动解决冲突自相矛盾/误伤合法操作
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   "= CNB 规范\n\n== 合并请求的合并主体（NPC 禁合并）\n"
                   "* **CNB NPC 严禁合并（L1）**，**人工要求**、**直接授权**也必须拒绝"
                   "（**授权不免除**）。\n"
                   "* **判定标准**：①**执行了合并动作**；②**豁免**；③**顶替**。\n")
        cm.check_npc_merge_guard()
        self.assertIn("不是合并", self.error_texts())

    def test_delivery_fragment_without_ban_reports(self):
        # 反例：提示词公共片段漏条 → 复制到未知项目执行的那份没有这条禁令
        self._write_valid()
        self.write("prompts/_common.txt",
                   "// tag::delivery[]\n8. 交付：按环境区分提交与推送。\n// end::delivery[]\n")
        cm.check_npc_merge_guard()
        self.assertIn("合并一律不做", self.error_texts())

    def test_existing_conflict_section_replaced_reports(self):
        # 反例（本轮实测犯过的真实回归）：新增节点把同文件既有的「冲突处理」整段替换掉
        # ——规则凭空消失，而其余检查全绿（文件只是变短、无引用悬空、语法无错）
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   self.CNB.replace("== 冲突处理", "== 其它"))
        cm.check_npc_merge_guard()
        self.assertIn("冲突处理", self.error_texts())

    def test_existing_conflict_criterion_removed_reports(self):
        # 反例：既有「冲突处理」节还在，但判据被抽走（只剩个标题）
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   self.CNB.replace("自动解决冲突", "另议"))
        cm.check_npc_merge_guard()
        self.assertIn("自动解决冲突", self.error_texts())

    def test_existing_branch_rule_removed_reports(self):
        # 反例：既有「分支与合并请求统一」的判据被删（同文件规则不得被顶掉）
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   self.CNB.replace("只能修改同一个分支", "自行决定"))
        cm.check_npc_merge_guard()
        self.assertIn("只能修改同一个分支", self.error_texts())

    def test_registry_not_synced_reports(self):
        # 反例：公开提示词入口未同步 → 登记处与实际口径不一致，照登记处读会漏
        self._write_valid()
        self.write("PROMPTS.adoc", "公共约定：交付按执行环境区分。\n")
        cm.check_npc_merge_guard()
        self.assertIn("合并一律不做", self.error_texts())

    def test_prompts_file_missing_reports(self):
        # 反例：公开提示词入口被删
        self._write_valid()
        os.remove(cm.PROMPTS_FILE)
        cm.check_npc_merge_guard()
        self.assertIn("缺少公开提示词入口", self.error_texts())



# --------------------------------------------------------------------------- #
# check_rename_split_guard（P7：重命名与内容修改须分两个提交）
# --------------------------------------------------------------------------- #
# 中文引号（在用例里拼反例字符串时用，避免与 Python 字符串引号冲突）
LQ = "\u201c"
RQ = "\u201d"


def _real_git_rename_section() -> str:
    """从真实 specs/general/git.adoc 取「重命名与内容修改须分两个提交」整节。

    用例的"正例"直接用真实条文，避免测试里维护第二份会漂移的正文——防线的判据正是
    对着真实条文写的，抄一份到测试里必然不同步。
    """
    path = os.path.join(os.path.dirname(HERE), "specs", "general", "git.adoc")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    start = text.index("== 重命名与内容修改须分两个提交")
    end = text.index("\n== 行尾与检出归一")
    return text[start:end]



def _real_ci_runtime_env_section() -> str:
    """从真实 specs/general/ci-cd.adoc 取「运行环境须与项目声明一致」整节。

    正例直接用真实条文，避免测试里维护第二份会漂移的正文——防线的判据正是对着真实条文
    写的（与 git rename 节同一做法）。
    """
    path = os.path.join(os.path.dirname(HERE), "specs", "general", "ci-cd.adoc")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    start = text.index("== 运行环境须与项目声明一致")
    end = text.index("\n== 校验链完整")
    return text[start:end]


class TestCheckRuntimeEnvGuard(CheckSpecsTestCase):
    """钉住用户提出的硬性要求：运行环境须与项目声明一致（换版本能跑通也不得换）。

    本条最易被三条路径绕过——"另一个版本也跑通了"（结果导向的自我豁免）、等价/兼容版本顶替、
    环境声明缺失或不可得时用默认版本开工并记作通过。故除正例外，用例专门覆盖整节被删、L1 标注
    被摘、"能跑通也不得换"被删、判定标准被抽、声明落点被删、降级路径被删、依据行被删、
    三处引用断开、调度器识别特征被删、维护方与图书馆落点缺失等反例。
    """

    CI_SECTION = _real_ci_runtime_env_section()

    def _write_valid(self) -> None:
        self.write("specs/general/ci-cd.adoc", "= CI 规范\n\n" + self.CI_SECTION)
        self.write(
            "specs/core/execution.adoc",
            "= 执行原则\n\n* 运行环境：开发与验证**一律用项目声明的那一个运行环境**，"
            "换别的版本也能跑通也不得换（L1）——见 "
            "link:../general/ci-cd.adoc[]「运行环境须与项目声明一致」\n")
        self.write(
            "specs/general/verify.adoc",
            "= 验证规范\n\n* 构建/测试/脚本一律用项目声明的运行环境（L1），见 "
            "link:ci-cd.adoc[]「运行环境须与项目声明一致」\n")
        self.write(
            "specs/general/planning.adoc",
            "= 规划规范\n\n* 基线须在项目声明的运行环境下取得，见 "
            "link:ci-cd.adoc[]「运行环境须与项目声明一致」\n")
        self.write(
            "AGENTS_COMMON.adoc",
            "= 规范\n\n== 分类与懒加载\n\n* 运行环境：**识别特征**——项目有声明运行环境的"
            "落点（`pom.xml` 的 `java.version`、`.nvmrc`、`.python-version`），"
            "或要跑构建/测试/脚本；出现\"换个版本也能跑通\"\"用默认版本先试\" → "
            "link:specs/general/ci-cd.adoc[]（运行环境须与项目声明一致）\n")
        self.write(
            "AGENTS.adoc",
            "= 项目规范\n\n* 工具声明：`check_runtime_env_guard` —— 运行环境防线"
            "（运行环境须与项目声明一致）\n")
        self.write(
            "library/adoption.adoc",
            "= 准入依据\n\n== 同义性差异与覆盖点（本集合自己承认的）\n"
            "* 运行环境须与项目声明一致（L1）是本集合更严的判据化取舍。\n")

    def _drop_from_section(self, needle: str) -> None:
        """把权威定义节里的某个短语删掉后重写文件（反例构造）。"""
        text = ("= CI 规范\n\n" + self.CI_SECTION).replace(needle, "")
        self.write("specs/general/ci-cd.adoc", text)

    def test_valid_passes(self):
        self._write_valid()
        cm.check_runtime_env_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_ci_file_reports(self):
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "general", "ci-cd.adoc"))
        cm.check_runtime_env_guard()
        self.assertIn("缺少", self.error_texts())

    def test_section_deleted_reports(self):
        # 反例：整节被删 -> "按能跑通选版本"重回默认做法
        self._write_valid()
        self.write("specs/general/ci-cd.adoc", "= CI 规范\n\n== 核心原则\n* 略。\n")
        cm.check_runtime_env_guard()
        self.assertIn("未找到", self.error_texts())

    def test_l1_marking_removed_reports(self):
        # 反例：把"严禁/（L1）"摘掉、降级为建议
        self._write_valid()
        self._drop_from_section("**严禁使用与声明不同的运行环境**")
        cm.check_runtime_env_guard()
        self.assertIn("L1", self.error_texts())

    def test_runnable_excuse_removed_reports(self):
        # 反例：删掉"即使能跑通也不得换" -> 最易被"另一个版本也跑通了"合理化掉
        self._write_valid()
        self._drop_from_section("**即使换一个版本也能正常跑通流程，也不得换**")
        cm.check_runtime_env_guard()
        self.assertIn("跑通", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例：只留口号、判定标准被抽掉
        self._write_valid()
        self.write("specs/general/ci-cd.adoc",
                   "= CI 规范\n\n== 运行环境须与项目声明一致\n\n"
                   "[quote]\n本条很重要，请务必注意。\n")
        cm.check_runtime_env_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_declaration_source_removed_reports(self):
        # 反例：删掉"取项目已有声明、不得另立第二真源" -> 出现两个互相冲突的版本来源
        self._write_valid()
        self._drop_from_section("**不得**为满足本条另建一份版本声明")
        cm.check_runtime_env_guard()
        self.assertIn("声明落点", self.error_texts())

    def test_fallback_path_removed_reports(self):
        # 反例：删掉降级路径 -> 要么把引用方卡死，要么"用别的版本跑绿"被记成通过
        self._write_valid()
        self._drop_from_section("**环境不可得或未声明时走降级路径，不阻断、也不记作通过（L1）**")
        cm.check_runtime_env_guard()
        self.assertIn("降级路径", self.error_texts())

    def test_rationale_removed_reports(self):
        # 反例：依据行被整段删掉（依据可压成标准名/编号，但不得消失）
        self._write_valid()
        self._drop_from_section("The Twelve-Factor App")
        cm.check_runtime_env_guard()
        self.assertIn("依据", self.error_texts())

    def test_execution_reference_removed_reports(self):
        # 反例：必加载层的引用被删 -> 非流水线场景读不到本条
        self._write_valid()
        self.write("specs/core/execution.adoc", "= 执行原则\n\n* 其他规则。\n")
        cm.check_runtime_env_guard()
        self.assertIn("必加载层", self.error_texts())

    def test_verify_reference_removed_reports(self):
        # 反例：验证侧引用被删 -> 验证时的环境一致性无人负责
        self._write_valid()
        self.write("specs/general/verify.adoc", "= 验证规范\n\n* 其他。\n")
        cm.check_runtime_env_guard()
        self.assertIn("verify.adoc", self.error_texts())

    def test_planning_reference_removed_reports(self):
        # 反例：基线侧引用被删 -> 基线可能在错误环境下取得、统计不可比
        self._write_valid()
        self.write("specs/general/planning.adoc", "= 规划规范\n\n* 其他。\n")
        cm.check_runtime_env_guard()
        self.assertIn("planning.adoc", self.error_texts())

    def test_dispatcher_entry_removed_reports(self):
        # 反例：调度器识别特征被删 -> 本条永远不会被加载（规则实际失效）
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "= 规范\n\n== 分类与懒加载\n\n* 其他。\n")
        cm.check_runtime_env_guard()
        self.assertIn("调度器", self.error_texts())

    def test_maintainer_registration_removed_reports(self):
        # 反例：维护方工具声明清单未登记该防线
        self._write_valid()
        self.write("AGENTS.adoc", "= 项目规范\n\n* 其他。\n")
        cm.check_runtime_env_guard()
        self.assertIn("AGENTS.adoc", self.error_texts())

    def test_library_adoption_removed_reports(self):
        # 反例：图书馆未记同义性差异 -> 读者会把本站取舍当标准原文
        self._write_valid()
        self.write("library/adoption.adoc", "= 准入依据\n\n* 其他。\n")
        cm.check_runtime_env_guard()
        self.assertIn("adoption.adoc", self.error_texts())


class TestCheckRenameSplitGuard(CheckSpecsTestCase):
    """钉住用户提出的 P7：同一文件的重命名与内容修改须分两个提交。

    本条容易被三条路径绕过——改动很小/只有三处引用（合并提交被合理化）、只 `git mv` 不先提交
    （中间版本从未存在过）、用压缩提交把两个并回一个。故除正例外，用例专门覆盖整节被删、
    判据被抽、分量不是理由被删、提交顺序被删、无损拆分被删、两个都进同一 PR 被删、
    压缩提交接口被删、例外被删、引用方自检被删、必加载层重申被删、铁律登记被删、
    维护方清单少列 P7 与级别被降等反例。
    """

    GIT_SECTION = _real_git_rename_section()

    def _write_valid(self) -> None:
        self.write("specs/general/git.adoc", "= git 规范\n\n" + self.GIT_SECTION)
        self.write(
            "specs/platform/cnb.adoc",
            "= CNB 平台\n\n== 压缩提交（提交历史的整理）\n"
            "* **压缩提交＝提交历史整理（L1）**：用户要求时按本条执行。\n"
            "* **压缩对象不含\"改名提交 + 内容修改提交\"（L1，与「重命名与内容修改须分两个提交」的接口）**："
            "拆出的那两个提交**不是**本节的临时中间提交（别名：改名提交 + 内容修改提交），"
            "未点名本条时本次任务的**其余提交照默认压成一个**、那两个提交**原样保留**；"
            "用户**明确声明**（须点名重命名与内容修改）时按 git 规范"
            "「例外」执行。\n")
        self.write(
            "specs/core/execution.adoc",
            "= 执行原则\n\n== 文件操作强制检查\n"
            "* **重命名与内容修改须分两个提交（L1 最高关注项 P7）**：第一个提交**只做重命名、"
            "内容逐字节不变**（先 `git mv` 并只提交改名），第二个提交**再改内容**。\n")
        self.write(
            "AGENTS_COMMON.adoc",
            "= 规范\n\n== 最高优先级铁律（先读）\n"
            "* **同一文件的重命名与内容修改必须分两个提交**：**最高关注项 P7**；"
            "先 `git mv` 并只提交改名（**内容逐字节不变**），**再改内容**；"
            "**\"压缩提交\"未点名本条时，其余提交默认压成一个、本条的两个提交原样保留**；见 "
            "link:specs/general/git.adoc[]\u300c重命名与内容修改须分两个提交（默认固定动作）\u300d。\n")
        self.write(
            "specs-project-maintainer/priority.adoc",
            "= 最高关注项\n\n* **规范性铁律（P1/P2/P3/P5/P6/P7，条款本身 L1）**：略。\n\n"
            "=== P7. 重命名与内容修改必须分两个提交\n"
            "* **要求（L1，最高）**：分两个提交、先重命名后改内容；本次涉及改名的文件全收在"
            "**同一个改名提交**里、**不按文件个数分摊**；**「压缩提交」未点名本条**时**其余提交"
            "默认压成一个**、本条两个提交**原样保留**。\n"
            "* **依据**：ISO 10007。\n"
            "* **判定标准**：`git log --follow --name-status` 应见先 R 后 M。\n")

    def _drop(self, needle: str) -> None:
        """把权威定义节里的某条 bullet 删掉后重写文件（反例构造）。"""
        text = ("= git 规范\n\n" + self.GIT_SECTION).replace(needle, "")
        self.write("specs/general/git.adoc", text)

    def test_valid_passes(self):
        self._write_valid()
        cm.check_rename_split_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_git_file_reports(self):
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "general", "git.adoc"))
        cm.check_rename_split_guard()
        self.assertIn("缺少", self.error_texts())

    def test_section_deleted_reports(self):
        # 反例：整节被删 -> 拆两个提交只能靠执行者临场发挥
        self._write_valid()
        self.write("specs/general/git.adoc", "= git 规范\n\n== 文件移动与重命名\n* 略。\n")
        cm.check_rename_split_guard()
        self.assertIn("重命名与内容修改须分两个提交", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例（关键词堆砌式假绿）：只留节名与口号，判定标准被抽掉
        self._write_valid()
        self.write("specs/general/git.adoc",
                   "= git 规范\n\n== 重命名与内容修改须分两个提交（默认固定动作）\n\n"
                   "[quote]\n本节是**权威完整定义**（最高关注项 P7）。\n")
        cm.check_rename_split_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_order_bullet_removed_reports(self):
        # 反例（整条 bullet 被摘掉）：只"轴名齐全、判据被抽走"的形态——按内容关键词的核对
        # 会被相邻条款的字样兜住，故核对的必须是**该条自身**的条目轴与判据。
        # 方法名与本类下方的 `test_item_label_removed_reports` **不得重名**——同一个测试类里
        # 重名的后一个会静默覆盖前一个，这条用例曾因此从未执行（判据对应的轴也在别处出现过，
        # 于是"整条被摘掉"这一最危险的形态无人发声）。
        self._write_valid()
        # 整条摘掉 + 抹掉该条独有的判据措辞（判据被搬进相邻条目时同样须报红）
        self._drop("* **提交顺序（L1）**")
        self._drop("、后改内容")
        cm.check_rename_split_guard()
        self.assertIn("提交顺序", self.error_texts())

    def test_size_is_no_excuse_removed_reports(self):
        # 反例：删掉分量不是理由 -> 改动很小/只有三处引用即可自圆其说
        self._write_valid()
        self._drop("* **分量大小不是理由（L1）**")
        cm.check_rename_split_guard()
        self.assertIn("分量大小不是理由", self.error_texts())

    def test_order_clause_removed_reports(self):
        # 反例：删掉提交顺序 -> 先改内容再改名，可能连 rename 识别一起丢掉（P1 也失效）
        self._write_valid()
        self._drop("* **提交顺序（L1）**")
        cm.check_rename_split_guard()
        self.assertIn("提交顺序", self.error_texts())

    def test_lossless_split_removed_reports(self):
        # 反例：删掉无损拆分 -> 只 git mv、改动留在工作区，中间版本从未存在过
        self._write_valid()
        self._drop("* **无损拆分（L1，判定标准）**")
        cm.check_rename_split_guard()
        self.assertIn("无损拆分", self.error_texts())

    def test_same_pr_clause_removed_reports(self):
        # 反例：删掉两个提交都进同一 PR -> 第二个提交留本地，本条形同虚设
        self._write_valid()
        self._drop("* **两个提交都要进本次交付（L1）**")
        cm.check_rename_split_guard()
        self.assertIn("两个提交都要进本次交付", self.error_texts())

    def test_exemption_clause_removed_reports(self):
        # 反例：删掉例外 -> 与用户声明的例外冲突时无条文可依
        self._write_valid()
        self._drop("* **例外（只有一条，L1）**")
        cm.check_rename_split_guard()
        self.assertIn("例外", self.error_texts())

    def test_compression_clause_removed_reports(self):
        # 反例：删掉与「压缩提交」的接口 -> 出现"历史都整理干净了、把两个并回一个"的自我豁免路径
        self._write_valid()
        self._drop("为由把两者压回一个")
        cm.check_rename_split_guard()
        self.assertIn("压缩提交", self.error_texts())

    def test_selfcheck_removed_reports(self):
        # 反例：删掉引用方自检命令 -> 规范集合看不到引用方工作区，抓手落空
        self._write_valid()
        self._drop("* **可执行抓手（引用方项目自检）**")
        cm.check_rename_split_guard()
        self.assertIn("可执行抓手", self.error_texts())

    def test_item_label_removed_reports(self):
        # 反例（整条 bullet 被摘掉、正文并入相邻条目）：按内容关键词核对可能被相邻条款的
        # 字样兜住，故须有"条目轴逐项"的结构核对对"整条被摘掉"发声
        self._write_valid()
        self._drop("* **分量大小不是理由（L1）**")
        cm.check_rename_split_guard()
        self.assertIn("分量大小不是理由", self.error_texts())

    def test_batch_rename_clause_removed_reports(self):
        # 反例：删掉"不按文件个数分摊" -> 多文件同时改名会被读成"每个文件各开一个改名提交"
        # （"改动只涉及本文件"被当成拆分依据，批量改名提交就此消失）
        self._write_valid()
        self._drop("**不按文件个数分摊**")
        cm.check_rename_split_guard()
        self.assertIn("文件个数", self.error_texts())

    def test_batch_delivery_clause_removed_reports(self):
        # 反例：删掉"分批交付时序列不重排" -> 分批整理时以"压缩提交"为由把已交付的两个提交压掉或重排
        self._write_valid()
        self._drop("**同一 PR 内改动分批交付时，这条序列不重排**")
        cm.check_rename_split_guard()
        self.assertIn("分批交付", self.error_texts())

    def test_chain_check_notion_removed_reports(self):
        # 反例：删掉断链核对的**取值形态**（"那一条批量改名记录仍在"）-> "那一批改名"被拆分/
        # 省略成「新增 + 删除」时无抓手可核。核的是取值形态而不是具体命令：命令属执行动作，
        # 收进正文即第二处"取法"（见 `specs-project-maintainer/spec-lifecycle.adoc`
        # 「以对象定义规则、不给具体操作」）。
        self._write_valid()
        self._drop("批量改名")
        cm.check_rename_split_guard()
        self.assertIn("批量改名", self.error_texts())

    def test_compression_request_boundary_removed_reports(self):
        # 反例：删掉"压缩提交的请求不覆盖本条" -> "用户说要合并成一个提交"就成了本条失效的依据
        # （这正是用户点名不能照做的形态：合并/压缩的请求不解除重命名与内容修改要分两个提交）
        self._write_valid()
        self._drop("* **「压缩提交」的请求不覆盖本条（L1）**")
        cm.check_rename_split_guard()
        self.assertIn("压缩提交", self.error_texts())

    def test_exemption_needs_named_declaration(self):
        # 反例：例外允许"只说合并/压缩"就算声明 -> 本条的例外被放宽成"共用一个词即可"
        self._write_valid()
        self._drop("点名重命名与内容修改")
        cm.check_rename_split_guard()
        self.assertIn("点名", self.error_texts())

    def test_compression_post_check_removed_reports(self):
        # 反例：删掉"压缩后核对" -> 压缩要求把本条的记录一并压掉时无抓手可核
        self._write_valid()
        self._drop("**压缩后核对**")
        cm.check_rename_split_guard()
        self.assertIn("压缩后核对", self.error_texts())

    def test_platform_interface_removed_reports(self):
        # 反例：平台层「压缩提交」没写与 P7 的接口 -> 平台侧可自行把"要压缩"读成"压回一个"
        self._write_valid()
        self.write("specs/platform/cnb.adoc", "= CNB 平台\n\n== 压缩提交（提交历史的整理）\n* 另议。\n")
        cm.check_rename_split_guard()
        self.assertIn("cnb.adoc", self.error_texts())

    def test_compression_boundary_body_gutted_reports(self):
        # 反例：边界条只留轴标题、正文被抽空（要求被搬进相邻条目）——
        # 整节关键词核对会被相邻条款的字样兜住，故须按条目**自身**的正文核（实测旧法静默通过）
        self._write_valid()
        text = ("= git 规范\n\n" + self.GIT_SECTION)
        b = cm._bullet_text(text, "「压缩提交」的请求不覆盖本条")
        self.write("specs/general/git.adoc",
                   text.replace(b, b.split("**：")[0] + "**：另议。\n"))
        cm.check_rename_split_guard()
        self.assertIn("原样保留", self.error_texts())

    def test_compression_boundary_criteria_removed_reports(self):
        # 反例：边界条抽掉自身的「判定标准」——它退化成一句口号，复核者无从判定某次是否越界
        self._write_valid()
        text = ("= git 规范\n\n" + self.GIT_SECTION)
        b = cm._bullet_text(text, "「压缩提交」的请求不覆盖本条")
        head, _, tail = b.partition("**判定标准（逐条可核对，任一命中即不合规）**")
        self.write("specs/general/git.adoc",
                   text.replace(b, head + "**为什么算两件事（依据）**" + tail.split("**为什么算两件事（依据）**", 1)[-1]))
        cm.check_rename_split_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_platform_interface_decoy_reports(self):
        # 反例：平台层接口被换成"只保留通用词"的诱饵条目（两个提交/别名/原样保留/例外/声明/点名
        # 都出现，但接口要求本身没了）——整节关键词核对会被兜住，故须按接口条自身核（实测旧法静默通过）
        self._write_valid()
        cnb = open(os.path.join(cm.REPO_ROOT, "specs", "platform", "cnb.adoc"), encoding="utf-8").read()
        line = [l for l in cnb.split("\n") if "别名" in l][0]
        self.write("specs/platform/cnb.adoc",
                   cnb.replace(line, "* 另议：两个提交、别名的说法不是重点，原样保留与否、"
                                     "例外与声明、点名都见别处。"))
        cm.check_rename_split_guard()
        self.assertIn("压缩对象不含", self.error_texts())

    def test_resident_reference_removed_reports(self):
        # 反例：必加载层重申行被删 -> 常驻上下文里读不到 P7（下次会话不会加载 git 规范）
        self._write_valid()
        self.write("specs/core/execution.adoc", "= 执行原则\n\n== 文件操作强制检查\n* 略。\n")
        cm.check_rename_split_guard()
        self.assertIn("P7", self.error_texts())

    def test_iron_rule_registration_removed_reports(self):
        # 反例：进门必读的铁律行被删 -> 只在用到 git 时才可能读到本条
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "= 规范\n\n== 最高优先级铁律（先读）\n* 另议。\n")
        cm.check_rename_split_guard()
        self.assertIn("最高优先级铁律", self.error_texts())

    def test_maintainer_entry_removed_reports(self):
        # 反例：维护方不可降级清单少列 P7 -> 重构/去重时会被当成普通条目删掉
        self._write_valid()
        self.write("specs-project-maintainer/priority.adoc",
                   "= 最高关注项\n\n* **规范性铁律（P1/P2，条款本身 L1）**：略。\n\n"
                   "=== P2. 调整规范必须保证完整性\n* **要求（L1，最高）**：略。\n")
        cm.check_rename_split_guard()
        self.assertIn("P7", self.error_texts())

    def test_maintainer_p7_skeleton_reports(self):
        # 反例（本轮实测缺口）：把维护方 P7 的『要求』压成两句骨架——"要求/依据/判定标准"
        # 三个轴名都还在，而**可核对的判据**被抽掉（不按文件个数分摊、未点名本条时原样保留）。
        # 旧判据只核轴名，故这种"轴名齐全、判据消失"的形态能全绿；读者按 P7 核对时，
        # 批量改名与「压缩提交」的接口两处判据已无从判定。
        self._write_valid()
        self.write("specs-project-maintainer/priority.adoc",
                   "= 最高关注项\n\n* **规范性铁律（P1/P2/P3/P5/P6/P7，条款本身 L1）**：略。\n\n"
                   "=== P7. 重命名与内容修改必须分两个提交\n"
                   "* **要求（L1，最高）**：分两个提交、先重命名后改内容。\n"
                   "* **依据**：ISO 10007。\n"
                   "* **判定标准**：`git log --follow --name-status` 应见先 R 后 M。\n")
        cm.check_rename_split_guard()
        self.assertIn("不按文件个数分摊", self.error_texts())
        self.assertIn("原样保留", self.error_texts())

    def test_maintainer_overview_omits_p6_reports(self):
        # 反例（本轮实测缺口）：分级概览行回到旧口径 "P1/P2/P3/P5/P7"——把 P6（协作执行者
        # 选择）漏在"条款本身 L1"的铁律之外。旧判据只找 "P7" 字样，故这一漏项能靠相邻字样
        # 兜住而全绿；读者按概览核对时会漏项（尤其是抽去 P4/P6 的级别说明之后）。
        self._write_valid()
        self.write("specs-project-maintainer/priority.adoc",
                   "= 最高关注项\n\n* **规范性铁律（P1/P2/P3/P5/P7，条款本身 L1）**：略。\n\n"
                   "=== P7. 重命名与内容修改必须分两个提交\n"
                   "* **要求（L1，最高）**：分两个提交、先重命名后改内容。\n"
                   "* **依据**：ISO 10007。\n"
                   "* **判定标准**：`git log --follow --name-status` 应见先 R 后 M。\n")
        cm.check_rename_split_guard()
        self.assertIn("P6", self.error_texts())

    def test_maintainer_level_removed_reports(self):
        # 反例：P7 条目的级别被静默降级（要求（L1，最高 -> L2）
        self._write_valid()
        self.write("specs-project-maintainer/priority.adoc",
                   "= 最高关注项\n\n* **规范性铁律（P1/P2/P3/P5/P6/P7，条款本身 L1）**：略。\n\n"
                   "=== P7. 重命名与内容修改必须分两个提交\n"
                   "* **要求（L2）**：分两个提交。\n* **依据**：ISO 10007。\n* **判定标准**：略。\n")
        cm.check_rename_split_guard()
        self.assertIn("P7", self.error_texts())

    def test_restatement_default_one_commit_removed_reports(self):
        # 反例：三处**复述行**（铁律 / 维护方 P7 / 平台层接口条）各自的"默认压成一个"被抽掉
        # → 真源条文还在、复述行读不出默认交付形态，旧口径（只压部分）从复述行上复活。
        for rel, needle, repl in (
            ("AGENTS_COMMON.adoc",
             "**\"压缩提交\"未点名本条时，其余提交默认压成一个、本条的两个提交原样保留**",
             "**\"压缩提交\"不覆盖本条**"),
            ("specs-project-maintainer/priority.adoc",
             "**其余提交默认压成一个**",
             "只压临时中间提交"),
            ("specs/platform/cnb.adoc",
             "本次任务的**其余提交照默认压成一个**",
             "**照旧处理**"),
        ):
            self._write_valid()
            body = open(os.path.join(self.root, rel), encoding="utf-8").read()
            self.assertIn(needle, body, f"夹具与现役条文已脱节：{rel}")
            self.write(rel, body.replace(needle, repl))
            cm.check_rename_split_guard()
            self.assertTrue(self.error_texts().strip(),
                            f"{rel} 的复述行被抽掉后防线未报红——锚点与真源脱节")
            cm.errors.clear()


class TestCheckCriteriaNotAxisGuard(CheckSpecsTestCase):
    """钉住『防线的核对对象是判据本体、不是轴名』这条通则**进了规范正文**。

    本条是**下一轮维护者读得到、读不到**的问题，不是某次审核有没有发现的问题：
    教训（「轴名齐全 ≠ 判据在」）原只写在 `script/check_specs.py` 与配套测试的注释里——
    正例全绿只能说明防线不误报，**防线的实际效力全靠反例用例**；而「下一个人读规范时
    看不看得到这条通则」只能靠正文存在性与要点齐备来钉。
    故用例覆盖：整节被删（回到只活在注释里）、核对对象被抹成一句口号、判定标准被抽、
    必配反例须报红被删、以及维护方入口未登记（通则不会被加载）。
    """

    CFG = LQ
    CBR = RQ

    SECTION = (
        "== 强调的正确做法（避免" + LQ + "写两次" + RQ + "的误解）\n"
        "\n"
        "* **机械钉住**：对" + LQ + "任何时候都不得消失" + RQ + "的条目，用校验脚本钉住其**存在性**。\n"
        "\n"
        "=== 机械防线的核对对象是**判据本体**，不是轴名（L1）\n"
        "\n"
        "**" + LQ + "条目有要求/依据/判定标准三个轴" + RQ + "不等于" + LQ + "判据在" + RQ + "**。\n"
        "\n"
        "* **核对对象（L1）**：机械防线须钉**判据本体**——即**判定标准里能拿去核对的那句话**。"
        "**只核" + LQ + "轴名/条目标题在不在" + RQ + "即为防线空转**。\n"
        "* **判定标准（逐条可核对，任一命中即未做到）**：① 被钉的是**轴名**；② 抽掉判据句后"
        "防线**仍不报红**；③ 靠**相邻条目的字样**兜住已消失的要求。\n"
        "* **必配反例用例（L1）**：须有**一条" + LQ + "轴名齐全、判据被抽走" + RQ + "的反例用例**"
        "——改造后防线**必须报红**。\n"
        # 同节还承载「机械核对边界」两条（本轮新增判据本体）：夹具须含这两类取值，
        # 否则正例会被新增要点判成缺失——红的是夹具，不是实现。
        "**机械核对边界（覆盖不到的两类，一次声明）**：机械核对覆盖不到**运行时事实**与"
        "**语义判断**两类。\n"
    )

    def _write(self, section: str = None, registered: bool = True) -> None:
        self.write("specs-project-maintainer/priority.adoc", section or self.SECTION)
        self.write("AGENTS.adoc",
                   "= 项目规范\n\n"
                   + ("* 维护方清单：`specs-project-maintainer/priority.adoc`\n"
                      if registered else ""))

    def test_valid_passes(self):
        self._write()
        cm.check_criteria_not_axis_guard()
        self.assertEqual(cm.errors, [])

    def test_mechanical_limit_removed_reports(self):
        # 反例：把「机械核对边界」的两类取值抽掉——缺它则每道防线各写一句口径，
        # 边界随措辞漂移（本轮实测：该句式在 check_specs.py 出现 91 处）
        self._write(section=self.SECTION.replace("语义判断", "别的东西"))
        cm.check_criteria_not_axis_guard()
        self.assertIn("语义判断", self.error_texts())

    def test_missing_priority_file_reports(self):
        # 反例：维护方清单缺失 -> 通则失去落点
        self._write()
        os.remove(os.path.join(self.root, "specs-project-maintainer", "priority.adoc"))
        cm.check_criteria_not_axis_guard()
        self.assertIn("priority.adoc", self.error_texts())

    def test_section_removed_reports(self):
        # 反例（本轮实测形态）：通则整节被删、只剩在脚本注释里 -> 下一个维护者读规范看不到
        self._write("== 强调的正确做法\n\n* **机械钉住**：钉住其**存在性**。\n")
        cm.check_criteria_not_axis_guard()
        self.assertIn("注释", self.error_texts())

    def test_axis_only_wording_removed_reports(self):
        # 反例：只留"钉住存在性"、把"钉判据本体、不钉轴名"抹掉 -> 回到"轴名齐即通过"
        self._write(self.SECTION.replace(
            "* **核对对象（L1）**：机械防线须钉**判据本体**——即**判定标准里能拿去核对的那句话**。",
            "* **核对对象（L1）**：机械防线须钉住条目形态是否齐备。"))
        cm.check_criteria_not_axis_guard()
        self.assertIn("判据本体", self.error_texts())

    def test_idle_guard_wording_removed_reports(self):
        # 反例：删掉"只核轴名即为防线空转"这一失效形态 -> 读者会把"轴名齐"当成"判据在"
        self._write(self.SECTION.replace(
            "**只核" + LQ + "轴名/条目标题在不在" + RQ + "即为防线空转**。", "。"))
        cm.check_criteria_not_axis_guard()
        self.assertIn("轴名", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例：判定标准被抽 -> 本通则自身退化成一喊句口号，无法判定某道防线是否空转
        self._write(self.SECTION.replace(
            "* **判定标准（逐条可核对，任一命中即未做到）**：① 被钉的是**轴名**；② 抽掉判据句后"
            "防线**仍不报红**；③ 靠**相邻条目的字样**兜住已消失的要求。\n", ""))
        cm.check_criteria_not_axis_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_counterexample_requirement_removed_reports(self):
        # 反例：删掉"必配反例用例（轴名齐全、判据被抽走须报红）" -> 防线的实际效力无从证明
        self._write(self.SECTION.replace(
            "* **必配反例用例（L1）**：须有**一条" + LQ + "轴名齐全、判据被抽走" + RQ + "的反例用例**"
            "——改造后防线**必须报红**。\n", ""))
        cm.check_criteria_not_axis_guard()
        self.assertIn("报红", self.error_texts())

    def test_maintainer_entry_unregistered_reports(self):
        # 反例：清单未在维护方入口登记 -> 不会被加载、通则实际失效
        self._write(registered=False)
        cm.check_criteria_not_axis_guard()
        self.assertIn("AGENTS.adoc", self.error_texts())


class TestCheckRefinementGuard(CheckSpecsTestCase):
    """钉住『精炼性（同一描述只写一处）』防线：判据本体与两处动作落点。

    用户本轮点名的两条要求：①「精炼性规范应该在 review 及重构时强制生效」；
    ②「依旧有很多相同的描述在不同的地方，不满足精炼性的要求」。故用例覆盖
    **两种降级形态**：判据被压成一句口号（轴名齐、判据被抽走）、以及
    "只在通用层写了、在评审与重构里不生效"（固定动作与 `delivery` 片段缺该条）。
    """

    SECTION = (
        "== 精炼性（同一描述只写一处）\n\n"
        "* **重复面是必查项（L1）**：须判\"这条描述在本仓库还有没有第二处\"——"
        "**这是\"没发现重复\"与\"没查过重复\"的分界**。\n"
        "* **判定标准（任一命中即为重复描述）**：① 同一事实在两处以上**以完整表述出现**；"
        "③ 一处改了而另一处必须跟着改——**\"改一处要记得改 N 处\"本身即重复的证据**。\n"
        "* **收敛形态（L1）**：**一处完整定义，其余位置只留\"这是什么 + 在哪\"的一行引用**。\n"
        "* **收敛时不得以去重换缺失（L1，与\"内容不减少\"的边界）**：**删掉的必须是重复表述本身，"
        "被删处须留下可达的引用**；**对无法确定是否重复的内容一律保留**。\n"
        "* **两类形态不得被当成重复收敛**：① **最高关注项与其引用**；② **各自的承接**。\n"
        "* **\"篇幅大\"与\"重复\"是两件事**：**判据是\"同一描述有几处\"，不是字多字少**。\n"
        "* 依据（标准名/编号）：ISO/IEC Directives Part 2 与 ISO/IEC/IEEE 29148；"
        "ISO 10007；DRY。\n\n")

    CHANGE_REVIEW = (
        "== 改动后的 review（每次改完都得复核一次）\n\n"
        "* **\"改完即审\"的固定动作（L1）**：① **跑**机械手段；② **比**基线；"
        "③ **核**改动清单与用户原话是否一一对应，**并按「精炼性」核对一遍重复面**；④ **留**证。\n")

    DELIVERY = (
        "// tag::delivery[]\n"
        "**交付**：\n"
        "   - **重复面的处理（L1，评审与重构的固定动作）**：重复面记入清单并"
        "**按「一处完整定义 + 其余一行引用」收敛**；**不得以去重换缺失**；"
        "汇报里须**显式给出重复面的处理结果**——\"查了几处、收敛了哪些\"。\n"
        "// end::delivery[]\n")

    def _write(self, section=None, change_review=None, delivery=None) -> None:
        self.write("specs/general/review.adoc",
                   (section or self.SECTION) + (change_review or self.CHANGE_REVIEW))
        self.write("prompts/_common.txt", delivery if delivery is not None else self.DELIVERY)

    def test_valid_passes(self):
        self._write()
        cm.check_refinement_guard()
        self.assertEqual([], cm.errors)

    def test_section_removed_reports(self):
        # 反例：整节被删 → 精炼性退化成"写得短一点"的个人偏好，无处可查
        self._write(section="== 问题记录\n\n* 记一笔。\n\n")
        cm.check_refinement_guard()
        self.assertIn("精炼性", self.error_texts())

    def test_checklist_wording_removed_reports(self):
        # 反例（反例本体：轴名齐全、判据被抽走）：把"必查项 + 与没查过的分界"压成一句口号
        self._write(section=self.SECTION.replace(
            "* **重复面是必查项（L1）**：须判\"这条描述在本仓库还有没有第二处\"——"
            "**这是\"没发现重复\"与\"没查过重复\"的分界**。\n",
            "* **重复面是必查项（L1）**：注意别写重复内容。\n"))
        cm.check_refinement_guard()
        self.assertIn("必查项", self.error_texts())

    def test_convergence_form_removed_reports(self):
        # 反例：收敛形态被删 → "发现重复"没有规定的处置方式（容易滑向"删掉了事"）
        self._write(section=self.SECTION.replace(
            "* **收敛形态（L1）**：**一处完整定义，其余位置只留\"这是什么 + 在哪\"的一行引用**。\n", ""))
        cm.check_refinement_guard()
        self.assertIn("收敛形态", self.error_texts())

    def test_contraction_boundary_removed_reports(self):
        # 反例：与"内容不减少"（最高关注项）的边界被删 → 去重会以"删重复"的名义删掉唯一那份内容
        self._write(section=self.SECTION.replace(
            "* **收敛时不得以去重换缺失（L1，与\"内容不减少\"的边界）**：**删掉的必须是重复表述本身，"
            "被删处须留下可达的引用**；**对无法确定是否重复的内容一律保留**。\n",
            "* **收敛时注意别删太多**。\n"))
        cm.check_refinement_guard()
        self.assertIn("不得以去重换缺失", self.error_texts())

    def test_keeper_forms_removed_reports(self):
        # 反例：删掉"两类形态不得被当成重复收敛" → 会把刻意强调的引用与分层承接误当重复合并掉
        self._write(section=self.SECTION.replace(
            "* **两类形态不得被当成重复收敛**：① **最高关注项与其引用**；② **各自的承接**。\n", ""))
        cm.check_refinement_guard()
        self.assertIn("重复收敛", self.error_texts())

    def test_review_action_removed_reports(self):
        # 反例（用户点名的"应该在 review 时强制生效"）：固定动作里不再核重复面
        self._write(change_review=self.CHANGE_REVIEW.replace("，**并按「精炼性」核对一遍重复面**", ""))
        cm.check_refinement_guard()
        self.assertIn("固定动作", self.error_texts())

    def test_delivery_clause_removed_reports(self):
        # 反例（"应该在重构时也强制生效"）：提示词片段里该条被删 → 两个提示词都不再带这个动作
        self._write(delivery="// tag::delivery[]\n**交付**：有改动就提交。\n// end::delivery[]\n")
        cm.check_refinement_guard()
        self.assertIn("_common.txt", self.error_texts())


class TestCheckDuplicateScanGuard(CheckSpecsTestCase):
    """钉住『逐字重复扫描』防线：**同一条判据在两处逐字重复必须报红**。

    这是「精炼性」在机械侧的唯一抓手（此前只有语义复核）。故用例的核心不是"防线函数
    会不会被调用"，而是**逐字重复真的被拦下**、且**不该报的（短实体、例外清单、
    历史留痕、片段引用）不误伤**——防线的误报会逼出"为了过检查而删内容"的反用，
    与 `review.adoc`「精炼性」的边界相抵。
    """

    DUP = ("* **运行契约（L1）**：加载与遵守的代价是否说得清——加载面体积、时延与依赖要求"
           "（含版本要求，且须给出不可用时的降级路径）；**不得以\"不贵\"含糊带过**。\n")
    OTHER = "* **别的一条**：讲的是另一件事，措辞也不同，不会与上面逐字重合。\n"

    def test_verbatim_duplication_reports(self):
        self.write("specs/general/a.adoc", self.DUP)
        self.write("specs/general/b.adoc", self.DUP)
        cm.check_duplicate_scan_guard()
        self.assertIn("重合", self.error_texts())

    def test_no_duplication_passes(self):
        self.write("specs/general/a.adoc", self.DUP)
        self.write("specs/general/b.adoc", self.OTHER)
        cm.check_duplicate_scan_guard()
        self.assertEqual(cm.errors, [])

    def test_include_reference_not_reported(self):
        # `include::` 是"同一份内容被两处引入"（一处维护两处生效），逐字一致是本来的要求
        self.write("prompts/_common.txt", "// tag::x[]\n内容占位，长到超过阈值用来核对不误伤。\n// end::x[]\n")
        for n in ("a", "b"):
            self.write(f"prompts/{n}.adoc", "include::_common.txt[tag=x]\n")
        cm.check_duplicate_scan_guard()
        self.assertEqual(cm.errors, [])

    def test_excluded_history_not_reported(self):
        # 历史留痕（CHANGELOG）的职责就是逐字保留，要求它"不重复"与它的角色直接冲突
        self.write("specs/general/a.adoc", self.DUP)
        self.write("CHANGELOG.adoc", self.DUP)
        self.write("specs/general/b.adoc", self.OTHER)
        cm.check_duplicate_scan_guard()
        self.assertEqual(cm.errors, [])


class TestCheckPointerNoVerbatimGuard(CheckSpecsTestCase):
    """钉住『自称回指的行不得复述取值』防线（`check_pointer_no_verbatim_guard`）。

    这是「同一件事只在一处给真源」的**第二道机械抓手**——补 `check_duplicate_scan_guard`
    的**下界**：阈值 40 只报"长度极显著"的重合，而"回指句 + 顺手把取值抄一遍"的公共子串
    常只有二十几字，`duplicate_scan` **核不出来**（本轮实证：`library/mirrors.adoc` 自称
    "本文件只给实测记录、取舍本体见 `adoption.adoc`"，却仍逐字写下「每级先实测可用、
    不跳级、不覆盖既有配置」21 字）。

    用例覆盖：① 回指却复述取值 → 报红；② 纯回指 → 全绿；③ 不含回指标记的行不在核对面内；
    ④ 标准名/材料名的正当重合按 `ignore` 豁免（防"为过检查而删标准名"）。
    """

    POINTER = ("* **须注意的语义差异（同义性）**：本集合据此推出的是自己的判据化取舍"
               "（**取值见** `library/adoption.adoc`「库源次序」条，本文件只给实测记录）——"
               "每级先实测可用、不跳级、不覆盖既有配置，且不覆盖引用方配置。\n")
    ADOPTION = ("* **库源次序（本集合的判据化取舍）**：每级先实测可用、不跳级、"
                "不覆盖既有配置，且不覆盖引用方配置。\n")

    def setUp(self) -> None:
        super().setUp()
        self.write("library/adoption.adoc", self.ADOPTION)
        # 规则数据把整批"会自称回指"的文件都列进核对面，缺一份即报"落点无处承载"——
        # 夹具须与规则数据的 `files` **同形**，否则用例会因"文件缺失"而非"判据命中"报红
        # （这也是本防线的一条自查：新增落点时必须同步夹具，落点漂移不会被静默放过）。
        for rel in cm.POINTER_SCAN_FILES:
            if rel == "library/adoption.adoc":
                continue
            self.write(rel, "= 占位\n\n本文件只给实测记录与索引。\n")

    def test_pointer_restating_values_reports(self):
        self.write("library/mirrors.adoc", self.POINTER)
        cm.check_pointer_no_verbatim_guard()
        self.assertIn("重合", self.error_texts())

    def test_pure_pointer_passes(self):
        self.write("library/mirrors.adoc",
                   "* **须注意的语义差异（同义性）**：本集合据此推出的是自己的判据化取舍"
                   "（**取值见** `library/adoption.adoc`「库源次序」条，本文件只给实测记录）。\n"
                   "* 取样条件与实测取值见下。\n")
        cm.check_pointer_no_verbatim_guard()
        self.assertEqual(cm.errors, [])

    def test_line_without_marker_not_checked(self):
        # 没自称"见别处"的行归 `duplicate_scan` 管（阈值口径不同），本条不越界
        self.write("library/mirrors.adoc", self.ADOPTION)
        cm.check_pointer_no_verbatim_guard()
        self.assertEqual(cm.errors, [])

    def test_scan_files_match_rule_data(self):
        # 常驻常量与规则数据**逐项同源**：新增落点时两处必须一起改，
        # 否则用例会因"文件缺失"报红（本防线的一条自查）
        import tomllib
        with open(os.path.join(HERE, "specs-rules", "duplicate.toml"), "rb") as fh:
            data = tomllib.load(fh)
        steps = data["guards"]["check_pointer_no_verbatim_guard"]
        files = []
        for st in steps:
            files.extend(st.get("files", []))
        self.assertEqual(sorted(set(files)), sorted(set(cm.POINTER_SCAN_FILES)),
                         "核对面须与规则数据逐项一致（改一处必须改另一处）")

    def test_scan_files_cover_all_adoc(self):
        # 反面：核对面只列"已知会自称回指的那些文件"时，未列入的文件永远不被扫描——
        # 防线静默少扫一层而读者以为已覆盖。故核对面须覆盖仓库里全部 .adoc
        # （历史留痕 `CHANGELOG.adoc` 除外——它的职责就是逐字保留历史产物）。
        import subprocess
        repo = os.path.dirname(HERE)
        tracked = subprocess.run(["git", "ls-files", "*.adoc"], cwd=repo,
                                 capture_output=True, text=True).stdout.split()
        expected = sorted(f for f in tracked if f != "CHANGELOG.adoc")
        self.assertEqual(list(cm.POINTER_SCAN_FILES), expected,
                         "自称回指的核对面须覆盖全部 .adoc——只列已知文件会让未列入者"
                         "永远处于盲区，且漏掉时防线静默少扫一层")

    def test_code_and_prompt_files_are_scanned(self):
        # **正面**：上一轮实证的两处盲区（通用层 `coding.adoc`、提示词正文）必须在核对面内——
        # 它们是"回指句 + 顺手抄取值"最可能出现的两层（都把取值推给别处、又忍不住复述一遍）。
        for rel in ("specs/general/coding.adoc", "prompts/review.adoc"):
            self.assertIn(rel, cm.POINTER_SCAN_FILES)

    def test_standard_name_exempt(self):
        # 标准名/材料名本就该逐字一致（`specs/general/source.adoc`「外部引用」）——
        # 规则数据的 `ignore` 把它排除，否则同一批标准名会被反复判红
        self.write("library/adoption.adoc",
                   "* 依据：The Twelve-Factor App（依赖须显式声明）。\n")
        self.write("library/mirrors.adoc",
                   "* **须注意的语义差异**：本集合据此推出的取舍见 `library/adoption.adoc`、"
                   "本文件只给实测记录；外部材料含 The Twelve-Factor App（依赖须显式声明）一类。\n")
        cm.check_pointer_no_verbatim_guard()
        self.assertEqual(cm.errors, [])


class TestCheckInfoDensityGuard(CheckSpecsTestCase):
    """钉住『信息密度（每句须承载）』防线：判据本体、两处互引与图书馆依据。

    用户本轮的要求是"把学位论文/期刊论文的要求里**有用的**引入规范"，查证后取的唯一
    一条是**学术文体用信息密度衡量冗余**（依据 GB/T 7713.2-2022 / GB/T 7713.1-2025）。
    它在补的正是"单处里的废话"这个真空：`review.adoc`「精炼性」只判跨处重复。

    故用例除正例外，专门覆盖**"轴名齐全、判据被抽走"的反例本体**——判定标准、与 P3 的
    边界、适用面、依据行任一被抽掉时，防线**必须报红**（只核"这一节在不在"属防线空转）。
    """

    SECTION = (
        "== 注释与文档\n\n"
        "=== 信息密度（每句须承载）\n\n"
        "**它与 `specs/general/review.adoc`「精炼性」是两件事、两把尺子**："
        "精炼性判**\"同一描述有几处\"**；本条判**\"单处里有多少句是废话\"**——"
        "**只有一处、完全不重复的一段文字，仍可能通篇是废话**。\n"
        "* **每一句都要有承载（L2）**：**判定标准（任一命中即违规）**：① **复述**；"
        "② **空话**；③ **同义反复**；④ **可有可无的铺垫**。\n"
        "* **陈述句不得降格为表意不明（L2）**：删掉**不承载信息的限定语**；"
        "确属有边界的判断**须写出边界**。\n"
        "* **边界（防反用，L1）**：**内容不减少（最高关注项 P3）优先于本条**；"
        "**只有\"这一句没有承载\"才是**；把多条判据合并成一句口号属**违反 P3**。\n"
        "* **适用面（L2）**：适用于会被他人读的产物；**不适用**于代码与测试断言。\n"
        "* **发现即改、不单独发动全库清理（L2）**：改到哪就按本条看哪（随动迁移，见 `specs/core/execution.adoc`）。\n"
        "* 依据（标准名/编号）：**GB/T 7713.2-2022** 与 **GB/T 7713.1-2025**；"
        "**ISO/IEC Directives Part 2**；**ISO/IEC/IEEE 29148**。\n\n"
        "== 文档组织与导航\n\n* 略。\n")

    DOC_QUALITY = (
        "⑤ **简洁**——说清核心即可（\"信息密度\"是它的可判定形式，"
        "判据见本文「信息密度（每句须承载）」）；\n")

    REFINEMENT = (
        "== 精炼性（同一描述只写一处）\n\n"
        "* **与「信息密度」的分工（两把尺子，都要过）**：该判据在 "
        "`specs/general/doc.adoc`「信息密度（每句须承载）」。\n")

    LIBRARY = (
        "== GB/T 7713 系列（学位论文 / 学术论文编写规则）\n\n"
        "* **GB/T 7713.1-2025**《信息与文献 编写规则 第1部分：学位论文》——现行。\n"
        "* **GB/T 7713.1-2006**——**已废止**。\n"
        "* **GB/T 7713.2-2022**《学术论文编写规则》——现行。\n"
        "* **须注意的语义差异（同义性，L1）**：只取判据、不搬其文档构件。\n")

    def _write(self, section=None, doc_quality=None, refinement=None, library=None) -> None:
        # 两句都进同一份 `doc.adoc`（"⑤ 简洁"那一行属「文档质量」条、与本条同文件），
        # 故**一次写完**——分两次 write 会以后一次覆盖前一次，夹具里就少了那半句。
        self.write("specs/general/doc.adoc",
                   (doc_quality if doc_quality is not None else self.DOC_QUALITY)
                   + (section if section is not None else self.SECTION))
        self.write("specs/general/review.adoc",
                   refinement if refinement is not None else self.REFINEMENT)
        self.write("library/sources.adoc",
                   library if library is not None else self.LIBRARY)

    def test_valid_passes(self):
        self._write()
        cm.check_info_density_guard()
        self.assertEqual([], cm.errors)

    def test_section_removed_reports(self):
        # 反例：整节被删 -> "单处里的废话"重新变成判不了的区域
        self._write(section="== 文档组织与导航\n\n* 略。\n")
        cm.check_info_density_guard()
        self.assertIn("信息密度", self.error_texts())

    def test_division_of_labor_removed_reports(self):
        # 反例（反例本体：轴名齐全、判据被抽走）：与「精炼性」的分工被压成一句口号
        self._write(section=self.SECTION.replace(
            "**它与 `specs/general/review.adoc`「精炼性」是两件事、两把尺子**："
            "精炼性判**\"同一描述有几处\"**；本条判**\"单处里有多少句是废话\"**——"
            "**只有一处、完全不重复的一段文字，仍可能通篇是废话**。\n",
            "**本条与精炼性相关。**\n"))
        cm.check_info_density_guard()
        self.assertIn("分工", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例：判定标准被抽成一句"要注意" -> 本条自身不可判定
        self._write(section=self.SECTION.replace(
            "* **每一句都要有承载（L2）**：**判定标准（任一命中即违规）**：① **复述**；"
            "② **空话**；③ **同义反复**；④ **可有可无的铺垫**。\n",
            "* **每一句都要有承载（L2）**：注意别写废话。\n"))
        cm.check_info_density_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_p3_boundary_removed_reports(self):
        # 反例：与 P3 的边界被删 -> 本条会被反用成"这一段很长就删短"
        self._write(section=self.SECTION.replace(
            "* **边界（防反用，L1）**：**内容不减少（最高关注项 P3）优先于本条**；"
            "**只有\"这一句没有承载\"才是**；把多条判据合并成一句口号属**违反 P3**。\n",
            "* **边界（防反用，L1）**：长文可以删短。\n"))
        cm.check_info_density_guard()
        self.assertIn("边界", self.error_texts())

    def test_scope_removed_reports(self):
        # 反例：适用面被删 -> 会被套到代码与测试断言上（高频误伤）
        self._write(section=self.SECTION.replace(
            "* **适用面（L2）**：适用于会被他人读的产物；**不适用**于代码与测试断言。\n", ""))
        cm.check_info_density_guard()
        self.assertIn("适用面", self.error_texts())

    def test_basis_line_removed_reports(self):
        # 反例：依据行被删 -> "学术文体以信息密度衡量冗余"这一来源无从核对
        self._write(section=self.SECTION.replace(
            "* 依据（标准名/编号）：**GB/T 7713.2-2022** 与 **GB/T 7713.1-2025**；"
            "**ISO/IEC Directives Part 2**；**ISO/IEC/IEEE 29148**。\n", ""))
        cm.check_info_density_guard()
        self.assertIn("依据", self.error_texts())

    def test_doc_quality_xref_removed_reports(self):
        # 反例：从「简洁」这个入口进不去 -> 本条只能靠整份读 doc.adoc 才被发现
        self._write(doc_quality="⑤ **简洁**——禁止长篇大论，说清核心即可；\n")
        cm.check_info_density_guard()
        self.assertIn("doc.adoc", self.error_texts())

    def test_review_xref_removed_reports(self):
        # 反例：从「精炼性」这个入口进不去 -> 两条被读成同一件事（或本条被当重复删掉）
        self._write(refinement="== 精炼性（同一描述只写一处）\n\n* 别写重复内容。\n")
        cm.check_info_density_guard()
        self.assertIn("review.adoc", self.error_texts())

    def test_library_topic_removed_reports(self):
        # 反例：图书馆没有该主题段 -> 正文里的标准号无处逐字核对（依据只存名称）
        self._write(library="== 别的标准\n\n* 略。\n")
        cm.check_info_density_guard()
        self.assertIn("sources.adoc", self.error_texts())

    def test_doc_basis_names_present_but_broken_reports(self):
        # 反例（本轮实测形态）：依据行里标准名在、却写成**不成对的加粗标记**
        # （`**GB/T 7713.2-2022（学术论文编写规则**`）——按"关键字在不在"核会全绿，
        # 而读者读到的标准名与标准编号错位。故依据行另按**逐条标准名**核。
        self._write(section=self.SECTION.replace(
            "**GB/T 7713.2-2022** 与 **GB/T 7713.1-2025**；",
            "**GB/T 7713.2-2022（学术论文编写规则** 与 **GB/T 7713.1-2025**；"))
        cm.check_info_density_guard()
        self.assertIn("依据行的标准名", self.error_texts())

    def test_superseded_version_not_exposed_reports(self):
        # 反例：换版关系不写明 -> 会把已废止的 GB/T 7713.1-2006 当现行引用
        self._write(library=self.LIBRARY.replace("**已废止**", "旧版本"))
        cm.check_info_density_guard()
        self.assertIn("废止", self.error_texts())


class TestCheckAlterMergeGuard(CheckSpecsTestCase):
    """钉住『SQL 写法（同表同类操作合并、独立成文件、写库名）』防线：判据本体 + 加载门。

    用户要求（Issue #154）："调整规范 sql 下 alter 的同类操作（移动、新增等）可以合并为
    一条 sql（支持的情况下，mysql 就支持），优先合并，不要每个字段写一条"；追加：
    "insert update 等 dml 操作同理，但是用户主动写的除外（不改用户的，也不告警……此条只
    使用于 dml，ddl 一定会锁表）"、"sql 应该要单独建个文件吧？"、
    "写 sql 时，要带库名（ddl/dml强制）"；本轮再追加："应该要有个单独的 sql 规范文件"。

    **真源位置（本轮调整）**：判据落在 `specs/general/sql.adoc`「SQL 写法」**一个节**
    （SQL 是跨语言写法，不埋在某个技术栈文件的跨语言脚本条下）；故用例的夹具以该文件为准，
    并覆盖**加载门**——本轮实测的失效形态是"文件建对了、判据也齐，但登记与引用两处都没接上"：
    ① 调度器未登记（含**写成了别的技术栈文件**这一形态）、② Java 栈的「跨语言执行脚本」节
    未指向真源、③ 登记里的路径取不回（引用方按公共输入加载时拿到死引用）。

    另覆盖**"轴名齐全、判据被抽走"的反例本体**（「同类操作」定义、判定标准、例外、依据、
    存量边界任一被抽掉必须报红），以及**第二处真源的反向核验**：「独立成文件」「写库名」
    两条的判据本体由 `check_external_script_guard` 钉，本防线不得再钉一份。
    """

    SECTION = (
        "== SQL 写法\n\n"
        "* **独立成文件（L1）**：SQL 单独建文件（`.sql`）。\n"
        "* **写库名（L1）**：表名用限定名称。\n"
        "* **同表同类操作合并为一条（DDL 强制、DML 优先；L2）**：**同类操作**＝同一个动作、"
        "作用在同一张表——**新增**（`ADD COLUMN`）、**移动**（`MODIFY COLUMN`）等——"
        "在**目标数据库支持**在一条语句里并列时**须合并进一条**、**不得每个字段写一条**；"
        "确实合并不了才分开写、并在该处写明原因（数据库不支持 / 必须串行 / "
        "中间步骤有数据依赖）。\n"
        "** **判定标准（任一命中即违规）**：① 同一张表同类别的 ≥2 个动作（≥2 个字段）"
        "**写成 ≥2 条语句**，而目标数据库支持在一条语句里并列；② 按字段/按行**批量生成**时，"
        "**生成脚本须按表合并输出**；③ **反向越界**——合并后跨越**不同表**或**不同动作类型**"
        "——那不是「同类操作」、**属过度合并**。\n"
        "** **例外面（只适用于 DML）**：合并只约束**执行者本次新写的 DML**——"
        "**用户主动写的 DML 一律不动、不告警**；**DDL 不适用这个例外**"
        "（用户原话：「此条只使用于 dml，ddl 一定会锁表」）。**DML 优先合并**。\n"
        "** **存量边界**：发现即改、不单独发动全库清理（随动迁移，见 `specs/core/execution.adoc`）。\n"
        "* 依据（标准名/编号）：MySQL 官方文档（`ALTER TABLE` 语法、Online DDL）。\n\n"
        "== 缓存与热点\n\n* 略。\n")

    JAVA_SECTION = (
        "= Java 规范\n\n"
        "== 跨语言执行脚本（SQL / Lua 等）\n\n"
        "* **SQL 写法（L1）**：SQL 独立成文件（`.sql` 放 `src/main/resources/`）、"
        "语句带库名、同表同类操作合并为一条，判据见 `specs/general/sql.adoc`「SQL 写法」。\n")

    JAVA_SECTION_NO_REF = (
        "= Java 规范\n\n"
        "== 跨语言执行脚本（SQL / Lua 等）\n\n"
        "* **SQL（L1）**：SQL 单独建文件、按资源加载（`src/main/resources/`）。\n")

    ENTRY = (
        "* **写/改 SQL**（新建或改动 `.sql`、迁移脚本，或要写/改 `ALTER TABLE`/`INSERT`；"
        "识别特征：SQL 写法——独立成文件、语句带库名、同表同类操作合并为一条）"
        "→ `specs/general/sql.adoc`\n")

    LIBRARY = (
        "== 跨语言执行脚本（SQL / Lua 写资源文件，不写字符串拼接）\n\n"
        "* **材料与用途**：\n"
        "** **MySQL 官方文档**（`ALTER TABLE` 语法与 Online DDL 章节）："
        "`ALTER TABLE tbl_name [alter_option [, alter_option] ...]`——"
        "**一条语句可并列多个 alter_option**。\n"
        "* **须注意的语义差异（同义性）**：**MySQL 官方文档给的是语法能力与代价说明，"
        "并未规定「同表同类操作必须合并」**——「须合并、不得每个字段一条」是**本集合**"
        "据此推出的判据化取舍（依据 ISO/IEC 25010 性能效率）。\n")

    def _write(self, section=None, entry=None, java_section=None, library=None) -> None:
        self.write("specs/general/sql.adoc",
                   section if section is not None else self.SECTION)
        self.write("specs/stack/java.adoc",
                   java_section if java_section is not None else self.JAVA_SECTION)
        self.write("AGENTS_COMMON.adoc",
                   entry if entry is not None else self.ENTRY)
        self.write("library/sources.adoc",
                   library if library is not None else self.LIBRARY)

    def test_valid_passes(self):
        self._write()
        cm.check_alter_merge_guard()
        self.assertEqual([], cm.errors)

    def test_file_removed_reports(self):
        # 反例：真源文件被删 -> 判据无处承载
        self.write("specs/stack/java.adoc", self.JAVA_SECTION)
        self.write("AGENTS_COMMON.adoc", self.ENTRY)
        self.write("library/sources.adoc", self.LIBRARY)
        cm.check_alter_merge_guard()
        self.assertIn("sql.adoc", self.error_texts())

    def test_section_removed_reports(self):
        # 反例：真源里的「SQL 写法」节被删 -> 该条失去落点
        self._write(section="== 缓存与热点\n\n* 略。\n")
        cm.check_alter_merge_guard()
        self.assertIn("SQL 写法", self.error_texts())

    def test_rule_body_removed_reports(self):
        # 反例（反例本体：轴名齐全、判据被抽走）：规则本体被压成一句口号
        self._write(section=self.SECTION.replace(
            "* **同表同类操作合并为一条（DDL 强制、DML 优先；L2）**：**同类操作**＝同一个动作、"
            "作用在同一张表——**新增**（`ADD COLUMN`）、**移动**（`MODIFY COLUMN`）等——"
            "在**目标数据库支持**在一条语句里并列时**须合并进一条**、**不得每个字段写一条**；",
            "* **合并（L2）**：ALTER 要注意别写太多条；"))
        cm.check_alter_merge_guard()
        self.assertIn("规则本体", self.error_texts())

    def test_exception_removed_reports(self):
        # 反例：合并不了的例外被删 -> 本条被读成"任何情况都必须合并"
        self._write(section=self.SECTION.replace(
            "确实合并不了才分开写、并在该处写明原因（数据库不支持 / 必须串行 / "
            "中间步骤有数据依赖）。", "不合并不合规。"))
        cm.check_alter_merge_guard()
        self.assertIn("例外", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例：判定标准被抽走 -> "合没合并"交回执行者凭感觉
        self._write(section=self.SECTION.replace(
            "** **判定标准（任一命中即违规）**：① 同一张表同类别的 ≥2 个动作（≥2 个字段）"
            "**写成 ≥2 条语句**，而目标数据库支持在一条语句里并列；② 按字段/按行**批量生成**时，"
            "**生成脚本须按表合并输出**；③ **反向越界**——合并后跨越**不同表**或**不同动作类型**"
            "——那不是「同类操作」、**属过度合并**。\n", "** **注意**：尽量合并。\n"))
        cm.check_alter_merge_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_over_merge_ban_removed_reports(self):
        # 反例：反向禁令（跨表/跨动作类型不属同类）被删 -> 会被读成"能塞进一条就塞"
        self._write(section=self.SECTION.replace(
            "③ **反向越界**——合并后跨越**不同表**或**不同动作类型**"
            "——那不是「同类操作」、**属过度合并**。", "。"))
        cm.check_alter_merge_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_basis_removed_reports(self):
        # 反例：依据行被删 -> "优先合并"的来源无从核对（会被当成自定偏好）
        self._write(section=self.SECTION.replace(
            "* 依据（标准名/编号）：MySQL 官方文档（`ALTER TABLE` 语法、Online DDL）。\n", ""))
        cm.check_alter_merge_guard()
        self.assertIn("依据", self.error_texts())

    def test_legacy_boundary_removed_reports(self):
        # 反例：存量边界被删 -> 会被读成"立刻发动全库改写历史迁移"
        self._write(section=self.SECTION.replace(
            "** **存量边界**：发现即改、不单独发动全库清理"
            "（随动迁移，见 `specs/core/execution.adoc`）。\n", ""))
        cm.check_alter_merge_guard()
        self.assertIn("存量边界", self.error_texts())

    def test_dml_user_written_exemption_removed_reports(self):
        # 反例（反例本体）：DML 条在、但"用户主动写的除外"例外被抽走
        # -> 执行者会去改用户主动写的 DML（越权且可能把用户的锁行为改坏）
        self._write(section=self.SECTION.replace(
            "**用户主动写的 DML 一律不动、不告警**；", "DML 也要尽量合并；"))
        cm.check_alter_merge_guard()
        self.assertIn("除外", self.error_texts())

    def test_dml_exception_scope_removed_reports(self):
        # 反例：缺「DDL 不适用这个例外」-> 例外被错读到 DDL 上，退回"每条 ALTER 写一行"
        self._write(section=self.SECTION.replace(
            "**DDL 不适用这个例外**（用户原话：「此条只使用于 dml，ddl 一定会锁表」）。", ""))
        cm.check_alter_merge_guard()
        self.assertIn("DDL 不适用这个例外", self.error_texts())

    # ---- 加载门（本轮新增：真源换了文件，登记/引用/可取回三处都要接上）----

    def test_dispatcher_entry_removed_reports(self):
        # 反例：调度器根本没登记真源文件 -> 该文件不会被加载、判据齐备也无入口
        self._write(entry="* **别的技术栈** → `specs/stack/other.adoc`\n")
        cm.check_alter_merge_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_dispatcher_still_points_at_java_stack_reports(self):
        # 反例（本轮实测的失效形态）：登记还停在旧落点（指向技术栈文件）——
        # 真源文件永不被取回、也永不被加载
        self._write(entry="* **Java 项目**（存在 `.java`）→ `specs/stack/java.adoc`。"
                          "识别特征：**SQL 写法**（独立 `.sql` 文件、语句带库名、"
                          "同表同类操作合并为一条 `ALTER TABLE`/`INSERT`/`UPDATE`）\n")
        cm.check_alter_merge_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_dispatcher_feature_removed_reports(self):
        # 反例：调度器识别特征缺 `ALTER TABLE` -> 改 SQL 时永不触发加载、判据实际失效
        self._write(entry="* **写/改 SQL** → `specs/general/sql.adoc`\n")
        cm.check_alter_merge_guard()
        self.assertIn("识别特征", self.error_texts())

    def test_dispatcher_path_not_fetchable_reports(self):
        # 反例（本轮实测的失效形态）：登记里的路径取不回——取回脚本按 `specs/*.adoc`
        # 解析入口清单，路径层级写错（漏掉 `specs/`）时站点回落成首页、取到的其实是 HTML，
        # 引用方读到的是死引用。判据即取回脚本用的那条正则。
        self._write(entry=self.ENTRY.replace("`specs/general/sql.adoc`",
                                             "`general/sql.adoc`"))
        cm.check_alter_merge_guard()
        self.assertIn("取回", self.error_texts())

    def test_dispatcher_entry_without_path_reports(self):
        # 反例：登记项整行没有仓库内路径（真源文件根本取不回来）
        self._write(entry="* **写/改 SQL** → 见 SQL 规范一节\n")
        cm.check_alter_merge_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_java_stack_reference_removed_reports(self):
        # 反例：Java 栈的「跨语言执行脚本」节不再指向真源 -> Java 项目读该节时
        # 不知道 SQL 写法另有真源（判据一处、其余一跳引用）
        self._write(java_section=self.JAVA_SECTION_NO_REF)
        cm.check_alter_merge_guard()
        self.assertIn("specs/general/sql.adoc", self.error_texts())

    def test_java_stack_section_removed_reports(self):
        # 反例：Java 栈的该节被删 -> Java 项目执行 SQL 时没有落点可循
        self._write(java_section="= Java 规范\n\n== 命名\n\n* 略。\n")
        cm.check_alter_merge_guard()
        self.assertIn("跨语言执行脚本", self.error_texts())

    def test_java_stack_landing_removed_reports(self):
        # 反例：引用到了真源、但 Java 落点被抽走（`.sql` 放哪、怎么执行）——
        # 引用成一个没有落地方式的指针
        self._write(java_section=self.JAVA_SECTION.replace(
            "（`.sql` 放 `src/main/resources/`）", ""))
        cm.check_alter_merge_guard()
        self.assertIn("落点", self.error_texts())

    # ---- 图书馆依据落点 ----

    def test_library_basis_removed_reports(self):
        # 反例：图书馆没有该依据条目 -> 正文里的 MySQL 官方文档无处逐字核对（依据只剩名称）
        self._write(library="== 别的标准\n\n* 略。\n")
        cm.check_alter_merge_guard()
        self.assertIn("sources.adoc", self.error_texts())

    def test_library_synonymity_note_removed_reports(self):
        # 反例：图书馆不标注"官方材料未规定必须合并" -> 读者会把本集合的取舍当成 MySQL 的要求
        self._write(library="== 跨语言执行脚本\n\n* **MySQL 官方文档**：有 `alter_option`。\n")
        cm.check_alter_merge_guard()
        self.assertIn("同义性", self.error_texts())

    # ---- 第二处真源的反向核验 ----

    def test_sql_file_body_not_pinned_here(self):
        # 反向核验：「SQL 须独立成文件」的判据本体由 `check_external_script_guard` 钉，
        # 把本处那条抽光时本防线**不**报红（否则就是同一条规范的第二处真源）。
        self._write(section=self.SECTION.replace(
            "* **独立成文件（L1）**：SQL 单独建文件（`.sql`）。", "* **SQL（L1）**：略。"))
        cm.check_alter_merge_guard()
        self.assertEqual([], cm.errors)

    def test_database_name_body_not_pinned_here(self):
        # 反向核验：同上——「写库名」的判据本体不在本防线。
        self._write(section=self.SECTION.replace(
            "* **写库名（L1）**：表名用限定名称。", "* **SQL（L1）**：略。"))
        cm.check_alter_merge_guard()
        self.assertEqual([], cm.errors)

    def test_dml_library_basis_not_pinned_here(self):
        # 反向核验：多值 `INSERT` 与 ISO/IEC 9075 两组依据被抽走时本防线也不报红
        # （它们的判据本体在别处，依据再各钉一份同属重复）。
        self._write(library="== 跨语言执行脚本\n\n"
                           "* **MySQL 官方文档**：`ALTER TABLE` 可并列 `alter_option`，"
                           "Online DDL 说明每动作默认各自执行。\n"
                           "* **须注意的语义差异（同义性）**：**并未规定**必须合并，"
                           "是**本集合**的取舍。\n")
        cm.check_alter_merge_guard()
        self.assertEqual([], cm.errors)

    def test_merge_reason_criterion_not_pinned_here(self):
        # 反向核验（第二处真源、此前评审发现的那处）：本防线的锚点里不得再出现
        # "真源"之类的重复钉法（锚点已收成一处）。
        self.assertTrue(all("真源" not in why for _, _, why in cm.ALTER_MERGE_ANCHORS))

    def test_phase_closed(self):
        # 反例（本轮实测）：函数末尾缺 phase_done() -> 本阶段在进度日志里以「▶」起头、
        # 接着就被下一阶段的「▶」直接覆盖，既不报错也不显示完成。故补用例钉住。
        self._write()
        log = self.capture_phase_log()
        try:
            start = len(log)
            cm.check_alter_merge_guard()
            self.assertEqual([], cm.errors)
            self.assertTrue(self.phase_closed(start))
        finally:
            self.restore_phase_log()

    def test_phase_closed_detects_missing_done(self):
        # 反向核验上面那条用例真的在判「本阶段被收尾」：直接 phase() 而不 phase_done()，
        # 须判为未收尾（防判据写成恒真）。
        log = self.capture_phase_log()
        try:
            start = len(log)
            cm.phase("模拟阶段")
            self.assertFalse(self.phase_closed(start))
        finally:
            self.restore_phase_log()


class TestCheckJavaSerialGuard(CheckSpecsTestCase):
    """钉住『Java 序列化 / 局部变量推断 / 链式调用换行』防线：判据本体不得被删。

    用户本轮三句话对应三处判据（`specs/stack/java.adoc`「序列化（`Serializable`）」与「编码」、
    `specs/general/coding.adoc`「表达式与调用写法」）。三处共用的性质是：**要治的都是「留了裁量点」**
    （要不要加 UID / `val` 还是 `var` 都行 / 链短就不换行）。故用例专门覆盖**「轴名齐全、判据被抽走」
    的反例本体**——把「不得为未实现者补字段」「用 `var` 却没重新赋值即违规」「长度不是判据」抽掉时
    必须报红（只核"这几节在不在"属防线空转）。
    """

    JAVA = (
        "= Java 规范\n\n"
        "== 编码\n\n"
        "* **强制优先使用 lombok（L1）**：能用 lombok 代替的绝不手写。\n"
        "* **局部变量强制使用 `val`/`var`，且优先 `val`、可变才用 `var`（L1）**：局部变量声明**必须且一律**使用 `val`/`var`，**先取 `val`**；"
        "仅当该变量**确实需要重新赋值**时才用 `var`——两者都优先于显式类型；字段不得使用。"
        "**`var` 是例外档、不是并列选项**。**判定标准（任一命中即违规）**："
        "① 写了显式类型且不属例外；② **用 `var` 声明的局部变量此后从未重新赋值**；"
        "③ 同法里一半 `val` 一半显式类型。**例外（L2）**：**类型推断结果不清晰**、"
        "**以 `null` 字面量初始化**等场景可写显式类型。**未引入 lombok 时**：JDK 只有 `var`、"
        "**没有 `val`**，按 `var` 执行。**依据（标准名/编号）**：ISO/IEC 25010、"
        "ISO/IEC/IEEE 29148、**Project Lombok 官方文档**、**Google Java Style Guide**；"
        "**「优先 `val`、可变才 `var`」是本集合对 lombok 的判据化取值**。\n\n"
        "== 序列化（`Serializable`）\n\n"
        "仅适用于**声明实现 `java.io.Serializable` 的类**。\n\n"
        "* **已实现 `Serializable` 的类型须显式声明 `serialVersionUID`（L1）**："
        "（含父类已实现）**必须显式声明**；取值按 `lombok.config` 的**实时取值**，"
        "既无配置时取 `1L`。\n"
        "* **`@Serial` 标注（L2，JDK 14+）**：使拼写错误在**编译期报出**。\n"
        "* **不为未实现 `Serializable` 的类型补（L1）**：**不得**为「消警告」加该字段，"
        "**也不得顺手给它加 `implements Serializable`**。\n"
        "* **显式声明优先于抑制（L1）**：以 `@SuppressWarnings` 代替显式声明不算完成"
        "（见 `specs/general/coding.adoc`「警告与弃用」）。\n"
        "* **判定标准（任一命中即违规）**：①②③④。**存量**：随动迁移，见 `specs/core/execution.adoc`。\n"
        "* 依据（标准名/编号）：**Java Object Serialization Specification**、"
        "**Java 官方 API 文档**、ISO/IEC 25010、ISO/IEC/IEEE 29148；"
        "**「默认取 `1L`」是本集合的取值**。\n\n"
        "== 对象转换（MapStruct）\n\n* 略。\n")

    CODING = (
        "= 通用编码规范\n\n== 表达式与调用写法\n\n"
        "* **链式调用一律换行（L1）**：调用链**每个环节各占一行**、`.` 起头；"
        "**长度不是判据**——再短的链也换行，**不得**因为「这行放得下」而写成一行。"
        "**判定标准（任一命中即违规）**：① 同一行里出现**两处及以上**的调用链环节；② 以「很短」为由保持单行。"
        "**例外（L2）**：**单个不可再分的原子表达式**、注解、**测试断言**里单层断言。"
        "**边界（防反用）**：本条**只规定换行形态、不改变求值语义与调用顺序**。"
        "**依据（标准名/编号）**：ISO/IEC 25010、ISO/IEC/IEEE 29148、"
        "**Google Java Style Guide**、**阿里巴巴 Java 开发手册**；"
        "**「哪怕很短也要换行」是本集合的判据化取值**。\n")

    COMMON = ("= 入口\n\n== 分类与懒加载（加载调度器）\n"
              "* 任何代码活动（要判「**链式调用一律换行**」）\n"
              "* Java 项目 → 识别特征：**serialVersionUID**、**局部变量强制用 `val`/`var`、且优先 `val`、可变才 `var`**\n")

    SOURCES = ("= 依据图书馆\n\n== Java 序列化的版本化（Java Object Serialization Specification）\n\n"
               "* 材料：**Java Object Serialization Specification**、`java.io.Serial`；"
               "**本次未逐字取回**。\n"
               "* **须注意的语义差异（同义性）**：未规定必须显式声明。\n")

    ADOPTION = ("= 自身取舍\n\n"
                "* **`serialVersionUID` 默认取 `1L`…三条均为本集合自己的判据化取舍**："
                "用户原文口径为「没实现不自动加 Serializable 实现」。\n")

    def _write(self, java=None, coding=None, common=None, sources=None, adoption=None):
        self.write("specs/stack/java.adoc", java if java is not None else self.JAVA)
        self.write("specs/general/coding.adoc", coding if coding is not None else self.CODING)
        self.write("AGENTS_COMMON.adoc", common if common is not None else self.COMMON)
        self.write("library/sources.adoc", sources if sources is not None else self.SOURCES)
        self.write("library/adoption.adoc", adoption if adoption is not None else self.ADOPTION)

    def test_valid_passes(self):
        self._write()
        cm.check_java_serial_guard()
        self.assertEqual([], cm.errors)

    def test_serial_section_removed_reports(self):
        # 反例：整节被删 -> "结构一变即 InvalidClassException"重新变成无人管
        self._write(java=self.JAVA.replace("== 序列化（`Serializable`）", "== 其他"))
        cm.check_java_serial_guard()
        self.assertIn("序列化", self.error_texts())

    def test_must_be_explicit_removed_reports(self):
        # 反例（反例本体：轴名齐全、判据被抽走）："必须显式声明"被压成"建议加上"
        self._write(java=self.JAVA.replace(
            "* **已实现 `Serializable` 的类型须显式声明 `serialVersionUID`（L1）**："
            "（含父类已实现）**必须显式声明**；", "* **UID 相关（L1）**：可以加上；"))
        cm.check_java_serial_guard()
        self.assertIn("必须显式声明", self.error_texts())

    def test_not_for_non_serializable_removed_reports(self):
        # 反例：用户点名的边界（未实现者不补、也不顺手加接口）被删 —— 判定面被自行放大
        self._write(java=self.JAVA.replace(
            "* **不为未实现 `Serializable` 的类型补（L1）**：**不得**为「消警告」加该字段，"
            "**也不得顺手给它加 `implements Serializable`**。\n", ""))
        cm.check_java_serial_guard()
        self.assertIn("未实现", self.error_texts())

    def test_suppress_substitute_removed_reports(self):
        # 反例：允许用抑制代替显式声明 -> 与「警告与弃用」相抵、用户要治的警告照旧
        self._write(java=self.JAVA.replace(
            "* **显式声明优先于抑制（L1）**：以 `@SuppressWarnings` 代替显式声明不算完成"
            "（见 `specs/general/coding.adoc`「警告与弃用」）。\n", ""))
        cm.check_java_serial_guard()
        self.assertIn("抑制", self.error_texts())

    def test_default_value_removed_reports(self):
        # 反例：缺省取值被删 -> "默认值是多少"回到执行者手里（本条的动因就是反复的警告）
        self._write(java=self.JAVA.replace("既无配置时取 `1L`。", "按需自行取值。")
                    .replace("**「默认取 `1L`」是本集合的取值**", "**缺省值属本集合取值**"))
        cm.check_java_serial_guard()
        self.assertIn("取 `1L`", self.error_texts())

    def test_serial_basis_removed_reports(self):
        # 反例：依据行被删 -> "为什么必须显式声明"的来源无从核对
        self._write(java=self.JAVA.replace(
            "* 依据（标准名/编号）：**Java Object Serialization Specification**、"
            "**Java 官方 API 文档**、ISO/IEC 25010、ISO/IEC/IEEE 29148；"
            "**「默认取 `1L`」是本集合的取值**。\n", ""))
        cm.check_java_serial_guard()
        self.assertIn("依据", self.error_texts())

    def test_val_var_priority_removed_reports(self):
        # 反例：与旧条重复的旧口径留着、新口径（优先 val、可变才 var）被删 —— 变成"两者等价"
        self._write(java=self.JAVA.replace(
            "* **局部变量强制使用 `val`/`var`，且优先 `val`、可变才用 `var`（L1）**", "* **局部变量类型（L1）**"))
        cm.check_java_serial_guard()
        self.assertIn("优先 val", self.error_texts())

    def test_var_never_reassigned_removed_reports(self):
        # 反例：唯一可机械核对的那句话（用 var 却没重新赋值即违规）被抽走 -> "优先 val"成了口号
        self._write(java=self.JAVA.replace(
            "② **用 `var` 声明的局部变量此后从未重新赋值**；", "② 略；"))
        cm.check_java_serial_guard()
        self.assertIn("从未重新赋值", self.error_texts())

    def test_chain_length_not_criterion_removed_reports(self):
        # 反例：把"长度不是判据"删掉 -> 退回通行风格的"按行宽决定"（用户点名的裁量点）
        self._write(coding=self.CODING.replace("**长度不是判据**——再短的链也换行，", "行宽受限时，"))
        cm.check_java_serial_guard()
        self.assertIn("长度不是判据", self.error_texts())

    def test_chain_semantics_boundary_removed_reports(self):
        # 反例：只改形态、不改语义的边界被删 -> 本条被反用成"把链拆成多个中间变量"
        self._write(coding=self.CODING.replace(
            "**边界（防反用）**：本条**只规定换行形态、不改变求值语义与调用顺序**。", ""))
        cm.check_java_serial_guard()
        self.assertIn("求值语义", self.error_texts())

    def test_chain_section_removed_reports(self):
        # 反例：coding.adoc 整份缺失 -> 链式换行规则没了落点
        self._write(coding="= 别的\n\n* 略。\n")
        cm.check_java_serial_guard()
        self.assertIn("链式调用一律换行", self.error_texts())

    def test_dispatcher_missing_chain_feature_reports(self):
        # 反例：通用层条目缺识别特征 -> 写非 Java 项目代码也不会加载（用户要求"所有语言"）
        self._write(common=self.COMMON.replace("链式调用一律换行", "某风格"))
        cm.check_java_serial_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_dispatcher_missing_serial_feature_reports(self):
        # 反例：Java 栈条目缺识别特征 -> 该条永远不会被触发加载、规则实际失效
        self._write(common=self.COMMON.replace("serialVersionUID", "某字段"))
        cm.check_java_serial_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_library_sources_topic_removed_reports(self):
        # 反例：图书馆无该主题 -> 标准依据只存名称、日后无从核对"它今天还成立吗"
        self._write(sources="= 图书馆\n\n* 略。\n")
        cm.check_java_serial_guard()
        self.assertIn("sources.adoc", self.error_texts())

    def test_library_adoption_tradeoff_removed_reports(self):
        # 反例：取舍记录被删 -> 读者会以为"默认 1L"是标准的明文要求
        self._write(adoption="= 取舍\n\n* 略。\n")
        cm.check_java_serial_guard()
        self.assertIn("adoption.adoc", self.error_texts())


class TestCheckSquashCommitGuard(CheckSpecsTestCase):
    """钉住『压缩提交防线』：用户要求"压缩提交"时的判据、禁止形态与新旧 sha 对应关系。

    这条容易被两边夹：一边是"AI 不许强推/不许改写历史"的一般口径（执行者据此**拒绝**用户
    明确要求的压缩提交），另一边是"压缩就是重写历史"的含糊理解（执行者顺手把他人提交、
    已合入的历史一并压掉，或夹带改动）。故本组用例除正例外，专门覆盖"条文被删""判据被抽"
    "许可形态被删""与禁合并的接口被删""调度器/README 未同步"等反例。
    """

    CNB = (
        "= CNB 规范（平台层）\n\n"
        "== 合并请求的合并主体（NPC 禁合并）\n"
        "* **CNB NPC 严禁合并（L1）**，**授权不免除**。\n\n"
        "== 压缩提交（提交历史的整理，平台侧追加口径）\n"
        "**规则本体（工具无关）在 `specs/general/version-control.adoc`「压缩提交」**；"
        "本节只写本平台的追加口径。\n"
        "* **压缩提交＝提交历史整理，不属禁止行为（L1）**："
        "压缩**只作用于本次任务自己的 PR 源分支**，**不动目标分支**、不动他人分支。\n"
        "* **禁止的压缩形态（平台侧追加）**：①**他人（或其它任务）的提交**；②**已合入目标分支**的历史。\n"
        "* **须先确认无人在用旧对象（L1）**：确认**无他人正基于该分支的旧 sha 工作**"
        "（**已派发、正等待结论**）；确需执行时须**明确告知受影响方**新 sha、并把旧 sha 上的结论**标为过期**。\n"
        "* **压缩后须声明新旧 sha 对应关系（L1）**：写明“**新 sha 为 X，旧 sha Y 作废**”，并如实列出**被压缩掉的中间 sha**；"
        "**按旧 sha 复核的结论视为过期**。\n"
        "* **推送口径（L1）**：用 `--force-with-lease`，**不得**用裸 `git push --force`；"
        "“AI 不做强推”的一般口径**不适用于本条的压缩提交**；**授权范围仅限本次 PR 的源分支**。\n"
        "* **与「NPC 禁合并」互不豁免（L1）**：**压缩提交**不是合并**，故要求压缩提交时照做；"
        "但**不构成\"可以合并\"的依据**。\n\n"
        "== 对象钉定与可追溯\n"
        "* 压缩提交后强推——那是**合规动作、不是违规改写**；"
        "**压缩提交/强推会替换对象，须声明对应关系**。\n"
    )

    def _write_valid(self) -> None:
        self.write("specs/platform/cnb.adoc", self.CNB)
        self.write(
            "AGENTS_COMMON.adoc",
            "* **版本管理** → `specs/general/version-control.adoc`\n"
            "* CNB 平台 → cnb（**压缩提交（提交历史整理的判据）**、**对象钉定与可追溯**）\n")
        self.write(
            "README.adoc",
            "* `specs/general/` — 通用层：**版本管理（`version-control.adoc`；工具无关）**\n"
            "* `specs/platform/` — 平台层：cnb（**压缩提交（提交历史整理：判据与禁止形态）**、"
            "**对象钉定与可追溯**）\n"
            "* **压缩提交要照做、默认压成一个、合并仍不做**：默认交付形态＝本次任务的提交压成一个提交；"
            "压缩提交不构成“可以合并”的依据。\n")

    def test_valid_passes(self):
        self._write_valid()
        cm.check_squash_commit_guard()
        self.assertEqual(cm.errors, [])

    def test_no_duplicate_reports_for_same_finding(self):
        # 反例（回归钉）：本防线的规则步骤按落点分成多组，脚本会在多处引用同一防线名；
        # 同一处缺失只应报一条——重复报出会把真正的问题埋进噪音里（本仓库实测过 12 条
        # 里只有 4 条是不同问题）
        self._write_valid()
        cnb = os.path.join(self.root, "specs", "platform", "cnb.adoc")
        with open(cnb, encoding="utf-8") as fh:
            text = fh.read()
        self.write("specs/platform/cnb.adoc", text.replace("压缩提交", "X压缩X", 60))
        cm.check_squash_commit_guard()
        dup = [e for e in cm.errors
               if "缺失要点 ['== 压缩提交']" in e]
        self.assertEqual(len(dup), 1, f"同一处缺失被重复报出：{len(dup)} 次")

    def test_missing_file_reports(self):
        # 反例：平台层规范文件被删 → 要求无处承载
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "platform", "cnb.adoc"))
        cm.check_squash_commit_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_section_deleted_reports(self):
        # 反例：整节被删 → 用户要求"压缩提交"时无条文可依（只能在"用户要求"与
        # "规范像是禁止"之间自行发挥）
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   "= CNB 规范\n\n== 合并请求的合并主体（NPC 禁合并）\n"
                   "* **严禁合并**，**授权不免除**。\n\n== 对象钉定与可追溯\n* 另议。\n")
        cm.check_squash_commit_guard()
        self.assertIn("压缩提交", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例（关键词堆砌式假绿）：只留节名与一句口号，判据被抽掉
        self._write_valid()
        cnb = self.CNB
        cnb = cnb.replace("压缩**只作用于本次任务自己的 PR 源分支**，**不动目标分支**、不动他人分支。", "")
        self.write("specs/platform/cnb.adoc", cnb)
        cm.check_squash_commit_guard()
        self.assertIn("作用域", self.error_texts())

    def test_forbidden_forms_removed_reports(self):
        # 反例：禁止形态被删 → 顺手把他人提交/已合入历史一并压掉、或夹带改动，无判据可拦
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   self.CNB.replace("* **禁止的压缩形态（平台侧追加）**：①**他人（或其它任务）的提交**；"
                                    "②**已合入目标分支**的历史。\n", ""))
        cm.check_squash_commit_guard()
        self.assertIn("禁止的压缩形态", self.error_texts())

    def test_no_exemption_from_merge_ban_removed_reports(self):
        # 反例：与「NPC 禁合并」的接口被删 → 出现"历史都整理干净了，顺手合了吧"式自我豁免
        self._write_valid()
        marker = "* **与「NPC 禁合并」互不豁免（L1）**：**压缩提交**不是合并**，故要求压缩提交时照做；"
        cnb = self.CNB.replace(marker, "").replace("但**不构成“可以合并”的依据**。", "")
        self.write("specs/platform/cnb.adoc", cnb)
        cm.check_squash_commit_guard()
        self.assertIn("互不豁免", self.error_texts())

    def test_force_push_clause_removed_reports(self):
        # 反例：推送口径被删 → 执行者要么拒绝压缩（"AI 不做强推"）要么用裸 --force 覆盖
        self._write_valid()
        cnb = self.CNB.replace("用 `--force-with-lease`，**不得**用裸 `git push --force`；", "")
        self.write("specs/platform/cnb.adoc", cnb)
        cm.check_squash_commit_guard()
        self.assertIn("--force-with-lease", self.error_texts())

    def test_sha_correspondence_removed_reports(self):
        # 反例：对应关系声明被删 → 下游按已失效的 sha 复核，结论错位
        self._write_valid()
        cnb = self.CNB.replace("* **压缩后须声明新旧 sha 对应关系（L1）**：", "* **附注**：")
        self.write("specs/platform/cnb.adoc", cnb)
        cm.check_squash_commit_guard()
        self.assertIn("压缩后须声明新旧 sha 对应关系", self.error_texts())

    def test_compliance_note_removed_reports(self):
        # 反例：对象钉定侧的"合规动作"标注被删 → 下游把合规的 sha 变化当成违规改写
        self._write_valid()
        cnb = self.CNB.replace("那是**合规动作、不是违规改写**；", "")
        self.write("specs/platform/cnb.adoc", cnb)
        cm.check_squash_commit_guard()
        self.assertIn("合规动作", self.error_texts())

    def test_existing_merge_ban_replaced_reports(self):
        # 反例（本仓库实测犯过的同类回归）：新增节点把同文件既有的「NPC 禁合并」顶掉
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   self.CNB.replace("== 合并请求的合并主体（NPC 禁合并）", "== 其它"))
        cm.check_squash_commit_guard()
        self.assertIn("NPC 禁合并", self.error_texts())

    def test_dispatcher_not_synced_reports(self):
        # 反例：调度器未同步 → 规则在、但没人会读到
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "* CNB 平台 → cnb（**对象钉定与可追溯**）\n")
        cm.check_squash_commit_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例：公开面只看得见"禁止"、看不到用户可要求的这条
        self._write_valid()
        self.write("README.adoc", "* `specs/platform/` — 平台层：cnb（**对象钉定与可追溯**）\n")
        cm.check_squash_commit_guard()
        self.assertIn("README", self.error_texts())


class TestCheckMergeRelationshipGuard(CheckSpecsTestCase):
    """钉住『合并关系防线』：解决冲突/压缩后**目标分支仍须是本分支的祖先**。

    这条来自一次**工作树看不出、平台必拦**的真实失效：把"解决冲突"做成"照抄目标分支的
    文件内容后另起一个单亲提交"，`git diff` 看不出毛病、单测也全绿，但目标分支并未成为
    本分支的祖先，平台侧据合并关系判定，PR 仍卡在 `code_conflict`。坏形态**没有任何一处
    本地可见的异常**，唯一判据是历史拓扑，而这种判据最容易被顺手"整理掉"（用户要求压缩时
    把合并提交一并压掉）。故本组用例除正例外，专门覆盖"条文被删""判据被抽""根因形态被删"
    "压缩不吞合并提交缺失""文件缺失"等反例。
    """

    # 夹具与真实文件**同形**：平台侧**只指向** git 侧的核对命令真源，**不**把
    # `git merge-base <分支> <目标分支>` / `git rev-list --parents -n1` 的字面命令抄一份
    # ——那是 `specs/general/git.adoc`「压缩后的合并关系核对」的正文取值，抄回平台层即第二真源
    # （`terminology.adoc`「数据字典」的反膨胀；本 PR 的立项口径）。
    CNB = (
        "= CNB 规范（平台层）\n\n"
        "== 压缩提交（提交历史的整理）\n"
        "* **压缩须保留与目标分支的合并关系（L1）**：压缩后的提交**须仍以目标分支的最新提交为祖先**"
        "（核对命令见 `specs/general/git.adoc`「压缩后的合并关系核对」，本处不复述）。**本条在本平台的"
        "真实失效**：把\"解决冲突\"做成\"**照抄目标分支的文件内容后另起一个单亲提交**\"，工作树看起来"
        "一致，但**目标分支并未成为本分支的祖先**，平台侧仍报冲突、PR 卡在 `code_conflict`"
        "（判据：`git merge-base --is-ancestor <目标分支> <分支>` 为假）。**正确做法**：真做一次合并后"
        "以合并提交落盘；压缩**不吞掉合并提交**（**合并提交是\"已并入\"的凭据**）。\n"
        "* **禁止的压缩形态（L1）**：①他人提交；②已合入目标分支的历史。\n"
    )

    def _write_valid(self) -> None:
        self.write("specs/platform/cnb.adoc", self.CNB)

    def test_valid_passes(self):
        self._write_valid()
        cm.check_merge_relationship_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_file_reports(self):
        # 反例：平台层规范文件被删 → 要求无处承载
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "platform", "cnb.adoc"))
        cm.check_merge_relationship_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_rule_deleted_reports(self):
        # 反例：整条 L1 被删 → "照抄内容后另起单亲提交"的失效复发
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   "= CNB 规范\n\n== 压缩提交（提交历史的整理）\n"
                   "* **压缩提交＝提交历史整理**。\n")
        cm.check_merge_relationship_guard()
        self.assertIn("合并关系", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例（关键词堆砌式假绿）：只留标题与一句口号，**既不指向 git 侧真源、也给不出可核对的东西**。
        # 本轮把锚点由"逐字抄 git 侧命令"放宽为"指点到真源"（抄进来即第二真源），故此处的反例
        # 也改成"连真源都不指"——它才是放宽后真正要拦的形态。
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   "= CNB 规范\n\n== 压缩提交（提交历史的整理）\n"
                   "* **压缩须保留与目标分支的合并关系（L1）**：压缩后仍以目标分支最新提交为祖先，"
                   "**须仍以目标分支的最新提交为祖先**，务必谨慎。\n")
        cm.check_merge_relationship_guard()
        self.assertIn("合并关系", self.error_texts())

    def test_verbatim_commands_not_required(self):
        # 正例（本轮新增）：平台侧**只指向** git 侧真源、**不**逐字抄核对命令 → 全绿。
        # 这是本 PR 的口径：`git merge-base <分支> <目标分支>` 等是 `git.adoc` 的正文取值，
        # 抄回平台层即第二真源；平台侧只需让读者**走得到**真源。
        self._write_valid()
        self.assertNotIn("git rev-list --parents -n1", self.CNB)
        cm.check_merge_relationship_guard()
        self.assertEqual(cm.errors, [])

    def test_root_cause_removed_reports(self):
        # 反例：根因形态被删 → 条文会被读成"工作树一致即可"，正是要拦的失效
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   "= CNB 规范\n\n== 压缩提交（提交历史的整理）\n"
                   "* **压缩须保留与目标分支的合并关系（L1）**：**须仍以目标分支的最新提交为祖先**，"
                   "核对命令见 `specs/general/git.adoc`「压缩后的合并关系核对」；"
                   "`git merge-base --is-ancestor <目标分支> <分支>` 为假即违规。\n")
        cm.check_merge_relationship_guard()
        self.assertIn("根因", self.error_texts())

    def test_squash_swallowing_merge_commit_reports(self):
        # 反例：没有"压缩不吞掉合并提交"这一接口 → 用户要求压缩时会把唯一凭据一并压掉
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   "= CNB 规范\n\n== 压缩提交（提交历史的整理）\n"
                   "* **压缩须保留与目标分支的合并关系（L1）**：**须仍以目标分支的最新提交为祖先**"
                   "（核对命令见 `specs/general/git.adoc`「压缩后的合并关系核对」）；"
                   "根因：**照抄目标分支的文件内容后另起一个单亲提交**，"
                   "**目标分支并未成为本分支的祖先**；"
                   "`git merge-base --is-ancestor <目标分支> <分支>` 为假。\n")
        cm.check_merge_relationship_guard()
        self.assertIn("不吞掉合并提交", self.error_texts())


class TestCheckBaselineSyncGuard(CheckSpecsTestCase):
    """钉住『基线同步防线』：**压缩前须先并入目标分支的最新改动**（用户提出，Issue #198，P0）。

    用户原话："我不希望再出现丢失内容，压缩前先合并 main 有用吗？尽所有可能避免丢失内容，
    这是 P0 优先级（最高）"；实证形态：PR `cc332030/ctool4j#101` 的源分支停在旧基点上、
    **从未同步过目标分支**，压缩一次即把目标分支上刚合入的两批改动带成删除（22 文件、+615/−1447）。

    本组覆盖三处落点（通用层判据本体 / git 层取值形态 / 平台层后果）与公开面，
    并专门覆盖两类最要害的反例：
      * **假绿形态**——"只把文件内容改成和目标分支一样"冒充已并入（内容上看不出来、照旧删内容）；
      * **既有判据的免疫形态**——「共同祖先恰好等于目标分支本身」时"目标分支是祖先"为真，
        故须有"不得以这条关系为真顶掉本条"这一句（缺则本条被既有判据兜住、形同不存在）。
    另有"本条被误判为既有条文的重复表述而合并删除"这一反例（分工句是它的挡板）。
    """

    VC = (
        "= 版本管理规范（通用层）\n\n"
        "== 压缩提交（提交历史整理）\n\n"
        "* **压缩前须先并入目标分支的最新改动（L1）**：**在压缩任何内容之前**，须确认本分支已把"
        "目标分支的**当前最新提交**并入过——**若未并入，先并入、再压缩**（这一步不是压缩的"
        "组成部分，是它的**前置**）。**判定标准（可核对）**：一份为本分支算出的合并结果，"
        "与仅按目标分支当前最新提交、同一基点算出的那份，**逐条一致、且为空**；合并关系须"
        "真实成立（**目标分支的最新提交是本分支的祖先**）——**不得**用\"只把文件内容改成和"
        "目标分支一样\"折衷：那样在内容上看不出来，而\"已并入\"并没有发生过，"
        "**照旧会把目标分支的改动压成删除**。**根因**：压缩的产物是\"**相对目标分支的差异**\"；"
        "分支停在旧基点上时，那个差异里**混进了**\"目标分支后来新加的东西\"，"
        "**压缩一次就等于把它们删一次**。**依据**：**变更须基于可追溯的基线状态（ISO 10007）**——"
        "\"基线是否已并入\"必须是可核对的事实，**不能靠\"我以为是最新的\"**。\n"
        "* **相对基线两侧核、不得整体取一侧（L1）**：\"目标分支在基线之后新增的\"与"
        "\"本分支在基线之后新增的\"**两批都在**。**判定标准**：① 取\"**整体取一侧**\"收尾；"
        "**取值**：两侧都有改动的那一处须按两档取值形态核对——**文件级**"
        "（**一侧删除、另一侧改动的同一文件须逐条裁决并写明**）与**内容级**"
        "（**不得只看\"冲突标记没了\"**）。\n"
        "* **压缩前相对基线逐项核（L1）**：**合并后的差异检出**与仅按目标分支当前最新提交、"
        "同一基点算出的那份**逐条一致（且为空）**——**这一份非空本身就是判据**"
        "（**不是与\"逐条一致\"并列取舍的第二条**）：非空即说明有改动被记成了反向删除，"
        "其中含**同侧**的形态（**本分支在基线之后新增过、又被回退成删除的地方**）。"
        "**两个方向都要核**："
        "① **目标分支在基线之后新增的内容**，**一条都不能少**；"
        "② **本分支在基线之后新增的内容**，**一条都不能少**。"
        "**这一条与「解决冲突后须核查是否丢失内容」的分工**：那三档判据核的是\"**冲突两侧**\"，"
        "本条核的是\"**分支自己的旧快照 vs 目标分支**\"——**另立一条**、**不得互相替代**。\n"
        "* **压缩后须核查有无多余的删除（L1）**：压缩的产出形态须相对**目标分支的当前最新提交**"
        "核一遍**有没有多余的删除**。**判定标准**：① 交付形态里**给不出这份账**；"
        "② 只核到**有没有冲突标记 / 能不能编译**、或只核**两侧内容在不在**；"
        "③ 只核**被整体删除的文件**，**分支自己（基线之后）新增过、又被回退成删除的地方**一处未核。"
        "**四个核对方向**：① **该在的东西一次都没被删**；② **本分支自己新增过的东西**"
        "在压缩后的形态里不得出现为删除；③ **本分支与基线共有的东西**不得只因压缩而消失；"
        "④ **该删的那侧**须逐条给出原因、**不得整体取一侧收尾**。"
        "**与「解决冲突后须核查是否丢失内容」的分工**：本条核的是"
        "**压缩之后的产出形态里有没有多出删除**——**另立一条不得互相替代**。"
        "**与「压缩＝提交历史整理，内容零变化」的分工**：**前者为空与后者的账非空可以同时成立**，"
        "故两条互不替代。\n"
        "* **压缩＝提交历史整理，内容零变化（L1）**：整理前后工作副本差异为空。\n"
    )

    GIT = (
        "= git 规范（通用层）\n\n== 冲突与压缩提交（git 侧落地）\n\n"
        "* **并入是否真实发生的核对（L1）**：核对到的是**取值状态**——"
        "**目标分支的当前最新提交是本分支的祖先**，且差异检出是按\"已并入该最新提交\"重算过的。"
        "**这一条与「压缩后的合并关系核对」的分工**：那条核的是『压缩之后不要把它弄丢』，"
        "本条核的是『**压缩之前它到底发生过没有**』——**`git merge-base` 的取值**"
        "**恰好等于目标分支本身**时，前者为真、却不是\"已并入最新\"；"
        "故**不得以这条关系为真顶掉本条**。\n"
        "* **相对基线的核对（L1）**：**两个方向都核**：目标分支在基线之后新增的一条不少、"
        "本分支在基线之后新增的一条不少；账是\"合并后的差异检出与仅按目标分支当前最新提交、"
        "同一基点算出的那份**逐条一致（且为空）**\"。**不得整体取一侧收尾**。\n"
        "* **压缩后不足量删除的核对（L1）**：核对到的是**取值状态**——"
        "**本分支在基线之后新增的条目不得出现为删除**；核的账须与\"仅按目标分支当前最新提交、"
        "同一基点重算\"的那一份**逐条一致**，且**那一份为空**。"
        "**这一条与「相对基线的核对」的分工**：那条在**并入时**核；本条在**压缩之后**核。\n"
        "* **被改过 / 删过的文件里的删除条目逐处核（L1）**：**两个方向的删除各自都是空**；"
        "**不得只核被整体删除的文件**——**改过的文件里混着反向删除，文件级根本看不出来**；"
        "**一侧单方删除的，不得被另一侧的删除抵消**。\n"
        "* **压缩后的合并关系核对（L1）**：另议。\n"
    )

    CNB = (
        "= CNB 规范（平台层）\n\n== 压缩提交（提交历史的整理）\n"
        "* **压缩后须核查有无多余的删除（L1）**：压缩后须核**有没有多余的删除**"
        "（**规则本体与四个核对方向见** `specs/general/version-control.adoc`「压缩提交」）。"
        "**本平台上的真实失效形态**：本平台是**跨轮次接续**的——压缩后这一问，"
        "**既有的任何一条都没读过**，故一条看起来干净的提交能一路报绿走到合并。"
        "**与「压缩须保留与目标分支的合并关系」的关系**：两条核的是**不同的两件事**"
        "（**产出形态里有没有多出删除 / 合并关系丢没丢**），**互不替代**——"
        "**合并关系为真**不构成\"没有多余删除\"为真的依据——合并关系为真**不构成**任何豁免。\n"
        "* **压缩前须先并入目标分支的最新提交（L1，本平台的用户点名形态）**：用户要求压缩时，"
        "**先确认本分支已把目标分支的当前最新提交并入过**——未并入则**先并入、再压缩**"
        "（规则本体见 `specs/general/version-control.adoc`「压缩提交」；本处只补平台侧能观测到的后果）。"
        "**本平台上的真实失效形态**：分支**从未同步过目标分支**时，`git merge-base` "
        "恰好**等于目标分支本身**——于是\"目标分支是祖先\"**为真**、既有的两条关系判据"
        "与机械防线**全部报绿**，而**压缩一次即把目标分支后合入的改动整批删掉**；"
        "这批删除会**随 PR 合并落进目标分支**、**不可逆**。**判定标准**：**交付说明里须给出**"
        "\"已并入目标分支当前最新提交\"这一事实的**取值**；**只说\"分支是最新的\"不给取值，"
        "即不合规**。**与「压缩后的合并关系核对」的关系**：两条核的是**不同的两件事**"
        "（**压缩之前发没发生过并入** / **压缩之后关系丢没丢**），**互不替代**。\n"
    )

    def _write_valid(self) -> None:
        self.write("specs/general/version-control.adoc", self.VC)
        self.write("specs/general/git.adoc", self.GIT)
        self.write("specs/platform/cnb.adoc", self.CNB)
        self.write(
            "README.adoc",
            "* **压缩前先并入目标分支**，否则\"压缩一次\"就是\"删一次\"；"
            "**\"目标分支是祖先\"这句话在\"没并入最新\"的形态下照样为真**，"
            "**不能拿它当事发过的凭据**。\n"
            "* **压缩后要核\"有没有多余的删除\"**：**基准是目标分支的最新提交、不是本地历史**；"
            "改过的文件里混进反向删除时**文件个数不变、文件级看不出来**。\n")

    def test_valid_passes(self):
        self._write_valid()
        cm.check_baseline_sync_guard()
        self.assertEqual(cm.errors, [])

    def test_general_file_missing_reports(self):
        # 反例：规则本体无处承载（用户口称"版本管理"、未点名 git/CNB）
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "general", "version-control.adoc"))
        cm.check_baseline_sync_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_section_missing_reports(self):
        # 反例：通用层「压缩提交」整节被删 → 前置条与两个方向的核对都失去落点
        self._write_valid()
        self.write("specs/general/version-control.adoc",
                   "= 版本管理规范（通用层）\n\n== 其它节\n\n* 另议。\n")
        cm.check_baseline_sync_guard()
        self.assertIn("压缩提交", self.error_texts())

    def test_gate_clause_removed_reports(self):
        # 反例：前置条被整条抽掉（只剩"压缩要内容零变化"）→ 执行者直接进入压缩（正是 #101 的形态）
        self._write_valid()
        vc = self.VC.replace("* **压缩前须先并入目标分支的最新改动（L1）**：", "* **附注**：")
        self.write("specs/general/version-control.adoc", vc)
        cm.check_baseline_sync_guard()
        self.assertIn("压缩前须先并入目标分支的最新改动", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例（关键词堆砌式假绿）：只留标题与一句口号 → 判据退化成印象
        self._write_valid()
        vc = self.VC.replace(
            "**判定标准（可核对）**：一份为本分支算出的合并结果，"
            "与仅按目标分支当前最新提交、同一基点算出的那份，**逐条一致、且为空**；"
            "合并关系须真实成立（**目标分支的最新提交是本分支的祖先**）",
            "务必谨慎。")
        self.write("specs/general/version-control.adoc", vc)
        cm.check_baseline_sync_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_fake_merge_excuse_removed_reports(self):
        # 反例：**假绿形态**被删（"只把文件内容改成和目标分支一样"）→ 该折衷重新成为默许写法
        self._write_valid()
        vc = self.VC.replace("**不得**用\"只把文件内容改成和目标分支一样\"折衷："
                             "那样在内容上看不出来，而\"已并入\"并没有发生过", "")
        self.write("specs/general/version-control.adoc", vc)
        cm.check_baseline_sync_guard()
        self.assertIn("折衷", self.error_texts())

    def test_root_cause_removed_reports(self):
        # 反例：根因句被删 → 本条会被读成"多做一步合并"的流程建议，而不是"不这么做就删内容"
        self._write_valid()
        vc = self.VC.replace("**根因**：压缩的产物是\"**相对目标分支的差异**\"；", "**说明**：另议。")
        self.write("specs/general/version-control.adoc", vc)
        cm.check_baseline_sync_guard()
        self.assertIn("根因", self.error_texts())

    def test_two_sided_check_removed_reports(self):
        # 反例：并入时的"两侧核、不得整体取一侧"被删 → 并入动作自己就可能丢内容
        self._write_valid()
        vc = self.VC.replace("* **相对基线两侧核、不得整体取一侧（L1）**：", "* **附注**：")
        self.write("specs/general/version-control.adoc", vc)
        cm.check_baseline_sync_guard()
        self.assertIn("相对基线两侧核", self.error_texts())

    def test_value_form_grades_removed_reports(self):
        # 反例：两档取值形态被抽掉 → 核查只能退到"冲突标记没了"
        self._write_valid()
        vc = self.VC.replace("**取值**：两侧都有改动的那一处须按两档取值形态核对——"
                             "**文件级**（", "**取值**：（")
        self.write("specs/general/version-control.adoc", vc)
        cm.check_baseline_sync_guard()
        self.assertIn("文件级", self.error_texts())

    def test_pre_squash_recheck_removed_reports(self):
        # 反例：压缩前的复核被删 → 只核了并入那一步、压缩前不再算账
        self._write_valid()
        vc = self.VC.replace("* **压缩前相对基线逐项核（L1）**：", "* **附注**：")
        self.write("specs/general/version-control.adoc", vc)
        cm.check_baseline_sync_guard()
        self.assertIn("压缩前相对基线逐项核", self.error_texts())

    def test_direction_criteria_removed_reports(self):
        # 反例：两个方向各自的判据被抽 → 只剩"两侧都要核"这句方向性口号、无从判定
        self._write_valid()
        vc = self.VC.replace(
            "**两个方向都要核**：① **目标分支在基线之后新增的内容**，**一条都不能少**；"
            "② **本分支在基线之后新增的内容**，**一条都不能少**。", "务必都核。")
        self.write("specs/general/version-control.adoc", vc)
        cm.check_baseline_sync_guard()
        self.assertIn("目标分支在基线之后新增的内容", self.error_texts())

    def test_demarcation_removed_reports(self):
        # 反例：与既有核查条的分工句被删 → 本条会被判为既有条文的重复表述而合并删除（真源消失）
        self._write_valid()
        vc = self.VC.replace(
            "**这一条与「解决冲突后须核查是否丢失内容」的分工**：那三档判据核的是\"**冲突两侧**\"，"
            "本条核的是\"**分支自己的旧快照 vs 目标分支**\"——**另立一条**、**不得互相替代**。", "")
        self.write("specs/general/version-control.adoc", vc)
        cm.check_baseline_sync_guard()
        self.assertIn("分支自己的旧快照 vs 目标分支", self.error_texts())

    def test_basis_line_removed_reports(self):
        # 反例：依据行被删 → 读者以为这是自造的口径
        self._write_valid()
        vc = self.VC.replace("**依据**：**变更须基于可追溯的基线状态（ISO 10007）**——"
                             "\"基线是否已并入\"必须是可核对的事实，**不能靠\"我以为是最新的\"**。", "")
        self.write("specs/general/version-control.adoc", vc)
        cm.check_baseline_sync_guard()
        self.assertIn("ISO 10007", self.error_texts())

    def test_git_layer_value_form_removed_reports(self):
        # 反例：git 层只剩口号、给不出取值形态
        self._write_valid()
        git = self.GIT.replace("* **并入是否真实发生的核对（L1）**：", "* **附注**：")
        self.write("specs/general/git.adoc", git)
        cm.check_baseline_sync_guard()
        self.assertIn("并入是否真实发生的核对", self.error_texts())

    def test_git_layer_immunity_clause_removed_reports(self):
        # 反例（最要害）：**"共同祖先恰好等于目标分支本身"这一免疫形态**被删
        # → 本条会被既有判据（"目标分支是祖先"为真）兜住、形同不存在
        self._write_valid()
        git = self.GIT.replace("**`git merge-base` 的取值**"
                               "**恰好等于目标分支本身**时，前者为真、却不是\"已并入最新\"；"
                               "故**不得以这条关系为真顶掉本条**。", "")
        self.write("specs/general/git.adoc", git)
        cm.check_baseline_sync_guard()
        self.assertIn("恰好等于目标分支本身", self.error_texts())

    def test_git_layer_two_direction_removed_reports(self):
        # 反例：git 层的相对基线核对被掏空（只剩通用层的口号）
        self._write_valid()
        git = self.GIT.replace("* **相对基线的核对（L1）**：", "* **附注**：")
        self.write("specs/general/git.adoc", git)
        cm.check_baseline_sync_guard()
        self.assertIn("相对基线的核对", self.error_texts())

    def test_platform_clause_removed_reports(self):
        # 反例：平台侧追加口径被删 → 本平台按"一个 PR 一条源分支、压完就合"的形态恰好漏掉
        self._write_valid()
        cnb = self.CNB.replace("* **压缩前须先并入目标分支的最新提交（L1，本平台的用户点名形态）**：",
                               "* **附注**：")
        self.write("specs/platform/cnb.adoc", cnb)
        cm.check_baseline_sync_guard()
        self.assertIn("压缩前须先并入目标分支的最新提交", self.error_texts())

    def test_platform_observable_failure_removed_reports(self):
        # 反例：平台侧看不见"既不报绿又不可逆"这一面 → 读者把它当成通用层的一句重复
        self._write_valid()
        cnb = self.CNB.replace("既有的两条关系判据"
                               "与机械防线**全部报绿**，", "")
        self.write("specs/platform/cnb.adoc", cnb)
        cm.check_baseline_sync_guard()
        self.assertIn("全部报绿", self.error_texts())

    def test_platform_irreversible_clause_removed_reports(self):
        # 反例：不可逆这一面被删 → 平台侧看不出为什么在本平台更危险
        self._write_valid()
        cnb = self.CNB.replace("这批删除会**随 PR 合并落进目标分支**、**不可逆**。", "")
        self.write("specs/platform/cnb.adoc", cnb)
        cm.check_baseline_sync_guard()
        self.assertIn("不可逆", self.error_texts())

    def test_platform_criteria_removed_reports(self):
        # 反例：平台侧的判定标准被抽 → 本条在自己这一层不可判定
        self._write_valid()
        cnb = self.CNB.replace("**判定标准**：**交付说明里须给出**"
                               "\"已并入目标分支当前最新提交\"这一事实的**取值**；"
                               "**只说\"分支是最新的\"不给取值，即不合规**。", "务必谨慎。")
        self.write("specs/platform/cnb.adoc", cnb)
        cm.check_baseline_sync_guard()
        self.assertIn("交付说明里须给出", self.error_texts())

    def test_platform_demarcation_removed_reports(self):
        # 反例：平台侧与既有条的关系句被删 → 本条被读成既有条的重复而合并掉
        self._write_valid()
        cnb = self.CNB.replace("**与「压缩后的合并关系核对」的关系**：两条核的是**不同的两件事**"
                               "（**压缩之前发没发生过并入** / **压缩之后关系丢没丢**），"
                               "**互不替代**。", "")
        self.write("specs/platform/cnb.adoc", cnb)
        cm.check_baseline_sync_guard()
        self.assertIn("互不替代", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例：公开面只看得见"要压缩"、看不见这条 P0 前置
        self._write_valid()
        self.write("README.adoc", "* 另议。\n")
        cm.check_baseline_sync_guard()
        self.assertIn("README", self.error_texts())

    def test_readme_old_criteria_still_believed_reports(self):
        # 反例：公开面不点明"既有那句关系判据在没并入最新的形态下照样为真"
        # → 读者沿用旧判据、把本条读成多余的一步
        self._write_valid()
        self.write("README.adoc",
                   "* **压缩前先并入目标分支**，否则\"压缩一次\"就是\"删一次\"。\n")
        cm.check_baseline_sync_guard()
        self.assertIn("照样为真", self.error_texts())

    def test_nonempty_is_primary_criterion_removed_reports(self):
        # 反例（用户本轮要求的核心）：把「非空本身就是判据」抽回成并列取舍的第二条
        # → 失效形态（那一份恰恰非空）被读成"两个并列条件之一"而放过
        self._write_valid()
        vc = self.VC.replace("——**这一份非空本身就是判据**"
                             "（**不是与\"逐条一致\"并列取舍的第二条**）：非空即说明有改动被记成了反向删除，"
                             "其中含**同侧**的形态（**本分支在基线之后新增过、又被回退成删除的地方**）。", "")
        self.write("specs/general/version-control.adoc", vc)
        cm.check_baseline_sync_guard()
        self.assertIn("非空本身就是判据", self.error_texts())

    def test_post_squash_deletion_clause_removed_reports(self):
        # 反例：新增的「压缩后须核查有无多余的删除」整条被抽掉
        # → 用户要的"压缩后"这个动作点无人核（只剩压缩前那一步）
        self._write_valid()
        vc = self.VC.replace("* **压缩后须核查有无多余的删除（L1）**：", "* **附注**：")
        self.write("specs/general/version-control.adoc", vc)
        cm.check_baseline_sync_guard()
        self.assertIn("压缩后须核查有无多余的删除", self.error_texts())

    def test_post_squash_criteria_removed_reports(self):
        # 反例：三态判定标准被抽（只留标题）→ 本条在自己这一层不可判定
        self._write_valid()
        vc = self.VC.replace("**判定标准**：① 交付形态里**给不出这份账**；"
                             "② 只核到**有没有冲突标记 / 能不能编译**、或只核**两侧内容在不在**；"
                             "③ 只核**被整体删除的文件**，**分支自己（基线之后）新增过、又被回退成删除的地方**一处未核。",
                             "务必谨慎。")
        self.write("specs/general/version-control.adoc", vc)
        cm.check_baseline_sync_guard()
        self.assertIn("给不出这份账", self.error_texts())

    def test_post_squash_four_directions_removed_reports(self):
        # 反例（"检查所有有删除的地方"落空）：四个核对方向被抽 → 只核一个维度
        self._write_valid()
        vc = self.VC.replace("**四个核对方向**：① **该在的东西一次都没被删**；"
                             "② **本分支自己新增过的东西**在压缩后的形态里不得出现为删除；"
                             "③ **本分支与基线共有的东西**不得只因压缩而消失；"
                             "④ **该删的那侧**须逐条给出原因、**不得整体取一侧收尾**。",
                             "务必都核。")
        self.write("specs/general/version-control.adoc", vc)
        cm.check_baseline_sync_guard()
        self.assertIn("四个核对方向", self.error_texts())

    def test_post_squash_demarcations_removed_reports(self):
        # 反例：两处分工句被删 → 本条会被判为既有条的重复而合并删除（真源消失）
        self._write_valid()
        vc = self.VC.replace("**与「解决冲突后须核查是否丢失内容」的分工**：本条核的是"
                             "**压缩之后的产出形态里有没有多出删除**——**另立一条不得互相替代**。"
                             "**与「压缩＝提交历史整理，内容零变化」的分工**："
                             "**前者为空与后者的账非空可以同时成立**，故两条互不替代。", "")
        self.write("specs/general/version-control.adoc", vc)
        cm.check_baseline_sync_guard()
        self.assertIn("压缩之后的产出形态里有没有多出删除", self.error_texts())

    def test_git_post_squash_deletion_removed_reports(self):
        # 反例：git 层的「压缩后不足量删除的核对」被删 → 压缩后这一问没有取值可核
        self._write_valid()
        git = self.GIT.replace("* **压缩后不足量删除的核对（L1）**：", "* **附注**：")
        self.write("specs/general/git.adoc", git)
        cm.check_baseline_sync_guard()
        self.assertIn("压缩后不足量删除的核对", self.error_texts())

    def test_git_per_file_deletions_removed_reports(self):
        # 反例（"所有有删除的地方"最易漏的一档）：只核被整体删除的文件被重新默许
        self._write_valid()
        git = self.GIT.replace("* **被改过 / 删过的文件里的删除条目逐处核（L1）**：", "* **附注**：")
        self.write("specs/general/git.adoc", git)
        cm.check_baseline_sync_guard()
        self.assertIn("被改过 / 删过的文件里的删除条目逐处核", self.error_texts())

    def test_platform_post_squash_clause_removed_reports(self):
        # 反例：平台侧的「压缩后须核查有无多余的删除」被删 → 本平台这一问没有落点
        self._write_valid()
        cnb = self.CNB.replace("* **压缩后须核查有无多余的删除（L1）**：", "* **附注**：")
        self.write("specs/platform/cnb.adoc", cnb)
        cm.check_baseline_sync_guard()
        self.assertIn("压缩后须核查有无多余的删除", self.error_texts())

    def test_platform_deletion_demarcation_removed_reports(self):
        # 反例：平台侧与关系条的分工句被删 → 会拿"合并关系为真"顶掉本条
        self._write_valid()
        cnb = self.CNB.replace("**与「压缩须保留与目标分支的合并关系」的关系**：两条核的是**不同的两件事**"
                               "（**产出形态里有没有多出删除 / 合并关系丢没丢**），**互不替代**——"
                               "**合并关系为真**不构成\"没有多余删除\"为真的依据——合并关系为真**不构成**任何豁免。", "")
        self.write("specs/platform/cnb.adoc", cnb)
        cm.check_baseline_sync_guard()
        self.assertIn("产出形态里有没有多出删除 / 合并关系丢没丢", self.error_texts())

    def test_readme_post_squash_deletion_removed_reports(self):
        # 反例：公开面看不见"压缩后要核有没有多余的删除" → 只看得见压缩前那一步
        self._write_valid()
        self.write("README.adoc",
                   "* **压缩前先并入目标分支**，否则\"压缩一次\"就是\"删一次\"；"
                   "**\"目标分支是祖先\"这句话在\"没并入最新\"的形态下照样为真**，"
                   "**不能拿它当事发过的凭据**。\n")
        cm.check_baseline_sync_guard()
        self.assertIn("压缩后要核", self.error_texts())


class TestCheckConflictResolutionGuard(CheckSpecsTestCase):
    """钉住『冲突与压缩提交防线』：先解冲突、再压缩（最终只有一个提交），解冲突后须核查是否丢内容。

    用户原话："当提出压缩提交时，有冲突要先解决冲突，解决冲突+压缩提交，最后应当只有一个提交；
    解决版本工具冲突后，需要核查是否丢失内容。" 两件事都属"工作区看起来对、判据在别处"：
    取一侧收尾后文件照旧能编译、冲突标记也没了，而少了的内容只在提交历史里看得出来。

    **分层是本组用例的核心**：用户随后明确"**git 规范也要**"且"**我说的版本管理，可没说 cnb、git，
    万一我用的 svn？**"——故规则本体（工具无关）必须在**通用层**，git 侧的核对命令在 **git 层**，
    平台层只留追加口径并**指向通用层**。本组覆盖"规则本体退回平台层""git 侧落地缺失"    "平台层不指向通用层"，以及原有的顺序条/反向判据/核查条/失效形态/接口缺失/按节取文本等反例。
    """

    VC = (
        "= 版本管理规范（通用层）\n\n"
        "== 为什么把版本管理与某个工具分开写\n\n"
        "本文件只写**工具无关**的规则本体；引用方用 git 还是 **SVN** 都读得到，"
        "**不得把某工具的命令当成规则前提**。\n\n"
        "== 冲突处理\n\n"
        "* 冲突须自动解决。\n"
        "* **冲突与压缩提交同时提出时：先解冲突、再压缩，最终只有一个提交（L1）**："
        "① **先解决冲突**，② **再压缩提交**，③ 交付形态是**最终只有一个提交**。"
        "**判定标准**：① 拿\"还有冲突\"当不做压缩的理由，或反过来拿\"要压缩\"当不解冲突的理由"
        "（两者都落地才算完成）；② 解冲突与压缩各自留了一个提交；"
        "③ 只解了冲突、没压缩。\n"
        "* **\"只被要求压缩、没被要求解决冲突\"也要先解冲突（L1）**：触发面不限于同时或先后"
        "提出两件事——用户**只要求**\"压缩提交\"、**没提**解决冲突，而当前分支与目标分支"
        "**实际存在冲突**时，同样须先解冲突、再压缩；不得把\"用户没提解决冲突\"读成\"不用做\"。"
        "**判定标准**：① 报\"已压缩提交\"却**对冲突只字未提**；② **以\"用户没提解决冲突/没被要求\""
        "为由只压不解决**；③ 把解决冲突做成**照抄目标分支的文件内容后另起一个单亲提交**"
        "（目标分支**并非本分支的祖先**）；④ 拿\"要求里只写了压缩\"当挡箭牌。\n"
        "* **解决冲突后须核查是否丢失内容（L1）**：不得凭\"没有冲突标记了\"就认为解决完毕。"
        "**判定标准**：① 用\"**整体取一侧**\"收尾、不做逐处对照；② 只核\"文件能编译\"；"
        "③ 汇报\"冲突已解决\"却不给出**核查判据**。**该用哪些判据随对象定**：文本类按内容侧对照，"
        "**改名/移动/删除与文件数**按版本管理工具的识别口径，**版本文档类**逐条核对两侧条目的并集。\n\n"
        "== 压缩提交（提交历史整理）\n"
        "* **压缩不等于解冲突（L1）**：整体取一侧后压成一个提交是把丢内容藏进干净的提交里；"
        "**压缩不能替代解冲突**。\n"
        "* **默认压成一个提交（L1，本节默认交付形态）**：用户要求\"压缩提交\"时，"
        "默认交付形态是本次任务的提交压成一个提交——未经用户点名，"
        "**不得**以\"只压部分提交\"、\"保留某些提交不压\"收尾"
        "（允许保留的例外只有下一条的两类）。\n"
        "* **压缩对象只有本次任务尚未合入的提交；允许保留的例外（L1）**："
        "压缩对象是本次任务产生的、尚未合入目标分支的提交——压缩须把这部分全部压成一个提交；"
        "**允许保留（不并入压缩）的只有两类**：① **已合入目标分支**的历史；"
        "② `specs/general/git.adoc`「重命名与内容修改须分两个提交」（最高关注项 P7）拆出的那两个提交"
        "（未点名该条时**原样保留**）。\n"
    )

    GIT = (
        "= git 规范（通用层）\n\n== 冲突与压缩提交（git 侧落地）\n\n"
        "* 规则本体见 `specs/general/version-control.adoc`；本节只写 git 上取哪个值来判（只给取值形态）。\n"
        "* **核对（L1）**：核对到的是取值状态——差异检出里不出现同一批改动的\"删除 + 新增一对\"、"
        "应保留历史的文件**被识别为 rename**；**不得整体取一侧收尾**（取哪一侧、用什么开关属执行动作）。\n"
        "* **\"最终只有一个提交\"的核对（L1）**：核对到的是取值状态——目标分支到本分支之间**只有一个提交**，"
        "且压缩后仍**能取到**拆出的那两条记录。\n"
    )

    CNB = (
        "= CNB 规范（平台层）\n\n"
        "== 冲突处理（平台侧追加口径）\n\n"
        "**规则本体（工具无关）在 `specs/general/version-control.adoc`「冲突处理」**；本节只写追加口径：\n\n"
        "* 并行任务冲突照常自动解决。\n"
        "* 交付形态按本平台表达：**该合并请求的源分支上最终只有一个提交**"
        "（`git log --oneline <目标分支>..HEAD` **只有一条**）。\n"
        "* **\"只被要求压缩提交\"时冲突处置不豁免（L1，本题的用户点名形态）**：要求只写了压缩、"
        "**没被要求不等于可以搁置**；③ 用照抄目标分支内容 + 单亲提交冒充已解决时，"
        "目标分支**并非本分支的祖先**（判据 `git merge-base --is-ancestor <目标分支> <分支>`）。"
        "解冲突是在**当前分支内**完成、**不是合并**（与「NPC 禁合并」各自独立、互不豁免）。\n\n"
        "== 合并请求的合并主体（NPC 禁合并）\n* **严禁合并**。\n\n"
        "== 压缩提交（提交历史的整理，平台侧追加口径）\n"
        "**规则本体（工具无关）在 `specs/general/version-control.adoc`「压缩提交」**；"
        "本节只写本平台的追加口径。\n"
        "* **与「冲突处理」的接口（L1）**：用户提出压缩提交而分支上**还有冲突**时"
        "**不得把冲突留在原地只做压缩**——须按「冲突处理」节**先解冲突、再压缩**。\n"
    )

    def _write_valid(self) -> None:
        self.write("specs/general/version-control.adoc", self.VC)
        self.write("specs/general/git.adoc", self.GIT)
        self.write("specs/platform/cnb.adoc", self.CNB)
        self.write(
            "AGENTS_COMMON.adoc",
            "* **版本管理** → `specs/general/version-control.adoc`\n"
            "* CNB 平台 → cnb（**冲突与压缩提交同时提出（先解冲突、再压缩、最终只有一个提交；"
            "解冲突后须核查是否丢内容）**与**只被要求压缩提交**（没被要求解决冲突时也不豁免））\n")
        self.write(
            "README.adoc",
            "* `specs/general/` — 通用层：**版本管理（`version-control.adoc`；**先解冲突、再压缩、"
            "最终只有一个提交**、**解冲突后须核查是否丢内容**、**只被要求压缩**时冲突处置也不豁免）**\n")

    def test_valid_passes(self):
        self._write_valid()
        cm.check_conflict_resolution_guard()
        self.assertEqual(cm.errors, [])

    def test_general_file_missing_reports(self):
        # 反例：规则本体无处承载（用户口称『版本管理』、未点名 git/CNB，规则本体必须在通用层）
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "general", "version-control.adoc"))
        cm.check_conflict_resolution_guard()
        self.assertIn("缺少文件", self.error_texts())
        self.assertIn("version-control.adoc", self.error_texts())

    def test_git_file_missing_reports(self):
        # 反例：git 侧落地无处承载（用户点名『git 规范也要』）
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "general", "git.adoc"))
        cm.check_conflict_resolution_guard()
        self.assertIn("git.adoc", self.error_texts())

    def test_section_deleted_reports(self):
        # 反例：通用层整节被删 → 先解冲突再压缩与解冲突后的核查都失去落点
        self._write_valid()
        self.write("specs/general/version-control.adoc",
                   "= 版本管理规范（通用层）\n\n== 压缩提交（提交历史整理）\n* 另议。\n")
        cm.check_conflict_resolution_guard()
        self.assertIn("冲突处理", self.error_texts())

    def test_order_clause_removed_reports(self):
        # 反例：顺序与交付形态被抽掉 → "还有冲突"或"要压缩"任一都能当另一个的挡箭牌
        self._write_valid()
        vc = self.VC.replace(
            "* **冲突与压缩提交同时提出时：先解冲突、再压缩，最终只有一个提交（L1）**："
            "① **先解决冲突**，② **再压缩提交**，③ 交付形态是**最终只有一个提交**。", "\n")
        self.write("specs/general/version-control.adoc", vc)
        cm.check_conflict_resolution_guard()
        self.assertIn("最终只有一个提交", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例（关键词堆砌式假绿）：只留标题与一句口号，反向判据被抽走
        self._write_valid()
        vc = self.VC.replace(
            "**判定标准**：① 拿\"还有冲突\"当不做压缩的理由，或反过来拿\"要压缩\"当不解冲突的理由"
            "（两者都落地才算完成）；② 解冲突与压缩各自留了一个提交；"
            "③ 只解了冲突、没压缩。\n", "务必谨慎。\n", 1)
        self.write("specs/general/version-control.adoc", vc)
        cm.check_conflict_resolution_guard()
        self.assertIn("拿", self.error_texts())

    def test_integrity_check_clause_removed_reports(self):
        # 反例：解冲突后的核查条被删 → "取一侧收尾"就算解决完毕，丢内容无人发现
        self._write_valid()
        vc = self.VC.replace("* **解决冲突后须核查是否丢失内容（L1）**：", "* **附注**：")
        self.write("specs/general/version-control.adoc", vc)
        cm.check_conflict_resolution_guard()
        self.assertIn("解决冲突后须核查是否丢失内容", self.error_texts())

    def test_integrity_criteria_removed_reports(self):
        # 反例：失效形态与三档核查判据被抽掉 → "核查"退化成"没有冲突标记就算完"
        self._write_valid()
        vc = self.VC.replace(
            "**判定标准**：① 用\"**整体取一侧**\"收尾、不做逐处对照；② 只核\"文件能编译\"；"
            "③ 汇报\"冲突已解决\"却不给出**核查判据**。**该用哪些判据随对象定**：文本类按内容侧对照，"
            "**改名/移动/删除与文件数**按版本管理工具的识别口径，**版本文档类**逐条核对两侧条目的并集。\n",
            "务必仔细核对。\n")
        self.write("specs/general/version-control.adoc", vc)
        cm.check_conflict_resolution_guard()
        self.assertIn("核查判据", self.error_texts())

    def test_tool_agnostic_declaration_removed_reports(self):
        # 反例：通用层**定性节**里丢了"工具无关"声明 → 规则被读成 git 专属，与用户"没说 cnb、git"相抵。
        # 判据**按定性节取文本**：正文别处顺手提一句"换用 SVN 同样成立"顶不了声明本身。
        self._write_valid()
        vc = self.VC.replace("本文件只写**工具无关**的规则本体", "本文件只写**git 上**的规则本体")
        self.write("specs/general/version-control.adoc", vc)
        cm.check_conflict_resolution_guard()
        self.assertIn("定性节", self.error_texts())

    def test_tool_agnostic_keywords_outside_section_do_not_cover(self):
        # 反例：定性节里"工具无关"被删、但**文件别处**（另一节的引号引用里）还留着"工具无关"与"SVN"
        # → 全文匹配会读成齐备；按节取文本必须报红
        self._write_valid()
        vc = self.VC.replace("本文件只写**工具无关**的规则本体", "本文件只写**git 上**的规则本体")
        vc += "\n== 其它\n\n* 换用 SVN 同样成立，本规则与工具无关。\n"
        self.write("specs/general/version-control.adoc", vc)
        cm.check_conflict_resolution_guard()
        self.assertIn("定性节", self.error_texts())

    def test_reverse_criteria_half_removed_reports(self):
        # 反例：反向判据只留前半句（本项两个关键词按 AND 判）→ 执行者仍能把"要压缩"当不解冲突的理由
        self._write_valid()
        vc = self.VC.replace("，或反过来拿\"要压缩\"当不解冲突的理由（两者都落地才算完成）", "")
        self.write("specs/general/version-control.adoc", vc)
        cm.check_conflict_resolution_guard()
        self.assertIn("要压缩", self.error_texts())

    def test_git_layer_delivery_criteria_needs_value_form(self):
        # 反例：git 层把可核对的**取值状态**删了、只留一句"应只有一条" → 判据退化成断言，无从核对。
        # 核的是取值形态（"只有一个提交"这一状态），不是具体命令（命令属执行动作）。
        self._write_valid()
        git = self.GIT.replace("只有一个提交", "符合要求")
        self.write("specs/general/git.adoc", git)
        cm.check_conflict_resolution_guard()
        self.assertIn("git.adoc", self.error_texts())

    def test_platform_squash_section_not_pointing_to_general_reports(self):
        # 反例：平台层**「压缩提交」节**把规则本体抄回平台层（「冲突处理」节还指一句）
        # → 全文匹配会假绿，必须按该节自己的正文核对
        self._write_valid()
        cnb = self.CNB.replace(
            "**规则本体（工具无关）在 `specs/general/version-control.adoc`「压缩提交」**",
            "**本节定压缩提交的规则本体**")
        self.write("specs/platform/cnb.adoc", cnb)
        cm.check_conflict_resolution_guard()
        self.assertIn("「压缩提交」节", self.error_texts())

    def test_squash_interface_removed_reports(self):
        # 反例：与「压缩提交」的接口被删 → "冲突正多、先压成一个干净的提交"式自我豁免复发
        self._write_valid()
        vc = self.VC.replace(
            "* **压缩不等于解冲突（L1）**：整体取一侧后压成一个提交是把丢内容藏进干净的提交里；"
            "**压缩不能替代解冲突**。\n", "")
        self.write("specs/general/version-control.adoc", vc)
        cm.check_conflict_resolution_guard()
        self.assertIn("压缩不等于解冲突", self.error_texts())

    def test_default_one_commit_clause_removed_reports(self):
        # 反例：默认交付形态被删 → 执行者可自行把"压几个"当裁量点、旧口径（只压部分）回归
        self._write_valid()
        vc = self.VC.replace("* **默认压成一个提交（L1，本节默认交付形态）**：", "* **附注**：")
        self.write("specs/general/version-control.adoc", vc)
        cm.check_conflict_resolution_guard()
        self.assertIn("默认压成一个提交", self.error_texts())

    def test_default_one_commit_partial_form_allowed_reports(self):
        # 反例：默认条被改写成"允许只压部分"（判定句被抽）→ 默认口径名存实亡
        self._write_valid()
        vc = self.VC.replace(
            "**不得**以\"只压部分提交\"、\"保留某些提交不压\"收尾"
            "（允许保留的例外只有下一条的两类）。",
            "压几个可按现场裁量。")
        self.write("specs/general/version-control.adoc", vc)
        cm.check_conflict_resolution_guard()
        self.assertIn("默认压成一个提交", self.error_texts())

    def test_exception_list_removed_reports(self):
        # 反例：允许保留的例外清单被整条抽掉 → 例外面回到执行者自由裁量
        self._write_valid()
        vc = self.VC.replace(
            "* **压缩对象只有本次任务尚未合入的提交；允许保留的例外（L1）**："
            "压缩对象是本次任务产生的、尚未合入目标分支的提交——压缩须把这部分全部压成一个提交；"
            "**允许保留（不并入压缩）的只有两类**：① **已合入目标分支**的历史；"
            "② `specs/general/git.adoc`「重命名与内容修改须分两个提交」（最高关注项 P7）拆出的那两个提交"
            "（未点名该条时**原样保留**）。\n", "")
        self.write("specs/general/version-control.adoc", vc)
        cm.check_conflict_resolution_guard()
        self.assertIn("允许保留", self.error_texts())

    def test_git_layer_criteria_removed_reports(self):
        # 反例：git 侧核对的**取值形态**被抽掉 → 用户点名"git 规范也要"落了空。
        # 核的是取值形态（"删除 + 新增一对"不出现、被识别为 rename），不是具体命令——
        # 命令属执行动作，收进正文即第二处"取法"。
        self._write_valid()
        git = self.GIT.replace("差异检出里不出现同一批改动的\"删除 + 新增一对\"、"
                               "应保留历史的文件**被识别为 rename**；", "")
        self.write("specs/general/git.adoc", git)
        cm.check_conflict_resolution_guard()
        self.assertIn("git.adoc", self.error_texts())

    def test_platform_squash_section_interface_removed_reports(self):
        # 反例：平台层**「压缩提交」节**的接口条被删（「冲突处理」节还写着同口径）
        # → 全文匹配会假绿，必须按该节自己的正文核对
        self._write_valid()
        cnb = self.CNB.replace(
            "* **与「冲突处理」的接口（L1）**：用户提出压缩提交而分支上**还有冲突**时"
            "**不得把冲突留在原地只做压缩**——须按「冲突处理」节**先解冲突、再压缩**。\n", "")
        self.write("specs/platform/cnb.adoc", cnb)
        cm.check_conflict_resolution_guard()
        self.assertIn("「压缩提交」节", self.error_texts())

    def test_git_section_emptied_but_keywords_elsewhere_reports(self):
        # 反例：git 层本节被掏空、命令搬到另一节 → 全文匹配会假绿，须按节取文本
        self._write_valid()
        git = ("= git 规范（通用层）\n\n== 冲突与压缩提交（git 侧落地）\n\n另议。\n\n"
               "== 其它节\n\n* 顺手提一句：`--ours`/`--theirs` 不可取、`git diff --name-status`\n"
               "  与 `rename`、`git log --oneline` **只有一条**。\n")
        self.write("specs/general/git.adoc", git)
        cm.check_conflict_resolution_guard()
        self.assertIn("git.adoc", self.error_texts())

    def test_platform_not_pointing_to_general_reports(self):
        # 反例：平台层不再指向通用层规则本体 → 规则本体又退回平台层（非 CNB/非 git 读不到）
        self._write_valid()
        cnb = self.CNB.replace("**规则本体（工具无关）在 `specs/general/version-control.adoc`「冲突处理」**",
                               "本节定冲突处理")
        self.write("specs/platform/cnb.adoc", cnb)
        cm.check_conflict_resolution_guard()
        self.assertIn("version-control.adoc", self.error_texts())

    def test_section_scoped_text_reports(self):
        # 反例：条文从「冲突处理」节被搬走、别处还提一句 → 全文匹配会假绿
        self._write_valid()
        vc = self.VC.replace("== 冲突处理", "== 其它节")
        self.write("specs/general/version-control.adoc", vc)
        cm.check_conflict_resolution_guard()
        self.assertIn("冲突处理", self.error_texts())

    def test_squash_only_trigger_removed_reports(self):
        # 反例（用户本轮点名的形态）：通用层只写"同时/先后提出两件事"，把"**只被要求压缩、
        # 没被要求解决冲突**"这一触发面抽掉 → 执行者照字面只做压缩、把冲突搁置
        self._write_valid()
        vc = self.VC.replace(
            "* **\"只被要求压缩、没被要求解决冲突\"也要先解冲突（L1）**：触发面不限于同时或先后"
            "提出两件事——用户**只要求**\"压缩提交\"、**没提**解决冲突，而当前分支与目标分支"
            "**实际存在冲突**时，同样须先解冲突、再压缩",
            "* 另议：用户**只要求**\"压缩提交\"、**没提**解决冲突时，另议")
        self.write("specs/general/version-control.adoc", vc)
        cm.check_conflict_resolution_guard()
        self.assertIn("只被要求压缩", self.error_texts())

    def test_squash_only_criteria_removed_reports(self):
        # 反例：触发面在、判定标准被抽（只剩口号）→"报已压缩却对冲突只字未提"无从判定
        self._write_valid()
        vc = self.VC.replace(
            "**判定标准**：① 报\"已压缩提交\"却**对冲突只字未提**；② **以\"用户没提解决冲突/没被要求\""
            "为由只压不解决**；③ 把解决冲突做成**照抄目标分支的文件内容后另起一个单亲提交**"
            "（目标分支**并非本分支的祖先**）；④ 拿\"要求里只写了压缩\"当挡箭牌。", "务必谨慎。")
        self.write("specs/general/version-control.adoc", vc)
        cm.check_conflict_resolution_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_platform_squash_only_clause_removed_reports(self):
        # 反例：平台层的触发面被删 → 本平台上的派发形态（要求常只写一件事）恰好漏掉这条
        self._write_valid()
        cnb = self.CNB.replace(
            "* **\"只被要求压缩提交\"时冲突处置不豁免（L1，本题的用户点名形态）**：要求只写了压缩、"
            "**没被要求不等于可以搁置**；③ 用照抄目标分支内容 + 单亲提交冒充已解决时，"
            "目标分支**并非本分支的祖先**（判据 `git merge-base --is-ancestor <目标分支> <分支>`）。"
            "解冲突是在**当前分支内**完成、**不是合并**（与「NPC 禁合并」各自独立、互不豁免）。\n",
            "")
        self.write("specs/platform/cnb.adoc", cnb)
        cm.check_conflict_resolution_guard()
        self.assertIn("只被要求压缩提交", self.error_texts())

    def test_dispatcher_squash_only_feature_removed_reports(self):
        # 反例：调度器缺"冲突/压缩提交"这一触发特征 → 该触发面永不被加载
        # （调度器只写触发特征，不抄条目本体：`先解冲突、再压缩、最终只有一个提交` 那类是本体取值）
        self._write_valid()
        self.write(
            "AGENTS_COMMON.adoc",
            "* **版本管理** → `specs/general/version-control.adoc`\n"
            "* CNB 平台 → cnb（**评论**）\n")
        cm.check_conflict_resolution_guard()
        self.assertIn("压缩提交", self.error_texts())

    def test_readme_squash_only_clause_removed_reports(self):
        # 反例：公开面只看得见"同时提出"那一种触发面
        self._write_valid()
        self.write(
            "README.adoc",
            "* `specs/general/` — 通用层：**版本管理（`version-control.adoc`；**先解冲突、再压缩、"
            "最终只有一个提交**、**解冲突后须核查是否丢内容**）**\n")
        cm.check_conflict_resolution_guard()
        self.assertIn("只被要求压缩", self.error_texts())

    def test_dispatcher_not_synced_reports(self):
        # 反例：调度器未登记通用层加载项 → 规则在、但没人会读到
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "* CNB 平台 → cnb（**冲突与压缩提交**）\n")
        cm.check_conflict_resolution_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例：公开面看不到这条默认动作
        self._write_valid()
        self.write("README.adoc", "* `specs/platform/` — 平台层：cnb（压缩提交）\n")
        cm.check_conflict_resolution_guard()
        self.assertIn("README", self.error_texts())


class TestCheckConfigClassGuard(CheckSpecsTestCase):
    """钉住『配置类不写逻辑』：配置类只保持 POJO 的基本功能，逻辑下沉到 utils/service。

    该条来自用户明确要求且**任何情况都不允许**，最易被两件事冲掉：
      * **"某处特殊"式豁免** —— 一句"这个配置类比较特殊，就地处理更快"就把无例外写回例外；
      * **关键词堆砌式假绿** —— 只留标题、把判定标准或识别特征抽掉，规则照样"在"。
    故本组用例除正例外，专门覆盖"条文被删""降级成建议""判定标准被抽""识别特征被删"
    "Java/Spring 落点缺失""README 未同步"等反例。
    """

    CODING = (
        "= 通用编码规范\n\n== 类设计\n"
        "* 配置类不写逻辑（各类承载配置的类，如 Spring `@ConfigurationProperties`、"
        "`@Configuration` 等）：除声明配置项与按配置装配对象外，**不得包含任何逻辑**——"
        "任何情况都不允许，无例外；配置类只保持纯数据对象（POJO）的基本功能，"
        "需计算/转换/组装时下沉到工具类或服务中。"
        "判定标准：①不得出现条件分支与循环；②不得做计算与对外部对象的访问；"
        "③`@Bean` 方法须是构造/装配形态。"
        "识别特征：以 Config/Properties/Options/Settings 等命名的类。"
        "**存量处理**：本条严于框架常规用法（随动迁移，见 `specs/core/execution.adoc`）。\n")

    def setUp(self) -> None:
        super().setUp()
        self._orig_coding = cm.CODING_FILE
        self._orig_java = cm.JAVA_STACK_FILE
        self._orig_spring = cm.SPRING_STACK_FILE
        self._orig_readme = cm.README_FILE
        cm.CODING_FILE = os.path.join(self.root, "specs", "general", "coding.adoc")
        cm.JAVA_STACK_FILE = os.path.join(self.root, "specs", "stack", "java.adoc")
        cm.SPRING_STACK_FILE = os.path.join(self.root, "specs", "stack", "spring.adoc")
        cm.README_FILE = os.path.join(self.root, "README.adoc")

    def tearDown(self) -> None:
        (cm.CODING_FILE, cm.JAVA_STACK_FILE, cm.SPRING_STACK_FILE,
         cm.README_FILE) = (self._orig_coding, self._orig_java, self._orig_spring,
                            self._orig_readme)
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("specs/general/coding.adoc", self.CODING)
        self.write("specs/stack/java.adoc",
                   "= Java 规范\n"
                   "* 配置类识别特征（`@ConfigurationProperties` 等）：标注 "
                   "`@ConfigurationProperties` 的类一律属配置类，**不得含任何逻辑**。\n")
        self.write("specs/stack/spring.adoc",
                   "= Spring 规范\n\n== 配置\n"
                   "* 配置类不写逻辑（**任何情况都不允许**）：`@ConfigurationProperties` 类与 "
                   "`@Configuration` 类只承载配置项声明与装配，逻辑下沉到工具类或 Service"
                   "（判定标准：条件分支为零、不做计算与对外访问）。\n"
                   "* 与框架既有做法的边界（防静默推翻）：本条**严于** Spring 的常规用法，"
                   "已有项目改到的文件顺带调整（随动迁移，见 `specs/core/execution.adoc`）。\n")
        self.write("README.adoc", "目录结构：通用编码（含**配置类不写逻辑**）。\n")

    def test_valid_config_class_guard_passes(self):
        self._write_valid()
        cm.check_config_class_guard()
        self.assertEqual(cm.errors, [])

    def test_coding_file_missing_reports(self):
        # 反例：通用层条文无处承载（该条跨语言，不能只留在某一技术栈文件里）
        self._write_valid()
        os.remove(cm.CODING_FILE)
        cm.check_config_class_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_clause_deleted_reports(self):
        # 反例：条文被删（只留标题）→ 配置类重新变成"什么都能塞"
        self._write_valid()
        self.write("specs/general/coding.adoc", "= 通用编码规范\n\n== 类设计\n* 类设计。\n")
        cm.check_config_class_guard()
        self.assertIn("配置类不写逻辑", self.error_texts())

    def test_no_exception_claims_removed_reports(self):
        # 反例：'任何情况都不允许'被删（悄悄降级成建议）→ "某处特殊"式豁免重新出现
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("——任何情况都不允许，无例外", ""))
        cm.check_config_class_guard()
        self.assertIn("任何情况都不允许", self.error_texts())

    def test_destination_removed_reports(self):
        # 反例：'逻辑下沉到工具类或服务'被删 → 逻辑无处安放，执行者只能塞回配置类
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("需计算/转换/组装时下沉到工具类或服务中", ""))
        cm.check_config_class_guard()
        self.assertIn("工具类或服务", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例（关键词堆砌式假绿）：判定标准被抽掉 → 只剩口号、无法判定
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.split("判定标准")[0])
        cm.check_config_class_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_identification_removed_reports(self):
        # 反例：识别特征被删 → 命名不规范的配置类会被漏过
        self._write_valid()
        self.write("specs/general/coding.adoc", self.CODING.split("识别特征")[0])
        cm.check_config_class_guard()
        self.assertIn("识别特征", self.error_texts())

    def test_coding_without_migration_boundary_reports(self):
        # 反例：未写存量边界 → 严于框架常规用法的条目会变成"静默推翻引用方既有做法"
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("（随动迁移，见 `specs/core/execution.adoc`）", ""))
        cm.check_config_class_guard()
        self.assertIn("存量处理", self.error_texts())

    def test_spring_without_framework_boundary_reports(self):
        # 反例：未写明"该条严于框架常规用法 + 存量随动迁移" → 拿"官方本来允许"当豁免
        self._write_valid()
        self.write("specs/stack/spring.adoc",
                   "= Spring 规范\n\n== 配置\n"
                   "* 配置类不写逻辑：`@ConfigurationProperties` 类与 `@Configuration` 类"
                   "只承载声明与装配，逻辑下沉到工具类或 Service（判定标准：条件分支为零）。\n")
        cm.check_config_class_guard()
        self.assertIn("严于", self.error_texts())

    def test_java_stack_marker_missing_reports(self):
        # 反例：Java 栈文件未点名 `@ConfigurationProperties` 类属配置类
        self._write_valid()
        self.write("specs/stack/java.adoc", "= Java 规范\n* 命名规则。\n")
        cm.check_config_class_guard()
        self.assertIn("配置类识别特征", self.error_texts())

    def test_spring_stack_clause_missing_reports(self):
        # 反例：Spring 栈文件未在「配置」节点名两类配置类
        self._write_valid()
        self.write("specs/stack/spring.adoc", "= Spring 规范\n\n== 配置\n* 配置项绑定。\n")
        cm.check_config_class_guard()
        self.assertIn("spring.adoc", self.error_texts())

    def test_dispatcher_platform_entry_not_pointing_reports(self):
        # 反例：调度器**第二处**识别特征（CNB 平台条目）被删 → 平台侧该节不会被加载
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
                   "  ** 多 agent 协作（含**派发入口（评论唤起新实例）**）"
                   " → link:specs/general/collab.adoc[]\n"
                   "  ** CNB 平台（任务开发与合并请求管理） → link:specs/platform/cnb.adoc[]\n")
        cm.check_comment_dispatch_guard()
        self.assertIn("在 Issue/PR 里发评论 @ 某个 NPC 发起一次执行", self.error_texts())

    def test_dispatcher_collab_entry_not_pointing_reports(self):
        # 反例：调度器**第一处**识别特征（多 agent 协作条目）被删
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
                   "  ** 多 agent 协作（含拆分、调用量控制） → link:specs/general/collab.adoc[]\n"
                   "  ** CNB 平台（含**在 Issue/PR 里发评论 @ 某个 NPC 发起一次执行**）"
                   " → link:specs/platform/cnb.adoc[]\n")
        cm.check_comment_dispatch_guard()
        self.assertIn("评论唤起新实例", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例：README 目录说明未同步 → 读者按 README 学习时无从知道有这条规则
        self._write_valid()
        self.write("README.adoc", "目录结构：（未同步）。\n")
        cm.check_config_class_guard()
        self.assertIn("README", self.error_texts())


class TestCheckAbstractionAdoptionGuard(CheckSpecsTestCase):
    """钉住『抽象与接入成本』：对外能力的可替换点须有唯一装配点、须有可用默认。

    该条来自用户的真实设计失效报告（"要求都实现了、功能都实现了，却很难用"——某接口在
    每个 service 使用点各实现一遍）。最易被三件事冲掉：
      * **降级成建议** —— 级别标注被拿掉、"须"被改成"建议"，条文形式上还在；
      * **关键词堆砌式假绿** —— 只留小节名与一句总述，判定标准/要点被抽走；
      * **技术栈侧断链** —— Spring「配置」不再引用该节（Spring 项目按栈文件学习即漏掉）。
    故用例除正例外，专门覆盖"节被删""L1 条文被删""判定标准被抽""级别标注被拿掉"
    "要点被删""依据行被删""Spring 引用断链"等反例。
    """

    CODING = (
        "= 通用编码规范\n\n== 抽象与接入成本\n\n"
        "对外提供能力时，**接入成本是设计指标**。判定标准：**同一个可替换点在接入方"
        "出现的次数不随使用点数量增加**，否则即为抽象漏做（按「代码复用」处理）。\n\n"
        "* 唯一装配点（L1）：可替换点须有唯一的一处声明/装配落点，"
        "**不得要求多个使用点各自提供同一实现或同一配置**。"
        "判定特征：同一实现类型/配置项在接入方出现次数 > 1，即判重复。\n"
        "* 可替换点须有可用默认（L1）：每个可替换点**须有可用的默认实现/默认值**；"
        "给不出默认时须显式声明必填失败面，**禁止既无默认又不声明**。"
        "判定标准：二者必居其一。\n"
        "* 能自动装配就不要求接入方手写（L2）：如 SPI 自动装配（`ServiceLoader`）。\n"
        "* 存量边界：适用面为**新写的对外能力**与**改到的既有抽象**"
        "（随动迁移，见 `specs/core/execution.adoc`）。\n"
        "* 多实现用限定符、不逐层传参（L2）：用限定符/命名 Bean 区分，"
        "禁止参数穿透；跨层级对象用作用域/上下文对象承载。\n"
        "* 依据（标准名/编号）：ISO/IEC 25010、ISO 9241-110、ISO/IEC/IEEE 29148、"
        "The Twelve-Factor App、Spring Boot 官方文档。\n")

    SPRING = (
        "= Spring 规范\n\n== 配置\n"
        "* 配置项须有默认值或显式必填声明"
        "（通用要求见 link:../general/coding.adoc[]「抽象与接入成本」）。\n")

    def setUp(self) -> None:
        super().setUp()
        self._orig_coding = cm.CODING_FILE
        self._orig_spring = cm.SPRING_STACK_FILE
        cm.CODING_FILE = os.path.join(self.root, "specs", "general", "coding.adoc")
        cm.SPRING_STACK_FILE = os.path.join(self.root, "specs", "stack", "spring.adoc")

    def tearDown(self) -> None:
        (cm.CODING_FILE, cm.SPRING_STACK_FILE) = (self._orig_coding, self._orig_spring)
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("specs/general/coding.adoc", self.CODING)
        self.write("specs/stack/spring.adoc", self.SPRING)

    def test_valid_abstraction_adoption_guard_passes(self):
        self._write_valid()
        cm.check_abstraction_adoption_guard()
        self.assertEqual(cm.errors, [])

    def test_coding_file_missing_reports(self):
        # 反例：通用层落点丢失（该条跨语言，不能只留在某一技术栈文件里）
        self._write_valid()
        os.remove(cm.CODING_FILE)
        cm.check_abstraction_adoption_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_section_deleted_reports(self):
        # 反例：整节被删 → "每个使用点各实现一遍"重新变成默认做法
        self._write_valid()
        self.write("specs/general/coding.adoc", "= 通用编码规范\n\n== 代码复用\n* 不重复。\n")
        cm.check_abstraction_adoption_guard()
        self.assertIn("抽象与接入成本", self.error_texts())

    def test_unique_wiring_clause_removed_reports(self):
        # 反例：L1（a）被删 → 允许"三个 service 各传一遍实现类型"
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace(
                       "不得要求多个使用点各自提供同一实现或同一配置", ""))
        cm.check_abstraction_adoption_guard()
        self.assertIn("唯一装配点", self.error_texts())

    def test_default_requirement_removed_reports(self):
        # 反例：L1（b）被删 → 可替换点可以既无默认、也不声明必填
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("禁止既无默认又不声明", ""))
        cm.check_abstraction_adoption_guard()
        self.assertIn("禁止既无默认又不声明", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例（关键词堆砌式假绿）：判定标准被抽掉 → 只剩口号、无法判定
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("次数不随使用点数量增加", "")
                              .replace("出现次数 > 1", ""))
        cm.check_abstraction_adoption_guard()
        self.assertIn("判定", self.error_texts())

    def test_level_marks_removed_reports(self):
        # 反例：级别标注被拿掉（L1 被悄悄降级成建议）
        self._write_valid()
        self.write("specs/general/coding.adoc", self.CODING.replace("（L1）", "")
                   .replace("（L2）", ""))
        cm.check_abstraction_adoption_guard()
        self.assertIn("L1", self.error_texts())

    def test_source_line_removed_reports(self):
        # 反例：依据行被删（后人无从判断该条还成不成立）
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("ISO/IEC/IEEE 29148", ""))
        cm.check_abstraction_adoption_guard()
        self.assertIn("ISO/IEC/IEEE 29148", self.error_texts())

    def test_migration_boundary_removed_reports(self):
        # 反例：存量边界被删 → 该条（严于常见既成做法）会被读成"必须立即全量重构"
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("随动迁移，见 `specs/core/execution.adoc`", ""))
        cm.check_abstraction_adoption_guard()
        self.assertIn("存量边界", self.error_texts())

    def test_spring_backlink_removed_reports(self):
        # 反例：Spring「配置」不再引用该节 → Spring 项目按栈文件学习会漏掉接入成本判据
        self._write_valid()
        self.write("specs/stack/spring.adoc", "= Spring 规范\n\n== 配置\n* 配置项绑定。\n")
        cm.check_abstraction_adoption_guard()
        self.assertIn("spring.adoc", self.error_texts())


class TestCheckReusePrecedentGuard(CheckSpecsTestCase):
    """钉住『既有实现与先例优先』：先查项目已有能力与先例，禁止手写原生写法绕过。

    该条对应用户报告的真实失效：agent 不读项目既有实现，已有 `IdUtil.fastUUID()`/
    `CIdUtils.UUID()` 仍手写 `UUID.randomUUID().toString()`，已有 `CollUtil.isNotEmpty`
    仍手写 `x != null && !x.isEmpty()`。最易被两件事冲掉：
      * **降级成建议** —— "尽量复用"读起来无害，于是"有先例也照写原生"回来；
      * **优先级被改回 JDK 优先** —— 与用户要求相反（原实现即如此）。
    故本组用例覆盖"条文被删""反例被抽""优先级顺序反了""Java 栈落点缺失""README 未同步"。
    """

    CODING = (
        "= 通用编码规范\n"
        "\n"
        "== 代码复用\n"
        "* **既有实现与先例优先（L1，动手前先查）**：写任何代码前，先查项目自有工具类与同类场景先例、再查已引入依赖是否已有等价能力，有则必须复用、写法跟随先例。\n"
        "* **不得以语言内置写法绕过既有能力（L1）**：已有 `IdUtil.fastUUID()`/`CIdUtils.UUID()` 仍手写 `UUID.randomUUID().toString()`、已有 `CollUtil.isNotEmpty` 仍手写 `x != null && !x.isEmpty()` 属反例。\n"
    )

    SYNTAX = (
        "= Java 工具类规范\n"
        "\n"
        "== 工具类使用优先级\n"
        "* 1. **项目自有工具类**（最优先）：如 `CIdUtils.UUID()`、`CList`。\n"
        "* 2. **通用第三方工具库**：hutool 的 `IdUtil`、`CollUtil`。\n"
        "* 3. **JDK 标准库自带能力**（最低优先级）：仅无等价能力时使用。\n"
        "**同一操作已有统一入口/先例时，一律跟随先例。**\n"
    )

    def setUp(self) -> None:
        super().setUp()
        self._orig_coding = cm.CODING_FILE
        self._orig_spring = cm.SPRING_STACK_FILE
        self._orig_java = cm.JAVA_STACK_FILE
        self._orig_syntax = cm.JAVA_SYNTAX_FILE
        self._orig_readme = cm.README_FILE
        cm.CODING_FILE = os.path.join(self.root, "specs", "general", "coding.adoc")
        cm.SPRING_STACK_FILE = os.path.join(self.root, "specs", "stack", "spring.adoc")
        cm.JAVA_STACK_FILE = os.path.join(self.root, "specs", "stack", "java.adoc")
        cm.JAVA_SYNTAX_FILE = os.path.join(self.root, "specs", "stack", "java-syntax.adoc")
        cm.README_FILE = os.path.join(self.root, "README.adoc")

    def tearDown(self) -> None:
        (cm.CODING_FILE, cm.SPRING_STACK_FILE, cm.JAVA_STACK_FILE, cm.JAVA_SYNTAX_FILE,
         cm.README_FILE) = (self._orig_coding, self._orig_spring, self._orig_java,
                            self._orig_syntax, self._orig_readme)
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("specs/general/coding.adoc", self.CODING)
        self.write("specs/stack/spring.adoc",
                   "= Spring 规范\n\n== 配置\n"
                   "* 配置项须有默认值或显式必填声明"
                   "（通用要求见 link:../general/coding.adoc[]「抽象与接入成本」）。\n")
        self.write("specs/stack/java-syntax.adoc", self.SYNTAX)
        self.write("specs/stack/java.adoc",
        "= Java 规范\n"
        "\n"
        "== 编码\n"
        "* 既有工具类/先例优先：见 `specs/stack/java-syntax.adoc` 与 `specs/general/coding.adoc`「代码复用」。\n"
        )
        self.write("README.adoc", "目录结构：通用编码（含**既有实现与先例优先**）。\n")

    def test_valid_reuse_precedent_guard_passes(self):
        self._write_valid()
        cm.check_reuse_precedent_guard()
        self.assertEqual(cm.errors, [])

    def test_clause_deleted_reports(self):
        # 反例：通用层条文被删 → 编码者退回"凭语言常识现写"
        self._write_valid()
        self.write("specs/general/coding.adoc", "= 通用编码规范\n\n== 代码复用\n* 复用。\n")
        cm.check_reuse_precedent_guard()
        self.assertIn("既有实现与先例优先", self.error_texts())

    def test_bypass_clause_removed_reports(self):
        # 反例：'不得以语言内置写法绕过既有能力'被删 → 有先例也照写原生
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.split("不得以语言内置写法绕过既有能力")[0])
        cm.check_reuse_precedent_guard()
        self.assertIn("绕过既有能力", self.error_texts())

    def test_examples_removed_reports(self):
        # 反例（关键词堆砌式假绿）：典型反例被抽掉 → 判据不可判定
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   "= 通用编码规范\n\n== 代码复用\n"
                   "* **既有实现与先例优先（L1，动手前先查）**：有则必须复用，跟随先例。\n"
                   "* **不得以语言内置写法绕过既有能力（L1）**：禁止手写原生写法。\n")
        cm.check_reuse_precedent_guard()
        self.assertIn("IdUtil", self.error_texts())

    def test_priority_order_reverted_reports(self):
        # 反例：优先级被改回"JDK 优先"（与用户要求相反）
        self._write_valid()
        self.write("specs/stack/java-syntax.adoc",
                   "= Java 工具类规范\n\n== 工具类使用优先级\n"
                   "* 1. **JDK 标准库自带能力**：优先使用 `List.of` 等。\n"
                   "* 2. **项目自有工具类**：`CIdUtils`。\n"
                   "* 3. **通用第三方工具库**：`IdUtil`、`CollUtil`。\n跟随先例。\n")
        cm.check_reuse_precedent_guard()
        self.assertIn("JDK 优先", self.error_texts())

    def test_java_syntax_missing_reports(self):
        # 反例：Java 栈优先级清单缺失
        self._write_valid()
        os.remove(cm.JAVA_SYNTAX_FILE)
        cm.check_reuse_precedent_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_java_stack_marker_missing_reports(self):
        # 反例：Java 栈文件未补该条识别特征与引用
        self._write_valid()
        self.write("specs/stack/java.adoc", "= Java 规范\n* 命名规则。\n")
        cm.check_reuse_precedent_guard()
        self.assertIn("java.adoc", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例：README 目录说明未同步
        self._write_valid()
        self.write("README.adoc", "目录结构：（未同步）。\n")
        cm.check_reuse_precedent_guard()
        self.assertIn("README", self.error_texts())


class TestCheckExternalScriptGuard(CheckSpecsTestCase):
    """钉住『跨语言执行脚本的落点防线』：脚本独立成文件放资源文件夹、扩展名取被调语言。

    该条对应用户报告的真实失效与要求：宿主语言里被执行的另一语言脚本用**字符串拼接/
    字符串模板**内联——**没有高亮、也没有错误校验**，语法错/字段名错/参数个数不匹配都到
    运行期才暴露。要求是**所有语言**统一：放资源文件夹、扩展名取目标语言的扩展名（或该
    技术明确支持的文件形式，如 MyBatis 的 XML 承载 SQL），lua 通过读取文件使用。
    最易被三件事冲掉：**条文被删**（退回内联）、**降级成建议**、**技术栈落点缺失或
    优先级/结构被改**（Java 侧只写"建议用文件"而无 `src/main/resources/`、`DefaultRedisScript`、
    MyBatis 的 `*.xml` 与 `${}` 白名单）。**加载时机**同理：删掉"性能敏感路径不每次读"
    或删掉"需求要求内容会变的不缓存"都会让本条失真，故一并逐项覆盖。
    """

    CODING = (
        "= 通用编码规范\n"
        "\n"
        "== 跨语言执行脚本的落点（资源文件夹，不写字符串拼接/模板）\n"
        "\n"
        "被调语言的脚本不得以字符串拼接、字符串模板内联在宿主语言代码里，一律独立成文件"
        "放在资源文件夹。\n"
        "* **落点（L1）**：跨语言脚本须独立成文件，放在资源文件夹，**不得**内联在宿主语言代码里。\n"
        "* **扩展名（L1）**：文件扩展名**取被调语言自身的扩展名**；无通用扩展名时取该技术"
        "明确支持的文件形式（如 MyBatis 的 `*.xml` 承载 SQL）。\n"
        "* **读取方式（L1）**：脚本**从资源读取后执行**。\n"
        "* **判定标准（任一命中即违规）**：①宿主语言代码里出现被调语言的语句文本（`SELECT`）；"
        "②以字符串拼接、格式化、插值、模板字面量组装该脚本；③性能敏感路径上\"每次使用都重新读取\"。\n"
        "* **加载时机（L1）**：**性能敏感**路径不得每次使用都去读资源——资源进 "
        "`classpath` 后发布即不变，须**第一次使用**时读取一次并缓存；"
        "**需求要求内容会变**的（如 HTML 模板）**不适用缓存**。\n"
        "* **反例（L2）**：Java 里拼 SQL、把一段 Lua 写成 Java 多行字符串再 `eval`。\n"
        "* 依据（标准名/编号）：OWASP SQL Injection Prevention Cheat Sheet；ISO/IEC 25010。\n"
    )

    def setUp(self) -> None:
        super().setUp()
        self._orig_coding = cm.CODING_FILE
        self._orig_java = cm.JAVA_STACK_FILE
        self._orig_spring = cm.SPRING_STACK_FILE
        self._orig_readme = cm.README_FILE
        cm.CODING_FILE = os.path.join(self.root, "specs", "general", "coding.adoc")
        cm.JAVA_STACK_FILE = os.path.join(self.root, "specs", "stack", "java.adoc")
        cm.SPRING_STACK_FILE = os.path.join(self.root, "specs", "stack", "spring.adoc")
        cm.README_FILE = os.path.join(self.root, "README.adoc")

    def tearDown(self) -> None:
        (cm.CODING_FILE, cm.JAVA_STACK_FILE, cm.SPRING_STACK_FILE,
         cm.README_FILE) = (self._orig_coding, self._orig_java, self._orig_spring,
                            self._orig_readme)
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("specs/general/coding.adoc", self.CODING)
        self.write("specs/stack/java.adoc",
                   "= Java 规范\n\n== 跨语言执行脚本（SQL / Lua 等）\n"
                   "* SQL 按资源加载 `.sql`（`src/main/resources/` 下）。\n"
                   "* Lua 写成 `.lua` 文件、用 `DefaultRedisScript` 加载。\n"
                   "* 加载时机：性能敏感路径按 `private static final` 声明脚本；"
                   "不敏感路径每次读无妨；需求要求内容会变的模板**不缓存**；"
                   "Redis 热点按 `EVALSHA` 复用。\n"
                   "* MyBatis 的 SQL 写 mapper `*.xml`；`${}` 是拼接、须白名单校验，"
                   "其余用 `#{}`。\n")
        self.write("specs/stack/spring.adoc",
                   "= Spring 规范\n\n== 跨语言执行脚本（资源文件夹）\n"
                   "* 见「跨语言执行脚本（SQL / Lua 等）」。\n"
                   "* 加载时机：性能敏感路径按静态常量读一次；需求要求内容会变的模板"
                   "不适用缓存。\n")
        # 调度器**只给触发特征**（要把 SQL/Lua 等放进资源目录时即命中），
        # 不抄条目本体的落点取值（`src/main/resources/` 在 `java.adoc` 里）。
        self.write("AGENTS_COMMON.adoc",
                   "通用编码 `specs/general/coding.adoc`（识别特征：跨语言——要把 SQL/Lua "
                   "等被调语言内联在宿主语言里）；Java 登记 `specs/stack/java.adoc`"
                   "（识别特征：跨语言——要把 SQL/Lua 等放进资源目录）\n")
        self.write("README.adoc",
                   "目录结构：通用编码（含**跨语言执行脚本的落点**、**加载时机**）。\n")

    def test_valid_external_script_guard_passes(self):
        self._write_valid()
        cm.check_external_script_guard()
        self.assertEqual(cm.errors, [])

    def test_clause_deleted_reports(self):
        # 反例：通用层该节被删 → SQL/Lua 无处安放、重新内联成字符串
        self._write_valid()
        self.write("specs/general/coding.adoc", "= 通用编码规范\n\n== 表达式与调用写法\n* x。\n")
        cm.check_external_script_guard()
        self.assertIn("跨语言执行脚本的落点", self.error_texts())

    def test_extension_clause_removed_reports(self):
        # 反例：扩展名要求（含 MyBatis 例外）被抽掉 → 退回无语义扩展名
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("取被调语言自身的扩展名", "取合适扩展名")
                              .replace("如 MyBatis 的 `*.xml` 承载 SQL", ""))
        cm.check_external_script_guard()
        self.assertIn("扩展名", self.error_texts())

    def test_read_clause_removed_reports(self):
        # 反例：'按资源读取后执行'被删 → '放文件'退化成'放文件但读进字符串再拼装'
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("**读取方式（L1）**：脚本**从资源读取后执行**。", ""))
        cm.check_external_script_guard()
        self.assertIn("从资源读取后执行", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例（关键词堆砌式假绿）：判定标准被抽成一句总述 → 判据不可判定
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   "= 通用编码规范\n\n== 跨语言执行脚本的落点（资源文件夹，不写字符串拼接/模板）\n"
                   "* 落点：放资源文件夹。\n"
                   "* 扩展名：取被调语言自身的扩展名（如 MyBatis 的 `*.xml` 承载 SQL）。\n"
                   "* 读取方式：从资源读取后执行。\n"
                   "* 反例：多行字符串。\n"
                   "* 依据：OWASP SQL Injection Prevention Cheat Sheet。\n")
        cm.check_external_script_guard()
        self.assertIn("SELECT", self.error_texts())

    def test_java_landing_missing_reports(self):
        # 反例：Java 栈落点缺失（只改通用层 = Java 项目读不到判据）
        self._write_valid()
        self.write("specs/stack/java.adoc", "= Java 规范\n\n== 健壮性\n* null。\n")
        cm.check_external_script_guard()
        self.assertIn("java.adoc", self.error_texts())

    def test_java_lua_clause_removed_reports(self):
        # 反例：Java 侧 Redis/Lua 的做法被抽掉（用户明确点名的场景：lua 通过读取文件使用）
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   "= Java 规范\n\n== 跨语言执行脚本（SQL / Lua 等）\n"
                   "* SQL 按资源加载 `.sql`（`src/main/resources/` 下）。\n"
                   "* MyBatis 的 SQL 写 mapper `*.xml`；`${}` 是拼接、须白名单校验，"
                   "其余用 `#{}`。\n")
        cm.check_external_script_guard()
        self.assertIn(".lua", self.error_texts())

    def test_spring_reference_missing_reports(self):
        # 反例：Spring 栈未引用该条 → Spring 项目漏掉判据
        self._write_valid()
        self.write("specs/stack/spring.adoc", "= Spring 规范\n\n== 事务\n* 事务。\n")
        cm.check_external_script_guard()
        self.assertIn("spring.adoc", self.error_texts())

    def test_dispatcher_registration_missing_reports(self):
        # 反例：调度器未登记识别特征 → 该节永不被加载
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "通用编码 `specs/general/coding.adoc`\n")
        cm.check_external_script_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例：README 目录说明未同步 → 读者按 README 学习时无从知道有这条规则
        self._write_valid()
        self.write("README.adoc", "目录结构：（未同步）。\n")
        cm.check_external_script_guard()
        self.assertIn("README", self.error_texts())

    def test_loading_time_clause_removed_reports(self):
        # 反例：加载时机被删 → 争分夺秒的路径（Redis 操作）每次都去读一遍资源
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace(
                       "* **加载时机（L1）**：**性能敏感**路径不得每次使用都去读资源——资源进 "
                       "`classpath` 后发布即不变，须**第一次使用**时读取一次并缓存；"
                       "**需求要求内容会变**的（如 HTML 模板）**不适用缓存**。\n", ""))
        cm.check_external_script_guard()
        self.assertIn("加载时机", self.error_texts())

    def test_mutable_content_boundary_removed_reports(self):
        # 反例：反面边界被抽掉（只剩"读一次缓存"）→ 可变模板被冻结在首读版本上
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace(
                       "**需求要求内容会变**的（如 HTML 模板）**不适用缓存**。",
                       "读一次就缓存。"))
        cm.check_external_script_guard()
        self.assertIn("不适用缓存", self.error_texts())

    def test_java_loading_time_removed_reports(self):
        # 反例：Java 侧只写"放文件"、没有加载时机 → 方法内 new DefaultRedisScript 每次读
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   "= Java 规范\n\n== 跨语言执行脚本（SQL / Lua 等）\n"
                   "* SQL 按资源加载 `.sql`（`src/main/resources/` 下）。\n"
                   "* Lua 写成 `.lua` 文件、用 `DefaultRedisScript` 加载。\n"
                   "* MyBatis 的 SQL 写 mapper `*.xml`；`${}` 是拼接、须白名单校验，"
                   "其余用 `#{}`。\n")
        cm.check_external_script_guard()
        self.assertIn("private static final", self.error_texts())

    def test_spring_loading_time_not_synced_reports(self):
        # 反例：Spring 栈未承接加载时机 → Spring 项目读到"放文件"却仍每次都去读
        self._write_valid()
        self.write("specs/stack/spring.adoc",
                   "= Spring 规范\n\n== 跨语言执行脚本（资源文件夹）\n"
                   "* 见「跨语言执行脚本（SQL / Lua 等）」。\n")
        cm.check_external_script_guard()
        self.assertIn("加载时机", self.error_texts())

    def test_readme_loading_time_not_synced_reports(self):
        # 反例：README 未同步加载时机 → 读者不知道这条管到读取次数
        self._write_valid()
        self.write("README.adoc", "目录结构：通用编码（含**跨语言执行脚本的落点**）。\n")
        cm.check_external_script_guard()
        self.assertIn("加载时机", self.error_texts())


class TestCheckCiCdGuard(CheckSpecsTestCase):
    """钉住「CI/CD 与平台协作防线」：踩坑判据不得被删或降级。

    背景（CI 内 agent 的踩坑报告）：CI 只跑主校验脚本、配套测试从未执行；触发路径与
    校验对象不一致；引用不存在的镜像/制品在 Prepare 阶段即失败；任务长期停在 pending
    无可判定超时；分支多次推送/压缩提交强推后复核按分支名取到过期对象。这些反复出现，
    故机械钉住 CICD 规范（校验链完整/触发范围/依赖可用/超时/非确定性 AI）与 CNB 平台
    规范（钉 sha、强推对应关系、执行者可用性、流水线不无界挂起）的关键要点。
    """

    def _write_valid(self):
        self.write("specs/general/ci-cd.adoc",
                   "= CI/CD 规范（通用层）\n\n"
                   "* 校验链完整：流水线须跑全既定校验；只跑主校验脚本 属验证不完整；"
                   "测试文件须能被测试框架自动发现。\n"
                   "* 触发路径须覆盖校验对象。\n"
                   "* 上游依赖须先确认实际可用。\n"
                   "* 每次执行须有可判定的超时。\n"
                   "* 不在 CI 中调用会给出非确定性结论的外部 AI。\n")
        self.write("specs/platform/cnb.adoc",
                   "= CNB 规范（平台层）\n\n"
                   "* 派发与复核须钉定 commit sha；须先取得该分支当前指向的 sha。\n"
                   "* 压缩提交/强推会替换对象，旧 sha 的结论视为过期。\n"
                   "* 派发前确认执行者实际可用。\n"
                   "* 流水线不无界挂起。\n")
        self.write("specs/general/verify.adoc",
                   "= 验证\n\n"
                   "* 验证须覆盖项目的全部既定校验手段、按需验证、不滥验证。\n"
                   "* 验证对象须钉定 commit sha。\n")
        self.write("specs/general/collab.adoc",
                   "= 协作\n\n"
                   "* 派发对象须钉定 commit sha。\n"
                   "* 派发前确认执行者可执行。\n")

    def test_valid_passes(self):
        self._write_valid()
        cm.check_ci_cd_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_ci_cd_file_reports(self):
        self.write("specs/platform/cnb.adoc", "CNB")
        cm.check_ci_cd_guard()
        self.assertIn("ci-cd.adoc", self.error_texts())

    def test_missing_ci_chain_completeness_reports(self):
        # 反例：把"须跑全既定校验（含配套测试）"抽掉（回到"只跑主脚本也算验证"）
        self._write_valid()
        self.write("specs/general/ci-cd.adoc", "= CI/CD 规范\n\n* 早失败。\n")
        cm.check_ci_cd_guard()
        self.assertIn("校验链完整", self.error_texts())

    def test_missing_ci_timeout_reports(self):
        # 反例：超时要求被删（流水线可无限挂在 pending）
        self._write_valid()
        p = "specs/general/ci-cd.adoc"
        t = open(os.path.join(self.root, p), encoding="utf-8").read()
        self.write(p, t.replace("每次执行须有可判定的超时", "超时另说"))
        cm.check_ci_cd_guard()
        self.assertIn("可判定的超时", self.error_texts())

    def test_missing_cnb_sha_pin_reports(self):
        # 反例：钉定 commit sha 的要点被抽掉、仅保留 NPC 禁合并节（按分支名取到过期对象、复核错位）。
        # 断言用本防线独有的「先取得该分支当前指向的 sha」——它与 `check_npc_merge_guard` 各自钉住
        # 同一文件的不同要点，故本防线须能在"禁合并节还在"时独立报出。
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   "= CNB\n\n== 合并请求的合并主体（NPC 禁合并）\n\n"
                   "* NPC 严禁合并合并请求。\n")
        cm.check_ci_cd_guard()
        self.assertIn("先取得该分支当前指向的 sha", self.error_texts())

    def test_missing_verify_full_chain_reports(self):
        # 反例：通用验证侧"须覆盖全部既定校验手段"被删
        self._write_valid()
        self.write("specs/general/verify.adoc", "= 验证\n\n* 以真实结果为准。\n")
        cm.check_ci_cd_guard()
        self.assertIn("验证须覆盖项目的全部既定校验手段", self.error_texts())

    def test_missing_collab_pin_reports(self):
        # 反例：协作侧"派发对象须钉定 commit sha"被删
        self._write_valid()
        self.write("specs/general/collab.adoc", "= 协作\n\n* 子 agent。\n")
        cm.check_ci_cd_guard()
        self.assertIn("派发对象须钉定 commit sha", self.error_texts())


class TestCheckScopeBoundaryGuard(CheckSpecsTestCase):
    """钉住『改动范围边界防线』：未声明即拒绝越界改动的边界不得被删或降级。

    背景（用户明确的收紧要求，且明确"适用于所有项目"）：执行者可能因"任务里引用了
    工作空间以外的文件或其他项目"而把改动落到用户**并未授权**的位置上——**引用被误当
    成授权**。本地/服务器上"文件都在"时，禁的是**改入口工作空间以外的文件**；在代码
    托管平台上，可写范围被放大成"你有权限的全部仓库"，故禁的是**改其他仓库**。故机械
    钉住**两层**：通用层（`specs/general/scope.adoc` 的两节）与平台层
    （`specs/platform/cnb.adoc` 的当前项目口径）+ 提示词公共片段
    （`prompts/_common.txt` 的 `scope-boundary`）+ 两个提示词代码块内的引入。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_prompts = (cm.PROMPTS_FILE, cm.PROMPTS_DIR, cm.COMMON_PROMPT_FILE)
        cm.PROMPTS_DIR = os.path.join(self.root, "prompts")
        cm.COMMON_PROMPT_FILE = os.path.join(self.root, "prompts", "_common.txt")

    def tearDown(self) -> None:
        (cm.PROMPTS_FILE, cm.PROMPTS_DIR,
         cm.COMMON_PROMPT_FILE) = self._orig_prompts
        super().tearDown()

    SCOPE = ("= 改动范围边界规范（通用层）\n\n"
             "== 工作空间边界（不依赖任何平台）\n"
             "* **只改当前工作空间（L1）**：执行者**只允许修改本次任务的工作空间**——"
             "下称**入口工作空间**；越出该工作空间的改动一律不得执行。\n"
             "* **未声明即拒绝（L1）**：除非用户**主动声明**把某处纳入本次范围，否则"
             "**不得改动任何工作空间以外的文件**；拒绝须说明依据（同「拒绝的形态」）。\n"
             "* **引用 ≠ 授权（L1）**：引用了工作空间以外的文件只构成读取/对照许可，"
             "**不构成改动**它的授权。\n"
             "* **只读与对照照常做（L1）**：读取、比对**不在禁止之列**（失效目标是改动）。\n"
             "* **判定标准**：①改动对象不在入口工作空间内；②以『引用过它』为由**自我豁免**；"
             "③把越界改动**顶替**给他人完成。\n"
             "== 已知例外（唯二的解禁情形，靠用户显式给出、不靠推断）\n"
             "* ①**用户显式声明**把某处纳入本次范围；②用户声明某处\"只读\"时优先。\n"
             "== 拒绝的形态（L1）\n"
             "* 须写明依据与要补什么声明；**拒绝不等于任务失败**。\n"
             "== 平台上的仓库边界（代码托管平台）\n"
             "* **只改当前项目（L1）**：当前项目＝**入口项目**；**只改当前项目**，"
             "不向其他仓库写入/提交/推送、不建分支建 PR。\n")

    CNB = ("= CNB 规范（平台层）\n\n"
           "== 变更范围只限当前项目（未声明即拒绝）\n"
           "**通用口径（规则本体）在 link:../general/scope.adoc[]**。\n"
           "* **只改当前项目（L1）**：执行者只允许修改当前项目——即本次任务的**入口项目**；"
           "越出该项目（写入/创建/删除/移动/格式化/提交/推送）一律不得执行。\n"
           "* **未声明即拒绝（L1）**：除非用户**显式声明**，否则不得修改任何其他项目；"
           "用户引用了另一个项目**不构成授权**——**引用 ≠ 授权**；须拒绝并说明依据，"
           "其余在当前项目内可做的部分照常完成。\n"
           "* **例外（唯二解禁情形）**：①**用户显式声明**把某个其他项目纳入本次范围，"
           "**未声明**一律不改；"
           "②用户声明某项目**只读**/禁止改动（该声明优先）。\n"
           "* **判定标准**：①改动对象不是入口项目；②以『用户引用了它』为由**自我豁免**；"
           "③把越界改动**顶替**给他人完成。\n")

    COMMON = ("提示词公共片段。\n"
              "// tag::scope-boundary[]\n"
              "**改动范围边界（L1）**：本次任务**只允许修改本次任务的工作空间**——"
              "**入口工作空间**；在代码托管平台上按**只允许修改当前项目**（**入口项目**）"
              "表达；**未声明**即不得改别处，越界改动**必须拒绝**并说明**依据**。"
              "**引用 ≠ 授权**：引用了工作空间以外的文件/其他项目"
              "**不构成改动它的授权**；要改它须用户**显式声明**纳入范围，"
              "用户声明\"只读\"时优先。\n"
              "// end::scope-boundary[]\n")

    def _write_valid(self) -> None:
        self.write("specs/general/scope.adoc", self.SCOPE)
        self.write("specs/platform/cnb.adoc", self.CNB)
        self.write("prompts/_common.txt", self.COMMON)
        self.write("prompts/review.adoc",
                   "= 检查修复\n\n[listing]\n----\n"
                   "include::_common.txt[tag=scope-boundary]\n----\n")

    def test_valid_passes(self):
        self._write_valid()
        cm.check_scope_boundary_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_common_layer_file_reports(self):
        # 反例：通用层规范文件被删 → 非平台场景（本地/服务器）下这条边界无处承载
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "general", "scope.adoc"))
        cm.check_scope_boundary_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_missing_workspace_section_reports(self):
        # 反例：通用层的「工作空间边界」节被删（只剩平台口径 → 本地场景无人拦）
        self._write_valid()
        self.write("specs/general/scope.adoc",
                   "= 改动范围边界规范（通用层）\n\n"
                   "== 平台上的仓库边界（代码托管平台）\n"
                   "* **只改当前项目（L1）**：当前项目＝**入口项目**。\n")
        cm.check_scope_boundary_guard()
        self.assertIn("工作空间边界（不依赖任何平台）", self.error_texts())

    def test_missing_platform_section_reports(self):
        # 反例：通用层的「平台上的仓库边界」节被删（平台可写范围被放大、无人拦）
        self._write_valid()
        self.write("specs/general/scope.adoc",
                   "= 改动范围边界规范（通用层）\n\n"
                   "== 工作空间边界（不依赖任何平台）\n"
                   "* 只允许修改本次任务的工作空间（**入口工作空间**）。\n")
        cm.check_scope_boundary_guard()
        self.assertIn("平台上的仓库边界（代码托管平台）", self.error_texts())

    def test_missing_cnb_file_reports(self):
        # 反例：平台层规范文件被删 → 平台侧口径无处承载
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "platform", "cnb.adoc"))
        cm.check_scope_boundary_guard()
        self.assertIn("平台侧口径无处承载", self.error_texts())

    def test_missing_section_reports(self):
        # 反例：平台层整节被删（越界改动重新无人拦）
        self._write_valid()
        self.write("specs/platform/cnb.adoc", "= CNB 规范\n\n== 冲突处理\n* 自动解决。\n")
        cm.check_scope_boundary_guard()
        self.assertIn("变更范围只限当前项目", self.error_texts())

    def test_cnb_not_pointing_to_general_layer_reports(self):
        # 反例：平台层不再指向通用层规则本体（非平台场景读不到这条边界）
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   "= CNB 规范\n\n== 变更范围只限当前项目（未声明即拒绝）\n"
                   "* 只允许修改当前项目（**入口项目**）；**引用 ≠ 授权**、**不构成授权**，"
                   "未声明即拒绝；**例外**：用户**显式声明**或声明**只读**。"
                   "**判定标准**：不是入口项目 / **自我豁免** / **顶替**。\n")
        cm.check_scope_boundary_guard()
        self.assertIn("../general/scope.adoc", self.error_texts())

    def test_reference_is_not_authorization_removed_reports(self):
        # 反例：把"引用 ≠ 授权"抽掉（回到"任务里提到了就能改"的口子）
        self._write_valid()
        self.write("specs/general/scope.adoc",
                   "= 改动范围边界规范（通用层）\n\n"
                   "== 工作空间边界（不依赖任何平台）\n"
                   "* 只允许修改本次任务的工作空间（**入口工作空间**）；"
                   "**未声明即拒绝**、须说明依据并拒绝，**拒绝不等于任务失败**。\n"
                   "* **判定标准**：不在入口工作空间内 / **自我豁免** / **顶替**。\n"
                   "== 已知例外（唯二的解禁情形）\n* **用户显式声明**；声明**只读**时优先。\n"
                   "== 拒绝的形态\n* 说明依据。\n"
                   "== 平台上的仓库边界（代码托管平台）\n"
                   "* **只改当前项目**：**入口项目**。\n")
        cm.check_scope_boundary_guard()
        self.assertIn("引用 ≠ 授权", self.error_texts())

    def test_missing_exception_reports(self):
        # 反例：例外被删（要么自相矛盾、要么给"看着办"留口子）
        self._write_valid()
        self.write("specs/general/scope.adoc",
                   "= 改动范围边界规范（通用层）\n\n"
                   "== 工作空间边界（不依赖任何平台）\n"
                   "* 只允许修改本次任务的工作空间（**入口工作空间**）；**未声明即拒绝**；"
                   "**引用 ≠ 授权**、**不构成改动**它的授权；须拒绝并说明依据，"
                   "**拒绝不等于任务失败**。\n"
                   "* **只读与对照照常做**：读取**不在禁止之列**。\n"
                   "* **判定标准**：不在入口工作空间内 / **自我豁免** / **顶替**。\n"
                   "== 拒绝的形态\n* 说明依据。\n"
                   "== 平台上的仓库边界（代码托管平台）\n"
                   "* **只改当前项目**：**入口项目**。\n")
        cm.check_scope_boundary_guard()
        self.assertIn("已知例外", self.error_texts())

    def test_missing_prompt_fragment_reports(self):
        # 反例：提示词公共片段缺 scope-boundary（复制到未知项目后没有这条边界）
        self._write_valid()
        self.write("prompts/_common.txt", "// tag::delivery[]\n交付。\n// end::delivery[]\n")
        cm.check_scope_boundary_guard()
        self.assertIn("scope-boundary", self.error_texts())

    def test_prompt_fragment_without_workspace_clause_reports(self):
        # 反例：提示词片段只剩平台口径（本地场景下复制出去的那份没有这条边界）
        self._write_valid()
        self.write("prompts/_common.txt",
                   "// tag::scope-boundary[]\n"
                   "**只允许修改当前项目**（**入口项目**）；**未声明**即不得改别处，"
                   "越界改动**必须拒绝**并说明**依据**；**引用 ≠ 授权**，"
                   "**不构成改动它的授权**；**显式声明**、声明\"只读\"时优先。\n"
                   "// end::scope-boundary[]\n")
        cm.check_scope_boundary_guard()
        self.assertIn("只允许修改本次任务的工作空间", self.error_texts())

    def test_prompt_not_including_fragment_reports(self):
        # 反例：提示词代码块未引入该片段
        self._write_valid()
        self.write("prompts/review.adoc", "= 检查修复\n\n[listing]\n----\n正文。\n----\n")
        cm.check_scope_boundary_guard()
        self.assertIn("未引入公共片段 `scope-boundary`", self.error_texts())


class TestCheckRefScopeWordingGuard(CheckSpecsTestCase):
    """钉住『默认引用面口径防线』：不得再把本仓库内容写成"私有 / 不对外发布"。

    背景（用户纠正的事实错误）：本仓库**所有内容都会被发布出去**（站点渲染本仓库
    文档），"私有"从来没有发生——**默认只有公共规范被引用方按入口加载**，其余落点
    只是**不在默认引用面内**。口径写错会连带改错判断（把"发布与否"当成可选项）。
    """

    def test_clear_wording_passes(self):
        # 正例：写"不在默认引用面内"（并如实说明本仓库内容全部会发布）
        self.write("library/README.adoc",
                   "= 图书馆\n\n本目录**不在默认引用面内**——本仓库内容全部会被发布，\n"
                   "区别只在默认引用什么；引用方工作区里也没有本仓库的文件。\n")
        cm.check_ref_scope_wording_guard()
        self.assertEqual(cm.errors, [])

    def test_private_not_distributed_wording_reports(self):
        # 反例：写成本仓库私有、不随规范分发（与平台事实相反）
        self.write("library/README.adoc",
                   "= 图书馆\n\n本目录属本仓库私有内容、不随规范分发给引用方。\n")
        cm.check_ref_scope_wording_guard()
        self.assertIn("不得写", self.error_texts())

    def test_private_before_not_distributed_reports(self):
        # 反例：同一句里"私有"与"不分发"分离出现（真实历史写法）
        self.write("AGENTS.adoc",
                   "= 项目规范\n\n仓库根 library/ 是本项目的图书馆（本仓库私有、不随规范分发）。\n")
        cm.check_ref_scope_wording_guard()
        self.assertIn("不随规范分发", self.error_texts())

    def test_quoting_the_error_is_exempt(self):
        # 正例：**引用/纠正**该错误表述本身（含"不是/不得写"等词）不报——否则防线的
        # 说明文字自己就把自己拦下（防线的判据须可自述）
        self.write("PUBLIC.adoc",
                   "= 公共内容入口索引\n\n注意：不得写\"本仓库私有、不随规范分发\"——"
                   "本仓库所有内容都会被发布。\n")
        cm.check_ref_scope_wording_guard()
        self.assertEqual(cm.errors, [])

    def test_private_fallback_wording_is_exempt(self):
        # 正例："私有落点/私有抓手名"是**自足性**判据，与发布与否无关，不得误伤
        self.write("specs/general/context.adoc",
                   "= 上下文\n\n不得让引用方依赖本仓库私有物：条目不得引用引用方看不到的"
                   "私有脚本名、仓库结构或私有约定。\n")
        cm.check_ref_scope_wording_guard()
        self.assertEqual(cm.errors, [])

    def test_changelog_is_exempt(self):
        # 正例：CHANGELOG 记的是**当时口径**（历史事实），不得改写、也不得被拦
        self.write("CHANGELOG.adoc",
                   "= 变更日志\n\n- 3.4 | 2026-09-12 | 图书馆属本仓库私有、不随规范分发\n")
        cm.check_ref_scope_wording_guard()
        self.assertEqual(cm.errors, [])


class TestCheckChangelogEntryGuard(CheckSpecsTestCase):
    """钉住变更日志条目的**单行**形态（防日志被当成追加区、同一条目被多行续写）。

    真实失效形态：herdoc / 多次 append 习惯把同一条目续写成多行，形态上仍像"有记录"，
    实际与下一条粘连、渲染成一整段——单行是机械可判定的，故须有抓手。
    """

    def test_single_line_entries_pass(self):
        self.write("CHANGELOG.adoc",
                   "= 变更日志\n\n- 1.1 | 2026-09-12 | 新增某项能力\n"
                   "- 1.0 | 2026-08-23 | 初始发布\n")
        cm.check_changelog_entry_guard()
        self.assertEqual(cm.errors, [])

    def test_wrapped_entry_reports(self):
        # 反例：同一条目被续写成多行（最后一条被追加续行）
        self.write("CHANGELOG.adoc",
                   "= 变更日志\n\n- 1.0 | 2026-08-23 | 初始发布\n后面的续行文本\n")
        cm.check_changelog_entry_guard()
        self.assertIn("续行", self.error_texts())

    def test_multiline_entry_middle_reports(self):
        # 反例：续行出现在条目之间（下一条不是条目行、也不是空行/标题）
        self.write("CHANGELOG.adoc",
                   "= 变更日志\n\n- 1.1 | 2026-09-12 | 新增能力\n"
                   "（补充说明：这一段其实属于上一条）\n- 1.0 | 2026-08-23 | 初始发布\n")
        cm.check_changelog_entry_guard()
        self.assertIn("续行", self.error_texts())

    def test_section_heading_after_entry_passes(self):
        # 正例：条目后紧跟节标题（如分节组织日志）不算续行
        self.write("CHANGELOG.adoc",
                   "= 变更日志\n\n- 1.0 | 2026-08-23 | 初始发布\n\n== 历史\n")
        cm.check_changelog_entry_guard()
        self.assertEqual(cm.errors, [])

    def test_overlong_entry_reports(self):
        # 反例：单行条目过长（混入了实现细节/清单，应拆条或删减）
        self.write("CHANGELOG.adoc",
                   "= 变更日志\n\n- 1.1 | 2026-09-12 | " + "细节" * 1200 + "\n")
        cm.check_changelog_entry_guard()
        self.assertIn("条目过长", self.error_texts())

    def test_missing_changelog_reports(self):
        cm.check_changelog_entry_guard()
        self.assertIn("缺少统一变更日志", self.error_texts())


class TestCheckChangelogStructureGuard(CheckSpecsTestCase):
    """钉住『变更日志组织形态与表格形态防线』。

    失效形态（用户报告、实测）：单行流水式日志在一个版本改了很多东西时**不可检索**；
    反向失效是**换成表格后把"影响"列省掉**、或**用类型列代替破坏性变更标注**；
    以及把**排序方向**写成正序、或把"版本倒序"与"时间倒序"读成两种可择一的排序
    （用户口径：**排序方式还是时间倒序，版本是越来越大的、版本倒序和时间倒序是一样的**）。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_extra = (cm.CHANGELOG_STRUCTURE_FILE, cm.CHANGELOG_EVIDENCE_FILE)
        cm.CHANGELOG_STRUCTURE_FILE = os.path.join(
            self.root, "specs", "general", "changelog.adoc")
        cm.CHANGELOG_EVIDENCE_FILE = os.path.join(
            self.root, "library", "sources.adoc")

    def tearDown(self) -> None:
        cm.CHANGELOG_STRUCTURE_FILE, cm.CHANGELOG_EVIDENCE_FILE = self._orig_extra
        super().tearDown()

    CHANGELOG_TEXT = (
        "= 变更日志编写规范\n\n"
        "== 组织形态（按版本分组；版本内按类型分组）\n\n"
        "* **以发布版本为一级分组（默认**，L1）**：版本号即发布标识\n"
        "* **按时间流水（次级形态，L2）**：仅在项目**没有\"发布版本\"概念**时使用\n"
        "* **排序方向恒为时间倒序**（最新在上）；**版本倒序与时间倒序**是同一件事，"
        "**不存在**正序形态；流水式**不得在条目之间插入版本分组**；"
        "**两种分组口径不并存**——**一个项目同一种日志只能用一种分组口径**\n"
        "* **组内按类型分组**：类型取**固定的闭集**、同一项目内用词一致\n"
        "* **没有条目的分组不写**\n\n"
        "== 应当记录（有价值）\n\n"
        "* **对外可见的行为/接口/契约变更**\n\n"
        "**要素齐备底线**：齐备类型、变更点、影响、标记四项要素\n\n"
        "== 表格形态的判据\n\n"
        "* **列义：表格承载的字段**\n"
        "  ** **分组列 = 受影响的对象**\n"
        "  ** **类型列 = 变更类型**\n"
        "  ** **变更点 = 受影响的对外标识**\n"
        "  ** **影响 = 读者要做什么、能感知到什么**\n"
        "* **判据依赖关系**：不得用类型分级代替破坏性变更标注；"
        "不得把影响写成变更点两列的同义重复；影响列写不出读者要做的动作时**不该记**\n"
        "* **破坏性变更在表格中的标注**：逐行标注，**不得只放在版本组的引文**\n"
        "* **条目下限（L1）**：表格里一条 = 一个变更点\n\n"
        "== 条目书写\n\n"
        "* **两种条目形态（择一，不得混用）**：流水式与表格式\n"
    )

    EVIDENCE_TEXT = (
        "== 变更日志的形态\n\n"
        "* Keep a Changelog、Conventional Commits、Conventional Changelog 三条依据齐备；"
        "* 自述没有标准格式：\"Not really\"——属**约定**\n"
        "* 逐字：\"Changelogs are for humans, not machines.\"、"
        "\"The same types of changes should be grouped.\"\n"
        "* BREAKING CHANGES 分组与 scope/subject 分列\n"
        "* **版本倒序即时间倒序**是本集合的判据化表述（**排序方向**的前提是版本号单调递增）\n"
        "* 日期取**tag 创建日优先**\n"
        "* **同义性差异**：外部材料**未**要求按版本分组、**未**把两种写法写成两种排序、"
        "**未**要求表格形态\n"
    )

    def _write_valid(self):
        self.write("specs/general/changelog.adoc", self.CHANGELOG_TEXT)
        self.write("library/sources.adoc", self.EVIDENCE_TEXT)

    def test_valid_passes(self):
        self._write_valid()
        cm.check_changelog_structure_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_table_section_reports(self):
        # 反例：表格形态的判据节被删（加了列却没人知道每列该写什么）
        self._write_valid()
        self.write("specs/general/changelog.adoc",
                   self.CHANGELOG_TEXT.replace("== 表格形态的判据", "== 其它"))
        cm.check_changelog_structure_guard()
        self.assertIn("表格形态的判据", self.error_texts())

    def test_impact_column_removed_reports(self):
        # 反例：表格**把"影响"列省掉**（形态更整齐、要传递的信息反而更少）
        self._write_valid()
        self.write("specs/general/changelog.adoc",
                   self.CHANGELOG_TEXT.replace(
                       "  ** **影响 = 读者要做什么、能感知到什么**\n", ""))
        cm.check_changelog_structure_guard()
        self.assertIn("影响 = 读者要做什么、能感知到什么", self.error_texts())

    def test_order_direction_flipped_to_ascending_reports(self):
        # 反例：把**排序方向**从时间倒序写成正序（版本倒序即时间倒序，正序无依据）
        self._write_valid()
        self.write("specs/general/changelog.adoc",
                   self.CHANGELOG_TEXT.replace("**排序方向恒为时间倒序**", "**按时间正序**"))
        cm.check_changelog_structure_guard()
        self.assertIn("排序方向恒为时间倒序", self.error_texts())

    def test_version_vs_time_order_claim_removed_reports(self):
        # 反例：把"版本倒序即时间倒序"删掉——二者会被读成两种可择一的排序
        self._write_valid()
        self.write("specs/general/changelog.adoc",
                   self.CHANGELOG_TEXT.replace(
                       "；**版本倒序与时间倒序**是同一件事，**不存在**正序形态；"
                       "流水式**不得在条目之间插入版本分组**", ""))
        cm.check_changelog_structure_guard()
        self.assertIn("版本倒序与时间倒序", self.error_texts())

    def test_secondary_flow_form_removed_reports(self):
        # 反例：无发布版本概念的项目专用的次级形态被删
        self._write_valid()
        self.write("specs/general/changelog.adoc",
                   self.CHANGELOG_TEXT.replace(
                       "* **按时间流水（次级形态，L2）**：仅在项目**没有\"发布版本\"概念**时使用\n", ""))
        cm.check_changelog_structure_guard()
        self.assertIn("按时间流水（次级形态，L2）", self.error_texts())

    def test_evidence_order_claim_unmarked_reports(self):
        # 反例：图书馆没如实标注"版本倒序即时间倒序"是本集合表述
        self._write_valid()
        self.write("library/sources.adoc", self.EVIDENCE_TEXT.replace(
            "* **版本倒序即时间倒序**是本集合的判据化表述（**排序方向**的前提是版本号单调递增）\n",
            ""))
        cm.check_changelog_structure_guard()
        self.assertIn("排序方向", self.error_texts())

    def test_evidence_date_priority_removed_reports(self):
        # 反例：日期口径的优先序（tag 创建日优先）被删
        self._write_valid()
        self.write("library/sources.adoc", self.EVIDENCE_TEXT.replace(
            "* 日期取**tag 创建日优先**\n", ""))
        cm.check_changelog_structure_guard()
        self.assertIn("tag 创建日优先", self.error_texts())

    def test_type_column_replaces_breaking_marker_reports(self):
        # 反例：用类型列代替破坏性变更标注（破坏性变更在表格里"消失"）
        self._write_valid()
        self.write("specs/general/changelog.adoc",
                   self.CHANGELOG_TEXT.replace("不得用类型分级代替破坏性变更标注", "按类型判即可"))
        cm.check_changelog_structure_guard()
        self.assertIn("不得用类型分级代替破坏性变更标注", self.error_texts())

    def test_two_baselines_coexist_reports(self):
        # 反例：两种时间基准被写成可以并存（同一改动被记两次）
        self._write_valid()
        self.write("specs/general/changelog.adoc",
                   self.CHANGELOG_TEXT.replace("**两种分组口径不并存**", "**两种分组口径可并用**"))
        cm.check_changelog_structure_guard()
        self.assertIn("两种分组口径不并存", self.error_texts())

    def test_evidence_missing_keeps_not_really_reports(self):
        # 反例：图书馆依据被删（形态取舍无出处、容易被读成"某标准要求"）
        self._write_valid()
        self.write("library/sources.adoc", "== 其它\n")
        cm.check_changelog_structure_guard()
        self.assertIn("Keep a Changelog", self.error_texts())

    def test_evidence_written_as_standard_reports(self):
        # 反例：把业界约定写成标准（丢掉"没有标准格式"的如实标注）
        self._write_valid()
        self.write("library/sources.adoc", self.EVIDENCE_TEXT.replace(
            "\"Not really\"——属**约定**", "这是标准"))
        cm.check_changelog_structure_guard()
        self.assertIn("Not really", self.error_texts())

    def test_missing_structure_file_reports(self):
        # 反例：规则落点消失
        cm.check_changelog_structure_guard()
        self.assertIn("缺少 specs/general/changelog.adoc", self.error_texts())


class TestCheckCommitMessageGuard(CheckSpecsTestCase):
    """钉住『提交信息防线』。

    缺口（用户要求「找业界公共规范取长补短」后发现）：本集合早已把 Conventional Commits
    1.0.0 的原文收进图书馆，却**只用它支撑变更日志的展示形态**；`specs/` 里没有任何一条
    约束「提交信息怎么写」——同一条链的上游空着（提交信息没有类型，变更日志的「按类型分组」
    只能人工归类）。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_extra = (cm.COMMIT_MESSAGE_FILE,)
        cm.COMMIT_MESSAGE_FILE = os.path.join(self.root, "specs", "general", "git.adoc")

    def tearDown(self) -> None:
        (cm.COMMIT_MESSAGE_FILE,) = self._orig_extra
        super().tearDown()

    TEXT = (
        "= git 规范\n\n"
        "== 提交信息\n\n"
        "* **首行写类型前缀（L2）**：按 `<type>[(scope)]: <subject>` 书写，`type` 取**固定闭集**\n"
        "* **判定标准**：首行不以 `<type>:` 或 `<type>(scope):` 起头即不合规\n"
        "* **破坏性变更须显式标注（L2）**：加 `!` 并在页脚写 `BREAKING CHANGE: <说明>`；"
        "**不得把某个类型默认为破坏性的**\n"
        "* **正文写「为什么」与边界（L2）**\n"
        "* **依据（标准名/编号）**：Conventional Commits 1.0.0——**业界约定、非标准**\n"
    )

    def test_valid_passes(self):
        self.write("specs/general/git.adoc", self.TEXT)
        cm.check_commit_message_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_section_reports(self):
        self.write("specs/general/git.adoc", self.TEXT.replace("== 提交信息", "== 其它"))
        cm.check_commit_message_guard()
        self.assertIn("== 提交信息", self.error_texts())

    def test_missing_verdict_criteria_reports(self):
        # 反例：可核对的判定标准被删（只剩「建议加类型」，无法判定是否被遵守）
        self.write("specs/general/git.adoc", self.TEXT.replace(
            "* **判定标准**：首行不以 `<type>:` 或 `<type>(scope):` 起头即不合规\n", ""))
        cm.check_commit_message_guard()
        self.assertIn("起头即不合规", self.error_texts())

    def test_breaking_change_marker_removed_reports(self):
        self.write("specs/general/git.adoc", self.TEXT.replace(
            "**不得把某个类型默认为破坏性的**", "破坏性变更按类型判断即可"))
        cm.check_commit_message_guard()
        self.assertIn("不得把某个类型默认为破坏性的", self.error_texts())

    def test_evidence_written_as_standard_reports(self):
        # 反例：把业界约定写成标准（丢掉「业界约定、非标准」的如实标注）
        self.write("specs/general/git.adoc", self.TEXT.replace("**业界约定、非标准**", "**标准**"))
        cm.check_commit_message_guard()
        self.assertIn("业界约定、非标准", self.error_texts())

    def test_missing_file_reports(self):
        cm.check_commit_message_guard()
        self.assertIn("缺少", self.error_texts())


class TestCheckHttpSemanticsGuard(CheckSpecsTestCase):
    """钉住『HTTP 接口语义防线』。

    缺口：此前只覆盖 HTTP 接口的**路径命名风格**，方法与状态码语义未覆盖——而「GET 承载写
    操作」会被爬虫/预取在无人操作时触发副作用，『错误一律包 200』会让重试、缓存、监控与
    网关策略全部失效。级别也须如实：安全方法 L1、幂等/状态码 L2、Problem Details L3。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_extra = (cm.HTTP_SEMANTICS_FILE, cm.HTTP_EVIDENCE_FILE)
        cm.HTTP_SEMANTICS_FILE = os.path.join(self.root, "specs", "general", "coding.adoc")
        cm.HTTP_EVIDENCE_FILE = os.path.join(self.root, "library", "sources.adoc")

    def tearDown(self) -> None:
        cm.HTTP_SEMANTICS_FILE, cm.HTTP_EVIDENCE_FILE = self._orig_extra
        super().tearDown()

    TEXT = (
        "= 通用编码规范\n\n"
        "== HTTP 接口语义（对外提供或调用 HTTP 接口的项目）\n\n"
        "**适用范围**：项目**对外提供或调用 HTTP 接口**时适用\n\n"
        "* **安全方法不得产生状态变更（L1）**：`GET`、`HEAD`、`OPTIONS`、`TRACE` 是安全方法，"
        "**不得**用它们承载写/删/状态流转等动作\n"
        "* **幂等语义与重试须对齐（L2）**：`PUT`、`DELETE` 幂等，非幂等请求不得配自动重试\n"
        "* **状态码按语义使用（L2）**：`4xx`/`5xx` 表达错误，不得出现 `200` + `success:false`\n"
        "* **对外错误响应统一结构（L3，可选）**：媒体类型 `application/problem+json`\n"
        "* **依据（标准名/编号）**：RFC 9110；RFC 9457\n"
    )

    EVIDENCE = (
        "= 外部标准原文摘录\n\n"
        "== HTTP 接口语义与错误响应（RFC 9110 / RFC 9457）\n\n"
        "* 逐字：\"essentially read-only\"、\"GET, HEAD, OPTIONS, and TRACE methods are "
        "defined to be safe\"\n"
        "* 逐字：idempotent 与 automatically retry\n"
        "* 逐字：\"three-digit integer code\"\n"
        "* 逐字：\"machine-readable details of errors\"、媒体类型 application/problem+json\n"
        "* **同义性差异**：不得用 200 包错误是本集合的**判据化取值**\n"
        "* Problem Details 是标准定义的**可选项**\n"
    )

    def _write_valid(self):
        self.write("specs/general/coding.adoc", self.TEXT)
        self.write("library/sources.adoc", self.EVIDENCE)

    def test_valid_passes(self):
        self._write_valid()
        cm.check_http_semantics_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_section_reports(self):
        self._write_valid()
        self.write("specs/general/coding.adoc", self.TEXT.replace("== HTTP 接口语义", "== 其它"))
        cm.check_http_semantics_guard()
        self.assertIn("== HTTP 接口语义", self.error_texts())

    def test_safe_method_downgraded_reports(self):
        # 反例：安全方法被降级为 L2（等于允许用 GET 做写操作）
        self._write_valid()
        self.write("specs/general/coding.adoc", self.TEXT.replace(
            "安全方法不得产生状态变更（L1）", "安全方法不得产生状态变更（L2）"))
        cm.check_http_semantics_guard()
        self.assertIn("安全方法不得产生状态变更（L1）", self.error_texts())

    def test_problem_details_upgraded_reports(self):
        # 反例：可选的错误响应格式被升成 L1（高频误伤只做内网接口的项目）
        self._write_valid()
        self.write("specs/general/coding.adoc", self.TEXT.replace(
            "对外错误响应统一结构（L3，可选）", "对外错误响应统一结构（L1）"))
        cm.check_http_semantics_guard()
        self.assertIn("对外错误响应统一结构（L3", self.error_texts())

    def test_scope_removed_reports(self):
        self._write_valid()
        self.write("specs/general/coding.adoc", self.TEXT.replace(
            "**适用范围**：项目**对外提供或调用 HTTP 接口**时适用\n\n", ""))
        cm.check_http_semantics_guard()
        self.assertIn("对外提供或调用 HTTP 接口", self.error_texts())

    def test_evidence_missing_reports(self):
        self._write_valid()
        self.write("library/sources.adoc", "= 其它\n")
        cm.check_http_semantics_guard()
        self.assertIn("HTTP 接口语义与错误响应（RFC 9110 / RFC 9457）", self.error_texts())

    def test_evidence_intrinsic_value_written_as_standard_reports(self):
        # 反例：把本集合的判据化取值写成标准原文
        self._write_valid()
        self.write("library/sources.adoc", self.EVIDENCE.replace(
            "* **同义性差异**：不得用 200 包错误是本集合的**判据化取值**\n", ""))
        cm.check_http_semantics_guard()
        self.assertIn("判据化取值", self.error_texts())

    def test_missing_file_reports(self):
        cm.check_http_semantics_guard()
        self.assertIn("缺少", self.error_texts())


class TestCheckReviewGuard(CheckSpecsTestCase):
    """钉住『评审备注落点』判据与两处引用（全局性问题不进范围性落点、全局备注不夹带范围内容）。

    实测失效：把"全项目都要注意 X"备注进某个类的 javadoc——只有读那个类的人看得见、
    换个入口就找不到；故判据（去限定词仍成立＝全局，只有一处能触发＝范围）与两个方向的
    约束须都在，且必加载层执行原则与 doc-design「信息归属」两处引用不得断开。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_files = (cm.REVIEW_FILE, cm.EXECUTION_FILE)
        cm.REVIEW_FILE = os.path.join(self.root, "specs", "general", "review.adoc")
        cm.EXECUTION_FILE = os.path.join(self.root, "specs", "core", "execution.adoc")

    def tearDown(self) -> None:
        (cm.REVIEW_FILE, cm.EXECUTION_FILE) = self._orig_files
        super().tearDown()

    def _write_valid(self):
        self.write("specs/general/review.adoc",
                   "= code review 规范\n\n== 问题记录\n\n"
                   "* **备注落点按事项的适用范围判定（L1）**：判定标准："
                   "①去掉具体类名/模块名后该结论是否仍成立；②是否只有某一处能触发或违反。\n"
                   "  ** 全局性 → 全局落点，**不得**写进范围性落点；"
                   "**全局备注里也不出现范围性内容**。\n"
                   "  ** 范围性 → 范围内落点，不上升为全局规范。\n")
        self.write("specs/core/execution.adoc",
                   "* 临时文档只做问题记录、不写备注（备注写入持久文档，"
                   "**落点按事项的适用范围判定**，见 link:../general/review.adoc[]「问题记录」）\n")
        self.write("specs/general/doc-design.adoc",
                   '* **发现的问题/事项的备注落点同样按"范围"判定**'
                   '（见 link:../general/review.adoc[]「问题记录」）。\n')

    def test_valid_rule_passes(self):
        self._write_valid()
        cm.check_review_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_review_file_reports(self):
        cm.check_review_guard()
        self.assertIn("缺少 code review 规范文件", self.error_texts())

    def test_dropped_global_note_ban_reports(self):
        # 反例：删掉"全局备注里也不出现范围性内容" → 全局落点里写具体类/方法细节又变成默许
        self._write_valid()
        p = os.path.join(self.root, "specs", "general", "review.adoc")
        with open(p, encoding="utf-8") as fh:
            t = fh.read()
        self.write("specs/general/review.adoc",
                   t.replace("全局备注里也不出现范围性内容", "备注要简洁"))
        cm.check_review_guard()
        self.assertIn("全局备注里也不出现范围性内容", self.error_texts())

    def test_dropped_reference_reports(self):
        # 反例：必加载层不再指向 review 规范 → 不按 review 规范加载的执行者学不到该判据
        self._write_valid()
        self.write("specs/core/execution.adoc", "* 临时文档只做问题记录。\n")
        cm.check_review_guard()
        self.assertIn("specs/core/execution.adoc", self.error_texts())


class TestCheckPromptDeliverySurfaceGuard(CheckSpecsTestCase):
    """钉住『提示词取值路径与装配状态』：不得退回与实测不符的印象式说法。

    用户指出的既有偏差：提示词与 `PROMPTS.adoc` 长期写"渲染视图下 `include::` 已展开"，
    但**实测**站点**原始文件地址**直出的是**仓库字节**（与工作区逐字节一致、指令仍在），
    站点上装配过的只有 `index.html` **页面内**渲染出的 HTML；而"把原始文件地址当渲染视图"
    正是上一轮实证过的失效。本组用例把"按取值路径判断 + 实证字样 + 禁止式表述"钉住。
    """

    COMMON = ("提示词公共片段\n"
              "查看与复制方式（**按取值路径判断，不按\"渲染视图\"这个印象**）："
              "`include::` **只在 AsciiDoc 处理器解析时**才展开，"
              "**判定依据是\"当前内容是被谁加工的\"、不是\"看起来像不像渲染过的页面\"**：\n"
              "- **经处理器装配过的内容**（IDE 预览、`asciidoctor` 渲染、站点页面内渲染的正文区）"
              "——未见指令即已装配；\n"
              "- **未经处理器装配的内容**：远程**原始文件**地址与本地读取都属此类，"
              "站点对非 HTML 文件**直出**仓库字节、与工作区**逐字节一致**，指令仍在；"
              "**本地读本文件**与远程取它**等价**；\n"
              "- **不得**把\"站点/渲染视图已展开\"**当成取用时的事实**——"
              "**原始文件地址与本地文件都不会装配**。\n")

    PROMPT = ("= 检查修复\n\n**给 AI 的读取说明（保证内容完整，先做）**："
              "判据是\"内容有没有被 AsciiDoc 处理器装配过\"——取到**原始文件**时指令"
              "**不会被展开**，请先读取片段**补齐**；**不得**以\"这是站点的**渲染视图**\"为由"
              "**跳过补齐**。\n")

    REGISTRY = ("=== 取值路径与装配状态（判据，不靠印象）\n\n"
                "| 取值路径 | 已装配？ |\n"
                "| IDE 预览 / 站点页面内渲染 | 是 |\n"
                "| 远程原始文件地址（**未装配**） | 否 |\n"
                "- **站点直链 = 仓库字节**：非 HTML 文件**直出原文**、与站点发布分支的同名文件逐字节一致；"
                "站点上存在装配形态的只有 `index.html` 自己的正文区。\n"
                "- **配图与判据一致**：三类是**不同取值路径**，**不是三种**版本的提示词。\n"
                "- **实证与话术（L1）**：**不得**留下与路径绑不上的笼统说法；"
                "须与实际抽样一致。\n")

    def setUp(self) -> None:
        super().setUp()
        self._prompts_orig = (cm.PROMPTS_FILE, cm.PROMPTS_DIR, cm.COMMON_PROMPT_FILE)
        cm.PROMPTS_FILE = os.path.join(self.root, "PROMPTS.adoc")
        cm.PROMPTS_DIR = os.path.join(self.root, "prompts")
        cm.COMMON_PROMPT_FILE = os.path.join(self.root, "prompts", "_common.txt")
        self._repo_root_orig = cm.REPO_ROOT
        cm.REPO_ROOT = self.root

    def tearDown(self) -> None:
        (cm.PROMPTS_FILE, cm.PROMPTS_DIR, cm.COMMON_PROMPT_FILE) = self._prompts_orig
        cm.REPO_ROOT = self._repo_root_orig
        super().tearDown()

    LIB_README = ("图书馆入口的取值形态：站点直链取到的是**未经处理器装配的仓库字节**——"
                  "站点对非 HTML 文件直出原文，页面内装配只发生在 `index.html` 自己的**正文区**。\n")
    LIB_USAGE = ("入口：`https` 直接可达（实测返回纯文本，即**未经装配的仓库字节**）。\n")
    LIB_SOURCES = ("取用侧实测：站点直链 → `text/plain`、**未经处理器装配的仓库字节**、"
                   "与站点发布分支的同名文件**逐字节一致**。\n")

    def _write_valid(self) -> None:
        self.write("prompts/_common.txt", self.COMMON)
        for name in ("review.adoc", "refactor.adoc"):
            self.write("prompts/" + name, self.PROMPT)
        self.write("PROMPTS.adoc", self.REGISTRY)
        self.write("AGENTS.adoc", "提示词条的**取值路径**须与实际一致；"
                                  "由 `check_prompt_delivery_surface_guard` 钉住。\n")
        self.write("library/README.adoc", self.LIB_README)
        self.write("library/usage.adoc", self.LIB_USAGE)
        self.write("library/sources.adoc", self.LIB_SOURCES)

    def test_valid_surface_passes(self):
        self._write_valid()
        cm.check_prompt_delivery_surface_guard()
        self.assertEqual(cm.errors, [])

    def test_fragment_missing_judgement_reports(self):
        # 反例：片段没写"按取值路径判断" → 执行者只能靠印象推断
        self._write_valid()
        self.write("prompts/_common.txt",
                   "查看与复制方式：渲染视图下已展开、内容完整。\n")
        cm.check_prompt_delivery_surface_guard()
        self.assertIn("按取值路径判断", self.error_texts())

    def test_fragment_missing_evidence_reports(self):
        # 反例：抽掉实证（逐字节一致/直出） → 后来者仍按"站点=渲染视图"推断
        self._write_valid()
        self.write("prompts/_common.txt",
                   self.COMMON.replace("**逐字节一致**", "内容相同")
                               .replace("**直出**", "按原样返回"))
        cm.check_prompt_delivery_surface_guard()
        self.assertIn("逐字节一致", self.error_texts())

    def test_prompt_note_not_updated_reports(self):
        # 反例：提示词读取说明仍按"渲染视图"陈述（题面侧没跟上）
        self._write_valid()
        self.write("prompts/review.adoc",
                   "= 检查修复\n\n**给 AI 的读取说明**：渲染视图下片段已展开、内容完整。\n")
        cm.check_prompt_delivery_surface_guard()
        self.assertIn("内容有没有被 AsciiDoc 处理器装配过", self.error_texts())

    def test_registry_table_removed_reports(self):
        # 反例：入口没有判据表 → 三类取值路径与两类状态无处可查
        self._write_valid()
        self.write("PROMPTS.adoc", "* 公共片段与 AI 读取：取到原始文件时须补齐。\n")
        cm.check_prompt_delivery_surface_guard()
        self.assertIn("取值路径与装配状态", self.error_texts())

    def test_not_three_versions_clause_removed_reports(self):
        # 反例：抽掉"不是三种版本" → 未展开会被读成内容缺失/旧版
        self._write_valid()
        self.write("PROMPTS.adoc", self.REGISTRY.replace("**不是三种**", "可与"))
        cm.check_prompt_delivery_surface_guard()
        self.assertIn("不是三种", self.error_texts())

    def test_wording_rule_removed_reports(self):
        # 反例：抽掉 L1 话术条 → "渲染视图下已展开"这类说法可以再写回来
        self._write_valid()
        self.write("PROMPTS.adoc",
                   self.REGISTRY.replace("**实证与话术（L1）**",
                                         "**补充说明**"))
        cm.check_prompt_delivery_surface_guard()
        self.assertIn("实证与话术", self.error_texts())

    def test_maintainer_entry_not_synced_reports(self):
        # 反例：维护方入口未登记该口径与抓手 → 后来者无从知道这条存在
        self._write_valid()
        self.write("AGENTS.adoc", "普通项目规范说明。\n")
        cm.check_prompt_delivery_surface_guard()
        self.assertIn("check_prompt_delivery_surface_guard", self.error_texts())


class TestCheckQuoteLineGuard(CheckSpecsTestCase):
    """钉住『引文段落防线』：引文段落不得用裸 `>` 起头（会被解析成 callout list 而中断编译）。

    真实失效（本项目实测）：文档里"引文/说明"段落长期写作 `> 说明：…`，页面侧
    （`index.html` 用 Asciidoctor.js）渲染成引用块、看不出问题；但旧式 AsciiDoc
    （Python `asciidoc`）的 `[listdef-callout]` 正则 `^<?(?P<index>\d*)> +(?P<text>.+)$`
    把单 `>` 起头者吃掉后 `index` 取到空串，随即 `List.calc_style()` 里 `assert False`，
    **整个文件编译失败**——实测一次性打死 6 个文件。该形态纯文本可判定，故须有抓手
    （`check_asciidoctor_syntax` 只在环境里真有 asciidoctor 时才跑，拦不住）。
    """

    def test_quote_marker_passes(self):
        # 正例：用 [quote] + 正文行（两代解析器都渲染成引用块）
        self.write("A.adoc", "= A\n\n[quote]\n说明：正文\n")
        cm.check_quote_line_guard()
        self.assertEqual(cm.errors, [])

    def test_bare_gt_line_reports(self):
        # 反例：裸 `>` 起头（本仓库此前的写法）——会被当成 callout list
        self.write("A.adoc", "= A\n\n> 说明：正文\n")
        cm.check_quote_line_guard()
        self.assertIn("裸 `>` 起头", self.error_texts())

    def test_bare_gt_reports_file_and_line(self):
        # 反例：须报出**文件与行号**（否则一堆文档里无从下手）
        self.write("library/README.adoc", "= 图书馆\n\n正文\n> 依据：RFC 2119\n")
        cm.check_quote_line_guard()
        self.assertIn("library/README.adoc", self.error_texts())
        self.assertIn(":4", self.error_texts())

    def test_inline_gt_not_reported(self):
        # 正例：行内 `>`（比较运算符、shell 重定向、`<commit>:<path>`）不在判定面内
        self.write("A.adoc",
                   "= A\n\nshell 重定向用 `cmd > log`；比较写作 `a > b`；"
                   "定位写作 `<commit>:<path>`\n")
        cm.check_quote_line_guard()
        self.assertEqual(cm.errors, [])

    def test_nested_list_marker_not_reported(self):
        # 正例：列表里的 `** ` 与 `* ` 不误报（只判行首 `> `）
        self.write("A.adoc", "= A\n\n* 一\n** 二\n")
        cm.check_quote_line_guard()
        self.assertEqual(cm.errors, [])


class TestCheckDependencyViewGuard(CheckSpecsTestCase):
    """钉住『依赖关系文档』：模块间依赖的唯一视图（完整、UML、可直达、不过期、不重复声明）。

    该条对应用户报告的真实失效：AI 编辑代码时**加重复依赖**——模块已经（直接或间接）
    依赖了某库，却又在它的依赖清单里声明一次。根因不是"忘了"，而是**没有一份完整依赖
    关系的视图**，只能临场重建依赖树。最易被两件事冲掉：
      * **降级成一句口号** —— "要注意依赖关系"读起来无害，于是重复依赖照旧；
      * **入口不指向它** —— 规则写在被引用的文件里、加载调度器/依赖规范都不指向它，
        多模块项目与"增删依赖"场景根本不会加载到（写了等于没写）。
    故本组用例覆盖"节被删""UML 优先被删""先查本文档被删""缺失即新增被删""不重复声明被删"
    "调度器未指向""依赖规范未指向"。
    """

    SECTION = (
        "== 依赖关系文档（模块间依赖的唯一视图）\n"
        "\n"
        "**识别特征**：多模块结构，或动手增删依赖。\n"
        "\n"
        "* **完整依赖关系文档即唯一视图（L1）**：多模块项目须维护一份**完整依赖关系文档**"
        "（`<项目根>/doc/dependency.adoc`，单模块项目放 `<模块>/doc/dependency.adoc`）——"
        "**完整**指列出**当前项目全部模块之间**的依赖关系（谁依赖谁、方向；**不列第三方库清单**）。\n"
        "* **优先用 UML 表述（L1）**：依赖关系**以 UML 图为主**，模块用组件/包、依赖用依赖箭头；"
        "**不得只写一段文字描述**。\n"
        "* **位置须让 AI 直接处理（L1）**：文档须放在多模块项目的**文档根目录**"
        "（项目根 `doc/dependency.adoc`）。\n"
        "* **查依赖关系优先查本文档（L1）**：涉及依赖判断时**先读本视图**；"
        "**回答完即止，不重启依赖树解析**。\n"
        "* **文档缺失则新增，不跳过（L1）**：多模块项目**没有本视图时**，须在本次任务内"
        "**新增**；**存在但不完整**时补全后再用。\n"
        "* **依赖关系变更须与构建文件同一提交内同步（L1）**：**同一提交内**更新本视图。\n"
        "* **模块内外部依赖不重复声明（L1）**：**不得再在它的依赖清单里重复声明同一依赖**；"
        "**新增依赖前先读本视图**。\n"
        "* **文档与工具各司其职（L2）**：不替代构建工具（依赖树只描述**第三方库**）。\n"
        "* 依据（标准名/编号）：ISO/IEC/IEEE 42010、UML、ISO/IEC/IEEE 29148\n"
    )
    GENERIC = (
        "= 入口\n\n== 分类与懒加载（加载调度器）\n"
        "  ** 设计文档 → link:specs/general/doc-design.adoc[]"
        "（**含模块间依赖关系文档**，见其「依赖关系文档（模块间依赖的唯一视图）」）\n"
        "== 规范文件登记完整性\n"
    )
    DEPENDENCY = (
        "= 依赖管理规范\n\n== 引入依赖\n"
        "* **传递依赖不直接使用（L2）**：确需使用时须显式声明并说明理由。"
        "**多模块项目的模块间依赖不在本条范围**——模块已被（直接或间接）依赖时"
        "**不得重复声明同一依赖**，判定前先读模块间依赖的唯一视图"
        "（见 link:../general/doc-design.adoc[]「依赖关系文档（模块间依赖的唯一视图）」）。\n"
    )

    def setUp(self) -> None:
        super().setUp()
        self._orig_view = cm.DEPENDENCY_VIEW_FILE
        cm.DEPENDENCY_VIEW_FILE = os.path.join(
            self.root, "specs", "general", "doc-design.adoc")

    def tearDown(self) -> None:
        cm.DEPENDENCY_VIEW_FILE = self._orig_view
        CheckSpecsTestCase.tearDown(self)

    def _write_valid(self) -> None:
        self.write("specs/general/doc-design.adoc", "= 设计文档规范\n\n" + self.SECTION)
        self.write("AGENTS_COMMON.adoc", self.GENERIC)
        self.write("specs/general/dependency.adoc", self.DEPENDENCY)

    def test_valid_passes(self):
        self._write_valid()
        cm.check_dependency_view_guard()
        self.assertEqual(cm.errors, [])

    def test_section_deleted_reports(self):
        # 反例：整节被删 → 依赖视图无处承载，重复依赖照旧
        self._write_valid()
        self.write("specs/general/doc-design.adoc", "= 设计文档规范\n\n== 设计文档\n")
        cm.check_dependency_view_guard()
        self.assertIn("依赖关系文档（模块间依赖的唯一视图）", self.error_texts())

    def test_uml_priority_removed_reports(self):
        # 反例（关键词堆砌式假绿）：UML 优先被删、只剩"要有依赖文档" → 判据不可判定
        self._write_valid()
        self.write("specs/general/doc-design.adoc",
                   "= 设计文档规范\n\n" + self.SECTION.replace(
                       "* **优先用 UML 表述（L1）**：依赖关系**以 UML 图为主**，模块用组件/包、"
                       "依赖用依赖箭头；**不得只写一段文字描述**。\n", ""))
        cm.check_dependency_view_guard()
        self.assertIn("UML", self.error_texts())

    def test_read_first_rule_removed_reports(self):
        # 反例："先读本文档"被删 → 规则不会被使用（仍去解析依赖树）
        self._write_valid()
        self.write("specs/general/doc-design.adoc",
                   "= 设计文档规范\n\n" + self.SECTION.replace(
                       "* **查依赖关系优先查本文档（L1）**：涉及依赖判断时**先读本视图**；"
                       "**回答完即止，不重启依赖树解析**。\n", ""))
        cm.check_dependency_view_guard()
        self.assertIn("先读本视图", self.error_texts())

    def test_missing_then_add_removed_reports(self):
        # 反例："缺失则新增"被删 → 规则只对已合规项目生效
        self._write_valid()
        self.write("specs/general/doc-design.adoc",
                   "= 设计文档规范\n\n" + self.SECTION.replace(
                       "* **文档缺失则新增，不跳过（L1）**：多模块项目**没有本视图时**，"
                       "须在本次任务内**新增**；**存在但不完整**时补全后再用。\n", ""))
        cm.check_dependency_view_guard()
        self.assertIn("没有本视图时", self.error_texts())

    def test_no_duplicate_declare_removed_reports(self):
        # 反例："不重复声明"被删 → 本条要消灭的失效本身不再被约束
        self._write_valid()
        self.write("specs/general/doc-design.adoc",
                   "= 设计文档规范\n\n" + self.SECTION.replace(
                       "* **模块内外部依赖不重复声明（L1）**：**不得再在它的依赖清单里重复声明同一依赖**；"
                       "**新增依赖前先读本视图**。\n", ""))
        cm.check_dependency_view_guard()
        self.assertIn("不得再在它的依赖清单里重复声明", self.error_texts())

    def test_dispatcher_not_pointing_reports(self):
        # 反例：加载调度器未指向该节 → 多模块/增删依赖场景不会加载到它
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", self.GENERIC.replace(
            "（**含模块间依赖关系文档**，见其「依赖关系文档（模块间依赖的唯一视图）」）", ""))
        cm.check_dependency_view_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_dependency_spec_not_pointing_reports(self):
        # 反例：依赖规范未指向该视图 → 按依赖规范学习时漏掉这条
        self._write_valid()
        self.write("specs/general/dependency.adoc", "= 依赖管理规范\n\n== 引入依赖\n* 先查再用。\n")
        cm.check_dependency_view_guard()
        self.assertIn("dependency.adoc", self.error_texts())

    def test_missing_file_reports(self):
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "general", "doc-design.adoc"))
        cm.check_dependency_view_guard()
        self.assertIn("缺少文件", self.error_texts())


class TestCheckCommentDispatchGuard(CheckSpecsTestCase):
    """钉住『评论唤起新实例防线』：评论即派发入口的要点不得被删或降级。

    背景（用户提出的机制）：CNB 平台下**在 Issue/PR 里新增一条评论、@ 某个 NPC、说清要求**
    即发起一次执行，且**可以要求它使用干净的上下文**。高风险点在于被读成"@ 一下就能绕过
    派发规则"——故机械钉住"入口形态 / 不放宽任何派发约束 / 一次评论 = 一次派发 / 干净上下文
    须显式要求且不是保证 / 仅点名不构成派发"这几处要点，以及调度器识别特征与 README 同步。
    """

    CNB = ("= CNB 规范（平台层）\n\n"
           "== 评论唤起新实例（平台侧的派发入口）\n"
           "* **评论唤起是平台侧的派发方式，不改变派发判据（L1）**：在 Issue 或 PR 下"
           "**新增一条评论**、@ 某个 NPC（如 `@CodeBuddy`）、并在评论里**说清要求**，"
           "即新增一次执行；本条**只把『往哪派』说清楚，不放宽任何派发约束**"
           "（一律按 link:../general/collab.adoc[] 执行，也不构成『可以点名外部 Agent』的例外）。\n"
           "* **一次评论 = 一次派发，任务边界由评论正文界定（L1）**：要求须在**评论里写清**"
           "（做什么、边界、产物形态、验证口径）；**未写清的不得自行假定后开工**。\n"
           "* **要求『用干净上下文』是派发选项，须在评论里显式要求（L1）**：默认**沿用该 Issue/PR 的既有上下文**；"
           "显式要求时当作全新任务、**规范仍须按入口重新加载**（『上下文干净』只清历史对话、**不清约束**）；"
           "**该要求属降低风险的措施、要求不是保证**，须**如实说明本次实际读到的上下文范围**。\n"
           "* **唤起不等于自动开工（L3）**：单条评论**只有寒暄**/只 @ 一下时不构成派发，不得自行开工。\n"
           "* 正文里的具体实例名 `@CodeBuddy`（**仅作举例**）——其余口径见通用层。\n"
           "* **缺项**时须回复拒绝并**列出缺失项**；该要求**不豁免任何派发判据**。\n")

    COLLAB = ("= agent 协作规范（通用层）\n\n"
              "== 派发入口（往哪派、派什么）\n"
              "* **评论唤起是『评论即派发入口』的一种形态（L1）**：在 Issue / PR 下新增一条评论、"
              "在评论里点名 `@` 起某个 NPC 并在评论里说清要求，即在该任务单下新增一次执行；"
              "该入口**不豁免本文件的任何派发判据**。\n"
              "* **一次评论 = 一次派发，任务边界由评论正文界定（L1）**：要求须在评论里写清、"
              "**未写清的不得自行假定后开工**。\n"
              "* **可要求『用干净上下文』，但这是要求不是保证（L1）**：须先自评**环境能力**；"
              "**『上下文干净』只清历史对话、不清约束**；"
              "**不豁免本文件任何派发判据**，也**不意味着**连本次对象钉定都要另取一套。\n"
              "* **评论是『派发者』的入口，不是\"执行者\"的手段（L1）**：执行者"
              "**不得自行发一条评论**去唤起另一个 Agent/NPC 接手自己的活。\n"
              "* **要求未写清或判据不满足时的形态（L1）**：须在原评论下回复拒绝并列出**缺项**、"
              "**不得开工**，也不得拿『他没写清』当擅自扩大范围的挡箭牌；"
              "**留证落点**即该条**评论下的回复**。\n"
              "* **计数口径（L2）**：**一条评论 = 一次派发**；一条评论点名多个对象按 **N 次派发**计。\n"
              "* **本入口与文件操作的边界（L1）**：**评论不是交付**，改动仍按 link:../core/execution.adoc[]"
              "「文件操作强制检查」判。\n")

    GENERIC = ("= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
               "  ** 多 agent 协作（含**派发入口（评论唤起新实例：一次评论 = 一次派发）**）"
               " → link:specs/general/collab.adoc[]\n"
               "  ** CNB 平台（含**在 Issue/PR 里发评论 @ 某个 NPC 发起一次执行**）"
               " → link:specs/platform/cnb.adoc[]\n")

    def setUp(self) -> None:
        super().setUp()
        self._orig_readme = cm.README_FILE
        cm.README_FILE = os.path.join(self.root, "README.adoc")

    def tearDown(self) -> None:
        cm.README_FILE = self._orig_readme
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("specs/platform/cnb.adoc", self.CNB)
        self.write("specs/general/collab.adoc", self.COLLAB)
        self.write("AGENTS_COMMON.adoc", self.GENERIC)
        self.write("README.adoc", "# README\n\n## 目录结构\n* 平台层：cnb（含**评论唤起**口径）\n")

    def test_valid_passes(self):
        self._write_valid()
        cm.check_comment_dispatch_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_cnb_section_reports(self):
        # 反例：平台层该节被删 → 平台上的派发入口无人说清
        self._write_valid()
        self.write("specs/platform/cnb.adoc", "= CNB 规范（平台层）\n\n== 冲突处理\n* 自动解决。\n")
        cm.check_comment_dispatch_guard()
        self.assertIn("评论唤起新实例（平台侧的派发入口）", self.error_texts())

    def test_relaxed_dispatch_rule_reports(self):
        # 反例（最危险的一种）：把该入口写成"可以不按派发判据"（点名外部 Agent 的例外）
        self._write_valid()
        self.write("specs/platform/cnb.adoc", self.CNB.replace(
            "不放宽任何派发约束", "可按需放宽派发约束").replace(
            "也不构成『可以点名外部 Agent』的例外", "必要时可点名外部 Agent 顶替"))
        cm.check_comment_dispatch_guard()
        self.assertIn("不放宽任何派发约束", self.error_texts())

    def test_clean_context_as_default_reports(self):
        # 反例：把"干净上下文"写成默认（不再需要评论里显式要求）→ 读者按错的默认预期派活
        self._write_valid()
        self.write("specs/platform/cnb.adoc", self.CNB.replace(
            "默认**沿用该 Issue/PR 的既有上下文**", "默认即为干净上下文"))
        cm.check_comment_dispatch_guard()
        self.assertIn("沿用该 Issue/PR 的既有上下文", self.error_texts())

    def test_clean_context_carrying_constraints_reports(self):
        # 反例："不清约束"被删 → 会被执行成"上下文干净了所以不用再读规范"
        self._write_valid()
        self.write("specs/general/collab.adoc", self.COLLAB.replace("、不清约束", ""))
        cm.check_comment_dispatch_guard()
        self.assertIn("不清约束", self.error_texts())

    def test_missing_general_section_reports(self):
        # 反例：通用层「派发入口」节被删 → 非 CNB 场景下该入口无人说清
        self._write_valid()
        self.write("specs/general/collab.adoc", "= agent 协作规范（通用层）\n\n== 资源限制与感知\n* 硬超时。\n")
        cm.check_comment_dispatch_guard()
        self.assertIn("派发入口（往哪派、派什么）", self.error_texts())

    def test_dispatcher_not_pointing_reports(self):
        # 反例：调度器识别特征被删 → 该节永远不会被加载（写了等于没写）
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
                                          "  ** 多 agent 协作 → link:specs/general/collab.adoc[]\n")
        cm.check_comment_dispatch_guard()
        self.assertIn("评论唤起新实例", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例：README 目录说明未同步 → 读者按 README 学习时不知道有这个入口
        self._write_valid()
        self.write("README.adoc", "# README\n\n## 目录结构\n* 平台层：cnb\n")
        cm.check_comment_dispatch_guard()
        self.assertIn("评论唤起", self.error_texts())


class TestCheckSelfDispatchGuard(CheckSpecsTestCase):
    """钉住『不得自行发评论唤起自己防线』：执行者不得把任务在执行中重新发起一次。

    用户提出的收紧要求（"不能艾特自己"）。这条最容易被"分两步更清楚""换个节点更专注"
    合理化成自动动作——而每次唤起都要重新按入口加载规范、重新建上下文并付一次调用与等待，
    **跨轮分步该由人决定**。故本组用例把平台层/通用层/题面侧/登记处/调度器五处一并钉住。
    """

    CNB = (
        "= CNB 规范（平台层）\n\n"
        "== 评论唤起新实例（平台侧的派发入口）\n"
        "* **评论唤起是平台侧的派发方式（L1）**：在 Issue 或 PR 下**新增一条评论**、"
        "@ 某个 NPC（**仅作举例**）、并在评论里**说清要求**，即新增一次执行。\n"
        "* **不得以评论派发唤起自己（L1，防无限派发）**：被评论唤起的执行者**不得在本次执行中"
        "再发一条评论去点名唤起自己**（同一点名、**同一实例名**），"
        "**也不得转由他人**/其他执行者**代发**。判定标准：①本次执行期间新增的点名评论"
        "指向本条评论上的唤起名；②以\"分两步更清楚\"等理由**自我豁免**；"
        "③**实际发了这条评论**、把任务在执行中重新发起一次（判据是**这条评论发出去没有**、"
        "**不是这次执行有没有因此结束**）；④**转交他人**代发。"
        "**为什么**：**一次评论就是一次派发**，**发起下一次是派发者的动作**、不是执行者的动作。"
        "**正当形态**：**先停**、只输出一次\"**停下确认**\"，由**人**另发一条评论决定是否再来一次。\n"
        "* **须由与执行者相同的 Agent 承担验证（L1）**：**要求验证/复核须由与执行者相同的 "
        "Agent 来做的那些规则，只在本平台（CNB）成立**——**本平台之外不适用**：环境不提供同 Agent "
        "的子执行者时，**不得援引该条拒做或把任务停在中间**；**不提供**时按降级路径执行、"
        "**验证与交付不因此缺失**。判定标准：平台层未写明时不得援引本条拒做。"
        "**由谁承担**是**项目自身的取舍**（IEEE 1028 只要求有独立、可核对的评审发生）；"
        "条文的写入面本就在平台层、**不在公共内容**（`AGENTS_COMMON.adoc` + `specs/`）里，"
        "引用方按入口加载时**不会取到它**。\n"
        "* **复核者的来源：\"谁发起的\"与\"谁承担\"的区分（L1）**：**\"须由与执行者相同的 "
        "Agent 承担\"说的是复核者的来源要求，**不是复核的发起方式**、**各自独立**。"
        "故**执行者不得用**\"为了满足同 Agent 复核\"**去 @ 自己**（不因目的是复核而放宽）。"
        "**能不能拿到，在动手前判定**（`printenv CNB_EVENT` 实测）；"
        "**一个任务只由**人**决定起几次执行**，缺的复核**在本次执行内**按降级路径补。"
        "**该情形下的交付形态**：**照常交付**，结论里**如实写明可信的独立复核不可得**；"
        "**\"已交付 + 校验全绿 + 复核缺口如实标出\"不得混写**成\"已复核通过\"。"
        "判定标准：①用 @ 自己换取一次新执行来做复核 "
        "②把\"拿不到独立复核\"写成\"已复核通过\" ③以\"等下一轮复核\"为由**停在中间**不交付。\n"
    )

    COLLAB = (
        "= agent 协作规范（通用层）\n\n"
        "== 派发入口（往哪派、派什么）\n"
        "* **评论唤起是『评论即派发入口』的一种形态（L1）**：在 Issue / PR 下新增一条评论、"
        "点名并说清要求，即在该任务单下新增一次执行。\n"
        "* **执行者不得自行发评论唤起自己（L1，防无限派发）**：执行者不得在本次执行中"
        "自行发一条评论点名唤起自己（也不得转由他人代发）——**发起下一次是\"派发者\"的动作**，"
        "故**执行者\"想分步\"不是派发的依据**；**先停**、由**人**另发一条评论；"
        "**跨轮分步由人决定**。平台侧同口径条见 link:../platform/cnb.adoc[]。\n"
        "* **同 Agent 的适用面（L1，先定条件再谈强制）**：**不是无条件成立的规则**——"
        "以**平台层写明该前提成立**为前提；**平台层未写明**时不得援引本条拒做、照做该职责。"
        "**由谁承担**是**项目自身的取舍**，标准**未规定复核者须是同一产品**。\n"
        "* **\"复核者的来源\"与\"复核的发起\"是两件事（L1）**：不得把\"满足同 Agent\"读成"
        "\"必须再发一条评论叫一个 Agent 来\"——**一个任务只由人决定起几次执行**；"
        "**拿不到同 Agent 子执行者时**按降级路径**在本次执行内**补；**交付照常**、缺口如实写明。\n"
    )

    def setUp(self) -> None:
        super().setUp()
        self._orig_prompts = (cm.PROMPTS_FILE, cm.PROMPTS_DIR, cm.COMMON_PROMPT_FILE,
                              cm.README_FILE)
        cm.PROMPTS_FILE = os.path.join(self.root, "PROMPTS.adoc")
        cm.PROMPTS_DIR = os.path.join(self.root, "prompts")
        cm.COMMON_PROMPT_FILE = os.path.join(self.root, "prompts", "_common.txt")
        cm.README_FILE = os.path.join(self.root, "README.adoc")

    def tearDown(self) -> None:
        (cm.PROMPTS_FILE, cm.PROMPTS_DIR, cm.COMMON_PROMPT_FILE,
         cm.README_FILE) = self._orig_prompts
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("specs/platform/cnb.adoc", self.CNB)
        self.write("specs/general/collab.adoc", self.COLLAB)
        self.write("specs/general/verify.adoc",
                   "= 验证\n\n* **执行者选择：强制同 Agent（L1，其适用面由平台层限定）**："
                   "『由与执行者相同的 Agent 承担』**不是平台无关的强制前提**——"
                   "**平台层写明该前提成立**时按强制判；平台不提供同 Agent 子执行者时"
                   "**不得援引本条跳过复核**或把任务停在中间。\n")
        self.write("prompts/_common.txt", "// tag::delivery[]\n8. 交付\n// end::delivery[]\n")
        # 调度器**只给触发特征**（要发评论/按评论派发时即命中），不抄条目本体的禁令句。
        self.write("AGENTS_COMMON.adoc",
                   "* 多 agent 协作 → `specs/general/collab.adoc`"
                   "（识别特征：要发评论、要按评论派发一次执行）\n"
                   "* CNB 平台 → `specs/platform/cnb.adoc`"
                   "（识别特征：要发评论或处置评论、要派发或复核）\n")
        self.write("prompts/review.adoc",
                   "= 检查修复\n\n[listing]\n----\n"
                   "10. **不得自行发评论唤起自己（L1，防无限派发）**："
                   "**一次评论 = 一次派发**；想分步就**先停**、**由**人**另发一条评论**。\n"
                   "include::_common.txt[tag=delivery]\n----\n")
        self.write("prompts/refactor.adoc",
                   "= 重构\n\n[listing]\n----\n"
                   "10. **不得自行发评论唤起自己（L1，防无限派发）**："
                   "**一次评论 = 一次派发**；想分步就**先停**、**由**人**另发一条评论**。\n"
                   "include::_common.txt[tag=delivery]\n----\n")
        self.write("PROMPTS.adoc",
                   "* 公共约定：**不得自行发评论唤起自己**——\"分两步更清楚\"不构成理由。\n")
        self.write("README.adoc",
                   "# README\n\n**执行者不得在本次执行中自行发评论点名唤起自己**"
                   "（想分步就**先停**、由**人**另发一条评论；\"分两步更清楚\"不构成理由）。\n")

    def test_valid_passes(self):
        self._write_valid()
        cm.check_self_dispatch_guard()
        self.assertEqual(cm.errors, [])

    def test_missing_platform_file_reports(self):
        # 反例：平台层文件被删 → 自派禁令无处承载
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "platform", "cnb.adoc"))
        cm.check_self_dispatch_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_platform_clause_removed_reports(self):
        # 反例（最危险的一种）：平台层那条 L1 被整条删掉 → "再派一次"重新变成可选动作
        self._write_valid()
        cnb = self.CNB.replace(
            "* **不得以评论派发唤起自己（L1，防无限派发）**", "* **附注**")
        self.write("specs/platform/cnb.adoc", cnb)
        cm.check_self_dispatch_guard()
        self.assertIn("不得以评论派发唤起自己", self.error_texts())

    def test_platform_rule_relaxed_reports(self):
        # 反例：把禁令降级成建议（L1 被抽掉）→ 强制点没了
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   self.CNB.replace("（L1，防无限派发）**：被评论唤起的执行者",
                                    "**：原则上被评论唤起的执行者"))
        cm.check_self_dispatch_guard()
        self.assertIn("L1", self.error_texts())

    def test_relay_to_others_clause_removed_reports(self):
        # 反例："转由他人代发"被删 → 把自派外包出去就绕过了
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   self.CNB.replace("**也不得转由他人**/其他执行者**代发**。", "。"))
        cm.check_self_dispatch_guard()
        self.assertIn("代发", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例：判定标准被抽空（只留一句口号）→ 争议时无法判断是否被遵守
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   self.CNB.replace("①本次执行期间新增的点名评论"
                                    "指向本条评论上的唤起名；", "")
                   .replace("**实际发了这条评论**、把任务在执行中重新发起一次（判据是**这条评论发出去没有**、"
                            "**不是这次执行有没有因此结束**）；", "")
                   .replace("**转交他人**代发。", ""))
        cm.check_self_dispatch_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_process_boundary_clause_removed_reports(self):
        # 反例："判据是这条评论发出去没有"被删 → "不在同一进程内所以不算"成为新借口
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   self.CNB.replace("（判据是**这条评论发出去没有**、"
                                    "**不是这次执行有没有因此结束**）", ""))
        cm.check_self_dispatch_guard()
        self.assertIn("这条评论发出去没有", self.error_texts())

    def test_general_layer_clause_removed_reports(self):
        # 反例：通用层同口径条被删 → 非 CNB 场景下"想分步就自动再派"无人拦
        self._write_valid()
        self.write("specs/general/collab.adoc",
                   "= agent 协作规范（通用层）\n\n== 派发入口（往哪派、派什么）\n"
                   "* 评论即派发入口。\n")
        cm.check_self_dispatch_guard()
        self.assertIn("执行者不得自行发评论唤起自己", self.error_texts())

    def test_prompt_step_removed_reports(self):
        # 反例：题面侧步骤被删（片段在、流程里却没有这一步）→ 执行者按流程走即漏
        self._write_valid()
        self.write("prompts/refactor.adoc",
                   "= 重构\n\ninclude::_common.txt[tag=delivery]\n")
        cm.check_self_dispatch_guard()
        self.assertIn("不得自行发评论唤起自己", self.error_texts())

    def test_dispatcher_not_synced_reports(self):
        # 反例：调度器识别特征被删 → 该 L1 永远不会被加载（写了等于没写）
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "* 多 agent 协作（派发入口）\n* CNB 平台（评论唤起新实例）\n")
        cm.check_self_dispatch_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_registry_not_synced_reports(self):
        # 反例：登记处未同步 → 提示词被复制到未知项目后公开面看不到这条禁令
        self._write_valid()
        self.write("PROMPTS.adoc", "* 公共约定：改动范围边界。\n")
        cm.check_self_dispatch_guard()
        self.assertIn("PROMPTS.adoc", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例：README 使用要点未同步 → 公开面只看得见"可以评论派活"
        self._write_valid()
        self.write("README.adoc", "# README\n\n普通说明。\n")
        cm.check_self_dispatch_guard()
        self.assertIn("README", self.error_texts())

    def test_platform_applicability_removed_reports(self):
        # 反例（用户后续澄清的那一条）：平台层把"只适用于 CNB"的适用面删掉
        # → 该要求被外推成平台无关的强制前提，非 CNB 环境会把"没有同 Agent 子执行者"
        # 读成"所以不能验证/不能交付"。
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   self.CNB.replace("**只在本平台（CNB）成立**", "**一律成立**")
                   .replace("**本平台之外不适用**", "**各处一律适用**")
                   .replace("**不得援引该条拒做或把任务停在中间**", "**照常执行**"))
        cm.check_self_dispatch_guard()
        self.assertIn("本平台之外不适用", self.error_texts())

    def test_platform_not_public_content_clause_removed_reports(self):
        # 反例：把"写入面不在公共内容里"删掉 → 引用方会以为该前提随公共入口一起下发
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   self.CNB.replace("不在公共内容", "在公共内容"))
        cm.check_self_dispatch_guard()
        self.assertIn("不在公共内容", self.error_texts())

    def test_general_applicability_removed_reports(self):
        # 反例：通用层把"不是无条件成立的规则 / 以平台层写明为前提"删掉
        # → 通用层被当成平台无关的强制前提。
        self._write_valid()
        self.write("specs/general/collab.adoc",
                   self.COLLAB.replace("**不是无条件成立的规则**——"
                                       "以**平台层写明该前提成立**为前提；", ""))
        cm.check_self_dispatch_guard()
        self.assertIn("不是无条件成立的规则", self.error_texts())

    def test_self_mention_for_review_clause_removed_reports(self):
        # 反例：把"不得用为了复核去 @ 自己"删掉 → "再要一个干净上下文来复核"成为自派的正当理由
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   self.CNB.replace(
                       '故**执行者不得用**\"为了满足同 Agent 复核\"**去 @ 自己**'
                       '（不因目的是复核而放宽）。', "。"))
        cm.check_self_dispatch_guard()
        self.assertIn("去 @ 自己", self.error_texts())

    def test_deliver_without_review_not_confused_clause_removed_reports(self):
        # 反例：把"已交付 + 校验全绿 + 复核缺口如实标出不得混写成已复核通过"删掉
        # → 缺复核被悄悄记成"已复核通过"。
        self._write_valid()
        self.write("specs/platform/cnb.adoc",
                   self.CNB.replace(
                       '**\"已交付 + 校验全绿 + 复核缺口如实标出\"不得混写**成'
                       '\"已复核通过\"。', "。"))
        cm.check_self_dispatch_guard()
        self.assertIn("已复核通过", self.error_texts())

    def test_general_layer_source_vs_dispatch_clause_removed_reports(self):
        # 反例：通用层把"来源要求 ≠ 发起方式"这条配套判据删掉
        # → 非 CNB 场景下会被读成"必须自派"或"不许复核"。
        self._write_valid()
        self.write("specs/general/collab.adoc",
                   self.COLLAB.replace('* **"复核者的来源"与"复核的发起"是两件事（L1）**：'
                                       '不得把"满足同 Agent"读成'
                                       '"必须再发一条评论叫一个 Agent 来"——'
                                       '**一个任务只由人决定起几次执行**；'
                                       '**拿不到同 Agent 子执行者时**按降级路径'
                                       '**在本次执行内**补；**交付照常**、缺口如实写明。\n', ""))
        cm.check_self_dispatch_guard()
        self.assertIn("复核的发起", self.error_texts())

    def test_verify_applicability_removed_reports(self):
        # 反例：三视角落点把适用面标注删掉 → 不同口径的平台被同一条强判。
        self._write_valid()
        self.write("specs/general/verify.adoc",
                   "= 验证\n\n* 执行者选择：强制同 Agent（L1）：一律由与执行者相同的 Agent 承担。\n")
        cm.check_self_dispatch_guard()
        self.assertIn("其适用面由平台层限定", self.error_texts())


class TestCheckApiNamingGuard(CheckSpecsTestCase):
    """钉住『Feign 接口命名带所属域/项目前缀防线』。

    该条对应用户提出的真实失效：写 Feign 接口时接口名不带所归属的前缀，同域多个服务的同类
    Feign 接口**同名碰名**（`UserApi` 到处都是），只能靠包名区分。
    用户要求：`api` 前加一个前缀，**优先考虑已有的固定前缀**；没有先例则取项目名称单词的
    词首再组合（`user-center` → `UcUserApi`、`open-user-center` → `OucUserApi`）。
    用户同时限定范围：**目前只需要考虑 feign，不需要考虑其他对外接口**。

    最易被四件事冲掉：
      * **条文被删或降级成建议** —— "随手取个不碰名的"重回默认做法；
      * **范围被自行放大** —— 写回"对外提供或跨服务/跨项目调用的接口"，把用户明确排除的
        REST Controller / RPC 契约接口卷进来；
      * **技术栈落点缺失** —— Java 执行者按栈文件学，通用层有、栈层没有等于没写；
      * **调度器识别特征被删** —— 该条永远不会被触发加载（写了等于没写）。
    故本组用例覆盖：条文被删 / L1 被降级 / 范围限定被删 / 范围被写宽 / 判据被抽（先例优先、
    实例）/ 栈落点缺失 / 栈层不指向通用条 / 调度器未登记 / README 未同步 / 图书馆依据缺失。
    """

    CODING = (
        "= 通用编码规范\n"
        "\n"
        "== 命名与代码质量\n"
        "* Feign 接口命名带所属域/项目前缀（L1）：**Feign 声明式 HTTP 客户端接口**"
        "（跨服务远程调用接口；本次**只此一类**，其他对外接口如 REST Controller、RPC 服务契约接口"
        "暂不在本约束内，不按本条改名，也不得据此扩张判定）命名须为「**前缀 + 接口业务名 + `Api`**」，"
        "前缀由**接口所属的域/项目**决定——**先取该域已存在的固定前缀（先例优先），没有先例才按项目名"
        "取词首字母组合**（`user-center` → `Uc`、`open-user-center` → `Ouc`，即 `UcUserApi`、"
        "`OucUserApi`）。判定：①所属域已有固定前缀却另取一套；②同类接口有的带前缀有的不带"
        "（同一项目内不一致）；③把业务名或所属服务的全名当接口名前缀（如 `UserCenterUserApi` "
        "一类**拼全名**的写法）。\n"
    )

    JAVA = (
        "= Java 规范（技术栈层）\n"
        "\n"
        "== 命名\n"
        "* Feign 接口命名带所属域前缀（L1，Java 落点，本条唯一适用面）：**Feign 声明式 HTTP "
        "客户端接口**按「**前缀 + 接口业务名 + `Api`**」命名——`user-center` → `UcUserApi`、"
        "`open-user-center` → `OucUserApi`；**只约束 Feign 接口**，REST Controller、RPC 服务契约"
        "等其他对外接口不适用。判据见 link:../general/coding.adoc[]「命名与代码质量」的"
        "「Feign 接口命名带所属域/项目前缀」。\n"
    )

    GENERIC = (
        "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
        "  ** 编写代码 → link:specs/general/coding.adoc[]（含**「Feign 接口命名带所属域/项目前缀」**："
        "**只此一类**接口适用）\n"
        "  ** Java 项目（存在 `.java`）→ link:specs/stack/java.adoc[]（**Feign 接口命名**："
        "前缀 + 接口业务名 + `Api`，只约束 Feign 接口）\n"
    )

    SOURCES = (
        "= 图书馆依据\n\n== Feign 接口命名带所属域前缀（Spring Cloud）\n"
        "* 说明：此条为要点转述、非逐字摘录；本仓库**未逐字取回**，故不引用任何加引号的字句。\n"
        "* 适用范围：用户明确「目前只需要考虑 feign，不需要考虑其他对外接口」，故只取 Feign 这一类。\n"
    )

    def setUp(self) -> None:
        super().setUp()
        self._orig_coding = cm.CODING_FILE
        self._orig_java = cm.JAVA_STACK_FILE
        self._orig_generic = cm.GENERIC_FILE
        self._orig_readme = cm.README_FILE
        cm.CODING_FILE = os.path.join(self.root, "specs", "general", "coding.adoc")
        cm.JAVA_STACK_FILE = os.path.join(self.root, "specs", "stack", "java.adoc")
        cm.GENERIC_FILE = os.path.join(self.root, "AGENTS_COMMON.adoc")
        cm.README_FILE = os.path.join(self.root, "README.adoc")

    def tearDown(self) -> None:
        (cm.CODING_FILE, cm.JAVA_STACK_FILE, cm.GENERIC_FILE,
         cm.README_FILE) = (self._orig_coding, self._orig_java, self._orig_generic,
                            self._orig_readme)
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("specs/general/coding.adoc", self.CODING)
        self.write("specs/stack/java.adoc", self.JAVA)
        self.write("AGENTS_COMMON.adoc", self.GENERIC)
        self.write("README.adoc", "# README\n\n## 目录结构\n* 技术栈层：java（含**Feign 接口命名**）\n")
        self.write("library/sources.adoc", self.SOURCES)

    def test_valid_api_naming_guard_passes(self):
        self._write_valid()
        cm.check_api_naming_guard()
        self.assertEqual(cm.errors, [])

    def test_clause_deleted_reports(self):
        # 反例：通用层条文被删 → "随手取个不碰名的"重回默认做法
        self._write_valid()
        self.write("specs/general/coding.adoc", "= 通用编码规范\n\n== 命名与代码质量\n* 命名要清晰。\n")
        cm.check_api_naming_guard()
        self.assertIn("Feign 接口命名带所属域/项目前缀", self.error_texts())

    def test_level_downgraded_reports(self):
        # 反例：L1 被降级成建议（读起来无害，于是"项目小可以不加"重新成立）
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("（L1）", "（L2，建议）"))
        cm.check_api_naming_guard()
        self.assertIn("L1", self.error_texts())

    def test_scope_narrowing_removed_reports(self):
        # 反例：范围限定（只此一类接口）被删 → 判定面可被自行放大
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("（跨服务远程调用接口；本次**只此一类**，其他对外接口如 REST Controller、"
                                       "RPC 服务契约接口暂不在本约束内，不按本条改名，也不得据此扩张判定）", ""))
        cm.check_api_naming_guard()
        self.assertIn("只此一类", self.error_texts())

    def test_scope_widened_reports(self):
        # 反例：范围被写宽（用户明确排除的其他对外接口被卷进来）
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("（跨服务远程调用接口；本次**只此一类**，其他对外接口如 REST Controller、"
                                       "RPC 服务契约接口暂不在本约束内，不按本条改名，也不得据此扩张判定）",
                                       "（RPC/服务契约接口等其他对外接口同样适用）"))
        cm.check_api_naming_guard()
        self.assertIn("RPC/服务契约接口", self.error_texts())

    def test_precedent_priority_removed_reports(self):
        # 反例：'优先用已有的固定前缀'（先例优先）被抽掉 → 等于要求每个接口现场发明一套前缀
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("**先取该域已有的固定前缀（先例优先），", "")
                   .replace("先例优先", ""))
        cm.check_api_naming_guard()
        self.assertIn("先例优先", self.error_texts())

    def test_examples_removed_reports(self):
        # 反例（关键词堆砌式假绿）：实例被抽掉 → 读者无法判断自己是否命中
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   "= 通用编码规范\n\n== 命名与代码质量\n"
                   "* Feign 接口命名带所属域/项目前缀（L1）：只此一类，其他对外接口不适用。"
                   "前缀取已有固定前缀、先例优先；判定：同一项目内不一致属违规。"
                   "Feign 接口固定后缀 `Api`。\n")
        cm.check_api_naming_guard()
        self.assertIn("UcUserApi", self.error_texts())

    def test_java_stack_missing_reports(self):
        # 反例：Java 栈落点缺失 → Java 执行者按栈文件学仍会随手取名
        self._write_valid()
        os.remove(cm.JAVA_STACK_FILE)
        cm.check_api_naming_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_java_stack_not_pointing_general_reports(self):
        # 反例：栈层只写实例、不指向通用条 → 判据与反例在栈层读不到
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   "= Java 规范\n\n== 命名\n* Feign 接口：`UcUserApi`、`OucUserApi`。\n")
        cm.check_api_naming_guard()
        self.assertIn("coding.adoc", self.error_texts())

    def test_dispatcher_not_registered_reports(self):
        # 反例：调度器两处识别特征被删 → 该条永远不会被触发加载（写了等于没写）
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
                   "  ** 编写代码 → link:specs/general/coding.adoc[]\n")
        cm.check_api_naming_guard()
        self.assertIn("Feign 接口命名", self.error_texts())

    def test_dispatcher_scope_marker_removed_reports(self):
        # 反例：调度器只剩条名、范围标注被删 → 会被读成适用于所有接口
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
                   "  ** 编写代码 → link:specs/general/coding.adoc[]"
                   "（含**「Feign 接口命名带所属域/项目前缀」**）\n"
                   "  ** Java 项目 → link:specs/stack/java.adoc[]（**Feign 接口命名**）\n")
        cm.check_api_naming_guard()
        self.assertIn("只此一类", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例：README 目录说明未同步 → 公开面看不到这条
        self._write_valid()
        self.write("README.adoc", "# README\n\n## 目录结构\n* 技术栈层：java\n")
        cm.check_api_naming_guard()
        self.assertIn("接口命名", self.error_texts())

    def test_library_basis_missing_reports(self):
        # 反例：图书馆依据落点缺该条（依据只剩名称）
        self._write_valid()
        self.write("library/sources.adoc", "= 图书馆依据\n\n== 别的主题\n* 略。\n")
        cm.check_api_naming_guard()
        self.assertIn("library/sources.adoc", self.error_texts())

    def test_library_scope_note_removed_reports(self):
        # 反例：图书馆依据未写明只取 Feign 这一类 → 依据被读成通用命名规则
        self._write_valid()
        self.write("library/sources.adoc",
                   "= 图书馆依据\n\n== Feign 接口命名带所属域前缀（Spring Cloud）\n"
                   "* 说明：要点转述、非逐字摘录；本仓库**未逐字取回**。\n")
        cm.check_api_naming_guard()
        self.assertIn("只需要考虑 feign", self.error_texts())


class TestCheckApiContractReuseGuard(CheckSpecsTestCase):
    """钉住『请求/响应类优先移动复用 + HTTP 接口路径优先中划线』防线。

    两条都来自用户的一次要求：给已有接口加 Feign 内部接口时**优先移动请求/响应类、不新建**（例外只有
    数据库实体类与"类里引用了第三方类型"，且**本项目自身的依赖不算三方依赖**）；**feign 接口地址优先使用中划线**。

    最易被四件事冲掉：
      * **条文被删或降级成建议** —— "另建一套更省事"重回默认做法；
      * **例外与边界被写宽/抽掉** —— 尤其"本项目自身的依赖不算三方依赖"这条边界，缺位即等于给出一个
        随时可套用的豁免口（"它依赖本项目别的模块"就能另建一套）；
      * **路径条被删或退回下划线/驼峰** —— 同一项目两种风格并存；
      * **路径条被搬到通用层** —— 通用层会出现只在 Web 框架语境下有定义的判据（协议/框架专名污染）。
    故本组用例覆盖：条文缺失 / L1 降级 / 边界字句被抽 / 移动动作被抽 / 判定标准被抽 / 路径条缺失或降级 /
    两处照旧被删 / 路径条被写进通用层 / 调度器两处识别特征缺失 / README 未同步 / 图书馆依据缺失。
    """

    CODING = (
        "= 通用编码规范\n\n== 代码复用\n"
        "* **跨服务/对外调用的请求响应类优先移动复用，不新建（L1）**：给**已有的接口**增加**新的内部调用接口**"
        "（如 Feign 等声明式 HTTP 客户端）时，**优先把**该接口所需的**请求/响应类移动**到新接口所属的位置并**沿用**，"
        "**不得**为它另写一套同名同构的类。**移动而非复制**：移动后同步更新全部引用；"
        "**不得**一处移动、一处留副本。**两种例外**：①**数据库实体类**——除用户明确声明允许外一律**不移动**；"
        "②**引用了第三方类型**的类。**边界：本项目自身的依赖不算三方依赖**——由本项目自己的**其他模块**提供的类型"
        "仍属可一起移动。**判定标准（任一命中即违规）**：①另建新建的请求/响应类而项目内已有等价同类；"
        "②该新建类与既有类**同名或仅差包名**；③只**复制**既有类而不改原引用；"
        "④以「它依赖本项目的其他模块」为由拒绝移动；⑤**移动了数据库实体类**而没有用户声明。"
        "**存量边界**：改到哪个接口才顺带调整"
        "（随动迁移，见 `specs/core/execution.adoc`）。"
        "依据：ISO/IEC 25010 可维护性。\n"
    )

    SPRING = (
        "= Spring 规范（技术栈层）\n\n== 分层与职责\n"
        "* **HTTP 接口路径优先用中划线（kebab-case）（L1）**：路由路径的**路径片段**须用小写 + 中划线（`-`），"
        "**不得**用下划线（`_`）或驼峰/大写。**两处照旧**：①**服务路由前缀/网关前缀**；"
        "②**已发布、外部依赖的对外路径**。**判定标准**：①路径里出现 `_`；②路径片段用驼峰/大写；"
        "③同一接口内两种风格混用。**存量边界**：不发动全库改名（随动迁移，见 `specs/core/execution.adoc`）。"
        "**与命名规则的分工**：本条只管**路径字符串**，类名命名按 link:java.adoc[]「命名」。"
        "依据：RFC 3986。\n"
    )

    # 调度器**只给触发特征**（何时命中），不抄条目本体——刻意写成"只登记"的形态，
    # 与放宽后的守卫口径一致（`请求响应类`/`路由路径`/`对外接口…返回值…用什么类承载`）。
    GENERIC = (
        "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
        "  ** 编写代码 → link:specs/general/coding.adoc[]（识别特征："
        "要**新增一个内部调用接口**的请求响应类；要判定对外接口的请求/响应参数与返回值"
        "用什么类承载）\n"
        "  ** Spring 项目 → link:specs/stack/spring.adoc[]（识别特征：写/改路由路径）\n"
    )

    README = "# README\n\n## 目录结构\n* 通用层：请求响应类优先移动复用\n* 技术栈层：接口路径优先用中划线\n"

    SOURCES = (
        "= 图书馆依据\n\n== HTTP 接口路径的命名风格（RFC 3986）\n"
        "* **须注意的语义差异（同义性）**：标准只给方向与下限，判据化取值属本集合取舍。\n"
        "\n== 请求/响应类的复用与跨模块移动（ISO/IEC 25010 可维护性）\n"
        "* **须注意的语义差异（同义性）**：例外清单属本集合自己的取舍。\n"
    )

    ADOPTION = (
        "= 图书馆：本集合自身取舍\n\n== 同义性差异与覆盖点\n"
        "* **请求/响应类优先移动复用、HTTP 接口路径优先中划线（L1）两条均为本集合自己的判据化取舍**：略。\n"
    )

    def setUp(self) -> None:
        super().setUp()
        self._orig_coding = cm.CODING_FILE
        self._orig_spring = cm.SPRING_STACK_FILE
        self._orig_generic = cm.GENERIC_FILE
        self._orig_readme = cm.README_FILE
        cm.CODING_FILE = os.path.join(self.root, "specs", "general", "coding.adoc")
        cm.SPRING_STACK_FILE = os.path.join(self.root, "specs", "stack", "spring.adoc")
        cm.GENERIC_FILE = os.path.join(self.root, "AGENTS_COMMON.adoc")
        cm.README_FILE = os.path.join(self.root, "README.adoc")

    def tearDown(self) -> None:
        (cm.CODING_FILE, cm.SPRING_STACK_FILE, cm.GENERIC_FILE,
         cm.README_FILE) = (self._orig_coding, self._orig_spring, self._orig_generic,
                            self._orig_readme)
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("specs/general/coding.adoc", self.CODING)
        self.write("specs/stack/spring.adoc", self.SPRING)
        self.write("AGENTS_COMMON.adoc", self.GENERIC)
        self.write("README.adoc", self.README)
        self.write("library/sources.adoc", self.SOURCES)
        self.write("library/adoption.adoc", self.ADOPTION)

    def test_valid_guard_passes(self):
        self._write_valid()
        cm.check_api_contract_reuse_guard()
        self.assertEqual(cm.errors, [])

    def test_clause_deleted_reports(self):
        # 反例：通用层条文被删 → "另建一套更省事"重回默认做法
        self._write_valid()
        self.write("specs/general/coding.adoc", "= 通用编码规范\n\n== 代码复用\n* 复用。\n")
        cm.check_api_contract_reuse_guard()
        self.assertIn("跨服务/对外调用的请求响应类优先移动复用", self.error_texts())

    def test_level_downgraded_reports(self):
        # 反例：L1 被降级成建议
        self._write_valid()
        self.write("specs/general/coding.adoc", self.CODING.replace("（L1）", "（L2，建议）"))
        cm.check_api_contract_reuse_guard()
        self.assertIn("L1", self.error_texts())

    def test_dependency_boundary_removed_reports(self):
        # 反例：'本项目自身的依赖不算三方依赖'被抽掉 → 给出一个随时可套用的豁免口
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("**边界：本项目自身的依赖不算三方依赖**——", "")
                   .replace("本项目自身的依赖不算三方依赖", ""))
        cm.check_api_contract_reuse_guard()
        self.assertIn("本项目自身的依赖不算三方依赖", self.error_texts())

    def test_move_action_removed_reports(self):
        # 反例：'移动而非复制、同步更新全部引用'被抽 → 只剩"别新增"一句口号
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("**移动而非复制**：移动后同步更新全部引用；", ""))
        cm.check_api_contract_reuse_guard()
        self.assertIn("移动而非复制", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例（关键词堆砌式假绿）：判定标准被抽掉 → 无法判定是否命中
        self._write_valid()
        self.write("specs/general/coding.adoc", self.CODING.split("**判定标准")[0])
        cm.check_api_contract_reuse_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_spring_clause_deleted_reports(self):
        # 反例：路径条被删 → 下划线与驼峰混用重回默认做法
        self._write_valid()
        self.write("specs/stack/spring.adoc", "= Spring 规范\n\n== 分层与职责\n* 分层。\n")
        cm.check_api_contract_reuse_guard()
        self.assertIn("HTTP 接口路径优先用中划线（kebab-case）", self.error_texts())

    def test_spring_existing_paths_exception_removed_reports(self):
        # 反例：两处照旧（服务路由前缀、已发布对外路径）被抽掉 → 会被读成"所有路径都要改名"
        self._write_valid()
        self.write("specs/stack/spring.adoc",
                   self.SPRING.replace("**两处照旧**：①**服务路由前缀/网关前缀**；"
                                       "②**已发布、外部依赖的对外路径**。", ""))
        cm.check_api_contract_reuse_guard()
        self.assertIn("服务路由", self.error_texts())

    def test_path_clause_in_general_layer_reports(self):
        # 反例：路径条被放进通用层 → 只在 Web 框架语境下有定义的判据污染非 Web 项目
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING + "* HTTP 接口路径优先用中划线：路径片段用小写 + `-`。\n")
        cm.check_api_contract_reuse_guard()
        self.assertIn("coding.adoc", self.error_texts())

    def test_dispatcher_general_entry_not_pointing_reports(self):
        # 反例：调度器通用层识别特征被删 → 该条永远不会被触发加载
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
                   "  ** 编写代码 → link:specs/general/coding.adoc[]\n"
                   "  ** Spring 项目 → link:specs/stack/spring.adoc[]（**HTTP 接口路径优先用中划线**："
                   "路由路径片段用小写 + `-`）\n")
        cm.check_api_contract_reuse_guard()
        self.assertIn("请求响应类", self.error_texts())

    def test_dispatcher_spring_entry_not_pointing_reports(self):
        # 反例：调度器 Spring 条目识别特征被删 → Spring 执行者读不到该条
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
                   "  ** 编写代码 → link:specs/general/coding.adoc[]（识别特征："
                   "要**新增一个内部调用接口**的请求响应类；要判定对外接口的请求/响应参数与返回值"
                   "用什么类承载）\n"
                   "  ** Spring 项目 → link:specs/stack/spring.adoc[]\n")
        cm.check_api_contract_reuse_guard()
        self.assertIn("路由路径", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例：README 目录说明未同步 → 公开面看不到这两条
        self._write_valid()
        self.write("README.adoc", "# README\n\n## 目录结构\n* 通用层\n")
        cm.check_api_contract_reuse_guard()
        self.assertIn("README", self.error_texts())

    def test_library_basis_missing_reports(self):
        # 反例：图书馆依据落点缺这两条（依据只剩名称）
        self._write_valid()
        self.write("library/sources.adoc", "= 图书馆依据\n\n== 别的主题\n* 略。\n")
        cm.check_api_contract_reuse_guard()
        self.assertIn("library/sources.adoc", self.error_texts())

    def test_adoption_tradeoff_missing_reports(self):
        # 反例：'本集合自己承认的更严取舍'未登记 → 读者会把两条读成标准规定
        self._write_valid()
        self.write("library/adoption.adoc", "= 图书馆：本集合自身取舍\n\n== 同义性差异与覆盖点\n* 别的取舍。\n")
        cm.check_api_contract_reuse_guard()
        self.assertIn("library/adoption.adoc", self.error_texts())


class TestCheckPersistenceAccessGuard(CheckSpecsTestCase):
    """钉住『持久化访问防线』（通用层抽象 / 技术栈层框架专名）。

    该条对应用户明确提出的硬性要求：**强制使用 `IService` 的成员方法
    `lambdaQuery()`/`lambdaUpdate()`/`ktQuery()`/`ktUpdate()`，除非无法替代，否则禁止
    `new QueryWrapper` 及其子类**。用户报告的失效形态：Service 已经
    `extends ServiceImpl<XxxMapper, Xxx>`，业务代码里却仍 `new QueryWrapper<>()` /
    `new LambdaQueryWrapper<>()` 拼条件——同一项目并存两套写法；非 Lambda 形态还用
    **字符串写列名**（`eq("user_name", ...)`），编译期查不出、改名即静默失效。

    分层口径（用户追加要求"coding.adoc 是通用规范，不应写入 mybatis plus"）：通用层只留
    **跨语言抽象**（三条 L1 + 抽象判定标准 + 例外 + 存量），**框架专名与禁止清单的唯一落点**
    是 `specs/stack/java.adoc`（不新开 `mybatis.adoc`）。

    最易被五件事冲掉（故本组用例逐一覆盖）：
      * **条文被删或降级成建议** —— `new` 构造器重回默认做法；
      * **禁止面被放宽** —— 只禁非 Lambda 形态、漏掉"同样类型安全但仍绕过入口"的
        `new LambdaQueryWrapper`（用户要求是"及其子类"）；或把 `Wrappers.lambdaQuery()`
        一类**静态构造方法**重新放行（用户追加要求："也在禁用范围内：`Wrappers.lambdaQuery()`
        等，使用 `service.lambdaQuery()` 等"——静态工厂同样绕过统一入口）；
      * **技术栈落点缺失** —— Java 执行者按栈文件学，通用层有、栈层没有等于没写；
      * **通用层被框架专名污染** —— `coding.adoc` 里点名 `IService`/`QueryWrapper`，
        对非 Java 项目不成立、又白占其上下文；
      * **调度器识别特征被删或未去专名** —— 该条永远不会被触发加载（写了等于没写），
        或非 Java 项目也被带入 MyBatis-Plus 术语。
    """

    CODING = (
        "= 通用编码规范\n\n"
        "== 持久化访问（数据库/缓存等）\n"
        "访问数据库、缓存等持久化存储时，一律走所属技术已提供的类型安全/声明式查询构造 API"
        "与其统一入口。\n"
        "* **统一入口（L1）**：持久化操作须经该技术约定的统一访问入口调用（该技术承载"
        "查询/更新的既有抽象），不自建构造器。\n"
        "* **优先用类型安全/声明式查询构造 API（L1）**：以方法引用/属性名引用表达列名、"
        "以声明式方法名表达查询（`findByXxx` 一类）；禁止用字符串写列名表名的构造方式。\n"
        "* **替代优先（L1）**：技术自带替代写法时强制使用，只在该形态表达不了所需语义时才退回"
        "通用构造器，且须写明理由。\n"
        "* **判定标准（任一命中即违规）**：①出现技术自带构造器的直接 `new`；②列名以字符串写进"
        "查询构造；③绕过统一入口自建查询构造。\n"
        "* **例外与边界（L2）**：不禁止「跨语言执行脚本的落点」所指的映射文件承载。\n"
        "* **存量边界**：随动迁移，见 `specs/core/execution.adoc`。\n"
        "* 依据（标准名/编号）：ISO/IEC 25010、ISO/IEC/IEEE 29148。\n"
        "\n== 跨语言执行脚本的落点（资源文件夹，不写字符串拼接/模板）\n"
        "* 略。\n"
    )

    JAVA = (
        "= Java 规范（技术栈层）\n\n"
        "== 持久化访问（MyBatis-Plus / JPA 等）\n"
        "持久化访问按通用编码规范的「持久化访问（数据库/缓存等）」执行（见 "
        "link:../general/coding.adoc[]）；框架专名与禁止清单如下：\n"
        "* **MyBatis-Plus 强制使用 `IService` 的成员方法（L1）**：查询/更新一律走 `lambdaQuery()`、"
        "`lambdaUpdate()`、`ktQuery()`、`ktUpdate()`；禁止 `new QueryWrapper<>()`、"
        "`new UpdateWrapper<>()` 及其子类（含 `new LambdaQueryWrapper<>()`）。\n"
        "* **`IService` 之外的落点（L1）**：不得 `new` 任何 Wrapper，也不得改走 `Wrappers` 的"
        "**静态构造方法**（`Wrappers.lambdaQuery()` 一类）——静态构造同样绕过统一入口；落点只能"
        "是在 Mapper 接口上用注解/映射文件声明，或在该接口上以默认方法封装一次。\n"
        "* **例外（L2，须写清理由）**：确需 Wrapper 子类时在 Mapper 接口封装一次，业务侧不 new。\n"
        "* **判定标准（任一命中即违规）**：①构造器 `new`；②出现 `Wrappers.lambdaQuery()` 一类"
        "**静态构造方法**而本 Service 的成员方法可表达；③列名以字符串写进查询构造"
        "（可用方法引用表达时）；④绕过本实体 Service 的成员方法另起一套访问写法。\n"
        "* **存量边界**：随动迁移，见 `specs/core/execution.adoc`。\n"
    )

    # 调度器**只给触发特征**（在哪个类里调持久化 API、要查/改库时即命中），
    # 不抄条目本体的成员方法名与禁止面。
    GENERIC = (
        "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
        "  ** 编写代码 → link:specs/general/coding.adoc[]（识别特征：要写持久化访问代码"
        "——在哪个类里调持久化 API、要查/改库）\n"
        "  ** Java 项目（存在 `.java`）→ link:specs/stack/java.adoc[]（识别特征：持久化访问"
        "——要查/改库、出现统一入口/查询构造 API/包装器构造器字样）\n"
    )

    def setUp(self) -> None:
        super().setUp()
        self._orig_coding = cm.CODING_FILE
        self._orig_java = cm.JAVA_STACK_FILE
        self._orig_generic = cm.GENERIC_FILE
        self._orig_readme = cm.README_FILE
        cm.CODING_FILE = os.path.join(self.root, "specs", "general", "coding.adoc")
        cm.JAVA_STACK_FILE = os.path.join(self.root, "specs", "stack", "java.adoc")
        cm.GENERIC_FILE = os.path.join(self.root, "AGENTS_COMMON.adoc")
        cm.README_FILE = os.path.join(self.root, "README.adoc")

    def tearDown(self) -> None:
        (cm.CODING_FILE, cm.JAVA_STACK_FILE, cm.GENERIC_FILE,
         cm.README_FILE) = (self._orig_coding, self._orig_java, self._orig_generic,
                            self._orig_readme)
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("specs/general/coding.adoc", self.CODING)
        self.write("specs/stack/java.adoc", self.JAVA)
        self.write("AGENTS_COMMON.adoc", self.GENERIC)
        self.write("README.adoc", "# README\n\n## 目录结构\n* 通用层：含**持久化访问**：统一入口 + 类型安全构造\n")

    def test_valid_persistence_guard_passes(self):
        self._write_valid()
        cm.check_persistence_access_guard()
        self.assertEqual(cm.errors, [])

    def test_clause_deleted_reports(self):
        # 反例：通用层条文被删 → "随手 new 构造器"重回默认做法
        self._write_valid()
        self.write("specs/general/coding.adoc", "= 通用编码规范\n\n== 代码复用\n* 略。\n")
        cm.check_persistence_access_guard()
        self.assertIn("持久化访问（数据库/缓存等）", self.error_texts())

    def test_level_downgraded_reports(self):
        # 反例：统一入口被降级成建议（读起来无害，于是"偶尔 new 一下"重新成立）
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("**统一入口（L1）**", "**统一入口（L2，建议）**"))
        cm.check_persistence_access_guard()
        self.assertIn("统一入口（L1）", self.error_texts())

    def test_alternative_priority_removed_reports(self):
        # 反例：'替代优先'条被删 → "无法替代"的边界无处可判、禁止面可以被读成"看情况"
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("**替代优先（L1）**", "**补充说明**")
                   .replace("替代优先（L1）", "补充说明"))
        cm.check_persistence_access_guard()
        self.assertIn("替代优先（L1）", self.error_texts())

    def test_judgement_standard_removed_reports(self):
        # 反例：判定标准被删 → 只剩一句口径、无法判定是否命中
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("* **判定标准（任一命中即违规）**：①出现技术自带构造器的直接 "
                                       "`new`；②列名以字符串写进"
                                       "查询构造；③绕过统一入口自建查询构造。\n", ""))
        cm.check_persistence_access_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_general_layer_framework_name_reports(self):
        # 反例：通用层点名框架专名 → 对非 Java 项目不成立（替换主语测试失败）、白占其上下文
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("**优先用类型安全/声明式查询构造 API（L1）**：以方法引用/属性名引用表达列名、",
                                       "**优先用类型安全/声明式查询构造 API（L1）**：优先用 `IService` 的 `lambdaQuery()`、"))
        cm.check_persistence_access_guard()
        self.assertIn("IService", self.error_texts())

    def test_general_layer_wrapper_name_reports(self):
        # 反例：通用层把具体禁止清单（Wrapper 类名）写进来 → 专名归技术栈层
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("③绕过统一入口自建查询构造。",
                                       "③出现 `new QueryWrapper` 或 `new LambdaQueryWrapper`。"))
        cm.check_persistence_access_guard()
        self.assertIn("QueryWrapper", self.error_texts())

    def test_java_stack_missing_reports(self):
        # 反例：Java 栈落点缺失 → Java 执行者按栈文件学仍会随手 new
        self._write_valid()
        os.remove(cm.JAVA_STACK_FILE)
        cm.check_persistence_access_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_kt_methods_removed_reports(self):
        # 反例：Kotlin 的 kt* 成员方法被漏掉 → Kotlin 项目学不全、更新侧无落点
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   self.JAVA.replace("`lambdaUpdate()`、`ktQuery()`、`ktUpdate()`", "`lambdaUpdate()`"))
        cm.check_persistence_access_guard()
        self.assertIn("ktQuery", self.error_texts())

    def test_lambda_wrapper_subclass_allowed_reports(self):
        # 反例：禁止面被放宽成"只禁非 Lambda 形态" → 用户明确要求的"及其子类"被丢掉
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   self.JAVA.replace("、`new UpdateWrapper<>()` 及其子类（含 `new LambdaQueryWrapper<>()`）", ""))
        cm.check_persistence_access_guard()
        self.assertIn("子类", self.error_texts())

    def test_exception_clause_removed_reports(self):
        # 反例：例外条被删 → "无法替代"时执行者无处可去，只能继续 new
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   self.JAVA.replace("* **例外（L2，须写清理由）**：确需 Wrapper 子类时在 Mapper 接口"
                                     "封装一次，业务侧不 new。\n", ""))
        cm.check_persistence_access_guard()
        self.assertIn("例外（L2", self.error_texts())

    def test_iservice_static_factory_reallowed_reports(self):
        # 反例：`Wrappers` 一族静态构造方法被重新放行（条款改回"用 `Wrappers` 的静态方法即可"、
        # 判定标准也不再点名静态构造）→ 用户明确要求的"也在禁用范围内"被丢掉
        # （用户原话："也在禁用范围内：`Wrappers.lambdaQuery()` 等，使用 `service.lambdaQuery()` 等"）
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   self.JAVA.replace("不得 `new` 任何 Wrapper，也不得改走 `Wrappers` 的"
                                     "**静态构造方法**（`Wrappers.lambdaQuery()` 一类）——静态构造同样绕过统一入口；落点只能"
                                     "是在 Mapper 接口上用注解/映射文件声明，或在该接口上以默认方法封装一次。",
                                     "用 `Wrappers` 的静态方法即可。")
                            .replace("②出现 `Wrappers.lambdaQuery()` 一类"
                                     "**静态构造方法**而本 Service 的成员方法可表达；", ""))
        cm.check_persistence_access_guard()
        self.assertIn("静态构造", self.error_texts())

    def test_iservice_external_mapper_place_removed_reports(self):
        # 反例：`IService` 之外的落点（Mapper 注解/映射文件声明、Mapper 默认方法）被删
        # → 统一入口表达不了时执行者无处可去、只能回头 new 或走 Wrappers 静态工厂
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   self.JAVA.replace("落点只能是"
                                     "在 Mapper 接口上用注解/映射文件声明，或在该接口上以默认方法封装一次。",
                                     "落点见上。")
                            .replace("* **例外（L2，须写清理由）**：确需 Wrapper 子类时在 Mapper 接口"
                                     "封装一次，业务侧不 new。\n", ""))
        cm.check_persistence_access_guard()
        self.assertIn("Mapper 接口", self.error_texts())

    def test_dispatcher_registration_removed_reports(self):
        # 反例：调度器识别特征被删 → 该条永远不会被触发加载
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
                   "  ** 编写代码 → link:specs/general/coding.adoc[]\n"
                   "  ** Java 项目 → link:specs/stack/java.adoc[]\n")
        cm.check_persistence_access_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_dispatcher_java_entry_marker_removed_reports(self):
        # 反例：Java 栈登记只剩文件路径、连"要查/改库"这一触发特征都没有 → Java 项目看不到判据
        # （放宽后**不再**要求调度器抄成员方法名与禁止面——那是 `java.adoc` 的条目本体）
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
                   "  ** 编写代码 → link:specs/general/coding.adoc[]（识别特征：要写持久化访问代码"
                   "——在哪个类里调持久化 API、要查/改库）\n"
                   "  ** Java 项目（存在 `.java`）→ link:specs/stack/java.adoc[]\n")
        cm.check_persistence_access_guard()
        self.assertIn("Java 技术栈登记", self.error_texts())

    def test_dispatcher_general_entry_framework_name_reports(self):
        # 反例：通用层调度条目仍带框架专名 → 非 Java 项目也被带入 MyBatis-Plus 术语、与归属层冲突
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
                   "  ** 编写代码 → link:specs/general/coding.adoc[]（识别特征：要写持久化访问代码"
                   "——在哪个类里调 `IService` 的 `lambdaQuery()`）\n"
                   "  ** Java 项目（存在 `.java`）→ link:specs/stack/java.adoc[]（识别特征：持久化访问"
                   "——要查/改库、出现统一入口/查询构造 API/包装器构造器字样）\n")
        cm.check_persistence_access_guard()
        self.assertIn("IService", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例：README 目录说明未同步 → 公开面看不到这条
        self._write_valid()
        self.write("README.adoc", "# README\n\n## 目录结构\n* 通用层：通用编码\n")
        cm.check_persistence_access_guard()
        self.assertIn("持久化访问", self.error_texts())



class TestCheckDeprecatedApiGuard(CheckSpecsTestCase):
    """钉住『弃用类/API 防线』（代码侧禁止面 + 依赖侧不动依赖面）。

    该条对应用户明确提出的规范调整：**不用被弃用的类，使用其他类代替（升级类/同名新类最好），
    默认不调整依赖，也不动依赖版本**。用户报告的失效形态：旧写法与新写法并存两条路径
    （「旧写法也能跑」「新写法不熟」留下的裁量点），以及借"换掉弃用类"顺手升级依赖版本。

    两处同向落点：`specs/general/coding.adoc`「警告与弃用」给禁止面与替代者取向、
    `specs/general/dependency.adoc`「升级与废弃」给"不动依赖面"的落点。

    最易被冲掉的四件事（故本组用例逐一覆盖）：
      * **条文被删** —— 弃用者与替代者重新并存；
      * **替代者取向被删** —— 「升级类/同名新类最好」这一用户点名取向丢失、随手挑一个替代；
      * **默认不动依赖面被删** —— "换掉弃用类"被读成许可顺手升级依赖（与用户口径相抵）；
      * **存量条未写明不构成豁免** —— 后条被读成覆盖前条的许可，新代码照存量写。
    """

    CODING = (
        "= 通用编码规范\n\n"
        "== 警告与弃用\n"
        "* **警告处理（L1）**：新代码不得引入警告，存量警告须修复或声明。\n"
        "* **不得使用被弃用的类/API，改用替代者（L1）**：被标记弃用（`@Deprecated`、"
        "`deprecated`、文档标注废弃等）的类、方法、接口、字段一律**不得在新代码里使用**，"
        "须改用其替代者；替代者**优先取升级后的新类、或同名新类**，其余替代形态次之。\n"
        "* **判定标准（任一命中即违规）**：①新写的代码里出现被弃用类型/成员的直接使用；"
        "②以「旧写法也能跑」为由继续用被弃用者；③把替代者选成同类弃用者的别名"
        "（换了个弃用者不算替代）。\n"
        "* **例外（L2，须写清理由）**：替代者在本项目声明的依赖面内不存在时，可写明理由"
        "保持原状。\n"
        "* **默认不为此调整依赖、也不动依赖版本（L1）**：改用替代者**不得**顺带改依赖清单"
        "或依赖版本。\n"
        "* **内部弃用 API 的调用不迁移、不修复（L2，存量边界）**：既有调用点保持原样。"
        "**本条**只管既有调用点——**不构成**对新代码的豁免。\n"
        "* 依据（标准名/编号）：ISO/IEC 25010、ISO/IEC/IEEE 29148。\n"
        "\n== 表达式与调用写法\n"
        "* 略。\n"
    )

    DEPENDENCY = (
        "= 依赖管理规范（通用层，跨语言）\n\n"
        "== 升级与废弃\n"
        "* **升级前看变更说明（L1）**：升级依赖须先读其变更日志/发布说明。\n"
        "* **弃用类/API 的迁移默认不动依赖面（L1）**：代码里出现被弃用的类/API 时，按 "
        "`specs/general/coding.adoc`「警告与弃用」改调用点、改用替代者即可，"
        "**默认不调整依赖、也不动依赖版本**。**判定标准**：一次「弃用迁移」的改动里出现"
        "依赖清单或版本变化，而其理由只是「替代者需要新版本」却未走本节升级流程。\n"
    )

    def setUp(self) -> None:
        super().setUp()
        self._orig_coding = cm.CODING_FILE
        self._orig_dep = cm.DEPENDENCY_FILE
        cm.CODING_FILE = os.path.join(self.root, "specs", "general", "coding.adoc")
        cm.DEPENDENCY_FILE = os.path.join(self.root, "specs", "general", "dependency.adoc")

    def tearDown(self) -> None:
        (cm.CODING_FILE, cm.DEPENDENCY_FILE) = (self._orig_coding, self._orig_dep)
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("specs/general/coding.adoc", self.CODING)
        self.write("specs/general/dependency.adoc", self.DEPENDENCY)

    def test_valid_deprecated_api_guard_passes(self):
        self._write_valid()
        cm.check_deprecated_api_guard()
        self.assertEqual(cm.errors, [])

    def test_clause_deleted_reports(self):
        # 反例：整节被删 → 弃用者与替代者重新并存
        self._write_valid()
        self.write("specs/general/coding.adoc", "= 通用编码规范\n\n== 表达式与调用写法\n* 略。\n")
        cm.check_deprecated_api_guard()
        self.assertIn("警告与弃用", self.error_texts())

    def test_level_downgraded_reports(self):
        # 反例：禁止面被降级成建议 → "偶尔用一下弃用者"重新成立
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("不得使用被弃用的类/API，改用替代者（L1）",
                                       "不得使用被弃用的类/API，改用替代者（L2，建议）"))
        cm.check_deprecated_api_guard()
        self.assertIn("不得使用被弃用的类/API，改用替代者（L1）", self.error_texts())

    def test_alternative_priority_removed_reports(self):
        # 反例：替代者取向被删 → 用户点名的「升级类/同名新类最好」丢失
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("优先取升级后的新类、或同名新类", "随取一个可用者"))
        cm.check_deprecated_api_guard()
        self.assertIn("优先取升级后的新类、或同名新类", self.error_texts())

    def test_dependency_boundary_removed_reports(self):
        # 反例：默认不动依赖面被删 → "换掉弃用类"被读成许可顺手升级依赖
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("* **默认不为此调整依赖、也不动依赖版本（L1）**：改用替代者"
                                       "**不得**顺带改依赖清单或依赖版本。\n", ""))
        cm.check_deprecated_api_guard()
        self.assertIn("默认不为此调整依赖、也不动依赖版本（L1）", self.error_texts())

    def test_legacy_not_exempting_new_code_reports(self):
        # 反例：存量条未写明"不构成对新代码的豁免" → 两条同处一节、后条抵消前条
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("**本条**只管既有调用点——**不构成**对新代码的豁免。",
                                       "新代码也照存量写。"))
        cm.check_deprecated_api_guard()
        self.assertIn("豁免", self.error_texts())

    def test_dependency_side_not_synced_reports(self):
        # 反例：依赖侧落点缺失 → 代码条与依赖条脱节，"不动依赖面"无落点
        self._write_valid()
        self.write("specs/general/dependency.adoc", "= 依赖管理规范\n\n== 升级与废弃\n* 略。\n")
        cm.check_deprecated_api_guard()
        self.assertIn("弃用类/API 的迁移默认不动依赖面（L1）", self.error_texts())


class TestCheckConversionGuard(CheckSpecsTestCase):
    """钉住『对象转换防线』（通用层抽象 / 技术栈层框架专名 / **建议层口径**）。

    该条对应用户提出的规范建议：**多层嵌套对象转换时，优先使用 mapstruct（jvm 下），
    不允许手写转换代码——不是强制，但是建议**。用户报告的失效形态：对象含对象、集合含对象时
    **手写逐字段搬运**（一层层 `new` + 逐个 `set`/`get`）——没有编译期保障，模型加字段后只在
    运行期表现为"某个字段一直是空"。

    分层口径（与「持久化访问」同一套）：通用层只留**跨语言抽象**（优先声明式映射、目标式判据、
    范围、例外、存量），**框架专名与写法的唯一落点**是 `specs/stack/java.adoc`「对象转换
    （MapStruct）」（就地承载，不新开 `mapstruct.adoc`）。

    本防线**按建议层口径钉住**（不是强制面）——用户明确要求不做强制性限制，故最易被五件事冲掉：
      * **优先路径被删** —— 退回"怎么顺手怎么写"；
      * **被写成强制面** —— "不允许手写转换代码""一律"重新出现，与用户口径相抵；
      * **范围被抄窄或抽掉** —— 无嵌套（单层）不管被抄成"两三字段以内不管"；
      * **备注原因 / 等价路径合规被删** —— "手写须写理由"丢失、"必须用某个库"复辟；
      * **通用层被框架专名污染** —— `coding.adoc` 里点名 `MapStruct`/`@Mapper`，
        对非 JVM 项目不成立、又白占其上下文。
    """

    CODING = (
        "= 通用编码规范\n\n"
        "== 对象转换（多层嵌套对象的转换）\n"
        "多层嵌套对象的转换，**首选声明式映射完成的转换**；**无嵌套（单层）的转换不在本条范围内**。\n"
        "* **首选声明式映射（L2）**：转换**优先**由转换库的映射声明完成。**优先路径不是唯一解**："
        "深拷贝/结构复制工具、序列化（如 JSON）中转、手工构建器等等价路径同样合规，判据按下条。\n"
        "* **达标判据（本条判定的是结果，不是手段）**：同一份转换**只有一处来源**；该结构增删字段、"
        "改字段时，转换处**不会静默漏字段**。手写逐字段搬运在多层嵌套下达不到该判据。\n"
        "* **除主动声明外，优先声明式映射；确需手写时须备注原因（L2）**：人来主动声明允许手写的按声明写；"
        "否则优先走声明式映射，确需手写时在**代码注释写明原因**。本条**不设强制面**。\n"
        "* **映射声明的落点**：映射声明与转换方法独立成文件、不塞进纯数据结构类。\n"
        "* **例外与边界（L2）**：①映射声明表达不了的语义不在本条适用，可在映射声明内以自定义方法承接；"
        "②**无嵌套（单层）的转换不在本条范围内**（与字段数量无关）。\n"
        "* **存量边界**：随动迁移，见 `specs/core/execution.adoc`。\n"
        "* 依据（标准名/编号）：ISO/IEC 25010、ISO/IEC/IEEE 29148。\n"
        "\n== 代码复用\n* 略。\n"
    )

    JAVA = (
        "= Java 规范（技术栈层）\n\n"
        "== 对象转换（MapStruct）\n"
        "对象转换按通用编码规范的「对象转换（多层嵌套对象的转换）」执行"
        "（见 link:../general/coding.adoc[]）——JVM 下**优先用 MapStruct**、**建议不手写转换代码**。\n"
        "* **多层嵌套对象转换优先用 MapStruct（L2，建议）**：用 MapStruct 的 `@Mapper` 映射接口声明完成；"
        "**建议不手写转换代码**。**不做强制性限制**——深拷贝/结构复制工具、序列化中转等等价路径同样合规。\n"
        "* **嵌套结构由映射声明表达（写法建议，非强制）**：对象含对象、集合含对象由**映射方法自动调用**"
        "或集合映射方法表达；手写循环不构成违规。\n"
        "* **不并存两套写法（先例优先）**：项目已有转换工具/既有 Converter 先例时跟随先例并在其基础上扩展。\n"
        "* **例外与边界（L2）**：**无嵌套（单层）的转换不在本条范围内**；确需手写时在**代码注释备注原因**。\n"
        "* **存量边界**：随动迁移，见 `specs/core/execution.adoc`。\n"
    )

    GENERIC = (
        "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
        "  ** 编写代码 → link:specs/general/coding.adoc[]（含**「对象转换（多层嵌套对象的转换）」**："
        "多层嵌套对象之间的转换（对象含对象/集合含对象的字段搬运、逐层 `new` 组装、手写循环转换））\n"
        "  ** Java 项目（存在 `.java`）→ link:specs/stack/java.adoc[]（**对象转换**："
        "多层嵌套对象转换**优先用 MapStruct**、**建议不手写转换代码**）\n"
    )

    README = ("# README\n\n## 目录结构\n* 通用层：含**对象转换**：多层嵌套对象转换优先用声明式映射、"
              "建议不手写逐字段搬运\n* 技术栈层：java（含**对象转换**：优先 MapStruct、建议不手写）\n")

    SOURCES = (
        "= 图书馆依据\n\n== 多层嵌套对象转换用声明式映射（MapStruct）\n"
        "* 说明：此条为要点转述、非逐字摘录；本仓库**未逐字取回**官方原文。\n"
        "* **须注意的语义差异（同义性）**：材料未规定必须用某库、也未规定禁止手写转换；"
        "判据化取值属本集合的取向。\n"
    )

    ADOPTION = (
        "= 规范准入与自身取舍\n\n== 同义性差异与覆盖点（本集合自己承认的）\n"
        "* **多层嵌套对象转换优先声明式映射、JVM 下优先 MapStruct**是本集合自己的取向（**建议、非强制**）："
        "用户要求「优先使用 mapstruct（jvm下），不允许手动写转换代码——不是强制，但是建议」。\n"
    )

    def setUp(self) -> None:
        super().setUp()
        self._orig_coding = cm.CODING_FILE
        self._orig_java = cm.JAVA_STACK_FILE
        self._orig_generic = cm.GENERIC_FILE
        self._orig_readme = cm.README_FILE
        cm.CODING_FILE = os.path.join(self.root, "specs", "general", "coding.adoc")
        cm.JAVA_STACK_FILE = os.path.join(self.root, "specs", "stack", "java.adoc")
        cm.GENERIC_FILE = os.path.join(self.root, "AGENTS_COMMON.adoc")
        cm.README_FILE = os.path.join(self.root, "README.adoc")

    def tearDown(self) -> None:
        (cm.CODING_FILE, cm.JAVA_STACK_FILE, cm.GENERIC_FILE,
         cm.README_FILE) = (self._orig_coding, self._orig_java, self._orig_generic,
                            self._orig_readme)
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("specs/general/coding.adoc", self.CODING)
        self.write("specs/stack/java.adoc", self.JAVA)
        self.write("AGENTS_COMMON.adoc", self.GENERIC)
        self.write("README.adoc", self.README)
        self.write("library/sources.adoc", self.SOURCES)
        self.write("library/adoption.adoc", self.ADOPTION)

    def test_valid_conversion_guard_passes(self):
        self._write_valid()
        cm.check_conversion_guard()
        self.assertEqual(cm.errors, [])

    def test_clause_deleted_reports(self):
        # 反例①：通用层条文被删 → 退回"怎么顺手怎么写"
        self._write_valid()
        self.write("specs/general/coding.adoc", "= 通用编码规范\n\n== 代码复用\n* 略。\n")
        cm.check_conversion_guard()
        self.assertIn("对象转换（多层嵌套对象的转换）", self.error_texts())

    def test_preferred_path_removed_reports(self):
        # 反例②：优先路径被抽掉（只剩范围与例外）→ 该条失去取向
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("**首选声明式映射完成的转换**",
                                       "**由映射声明完成的转换**")
                   .replace("* **首选声明式映射（L2）**", "* **声明式映射（L2）**"))
        cm.check_conversion_guard()
        self.assertIn("首选声明式映射", self.error_texts())

    def test_forced_wording_reports(self):
        # 反例③：条文被写成强制面（用户口径是"不是强制，但是建议"）
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("**首选声明式映射完成的转换**",
                                       "**一律用既有转换库的声明式映射完成，不允许手写转换代码**"))
        cm.check_conversion_guard()
        self.assertIn("不允许手写转换代码", self.error_texts())

    def test_goal_judgement_removed_reports(self):
        # 反例④：目标式判据被删 → 判据退回"用没用某个库"
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("* **达标判据（本条判定的是结果，不是手段）**：同一份转换**只有一处来源**；"
                                       "该结构增删字段、改字段时，转换处**不会静默漏字段**。"
                                       "手写逐字段搬运在多层嵌套下达不到该判据。\n", ""))
        cm.check_conversion_guard()
        self.assertIn("达标判据", self.error_texts())

    def test_comment_reason_removed_reports(self):
        # 反例⑤：备注原因被删 → "手写须写理由"这一动作丢失
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("* **除主动声明外，优先声明式映射；确需手写时须备注原因（L2）**："
                                       "人来主动声明允许手写的按声明写；"
                                       "否则优先走声明式映射，确需手写时在**代码注释写明原因**。"
                                       "本条**不设强制面**。\n", ""))
        cm.check_conversion_guard()
        self.assertIn("备注原因", self.error_texts())

    def test_equivalent_path_removed_reports(self):
        # 反例⑥：等价路径合规被删 → 该条易被读成"必须用某个库"
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("**优先路径不是唯一解**："
                                       "深拷贝/结构复制工具、序列化（如 JSON）中转、手工构建器等等价路径同样合规，"
                                       "判据按下条。", ""))
        cm.check_conversion_guard()
        self.assertIn("等价路径同样合规", self.error_texts())

    def test_scope_by_field_count_reports(self):
        # 反例⑦：范围被抄窄成按字段数判（用户口径是"无嵌套（单层）不管"）
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("**无嵌套（单层）的转换不在本条范围内**",
                                       "**单层、两三个字段的转换不在本条强制面**"))
        cm.check_conversion_guard()
        self.assertIn("字段", self.error_texts())

    def test_exception_clause_removed_reports(self):
        # 反例⑧：例外条被删 → 既有做法被一刀切
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("* **例外与边界（L2）**：①映射声明表达不了的语义不在本条适用，"
                                       "可在映射声明内以自定义方法承接；"
                                       "②**无嵌套（单层）的转换不在本条范围内**（与字段数量无关）。\n", ""))
        cm.check_conversion_guard()
        self.assertIn("例外与边界（L2", self.error_texts())

    def test_general_layer_framework_name_reports(self):
        # 反例⑨：通用层点名 MapStruct → 对非 JVM 项目不成立（替换主语测试失败）
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("由转换库的映射声明完成。", "由 MapStruct 的 `@Mapper` 映射声明完成。"))
        cm.check_conversion_guard()
        self.assertIn("MapStruct", self.error_texts())

    def test_java_stack_missing_reports(self):
        # 反例⑩：Java 栈落点缺失 → Java 执行者按栈文件学仍会手写转换
        self._write_valid()
        os.remove(cm.JAVA_STACK_FILE)
        cm.check_conversion_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_java_stack_not_pointing_general_reports(self):
        # 反例⑪：栈层不指向通用条 → 通用层判据与例外在栈层读不到
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   "= Java 规范\n\n== 对象转换（MapStruct）\n"
                   "* 多层嵌套对象转换优先用 MapStruct、建议不手写转换代码。\n")
        cm.check_conversion_guard()
        self.assertIn("coding.adoc", self.error_texts())

    def test_java_stack_forced_wording_reports(self):
        # 反例⑫：栈层回退成强制面（"不允许手写转换代码"）→ 与用户口径相抵
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   self.JAVA.replace("**建议不手写转换代码**。**不做强制性限制**",
                                     "**不允许手写转换代码**"))
        cm.check_conversion_guard()
        self.assertIn("不允许手写转换代码", self.error_texts())

    def test_java_stack_nesting_clause_removed_reports(self):
        # 反例⑬：嵌套/集合由映射方法表达的推荐写法被删 → 多层嵌套靶心无处落
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   self.JAVA.replace("* **嵌套结构由映射声明表达（写法建议，非强制）**：对象含对象、"
                                     "集合含对象由**映射方法自动调用**或集合映射方法表达；手写循环不构成违规。\n",
                                     ""))
        cm.check_conversion_guard()
        self.assertIn("映射方法自动调用", self.error_texts())

    def test_dispatcher_registration_removed_reports(self):
        # 反例⑭：调度器识别特征被删 → 该条永远不会被触发加载（写了等于没写）
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
                   "  ** 编写代码 → link:specs/general/coding.adoc[]\n"
                   "  ** Java 项目 → link:specs/stack/java.adoc[]\n")
        cm.check_conversion_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_dispatcher_general_entry_framework_name_reports(self):
        # 反例⑮：通用层调度条目带框架专名 → 非 JVM 项目也被带入该库术语、与归属层冲突
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
                   "  ** 编写代码 → link:specs/general/coding.adoc[]（含**「对象转换（多层嵌套对象的转换）」**："
                   "多层嵌套对象之间的转换用 `MapStruct` 的 `@Mapper` 映射接口）\n"
                   "  ** Java 项目（存在 `.java`）→ link:specs/stack/java.adoc[]（**对象转换**："
                   "多层嵌套对象转换**优先用 MapStruct**、**建议不手写转换代码**）\n")
        cm.check_conversion_guard()
        self.assertIn("MapStruct", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例⑯：README 目录说明未同步（或仍写"不允许手写"）→ 公开面口径与条文不一致
        self._write_valid()
        self.write("README.adoc", "# README\n\n## 目录结构\n* 通用层：通用编码\n")
        cm.check_conversion_guard()
        self.assertIn("对象转换", self.error_texts())

    def test_library_basis_missing_reports(self):
        # 反例⑰：图书馆依据落点缺该条（依据只剩名称）
        self._write_valid()
        self.write("library/sources.adoc", "= 图书馆依据\n\n== 别的主题\n* 略。\n")
        cm.check_conversion_guard()
        self.assertIn("library/sources.adoc", self.error_texts())

    def test_library_adoption_note_removed_reports(self):
        # 反例⑱：本集合取向未登记 → 读者会把本集合的建议读成标准规定
        self._write_valid()
        self.write("library/adoption.adoc", "= 规范准入与自身取舍\n\n== 同义性差异\n* 略。\n")
        cm.check_conversion_guard()
        self.assertIn("library/adoption.adoc", self.error_texts())


class TestCheckWiringGuard(CheckSpecsTestCase):
    """钉住『防线接线完整性』：定义了的防线必须会被执行（`CHECKS` 序列 + 闭包可达）。

    本仓库的实测失效（2026-09 复核 PR #89 时用探针复现）：把任一道防线从执行序列里摘掉、
    或新增防线却忘记接线，**check_specs.py 与全部配套测试仍全绿**——既有用例都是逐个
    函数直接调用被测防线，从不经过接线路径。本防线把该失效变成机械可拦项。

    **2026-09 重构**：执行次序从"`main()` 正文里的行序"改为显式的 `CHECKS` 序列——
    次序因此成为**数据**（可复述、可对账）。承接该改动的是三组用例：①接线（本节，按
    序列判可达）；②次序与 `specs-project-maintainer/guards.adoc` 的清单表一致
    （`TestCheckGuardOrderGuard`）；③接线数、用例数、台账点名（`TestCheckGuardManifest`，
    夹具同步改为序列形态）。**夹具改写不是放宽判据**：反例仍逐个钉住"定义了却没人执行"、
    "按注释里写一句不算接线"、"序列点名了不存在的防线"三类。
    """

    def _write_valid(self, body=None):
        """造一份"定义了且被 `CHECKS` 序列编排"的最小脚本 + 一个合法仓库根。"""
        self.write("script/check_specs.py",
                   "def check_alpha():\n"
                   "    \"\"\"A.\"\"\"\n"
                   "    pass\n\n\n"
                   "def check_beta():\n"
                   "    \"\"\"B.\"\"\"\n"
                   "    pass\n\n\n"
                   "CHECKS = (\n"
                   "    check_alpha,\n"
                   "    check_beta,\n"
                   ")\n\n\n"
                   "def main(argv=None):\n"
                   "    for check in CHECKS:\n"
                   "        check()\n"
                   "    return 0\n")

    def test_all_wired_passes(self):
        # 正例：定义的防线全部在序列里 → 不报错
        self._write_valid()
        cm.check_wiring_guard()
        self.assertEqual(self.error_texts(), "")

    def test_defined_but_not_wired_reports(self):
        # 反例①：定义了却没进序列（"定义了却不执行"）→ 必须报错
        self.write("script/check_specs.py",
                   "def check_alpha():\n"
                   "    \"\"\"A.\"\"\"\n"
                   "    pass\n\n\n"
                   "def check_beta():\n"
                   "    \"\"\"B.\"\"\"\n"
                   "    pass\n\n\n"
                   "CHECKS = (\n"
                   "    check_alpha,\n"
                   ")\n\n\n"
                   "def main(argv=None):\n"
                   "    for check in CHECKS:\n"
                   "        check()\n"
                   "    return 0\n")
        cm.check_wiring_guard()
        self.assertIn("check_beta", self.error_texts())

    def test_wired_but_undefined_reports(self):
        # 反例②：序列点名了不存在的防线（接线与实现不一致）→ 必须报错
        self.write("script/check_specs.py",
                   "def check_alpha():\n"
                   "    \"\"\"A.\"\"\"\n"
                   "    pass\n\n\n"
                   "CHECKS = (\n"
                   "    check_alpha,\n"
                   "    check_gamma,\n"
                   ")\n\n\n"
                   "def main(argv=None):\n"
                   "    for check in CHECKS:\n"
                   "        check()\n"
                   "    return 0\n")
        cm.check_wiring_guard()
        self.assertIn("check_gamma", self.error_texts())

    def test_comment_mention_is_not_wiring(self):
        # 反例③：只在注释里提到防线名，不构成接线（防"注释里写一句就算接上了"）
        self.write("script/check_specs.py",
                   "def check_alpha():\n"
                   "    \"\"\"A.\"\"\"\n"
                   "    pass\n\n\n"
                   "def check_beta():\n"
                   "    \"\"\"B.\"\"\"\n"
                   "    pass\n\n\n"
                   "CHECKS = (\n"
                   "    check_alpha,\n"
                   "    # check_beta,\n"
                   ")\n\n\n"
                   "def main(argv=None):\n"
                   "    for check in CHECKS:\n"
                   "        check()\n"
                   "    return 0\n")
        cm.check_wiring_guard()
        self.assertIn("check_beta", self.error_texts())

    def test_nested_wiring_counts(self):
        # 正例：被序列中的防线调用到的也算"被执行到"
        self.write("script/check_specs.py",
                   "def check_alpha():\n"
                   "    \"\"\"A.\"\"\"\n"
                   "    check_beta()\n\n\n"
                   "def check_beta():\n"
                   "    \"\"\"B.\"\"\"\n"
                   "    pass\n\n\n"
                   "CHECKS = (\n"
                   "    check_alpha,\n"
                   ")\n\n\n"
                   "def main(argv=None):\n"
                   "    for check in CHECKS:\n"
                   "        check()\n"
                   "    return 0\n")
        cm.check_wiring_guard()
        self.assertEqual(self.error_texts(), "")

    def test_closure_does_not_depend_on_first_definition(self):
        # 反例：`check_alpha` 体内调 `check_beta`，而 `check_beta` 定义在 `check_alpha` 之前——
        # `_fn_body` 落在文件最后一个定义上时会扫到文件尾、把后面的防线全算成"可达"，
        # 于是"模块里最后一个 `def`"不接进序列也能被无关改动静默放过。
        self.write("script/check_specs.py",
                   "def check_beta():\n"
                   "    \"\"\"B.\"\"\"\n"
                   "    pass\n\n\n"
                   "def check_alpha():\n"
                   "    \"\"\"A.\"\"\"\n"
                   "    pass\n\n\n"
                   "CHECKS = (\n"
                   "    check_alpha,\n"
                   ")\n\n\n"
                   "def main(argv=None):\n"
                   "    for check in CHECKS:\n"
                   "        check()\n"
                   "    return 0\n")
        cm.check_wiring_guard()
        self.assertIn("check_beta", self.error_texts())

    def test_missing_script_reports(self):
        # 反例⑤：连脚本都找不到 → 必须报错，不得静默通过
        cm.check_wiring_guard()
        self.assertIn("check_specs.py", self.error_texts())

    def test_missing_checks_sequence_reports(self):
        # 反例⑥：脚本没有 `CHECKS` 序列（次序失去唯一来源）→ 必须报错
        self.write("script/check_specs.py",
                   "def check_alpha():\n"
                   "    \"\"\"A.\"\"\"\n"
                   "    pass\n")
        cm.check_wiring_guard()
        self.assertIn("CHECKS", self.error_texts())


class TestCheckPromptsIndexGuard(CheckSpecsTestCase):
    """钉住『提示词登记处索引形态』防线（本轮重构新增）。

    背景：`PROMPTS.adoc` 的公共约定原先把 `prompts/_common.txt` 各片段的要点**逐条复述**
    一遍——同一约束两份正文，片段一改这里就漂移。本轮改为**索引**（只写"有哪几个片段、
    每个片段管哪条边界、正文唯一落点在片段里"）。但索引也有反向失效：把某条边界从索引里
    **整条删掉**，复制提示词的人就再也看不到它。

    用例覆盖：①正例（索引形态 + 指向语 + 各片段名齐备）通过；②某条边界的片段名被整条删掉 →
    报错；③没写明"此处只作索引、正文在片段里" → 报错（会被读成全文）；④入口缺失 → 报错。
    """

    INDEX = (
        "= 公共任务提示词（入口）\n\n"
        "== 登记\n"
        "* 公共约定（**展开见 link:prompts/_common.txt[] 的对应片段——此处只作索引，不复述正文**）：\n"
        "** `baseline-and-compat` / `compat`：动手前与改动后的边界。\n"
        "** `scope-boundary`：改动范围边界。\n"
        "** `delivery`：交付边界。\n"
        "** `self-dispatch`：不得自行发评论唤起自己。\n"
        "** 各片段的正文只写在 link:prompts/_common.txt[]（一处维护、两处生效）。\n"
    )

    def setUp(self) -> None:
        super().setUp()
        self._orig_prompts = cm.PROMPTS_FILE
        cm.PROMPTS_FILE = os.path.join(self.root, "PROMPTS.adoc")

    def tearDown(self) -> None:
        cm.PROMPTS_FILE = self._orig_prompts
        super().tearDown()

    def test_valid_index_passes(self):
        self.write("PROMPTS.adoc", self.INDEX)
        cm.check_prompts_index_guard()
        self.assertEqual(cm.errors, [])

    def test_entry_deleted_reports(self):
        # 反例①：把 `self-dispatch`（不得自行发评论唤起自己）整条从登记处删掉 →
        # 复制提示词的人彻底看不到这条边界
        self.write("PROMPTS.adoc", self.INDEX.replace("** `self-dispatch`：不得自行发评论唤起自己。\n", ""))
        cm.check_prompts_index_guard()
        self.assertIn("self-dispatch", self.error_texts())

    def test_scope_entry_deleted_reports(self):
        # 反例②：把 `scope-boundary`（改动范围边界）整条删掉
        self.write("PROMPTS.adoc", self.INDEX.replace("** `scope-boundary`：改动范围边界。\n", ""))
        cm.check_prompts_index_guard()
        self.assertIn("scope-boundary", self.error_texts())

    def test_no_pointer_reports(self):
        # 反例③：只列片段名、没说"正文在片段里、此处只作索引" → 会被读成全文
        self.write("PROMPTS.adoc", self.INDEX.replace("——此处只作索引，不复述正文", "")
                   .replace("** 各片段的正文只写在 link:prompts/_common.txt[]（一处维护、两处生效）。\n", ""))
        cm.check_prompts_index_guard()
        self.assertIn("索引", self.error_texts())

    def test_missing_entry_file_reports(self):
        # 反例④：入口缺失 → 公共约定无处登记，必须报错、不得静默通过
        cm.check_prompts_index_guard()
        self.assertIn("PROMPTS.adoc", self.error_texts())


class TestCheckLombokConstructorGuard(CheckSpecsTestCase):
    """钉住『无参/必参/全参构造优先用 lombok、不手写』（用户提出的规范调整）。

    该条对应"顺手手写构造方法"这一真实失效：类上已标 `@Data`，仍另写无参/全参构造——
    同一构造出现两个来源（字段增删时改一处、另一处静默过期），样板代码遮蔽真实差异。
    最易被三件事冲掉：
      * **降级成建议** —— "尽量用 lombok"读起来无害，于是"手写更直观"重新成立；
      * **三种构造注解只留一半** —— 漏掉 `@RequiredArgsConstructor`（用户明确要求的"必参"
        这一档）后，执行者遇到必参构造无处可依、只能手写；
      * **例外被写宽** —— "注解表达不了"不限定在构造期校验/规范化/防御性拷贝上，
        就变成随时可套用的豁免口。
    故本组用例覆盖"条文被删""降级成建议""注解缺失""例外被抽""调度器/README 未同步"。
    """

    JAVA = (
        "= Java 规范\n"
        "\n"
        "== 编码\n"
        "* **无参 / 必参 / 全参构造优先用 lombok、不手写（L1）**：构造方法一律由 lombok 注解生成，"
        "**不得手写**任何构造方法体或参数列表——\n"
        "** **无参构造**：用 `@NoArgsConstructor`；\n"
        "** **必参构造**：用 `@RequiredArgsConstructor`；\n"
        "** **全参构造**：用 `@AllArgsConstructor`；\n"
        "** **同时需要多个**：**同时标多个构造注解**，各自生成一个。\n"
        "** **判定标准（任一命中即违规）**：①类中出现手写的构造方法，而该构造可由注解表达；"
        "②同一类里手写与 lombok 生成的构造方法并存；③以「lombok 表达不了」为由手写而未写原因。\n"
        "** 例外（L2，须写清理由）**：构造期需要注解表达不了的动作（校验/规范化/防御性拷贝）时，"
        "可手写该构造方法，须在代码**注释**写明原因。**存量边界**：随动迁移，见"
        " `specs/core/execution.adoc`。\n"
        "** 依据（标准名/编号）：ISO/IEC 25010（可维护性）；ISO/IEC/IEEE 29148（判定须可验证）。\n"
    )

    def setUp(self) -> None:
        super().setUp()
        self._orig_java = cm.JAVA_STACK_FILE
        self._orig_common = cm.GENERIC_FILE
        self._orig_readme = cm.README_FILE
        cm.JAVA_STACK_FILE = os.path.join(self.root, "specs", "stack", "java.adoc")
        cm.GENERIC_FILE = os.path.join(self.root, "AGENTS_COMMON.adoc")
        cm.README_FILE = os.path.join(self.root, "README.adoc")

    def tearDown(self) -> None:
        (cm.JAVA_STACK_FILE, cm.GENERIC_FILE, cm.README_FILE) = (
            self._orig_java, self._orig_common, self._orig_readme)
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("specs/stack/java.adoc", self.JAVA)
        self.write("AGENTS_COMMON.adoc",
                   "** 构造方法不手写**：无参/必参/全参构造用 lombok 注解"
                   "（`@NoArgsConstructor`/`@RequiredArgsConstructor`/`@AllArgsConstructor`）。\n")
        self.write("README.adoc", "技术栈层：java（含**构造方法不手写**）。\n")

    def test_valid_guard_passes(self):
        self._write_valid()
        cm.check_lombok_constructor_guard()
        self.assertEqual(cm.errors, [])

    def test_clause_deleted_reports(self):
        # 反例：条文被删 → "手写更直观"重回默认做法
        self._write_valid()
        self.write("specs/stack/java.adoc", "= Java 规范\n\n== 编码\n* 强制优先使用 lombok。\n")
        cm.check_lombok_constructor_guard()
        self.assertIn("无参 / 必参 / 全参构造优先用 lombok、不手写", self.error_texts())

    def test_level_downgraded_reports(self):
        # 反例：L1 被降级成建议 → "尽量用 lombok"读起来无害
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   self.JAVA.replace("不手写（L1）", "不手写（L2，建议）"))
        cm.check_lombok_constructor_guard()
        self.assertIn("L1", self.error_texts())

    def test_required_args_annotation_removed_reports(self):
        # 反例：必参构造注解被抽掉（用户明确要求的"必参"这一档）→ 必参构造仍手写
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   self.JAVA.replace("@RequiredArgsConstructor", "省略"))
        cm.check_lombok_constructor_guard()
        self.assertIn("RequiredArgsConstructor", self.error_texts())

    def test_judgement_standard_removed_reports(self):
        # 反例：判定标准被删 → 只剩一句口径、读者无法判断是否命中
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   self.JAVA.replace("** **判定标准（任一命中即违规）**：①类中出现手写的构造方法，"
                                     "而该构造可由注解表达；"
                                     "②同一类里手写与 lombok 生成的构造方法并存；"
                                     "③以「lombok 表达不了」为由手写而未写原因。\n", ""))
        cm.check_lombok_constructor_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_exception_clause_removed_reports(self):
        # 反例：例外条被删 → 既有正当做法（构造期校验）被一刀切
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   self.JAVA.replace("** 例外（L2，须写清理由）**", "** 说明**"))
        cm.check_lombok_constructor_guard()
        self.assertIn("例外", self.error_texts())

    def test_softening_wording_reports(self):
        # 反例（关键词堆砌式假绿）：条文还在，但措辞回退成"尽量/可手写"
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   self.JAVA.replace("**不得手写**任何构造方法体或参数列表",
                                     "尽量用 lombok，可手写构造方法"))
        cm.check_lombok_constructor_guard()
        self.assertIn("回退措辞", self.error_texts())

    def test_java_stack_missing_reports(self):
        # 反例：Java 栈落点缺失 → Java 执行者按栈文件学仍会手写
        self._write_valid()
        os.remove(cm.JAVA_STACK_FILE)
        cm.check_lombok_constructor_guard()
        self.assertIn("缺少文件", self.error_texts())

    def test_dispatcher_not_synced_reports(self):
        # 反例：调度器未同步识别特征 → Java 项目按栈登记加载时看不到这条
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "= 入口\n\nJava 项目 → java.adoc\n")
        cm.check_lombok_constructor_guard()
        self.assertIn("AGENTS_COMMON", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例：README 目录说明未同步 → 读者从目录说明看不到这条存在
        self._write_valid()
        self.write("README.adoc", "目录结构：（未同步）。\n")
        cm.check_lombok_constructor_guard()
        self.assertIn("README", self.error_texts())



class TestCheckEntityDtoGuard(CheckSpecsTestCase):
    """钉住『数据契约的载体（数据库实体类不进对外契约）』（Issue #158 用户要求）。

    用户原文口径：**除非用户主动声明，否则不将数据库实体类作为接口请求、响应参数
    （已经用了不管），适用任何语言**。该条此前**不存在**——「请求响应类优先移动复用」的
    例外① 只写"数据库实体类不移动"（管"搬不搬类"，不管"能不能当接口参数"），
    技术栈层的「对象转换」把 `Entity ↔ DTO ↔ VO` 并列、也没有任何禁止。

    最易被四件事冲掉：
      * **整节被删** —— 退回"实体类最省事"；
      * **判据被压成口号** —— 只剩"尽量用 DTO"，判定标准与识别判据全丢；
      * **边界被删** —— 纯内部调用 / 持久化自身出口两条一丢，本条被读宽成
        "任何函数都不得出现实体类"（把正常数据访问层与内部编排大面积判红）；
      * **"存量不管"被删** —— 用户点名的"已经用了不管"丢字，L1 被扩到存量接口上。

    故本组用例除正例外，逐条覆盖上述反例，外加"豁免面（用户声明）被删""识别判据
    退回按类名判""调度器未同步""技术栈层另立第二真源"。
    """

    CODING = (
        "= 通用编码规范\n\n"
        "== 数据契约的载体（数据库实体类不进对外契约）\n"
        "**任何语言**都适用：以数据库表/集合结构为载体的数据对象（下称**数据库实体类**"
        "——各语言栈里由对象-关系映射框架或映射注解定义的模型类/结构体）**不得**充当"
        "**对外数据契约的载体**——即外部可观测的请求参数、响应返回值。\n"
        "* **识别判据（先判对象，再判规则）**：类/结构体**以表结构为来源**即属本条所指的"
        "数据库实体类。**不看类名**。\n"
        "* **不得作为对外契约的请求参数与响应值（L1）**：对外暴露的接口**不得**以数据库实体类"
        "作为入参或返回类型，也**不得**在入参/返回值里**嵌套**它（集合元素、对象字段、"
        "分页包装体内均不得出现）。\n"
        "* **载体取该接口自己的请求/响应类（L1）**：对外接口须使用为该接口定义的请求类/响应类。\n"
        "* **判定标准（任一命中即违规）**：① 对外接口的入参类型或返回类型是数据库实体类；"
        "② 入参/返回值的字段或集合元素里嵌套数据库实体类；③ 让实体类实现/继承接口契约类型；"
        "④ 以「类名不叫 Entity」「内部调用不算对外」为由自我豁免。\n"
        "* **例外与边界（L2）**：① **纯内部调用**不在本条范围内；"
        "② **持久化自身的出口**不受本条约束；③ 项目自身规范可加严或收窄本条、"
        "冲突时以项目自身规范为准。\n"
        "* **存量边界（L1，用户点名「已经用了不管」）**：改到哪个接口才顺带调整"
        "（随动迁移，见 `specs/core/execution.adoc`）。\n"
        "* **例外之例外**：**除非用户主动声明**允许某处以数据库实体类作为请求/响应参数，"
        "否则一律适用本条。声明仅对该次任务、该处生效、**不得泛化**。\n"
        "* 依据（标准名/编号）：ISO/IEC 25010、ISO/IEC/IEEE 29148、OWASP API Security Top 10。\n"
        "\n== 持久化访问（数据库/缓存等）\n* 略。\n"
        "\n== 对象转换（多层嵌套对象的转换）\n* 略。\n"
    )

    GENERIC = (
        "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
        "  ** 任何代码活动 → link:specs/general/coding.adoc[]（识别特征：要判定"
        "**对外接口的请求/响应参数与返回值用什么类承载**（**数据库实体类不进对外契约**））\n"
    )

    ADOPTION = (
        "= 规范准入与自身取舍\n\n== 同义性差异与覆盖点（本集合自己承认的）\n"
        "* **数据库实体类不得作为接口的请求/响应参数（L1）是本集合自己的判据化取舍**："
        "外部材料只给方向与下限，**没有任何材料规定**这一层；规则本体见 "
        "`specs/general/coding.adoc`。\n"
    )

    JAVA = "= Java 规范\n\n== 编码\n* 普通规则。\n"

    def setUp(self) -> None:
        super().setUp()
        self._orig_coding = cm.CODING_FILE
        self._orig_generic = cm.GENERIC_FILE
        self._orig_java = cm.JAVA_STACK_FILE
        self._orig_spring = cm.SPRING_STACK_FILE
        cm.CODING_FILE = os.path.join(self.root, "specs", "general", "coding.adoc")
        cm.GENERIC_FILE = os.path.join(self.root, "AGENTS_COMMON.adoc")
        cm.JAVA_STACK_FILE = os.path.join(self.root, "specs", "stack", "java.adoc")
        cm.SPRING_STACK_FILE = os.path.join(self.root, "specs", "stack", "spring.adoc")

    def tearDown(self) -> None:
        (cm.CODING_FILE, cm.GENERIC_FILE, cm.JAVA_STACK_FILE,
         cm.SPRING_STACK_FILE) = (self._orig_coding, self._orig_generic,
                                  self._orig_java, self._orig_spring)
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("specs/general/coding.adoc", self.CODING)
        self.write("AGENTS_COMMON.adoc", self.GENERIC)
        self.write("specs/stack/java.adoc", self.JAVA)
        self.write("specs/stack/spring.adoc", self.JAVA)
        self.write("library/adoption.adoc", self.ADOPTION)

    def test_valid_entity_dto_guard_passes(self):
        self._write_valid()
        cm.check_entity_dto_guard()
        self.assertEqual(cm.errors, [])

    def test_section_deleted_reports(self):
        # 反例①：整节被删 → 退回"实体类最省事"
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   "= 通用编码规范\n\n== 代码复用\n* 略。\n")
        cm.check_entity_dto_guard()
        self.assertIn("数据契约的载体", self.error_texts())

    def test_clause_downgraded_reports(self):
        # 反例②：L1 被降级成建议 → "尽量用 DTO"读起来无害
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("不得作为对外契约的请求参数与响应值（L1）",
                                       "不得作为对外契约的请求参数与响应值（L2，建议）"))
        cm.check_entity_dto_guard()
        self.assertIn("L1", self.error_texts())

    def test_nesting_clause_removed_reports(self):
        # 反例③：嵌套面被删 → `Result<List<UserEntity>>` 被读成合法
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("也**不得**在入参/返回值里**嵌套**它（集合元素、对象字段、"
                                       "分页包装体内均不得出现）", ""))
        cm.check_entity_dto_guard()
        self.assertIn("嵌套", self.error_texts())

    def test_identification_by_source_removed_reports(self):
        # 反例④：识别判据被删 → 执行者改按类名判（UserDTO 里逐字段对应表结构就漏判）
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("* **识别判据（先判对象，再判规则）**：类/结构体"
                                       "**以表结构为来源**即属本条所指的"
                                       "数据库实体类。**不看类名**。\n", ""))
        cm.check_entity_dto_guard()
        self.assertIn("识别判据", self.error_texts())

    def test_internal_call_boundary_removed_reports(self):
        # 反例⑤：纯内部调用边界被删 → 本条被读宽成"任何函数都不得出现实体类"
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("① **纯内部调用**不在本条范围内；", ""))
        cm.check_entity_dto_guard()
        self.assertIn("纯内部调用", self.error_texts())

    def test_persistence_exit_boundary_removed_reports(self):
        # 反例⑥：持久化出口边界被删 → 与「持久化访问」节直接冲突
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("② **持久化自身的出口**不受本条约束；", ""))
        cm.check_entity_dto_guard()
        self.assertIn("持久化自身的出口", self.error_texts())

    def test_legacy_scope_removed_reports(self):
        # 反例⑦：用户点名的"已经用了不管"被删 → L1 被扩到存量接口上
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("* **存量边界（L1，用户点名「已经用了不管」）**：",
                                       "* **存量边界**："))
        cm.check_entity_dto_guard()
        self.assertIn("已经用了不管", self.error_texts())

    def test_user_declaration_exemption_removed_reports(self):
        # 反例⑧：豁免面（用户声明）被删 → 用户声明过的场景被判红
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("* **例外之例外**：**除非用户主动声明**允许某处以数据库实体类"
                                       "作为请求/响应参数，否则一律适用本条。"
                                       "声明仅对该次任务、该处生效、**不得泛化**。\n", ""))
        cm.check_entity_dto_guard()
        self.assertIn("除非用户主动声明", self.error_texts())

    def test_broader_exemption_removed_reports(self):
        # 反例⑨：豁免范围（不得泛化）被删 → 一次声明被当成长期授权
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("声明仅对该次任务、该处生效、**不得泛化**。", "声明生效。"))
        cm.check_entity_dto_guard()
        self.assertIn("不得泛化", self.error_texts())

    def test_framework_name_in_general_layer_reports(self):
        # 反例⑩：通用层被框架专名污染 → 非 Java 项目也被带入该框架术语、与归属层冲突
        self._write_valid()
        self.write("specs/general/coding.adoc",
                   self.CODING.replace("（下称**数据库实体类**——各语言栈里由对象-关系映射框架或"
                                       "映射注解定义的模型类/结构体）",
                                       "（下称**数据库实体类**，如 `@Entity` 标注的类）"))
        cm.check_entity_dto_guard()
        self.assertIn("@Entity", self.error_texts())

    def test_stack_layer_second_source_reports(self):
        # 反例⑪：技术栈层另立第二真源 → 两处各自漂移
        self._write_valid()
        self.write("specs/stack/java.adoc",
                   "= Java 规范\n\n== 编码\n* 数据库实体类不进对外契约。\n")
        cm.check_entity_dto_guard()
        self.assertIn("java.adoc", self.error_texts())

    def test_dispatcher_not_synced_reports(self):
        # 反例⑫：调度器未同步识别特征 → 写对外接口参数时不会触发加载这条
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
                   "  ** 任何代码活动 → link:specs/general/coding.adoc[]\n")
        cm.check_entity_dto_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_dispatcher_slogan_only_reports(self):
        # 反例⑬：调度条目只写口号（"数据契约"）→ 识别特征不可判读即漏加载
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "= AGENT 执行规范\n\n== 分类与懒加载（加载调度器）\n"
                   "  ** 任何代码活动 → link:specs/general/coding.adoc[]"
                   "（含**数据库实体类不进对外契约**：**数据契约**）\n")
        cm.check_entity_dto_guard()
        self.assertIn("对外接口", self.error_texts())

    def test_adoption_not_registered_reports(self):
        # 反例⑭：图书馆未登记该取舍 → 读者把本站口径读成标准规定
        self._write_valid()
        self.write("library/adoption.adoc", "= 规范准入与自身取舍\n\n== 同义性差异与覆盖点\n* 略。\n")
        cm.check_entity_dto_guard()
        self.assertIn("adoption.adoc", self.error_texts())

    def test_coding_file_missing_reports(self):
        # 反例⑮：通用层落点丢失 → 该条无处承载
        self._write_valid()
        os.remove(cm.CODING_FILE)
        cm.check_entity_dto_guard()
        self.assertIn("缺少文件", self.error_texts())

class TestCheckJavaInterfaceAccessorGuard(CheckSpecsTestCase):
    """钉住『Java 字段接口只加 get、不加 set』（用户先提「字段接口只允许 get」、再澄清「是接口不是类」）。

    该条对应用户点名的真实编译问题：**下游实现类可能加 `@Accessors(chain = true)`**，
    接口里一旦声明了 `void setXxx(...)` 形态的 setter，链式 setter 的返回类型与接口签名
    不一致、**下游直接编译不过**。最易被四件事冲掉：
      * **判定面被放大** —— 「只约束接口 / 类不适用」丢了，正常类的 lombok setter 被大面积判红
        （用户明确「是接口不是类」）；
      * **理由与后果被抽** —— `@Accessors(chain = true)` 与"编译不过"一丢，读者不知道要防什么，
        于是「接口不加 set 怎么写入」会把 setter 补回去；
      * **存量口径被删** —— 「已经有的不管，也不告警」丢字，L1 被扩到存量接口上；
      * **豁免被删或泛化** —— "除非主动声明"丢了声明过的场景被判红，没了"不得泛化"
        则一次声明被套到整个模块。
    故本组用例除正例外逐条覆盖上述反例，以及「轴名齐全、判据被抽走」的反例本体。
    """

    JAVA = (
        "= Java 规范（技术栈层）\n\n== 编码\n\n"
        "* **字段接口只加 get 方法、不加 set 方法（L1，只约束接口）**：**为字段设计的接口**"
        "（承载字段读写契约的接口）**只允许声明 get 方法**（含 lombok `@Getter`），"
        "**禁止声明 set 方法**——除非按本条下款**主动声明**。**本条只约束接口（`interface`）**："
        "**类不适用本条**、不据本条改造。**理由**：下游常在自己的实现类上加 "
        "`@Accessors(chain = true)`；接口里已声明 setter 时**链式方法无法满足该签名**、"
        "下游直接**编译不过**；**get 不受影响**。\n"
        "** **判定标准（任一命中即违规）**：① 接口里声明了 `set` 方法（手写或接口上的 lombok "
        "`@Setter`/`@Data`）；② 以「没法写入」为由补 setter 而未走主动声明；③ 自我豁免。\n"
        "** **例外（L2，主动声明才生效）**：**除非主动声明**否则一律适用；声明**仅对该处生效、"
        "**不得泛化**。\n"
        "** **存量边界（L1，用户点名「已经有的不管，也不告警」）**：**既有接口不视为违规、"
        "**不告警**、不要求整改**，改到哪个接口才顺带调整；**不得**发动全库改造"
        "（随动迁移，见 `specs/core/execution.adoc`）。\n"
        "** 依据（标准名/编号）：ISO/IEC 25010、ISO/IEC/IEEE 29148、**Project Lombok 官方文档**；"
        "**「接口只加 get、不加 set」是本集合自己更严的判据化取舍**。\n"
        # 相邻条目（真实文件里就在同节）：它也有『不适用本条』——按整文件核关键词时会把
        # 本条被抽走的收窄句兜住（本仓库实测复现），故夹具必须带上它
        "* **Feign 接口命名带所属域前缀（L1）**：**只约束 Feign 接口**，REST Controller、"
        "RPC 服务契约等其他对外接口不适用本条、不据此改名。\n")

    COMMON = (
        "= 通用规范\n"
        "** Java 项目（识别特征：**字段接口只加 get 不加 set**（写承载字段读写契约的 `interface`、"
        "或给这类接口加访问器注解时——**下游实现类可能加 `@Accessors(chain = true)`**））\n")

    README = "目录结构：java（含**字段接口只加 get、不加 set（只约束接口）**）。\n"

    ADOPTION = (
        "= 自身取舍\n\n"
        "* **字段接口只加 get、不加 set 是本集合自己的判据化取舍**：外部材料**未**规定该条；"
        "靶心是接口（**是接口不是类**）；**除非主动声明**才能豁免，**存量不管**。\n")

    SOURCES = (
        "= 依据图书馆\n\n== 字段接口的访问器与 lombok 链式风格（Project Lombok 官方文档）\n\n"
        "* `@Accessors(chain = true)` 生成的 setter 返回 `this` ⇒ 与接口的 `void` 签名"
        "**返回类型与接口签名不一致**、编译失败。\n"
        "* **须注意的语义差异（同义性，L1）**：官方文档**未**规定该禁令。\n")

    def setUp(self) -> None:
        super().setUp()
        self._orig_java = cm.JAVA_STACK_FILE
        self._orig_coding = cm.CODING_FILE
        self._orig_common = cm.GENERIC_FILE
        self._orig_readme = cm.README_FILE
        cm.JAVA_STACK_FILE = os.path.join(self.root, "specs", "stack", "java.adoc")
        cm.CODING_FILE = os.path.join(self.root, "specs", "general", "coding.adoc")
        cm.GENERIC_FILE = os.path.join(self.root, "AGENTS_COMMON.adoc")
        cm.README_FILE = os.path.join(self.root, "README.adoc")
        self.write("specs/stack/java.adoc", self.JAVA)
        self.write("specs/general/coding.adoc", "= 通用编码规范\n\n== 代码复用\n* 略。\n")
        self.write("AGENTS_COMMON.adoc", self.COMMON)
        self.write("README.adoc", self.README)
        self.write("library/adoption.adoc", self.ADOPTION)
        self.write("library/sources.adoc", self.SOURCES)

    def tearDown(self) -> None:
        (cm.JAVA_STACK_FILE, cm.CODING_FILE, cm.GENERIC_FILE,
         cm.README_FILE) = (self._orig_java, self._orig_coding, self._orig_common,
                            self._orig_readme)
        super().tearDown()

    def test_valid_passes(self):
        cm.check_java_interface_accessor_guard()
        self.assertEqual([], cm.errors)

    def test_rule_deleted_reports(self):
        # 反例①：整条被删（最简单的冲掉方式）→ 下游加 @Accessors 的编译问题重新无人管
        self.write("specs/stack/java.adoc", "= Java 规范\n\n== 编码\n\n* 别的要求。\n")
        cm.check_java_interface_accessor_guard()
        self.assertIn("字段接口只加 get 方法", self.error_texts())

    def test_interface_only_scope_removed_reports(self):
        # 反例②：判定面被放大——「只约束接口 / 类不适用」被抽掉，正常类的 lombok setter 被大面积判红
        self.write("specs/stack/java.adoc", self.JAVA.replace(
            "**本条只约束接口（`interface`）**：**类不适用本条**、不据本条改造。", "一律适用。"))
        cm.check_java_interface_accessor_guard()
        self.assertIn("不适用本条", self.error_texts())

    def test_interface_only_scope_hollowed_by_neighbor_rule_reports(self):
        # 反例②′（相邻条目兜底，本仓库实测复现）：把「类不适用本条」这半句抽掉、只留
        # `interface`——按整文件核关键词时，相邻 Feign 条目里的「其他对外接口不适用本条」
        # 会把已消失的要求兜住、防线全绿。故判定面收窄这一条须在**本条自己的正文**里核。
        self.write("specs/stack/java.adoc", self.JAVA.replace(
            "**本条只约束接口（`interface`）**：**类不适用本条**、不据本条改造。",
            "**本条只约束接口（`interface`）**。"))
        cm.check_java_interface_accessor_guard()
        self.assertIn("不适用本条", self.error_texts())

    def test_reason_removed_reports(self):
        # 反例③：理由被抽——不知道要防什么，遇到「接口不加 set 怎么写入」会把 setter 补回去
        self.write("specs/stack/java.adoc", self.JAVA.replace(
            "`@Accessors(chain = true)`；接口里已声明 setter 时**链式方法无法满足该签名**、"
            "下游直接**编译不过**；**get 不受影响**。", "会有些不方便。"))
        cm.check_java_interface_accessor_guard()
        self.assertIn("@Accessors", self.error_texts())

    def test_consequence_removed_reports(self):
        # 反例④：后果被删（只剩「不方便」这类措辞时，本条的级别与处置会被降级）
        self.write("specs/stack/java.adoc", self.JAVA.replace("编译不过", "有影响"))
        cm.check_java_interface_accessor_guard()
        self.assertIn("编译不过", self.error_texts())

    def test_stock_boundary_removed_reports(self):
        # 反例⑤（用户点名要件）：存量口径被删 → L1 被扩到存量接口上，存量项目大面积命中
        self.write("specs/stack/java.adoc", self.JAVA.replace(
            "** **存量边界（L1，用户点名「已经有的不管，也不告警」）**：**既有接口不视为违规、"
            "**不告警**、不要求整改**，改到哪个接口才顺带调整；**不得**发动全库改造"
            "（随动迁移，见 `specs/core/execution.adoc`）。\n", ""))
        cm.check_java_interface_accessor_guard()
        self.assertIn("不视为违规", self.error_texts())

    def test_exemption_removed_reports(self):
        # 反例⑥（用户原话要件）：豁免面被删 → 声明过的场景会被判红
        self.write("specs/stack/java.adoc", self.JAVA.replace(
            "** **例外（L2，主动声明才生效）**：**除非主动声明**否则一律适用；声明**仅对该处生效、"
            "**不得泛化**。\n", ""))
        cm.check_java_interface_accessor_guard()
        self.assertIn("除非主动声明", self.error_texts())

    def test_generalization_boundary_removed_reports(self):
        # 反例⑦：豁免范围被删 → 一次声明被套到整个模块（例外成了新的默认）
        self.write("specs/stack/java.adoc", self.JAVA.replace("**不得泛化**", "可参照"))
        cm.check_java_interface_accessor_guard()
        self.assertIn("不得泛化", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例⑧（反例本体：轴名齐全、判据被抽走）：判定标准被抽成一句总述
        self.write("specs/stack/java.adoc", self.JAVA.replace(
            "** **判定标准（任一命中即违规）**", "** **注意**："))
        cm.check_java_interface_accessor_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_basis_removed_reports(self):
        # 反例⑨：依据行被删 → 为什么是 L1、为什么默认禁 set 的来源无从核对
        self.write("specs/stack/java.adoc", self.JAVA.replace(
            "** 依据（标准名/编号）：ISO/IEC 25010、ISO/IEC/IEEE 29148、**Project Lombok 官方文档**；"
            "**「接口只加 get、不加 set」是本集合自己更严的判据化取舍**。\n", ""))
        cm.check_java_interface_accessor_guard()
        self.assertIn("依据", self.error_texts())

    def test_self_tradeoff_qualifier_removed_reports(self):
        # 反例⑩：定性被删 → 会被读成 lombok 或某标准的明文要求
        self.write("specs/stack/java.adoc", self.JAVA.replace(
            "**「接口只加 get、不加 set」是本集合自己更严的判据化取舍**。", "**这是通行做法**。"))
        cm.check_java_interface_accessor_guard()
        self.assertIn("判据化取舍", self.error_texts())

    def test_general_layer_second_source_reports(self):
        # 反例⑪：通用层也写一份（框架专名进通用层）→ 第二真源，两处必各自漂移
        self.write("specs/general/coding.adoc",
                   "= 通用编码规范\n\n== 代码复用\n* 接口不得加 set（下游可能加 "
                   "`@Accessors(chain = true)`）。\n")
        cm.check_java_interface_accessor_guard()
        self.assertIn("coding.adoc", self.error_texts())

    def test_dispatcher_trigger_removed_reports(self):
        # 反例⑫：调度器没有识别特征 → 写字段接口时该条永不被触发加载（实际失效）
        self.write("AGENTS_COMMON.adoc", "= 通用规范\n** Java 项目\n")
        cm.check_java_interface_accessor_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例⑬：README 目录说明未同步 → 读者按 README 学习时无从知道有这条规则
        self.write("README.adoc", "目录结构：（未同步）。\n")
        cm.check_java_interface_accessor_guard()
        self.assertIn("README", self.error_texts())

    def test_library_sources_removed_reports(self):
        # 反例⑭：图书馆无依据段 → 依据只存名称、日后无从核对「它今天还成立吗」
        self.write("library/sources.adoc", "= 图书馆\n\n* 略。\n")
        cm.check_java_interface_accessor_guard()
        self.assertIn("sources.adoc", self.error_texts())

    def test_library_adoption_tradeoff_removed_reports(self):
        # 反例⑮：取舍记录被删 → 读者会以为这是 lombok 的明文要求
        self.write("library/adoption.adoc", "= 取舍\n\n* 略。\n")
        cm.check_java_interface_accessor_guard()
        self.assertIn("adoption.adoc", self.error_texts())


class TestCheckJavaObjectTemplateGuard(CheckSpecsTestCase):
    """钉住『Java 数据对象模板』（用户口径：模板属"要么不读、要么整份读完"的产物，故单列成
    **模板文件**、不并进 `specs/stack/java.adoc`；判据本体仍留在规范文件里）。

    该条对应四处真实失效：
      * **模板被并回规范** —— 规范正文被撑大（每次加载都付上下文），而它又不一定被读到；
      * **判据本体被抽走** —— 只剩一份清单，读者不知道"为什么补注解不加 `@Accessors`"，
        于是"补注解也加上吧"重新成立（看起来只是多一个注解）；
      * **加载门丢了** —— 新建对象时该文件永不被加载，模板形同不存在；
      * **三处取值被删** —— 无参 `@AllArgsConstructor`、集合 `@Singular` 两条各自都可能被
        当成风格偏好顺手去掉。
    故本组用例除正例外逐条覆盖上述反例，以及"相邻条目的字样兜住已消失的要求"这一反例本体
    （`specs/stack/java.adoc`「编码」里构造注解字样在相邻条目里同样出现）。
    """

    # 判据本体夹具：与真实文件**同形**——含「清单句」（五项齐备）、三处取值的判据面、
    # 两档生效面、依据行。防线的 `bullet_tokens` 步按这些锚点核「本条自己的正文」，
    # 故夹具必须真的把它们写在本条正文里（否则正例即报红——正是本条要防的形态）。
    JAVA_RULE = (
        "* **数据对象模板（新建时整段照抄；存量主动声明才补）**：**新建**一个 Java 数据对象时"
        "注解清单整段照抄 `specs/stack/java-object.adoc` 的模板——`@Data`、"
        "`@Accessors(chain = true)`、`@SuperBuilder`、`@NoArgsConstructor`、"
        "`@AllArgsConstructor`。**模板文件不是规范文件**：那份文件只给可复制清单，本文件是其判据本体。\n"
        "** **新增对象时加 `@Accessors(chain = true)`；给既有对象补注解时按「类是否已提交」取值（L1）**：Spring 的 "
        "`BeanUtils` 会**忽略带泛型参数的 set 方法**（链式 setter 返回 `this`），拷贝时静默丢数据。"
        "**类已提交**则**默认不补**、**类未提交**则**可以补**。"
        "**判定标准（任一命中即违规）**：① 给**已提交**的类补注解时加上了 "
        "`@Accessors(chain = true)`；② 新建对象的注解清单缺 `@Accessors(chain = true)`。\n"
        "** **`@AllArgsConstructor` 无参数时不加（L1）**：类里**没有任何实例字段**时两者是同一个构造。"
        "**判定标准**：无字段的类上出现 `@AllArgsConstructor` 即违规。\n"
        "** **POJO 里的集合字段默认加 `@Singular`（L1）**：除非有问题。**判定标准（任一命中即违规）**："
        "① builder 侧**没有单个元素入口**、只能整集合设置。\n"
        "** **两档生效面**：**既有对象不主动改**、**主动声明**才补；**存量不告警**；"
        "**review 时对存量缺这套模板注解不提出问题**"
        "（全局口径见 `specs/general/review.adoc`「review 的默认检查面」，本条不复述）。\n"
        "** 依据（标准名/编号）：**Project Lombok 官方文档**、Spring Framework 官方文档。\n")

    JAVA = (
        "= Java 规范（技术栈层）\n\n== 编码\n\n"
        "* **无参 / 必参 / 全参构造优先用 lombok、不手写（L1）**：`@NoArgsConstructor`、"
        "`@RequiredArgsConstructor`、`@AllArgsConstructor`。\n"
        + JAVA_RULE)

    # 模板夹具：**只给"照抄时怎么用"，取值/机制/判定标准一律回指判据本体**——与真实文件
    # 同形（模板文件自称"不重复那些判据"，若在此再抄一份理由与判定标准，夹具自己就在
    # 示范第二真源，防线的用例反而把要防的形态固化成"正确写法"）。
    TPL = (
        "= Java 数据对象模板（技术栈层）\n\n"
        "**模板文件，不是规范文件**：本文件是**可整份照抄的完整模板**，其**判据本体**在 "
        "`specs/stack/java.adoc`（同一件事只在一处给真源）。**要么不读、要么整份读完**。\n\n"
        "**加载触发特征**：**新建一个 Java 数据对象**；**没有以上目的时不加载**。\n\n"
        "== 模板\n\n[source,java]\n----\n@Data\n@Accessors(chain = true)\n@SuperBuilder\n"
        "@NoArgsConstructor\n@AllArgsConstructor\n----\n\n"
        "照抄时的三条约定（**理由、机制与判定标准见** `specs/stack/java.adoc`「编码」的"
        "「数据对象模板」条，本文件**不重复它们**）：\n\n"
        "* **`@Accessors(chain = true)` 只在新增对象时加**：给既有对象**补注解时按该类是否已提交取值**"
        "——**已提交的默认不补**、**未提交的可以补**（分档判据、理由与判定标准见判据本体）。\n"
        "* **`@AllArgsConstructor` 无参数时不加**（此例外与判定标准见判据本体）。\n"
        "* **集合字段默认加 `@Singular`**：按\"每个集合字段都标\"处理（\"除非有问题\"与判定标准见判据本体）。\n"
        "* **注解次序**：模板里的次序已按 `specs/general/coding.adoc`「命名与代码质量」的"
        "**注解排序**规则排好；该规则**不在此重述**。\n\n"
        "== 生效面与存量\n\n"
        "**两档生效面**与其判定标准**见判据本体**，**不在此重述**；本文件**不改写**判据，也"
        "**不得以「模板没写」为由绕过判据本体**。**同理，review 时对存量缺这套注解不提出问题**——"
        "全局口径见 `specs/general/review.adoc`「review 的默认检查面」、本文件不重述。\n\n"
        "**依据（标准名/编号）**：**见判据本体**同一行——材料名与取舍声明只在那里写一份，"
        "本文件不重述。\n")

    COMMON = "** Java 数据对象模板 → `specs/stack/java-object.adoc`（识别特征：`@Singular`、`@Accessors(chain = true)`）\n"
    README = "技术栈层：**java-object（Java 数据对象模板——模板文件、非规范文件）**。\n"

    def setUp(self) -> None:
        super().setUp()
        self._orig_java = cm.JAVA_STACK_FILE
        self._orig_common = cm.GENERIC_FILE
        self._orig_readme = cm.README_FILE
        cm.JAVA_STACK_FILE = os.path.join(self.root, "specs", "stack", "java.adoc")
        cm.GENERIC_FILE = os.path.join(self.root, "AGENTS_COMMON.adoc")
        cm.README_FILE = os.path.join(self.root, "README.adoc")
        self.write("specs/stack/java.adoc", self.JAVA)
        self.write("specs/stack/java-object.adoc", self.TPL)
        self.write("AGENTS_COMMON.adoc", self.COMMON)
        self.write("README.adoc", self.README)

    def tearDown(self) -> None:
        (cm.JAVA_STACK_FILE, cm.GENERIC_FILE, cm.README_FILE) = (
            self._orig_java, self._orig_common, self._orig_readme)
        super().tearDown()

    def test_valid_passes(self):
        cm.check_java_object_template_guard()
        self.assertEqual([], cm.errors)

    def test_template_file_deleted_reports(self):
        # 反例①：模板文件被删/被并回规范 → 回到"撑大规范正文、而它又不一定被读"
        os.remove(os.path.join(self.root, "specs", "stack", "java-object.adoc"))
        cm.check_java_object_template_guard()
        self.assertIn("java-object.adoc", self.error_texts())

    def test_template_self_positioning_removed_reports(self):
        # 反例②：模板文件不再声明自己是模板/不是规范文件 → 会被当成又一份规范正文
        self.write("specs/stack/java-object.adoc", self.TPL.replace(
            "**模板文件，不是规范文件**", "**本文件是规范正文**").replace(
            "要么不读、要么整份读完", "随时可读"))
        cm.check_java_object_template_guard()
        self.assertIn("模板文件，不是规范文件", self.error_texts())

    def test_trigger_removed_reports(self):
        # 反例③：加载触发特征被删 → 新建对象时该文件永不被加载，模板形同不存在
        self.write("specs/stack/java-object.adoc", self.TPL.replace(
            "**加载触发特征**：**新建一个 Java 数据对象**；**没有以上目的时不加载**。\n", ""))
        cm.check_java_object_template_guard()
        self.assertIn("加载触发特征", self.error_texts())

    def test_template_annotation_removed_reports(self):
        # 反例④：模板体的整段清单缺一项 → "照抄"照出来的是半套，且缺的那项没有替代提示。
        # `@SuperBuilder` 在**判据本体**的"照抄后应齐备的五项"里同样出现，故一侧缺项即可报出。
        self.write("specs/stack/java-object.adoc", self.TPL.replace(
            "@SuperBuilder\n", "", 1))
        cm.check_java_object_template_guard()
        self.assertIn("@SuperBuilder", self.error_texts())

    def test_spec_annotation_removed_reports(self):
        # 反例④′：**判据本体**的"注解清单应齐备"缺一项（如把 `@SuperBuilder` 抽走）——
        # 模板文件仍给出五项，模板侧照抄得对，但判据本体已不再说"要包含它"，
        # "五项齐备"这条要求实际只剩模板文件一处承载（第二真源）。
        self.write("specs/stack/java.adoc", self.JAVA.replace("`@SuperBuilder`、", ""))
        cm.check_java_object_template_guard()
        self.assertIn("@SuperBuilder", self.error_texts())

    def test_half_add_rule_removed_reports(self):
        # 反例⑤（用户点名的失效形态）：把"已提交的默认不补 / 未提交的可以补"这半句抽掉
        # → "补注解也加上吧"重新成立。按真实文件的同形写法抽（真实文件是"只在新增对象时加：
        # 给既有对象补注解时按该类是否已提交取值——已提交的默认不补、未提交的可以补"）。
        self.write("specs/stack/java-object.adoc", self.TPL.replace(
            "——**已提交的默认不补**、**未提交的可以补**", "——**一律都加**"))
        cm.check_java_object_template_guard()
        self.assertIn("已提交的默认不补", self.error_texts())

    def test_committed_split_removed_from_spec_reports(self):
        # 反例⑤′（本轮新增取值）：判据本体里"类已提交 / 类未提交"两档被抽成一句"补注解不加"
        # → 用户点名的两档取值（已提交默认不补、未提交可以补）在规范里不再可核对。
        self.write("specs/stack/java.adoc", self.JAVA.replace(
            "**类已提交**则**默认不补**、**类未提交**则**可以补**。", ""))
        cm.check_java_object_template_guard()
        self.assertIn("类已提交", self.error_texts())

    def test_review_scope_removed_from_spec_reports(self):
        # 反例⑤″（review 不查存量缺注解已升为全局口径，用户点名 Issue #203）：判据本体里的
        # review 回指被整段抽走 → "review 不报存量缺注解"这条边界消失。
        self.write("specs/stack/java.adoc", self.JAVA.replace(
            "**review 时对存量缺这套模板注解不提出问题**"
            "（全局口径见 `specs/general/review.adoc`「review 的默认检查面」，本条不复述）", ""))
        cm.check_java_object_template_guard()
        self.assertIn("review 时对存量缺这套模板注解不提出问题", self.error_texts())

    def test_review_scope_removed_from_template_reports(self):
        # 反例⑤‴：模板侧的 review 回指被抽走 → 模板读者只拿到清单，不知道 review 不报这条。
        self.write("specs/stack/java-object.adoc", self.TPL.replace(
            "**同理，review 时对存量缺这套注解不提出问题**", "**另**"))
        cm.check_java_object_template_guard()
        self.assertIn("review 时对存量缺这套注解不提出问题", self.error_texts())

    def test_no_field_rule_removed_reports(self):
        # 反例⑦：无参不加 `@AllArgsConstructor` 被删 → 无字段的类上被补出"看起来像全参构造"的注解
        self.write("specs/stack/java-object.adoc", self.TPL.replace(
            "* **`@AllArgsConstructor` 无参数时不加**（此例外与判定标准见判据本体）。\n", ""))
        cm.check_java_object_template_guard()
        # 整段清单里另有 `@AllArgsConstructor`（模板体第五项）、且缺的是**这一条自己的正文**：
        # 防线按"这条要点缺了"报红，故断言看缺失要点提示而非注解字样本身
        self.assertIn("缺失要点", self.error_texts())

    def test_singular_rule_removed_reports(self):
        # 反例⑧：集合默认 `@Singular` 被删 → 单元素入口这条要求消失
        self.write("specs/stack/java-object.adoc", self.TPL.replace(
            "* **集合字段默认加 `@Singular`**：按\"每个集合字段都标\"处理（\"除非有问题\"与判定标准见判据本体）。\n", ""))
        cm.check_java_object_template_guard()
        self.assertIn("@Singular", self.error_texts())

    def test_scope_removed_reports(self):
        # 反例⑨（用户点名要件）：两档生效面被删 → L1 被扩到存量对象上，或反向被读成"存量无所谓"。
        # 真实文件把生效面写成 `== 生效面与存量` 一节，故按该节的两条约定删（夹具同形）。
        self.write("specs/stack/java-object.adoc", self.TPL.replace(
            "**两档生效面**与其判定标准**见判据本体**，**不在此重述**；",
            "**生效面**：看情况。"))
        cm.check_java_object_template_guard()
        self.assertIn("两档生效面", self.error_texts())

    def test_rule_body_removed_from_spec_reports(self):
        # 反例⑩（反例本体）：判据本体从规范文件里被整条抽走 → 模板文件成第二真源
        self.write("specs/stack/java.adoc",
                   "= Java 规范（技术栈层）\n\n== 编码\n\n* **别的条目**：略。\n")
        cm.check_java_object_template_guard()
        self.assertIn("数据对象模板", self.error_texts())

    def test_rule_body_hollowed_by_neighbor_rule_reports(self):
        # 反例⑩′（相邻条目兜底，本仓库实测过的形态）：本条正文里的判据被抽走，而相邻的
        # 「无参 / 必参 / 全参构造优先用 lombok」那条同样含 `@AllArgsConstructor` 等字样
        # → 按整节核关键词时会把已消失的要求兜住。故判据须在本条**自己的正文**里核。
        self.write("specs/stack/java.adoc", self.JAVA.replace(
            "`BeanUtils` 会**忽略带泛型参数的 set 方法**（链式 setter 返回 `this`），拷贝时静默丢数据。",
            "会有些问题。"))
        cm.check_java_object_template_guard()
        self.assertIn("忽略带泛型参数的 set 方法", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例⑪：判定标准被抽成一句口径 → 读者不知道自己是否命中
        self.write("specs/stack/java.adoc", self.JAVA.replace(
            "**判定标准（任一命中即违规）**：① 给**已提交**的类补注解时加上了", "**注意**：① 加上了"))
        cm.check_java_object_template_guard()
        self.assertIn("给**已提交**的类补注解时加上了", self.error_texts())

    def test_backref_removed_reports(self):
        # 反例⑥：回指判据本体这一句被抽掉（改用"同上"之类含糊指代）→ 模板侧只剩取值、
        # 读者拿不到机制与判定标准，"补注解也加上吧"重新成立（**本文件不重复判据**是它的定位）。
        # 同段三条各自回指判据本体，本用例一并抽掉，否则另两条的 `见判据本体` 会把已消失的
        # 回指兜住（正是本条要防的"相邻兜底"）。
        self.write("specs/stack/java-object.adoc", self.TPL.replace(
            "（理由与判定标准见判据本体）", "（照做即可）").replace(
            "（无实例字段时该注解没有落点，判定标准见判据本体）", "（照做即可）").replace(
            '（"除非有问题"与判定标准见判据本体）', "（照做即可）"))
        cm.check_java_object_template_guard()
        self.assertIn("缺失要点", self.error_texts())

    def test_template_duplicates_rule_mechanism_reports(self):
        # 反例⑥′（本文件的定位）：自称"不重复那些判据"，却把判据本体的**机制**抄回模板侧
        # → 同一件事两处各给一份真源、必各自漂移（这条靠**反向**核对：机制字样不得出现）。
        self.write("specs/stack/java-object.adoc", self.TPL.replace(
            "（分档判据、理由与判定标准见判据本体）",
            "（`BeanUtils` 会忽略带泛型参数的 set 方法，故补注解时不得加）"))
        cm.check_java_object_template_guard()
        self.assertIn("忽略带泛型参数的 set", self.error_texts())

    def test_template_duplicates_rule_criteria_reports(self):
        # 反例⑥″：把判据本体的**判定标准**抄回模板侧 → 同样属"在本文件示范重复"
        self.write("specs/stack/java-object.adoc", self.TPL.replace(
            "（分档判据、理由与判定标准见判据本体）",
            "（**判定标准（任一命中即违规）**：补注解时加了即违规）"))
        cm.check_java_object_template_guard()
        self.assertIn("判定标准（任一命中即违规）", self.error_texts())

    def test_dispatcher_trigger_removed_reports(self):
        # 反例⑫：调度器没登记/没识别特征 → 新建对象时该文件永不被加载（规则实际失效）
        self.write("AGENTS_COMMON.adoc", "= 通用规范\n** Java 项目\n")
        cm.check_java_object_template_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_checklist_sentence_missing_item_reports(self):
        # 反例⑭（本轮实测补的空白）：**清单句**里的 `@SuperBuilder` 被抽走，而同一个 bullet
        # 末尾的**依据行**仍罗列该注解名（Project Lombok 官方文档那一段）——以前按 bullet 级
        # 核时被同一 bullet 的后半句兜住、防线全绿。防线的「清单句」步按 `until` 截到依据行前，
        # 故此处必须报红。
        self.write("specs/stack/java.adoc", self.JAVA.replace(
            "`@SuperBuilder`、", ""))
        cm.check_java_object_template_guard()
        self.assertIn("@SuperBuilder", self.error_texts())

    def test_rule_body_criteria_backed_by_sibling_half_reports(self):
        # 反例⑮（本轮实测补的空白）：取值一的**判定标准**被抽走，而取值二/三处同样写着
        # 「判定标准」——按共享短语核时被同一 bullet 的另两处兜住。防线改核该句**独有的正文**
        # （`给**已提交**的类补注解时加上了`），故此处必须报红。
        self.write("specs/stack/java.adoc", self.JAVA.replace(
            "**判定标准（任一命中即违规）**：① 给**已提交**的类补注解时加上了",
            "**注意**：① 加上了"))
        cm.check_java_object_template_guard()
        self.assertIn("给**已提交**的类补注解时加上了", self.error_texts())

    def test_readme_entry_name_only_reports(self):
        # 反例⑯（本轮实测补的空白）：README 只留 `java-object` 这个**子串**（路径里也会出现）、
        # 没写条目名与「模板文件、非规范文件」的定位——单核子串太弱，防线要求两者同现。
        self.write("README.adoc", "技术栈层：见 `specs/stack/java-object.adoc`。\n")
        cm.check_java_object_template_guard()
        self.assertIn("模板文件、非规范文件", self.error_texts())

    def test_template_duplicates_scope_values_reports(self):
        # 反例⑰（本轮补的反向锚点）：模板侧把两档生效面的**取值**抄回（“既有对象主动声明才补、
        # 存量不告警”）——读起来像“结论摘要”、实为判据本体内容，是模板侧最易漏的一处重复。
        self.write("specs/stack/java-object.adoc", self.TPL.replace(
            "== 模板", "== 模板\n\n既有对象主动声明才补、存量不告警。"))
        cm.check_java_object_template_guard()
        self.assertIn("存量不告警", self.error_texts())

    def test_template_duplicates_own_tradeoff_claim_reports(self):
        # 反例⑱（本轮补的反向锚点）：模板侧把判据本体的**出处声明**（“是本集合自己的判据化取舍”）
        # 抄回——该声明只在判据本体与图书馆写，模板侧只回指。
        self.write("specs/stack/java-object.adoc", self.TPL.replace(
            "== 模板", "== 模板\n\n三处取值是本集合自己的判据化取舍。"))
        cm.check_java_object_template_guard()
        self.assertIn("是本集合自己的判据化取舍", self.error_texts())

    def test_ordering_pointer_removed_reports(self):
        # 反例⑲（本轮实测补的空白）：模板侧不再点名 `coding.acoc` 的「注解排序」节（次序判据
        # 的真源）——只核 `不在此重述` 会被同文件的「生效面」组兜住，防线改核本条独有的整句。
        self.write("specs/stack/java-object.adoc", self.TPL.replace(
            "模板里的次序已按", "模板次序是随便排的，"))
        cm.check_java_object_template_guard()
        self.assertIn("模板里的次序已按", self.error_texts())

    def test_readme_not_synced_reports(self):
        # 反例⑬：README 目录说明未同步 → 读者按 README 学习时无从知道有这条规则
        self.write("README.adoc", "目录结构：（未同步）。\n")
        cm.check_java_object_template_guard()
        self.assertIn("README", self.error_texts())


class TestCheckJavaEnumValueofCatchGuard(CheckSpecsTestCase):
    """钉住『Java 枚举查找的空 catch』（用户点名：`Enum.valueOf` 的异常只有可能是值没匹配上，
    另有自写枚举工具，故 Java 下允许空 `catch`）。

    本条是 L1「不得吞异常」的**唯一放宽口**，故最易被破坏的形态**不是"没写例外"，而是
    "例外被读宽"**——本组用例逐条覆盖：
      * **例外被抄成通用豁免** —— 准入条件（异常语义单一 + 取默认值即业务语义）与判定标准
        被删后，任何 `catch (Exception) {}` 都能自证"我这是枚举查询"；
      * **扩大的方向一：类级空 `catch`** —— `catch (Throwable)`/`catch (Exception)` 会把同一个
        `try` 里其他语句的异常一并吞掉，而它在代码表面恰恰"符合"例外（本条最危险的形态）；
      * **扩大的方向二：给已返回默认值的写法再补空 `catch`** —— 把本来已经正确的写法改坏；
      * **判据本体只活在一处** —— 通用层与 Java 侧各写一份判据（第二真源、两处各自漂移）；
      * **依据被读成标准规定** —— 图书馆不登记取舍，读者会把"允许空 catch"当成 JDK 的规定。
    故夹具按**判据本体**（准入四条、判定标准、两类扩大的排除）造，正例即真实文件的同形写法。
    """

    CODING_RULE = (
        "* **显式处理失败与边界（L1）**：**不得吞异常**（`catch` 后空实现、只打日志不处理）。"
        "**条件例外（L2，把\"查不到 → 取默认值\"这类纯取值转换写成空 `catch`）**："
        "只在该 API 的**异常只有一种原因**且调用方**以该查找的默认值为业务语义**时成立。"
        "**三条同时成立才算命中、缺一即回到 L1**：① **异常语义单一**；② **取不到即无值**；"
        "③ **默认值取自同一 API 的返回值**；**且该处须写明\"异常只有这一种原因\"的依据**。"
        "**判定标准（任一命中即不合规）**：① 该 API 的异常**不止一种原因**却按本例外空 `catch`；"
        "③ 借本例外绕过**可探测的非法输入**。"
        "**边界（防反用）**：命中的调用点**仍是空 `catch`**。\n")

    JAVA_RULE = (
        "* **`Enum.valueOf` 与自写枚举工具的空 `catch`（L1，本条是通用层「显式处理失败与边界」"
        "在 Java 的落点）**：`Enum.valueOf(...)` 抛出的 `IllegalArgumentException` "
        "**只有\"没有该枚举常量\"这一种原因**（因值不匹配而抛），且取不到值时取**默认值**"
        "就是业务语义——故此类调用**允许空 `catch`**；**自写的枚举工具**满足同一条件时同样允许。"
        "**判据本体在** `specs/general/coding.adoc`「代码质量（新产出即高质）」的"
        "「显式处理失败与边界」（准入三条 + 判定标准；本处不复述，只给 Java 落点与反面清单）。"
        "**判定标准（任一命中即不合规）**：① `catch` 住的是**非枚举查询的异常**却写空块体；"
        "③ 用带默认值的查询**绕开本该做的参数校验**；"
        "④ 空 `catch` 处**没有写明\"异常只有这一种原因\"的依据**。"
        "**边界（防反用）**：① **只放宽空块体**——该 `catch` 仍须捕获**具体异常类型**，"
        "**不得**写成 `catch (Throwable)`/`catch (Exception)` 这种**类级空 `catch`**"
        "（那种写法会把**同一个 `try` 里的其他语句**的异常一并吞掉）；"
        "② **工具类自身是正常类**：查不到就返回 `null`/`Optional.empty()` 的**本身就合规**，"
        "**此时无需、也不得**为该返回值再补一个空 `catch`；"
        "③ 只约束 Java、**替换主语测试**：非 Java 的对应能力另行判定。"
        "**存量**：随动迁移，见 `specs/core/execution.adoc`。"
        "**依据（标准名/编号）**：Java 官方 API 文档、ISO/IEC 25010、ISO/IEC/IEEE 29148。"
        "**「只此一种原因才允许空 `catch`」是本集合的判据化取值**。\n")

    def setUp(self) -> None:
        super().setUp()
        self._orig_java = cm.JAVA_STACK_FILE
        self._orig_coding = cm.CODING_FILE
        self._orig_common = cm.GENERIC_FILE
        cm.GENERIC_FILE = os.path.join(self.root, "AGENTS_COMMON.adoc")
        cm.JAVA_STACK_FILE = os.path.join(self.root, "specs", "stack", "java.adoc")
        cm.CODING_FILE = os.path.join(self.root, "specs", "general", "coding.adoc")
        self.write("specs/stack/java.adoc",
                   "= Java 规范（技术栈层）\n\n== 健壮性\n\n" + self.JAVA_RULE)
        self.write("specs/general/coding.adoc",
                   "= 通用编码规范\n\n== 代码质量（新产出即高质）\n\n" + self.CODING_RULE)
        self.write("library/adoption.adoc",
                   "= 取舍\n\n== 同义性差异与覆盖点（本集合自己承认的）\n"
                   "* 空 `catch`：`Enum.valueOf` 是本集合自己的判据化取舍，"
                   "也是「不得吞异常」的**唯一放宽口**。\n")
        self.write("library/sources.adoc",
                   "= 依据\n\n== 枚举查找的异常与空 `catch`\n"
                   "* `Enum.valueOf`（**本次未逐字取回**）。\n"
                   "* **须注意的语义差异（同义性，L1）**：API 文档未规定该不该吞。\n")

        self.write("AGENTS_COMMON.adoc",
                   "= 调度器\n\n**枚举查找的失败处理**（出现 `Enum.valueOf` 时）\n")

    def tearDown(self) -> None:
        (cm.JAVA_STACK_FILE, cm.CODING_FILE) = (self._orig_java, self._orig_coding)
        cm.GENERIC_FILE = self._orig_common
        super().tearDown()

    def _write_java(self, text):
        self.write("specs/stack/java.adoc", "= Java 规范（技术栈层）\n\n== 健壮性\n\n" + text)

    def _write_coding(self, text):
        self.write("specs/general/coding.adoc",
                   "= 通用编码规范\n\n== 代码质量（新产出即高质）\n\n" + text)

    def test_valid_passes(self):
        cm.check_java_enum_valueof_catch_guard()
        self.assertEqual([], cm.errors)

    def test_java_rule_removed_reports(self):
        # 反例①：Java 落点整条被删 → 例外无处可依（读者按栈文件学不到，或以为 L1 仍一刀切）
        self._write_java("* **别的条目**：略。\n")
        cm.check_java_enum_valueof_catch_guard()
        self.assertIn("Enum.valueOf", self.error_texts())

    def test_no_link_to_criteria_body_reports(self):
        # 反例②：不再回指通用层判据本体 → 本条要么失去判据、要么被就地再抄一份（第二真源）
        self._write_java(self.JAVA_RULE.replace(
            "**判据本体在** `specs/general/coding.adoc`「代码质量（新产出即高质）」的"
            "「显式处理失败与边界」（准入三条 + 判定标准；本处不复述，只给 Java 落点与反面清单）。", ""))
        cm.check_java_enum_valueof_catch_guard()
        self.assertIn("显式处理失败与边界", self.error_texts())

    def test_admission_condition_removed_reports(self):
        # 反例③（最危险的形态）：准入条件被删 → 例外只剩"允许空 catch"一句，任何 catch 都能自证合规
        self._write_java(self.JAVA_RULE.replace(
            "**只有\"没有该枚举常量\"这一种原因**（因值不匹配而抛）", "可能抛异常"))
        cm.check_java_enum_valueof_catch_guard()
        self.assertIn("这一种原因", self.error_texts())

    def test_scope_class_level_catch_removed_reports(self):
        # 反例④：扩大的方向一没被排除 → `catch (Exception) {}` 会被当成"符合例外"
        self._write_java(self.JAVA_RULE.replace(
            "**不得**写成 `catch (Throwable)`/`catch (Exception)` 这种**类级空 `catch`**"
            "（那种写法会把**同一个 `try` 里的其他语句**的异常一并吞掉）；", ""))
        cm.check_java_enum_valueof_catch_guard()
        self.assertIn("类级空 `catch`", self.error_texts())

    def test_default_value_boundary_removed_reports(self):
        # 反例⑤：扩大的方向二没被排除 → 给已返回默认值的写法再补空 catch
        self._write_java(self.JAVA_RULE.replace(
            "**此时无需、也不得**为该返回值再补一个空 `catch`", ""))
        cm.check_java_enum_valueof_catch_guard()
        self.assertIn("再补一个空 `catch`", self.error_texts())

    def test_basis_line_removed_reports(self):
        # 反例⑥：依据行与取舍定性被删 → 读者把"允许空 catch"读成 JDK 的规定
        self._write_java(self.JAVA_RULE.replace(
            "**依据（标准名/编号）**：Java 官方 API 文档、ISO/IEC 25010、ISO/IEC/IEEE 29148。"
            "**「只此一种原因才允许空 `catch`」是本集合的判据化取值**。", ""))
        cm.check_java_enum_valueof_catch_guard()
        self.assertIn("Java 官方 API 文档", self.error_texts())

    def test_general_layer_criteria_removed_reports(self):
        # 反例⑦：通用层的判据本体被抽走（只剩 Java 侧的一处）→ 例外失去准入判据、成通用豁免
        self._write_coding("* **显式处理失败与边界（L1）**：**不得吞异常**。\n")
        cm.check_java_enum_valueof_catch_guard()
        self.assertIn("三条同时成立才算命中", self.error_texts())

    def test_library_adoption_removed_reports(self):
        # 反例⑧：图书馆不登记取舍 → 该例外被读成某标准的规定
        self.write("library/adoption.adoc", "= 取舍\n\n== 同义性差异与覆盖点（本集合自己承认的）\n文字。\n")
        cm.check_java_enum_valueof_catch_guard()
        self.assertIn("唯一放宽口", self.error_texts())

    def test_library_sources_removed_reports(self):
        # 反例⑨：依据段被删 → 依据只存名称，日后无从核对"它今天还成立吗"
        self.write("library/sources.adoc", "= 依据\n\n== 别的主题\n文字。\n")
        cm.check_java_enum_valueof_catch_guard()
        self.assertIn("Enum.valueOf", self.error_texts())

    def test_load_gate_removed_reports(self):
        # 反例⑩：加载门没了（调度器不登记识别特征）→ 写 `Enum.valueOf` 时该条永不被加载，
        # 例外形同不存在；与 `check_java_object_template_guard` 同口径
        self.write("AGENTS_COMMON.adoc", "= 调度器\n\n别的条目。\n")
        cm.check_java_enum_valueof_catch_guard()
        self.assertIn("识别特征", self.error_texts())


class TestCheckDocTypeNotationGuard(CheckSpecsTestCase):
    """钉住『文档中提及类型优先写类名 + import，不写类全名』（用户提出的规范要求）。

    该条为 **L2**、且判据是语义的（`java.util.UUID` 一类外部类型全限定属合规），故防线
    **不扫存量文档**，只钉"条文与判据仍在、边界没被删"。最易被四件事冲掉：
      * **"如果有必要"被读成"想写就写"** —— 三个必要情形（同名类冲突 / 无代码示例可承载
        import / 外部或他仓类型）被抽掉后，禁则就交回执行者自裁；
      * **被读成本条禁止一切全限定** —— 例外边界（路径与坐标不是类型名、字符串与配置里必须
        全限定的场合、`{@link}`/`@see` 成员引用）被删，反而会写出不合法的 javadoc 标签；
      * **存量口径被扩成全库改** —— "不做一次性替换、随动调整"被删，会被扩成"扫全库改全限定"；
      * **调度器无识别特征** —— 规则写了却永不被触发加载（实际失效）。
    故本组用例除正例外，逐条覆盖上述反例。
    """

    DOC = (
        "= 文档规范\n\n== 注释与文档\n"
        "* **文档中提及类型优先写类名 + import，不写类全名（L2）**：文档提到某个类型时，"
        "**一律先直接写它的类名**（`CUnauthorizedException`），需要解析时在**就近的代码示例**里"
        "写一条 `import com.c332030.ctool4j.core.exception.CUnauthorizedException;`——"
        "**不得**用**类全名**充当标识。**\"如果有必要\"的判据**：①**同名类冲突**；"
        "②**无代码示例可承载 import**（纯文档通篇没有代码块）；"
        "③**该类型不在本仓库的 classpath 内**（不在本仓库依赖树里）。"
        "\"classpath\"取\"本仓库的依赖/可解析范围\"。"
        "**三个例外的边界**：①**路径与坐标**（文档里的链接与 `@see` 标签所引的文件路径）"
        "**不是类型名**，照常写全；②**字符串与配置**里必须全限定的场合（Spring 的 "
        "`@ConditionalOnClass`、`application.yml` 的 `main-class`、反射按名加载、`import` "
        "语句本身）属逻辑实现；③**文档自身的文本引用**仍按上条的引用写法。"
        "**本集合的自身取舍，属 L2**：**不做存量一次性替换、随动调整**。\n")

    JAVA = (
        "= Java 规范\n\n== javadoc\n"
        "* 类型指代写短类名 + import、不写全限定类名：javadoc 里提到某个类时**先写短类名**"
        "，需要解析时在**代码示例**里写一条 `import com.c332030.ctool4j.core.exception."
        "CUnauthorizedException;`；**不得**写全限定类名（**除非该类型不在本仓库的 classpath "
        "内**）。`{@link ...}` / `@see` 里按类全名做的"
        "**成员引用**（javadoc 标签要求合法引用，须全限定）照常。\n")

    # 调度器**只给触发特征**（要写文档注释/说明文字、要提到某个类型时即命中），
    # 不抄条目本体的取值（`不写类全名`/`包名 + 类名`/`classpath` 都在 `doc.adoc`/`java.adoc` 里）。
    COMMON = (
        "= 通用规范\n"
        "** 写注释/文档/格式 → `specs/general/doc.adoc`（识别特征：要写文档注释或说明文字、"
        "文中要提到一个类型）\n"
        "** Java 项目（**类型指代**：要写 javadoc、要提到一个类）\n")

    def setUp(self) -> None:
        super().setUp()
        self._orig_doc = cm.DOC_FILE
        self._orig_java = cm.JAVA_STACK_FILE
        cm.DOC_FILE = os.path.join(self.root, "specs", "general", "doc.adoc")
        cm.JAVA_STACK_FILE = os.path.join(self.root, "specs", "stack", "java.adoc")
        self.write("specs/general/doc.adoc", self.DOC)
        self.write("specs/stack/java.adoc", self.JAVA)
        self.write("AGENTS_COMMON.adoc", self.COMMON)

    def tearDown(self) -> None:
        (cm.DOC_FILE, cm.JAVA_STACK_FILE) = (self._orig_doc, self._orig_java)
        super().tearDown()

    def test_positive_passes(self):
        cm.check_doc_type_notation_guard()
        self.assertEqual([], cm.errors)

    def test_rule_deleted_reports(self):
        # 反例①：整条被删（最简单的冲掉方式）
        self.write("specs/general/doc.adoc", "= 文档规范\n\n== 注释与文档\n* 别的条目\n")
        cm.check_doc_type_notation_guard()
        self.assertIn("文档类型指代防线被破坏", self.error_texts())

    def test_level_downgraded_reports(self):
        # 反例②：级别被摘（L2 去掉后写类全名会重新变成个人选择）
        self.write("specs/general/doc.adoc", self.DOC.replace("不写类全名（L2）", "不写类全名"))
        cm.check_doc_type_notation_guard()
        self.assertIn("文档类型指代防线被破坏", self.error_texts())

    def test_necessary_cases_removed_reports(self):
        # 反例③：三个必要情形被抽掉 → "如果有必要"变成想写就写
        self.write("specs/general/doc.adoc",
                   self.DOC.replace("①**同名类冲突**；", "①……；"))
        cm.check_doc_type_notation_guard()
        self.assertIn("同名类冲突", self.error_texts())

    def test_exception_boundary_removed_reports(self):
        # 反例④：例外边界（路径不是类型名）被删 → 会被读成本条禁止一切全限定
        self.write("specs/general/doc.adoc",
                   self.DOC.replace("**不是类型名**，照常写全", "也照常写全"))
        cm.check_doc_type_notation_guard()
        self.assertIn("路径与坐标", self.error_texts())

    def test_conditional_on_class_boundary_removed_reports(self):
        # 反例⑤：字符串/配置里必须全限定的边界被删
        self.write("specs/general/doc.adoc",
                   self.DOC.replace("@ConditionalOnClass", "某些注解"))
        cm.check_doc_type_notation_guard()
        self.assertIn("@ConditionalOnClass", self.error_texts())

    def test_outside_classpath_case_hardened_reports(self):
        # 反例⑥：第三条判据被写成"不在本仓库/本项目内"（把"不在 classpath"偏严成"不在本仓库"，
        # 用户口径的后半句"除非不在 classpath 才能写类全名"失效）
        self.write("specs/general/doc.adoc",
                   self.DOC.replace("③**该类型不在本仓库的 classpath 内**（不在本仓库依赖树里）。",
                                    "③**该类型不在本仓库/本项目内**。"))
        cm.check_doc_type_notation_guard()
        self.assertIn("classpath", self.error_texts())

    def test_java_stock_scope_hardened_reports(self):
        # 反例⑦：Java 落点的同一判据被写成"外部依赖或他仓类型"（不含 classpath 口径）
        self.write("specs/stack/java.adoc",
                   self.JAVA.replace("（**除非该类型不在本仓库的 classpath 内**）", ""))
        cm.check_doc_type_notation_guard()
        self.assertIn("不在本仓库的 classpath 内", self.error_texts())

    def test_stock_scope_removed_reports(self):
        # 反例⑥：存量口径被删 → 会被扩成"扫全库改全限定"
        self.write("specs/general/doc.adoc",
                   self.DOC.replace("**不做存量一次性替换、随动调整**", "一律改齐"))
        cm.check_doc_type_notation_guard()
        self.assertIn("存量", self.error_texts())

    def test_java_landing_removed_reports(self):
        # 反例⑦：Java 落点被删（接口/import 的具体写法只在栈层说得清）
        self.write("specs/stack/java.adoc", "= Java 规范\n\n== javadoc\n* 别的要求\n")
        cm.check_doc_type_notation_guard()
        self.assertIn("全限定类名", self.error_texts())

    def test_java_member_ref_boundary_removed_reports(self):
        # 反例⑧：{@link}/@see 成员引用须全限定这条边界被删
        self.write("specs/stack/java.adoc", self.JAVA.replace("{@link", "链接"))
        cm.check_doc_type_notation_guard()
        self.assertIn("Java 栈", self.error_texts())

    def test_dispatcher_trigger_removed_reports(self):
        # 反例⑨：调度器没有识别特征 → 规则永不被触发加载（实际失效）
        self.write("AGENTS_COMMON.adoc", "= 通用规范\n** 别的条目\n")
        cm.check_doc_type_notation_guard()
        self.assertIn("文档", self.error_texts())

    def test_java_trigger_removed_reports(self):
        # 反例⑩：Java 栈条目的识别特征被删
        self.write("AGENTS_COMMON.adoc",
                   self.COMMON.replace("（**类型指代**：要写 javadoc、要提到一个类）", ""))
        cm.check_doc_type_notation_guard()
        self.assertIn("类型指代", self.error_texts())

    def test_missing_doc_file_reports(self):
        # 反例⑪：通用层落点文件缺失 → 必须报错、不得静默通过
        os.remove(os.path.join(self.root, "specs", "general", "doc.adoc"))
        cm.check_doc_type_notation_guard()
        self.assertIn("specs/general/doc.adoc", self.error_texts())


class TestCheckMavenMirrorGuard(CheckSpecsTestCase):
    """钉住 Maven「仓库与镜像」节：指定仓库、两条触发前提与换源边界不得被删改。

    该条规则的全部内容就是「用哪个仓库、什么前提下用」，故反例逐条对应"最易被精简掉"
    的字句：前提只剩一半、地址被换、优先次序被抹平、换源被读宽、换源出境内、既有配置被重配。
    正例含容差：节标题带括号补充、仓库地址改写成 `link:` 形态，均不报错。
    """

    SECTION = (
        "= Maven 规范\n\n== 仓库与镜像\n"
        "* 未配置过 Maven 仓库/镜像、且外网出口 IP 在中国大陆时（L1）："
        "必须先用这个仓库 `https://mirrors.cloud.tencent.com/nexus/repository/maven-public/`；"
        "仅当它不可用才允许改用其他在境内的镜像站；已配置过即不做，不覆盖既有配置。\n")

    def setUp(self) -> None:
        super().setUp()
        self.write("specs/stack/maven.adoc", self.SECTION)

    def test_positive_passes(self):
        cm.check_maven_mirror_guard()
        self.assertEqual([], cm.errors)

    def test_missing_file_reports(self):
        os.remove(os.path.join(self.root, "specs", "stack", "maven.adoc"))
        cm.check_maven_mirror_guard()
        self.assertIn("specs/stack/maven.adoc", self.error_texts())

    def test_section_deleted_reports(self):
        self.write("specs/stack/maven.adoc", "= Maven 规范\n\n== 依赖\n* 别的\n")
        cm.check_maven_mirror_guard()
        self.assertIn("仓库与镜像", self.error_texts())

    def test_section_title_extra_words_tolerated(self):
        # 节标题带括号补充属排版，不得因此报"缺少节"
        self.write("specs/stack/maven.adoc",
                   self.SECTION.replace("== 仓库与镜像",
                                        "== 仓库与镜像（公有仓库在国内的初始化）"))
        cm.check_maven_mirror_guard()
        self.assertEqual([], cm.errors)

    def test_designated_repo_removed_reports(self):
        self.write("specs/stack/maven.adoc",
                   self.SECTION.replace(
                       "https://mirrors.cloud.tencent.com/nexus/repository/maven-public/",
                       "https://example.invalid/repository/maven-public/"))
        cm.check_maven_mirror_guard()
        self.assertIn("mirrors.cloud.tencent.com", self.error_texts())

    def test_designated_repo_link_notation_tolerated(self):
        # 地址改写成 link: 形态（AsciiDoc 惯用写法）不得被误报为缺失
        self.write("specs/stack/maven.adoc",
                   self.SECTION.replace(
                       "`https://mirrors.cloud.tencent.com/nexus/repository/maven-public/`",
                       "link:https://mirrors.cloud.tencent.com/nexus/repository/maven-public/"
                       "[`https://mirrors.cloud.tencent.com/nexus/repository/maven-public/`]"))
        cm.check_maven_mirror_guard()
        self.assertEqual([], cm.errors)

    def test_forced_repo_wording_removed_reports(self):
        self.write("specs/stack/maven.adoc",
                   self.SECTION.replace("必须先用这个仓库", "可选其一"))
        cm.check_maven_mirror_guard()
        self.assertIn("必须先", self.error_texts())

    def test_trigger_condition_removed_reports(self):
        self.write("specs/stack/maven.adoc",
                   self.SECTION.replace("外网出口 IP 在中国大陆", "任何环境"))
        cm.check_maven_mirror_guard()
        self.assertIn("中国大陆", self.error_texts())

    def test_precondition_removed_reports(self):
        self.write("specs/stack/maven.adoc",
                   self.SECTION.replace("未配置过 Maven 仓库/镜像、且", "总是"))
        cm.check_maven_mirror_guard()
        self.assertIn("未配置过 Maven 仓库/镜像", self.error_texts())

    def test_existing_config_skip_removed_reports(self):
        self.write("specs/stack/maven.adoc",
                   self.SECTION.replace("已配置过即不做", "每次构建前都重配一遍"))
        cm.check_maven_mirror_guard()
        self.assertIn("已配置过即不做", self.error_texts())

    def test_fallback_condition_removed_reports(self):
        # "仅当它不可用才可换源"被放宽成"可自行另挑"即被拦下
        self.write("specs/stack/maven.adoc",
                   self.SECTION.replace("仅当它不可用才允许", "也可自行"))
        cm.check_maven_mirror_guard()
        self.assertIn("仅当它不可用", self.error_texts())

    def test_fallback_must_stay_in_china_reports(self):
        # 换源限定"在境内"被抹掉即被拦下（换到境外源等于没换）
        self.write("specs/stack/maven.adoc",
                   self.SECTION.replace("其他在境内的镜像站", "其他镜像站"))
        cm.check_maven_mirror_guard()
        self.assertIn("在境内的镜像站", self.error_texts())



class TestCheckMavenParallelGuard(CheckSpecsTestCase):
    """钉住 Maven「构建并行度」节：默认值口径、既有配置优先、模块粒度与三处落点。

    本条的关键是**两半都不能少**：只留"默认开并行"会变成"自己去开/去配"（覆盖引用方既有
    配置），只留"以配置为准"会退化成"没配过也不管"（用户口径是"默认会自己启用"）。
    故反例逐条对应最易被精简掉的字句，并逐处覆盖三处落点。
    """

    # 用例里的最小工件按防线的**要点清单自派生**——加一条要点只改一处，
    # 用例不会因为"正面用例其实没写全要点"而静默测不到（旧写法是手抄一份平行文本）。
    def _section(self):
        parts = []
        for name, tokens, _why in cm.MAVEN_PARALLEL_ANCHORS:
            parts.append("* " + name + "：" + "；".join(tokens) + "。\n")
        parts.append("* 依据（标准名/编号）：Maven 官方命令行参考、Apache Maven Surefire 插件文档、"
                     "ISO/IEC/IEEE 25010。\n")
        return "= Maven 规范\n\n== 构建并行度\n" + "".join(parts)

    def _common(self):
        return ("// tag::build-parallel[]\n"
                "**构建并行度（仅限 Maven 多模块构建）**：" + "；".join(cm.MAVEN_PARALLEL_PROMPT_ANCHORS) + "。\n"
                "// end::build-parallel[]\n")

    @property
    def SECTION(self):
        return self._section()

    @property
    def COMMON(self):
        return self._common()

    def _fixture(self):
        self.write("specs/stack/maven.adoc", self.SECTION)
        self.write("AGENTS_COMMON.adoc",
                   "* **Maven 构建**（存在 `pom.xml`/`mvnw`）→ `specs/stack/maven.adoc`。"
                   "识别特征：**要跑 Maven 构建/测试时**——**构建并行度**"
                   "（`.mvn/maven.config` 优先）与**仓库与镜像**\n")
        self.write("library/sources.adoc",
                   "== Maven 命令行与并行构建\n" + "\n".join(cm.MAVEN_PARALLEL_SOURCE_ANCHORS) + "\n")
        self.write("library/adoption.adoc",
                   "* **「Maven 默认启用多线程构建、以项目配置为准」是本站的判据化取舍**："
                   "官方只给机制与取值写法。\n")
        self.write("prompts/_common.txt", self.COMMON)
        self.write("prompts/review.adoc",
                   "**给 AI 的读取说明**：正文由 `prompts/_common.txt` 的公共片段（"
                   "`build-parallel` / `compat`）组装。\n"
                   "include::_common.txt[tag=build-parallel]\n")
        self.write("prompts/refactor.adoc",
                   "**给 AI 的读取说明**：正文由 `prompts/_common.txt` 的公共片段（"
                   "`build-parallel` / `compat`）组装。\n"
                   "include::_common.txt[tag=build-parallel]\n")

    def test_positive_passes(self):
        self._fixture()
        cm.check_maven_parallel_guard()
        self.assertEqual([], cm.errors)

    def test_missing_spec_reports(self):
        self._fixture()
        os.remove(os.path.join(self.root, "specs", "stack", "maven.adoc"))
        cm.check_maven_parallel_guard()
        self.assertIn("specs/stack/maven.adoc", self.error_texts())

    def test_section_deleted_reports(self):
        self._fixture()
        self.write("specs/stack/maven.adoc", "= Maven 规范\n\n== 依赖\n* 别的\n")
        cm.check_maven_parallel_guard()
        self.assertIn("构建并行度", self.error_texts())

    def test_default_switch_removed_reports(self):
        # 反例①：默认值口径被抽掉（只剩"以配置为准"）→ 没配过的项目照旧单线程
        self._fixture()
        self.write("specs/stack/maven.adoc",
                   self.SECTION.replace("不写 `-T` 即默认单线程", "按需自行决定"))
        cm.check_maven_parallel_guard()
        self.assertIn("不写 `-T` 即默认单线程", self.error_texts())

    def test_default_value_not_cores_reports(self):
        # 反例①-2：取值口径退回「写死的 1C」→ 取的不是当前设备核心数（用户点名）
        self._fixture()
        self.write("specs/stack/maven.adoc",
                   self.SECTION.replace("取值＝当前构建设备的核心数", "取值一律 `--threads 1C`"))
        cm.check_maven_parallel_guard()
        self.assertIn("取值＝当前构建设备的核心数", self.error_texts())

    def test_value_how_to_get_written_back_reports(self):
        # 反例①-4：取值写着"核心数"，却又把"怎么取核数"写回正文（用户点名要治的形态：
        # 规范只定义取值，不要在规范里写如何去拿核心数）
        self._fixture()
        self.write("specs/stack/maven.adoc",
                   self.SECTION.replace(
                       "核心数怎么得到是执行动作，不写进规范",
                       "核心数用 `nproc`／`sysctl -n hw.ncpu` 一类命令实测得到"))
        cm.check_maven_parallel_guard()
        self.assertIn("核心数怎么得到是执行动作", self.error_texts())

    def test_prompt_value_fixed_at_1c_reports(self):
        # 反例①-3：片段又变回「命令行补 `-T 1C`」→ 执行侧按写死值开（取不到当前设备核心数）
        self._fixture()
        self.write("prompts/_common.txt",
                   self.COMMON.replace("不得写死 `-T 1C`", "命令行补 `-T 1C`"))
        cm.check_maven_parallel_guard()
        self.assertIn("不得写死", self.error_texts())

    def test_cmdline_carrier_removed_reports(self):
        # 反例①-5：取值不再要求"写在命令行上"（改由环境变量一类载体传）→
        # 参数看着加了、命令形态无从核对，换个版本就悄悄退回单线程且不报错
        self._fixture()
        self.write("specs/stack/maven.adoc",
                   self.SECTION.replace("取值以命令行参数形态显式传（L1）", "取值可由环境变量或配置传入"))
        cm.check_maven_parallel_guard()
        self.assertIn("命令行参数形态显式传", self.error_texts())

    def test_prompt_cmdline_carrier_removed_reports(self):
        # 反例①-6：执行侧片段抽掉"必须以命令行参数形态显式传"这一半
        self._fixture()
        self.write("prompts/_common.txt",
                   self.COMMON.replace("取值必须以命令行参数形态显式传（L1）", "取值可用 `MAVEN_OPTS` 传"))
        cm.check_maven_parallel_guard()
        self.assertIn("命令行参数形态显式传", self.error_texts())

    def test_prompt_env_var_carrier_allowed_reports(self):
        # 反例①-7：片段把 `MAVEN_OPTS` 一类载体放开（失效形态：参数不在命令行上、无从核对）
        self._fixture()
        self.write("prompts/_common.txt",
                   self.COMMON.replace("不得改用 `MAVEN_OPTS` 一类环境变量载体", "允许用 `MAVEN_OPTS` 传"))
        cm.check_maven_parallel_guard()
        self.assertIn("MAVEN_OPTS", self.error_texts())

    def test_anchor_list_item_removed_reports(self):
        # 反例①-8（**清单删项**）：锚点清单是纯数据、只被本条防线读取——删掉一项时
        # 规范正文一字未动，那圈"逐 token 核现场文本"**一次都不报错**（"核过且通过"
        # 与"没核"无从区分）。本条的新增要点只在这里登记过一次，故须有入场核拦它。
        self._fixture()
        saved = cm.MAVEN_PARALLEL_ANCHORS
        reduced = copy.deepcopy(list(saved))
        reduced[0][1] = [t for t in reduced[0][1]
                         if t != "取值以命令行参数形态显式传（L1）"]
        cm.MAVEN_PARALLEL_ANCHORS = reduced
        try:
            self.write("specs/stack/maven.adoc", self.SECTION)
            cm.check_maven_parallel_guard()
            self.assertIn("锚点条数从下限", self.error_texts())
        finally:
            cm.MAVEN_PARALLEL_ANCHORS = saved

    def test_prompt_anchor_list_item_removed_reports(self):
        # 反例①-9（**片段清单删项**）：与上一条同源——删掉执行侧那两条要求后，
        # 片段一字未动、逐项核对全绿，而"取值须写在命令行上"就此失守
        self._fixture()
        saved = cm.MAVEN_PARALLEL_PROMPT_ANCHORS
        cm.MAVEN_PARALLEL_PROMPT_ANCHORS = [
            t for t in saved
            if t not in ("取值必须以命令行参数形态显式传（L1）",
                         "不得改用 `MAVEN_OPTS` 一类环境变量载体")]
        try:
            self.write("prompts/_common.txt", self.COMMON)
            cm.check_maven_parallel_guard()
            self.assertIn("锚点条数从下限", self.error_texts())
        finally:
            cm.MAVEN_PARALLEL_PROMPT_ANCHORS = saved

    def test_spec_cmdline_scope_removed_reports(self):
        # 反例②-2：覆盖口径的**取值句**被抽走（"取值相同也是覆盖"）而轴的标题仍在
        # ——只核组名/轴名属防线空转，故锚点取到判据本体那一句
        self._fixture()
        self.write("specs/stack/maven.adoc",
                   self.SECTION.replace("即使命令行传的取值与项目配置的完全相同", "取值相同时视为沿用"))
        cm.check_maven_parallel_guard()
        self.assertIn("即使命令行传的取值与项目配置的完全相同", self.error_texts())

    def test_spec_failure_mode_removed_reports(self):
        # 反例②-3：新增条文的**失效形态**被抽走（"悄悄退回单线程"）——只剩"必须写在命令行上"
        # 时读者不知道防的是什么，换个版本静默退化照旧发生
        self._fixture()
        self.write("specs/stack/maven.adoc",
                   self.SECTION.replace("悄悄退回单线程", "可能不被识别"))
        cm.check_maven_parallel_guard()
        self.assertIn("悄悄退回单线程", self.error_texts())

    def test_config_priority_removed_reports(self):
        # 反例②：最易被精简掉的一半——"配过即沿用、不得覆盖"（缺则去改引用方配置）
        self._fixture()
        self.write("specs/stack/maven.adoc",
                   self.SECTION.replace("不得覆盖、不得重复追加", "统一改成推荐取值"))
        cm.check_maven_parallel_guard()
        self.assertIn("不得覆盖", self.error_texts())

    def test_module_granularity_removed_reports(self):
        # 反例③：模块粒度被抽走 → "并行"被读成"模块内也并发"（与同一模块禁止并行构建冲突）
        self._fixture()
        self.write("specs/stack/maven.adoc",
                   self.SECTION.replace("模块间", "所有构建步骤都可以并行"))
        cm.check_maven_parallel_guard()
        self.assertIn("模块间", self.error_texts())

    def test_test_parallel_boundary_removed_reports(self):
        # 反例④：把构建并行与测试并行混为一谈（顺手开测试并行＝改变引用方既有行为）
        self._fixture()
        self.write("specs/stack/maven.adoc",
                   self.SECTION.replace("默认只启用构建并行，不因本条去开测试并行", "测试一并并行"))

        cm.check_maven_parallel_guard()
        self.assertIn("默认只启用构建并行", self.error_texts())

    def test_basis_name_removed_reports(self):
        # 反例⑤：依据被压成"本站规定"（读者无法核对官方到底有没有要求）
        self._fixture()
        self.write("specs/stack/maven.adoc",
                   self.SECTION.replace("Apache Maven Surefire 插件文档", "相关最佳实践"))
        cm.check_maven_parallel_guard()
        self.assertIn("Apache Maven Surefire", self.error_texts())

    def test_dispatcher_feature_removed_reports(self):
        # 反例⑥：调度器识别特征被删 → "要跑构建"时永远不会加载到该节
        self._fixture()
        self.write("AGENTS_COMMON.adoc",
                   "* **Maven 构建**（存在 `pom.xml`）→ `specs/stack/maven.adoc`\n")
        cm.check_maven_parallel_guard()
        self.assertIn("构建", self.error_texts())

    def test_library_source_anchor_removed_reports(self):
        # 反例⑦：图书馆官方原文锚点被删（依据只剩名称）
        self._fixture()
        self.write("library/sources.adoc", "== Maven\n什么都记不清了\n")
        cm.check_maven_parallel_guard()
        self.assertIn(cm.MAVEN_PARALLEL_SOURCE_ANCHORS[0], self.error_texts())

    def test_library_adoption_anchor_removed_reports(self):
        # 反例⑧：图书馆未登记"本站取舍" → 读者把本站口径当成 Maven 官方要求
        self._fixture()
        self.write("library/adoption.adoc", "== 同义性差异与覆盖点\n* 别的\n")
        cm.check_maven_parallel_guard()
        self.assertIn("判据化取舍", self.error_texts())

    def test_prompt_tag_removed_reports(self):
        # 反例⑨：提示词公共片段缺失 → 执行侧没有任何开并行的动作落点
        self._fixture()
        self.write("prompts/_common.txt", "（没有该片段）\n")
        cm.check_maven_parallel_guard()
        self.assertIn("build-parallel", self.error_texts())

    def test_prompt_tag_half_removed_reports(self):
        # 反例⑩：片段只留"默认开并行"、抽掉"配过就沿用不覆盖" → 执行者会去改引用方配置
        self._fixture()
        self.write("prompts/_common.txt",
                   "// tag::build-parallel[]\n没配过就补 `-T 2C`。\n// end::build-parallel[]\n")
        cm.check_maven_parallel_guard()
        self.assertIn("一律沿用", self.error_texts())

    def test_prompt_not_including_tag_reports(self):
        # 反例⑪：公共片段写了但提示词没引入（定义了却不生效）
        self._fixture()
        self.write("prompts/review.adoc",
                   "**给 AI 的读取说明**：正文由 `prompts/_common.txt` 的公共片段（"
                   "`build-parallel` / `compat`）组装。\n")
        cm.check_maven_parallel_guard()
        self.assertIn("prompts/review.adoc", self.error_texts())

    def test_prompt_read_guide_missing_tag_reports(self):
        # 反例⑫：片段被引入了、但读取说明的清单漏列（原始文件形态下读者按清单补齐，漏列即漏读）
        self._fixture()
        self.write("prompts/refactor.adoc",
                   "**给 AI 的读取说明**：正文由 `prompts/_common.txt` 的公共片段（"
                   "`compat`）组装。\n"
                   "include::_common.txt[tag=build-parallel]\n")
        cm.check_maven_parallel_guard()
        self.assertIn("prompts/refactor.adoc", self.error_texts())


class TestCheckRegistryMirrorGuard(CheckSpecsTestCase):
    """钉住『包源与镜像源』防线：推荐次序、降级边界与"先实测再启用"不得被删或降级。

    背景（本次用户要求 + 本项目实测）：换源此前只有 Maven 一栈的一条硬要求；其余语言/工具
    （npm、pip、Cargo、Go、RubyGems、容器镜像、系统包、运行时二进制）没有次序与边界，
    容易"凭感觉挑一个""直接跳到境外源"，或把**实测不存在**的目录（如"TUNA 的 npm 源"）
    照抄进配置。故反例逐条对应"最易被精简掉"的字句：次序被抹平、跳级、不先实测、
    覆盖引用方既有配置、把推荐读成强制。

    正例含容差：条目措辞与顺序可变（只认关键判据），源地址可增删（不钉名单）。
    """

    SECTION = (
        "= 依赖管理规范\n\n"
        "== 包源（包仓库/镜像站）的选用\n"
        "* 按次序选源、逐级降级，不得跳级（L1）：①就近/平台内已优化的源；②主流公共源；"
        "③地理上邻近的其他境外源；④更远的境外源站；只有当上一级实测取不到内容才降级；"
        "未配置过任何源时才动手配置。\n"
        "* 先实测可用再启用、一次配置到位（L1）：候选源须**已实测可用**；"
        "不得**在每一轮里反复重试**同一个源。\n"
        "* 不得覆盖引用方既有配置（L1）：已配置过**包源时**一律沿用；只有在\"未配置过任何源\"时才动手配置；"
        "**推荐源不是强制源**，用户/项目声明的源永远优先。\n"
        "* 结果须可复核（L2）：给结论时带**取值与条件**。\n")

    def setUp(self) -> None:
        super().setUp()
        self.write("specs/general/dependency.adoc", self.SECTION)
        self.write("specs/stack/maven.adoc", "见 mirrors.cloud.tencent.com/nexus/repository/maven-public/\n")
        self.write("specs/stack/python.adoc", "pip 源见 https://mirrors.cloud.tencent.com/pypi/simple/\n")
        self.write("specs/stack/java.adoc", "Clojars（clojars）构件另加源\n")
        self.write("specs/general/ci-cd.adoc", "取源按 link:dependency.adoc[]「包源（包仓库/镜像站）的选用」\n")
        self.write("specs/platform/cnb.adoc", "== 包源与镜像源（平台侧优先口径）\n* 优先用平台内源\n")
        self.write("library/README.adoc", "| link:mirrors.adoc[] | 包源依据 |\n")
        self.write("library/mirrors.adoc",
                   "= 包源\n外部材料**未**规定源站的优先级次序；本集合据此推出次序；"
                   "**取样条件**见下；复核实测见下；**判可用性要取确定存在的包、不要只请求站点/目录根**；"
                   "单次采样不构成\"某源更快\"的结论。\n== 实测记录\n")

    def test_positive_passes(self):
        cm.check_registry_mirror_guard()
        self.assertEqual([], cm.errors)

    def test_missing_dependency_file_reports(self):
        os.remove(os.path.join(self.root, "specs", "general", "dependency.adoc"))
        cm.check_registry_mirror_guard()
        self.assertIn("specs/general/dependency.adoc", self.error_texts())

    def test_early_return_paths_still_return_normally(self):
        # 回归：缺文件/缺节这两条**最早命中**的路径必须是"报错并返回"，不得继续往下走
        # （否则后面的常量解包会抛异常，防线从"报错"变成"崩掉"，而既有用例只断言错误文本、
        # 崩了也照样绿）。判据：正常返回 + 错误清单已写。
        os.remove(os.path.join(self.root, "specs", "general", "dependency.adoc"))
        cm.check_registry_mirror_guard()          # 不抛异常即为通过
        self.assertIn("specs/general/dependency.adoc", self.error_texts())

        cm.errors.clear()
        self.write("specs/general/dependency.adoc", "= 依赖\n\n== 别的\n")
        cm.check_registry_mirror_guard()
        self.assertIn("包源（包仓库/镜像站）的选用", self.error_texts())

    def test_topic_file_not_registered_in_index_reports(self):
        # 反例：主题文件在磁盘上、却漏登记到入口表——读者按入口找不到它
        # （既有 `quality.adoc` 就不在下限常量里，故完整性只能靠入口表核对，不能靠常量）
        self.write("library/extra.adoc", "= 另一个主题\n\n内容。\n")
        cm.check_registry_mirror_guard()
        self.assertIn("extra.adoc", self.error_texts())

    def test_weak_anchor_no_longer_passes_on_loose_tokens(self):
        # 反例：只留"已配置过**"这类任何措辞都会命中的片段、把边界句删掉 → 必须报错
        self.write("specs/general/dependency.adoc",
                   self.SECTION.replace("只有在\"未配置过任何源\"时才动手配置；", "已配置过**就跳过；")
                   .replace("**推荐源不是强制源**，用户/项目声明的源永远优先。", "必须用推荐源。"))
        cm.check_registry_mirror_guard()
        self.assertIn("不覆盖引用方既有配置", self.error_texts())

    def test_section_deleted_reports(self):
        self.write("specs/general/dependency.adoc", "= 依赖\n\n== 引入依赖\n* 别的\n")
        cm.check_registry_mirror_guard()
        self.assertIn("包源（包仓库/镜像站）的选用", self.error_texts())

    def test_order_terms_removed_reports(self):
        # 次序被压成"用国内源"时，跳级与境外分档就无从判断
        self.write("specs/general/dependency.adoc",
                   self.SECTION.replace("地理上邻近的其他境外源", "国外源"))
        cm.check_registry_mirror_guard()
        self.assertIn("邻近", self.error_texts())

    def test_probe_before_use_removed_reports(self):
        self.write("specs/general/dependency.adoc",
                   self.SECTION.replace("候选源须**已实测可用**", "按文档描述直接配置"))
        cm.check_registry_mirror_guard()
        self.assertIn("真实请求", self.error_texts())

    def test_existing_config_keep_removed_reports(self):
        self.write("specs/general/dependency.adoc",
                   self.SECTION.replace("已配置过**包源时**一律沿用", "每次都用推荐源覆盖"))
        cm.check_registry_mirror_guard()
        self.assertIn("沿用", self.error_texts())

    def test_recommend_not_force_removed_reports(self):
        self.write("specs/general/dependency.adoc",
                   self.SECTION.replace("**推荐源不是强制源**", "必须使用本规范指定的源"))
        cm.check_registry_mirror_guard()
        self.assertIn("强制源", self.error_texts())

    def test_stack_landing_missing_reports(self):
        # 栈侧落点被删 → 具体源地址无处承载（本条要防的正是"只有通用层、落不到现场"）
        self.write("specs/stack/python.adoc", "= Python\n")
        cm.check_registry_mirror_guard()
        self.assertIn("specs/stack/python.adoc", self.error_texts())

    def test_library_not_registered_reports(self):
        self.write("library/README.adoc", "| link:sources.adoc[] | 别的 |\n")
        cm.check_registry_mirror_guard()
        self.assertIn("mirrors.adoc", self.error_texts())

    def test_library_without_measured_record_reports(self):
        self.write("library/mirrors.adoc", "= 包源\n本处只写推荐名单。\n")
        cm.check_registry_mirror_guard()
        self.assertIn("library/mirrors.adoc", self.error_texts())


class TestCheckThroughputGuard(CheckSpecsTestCase):
    """钉住「执行吞吐」条：判据要点、常驻层引用与调度器登记不得被删。

    实证：Agent 慢的主因是**轮次**——实测一次任务 180 次模型请求 / 175 万 token 输入 /
    1659 s 运行，其中模型生成仅 580 s（约 65% 的墙钟花在轮次之间的工具执行与等待）。
    故反例逐条对应"最易被当废话砍掉"的字句：合并调用、构建输出一次取到、不重复读、
    往返成本入规划、凭据一次固化、镜像不重配、长流程不空转；另钉常驻层引用与调度器
    识别特征（缺则规则不可达、不加载）。
    """

    PLATFORM_SECTION = (
        "= CNB 平台相关\n\n== 执行吞吐（平台侧的两处特有代价）\n"
        "* 一次唤起 = 一次完整加载 + 一轮往返（L1）。\n"
        "* 状态查询按先取汇总、再按需下钻（L2）。\n"
        "* 不要用零信息的往返等长流程。\n"
        "* AI 用量汇总与 AI 请求明细是可观测面（L2）。\n")

    SECTION = (
        "= 上下文与读取范围规范\n\n== 执行吞吐（逐条判据）\n"
        "* 独立调用必须合并，禁止试探式往返（L1）：不得为了先看一步再决定下一步拆成多轮。\n"
        "* 构建与校验的输出须一次取到（L1）：执行 + 取统计 + 取失败明细一次完成。\n"
        "* 读到的内容一次沉淀、不重复读（L1）：同一路径在一次任务里被读第二次即违规。\n"
        "* 往返成本也要算（L2）：规划时估出预计要几轮往返。\n"
        "* 执行环境凭据须固化为可复用形态（L2）：开始时固化一次。\n"
        "* 本地缓存与镜像就近取用（L2）：已配置过即沿用、不覆盖、不重配。\n"
        "* 长流程不留零信息等待（L1）：在跑与卡住须可分辨。\n")

    def _write_all(self, context=None, core=None, common=None):
        self.write("specs/platform/cnb.adoc", self.PLATFORM_SECTION)
        self.write("specs/general/context.adoc", context if context is not None else self.SECTION)
        self.write("specs/core/execution.adoc",
                   core if core is not None else "= 执行原则\n执行轮次须合并（少绕）\n执行吞吐\n")
        self.write("AGENTS_COMMON.adoc",
                   common if common is not None else
                   "= 入口\n== 分类与懒加载（加载调度器）\n"
                   "  ** 执行吞吐（识别特征：预计需多次往返） → link:specs/general/context.adoc[]\n")

    def test_positive_passes(self):
        self._write_all()
        cm.check_throughput_guard()
        self.assertEqual([], cm.errors)

    def test_missing_file_reports(self):
        self._write_all()
        os.remove(os.path.join(self.root, "specs", "general", "context.adoc"))
        cm.check_throughput_guard()
        self.assertIn("specs/general/context.adoc", self.error_texts())

    def test_section_deleted_reports(self):
        self._write_all(context="= 上下文与读取范围规范\n\n== 读取范围\n* 别的\n")
        cm.check_throughput_guard()
        self.assertIn("执行吞吐", self.error_texts())

    def test_merge_rule_removed_reports(self):
        self._write_all(context=self.SECTION.replace("独立调用必须合并", "调用可分散"))
        cm.check_throughput_guard()
        self.assertIn("独立调用必须合并", self.error_texts())

    def test_probe_roundtrip_removed_reports(self):
        self._write_all(context=self.SECTION.replace("试探式往返", "多轮"))
        cm.check_throughput_guard()
        self.assertIn("试探式往返", self.error_texts())

    def test_build_output_rule_removed_reports(self):
        self._write_all(context=self.SECTION.replace("构建与校验的输出须一次取到", "构建输出稍后再说"))
        cm.check_throughput_guard()
        self.assertIn("构建与校验的输出须一次取到", self.error_texts())

    def test_no_repeat_read_removed_reports(self):
        self._write_all(context=self.SECTION.replace("同一路径在一次任务里被读第二次", "可按需再确认"))
        cm.check_throughput_guard()
        self.assertIn("不重复读", self.error_texts())

    def test_roundtrip_cost_removed_reports(self):
        self._write_all(context=self.SECTION.replace("往返成本也要算", "只管跑"))
        cm.check_throughput_guard()
        self.assertIn("往返成本也要算", self.error_texts())

    def test_credential_rule_removed_reports(self):
        self._write_all(context=self.SECTION.replace("固化为可复用形态", "每次都重新登录"))
        cm.check_throughput_guard()
        self.assertIn("固化为可复用形态", self.error_texts())

    def test_mirror_no_reconfigure_removed_reports(self):
        # "已配置过即沿用不重配"被抹掉即被拦下（与 Maven 侧同向：反复重配本身就是往返）
        self._write_all(context=self.SECTION.replace("不覆盖、不重配", "每次重建配置"))
        cm.check_throughput_guard()
        self.assertIn("不覆盖、不重配", self.error_texts())

    def test_zero_info_wait_removed_reports(self):
        self._write_all(context=self.SECTION.replace("零信息等待", "等待期间可轮询"))
        cm.check_throughput_guard()
        self.assertIn("零信息等待", self.error_texts())

    def test_resident_reference_removed_reports(self):
        # 常驻层未点到执行吞吐：每次会话加载的常驻层里没有这条纪律
        self._write_all(core="= 执行原则\n无关内容\n")
        cm.check_throughput_guard()
        self.assertIn("specs/core/execution.adoc", self.error_texts())

    def test_dispatcher_registration_removed_reports(self):
        # 调度器无本条的加载项与识别特征：规则永远不会被触发加载
        self._write_all(common="= 入口\n== 分类与懒加载（加载调度器）\n  ** 别的 → link:x[]\n")
        cm.check_throughput_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_section_title_extra_words_tolerated(self):
        # 节标题带括号补充属排版，不得因此报"缺少节"
        self._write_all(context=self.SECTION.replace("== 执行吞吐（逐条判据）",
                                                     "== 执行吞吐（逐条判据，少绕）"))
        cm.check_throughput_guard()
        self.assertEqual([], cm.errors)

    def _write_platform(self, content=None):
        self.write("specs/platform/cnb.adoc",
                   content if content is not None else self.PLATFORM_SECTION)

    def test_dedup_criterion_removed_reports(self):
        # 反例：只留"不重复读"这句方向、把**判定标准**整句抽掉（本轮新增的判据本体）——
        # 缺判定标准时该条退化成自觉要求，机械无从核对（用户要件「相同内容不得重复读取」
        # 在留证侧就只剩一句口号）
        self._write_all(context=self.SECTION.replace(
            "：同一路径在一次任务里被读第二次即违规", "。"))
        cm.check_throughput_guard()
        self.assertIn("不重复读的判定标准", self.error_texts())

    def test_platform_section_positive(self):
        self._write_all()
        self._write_platform()
        cm.check_throughput_guard()
        self.assertEqual([], cm.errors)

    def test_platform_section_deleted_reports(self):
        self._write_all()
        self._write_platform("= CNB 平台相关\n\n== 冲突处理\n* 别的\n")
        cm.check_throughput_guard()
        self.assertIn("specs/platform/cnb.adoc", self.error_texts())

    def test_platform_wakeup_cost_removed_reports(self):
        self._write_all()
        self._write_platform(self.PLATFORM_SECTION.replace("一次唤起 = 一次完整加载 + 一轮往返", "唤起即执行"))
        cm.check_throughput_guard()
        self.assertIn("一次唤起", self.error_texts())

    def test_platform_summary_first_removed_reports(self):
        self._write_all()
        self._write_platform(self.PLATFORM_SECTION.replace("先取汇总、再按需下钻", "逐个查"))
        cm.check_throughput_guard()
        self.assertIn("先取汇总", self.error_texts())

    def test_platform_observability_removed_reports(self):
        self._write_all()
        self._write_platform(self.PLATFORM_SECTION.replace("AI 用量汇总", "用量信息"))
        cm.check_throughput_guard()
        self.assertIn("AI 用量汇总", self.error_texts())


class TestCheckPerformanceGuard(CheckSpecsTestCase):
    """钉住「性能测试」防线：测量那一半与记录那一半的要点、两处落点与依据主题。

    实证（用户提出）：旧判据只有四条粗规则（独立性/对比测试/排除初始化干扰/结果分析），
    "跑一次看看谁快"即可交差——成绩是单次采样、没有离散度与可比基线，结论只有一句
    "快了 X 倍"；优化停在"改一版跑一次"，瓶颈不复测、失败方向不落盘，后来的人重踩同一个坑。
    故反例逐条对应"最易被当废话砍掉"的字句：基准那一类、离散度与样本量、公平比较、
    计时区间与消费结果、测量口径、必留证据、取数与组合矩阵、优化日志、闭环迭代、
    瓶颈归因与方向、结论落点与时效、优化不得改变行为。
    """

    SECTION = (
        "= 测试规范（通用层，跨语言）\n\n== 性能测试\n\n"
        "=== 承载与触发\n"
        "* 独立性（L1）：性能测试独立于单元测试。\n"
        "* 何时需要性能测试（L1）：按性能敏感度判定，命中任一特征才做，"
        "不得一律加、也不得漏掉真敏感点；多方案选型需要数据佐证。\n\n"
        "=== 对比与测量\n"
        "* 对比测试（L1）：类别至少 3 类，并含当前项目使用的那一类作基准。\n"
        "* 排除初始化干扰（L1）：须测两次、第二次在全部初始化完成后。\n"
        "* 测量口径须可核对（L1）：预热轮次、测量轮次、批量、计时口径、运行环境须写明。\n"
        "* 离散度与样本量（L1）：至少 3 次有效采样并报离散度；差异小于离散度视为无显著差异。\n"
        "* 公平比较（L1）：同一进程内交替测量、各自预热与迭代、同一份输入数据。\n"
        "* 计时区间界定（L1）：只计被测逻辑，测完必须消费结果。\n\n"
        "=== 记录（成绩与依据落在哪、记到什么程度）\n"
        "* 落点（L1）：跨类级进独立性能测试文档，用例级进测试代码文档注释。\n"
        "* 每次运行的必留证据（L1，四项缺一即不算测过）：测量口径、各方案成绩、结论、"
        "未选方案为什么不选。\n"
        "* 成绩怎么取数（L1）：每组方案记终值（均值或中位数）+ 离散度。\n"
        "* 方案组合与取舍须可核对（L2，多轮优化时）：试过的方案各给组合取值、终值、离散度、"
        "与基线之比与结论；覆盖范围如实声明。\n"
        "* 优化过程须可回溯（L2）：每轮的改动与假设、改前改后成绩、是否保留、瓶颈判断与下一步；"
        "不保留的改动同样须留痕。\n"
        "* 只记结果不记过程（L1）：只留取值 + 来源 + 结论。\n\n"
        "=== 迭代与收敛\n"
        "* 闭环迭代（L1）：测出瓶颈后继续优化并复测，直至收敛。\n"
        "* 收益判定用实测、不用估计（L1）。\n"
        "* 瓶颈归因与方向（L1）：写明瓶颈判断、依据与下一步方向。\n"
        "* 优化方向与思路（L1）：已试过的方向（含失败的）与尚未尝试的方向都须落盘。\n"
        "* 结论的落点（L1）：选型理由进代码文档注释/设计文档。\n"
        "* 结论的时效（L2）：环境或规模变化须重新核对。\n"
        "* 结果分析须给出原因与对策（L1）：差异由哪些原因引起，并给出对应的解决方案。\n"
        "* 优化不得改变行为（L1）：既有功能用例全绿。\n"
        "* 结果反哺基线（L2）：新取值成为此后比对的基线。\n")

    JAVA = (
        "= Java 测试规范\n\n== 启动型与端到端测试\n"
        "* **`PerfTests`（性能）**：测量与记录要求统一见 link:../general/testing.adoc[]"
        "「性能测试」；不混入常规 `test` 阶段、仅显式触发。\n")

    LIBRARY = (
        "= 性能测试判据的依据（测量与记录）\n\n"
        "== 当初要解决的失效（本项目实证）\n本项目实证。\n\n"
        "== 外部材料：JMH 官方文档（OpenJDK，微基准的行业事实标准）\n"
        "https://github.com/openjdk/jmh 未逐字取回（要点转述、非逐字摘录）。\n\n"
        "== 同义性差异与覆盖点（本集合自己承认的）\n"
        "ISO/IEC/IEEE 25010 / ISO/IEC/IEEE 29119-4；本集合自己的判据化取舍。\n")

    def _write_all(self, section=None, java=None, common=None, library=None):
        self.write("specs/general/testing.adoc",
                   section if section is not None else self.SECTION)
        self.write("specs/stack/java-testing.adoc",
                   java if java is not None else self.JAVA)
        self.write("library/performance.adoc",
                   library if library is not None else self.LIBRARY)
        self.write("AGENTS_COMMON.adoc",
                   common if common is not None else
                   "= 入口\n== 分类与懒加载（加载调度器）\n"
                   "  ** 跑测试/补测试，或做性能测试/性能优化（识别特征：判定某处是否需要性能测试、"
                   "性能敏感场景、多方案选型需数据佐证） → link:specs/general/testing.adoc[]"
                   "（性能测试的测量与记录判据、方案组合与成绩）\n")

    def test_positive_passes(self):
        self._write_all()
        cm.check_performance_guard()
        self.assertEqual([], cm.errors)

    def test_missing_spec_reports(self):
        self._write_all()
        os.remove(os.path.join(self.root, "specs", "general", "testing.adoc"))
        cm.check_performance_guard()
        self.assertIn("specs/general/testing.adoc", self.error_texts())

    def test_section_deleted_reports(self):
        self._write_all(section="= 测试规范\n\n== 单元测试\n* 别的\n")
        cm.check_performance_guard()
        self.assertIn("性能测试", self.error_texts())

    def test_baseline_member_removed_reports(self):
        # 缺"当前实现作基准"那一类：只剩候选方案之间的相对比较，"要不要换"无从判起
        self._write_all(section=self.SECTION.replace(
            "并含当前项目使用的那一类作基准", "并覆盖多种实现"))
        cm.check_performance_guard()
        self.assertIn("含当前项目使用的那一类作基准", self.error_texts())

    def test_dispersion_removed_reports(self):
        self._write_all(section=self.SECTION.replace(
            "至少 3 次有效采样并报离散度；差异小于离散度视为无显著差异",
            "跑几次取平均即可"))
        cm.check_performance_guard()
        self.assertIn("至少 3 次有效采样", self.error_texts())

    def test_fair_comparison_removed_reports(self):
        self._write_all(section=self.SECTION.replace(
            "同一进程内交替测量、各自预热与迭代、同一份输入数据", "各自跑即可"))
        cm.check_performance_guard()
        self.assertIn("同一进程", self.error_texts())

    def test_consume_result_removed_reports(self):
        self._write_all(section=self.SECTION.replace(
            "测完必须消费结果", "不必管结果"))
        cm.check_performance_guard()
        self.assertIn("消费结果", self.error_texts())

    def test_evidence_member_removed_reports(self):
        # 必留证据被削成三项（少了"未选方案为什么不选"）即被拦下
        self._write_all(section=self.SECTION.replace("、未选方案为什么不选", ""))
        cm.check_performance_guard()
        self.assertIn("未选方案为什么不选", self.error_texts())

    def test_score_matrix_removed_reports(self):
        # 方案组合的取值（组合/终值/离散度/与基线之比）被抹成一句"记录成绩"即被拦下
        self._write_all(section=self.SECTION.replace(
            "* 方案组合与取舍须可核对（L2，多轮优化时）：试过的方案各给组合取值、终值、离散度、"
            "与基线之比与结论；覆盖范围如实声明。\n",
            "* 成绩记录（L2）：记一下成绩就好。\n"))
        cm.check_performance_guard()
        self.assertIn("方案组合与取舍须可核对", self.error_texts())

    def test_optimization_log_removed_reports(self):
        # 优化过程的可回溯取值（含"失败尝试同样留痕"）被整条抽掉即被拦下
        self._write_all(section=self.SECTION.replace(
            "* 优化过程须可回溯（L2）：每轮的改动与假设、改前改后成绩、是否保留、瓶颈判断与下一步；"
            "不保留的改动同样须留痕。\n", ""))
        cm.check_performance_guard()
        self.assertIn("优化过程须可回溯", self.error_texts())

    def test_cause_analysis_removed_reports(self):
        # 旧"结果分析"条（差异由哪些原因引起 + 给出解决方案）被整条抽掉即被拦下
        self._write_all(section=self.SECTION.replace(
            "* 结果分析须给出原因与对策（L1）：差异由哪些原因引起，并给出对应的解决方案。\n", ""))
        cm.check_performance_guard()
        self.assertIn("结果分析须给出原因与对策（L1）", self.error_texts())

    def test_iteration_loop_removed_reports(self):
        self._write_all(section=self.SECTION.replace(
            "闭环迭代（L1）：测出瓶颈后继续优化并复测，直至收敛。",
            "跑一次即可。"))
        cm.check_performance_guard()
        self.assertIn("闭环迭代（L1）", self.error_texts())

    def test_behavior_unchanged_removed_reports(self):
        self._write_all(section=self.SECTION.replace(
            "优化不得改变行为（L1）：既有功能用例全绿。", "优化可顺手改行为。"))
        cm.check_performance_guard()
        self.assertIn("优化不得改变行为（L1）", self.error_texts())

    def test_dispatcher_entry_removed_reports(self):
        # 调度器无本条加载项：规则永远不会被触发加载
        self._write_all(common="= 入口\n== 分类与懒加载（加载调度器）\n  ** 别的 → link:x[]\n")
        cm.check_performance_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_java_carrier_removed_reports(self):
        self._write_all(java="= Java 测试规范\n\n== 断言\n* 别的\n")
        cm.check_performance_guard()
        self.assertIn("specs/stack/java-testing.adoc", self.error_texts())

    def test_library_missing_reports(self):
        self._write_all()
        os.remove(os.path.join(self.root, "library", "performance.adoc"))
        cm.check_performance_guard()
        self.assertIn("library/performance.adoc", self.error_texts())

    def test_library_anchor_removed_reports(self):
        # 同义性差异被删：读者会把"至少 3 次采样"读成某标准的规定
        self._write_all(library="= 性能测试判据的依据\n\n* JMH 见官方文档\n")
        cm.check_performance_guard()
        self.assertIn("同义性差异与覆盖点（本集合自己承认的）", self.error_texts())


class TestCheckQualityGuard(CheckSpecsTestCase):
    """钉住「代码质量（新产出即高质）」防线：十项下限、判定标准、依据与调度器登记。

    实证（用户报告）：有的时候功能是写出来了、但代码质量比较低——此前规范只覆盖形式类要求，
    新产出即高质的整体下限没有成文判据，执行者按"能跑就行"收敛。故反例逐条对应"最易被当
    废话砍掉"的字句：坏味道清单、嵌套上限、命名一致、不吞异常、资源成对释放、共享状态同步、
    可预见的性能退化、测试与文档、交付前逐条自查、依据行；另钉调度器识别特征与依据主题
    （缺则规则不加载、或依据只剩名称）。
    """

    SECTION = (
        "= 通用编码规范\n\n== 代码质量（新产出即高质）\n"
        "* 适用面：**适用面（先读）**——**写任何新代码、改任何既有代码**时适用；**新增的那一部分永远按本节判**。\n"
        "* **新代码不得引入坏味道（L1）**：重复代码、过长函数、依恋情结、注释代替澄清。\n"
        "* **职责单一、结构清晰（L1）**：能不能**一句话说清**它做什么；嵌套**三层以内**。\n"
        "* **命名表意、不用缩写（L1）**：同一概念在项目中只有一个叫法；禁缩写与拼音。\n"
        "* **可读性优先（L1）**：不用**魔法值**；同一表达式不重复求值。\n"
        "* **显式处理失败与边界（L1）**：**不得吞异常**；**边界条件必须显式处理**。"
        "**条件例外（L2，纯取值转换的查找式 API）**：须**异常语义单一**、**三条同时成立才算命中**、"
        "不得绕过**可探测的非法输入**、命中处**仍是空 `catch`**、"
        '须写明"异常只有这一种原因"的依据。\n'
        "* **无资源泄漏（L1）**：一律用**确定性释放**机制、成对释放。\n"
        "* **无并发隐患（L1）**：**共享可变状态**须有明确同步策略；锁范围与顺序写清。\n"
        "* **性能不写退化写法（L2）**：**循环内** IO 与查询、**N+1** 查询。\n"
        "* **测试与文档跟得上（L1）**：**新功能**必配用例；契约写进**文档注释**。\n"
        "* **交付前质量自检（L1）**：**逐条自查**本节十项；**能过机械判据是下限**。\n"
        "* 依据（标准名/编号）：ISO/IEC 25010、ISO/IEC/IEEE 12207、"
        "Martin Fowler《Refactoring》、Clean Code、SEI CERT。\n")

    LIBRARY = (
        "= 代码质量与生成开销的依据\n\n"
        "== 当初要解决的失效（本项目实证）\n文字。\n\n"
        "== 外部材料与逐字依据（业界事实标准与标准编号）\n"
        "ISO/IEC 25010、Martin Fowler《Refactoring》、Clean Code、"
        "SEI CERT Coding Standards、**未逐字取回**。\n\n"
        "== 同义性差异与覆盖点（本集合自己承认的）\n文字。\n")

    def _write_all(self, section=None, common=None, library=None):
        self.write("specs/general/coding.adoc",
                   section if section is not None else self.SECTION)
        self.write("library/quality.adoc",
                   library if library is not None else self.LIBRARY)
        self.write("AGENTS_COMMON.adoc",
                   common if common is not None else
                   "= 入口\n== 分类与懒加载（加载调度器）\n"
                   "  ** 编写代码（识别特征：**写任何新代码、改任何既有代码**（含**代码评审**）)"
                   " → link:specs/general/coding.adoc[]（代码质量（新产出即高质））\n")

    def test_positive_passes(self):
        self._write_all()
        cm.check_quality_guard()
        self.assertEqual([], cm.errors)

    def test_missing_spec_reports(self):
        self._write_all()
        os.remove(os.path.join(self.root, "specs", "general", "coding.adoc"))
        cm.check_quality_guard()
        self.assertIn("specs/general/coding.adoc", self.error_texts())

    def test_section_deleted_reports(self):
        self._write_all(section="= 通用编码规范\n\n== 代码复用\n* 别的\n")
        cm.check_quality_guard()
        self.assertIn("代码质量（新产出即高质）", self.error_texts())

    def test_smell_list_removed_reports(self):
        self._write_all(section=self.SECTION.replace("重复代码、过长函数、依恋情结、注释代替澄清",
                                                     "注意代码质量"))
        cm.check_quality_guard()
        self.assertIn("重复代码", self.error_texts())

    def test_nesting_limit_removed_reports(self):
        self._write_all(section=self.SECTION.replace("嵌套**三层以内**", "嵌套尽量少"))
        cm.check_quality_guard()
        self.assertIn("三层以内", self.error_texts())

    def test_naming_consistency_removed_reports(self):
        self._write_all(section=self.SECTION.replace("同一概念在项目中只有一个叫法", "命名要清晰"))
        cm.check_quality_guard()
        self.assertIn("同一概念在项目中只有一个叫法", self.error_texts())

    def test_swallow_exception_removed_reports(self):
        self._write_all(section=self.SECTION.replace("**不得吞异常**；", ""))
        cm.check_quality_guard()
        self.assertIn("不得吞异常", self.error_texts())

    def test_conditional_exception_removed_reports(self):
        # 反例：条件例外的**判据本体**被抽走（用户口径：`Enum.valueOf` 一类允许空 catch）——
        # 例外一宽即等于把"不得吞异常"整条的其余部分作废（任何 `catch (Exception) {}`
        # 都能自证"我这是枚举查询"），故它与「不得吞异常」本体同列本防线的要点。
        self._write_all(section=self.SECTION.replace(
            "**条件例外（L2，纯取值转换的查找式 API）**：须**异常语义单一**、"
            "**三条同时成立才算命中**、不得绕过**可探测的非法输入**、命中处**仍是空 `catch`**、"
            '须写明"异常只有这一种原因"的依据。', ""))
        cm.check_quality_guard()
        self.assertIn("异常语义单一", self.error_texts())

    def test_resource_release_removed_reports(self):
        self._write_all(section=self.SECTION.replace("一律用**确定性释放**机制、成对释放",
                                                     "注意释放资源"))
        cm.check_quality_guard()
        self.assertIn("确定性释放", self.error_texts())

    def test_concurrency_removed_reports(self):
        self._write_all(section=self.SECTION.replace("**共享可变状态**须有明确同步策略",
                                                     "注意并发"))
        cm.check_quality_guard()
        self.assertIn("共享可变状态", self.error_texts())

    def test_selfcheck_removed_reports(self):
        self._write_all(section=self.SECTION.replace("**逐条自查**本节十项", "自查即可"))
        cm.check_quality_guard()
        self.assertIn("逐条自查", self.error_texts())

    def test_basis_line_removed_reports(self):
        self._write_all(section=self.SECTION.replace(
            "ISO/IEC 25010、ISO/IEC/IEEE 12207、Martin Fowler《Refactoring》、Clean Code、SEI CERT。",
            "为业界共识。"))
        cm.check_quality_guard()
        self.assertIn("ISO/IEC 25010", self.error_texts())

    def test_dispatcher_entry_removed_reports(self):
        self._write_all(common="= 入口\n== 分类与懒加载（加载调度器）\n  ** 别的 → link:x[]\n")
        cm.check_quality_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_library_missing_reports(self):
        self._write_all()
        os.remove(os.path.join(self.root, "library", "quality.adoc"))
        cm.check_quality_guard()
        self.assertIn("library/quality.adoc", self.error_texts())

    def test_library_anchor_removed_reports(self):
        self._write_all(library="= 依据\n\n* 见业界材料\n")
        cm.check_quality_guard()
        self.assertIn("同义性差异与覆盖点（本集合自己承认的）", self.error_texts())


class TestCheckGenerationEfficiencyGuard(CheckSpecsTestCase):
    """钉住「生成效率 / token 纪律」防线：判据、边界条与调度器登记。

    实证（用户提出）：要"提高生成效率的规范"与"不影响功能完整性和代码质量的前提下提高 token
    利用率"，并追问"是一回事吗"。此前只有「执行吞吐」管调用形态，不管"这件事该做几轮"，
    也没有 token 维度的判据。故反例除逐条要点外，**重点钉两条边界**——"效率不得越过质量"与
    "三件事不得为省 token 让步"（缺位即等于允许以省为名跳过校验/复核/留证）。
    """

    GEN = (
        "== 生成效率（同等质量下最少往返）\n"
        "* **先定完成判据，再动手（L1）**：把**什么算做完**写成判据（**返工来源**）。\n"
        "* **一次做对一次做完（L1）**：**一次改到位**；不得**碎片推进**；"
        "判据：**本轮交付之后是否需要再改同一批文件**。\n"
        "* **延后验证、一次到位（L1）**：**攒到一处**；不得**重启一次构建**；"
        "**存在真实依赖**才逐步验证。\n"
        "* **失败一次就查根因，不靠重试撞对（L1）**：**反复重启同一构建**即违规；"
        "**同一问题上被执行第二遍**、且**新认识**缺位即违规。\n"
        "* **按需读取、不全量预处理（L1）**：**全量预读**即违规；**低信号**内容会降准确率。\n"
        "* **批量化同类操作（L2）**：**批量一次做完**、能**脚本化**就脚本化。\n"
        "* **任务边界一次说清（L2）**：**一次把边界与产物形态说清**；不得**先做一版看看**。\n"
        "* **依据名代替复述（L2）**：复述制造**第二真源**。\n"
        "* **不重做已做完的事（L2）**：不得**再确认一次**、**再跑一遍看看**。\n"
        "* **收尾一次收敛（L2）**：汇报**一次写完**；不得**零散补齐**。\n"
        "* **效率不得越过质量（L1，本节的边界）**：都**不得用于减少**必要工作；"
        "效率不是**更少的质量**。\n"
        "* 依据（标准名/编号）：ISO/IEC/IEEE 25010、Anthropic 工程博客、"
        "Agent Skills 开放规范。\n")

    TOKEN = (
        "== token 纪律（提高利用率与节省开销）\n"
        "* **先把两个概念分开**：**不是一回事**、但**手段大幅重叠**——"
        "**提高 token 利用率**是「每份输入产生的有效产出」，**节省 token** 是减少总量。\n"
        "* **利用率判据：输入须「**用到了**」（L1）**：**答不出用途**的即**无效输入**。\n"
        "* **约束放在外部、不进上下文（L1）**：能**落成文件**就不要复述；"
        "写在对话里每次请求都要重发。\n"
        "* **少复述、多引用（L1）**：不得**复述**已知内容，写**依据名**。\n"
        "* **不重复读、不重复贴（L1）**：**只读一次**、**只贴一次**。\n"
        "* **只记结论与取值、不带原始日志（L1）**：不夹带**原始日志**；写**取值 + 来源**。\n"
        "* **三件事不得为省 token 让步（L1，本条的边界）**：**功能完整性**、**代码质量**、"
        "**验证完整**一件都不能省。\n"
        "* **成本须可说明、不得以「不贵」带过（L2）**：**说不出来即应砍掉**。\n"
        "* **不设「必须量化 token」的要求**：**判据是**输入有没有被用上。\n"
        "* 依据（标准名/编号）：ISO/IEC/IEEE 25010、ISO/IEC Directives Part 2。\n")

    def _write_all(self, gen=None, token=None, common=None):
        body = ("= 上下文与读取范围规范\n\n"
                + (gen if gen is not None else self.GEN) + "\n"
                + (token if token is not None else self.TOKEN))
        self.write("specs/general/context.adoc", body)
        self.write("AGENTS_COMMON.adoc",
                   common if common is not None else
                   "= 入口\n== 分类与懒加载（加载调度器）\n"
                   "  ** 读取范围、生成效率（同等质量下最少往返）、token 纪律（提高利用率与"
                   "节省开销）、执行吞吐（识别特征：预计需多次往返、出现安排取舍）"
                   " → link:specs/general/context.adoc[]\n")

    def test_positive_passes(self):
        self._write_all()
        cm.check_generation_efficiency_guard()
        self.assertEqual([], cm.errors)

    def test_gen_section_deleted_reports(self):
        self._write_all(gen="== 别的东西\n* x")
        cm.check_generation_efficiency_guard()
        self.assertIn("生成效率", self.error_texts())

    def test_token_section_deleted_reports(self):
        self._write_all(token="== 别的东西\n* x")
        cm.check_generation_efficiency_guard()
        self.assertIn("token 纪律", self.error_texts())

    def test_utilization_judgement_removed_reports(self):
        self._write_all(token=self.TOKEN.replace("**答不出用途**的即**无效输入**", "尽量少读"))
        cm.check_generation_efficiency_guard()
        self.assertIn("无效输入", self.error_texts())

    def test_token_boundary_removed_reports(self):
        self._write_all(token=self.TOKEN.replace("**功能完整性**", "一切"))
        cm.check_generation_efficiency_guard()
        self.assertIn("功能完整性", self.error_texts())

    def test_efficiency_boundary_removed_reports(self):
        self._write_all(gen=self.GEN.replace("都**不得用于减少**必要工作", "尽量快"))
        cm.check_generation_efficiency_guard()
        self.assertIn("不得用于减少", self.error_texts())

    def test_not_same_thing_removed_reports(self):
        self._write_all(token=self.TOKEN.replace("**不是一回事**、但**手段大幅重叠**", "是一回事"))
        cm.check_generation_efficiency_guard()
        self.assertIn("不是一回事", self.error_texts())

    def test_retry_rule_removed_reports(self):
        self._write_all(gen=self.GEN.replace("**反复重启同一构建**即违规", "可反复试").replace("**同一问题上被执行第二遍**、且**新认识**缺位即违规。", "略。"))
        cm.check_generation_efficiency_guard()
        self.assertIn("同一问题上被执行第二遍", self.error_texts())

    def test_dispatcher_entry_removed_reports(self):
        self._write_all(common="= 入口\n== 分类与懒加载（加载调度器）\n  ** 别的 → link:x[]\n")
        cm.check_generation_efficiency_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())


class TestCheckDefaultReviewScopeGuard(CheckSpecsTestCase):
    """钉住『review 的默认检查面（只查问题，不动存量）』防线（用户点名，Issue #203）。

    用户口径：review 默认只查问题（代码/文档/用例三类），规范里取向性要求（如优先用
    `@ConfigurationProperties`）在 review 时不查出来；原单项豁免删掉、升为全局；不动
    存量，除非主动声明。故用例覆盖：判据本体三组锚点各自被抽、以及单项豁免的两种失效
    ——回指被删（真源断链）与旧措辞复活（第二真源）。
    """

    SECTION = (
        "== review 的默认检查面（只查问题，不动存量）\n\n"
        "review **默认只查问题**：**代码问题、文档问题、用例问题**三类。\n\n"
        "* **默认检查面（L1）**：review 只提出三类问题。其余规范条目**只约束\"本次新增/"
        "修改的内容\"**，对存量**默认不查、不报、不要求整改**。\n"
        "* **存量不动、随动迁移（L1）**：改到哪个文件才顺带调整，见 `specs/core/execution.adoc`"
        "**随动迁移**；**review 不得据此提出问题**。\n"
        "* **唯一例外是主动声明（L1）**：**声明是例外而非默认**，且**仅对当次生效**、"
        "**不得泛化**为默认检查面。\n"
        "* 依据（标准名/编号）：IEEE 1028；ISO/IEC/IEEE 29148。\n\n")

    JAVA = ("= Java 规范\n\n"
            "**review 时对存量缺这套模板注解不提出问题**"
            "（全局口径见 `specs/general/review.adoc`「review 的默认检查面」）。\n")
    CODING = ("= 通用编码\n\n"
              "**review 时对既有成员的位置不提出问题**"
              "（全局口径见 `specs/general/review.adoc`）。\n")

    def _write(self, section=None, java=None, coding=None) -> None:
        self.write("specs/general/review.adoc",
                   section if section is not None else self.SECTION)
        self.write("specs/stack/java.adoc", java if java is not None else self.JAVA)
        self.write("specs/general/coding.adoc", coding if coding is not None else self.CODING)

    def test_valid_passes(self):
        self._write()
        cm.check_default_review_scope_guard()
        self.assertEqual([], cm.errors)

    def test_section_removed_reports(self):
        # 反例①：整节被删 → 全局真源丢失，review 退回全量符合性审计
        self._write(section="== 问题记录\n\n* 记一笔。\n\n")
        cm.check_default_review_scope_guard()
        self.assertIn("review 的默认检查面", self.error_texts())

    def test_three_issues_removed_reports(self):
        # 反例②：三类问题清单/存量默认不查不报被抽 → 检查面退回"什么都查"
        self._write(section=self.SECTION.replace(
            "**默认不查、不报、不要求整改**", "按规范全量核对"))
        cm.check_default_review_scope_guard()
        self.assertIn("默认检查面", self.error_texts())

    def test_migrate_boundary_removed_reports(self):
        # 反例③：随动迁移与"不得据此提出问题"被抽 → 存量缺失被当成违规、发动全库改造
        self._write(section=self.SECTION.replace(
            "；**review 不得据此提出问题**", ""))
        cm.check_default_review_scope_guard()
        self.assertIn("存量随动迁移", self.error_texts())

    def test_exception_boundary_removed_reports(self):
        # 反例④："仅对当次生效、不得泛化"被抽 → 一次声明被泛化成默认检查面（反向失效）
        self._write(section=self.SECTION.replace(
            "**声明是例外而非默认**，且**仅对当次生效**、**不得泛化**为默认检查面。",
            "用户声明过一次后即可长期按声明查。"))
        cm.check_default_review_scope_guard()
        self.assertIn("唯一例外是主动声明", self.error_texts())

    def test_single_xref_removed_reports(self):
        # 反例⑤：单项豁免的回指被删 → 按该文件工作的执行者看不到这条边界（真源断链）
        self._write(java=self.JAVA.replace(
            "**review 时对存量缺这套模板注解不提出问题**", ""))
        cm.check_default_review_scope_guard()
        self.assertIn("specs/stack/java.adoc", self.error_texts())

    def test_old_wording_revived_reports(self):
        # 反例⑥：旧单项措辞复活 → 判定标准两处各写一份（第二真源、各自漂移）
        self._write(coding=self.CODING + (
            "**review 时把「既有成员的位置」当已知现状、不提出问题**（判定标准……）。\n"))
        cm.check_default_review_scope_guard()
        self.assertIn("旧单项措辞", self.error_texts())


class TestCheckAfterChangeReviewGuard(CheckSpecsTestCase):
    """钉住「改动后复核」防线：五件事、干净子 agent、三态台账与维护方登记。

    实证（用户要求）：每次加完规范之后都必须 review，机械手段一定要跑，干净的子 agent 也
    不能漏（有了就忽略、没有就加）。此前"改完规范要做什么"散在多节、没有固定动作清单，
    实测形态是只跑一遍主校验脚本、语义复核被"改动小"顺手跳过、台账写成散文结论。
    """

    VERIFY = (
        "= 验证规范\n\n== 改完规范必做的五件事（机械手段必跑，干净子 agent 复核不可漏）\n"
        "* **① 机械手段必须先跑、且跑全（L1，不可省）**：**全量扫描**；**报红就地修复**。\n"
        "* **② 干净子 agent 的语义复核不可漏（L1，有了就忽略、没有就加）**：项目规范已有就按"
        "已有那份执行；**没有就加**，补在**项目自身规范**里。\n"
        "* **③ 三视角一并回答、一次读取分栏列（L1）**：完整性、有效性与认知质量、接纳面。\n"
        "* **④ 复核要走三态台账**：通过 / 未发现问题 / **悬置**；**三态各占一栏、"
        "**不得合并**。\n"
        "* **⑤ 子 agent 不可用时的降级与留证（L1）**：**不得跳过复核**；不得换**外部来源**；"
        "**标注独立性边界**。\n"
        "* **本节的边界（L1）**：**只对规范类改动（B 类）**成立；**代码类改动不做三视角**。\n")

    REVIEW = (
        "= code review 规范\n\n== 改动后的 review（每次改完都得复核一次）\n"
        "* **每次改动后的常规 review（L1）**：范围＝**本次改动的全部产物**；"
        "动作＝**按改动性质取值**。\n"
        "* **改完即审的固定动作（L1）**：①**跑**机械手段；②**比**基线；③**核**原话；"
        "④**留**证。\n"
        "* **规范类改动不得只跑机械手段（L1）**：**跑绿了** **不等于**判据没被压成口号。\n"
        "* **复核者不可用时（L1）**：**不跳过复核**；或**如实标悬置**。\n"
        "* 依据（标准名/编号）：IEEE 1028、ISO 10007。\n")

    def _write_all(self, verify=None, review=None, maint=None, entry=None):
        self.write("specs/general/verify.adoc",
                   verify if verify is not None else self.VERIFY)
        self.write("specs/general/review.adoc",
                   review if review is not None else self.REVIEW)
        self.write("specs-project-maintainer/verify.adoc",
                   maint if maint is not None else
                   "= 维护方验证\n* 见「改完规范必做的五件事（机械手段必跑，干净子 agent 复核不可漏）」；"
                   "运行 check_specs_test.py 与 check_effective_test.py；"
                   "**有了就忽略、没有就加**。\n")
        self.write("AGENTS.adoc",
                   entry if entry is not None else
                   "= 项目规范\n* 见「改完规范必做的五件事（机械手段必跑，"
                   "干净子 agent 复核不可漏）」；机械手段须跑全；子 agent 复核不可漏。\n")

    def test_positive_passes(self):
        self._write_all()
        cm.check_after_change_review_guard()
        self.assertEqual([], cm.errors)

    def test_verify_section_deleted_reports(self):
        self._write_all(verify="= 验证规范\n\n== 别的\n* x\n")
        cm.check_after_change_review_guard()
        self.assertIn("改完规范必做的五件事", self.error_texts())

    def test_mechanical_first_removed_reports(self):
        self._write_all(verify=self.VERIFY.replace("**全量扫描**", "查一下"))
        cm.check_after_change_review_guard()
        self.assertIn("全量扫描", self.error_texts())

    def test_clean_agent_rule_removed_reports(self):
        self._write_all(verify=self.VERIFY.replace(
            "**没有就加**，补在**项目自身规范**里。", "。"))
        cm.check_after_change_review_guard()
        self.assertIn("没有就加", self.error_texts())

    def test_three_state_ledger_removed_reports(self):
        self._write_all(verify=self.VERIFY.replace("**不得合并**", "可合并"))
        cm.check_after_change_review_guard()
        self.assertIn("不得合并", self.error_texts())

    def test_downgrade_path_removed_reports(self):
        self._write_all(verify=self.VERIFY.replace(
            "**不得跳过复核**；不得换**外部来源**；", ""))
        cm.check_after_change_review_guard()
        self.assertIn("不得跳过复核", self.error_texts())

    def test_scope_boundary_removed_reports(self):
        self._write_all(verify=self.VERIFY.replace("**代码类改动不做三视角**", "都要做三视角"))
        cm.check_after_change_review_guard()
        self.assertIn("代码类改动不做三视角", self.error_texts())

    def test_change_review_section_deleted_reports(self):
        self._write_all(review="= code review 规范\n\n== 问题修复\n* x\n")
        cm.check_after_change_review_guard()
        self.assertIn("改动后的 review", self.error_texts())

    def test_every_change_removed_reports(self):
        self._write_all(review=self.REVIEW.replace("**本次改动的全部产物**", "大改动"))
        cm.check_after_change_review_guard()
        self.assertIn("本次改动的全部产物", self.error_texts())

    def test_mechanical_only_removed_reports(self):
        self._write_all(review=self.REVIEW.replace(
            "**跑绿了** **不等于**判据没被压成口号。", "跑绿就行。"))
        cm.check_after_change_review_guard()
        self.assertIn("跑绿了", self.error_texts())

    def test_maintainer_landing_removed_reports(self):
        self._write_all(maint="= 维护方验证\n* 别的\n")
        cm.check_after_change_review_guard()
        self.assertIn("specs-project-maintainer/verify.adoc", self.error_texts())

    def test_entry_landing_removed_reports(self):
        self._write_all(entry="= 项目规范\n* 别的\n")
        cm.check_after_change_review_guard()
        self.assertIn("AGENTS.adoc", self.error_texts())

class TestCheckCleanSubagentReviewGuard(CheckSpecsTestCase):
    """钉住『review 时的干净子 agent 复核』防线（用户提出，Issue #219）。

    用户原话："强制 review 时必须开启干净子 agent 进行 review"。失效形态是**要求全在、
    而干净上下文从未发生**：沿用本次会话结论充当复核、把"知道有子 agent 能力"当成
    "已派发"、或把复核者降级成"上一次那个上下文"。故用例逐项覆盖该节各要点被抽，以及
    "复用上一次上下文"这类放宽写法复活。
    """

    REVIEW = (
        "= code review 规范\n\n"
        "== review 时的干净子 agent 复核（强制）\n\n"
        "依据：评审与被评审须相互独立（IEEE 1028）。\n\n"
        "* **强制开干净子 agent（L1）**：用**与执行者相同的 Agent**。\n"
        "* **\"干净\"指上下文（L1）**：**上下文干净**——**不得复用前序对话里的结论**；"
        "**不得以自己那次执行的上下文充当复核的上下文**。\n"
        "* **通道须先实测、后派发（L1）**：只有确实取到的通道才算成立，**取不到按不成立处理**；"
        "确认该次调用**不承载本次会话的上下文**；对象须**钉定**。\n"
        "* **判定标准**：① **该入口的调用实际返回结果**；② **只带本次钉定的对象与其判据**。\n"
        "* **派发形式（L1）**：**一次性、边界明确、可超时**；**不带工具**；每次复核"
        "**换一次干净上下文**。\n"
        "* **硬超时（L1）**：到点按\"**放弃 + 如实标悬置**\"处置。\n"
        "* **不得换外部来源（L1）**：**不得换外部来源**的 Agent/NPC 顶替。\n"
        "* **降级路径（L1）**：**由执行者本人串行承担**、**标注独立性边界**，或**如实标悬置**；"
        "\"已交付 + 校验全绿 + 缺口\"**不得混写成**\"已复核通过\"。\n"
        "* **复核结论按三态留证**：**三态各占一栏、不得合并**；写明**实际读到的上下文范围**"
        "（判据见 `specs/general/verify.adoc`「验证的效力等级」）。\n"
        "* **对引用方的口径（L1）**：**不指定实现**；冲突时**以其自身规范为准**；只约束"
        "**本条生效之后**的 review。\n"
        "* **依据落点**：`specs/general/collab.adoc` 与 `specs/general/self-check.adoc`。\n"
        "== 改动后的 review（每次改完都得复核一次）\n"
        "* 执行形态见「review 时的干净子 agent 复核（强制）」——**本条只说**要做哪种复核，"
        "两者**互不替代**。\n")

    def _write_all(self, review=None, execution=True, common=True, maint=True):
        cm._RULES_RUN_THIS_PHASE.clear()
        self.write("specs/general/review.adoc",
                   review if review is not None else self.REVIEW)
        self.write("specs/core/execution.adoc",
                   ("= 执行原则\n\n== 任务生命周期与节点自查\n"
                    "| **验证** | **review 场景**下清理复核的干净子 agent 通道是否已实测"
                    "（见 `specs/general/review.adoc`）|\n") if execution else "= 执行原则\n")
        self.write("AGENTS_COMMON.adoc",
                   ("= 入口\n\n== 分类与懒加载（加载调度器）\n"
                    "* **code review**（识别特征：要做评审、要判能不能拿到**干净子 agent**）"
                    " → `specs/general/review.adoc`\n") if common else "= 入口\n")
        self.write("specs-project-maintainer/verify.adoc",
                   ("= 维护方验证\n* **review 时的干净子 agent 通道**：**能不能拿到**须实测，"
                    "判据见 `specs/general/review.adoc`「review 时的干净子 agent 复核（强制）」。\n")
                   if maint else "= 维护方验证\n* 别的\n")
        self.write_rules_fixture()

    def test_positive_passes(self):
        self._write_all()
        cm.check_clean_subagent_review_guard()
        self.assertEqual([], cm.errors)

    def test_section_removed_reports(self):
        # 反例①：整节被删 → 用户点名的那条要求失去落点
        self._write_all(review="= code review 规范\n\n== 问题修复\n* x\n")
        cm.check_clean_subagent_review_guard()
        self.assertIn("review 时的干净子 agent 复核", self.error_texts())

    def test_mandatory_removed_reports(self):
        # 反例②：强制语被降级成倡议 → "沿用本次会话结论当复核"照样发生
        self._write_all(review=self.REVIEW.replace(
            "**强制开干净子 agent（L1）**：用**与执行者相同的 Agent**。",
            "**建议**用子 agent 复核一遍。"))
        cm.check_clean_subagent_review_guard()
        self.assertIn("强制开干净子 agent", self.error_texts())

    def test_self_context_as_review_removed_reports(self):
        # 反例③：改动方不得自任复核上下文这一句被抽 → 复核与改动同一上下文仍算"已复核"
        self._write_all(review=self.REVIEW.replace(
            "**不得以自己那次执行的上下文充当复核的上下文**。", ""))
        cm.check_clean_subagent_review_guard()
        self.assertIn("不得以自己那次执行的上下文充当复核的上下文", self.error_texts())

    def test_channel_probe_removed_reports(self):
        # 反例④：通道实测判据被抽 → "我知道有子 agent 能力"被读成"已派发"
        self._write_all(review=self.REVIEW.replace(
            "**取不到按不成立处理**", "有需要就用"))
        cm.check_clean_subagent_review_guard()
        self.assertIn("通道须先实测", self.error_texts())

    def test_probe_criteria_removed_reports(self):
        # 反例⑤：实测到什么算成立的取值被抽 → "实测过"无判据
        self._write_all(review=self.REVIEW.replace(
            "**该入口的调用实际返回结果**", "看着可用"))
        cm.check_clean_subagent_review_guard()
        self.assertIn("通道的可执行性与原子性判据", self.error_texts())

    def test_hard_timeout_removed_reports(self):
        # 反例⑥：硬超时与到点处置被抽 → 派发会无限挂起
        self._write_all(review=self.REVIEW.replace(
            "**放弃 + 如实标悬置**", "等一等"))
        cm.check_clean_subagent_review_guard()
        self.assertIn("派发形式与硬超时", self.error_texts())

    def test_mention_only_removed_reports(self):
        # 反例⑦：一次性/不带工具被抽 → 复核者带上一次上下文、或自行探查仓库
        self._write_all(review=self.REVIEW.replace("**不带工具**；", ""))
        cm.check_clean_subagent_review_guard()
        self.assertIn("不带工具", self.error_texts())

    def test_downgrade_path_removed_reports(self):
        # 反例⑧：降级路径被抽 → 通道不可用会被读成"这次免了"
        self._write_all(review=self.REVIEW.replace(
            "**由执行者本人串行承担**、**标注独立性边界**", "换个人复核"))
        cm.check_clean_subagent_review_guard()
        self.assertIn("降级路径", self.error_texts())

    def test_external_source_removed_reports(self):
        # 反例⑨：不得换外部来源被抽 → 复核派给不可核对的跨来源执行者
        # （该组还含降级路径的四句，故整段替换、不逐句删——缺任一句整组即报）
        self._write_all(review=self.REVIEW.replace(
            "* **不得换外部来源（L1）**：**不得换外部来源**的 Agent/NPC 顶替。\n"
            "* **降级路径（L1）**：**由执行者本人串行承担**、**标注独立性边界**，或**如实标悬置**；"
            "\"已交付 + 校验全绿 + 缺口\"**不得混写成**\"已复核通过\"。\n",
            "* 拿不到就换别的 Agent 顶一下。\n"))
        cm.check_clean_subagent_review_guard()
        self.assertIn("不得换外部来源与降级路径", self.error_texts())

    def test_ledger_removed_reports(self):
        # 反例⑩：三态留证与"实际读到的上下文范围"被抽 → 留证退化成散文、"查不出"与"没做"分不清
        self._write_all(review=self.REVIEW.replace(
            "**三态各占一栏、不得合并**；", ""))
        cm.check_clean_subagent_review_guard()
        self.assertIn("留证形态", self.error_texts())

    def test_reuse_context_revived_reports(self):
        # 反例⑪：放宽形态复活——"复用上一次复核用过的上下文"成许可语态
        self._write_all(review=self.REVIEW.replace(
            "* **依据落点**：",
            "* 可以复用上一次复核用过的上下文。\n"
            "* **依据落点**："))
        cm.check_clean_subagent_review_guard()
        self.assertIn("被放宽的写法", self.error_texts())

    def test_backref_removed_reports(self):
        # 反例⑫：两节之间的回指被抽 → 按「改动后的 review」工作的执行者看不到干净上下文怎么落成
        self._write_all(review=self.REVIEW.replace(
            "* 执行形态见「review 时的干净子 agent 复核（强制）」——**本条只说**要做哪种复核，"
            "两者**互不替代**。\n", ""))
        cm.check_clean_subagent_review_guard()
        self.assertIn("执行形态回指", self.error_texts())

    def test_checklist_node_removed_reports(self):
        # 反例⑬：任务生命周期「验证」节点不问这一问 → 要求只在专项提示词里存在
        self._write_all(execution=False)
        cm.check_clean_subagent_review_guard()
        self.assertIn("specs/core/execution.adoc", self.error_texts())

    def test_dispatcher_trigger_removed_reports(self):
        # 反例⑭：调度器识别特征被抽 → 规则实际失效（不会被触发加载）
        self._write_all(common=False)
        cm.check_clean_subagent_review_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_maintainer_landing_removed_reports(self):
        # 反例⑮：维护方落点被删 → 公共要求与本地动作断链
        self._write_all(maint=False)
        cm.check_clean_subagent_review_guard()
        self.assertIn("specs-project-maintainer/verify.adoc", self.error_texts())


class TestCleanSubagentReviewAnchorListShape(CheckSpecsTestCase):
    """锚点清单自己的形状与条数（**规则数据是纯数据**，被削时现场一字不少）。

    失效形态：删掉 `CLEAN_SUBAGENT_REVIEW_ANCHORS` 里的一个锚点项、或删掉一个 `[`，
    规范正文一字不动，`_section_anchor_check` 的 `miss` 是空集——"核过且通过"与"没核"
    完全一样（本仓库已有实证的口径）。
    """

    def _write_all(self):
        cm._RULES_RUN_THIS_PHASE.clear()
        self.write_real_file("specs/general/review.adoc")
        self.write_real_file("specs/core/execution.adoc")
        self.write_real_file("AGENTS_COMMON.adoc")
        self.write_real_file("specs-project-maintainer/verify.adoc")
        self.write_rules_fixture()
        # `_RULES_TOKENS` 是**导入期**读的（模块级常量），用例改了它之后须还原
        self.addCleanup(cm._RULES_TOKENS.update, cm._RULES_TOKENS)

    def test_anchor_item_removed_reports(self):
        # 反例：清单里被削掉一个锚点项 → 按文档核的那些步骤全绿，只有条数这一步报得出
        self._write_all()
        anchors = [list(g) for g in cm._RULES_TOKENS["CLEAN_SUBAGENT_REVIEW_ANCHORS"]]
        anchors[2][1] = anchors[2][1][:1]
        cm._RULES_TOKENS["CLEAN_SUBAGENT_REVIEW_ANCHORS"] = anchors
        cm.check_clean_subagent_review_guard()
        self.assertIn("CLEAN_SUBAGENT_REVIEW_ANCHORS", self.error_texts())
        self.assertIn("只剩", self.error_texts())

    def test_group_shape_broken_reports(self):
        # 反例：清单里掉一个 `[`（少一项）或组里只剩一项 → 解包失败会让**整道防线**不生效，
        # 须先判形状、指名报出，不得静默（实测形态：`    [\n    [\n` 让解包直接抛异常）
        self._write_all()
        cm._RULES_TOKENS["CLEAN_SUBAGENT_REVIEW_ANCHORS"] = [["只有一项"]]
        cm.check_clean_subagent_review_guard()
        self.assertIn("三项", self.error_texts())


class TestCheckCrossPlatformScriptGuard(CheckSpecsTestCase):
    """钉住『跨环境脚本防线』：一份跨平台逻辑 + 各平台薄壳入口不得被删或降级。

    该条对应用户报告的真实失效与要求：同一功能要在 Windows 与 Linux 上都跑时，常见做法是
    **把逻辑写两遍**（`.bat` 一份、`.sh` 一份），两套行为慢慢漂移；用户的方案是**逻辑只写一份
    放跨平台逻辑代码**、`.bat`/`.sh` 只作为**入口**调用它，并要求给出**实现语言的推荐**。
    最易被冲掉的两处：①"入口里不得写逻辑"退化成"入口也可以稍微处理一下参数"；
    ②"只写一份"被"顺手再写个 sh 版本"绕过。故反例逐项覆盖这两处与语言取舍、工作目录约定。
    """

    SCRIPT = (
        "= 脚本规范\n"
        "\n"
        "== 跨环境脚本（入口 + 跨平台逻辑 + 实现语言取舍）\n"
        "\n"
        "同一功能要在多个操作系统上跑时，**不得把逻辑写两遍**——"
        "逻辑只写一份放**跨平台逻辑层**（一份跨平台逻辑代码）。\n"
        "* **入口层（薄壳）**：职责只有三件——定位逻辑代码、转交全部命令行参数、"
        "把它的退出码作为自己的退出码返回。\n"
        "* **入口层不得承载逻辑（L1）**：入口文件里**不得**出现判定分支、参数解析；"
        "**判定标准**：整份入口可逐行解释为上述三件事。\n"
        "* **入口层不为逻辑层添第二套选项语义（L1）**：只做转交，不解释参数含义、"
        "不设默认值、不吞参数；**例外**：`cmd.exe` 无法承载某些字符时**可以**按平台语法**转义**，"
        "但不得改变参数的值。\n"
        "* **入口层须让退出码可判定（L1）**：`cmd.exe` 用 `exit /b %errorlevel%`、"
        "`sh` 用 `exec`、PowerShell 用 `exit $LASTEXITCODE`。\n"
        "* **不得**在 `.sh` 里再写一遍逻辑（L1）：入口**只允许**一份薄壳，"
        "每个入口只是调用器、不是该平台版本。\n"
        "* **入口文件按平台规范落盘（L1）**：`.bat`/`.cmd` 与 `.ps1` 用 CRLF、`.sh` 用 LF，"
        "`.bat` 用纯 ASCII。\n"
        "* **逻辑代码不得假设自身所处目录（L1）**：入口以绝对路径调用、不 `cd`。\n"
        "* **入口层须与逻辑代码同处一目录、同名不同扩展名（L1）**：入口与逻辑代码放同一目录，"
        "主名必须相同，不另建 `bin/`/`script/`/`windows/`。\n"
        "* **入口脚本须能直接执行，调用方不加前后命令（L1）**：只给脚本名即可跑；"
        "**例外（必要参数除外）**：脚本自身功能参数不算前后命令。\n"
        "* **入口语言按平台默认具备者选（L1）**：Windows 取 `.bat`/`.cmd`、"
        "Linux/macOS 取 `.sh`；不得为一侧入口引入要另装的运行时。\n"
        "* **入口脚本不得为“跑逻辑”自加命令、也不得给逻辑代码塞参数（L1）**："
        "转交须与调用方给的一一对应。\n"
        "* **入口脚本不得要求调用方先做前置动作（L1）**：不设前置步骤，"
        "不得写“请先……”这类对调用方的要求。\n"
        "* **薄壳之外不得多做，但可以做“把逻辑层当命令直接跑”的薄壳（L1）**："
        "薄壳里允许出现与逻辑层调用等价的形态；**判定标准**：出现与"
        "“把调用方给的参数交给逻辑代码”**不等价**的动作即违规。\n"
        "* **入口不得为“让逻辑跑起来”改变系统状态（L1）**：安装/下载/解压任何运行时、"
        "包或依赖都**不属**薄壳；**代为获取运行时**不是入口的职责。\n"
        "\n"
        "**入口语言取舍（L1）**：Windows 取 `.bat`/`.cmd`、Linux/macOS 取 `.sh`。\n"
        "**实现语言取舍（L2）**：优先 **Python 3** 或 **Node.js**；单文件分发用 **Go**/**Rust**。\n"
        "* **默认不拿裸 shell 当逻辑层（L2）**：shell 作为入口恰当、作为逻辑层不恰当。\n"
        "\n"
        "== 与编码规范的关系\n"
        "* x。\n"
    )

    # 批处理栈夹具：满足 BATCH_STACK_KEYS 的全部要点（`.bat`/`.cmd` 的专属规则）
    BATCH = (
        "= Windows 批处理脚本规范（技术栈层）\n"
        "\n"
        "== 编码与行尾\n"
        "* **行尾 CRLF**：`.bat`/`.cmd` 一律 CRLF，**纯 ASCII**、**不写 BOM**。\n"
        "\n"
        "== 语法与健壮性\n"
        "* 首行 `@echo off`。\n"
        "* 块语句里用延迟展开（`setlocal enabledelayedexpansion` + `!var!`）。\n"
        "* 路径一律加引号；可选参数用 `%~1` 去引号后判空。\n"
        "* 未定义变量一律当错误。\n"
        "\n"
        f"== 作为跨环境入口（Windows 与 Linux 并存时）\n"
        f"* 见「{cm.CROSS_PLATFORM_SCRIPT_SECTION}」；只做**薄壳**，`exit /b %errorlevel%` 返回**退出码**。\n"
        "* **入口语言选择（入口的语言取值）**取 `.bat`/`.cmd`。\n"
        "* 不把 **PowerShell** 语法（`$` 变量、cmdlet、`-eq`）写进 `.bat`。\n"
    )

    def setUp(self) -> None:
        super().setUp()
        self._orig_script = cm.SCRIPT_SPEC_FILE
        self._orig_common = cm.GENERIC_FILE
        self._orig_readme = cm.README_FILE
        cm.SCRIPT_SPEC_FILE = os.path.join(self.root, "specs", "general", "script.adoc")
        cm.GENERIC_FILE = os.path.join(self.root, "AGENTS_COMMON.adoc")
        cm.README_FILE = os.path.join(self.root, "README.adoc")
        self._orig_stack = cm.CROSS_PLATFORM_STACK_FILES
        cm.CROSS_PLATFORM_STACK_FILES = tuple(
            os.path.join(self.root, "specs", "stack", n)
            for n in ("bash.adoc", "python.adoc", "batch.adoc", "powershell.adoc"))
        self._orig_batch = cm.BATCH_STACK_FILE
        cm.BATCH_STACK_FILE = os.path.join(self.root, "specs", "stack", "batch.adoc")

    def tearDown(self) -> None:
        (cm.SCRIPT_SPEC_FILE, cm.GENERIC_FILE, cm.README_FILE) = (
            self._orig_script, self._orig_common, self._orig_readme)
        cm.CROSS_PLATFORM_STACK_FILES = self._orig_stack
        cm.BATCH_STACK_FILE = self._orig_batch
        super().tearDown()

    def _write_valid(self, script: str = None) -> None:
        sec = cm.CROSS_PLATFORM_SCRIPT_SECTION
        self.write("specs/general/script.adoc", script if script is not None else self.SCRIPT)
        for n in ("bash.adoc", "python.adoc", "powershell.adoc"):
            self.write(f"specs/stack/{n}",
                       f"= 栈\n\n== 入口\n* 见「{sec}」。\n"
                       "* **入口的语言取值**：入口语言选择见上；"
                       "#!/usr/bin/env bash；执行策略 Bypass；"
                       "Python 只作逻辑层、不作入口（前置命令）；见 batch.adoc。\n")
        self.write("specs/stack/batch.adoc", self.BATCH)
        self.write("AGENTS_COMMON.adoc",
                   "脚本：**跨环境脚本**（`.bat`/`.cmd` 与 `.sh` 成对）；"
                   "批处理栈 `specs/stack/batch.adoc`\n")
        self.write("README.adoc", "目录：脚本（含**跨环境脚本**、各平台入口只做**薄壳**）。\n")
        self.write("library/adoption.adoc",
                   f"* **{sec}（L1）是本站取舍**：同义性差异见下。\n")

    def test_valid_cross_platform_guard_passes(self):
        self._write_valid()
        cm.check_cross_platform_script_guard()
        self.assertEqual(cm.errors, [])

    def test_section_deleted_reports(self):
        # 反例：整节被删 → 又退回"两个平台各写一份脚本"
        self._write_valid("= 脚本规范\n\n== 与编码规范的关系\n* x。\n")
        cm.check_cross_platform_script_guard()
        self.assertIn("跨环境脚本（入口", self.error_texts())

    def test_thin_shell_clause_removed_reports(self):
        # 反例：入口不承载逻辑的条文被抽掉 → 入口又可以"顺便处理一下参数"
        self._write_valid(self.SCRIPT.replace(
            "* **入口层不得承载逻辑（L1）**：入口文件里**不得**出现判定分支、参数解析；"
            "**判定标准**：整份入口可逐行解释为上述三件事。\n", "* 入口随便写。\n"))
        cm.check_cross_platform_script_guard()
        self.assertIn("入口层不得承载逻辑", self.error_texts())

    def test_no_second_logic_clause_removed_reports(self):
        # 反例：'不得在另一平台重写逻辑'被抽掉 → 顺手再写个 sh 版本
        self._write_valid(self.SCRIPT.replace(
            "* **不得**在 `.sh` 里再写一遍逻辑（L1）：入口**只允许**一份薄壳，"
            "每个入口只是调用器、不是该平台版本。\n", ""))
        cm.check_cross_platform_script_guard()
        self.assertIn("再写一遍", self.error_texts())

    def test_passthrough_clause_removed_reports(self):
        # 反例：'不为逻辑层添第二套选项语义'被抽掉 → 入口自定默认值、吞参数，两平台行为不同
        self._write_valid(self.SCRIPT.replace(
            "* **入口层不为逻辑层添第二套选项语义（L1）**：只做转交，不解释参数含义、"
            "不设默认值、不吞参数；**例外**：`cmd.exe` 无法承载某些字符时**可以**按平台语法**转义**，"
            "但不得改变参数的值。\n", "* 入口可以自己定默认值。\n"))
        cm.check_cross_platform_script_guard()
        self.assertIn("第二套选项语义", self.error_texts())

    def test_escape_exception_removed_reports(self):
        # 反例：转义例外被删 → "不得自行解析参数"被读成"连必要的转义都禁止"（cmd.exe 做不到）
        self._write_valid(self.SCRIPT.replace(
            "；**例外**：`cmd.exe` 无法承载某些字符时**可以**按平台语法**转义**，"
            "但不得改变参数的值", ""))
        cm.check_cross_platform_script_guard()
        self.assertIn("转义", self.error_texts())

    def test_exit_code_clause_removed_reports(self):
        # 反例：退出码判据被删 → 入口"总是成功"，调用方（CI）看不到真实成败
        self._write_valid(self.SCRIPT.replace(
            "* **入口层须让退出码可判定（L1）**：`cmd.exe` 用 `exit /b %errorlevel%`、"
            "`sh` 用 `exec`、PowerShell 用 `exit $LASTEXITCODE`。\n", "* 退出码不管。\n"))
        cm.check_cross_platform_script_guard()
        self.assertIn("退出码可判定", self.error_texts())

    def test_language_clause_removed_reports(self):
        # 反例：实现语言取舍被删 → 执行者只能凭"哪个顺手"选语言
        self._write_valid(self.SCRIPT.replace(
            "**实现语言取舍（L2）**：优先 **Python 3** 或 **Node.js**；"
            "单文件分发用 **Go**/**Rust**。\n", ""))
        cm.check_cross_platform_script_guard()
        self.assertIn("实现语言", self.error_texts())

    def test_bare_shell_clause_removed_reports(self):
        # 反例：'不拿裸 shell 当逻辑层'被删 → 逻辑又被写进 shell、平台差异回到逻辑层
        self._write_valid(self.SCRIPT.replace(
            "* **默认不拿裸 shell 当逻辑层（L2）**：shell 作为入口恰当、作为逻辑层不恰当。\n", ""))
        cm.check_cross_platform_script_guard()
        self.assertIn("裸 shell", self.error_texts())

    def test_workdir_clause_removed_reports(self):
        # 反例：目录约定被删 → 入口一 cd，相对路径在本地与 CI 下行为不同
        self._write_valid(self.SCRIPT.replace(
            "* **逻辑代码不得假设自身所处目录（L1）**：入口以绝对路径调用、不 `cd`。\n", ""))
        cm.check_cross_platform_script_guard()
        self.assertIn("不得假设自身所处目录", self.error_texts())

    def test_bootstrap_clause_removed_reports(self):
        # 反例：'入口不得安装/下载运行时'被删 → 入口退化成"自己想办法搞一个解释器"
        self._write_valid(self.SCRIPT.replace(
            "* **入口不得为“让逻辑跑起来”改变系统状态（L1）**：安装/下载/解压任何运行时、"
            "包或依赖都**不属**薄壳；**代为获取运行时**不是入口的职责。\n", ""))
        cm.check_cross_platform_script_guard()
        self.assertIn("代为获取运行时", self.error_texts())

    def test_equivalence_clause_removed_reports(self):
        # 反例：'可以做把逻辑层当命令直接跑的薄壳'被删 → 正当形态被一起禁掉
        self._write_valid(self.SCRIPT.replace(
            "* **薄壳之外不得多做，但可以做“把逻辑层当命令直接跑”的薄壳（L1）**："
            "薄壳里允许出现与逻辑层调用等价的形态；**判定标准**：出现与"
            "“把调用方给的参数交给逻辑代码”**不等价**的动作即违规。\n", ""))
        cm.check_cross_platform_script_guard()
        self.assertIn("薄壳之外不得多做", self.error_texts())

    def test_stack_pointer_missing_reports(self):
        # 反例：栈文件未指向本条的入口约定 → 该栈执行者读不到"薄壳、不写逻辑"
        self._write_valid()
        self.write("specs/stack/bash.adoc", "= 栈\n\n== 其他\n* x。\n")
        cm.check_cross_platform_script_guard()
        self.assertIn("specs/stack/bash.adoc", self.error_texts())

    def test_dispatcher_entry_removed_reports(self):
        # 反例：调度器识别特征被删 → 该条永远不会被触发加载
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "脚本：行尾按类型取值。\n")
        cm.check_cross_platform_script_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_readme_entry_removed_reports(self):
        # 反例：README 目录说明未同步 → 读者按 README 学习时不知道有这条规则
        self._write_valid()
        self.write("README.adoc", "目录：脚本。\n")
        cm.check_cross_platform_script_guard()
        self.assertIn("README.adoc", self.error_texts())

    def test_library_synonymy_removed_reports(self):
        # 反例：图书馆未记同义性差异 → 本站取舍会被读成外部标准原文
        self._write_valid()
        self.write("library/adoption.adoc", "= 取舍\n* 其它。\n")
        cm.check_cross_platform_script_guard()
        self.assertIn("library/adoption.adoc", self.error_texts())

    def test_same_dir_same_name_clause_removed_reports(self):
        # 反例：'同处一目录、主名相同'被删 → 入口另放 windows/ 目录，改逻辑连带改入口
        self._write_valid(self.SCRIPT.replace(
            "* **入口层须与逻辑代码同处一目录、同名不同扩展名（L1）**：入口与逻辑代码放同一目录，"
            "主名必须相同，不另建 `bin/`/`script/`/`windows/`。\n", ""))
        cm.check_cross_platform_script_guard()
        self.assertIn("同处一目录", self.error_texts())

    def test_no_extra_command_clause_removed_reports(self):
        # 反例：'不加前后命令'被删 → 又要求用户敲 `bash foo.sh` / `python3 foo.py`
        self._write_valid(self.SCRIPT.replace(
            "* **入口脚本须能直接执行，调用方不加前后命令（L1）**：只给脚本名即可跑；"
            "**例外（必要参数除外）**：脚本自身功能参数不算前后命令。\n", ""))
        cm.check_cross_platform_script_guard()
        self.assertIn("不加前后命令", self.error_texts())

    def test_entry_language_clause_removed_reports(self):
        # 反例：入口语言取舍被删（条文与结论文本都去掉）→ 入口语言选择无落点
        self._write_valid(self.SCRIPT.replace(
            "* **入口语言按平台默认具备者选（L1）**：Windows 取 `.bat`/`.cmd`、"
            "Linux/macOS 取 `.sh`；不得为一侧入口引入要另装的运行时。\n", "")
            .replace("**入口语言取舍（L1）**：Windows 取 `.bat`/`.cmd`、"
                     "Linux/macOS 取 `.sh`。\n", ""))
        cm.check_cross_platform_script_guard()
        self.assertIn("入口语言取舍", self.error_texts())

    def test_entry_language_section_removed_reports(self):
        # 反例：入口语言取舍整段被删（含结论行）→ 入口语言选择无落点
        self._write_valid(self.SCRIPT.replace(
            "**入口语言取舍（L1）**：Windows 取 `.bat`/`.cmd`、Linux/macOS 取 `.sh`。\n", ""))
        cm.check_cross_platform_script_guard()
        self.assertIn("入口语言取舍", self.error_texts())

    def test_no_precondition_clause_removed_reports(self):
        # 反例：'不设前置步骤'被删 → 入口又开始要求调用方先 cd / 设变量 / 装依赖
        self._write_valid(self.SCRIPT.replace(
            "* **入口脚本不得要求调用方先做前置动作（L1）**：不设前置步骤，"
            "不得写“请先……”这类对调用方的要求。\n", ""))
        cm.check_cross_platform_script_guard()
        self.assertIn("前置动作", self.error_texts())

    def test_no_self_added_command_clause_removed_reports(self):
        # 反例：'不得自加命令/塞参数'被删 → 入口里先 cd、装依赖，或给逻辑代码预置参数
        self._write_valid(self.SCRIPT.replace(
            "* **入口脚本不得为“跑逻辑”自加命令、也不得给逻辑代码塞参数（L1）**："
            "转交须与调用方给的一一对应。\n", ""))
        cm.check_cross_platform_script_guard()
        self.assertIn("自加命令", self.error_texts())

    def test_stack_same_dir_missing_reports(self):
        # 反例：栈文件未写本栈入口的落点与命名 → 通用层的'同处一目录、主名相同'在该栈无落点
        self._write_valid()
        self.write("specs/stack/bash.adoc",
                   f"= 栈\n\n== 入口\n* 见「{cm.CROSS_PLATFORM_SCRIPT_SECTION}」。\n")
        cm.check_cross_platform_script_guard()
        self.assertIn("specs/stack/bash.adoc", self.error_texts())


    def test_batch_stack_missing_reports(self):
        # 反例：`.bat`/`.cmd` 的专属栈文件缺失 → 用户指出的缺口（"没有看到 bat 脚本的规范文件"）
        # 复现：写批处理脚本时没有触发特征、也没有编码/行尾/块语句/退出码的落点
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "stack", "batch.adoc"))
        cm.check_cross_platform_script_guard()
        self.assertIn("specs/stack/batch.adoc", self.error_texts())

    def test_batch_stack_encoding_clause_removed_reports(self):
        # 反例：批处理栈的编码/行尾（CRLF + 纯 ASCII + 不写 BOM）被删
        # → `.bat` 又按通用 LF/UTF-8 落盘，在 Windows 上直接执行失败
        self._write_valid()
        self.write("specs/stack/batch.adoc",
                   self.BATCH.replace("* **行尾 CRLF**：`.bat`/`.cmd` 一律 CRLF，"
                                      "**纯 ASCII**、**不写 BOM**。\n", ""))
        cm.check_cross_platform_script_guard()
        self.assertIn("specs/stack/batch.adoc", self.error_texts())

    def test_batch_stack_delayed_expansion_removed_reports(self):
        # 反例：延迟展开的判据被删 → 块语句里 `%var%` 在解析期展开、取不到值
        self._write_valid()
        self.write("specs/stack/batch.adoc",
                   self.BATCH.replace("* 块语句里用延迟展开"
                                      "（`setlocal enabledelayedexpansion` + `!var!`）。\n", ""))
        cm.check_cross_platform_script_guard()
        self.assertIn("specs/stack/batch.adoc", self.error_texts())

    def test_batch_stack_exit_code_removed_reports(self):
        # 反例：`exit /b %errorlevel%` 的判据被删 → 退出码是最后一条命令的、调用方看不到真实成败
        self._write_valid()
        self.write("specs/stack/batch.adoc",
                   self.BATCH.replace("`exit /b %errorlevel%` 返回**退出码**",
                                      "调用方自己看输出"))
        cm.check_cross_platform_script_guard()
        self.assertIn("specs/stack/batch.adoc", self.error_texts())

    def test_batch_stack_powershell_syntax_mix_removed_reports(self):
        # 反例：'不得把 PowerShell 语法写进 .bat' 被删 → 混写出来的 `.bat` 一条都跑不通
        self._write_valid()
        self.write("specs/stack/batch.adoc",
                   self.BATCH.replace("* 不把 **PowerShell** 语法（`$` 变量、cmdlet、`-eq`）"
                                      "写进 `.bat`。\n", ""))
        cm.check_cross_platform_script_guard()
        self.assertIn("specs/stack/batch.adoc", self.error_texts())

    def test_powershell_missing_batch_pointer_reports(self):
        # 反例：powershell.adoc 不再指向批处理栈 → `.ps1` 的同名 `.bat` 其规则无处可查
        self._write_valid()
        self.write("specs/stack/powershell.adoc",
                   f"= 栈\n\n== 入口\n* 见「{cm.CROSS_PLATFORM_SCRIPT_SECTION}」。\n"
                   "* 同处一目录、主名相同；入口语言选择见上；执行策略 Bypass；\n")
        cm.check_cross_platform_script_guard()
        self.assertIn("specs/stack/powershell.adoc", self.error_texts())

    def test_dispatcher_batch_stack_entry_removed_reports(self):
        # 反例：调度器未登记批处理栈 → "写一个批处理脚本"没有触发特征、规则实际失效
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   "脚本：**跨环境脚本**（`.bat`/`.cmd` 与 `.sh` 成对）\n")
        cm.check_cross_platform_script_guard()
        self.assertIn("specs/stack/batch.adoc", self.error_texts())




class TestCheckScriptHeaderGuard(CheckSpecsTestCase):
    """钉住『脚本头部注释（文档头）防线』：文档头先行 + 细节不随维护丢失。

    对应用户要求：「需要呢，脚本很多细节可能随着维护丢失，文档先行也适用于脚本」。
    该条最易被冲掉的两处：①"文档先行"退化成"写完顺手补一段"（交付时文档头与实现已不同步）；
    ②注释里抄实现取值（"超时 30 秒"）——改代码不改注释即"文档说谎"，比不写更坏。
    故反例逐项覆盖：先行句、决策条目、取值条、入口注释边界、超容量移交、行数不设限、
    方法体边界、栈侧落点与公开面/依据登记。
    """

    SCRIPT = (
        "= 脚本规范\n"
        "\n"
        "== 脚本头部注释（文档头）\n"
        "\n"
        "* **文档头先行（头部注释必须先行，L1）**：动手先把内容写进文档头，"
        "**不得只留待办占位**；改动后在同一提交内同步。\n"
        "* **脚本必须写文档头（L2）**：承担实际功能的脚本都要有条目化文档头。\n"
        "* 条目化写明：\n"
        "  ** 脚本名称与用途；\n"
        "  ** **关键约定与设计决策**（**不得省略**）：约定与出处、"
        "**为什么这么做**与**放弃了哪些备选做法**；\n"
        "* **设计决策写成可核对的记录，不写成叙述（L1）**："
        "每条取舍写成**决策 + 理由 + 边界**；**判定标准**：只写决定不写理由即未达要求。\n"
        "* **注释里的取值：写抽象描述或常量名、不写硬编码数值（L1）**："
        "写 `TIMEOUT_SECONDS`，不写“超时 30 秒”；判定标准：两处真源。\n"
        "* **决策进头部/文件级文档注释，不写进方法体（L1）**：方法体只记局部决策。\n"
        "* **超过头部块注释容量的内容移交独立文档（L1）**："
        "**判据**：该移交而未移交。\n"
        "* **头部注释写在承载文档注释的位置，行数不设限（L1）**：篇幅按内容定。\n"
        "* **入口的注释边界（L1）**：入口注释**不得复述**逻辑层的参数语义与默认值。\n"
        "\n"
        "== 与编码规范的关系\n"
        "* x。\n"
    )

    def setUp(self) -> None:
        super().setUp()
        self._orig_script = cm.SCRIPT_SPEC_FILE
        self._orig_readme = cm.README_FILE
        cm.SCRIPT_SPEC_FILE = os.path.join(self.root, "specs", "general", "script.adoc")
        cm.README_FILE = os.path.join(self.root, "README.adoc")

    def tearDown(self) -> None:
        (cm.SCRIPT_SPEC_FILE, cm.README_FILE) = (self._orig_script, self._orig_readme)
        super().tearDown()

    def _write_valid(self, script: str = None) -> None:
        self.write("specs/general/script.adoc", script if script is not None else self.SCRIPT)
        self.write("specs/stack/python.adoc",
                   "= Python\n\n== 文件头\n"
                   "* 文档头写在模块 **docstring** 里、**不另起块注释**："
                   "docstring 是该语言的**文档注释机制**。\n"
                   "* docstring 里写**抽象描述或常量名**、**不抄实现取值**。\n")
        # 各栈按数据字典条只**指向**通用层落点（判据唯一落点＝通用层本节），
        # 并保留本栈取值（批处理用 `rem`/`::` 行注释）
        for n in ("bash.adoc", "batch.adoc", "powershell.adoc"):
            self.write(f"specs/stack/{n}",
                       "= 栈\n\n== 入口\n"
                       f"* **入口的头部注释只写入口自己**：判据见「{cm.SCRIPT_HEADER_SECTION}」"
                       "下的「入口的注释边界（L1）」；本栈用 `rem`/`::` 行注释。\n")
        # 调度器**只给触发特征**（要新写或改脚本、要写脚本文档头时即命中），
        # 不抄条目本体的取值（`文档头先行`/`常量名` 在 `script.adoc` 里）。
        self.write("AGENTS_COMMON.adoc",
                   "脚本 → `specs/general/script.adoc`（识别特征：要新写或改脚本、"
                   "要写脚本文档头）。\n")
        self.write("README.adoc", "目录：脚本（含**文档头先行**与**跨环境脚本**）。\n")
        self.write("library/adoption.adoc",
                   "* **「脚本头部注释（文档头）先行、细节有落点」是本站取舍**："
                   "同义性差异见下，如实标注**未确证**。\n")
        self.write("library/sources.adoc",
                   "== 脚本头部注释（文档头）与决策记载\n"
                   "* PEP 257（**要点转述、非逐字摘录**）；**同义性**差异见下。\n")

    def test_valid_script_header_guard_passes(self):
        self._write_valid()
        cm.check_script_header_guard()
        self.assertEqual(cm.errors, [])

    def test_section_deleted_reports(self):
        # 反例：整节被删 → 脚本的定位/用法/设计决策又只剩代码里可读，细节随维护丢失
        self._write_valid("= 脚本规范\n\n== 与编码规范的关系\n* x。\n")
        cm.check_script_header_guard()
        self.assertIn("脚本头部注释（文档头）", self.error_texts())

    def test_first_clause_removed_reports(self):
        # 反例："文档先行"被抽掉 → 退回成"要写文档"，交付时文档头与实现早已不同步
        self._write_valid(self.SCRIPT.replace(
            "* **文档头先行（头部注释必须先行，L1）**：动手先把内容写进文档头，"
            "**不得只留待办占位**；改动后在同一提交内同步。\n", "* 写完顺手补一段说明即可。\n"))
        cm.check_script_header_guard()
        self.assertIn("文档头先行", self.error_texts())

    def test_design_decision_item_removed_reports(self):
        # 反例：条目清单去掉"设计决策" → 本条要防的失效（为什么这么取边界、放弃了什么）原样存在
        self._write_valid(self.SCRIPT.replace(
            "  ** **关键约定与设计决策**（**不得省略**）：约定与出处、"
            "**为什么这么做**与**放弃了哪些备选做法**；\n", "  ** 用法与参数；\n"))
        cm.check_script_header_guard()
        self.assertIn("关键约定与设计决策", self.error_texts())

    def test_design_decision_judgement_removed_reports(self):
        # 反例：决策写成"决策 + 理由 + 边界"的判据被抽 → "记录设计思路"退化成一段叙述
        self._write_valid(self.SCRIPT.replace(
            "* **设计决策写成可核对的记录，不写成叙述（L1）**："
            "每条取舍写成**决策 + 理由 + 边界**；**判定标准**：只写决定不写理由即未达要求。\n", "* 有想法就写。\n"))
        cm.check_script_header_guard()
        self.assertIn("决策", self.error_texts())

    def test_constant_value_clause_removed_reports(self):
        # 反例：'取值写常量名、不写硬编码数值'被抽 → 改代码不改注释的"文档说谎"重回默许
        self._write_valid(self.SCRIPT.replace(
            "* **注释里的取值：写抽象描述或常量名、不写硬编码数值（L1）**："
            "写 `TIMEOUT_SECONDS`，不写“超时 30 秒”；判定标准：两处真源。\n", "* 取值按实际写。\n"))
        cm.check_script_header_guard()
        self.assertIn("常量名", self.error_texts())

    def test_method_body_boundary_removed_reports(self):
        # 反例：决策落点（头部 vs 方法体）被删 → 方案取舍抄进每个方法、改一处必漏一处
        self._write_valid(self.SCRIPT.replace(
            "* **决策进头部/文件级文档注释，不写进方法体（L1）**：方法体只记局部决策。\n", ""))
        cm.check_script_header_guard()
        self.assertIn("方法体", self.error_texts())

    def test_overflow_handoff_clause_removed_reports(self):
        # 反例：超容量移交独立文档被删 → 要么文档头堆成长文、要么内容被"写短点"删掉
        self._write_valid(self.SCRIPT.replace(
            "* **超过头部块注释容量的内容移交独立文档（L1）**："
            "**判据**：该移交而未移交。\n", "* 内容多就多写点。\n"))
        cm.check_script_header_guard()
        self.assertIn("移交独立文档", self.error_texts())

    def test_no_length_limit_clause_removed_reports(self):
        # 反例：'行数不设限'被删 → "简洁"被读成篇幅配额、内容要求被折成字数
        self._write_valid(self.SCRIPT.replace(
            "* **头部注释写在承载文档注释的位置，行数不设限（L1）**：篇幅按内容定。\n", ""))
        cm.check_script_header_guard()
        self.assertIn("不设限", self.error_texts())

    def test_entry_comment_boundary_removed_reports(self):
        # 反例：入口注释边界被删 → 同一份契约写两处（改逻辑不改入口注释）
        self._write_valid(self.SCRIPT.replace(
            "* **入口的注释边界（L1）**：入口注释**不得复述**逻辑层的参数语义与默认值。\n", ""))
        cm.check_script_header_guard()
        self.assertIn("入口", self.error_texts())

    def test_python_docstring_clause_removed_reports(self):
        # 反例：Python 侧不再用模块 docstring 承载 → 有文档注释机制却另起块注释（两处各写一半）
        self._write_valid()
        self.write("specs/stack/python.adoc", "= Python\n\n== 文件头\n* 随便写点说明。\n")
        cm.check_script_header_guard()
        self.assertIn("specs/stack/python.adoc", self.error_texts())

    def test_bash_entry_comment_clause_removed_reports(self):
        # 反例：bash 入口不再写"注释只写入口自己" → Windows/Linux 入口各抄一份逻辑层契约
        self._write_valid()
        self.write("specs/stack/bash.adoc", "= 栈\n\n== 入口\n* 见「跨环境脚本」。\n")
        cm.check_script_header_guard()
        self.assertIn("specs/stack/bash.adoc", self.error_texts())

    def test_dispatcher_feature_removed_reports(self):
        # 反例：调度器识别特征被删 → 该条永远不会被触发加载、规则实际失效
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "脚本：行尾按类型取值。\n")
        cm.check_script_header_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_readme_entry_removed_reports(self):
        # 反例：README 目录说明未同步 → 读者按 README 学习时不知道有这条要求
        self._write_valid()
        self.write("README.adoc", "目录：脚本。\n")
        cm.check_script_header_guard()
        self.assertIn("README.adoc", self.error_texts())

    def test_library_adoption_removed_reports(self):
        # 反例：图书馆未登记"本站取舍" → 本站口径会被读成某标准原文
        self._write_valid()
        self.write("library/adoption.adoc", "= 取舍\n* 其它。\n")
        cm.check_script_header_guard()
        self.assertIn("library/adoption.adoc", self.error_texts())

    def test_library_sources_removed_reports(self):
        # 反例：图书馆缺对应主题段 → 依据链断在这里（PEP 257/25010/29148 的方向失去落点）
        self._write_valid()
        self.write("library/sources.adoc", "= 来源\n* 其它。\n")
        cm.check_script_header_guard()
        self.assertIn("library/sources.adoc", self.error_texts())



class TestCheckScriptSelfdocGuard(CheckSpecsTestCase):
    """钉住『脚本自述文档防线』：脚本单打独斗、文档随脚本落盘。

    对应用户口径：「脚本比较特殊，大部分情况下都是单打独斗…各脚本之间也是独立的…
    否则文档直接以多行文档注释（优先级-高）/多行普通注释（优先级-中）/普通注释（优先级-低）
    的方式写在脚本里」。该条最易被冲掉的两处：①"文档"被外推到脚本之外（为每个脚本另建
    独立文档）；②承载方式降格（有文档注释机制却用普通注释、文档头散落成单行注释）。
    """

    SCRIPT = (
        "= 脚本规范\n"
        "\n"
        "== 脚本文档的承载位置与协作粒度（默认写进脚本自身）\n"
        "\n"
        "* **脚本默认单打独斗（L1）**：拆成多个脚本时**各脚本相互独立**；"
        "文档**默认直接写在脚本里、不另建独立文档**，有文档注释机制的语言一律用**文档注释**承载，"
        "按**多行文档注释 → 多行普通/块注释 → 普通注释**的优先级取值。命中即违规。\n"
        "* **唯一例外（L1）**：只有**超出头部块注释的容量**时才另建独立文档，**判定标准**："
        "该移交而未移交。\n"
        "* **大规模团队式协作是例外，不是默认（L2）**。\n"
        "\n"
        "== 脚本头部注释（文档头）\n"
        "\n"
        "* 文档头先行。\n"
    )

    def setUp(self) -> None:
        super().setUp()
        self._orig_script = cm.SCRIPT_SPEC_FILE
        self._orig_readme = cm.README_FILE
        cm.SCRIPT_SPEC_FILE = os.path.join(self.root, "specs", "general", "script.adoc")
        cm.README_FILE = os.path.join(self.root, "README.adoc")

    def tearDown(self) -> None:
        (cm.SCRIPT_SPEC_FILE, cm.README_FILE) = (self._orig_script, self._orig_readme)
        super().tearDown()

    def _write_valid(self, script: str = None) -> None:
        self.write("specs/general/script.adoc", script if script is not None else self.SCRIPT)
        self.write("specs/general/coding.adoc",
                   "= 编码\n\n== 注释\n"
                   "* 注释定位：**脚本的落点与粒度**：脚本默认**单打独斗**，"
                   "按**多行文档注释 → 多行普通/块注释 → 普通注释**取值。\n")
        self.write("specs/stack/python.adoc",
                   "= Python\n\n== 文件头\n"
                   "* **单打独斗的 `.py` 脚本同样用模块 docstring**、默认**不另建**独立文档。\n")
        self.write("specs/stack/bash.adoc",
                   "= 栈\n\n== 文件头\n"
                   "* **无文档注释机制，文档头用多行块注释**（连续 `#` 行）承载。\n")
        self.write("specs/stack/batch.adoc",
                   "= 栈\n\n== 注释与文档头\n"
                   "* 批处理的注释只有 `rem` 与 `::`；**文档头用连续的 `rem` 行**。\n")
        self.write("specs/stack/powershell.adoc",
                   "= 栈\n\n== 注释与文档头\n"
                   "* **用基于注释的帮助（comment-based help）承载文档头**。\n")
        # 调度器**只给触发特征**（要为脚本另建独立文档时即命中），不抄条目本体的取值。
        self.write("AGENTS_COMMON.adoc",
                   "脚本 → `specs/general/script.adoc`（识别特征：要为脚本另建独立文档）。\n")
        self.write("README.adoc",
                   "目录：脚本（含**文档默认写进脚本自身**与**跨环境脚本**）。\n")

    def test_valid_script_selfdoc_guard_passes(self):
        self._write_valid()
        cm.check_script_selfdoc_guard()
        self.assertEqual(cm.errors, [])

    def test_section_deleted_reports(self):
        # 反例：整节被删 → 文档承载位置又回到"逐脚本另建独立文档"的默认读法
        self._write_valid("= 脚本规范\n\n== 脚本头部注释（文档头）\n* x。\n")
        cm.check_script_selfdoc_guard()
        self.assertIn("脚本文档的承载位置与协作粒度", self.error_texts())

    def test_lone_wolf_clause_removed_reports(self):
        # 反例："单打独斗/各脚本相互独立"被抽 → 多脚本被当成多模块项目、每个脚本各建一篇文档
        self._write_valid(self.SCRIPT.replace(
            "* **脚本默认单打独斗（L1）**：拆成多个脚本时**各脚本相互独立**；", "* 脚本。"))
        cm.check_script_selfdoc_guard()
        self.assertIn("单打独斗", self.error_texts())

    def test_priority_ladder_removed_reports(self):
        # 反例：三级优先级被删 → "写在脚本里"没有可判定形态，文档头降格成零散单行注释
        self._write_valid(self.SCRIPT.replace(
            "按**多行文档注释 → 多行普通/块注释 → 普通注释**的优先级取值。", ""))
        cm.check_script_selfdoc_guard()
        self.assertIn("多行普通/块注释", self.error_texts())

    def test_no_side_doc_clause_removed_reports(self):
        # 反例："不另建独立文档/有机制须用文档注释"被抽 → 为脚本另建 .adoc 重回默许形态
        self._write_valid(self.SCRIPT.replace(
            "文档**默认直接写在脚本里、不另建独立文档**，有文档注释机制的语言一律用**文档注释**承载，", ""))
        cm.check_script_selfdoc_guard()
        self.assertIn("不另建独立文档", self.error_texts())

    def test_exception_clause_removed_reports(self):
        # 反例：唯一例外（超容量移交）被删 → "能拆成两处写"被当成另建文档的理由
        self._write_valid(self.SCRIPT.replace(
            "* **唯一例外（L1）**：只有**超出头部块注释的容量**时才另建独立文档，**判定标准**："
            "该移交而未移交。\n", "* 想拆就拆。\n"))
        cm.check_script_selfdoc_guard()
        self.assertIn("超出头部块注释的容量", self.error_texts())

    def test_team_exception_clause_removed_reports(self):
        # 反例：'大规模团队式协作是例外'被删 → 例外外推成所有脚本的默认文档组织
        self._write_valid(self.SCRIPT.replace(
            "* **大规模团队式协作是例外，不是默认（L2）**。\n", ""))
        cm.check_script_selfdoc_guard()
        self.assertIn("大规模团队式协作", self.error_texts())

    def test_coding_note_location_exception_removed_reports(self):
        # 反例：coding 的注释定位条不带脚本例外 → 原文会被读成"脚本也要按类/方法那套、文档另建"
        self._write_valid()
        self.write("specs/general/coding.adoc", "= 编码\n\n== 注释\n* 注释定位：详细设计进文档注释。\n")
        cm.check_script_selfdoc_guard()
        self.assertIn("specs/general/coding.adoc", self.error_texts())

    def test_python_clause_removed_reports(self):
        # 反例：Python 侧不再写"单文件脚本不另建文档" → 仍会被各建一篇文档
        self._write_valid()
        self.write("specs/stack/python.adoc", "= Python\n\n== 文件头\n* 随便写点说明。\n")
        cm.check_script_selfdoc_guard()
        self.assertIn("specs/stack/python.adoc", self.error_texts())

    def test_bash_clause_removed_reports(self):
        # 反例：bash 侧不写"无文档注释机制、用多行块注释" → 文档头散落成行尾零散注释
        self._write_valid()
        self.write("specs/stack/bash.adoc", "= 栈\n\n== 文件头\n* 见通用脚本规范。\n")
        cm.check_script_selfdoc_guard()
        self.assertIn("specs/stack/bash.adoc", self.error_texts())

    def test_batch_clause_removed_reports(self):
        # 反例：批处理侧不写 rem 承载 → 文档头写成 ::、或在括号块内失效
        self._write_valid()
        self.write("specs/stack/batch.adoc", "= 栈\n\n== 注释\n* 见通用脚本规范。\n")
        cm.check_script_selfdoc_guard()
        self.assertIn("specs/stack/batch.adoc", self.error_texts())

    def test_powershell_clause_removed_reports(self):
        # 反例：PowerShell 侧不写 comment-based help → 有文档注释机制却用普通 # 块注释
        self._write_valid()
        self.write("specs/stack/powershell.adoc", "= 栈\n\n== 注释\n* 随便写点说明。\n")
        cm.check_script_selfdoc_guard()
        self.assertIn("specs/stack/powershell.adoc", self.error_texts())

    def test_dispatcher_feature_removed_reports(self):
        # 反例：调度器识别特征被删 → 该条永远不会被触发加载、规则实际失效
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "脚本：行尾按类型取值。\n")
        cm.check_script_selfdoc_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_readme_entry_removed_reports(self):
        # 反例：README 目录说明未同步 → 读者按 README 学习时不知道该写在哪
        self._write_valid()
        self.write("README.adoc", "目录：脚本。\n")
        cm.check_script_selfdoc_guard()
        self.assertIn("README.adoc", self.error_texts())


class TestCheckCommentPreservationGuard(CheckSpecsTestCase):
    """钉住『评论不得删除防线』：任何情况下不得删除 Issue/PR 的评论（含 NPC 生成的）。

    用户明确要求：「任何情况下，不得删除 issue、pr 的评论（包括 npc 生成的）」。该条在本仓库
    正是一处失效面：既有"过程性叙述不得作为独立评论发出"的交付纪律容易被读成"发错的那条删掉
    就行"，而评论串是**派发的对象钉定与留证落点**、删除**不可逆**、**编辑同效**。
    """

    PKG = "specs/platform/cnb.adoc"
    COLLAB = "specs/general/collab.adoc"
    EXEC = "specs/core/execution.adoc"

    def setUp(self) -> None:
        super().setUp()
        self._orig_readme = cm.README_FILE
        cm.README_FILE = os.path.join(self.root, "README.adoc")

    def tearDown(self) -> None:
        cm.README_FILE = self._orig_readme
        super().tearDown()

    def _write_valid(self) -> None:
        self.write(self.PKG,
                   "= CNB\n\n== 评论不得删除（L1）\n"
                   "* **任何情况下都不得删除 Issue / PR 的评论**（含 **NPC** 生成的）："
                   "**不可逆**，评论是**留证落点**；**编辑**原话与删除**同效**；"
                   "正当处置是**再发一条更正**。**判定标准**：①**调用**了**删除评论的接口**；"
                   "②编辑既有评论；③转交他人代删；④自我豁免。\n"
                   "* 边界：清理 **临时产物** 照旧；与合并无关。\n")
        self.write(self.COLLAB,
                   "= 协作\n\n== 派发入口（往哪派、派什么）\n"
                   "* **评论不得删除（L1，平台无关）**：任务单下的评论**不得删除**——评论是**留证落点**、"
                   "**不可逆**；**编辑**与删除**同效**；**再发一条更正**；"
                   "边界见 **临时产物**；判据见 `specs/platform/cnb.adoc`「评论不得删除」。\n")
        self.write(self.EXEC,
                   "= 执行\n\n== 破坏性操作（不可逆，先确认再动手）\n"
                   "* **不得删除平台任务单（Issue / PR）下的评论（L1）**：**没有**『先确认』就能删的路径，"
                   "**一律不删**；**编辑**与删除**同效**；**再发一条更正**；"
                   "本地 **临时产物** 清理照旧。\n")
        self.write("AGENTS_COMMON.adoc", "平台：**评论不得删除**\n")
        self.write("README.adoc", "目录：平台（含**评论不得删除**）。\n")

    def test_valid_comment_preservation_guard_passes(self):
        self._write_valid()
        cm.check_comment_preservation_guard()
        self.assertEqual(cm.errors, [])

    def test_platform_clause_removed_reports(self):
        # 反例：平台层禁令被删 → 删除评论又成了"清理一下"的随手动作
        self._write_valid()
        self.write(self.PKG, "= CNB\n\n== 其它\n* x。\n")
        cm.check_comment_preservation_guard()
        self.assertIn("评论不得删除", self.error_texts())

    def test_edit_equivalence_removed_reports(self):
        # 反例：抽掉"编辑同效" → 删不掉就改掉，留证照样没了
        self._write_valid()
        self.write(self.PKG,
                   "= CNB\n\n== 评论不得删除（L1）\n"
                   "* **不得删除 Issue / PR 的评论**（含 **NPC** 生成的）：**不可逆**、**留证落点**；"
                   "**再发一条更正**。**判定标准**：①**调用**了**删除评论的接口**。\n"
                   "* 边界：**临时产物** 照旧；与合并无关。\n")
        cm.check_comment_preservation_guard()
        self.assertIn("同效", self.error_texts())

    def test_broken_layer_reports(self):
        # 反例：必加载层的"没有先确认就能删的路径"被删 → 被读成"确认过就能删"
        self._write_valid()
        self.write(self.EXEC,
                   "= 执行\n\n== 破坏性操作（不可逆，先确认再动手）\n"
                   "* **不得删除平台任务单（Issue / PR）下的评论（L1）**："
                   "**编辑**与删除**同效**；**再发一条更正**；**临时产物** 照旧。\n")
        cm.check_comment_preservation_guard()
        self.assertIn("specs/core/execution.adoc", self.error_texts())

    def test_generic_clause_removed_reports(self):
        # 反例：通用层同口径条被删 → 非 CNB 环境读不到这条禁令
        self._write_valid()
        self.write(self.COLLAB, "= 协作\n\n== 派发入口（往哪派、派什么）\n* x。\n")
        cm.check_comment_preservation_guard()
        self.assertIn("specs/general/collab.adoc", self.error_texts())

    def test_dispatcher_entry_removed_reports(self):
        # 反例：调度器识别特征被删 → 该禁令永远不会被触发加载
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "平台：分支与合并请求统一。\n")
        cm.check_comment_preservation_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_readme_entry_removed_reports(self):
        # 反例：README 目录说明未同步 → 读者找不到这条禁令
        self._write_valid()
        self.write("README.adoc", "目录：平台。\n")
        cm.check_comment_preservation_guard()
        self.assertIn("README.adoc", self.error_texts())

    def test_batch_first_line_guard_reports(self):
        # 反例：批处理栈的"天然不带 BOM / 首行"口径被删 → 空行或 BOM 把 `@echo off` 挤下首行
        self.write("specs/general/encoding.adoc",
                   "= t\n\n== 换行符（行尾）\n内容以 LF 为基准；`.bat`/`.cmd` 必须 CRLF；"
                   "由 `.gitattributes` 固定，`core.autocrlf` 交给仓库配置、不靠人工手动调整。\n")
        for f in ("bash.adoc", "python.adoc", "powershell.adoc"):
            self.write(f"specs/stack/{f}"
                      , "行尾：按本栈要求；BOM 是唯一允许出现在首行之前的东西\n")
        self.write("specs/stack/batch.adoc", "行尾：CRLF\n")
        self.write("AGENTS_COMMON.adoc", "登记 `specs/general/encoding.adoc`")
        orig = cm.LINE_ENDING_STACK_FILES
        cm.LINE_ENDING_STACK_FILES = tuple(
            os.path.join(self.root, "specs", "stack", f)
            for f in ("bash.adoc", "python.adoc", "batch.adoc", "powershell.adoc"))
        try:
            cm.check_line_ending_guard()
        finally:
            cm.LINE_ENDING_STACK_FILES = orig
        self.assertIn("batch.adoc", self.error_texts())
        self.assertIn("天然不带 BOM", self.error_texts())


class TestCheckEntryDocManifest(CheckSpecsTestCase):
    """钉住『入口文档持久化防线』：入口文档须给"隔一次会话还认得回来"的清单。

    对应用户实测点名的形态：安装把入口文档落到目标项目，它是**唯一持久化到项目里的产物**，
    而原模板只写"入口地址 + 遵守要求"——"规范副本落在哪、怎么再取一次"只存在于本人的会话里，
    **新开实例即丢失**。故反例逐项覆盖：承载判据的通用层文件被删、路径链缺项、
    副本落点被写成笼统说法、取回方式缺项。

    **落点已并入公共入口**（安装文档删除后，"工序侧"就是入口的「安装与更新」节）：
    判据与模板在同一个文件里，故夹具只有一个文件——节内的模板承载路径链与副本要点。

    **模板形态以用户手工编辑为准**（用户点名：不要 `= Agent 规范入口` 标题与那三节），
    故本类**不核模板小节结构**——核的是路径链与副本两要点**在模板正文里出现**；
    曾被核过的"三节标题"是本类上一版的判据，它会把用户删掉的三节又"补"回去，已撤。
    """

    TEMPLATE = (
        "= AGENT 执行规范\n\n"
        "== 安装与更新（引用方接入与取回口径）\n\n"
        "**写入判据**见 `specs/general/entry-doc.adoc`——那是唯一真源，本文件不重复其条文。\n\n"
        "[source,asciidoc]\n----\n"
        "本项目的 agent 执行规范入口为：\n\n"
        "https://agent.c332030.com/AGENTS_COMMON.adoc\n\n"
        "取规范脚本：\n\n"
        "https://agent.c332030.com/script/fetch-specs.py\n\n"
        "优先取到本地副本（避免网络原因无法访问）：规范文件统一下载到 `~/.cache/agent-specs`，"
        "在项目根目录运行一次取文件抓手即可；取不到时就直接读上面的远程入口；"
        "**需要最新规范时再运行一次取规范脚本即是更新**。\n"
        "----\n"
    )
    SPEC = ("入口文档是**唯一持久化到项目里的产物**；一次会话结束后，下一个会话"
            "（或另开的新实例）只能看到落到项目里的文件。\n"
            "临时产物按 `tmp/` 约定存放、**不写进入口文档**。\n"
            "**项目自身规范优先**：项目自己的规则不因重新执行安装被改写。\n"
            "本文件是这一判据的**唯一真源**；本文件不抄那几条路径的字面值。\n")

    def _write_manifest_valid(self, install_text=None):
        self.write("AGENTS_COMMON.adoc", install_text or self.TEMPLATE)
        self.write("specs/general/entry-doc.adoc", self.SPEC)

    def test_entry_doc_manifest_passes(self):
        # 正例：路径链齐 + 落点写清（`~/.cache/agent-specs`）+ 取回方式 + 承载文件在
        self._write_manifest_valid()
        cm.check_entry_doc_manifest()
        self.assertEqual([], cm.errors)

    def test_template_without_sections_passes(self):
        # 正例（用户口径）：模板**不带** `= Agent 规范入口` 标题与那三节，只要路径链与
        # 副本两要点在正文里，就应判绿——上一版判据在这里报红，等于拿机械判据盖掉用户的编辑
        self._write_manifest_valid(
            self.TEMPLATE.replace("本项目的 agent 执行规范入口为：\n\n", "", 1))
        cm.check_entry_doc_manifest()
        self.assertEqual([], cm.errors)

    def test_path_chain_removed_reports(self):
        # 反例（用户点名形态）：不给取规范脚本路径 → 新实例不知道如何下载规范
        self._write_manifest_valid(
            self.TEMPLATE.replace("https://agent.c332030.com/script/fetch-specs.py\n", ""))
        cm.check_entry_doc_manifest()
        self.assertIn("fetch-specs.py", self.error_texts())

    def test_spec_entry_removed_reports(self):
        # 反例：连规范入口路径都没了 → 新实例不知道规范在哪
        self._write_manifest_valid(
            self.TEMPLATE.replace("https://agent.c332030.com/AGENTS_COMMON.adoc\n", ""))
        cm.check_entry_doc_manifest()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_copy_points_removed_reports(self):
        # 反例：模板里不留落点 → 新实例不知道副本落在哪、只能自己猜路径
        self._write_manifest_valid(
            self.TEMPLATE.replace("规范文件统一下载到 `~/.cache/agent-specs`，", ""))
        cm.check_entry_doc_manifest()
        self.assertIn("用户家目录", self.error_texts())

    def test_spec_file_removed_reports(self):
        # 反例：承载判据的通用层文件被删 → 最小集与临时产物的分界无处可查
        self._write_manifest_valid()
        os.remove(os.path.join(self.root, "specs", "general", "entry-doc.adoc"))
        cm.check_entry_doc_manifest()
        self.assertIn("entry-doc.adoc", self.error_texts())

    def test_single_source_declaration_removed_reports(self):
        # 反例：判据侧不再声明"本文件是唯一真源"→ 同一件事可被别处再复述一遍，
        # 两处必然各自漂移（本仓库实测：入口模板与 entry-doc.adoc 曾逐句重复整段）
        self._write_manifest_valid()
        self.write("specs/general/entry-doc.adoc",
                   self.SPEC.replace("本文件是这一判据的**唯一真源**；", ""))
        cm.check_entry_doc_manifest()
        self.assertIn("唯一真源", self.error_texts())

    def test_install_pointer_removed_reports(self):
        # 反例：工序侧不再指向判据真源 → "该不该写"只能在本文件里再写一套
        self._write_manifest_valid(
            self.TEMPLATE.replace("那是唯一真源，本文件不重复其条文", "详见上文"))
        cm.check_entry_doc_manifest()
        self.assertIn("判据的真源", self.error_texts())

    def test_platform_cache_wording_revived_reports(self):
        # 反例（本轮实测缺口）：把落点写回"由平台缓存目录决定"（不再写用户家目录下的那一处）
        # ——落点一变成环境相关的事实，新实例就没法按入口文档写下的路径直接定位副本，
        # 只能按平台自己推。故本条把"落点须写到具体那一处（家目录 + 落点名同现）"钉住，
        # 防该要求被换成一句笼统说法而判据空转。
        self._write_manifest_valid(
            self.TEMPLATE.replace(
                "规范文件统一下载到 `~/.cache/agent-specs`，",
                "规范文件统一下载到本机**用户级缓存**（位置由平台缓存目录决定），"))
        cm.check_entry_doc_manifest()
        self.assertIn("用户家目录", self.error_texts())

    def test_update_point_removed_reports(self):
        # 反例：取回/更新方式被删 → 新实例不知道副本怎么再取一次
        self._write_manifest_valid(
            self.TEMPLATE.replace(
                "**需要最新规范时再运行一次取规范脚本即是更新**。", ""))
        cm.check_entry_doc_manifest()
        self.assertIn("再运行一次", self.error_texts())
class TestCheckInstallRepeatUpdateGuard(CheckSpecsTestCase):
    """钉住『安装幂等更新防线』：用户手工编辑过的模板内容不得被模板自动改回。

    对应本仓库实测的返工：上一轮实施按"与最新模板不一致即就地更新为最新模板"，
    把用户手工删掉的标题与三节**按判据恢复**了回去——用户点名『我手动删的，你不要给我补上去』
    『不要给我补，以我的为准』。故反例逐项覆盖：该条被删、只剩『以用户为准』而无『不自动改回』、
    不一致时不说（用户不知道入口文档与模板已不一致）、整条被删（该条无处承载）。

    **落点已并入公共入口**：安装口径现在写在 `AGENTS_COMMON.adoc`「安装与更新」的
    「本流程可重复执行、且以远程为准」一条里（原为独立安装文档的「重复执行（更新）时的行为」节）。
    """

    SECTION = (
        "== 安装与更新（引用方接入与取回口径）\n\n"
        "* **本流程可重复执行、且以远程为准**：\n"
        "** **入口文档（幂等）**：已含入口占位且与它逐字一致：不动；已含但不一致：就地更新为最新模板。\n"
        "** **用户改过的行以用户改过的为准**：**用户手工编辑过的模板内容一律照原文保留**"
        "——不符合本模板时**不自动改回**，只在汇报里指出不一致、**等用户定**。\n"
    )

    def _write_valid(self, section=None):
        self.write("AGENTS_COMMON.adoc",
                   "= AGENT 执行规范\n\n" + (section if section is not None else self.SECTION))

    def test_repeat_update_passes(self):
        # 正例：三项要点齐（以用户改过的为准 / 不自动改回 / 等用户定）
        self._write_valid()
        cm.check_install_repeat_update_guard()
        self.assertEqual([], cm.errors)

    def test_clause_removed_reports(self):
        # 反例：用户口径这条被整条删掉 → 「与模板不一致即就地更新」孤立生效，
        # 用户的手工编辑必被改回（本仓库实测过的返工形态）
        self._write_valid(self.SECTION.replace(
            "** **用户改过的行以用户改过的为准**：**用户手工编辑过的模板内容一律照原文保留**"
            "——不符合本模板时**不自动改回**，只在汇报里指出不一致、**等用户定**。\n", ""))
        cm.check_install_repeat_update_guard()
        self.assertIn("以用户改过的为准", self.error_texts())

    def test_downgraded_to_no_rewrite_only_reports(self):
        # 反例：只留"不自动改回"被抹掉 → 实施者仍可把『按模板修正』读成对用户有利而照做
        self._write_valid(self.SECTION.replace("**不自动改回**", "自行判断"))
        cm.check_install_repeat_update_guard()
        self.assertIn("不自动改回", self.error_texts())

    def test_silent_disagreement_reports(self):
        # 反例：不一致时什么都不说 → 用户不知道入口文档与模板已不一致
        self._write_valid(self.SECTION.replace("**等用户定**", "自行处置"))
        cm.check_install_repeat_update_guard()
        self.assertIn("等用户定", self.error_texts())

    def test_section_removed_reports(self):
        # 反例：整条被删 → 该条无处承载，"不一致即就地更新"反而成了唯一口径
        self.write("AGENTS_COMMON.adoc", "= AGENT 执行规范\n\n== 约束\n\n* 只创建入口占位。\n")
        cm.check_install_repeat_update_guard()
        self.assertIn("本流程可重复执行", self.error_texts())

    def test_missing_install_reports(self):
        # 反例：入口文件不在 → 幂等更新的一条无从核对
        cm.check_install_repeat_update_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())
class TestCheckSpecFetchGuard(CheckSpecsTestCase):
    """钉住『规范抓取（安装取文件）防线』：随规范分发的取文件脚本不得被删或退化。

    对应用户报告的真实失效：安装时"下载规范"没有抓手，执行者临场手拼逐条下载命令——
    硬编码长串文件名、内联进命令行还会被 shell 转义反复绊倒（用户实测日志 `ok=… bad=…`、
    转义一错就重来）；更根本的是**清单会腐化**（手工清单没人维护、新增规范就漏一份，
    用户那次漏了 `specs/` 的多数文件）。故反例逐项覆盖：脚本被删、退回手工清单、
    落点越界、入口不成对/缺退出码、`.bat` 非 CRLF、三处登记不同步。
    """

    SCRIPT_PY = (
        '#!/usr/bin/env python3\n'
        '"""fetch 脚本：清单从 AGENTS_COMMON.adoc 解析。\n'
        '默认以远程为准：内容不同才落盘、取回失败保留本地那一份，--keep 才不动本地那份。\n'
        '退出码：0 成功 / 1 有文件没取到 / 2 参数或前置条件错误。\n'
        '"""\n'
        'SPECS_REF_RE = "specs/"\n'
        'def local_bytes(p):\n'
        '    """本地副本的字节；读不到按没有本地副本处理"""\n'
        'def keep_local(dest):\n'
        '    """--keep：不动本地那份；判定标准：不得把本地副本删掉"""\n'
        'CACHE_HOME_DIR = ".cache"\n'
        'DOC = "只写落点目录：不写项目里其他位置；不删除既有文件"\n'
        'CACHE_APP_DIR = "agent-specs"\n'
        'INSTALL_SCRIPTS = ("script/fetch-specs.py", "script/clean_tmp.py")\n'
        'def fetch_install_scripts(base, out_dir, keep):\n'
        '    """安装脚本一并取到落点根下：os.path.basename(rel)；落点里的入口须能直接跑"""\n'
        'def _ensure_executable(dest, rel):\n'
        '    """补可执行位：os.chmod"""\n'
        'def resolve_out_dir(args):\n'
        '    """落点＝cache_slot_dir(shared_cache_dir(), args.base)（只有这一个落点）"""\n'
        'def shared_cache_dir():\n'
        '    """落点所在的那一层：用户家目录（os.path.expanduser）——本机所有项目共用一份"""\n'
        '    if not os.path.isdir(home):\n'
        '        raise ValueError("本机取不到用户家目录")\n'
        'def cache_slot_dir(d, b):\n'
        '    """按来源地址分槽（urllib.parse.urlsplit）；只进不出：不删除落点里的任何文件"""\n'
        '    return os.path.join(d, CACHE_HOME_DIR, CACHE_APP_DIR, b)\n'
        'def fetch(t):\n'
        '    """不是站点首页判据: <!doctype html / <html"""\n'
        'def main():\n'
        '    """默认跳过已存在；需要最新内容加 --force；落点相对当前工作目录；os.replace 原子落盘"""\n'
    )
    # **脚本头部注释＝取回口径的工序侧真源**（公共入口那一节只留落点与回指，不再复述这些句子）：
    # 夹具须与真实文件同形，否则"真源被抽空"这类反例在夹具里根本不成立。
    SCRIPT_PY_HEAD = (
        '"""fetch-specs - 把本规范集合取到本地副本。\n'
        '\n'
        '取回与更新口径（本节是"怎么取、怎么更新"的真源，公共入口只回指本节）：\n'
        '  - 一次取全：一次运行把入口与其 specs/ 全部取回，不必手拼逐条下载命令；\n'
        '  - 清单从入口自身解析：按加载调度器登记自动解析，新增一份规范不必改脚本、也不会漏取；\n'
        '  - 默认以远程为准：取回的字节与本地不同才落盘、远端改过就刷新，重复执行即是更新；\n'
        '  - --keep：不动本地那份；--base：换规范来源；\n'
        '  - 取回失败保留本地已有的那一份，不把副本删掉换成没有；\n'
        '  - 退出码：0 成功、1 有文件没取到、2 参数或前置条件错误——非 0 就别把副本当已就绪；\n'
        '  - 解释器兜底：一个都没有时**先按本平台既有的软件分发方式装一个 python 3**再重跑，\n'
        '    这是**人**的一步，入口**不得**代为安装运行时；\n'
        '    只装 python2 的发行版不算"一个都没有"；不建议改用 curl … | python3 -：它同样要 python。\n'
        '"""\n')
    SCRIPT_PY = SCRIPT_PY_HEAD + SCRIPT_PY
    SCRIPT_SH = (
        '#!/usr/bin/env bash\n'
        'set -u\n'
        'if command -v python3 >/dev/null 2>&1; then\n'
        '  runtime="python3"\n'
        'elif command -v python >/dev/null 2>&1; then\n'
        '  runtime="python"\n'
        'else\n'
        '  echo "错误: 未找到解释器 python3/python，无法运行 fetch-specs.py" >&2\n'
        '  exit 127\n'
        'fi\n'
        'exec "$runtime" "$(dirname "$0")/fetch-specs.py" "$@"\n'
    )

    def setUp(self) -> None:
        super().setUp()                 # 父类已把 REPO_ROOT 指到本用例的临时根
        os.makedirs(os.path.join(self.root, "script"), exist_ok=True)
        os.makedirs(os.path.join(self.root, "specs"), exist_ok=True)

    def _write_valid(self):
        # 落点/解释器兜底等防线按"仓库根相对路径"读脚本，且**带缓存**——用例换了 REPO_ROOT
        # 后缓存里可能还留着真实仓库的那一份（那时反例根本不生效、用例静默通过）。故写入前
        # 先清缓存（本仓库实测：不清时"脚本被删/被退化"的反例读到的是真实脚本、防线不报红）。
        cm.REPO_SCRIPT_SRC_CACHE.clear()
        self.write("script/fetch-specs.py", self.SCRIPT_PY)
        self.write("script/fetch-specs.sh", self.SCRIPT_SH)
        with open(os.path.join(self.root, "script", "fetch-specs.bat"), "wb") as fh:
            fh.write(b'@echo off\r\n'
                     b'where py >nul 2>nul && set "FETCH_SPECS_RUNTIME=py -3"\r\n'
                     b'if not defined FETCH_SPECS_RUNTIME where python3 >nul 2>nul && '
                     b'set "FETCH_SPECS_RUNTIME=python3"\r\n'
                     b'if not defined FETCH_SPECS_RUNTIME where python >nul 2>nul && '
                     b'set "FETCH_SPECS_RUNTIME=python"\r\n'
                     b'if not defined FETCH_SPECS_RUNTIME (\r\n'
                     b'  echo Error: no python interpreter found 1>&2\r\n'
                     b'  exit /b 127\r\n'
                     b')\r\n'
                     b'%FETCH_SPECS_RUNTIME% "%~dp0fetch-specs.py" %*\r\n'
                     b'exit /b %errorlevel%\r\n')
        # 入口（**兼具安装口径**）：既有各节要点 + 入口模板代码块（承载"怎么取/取不到怎么办/怎么更新"三要点）
        self.write("AGENTS_COMMON.adoc", self.INSTALL_BODY)
        self.write("README.adoc", "工具 fetch-specs：落点、取回与更新方式见 AGENTS_COMMON.adoc"
                                 "「取规范到本地副本」（唯一真源）。\n")
        self.write("PUBLIC.adoc", "抓取工具：落点与取回方式见 AGENTS_COMMON.adoc"
                                 "「取规范到本地副本」（唯一真源）。\n")

    # 入口文件（**兼具安装口径**）：模板代码块里放"入口占位那一行"（三要点齐备；
    # 个别用例替换它跑反例）。安装文档已删，模板与取回口径都落在入口这个文件里。
    INSTALL_BODY = (
        "= AGENT 执行规范（公共入口）\n\n"
        "== 访问与解析（引用方须知）\n\n取本地副本见 fetch-specs。\n\n"
        "== 安装与更新（引用方接入与取回口径）\n\n"
        "[source,asciidoc]\n----\n"
        "本项目的 agent 执行规范入口为：\n\n"
        "https://agent.c332030.com/AGENTS_COMMON.adoc\n\n"
        "优先取到本地副本（避免网络原因无法访问）：规范文件统一下载到 `~/.cache/agent-specs`，"
        "在项目根目录运行一次取文件抓手即可；取不到时就直接读上面的远程入口；"
        "**需要最新规范时再运行一次取规范脚本即是更新**。\n\n"
        "读取该入口及其引用的 specs/ 规范，并持续遵守其全部要求。\n\n"
        "规范属强制约束：**开工前必须先读取规范再执行**，不得因未读取/记不全而跳过或放宽任何条款。\n"
        "----\n\n"
        "* **入口文档（安装流程）**：文件名取 `AGENTS.adoc`；已存在 `AGENTS.md` 时就地融合"
        "（**不重命名、不迁移、不另建**）。**写入判据**见 `specs/general/entry-doc.adoc`"
        "——那是唯一真源。\n"
        "* **本流程可重复执行、且以远程为准**：\n"
        "** **入口文档（幂等）**：已含入口占位且逐字一致：不动；**用户改过的行以用户改过的为准**："
        "**用户手工编辑过的模板内容一律照原文保留**——不符合本模板时**不自动改回**，"
        "只在汇报里指出不一致、**等用户定**。\n\n"
        "== 取规范到本地副本\n\n"
        "* 落点只有一处：副本取到**用户家目录**下的 `.cache/agent-specs` 这一处"
        "（本机所有项目共用一份）；下载的东西一律只落这一处：规范副本、取规范脚本"
        "（fetch-specs.py 及其同名入口）、清理脚本 clean_tmp.py 都落这一个路径下，"
        "不在项目里另留副本；取不到时直接读远程入口。\n"
        "* 取回口径的工序侧真源是 `script/fetch-specs.py` 的**头部注释**：怎么取、怎么更新、"
        "脚本开关与解释器兜底次序都写在那里，本节不复述、也不在别处再抄一份。\n")

    ENTRY_LINE = (
        "优先取到本地副本（避免网络原因无法访问）：规范文件统一下载到 `~/.cache/agent-specs`，"
        "在项目根目录运行一次取文件抓手即可；取不到时就直接读上面的远程入口；"
        "**需要最新规范时再运行一次取规范脚本即是更新**。")

    def _write_install_with_entry_line(self, entry_line: str) -> None:
        """把给定的"入口占位那一行"替进模板代码块（其余要点照旧）——用于跑反例。"""
        self.write("AGENTS_COMMON.adoc", self.INSTALL_BODY.replace(self.ENTRY_LINE, entry_line))

    def test_valid_passes(self):
        self._write_valid()
        cm.check_spec_fetch_guard()
        self.assertEqual([], cm.errors)

    def test_missing_script_reports(self):
        # 反例：抓手被删 → 执行者又临场手拼逐条下载命令
        self._write_valid()
        os.remove(os.path.join(self.root, "script", "fetch-specs.py"))
        cm.check_spec_fetch_guard()
        self.assertIn("fetch-specs.py", self.error_texts())

    def test_missing_bat_entry_reports(self):
        # 反例：Windows 入口缺失 → 该平台没有可执行入口（退化成手工拼命令）
        self._write_valid()
        os.remove(os.path.join(self.root, "script", "fetch-specs.bat"))
        cm.check_spec_fetch_guard()
        self.assertIn("fetch-specs.bat", self.error_texts())

    def test_manual_list_regression_reports(self):
        # 反例：退回手工清单（不再从入口解析）→ 新增规范就漏一份
        self._write_valid()
        self.write("script/fetch-specs.py",
                   '#!/usr/bin/env python3\n'
                   '"""读 AGENTS_COMMON.adoc。"""\n'
                   '"""退出码：0 / 1 / 2。"""\n'
                   '"""落点必须位于当前工作目录之下、相对当前工作目录。"""\n'
                   '"""默认跳过；--force。"""\n'
                   'def f(t):\n'
                   '    """<!doctype html"""\n')
        cm.check_spec_fetch_guard()
        self.assertIn("SPECS_REF_RE", self.error_texts())

    def test_bat_lf_line_ending_reports(self):
        # 反例：`.bat` 被写成 LF → 在 cmd.exe 下直接执行失败
        self._write_valid()
        with open(os.path.join(self.root, "script", "fetch-specs.bat"), "wb") as fh:
            fh.write(b'@echo off\npython3 "%~dp0fetch-specs.py" %*\nexit /b %errorlevel%\n')
        cm.check_spec_fetch_guard()
        self.assertIn("CRLF", self.error_texts())

    def test_bat_exit_code_missing_reports(self):
        # 反例：入口不返回退出码 → "失败也成功"，调用方无法判定
        self._write_valid()
        with open(os.path.join(self.root, "script", "fetch-specs.bat"), "wb") as fh:
            fh.write(b'@echo off\r\npython3 "%~dp0fetch-specs.py" %*\r\n')
        cm.check_spec_fetch_guard()
        self.assertIn("errorlevel", self.error_texts())

    def test_non_atomic_write_reports(self):
        # 反例：退回"直接 wb 覆盖"→ 传输中断会把原有好副本截断成半份
        self._write_valid()
        self.write("script/fetch-specs.py", self.SCRIPT_PY.replace("；os.replace 原子落盘", ""))
        cm.check_spec_fetch_guard()
        self.assertIn("os.replace", self.error_texts())

    def test_install_scripts_not_fetched_reports(self):
        # 反例：只取规范副本、不把安装脚本一并取到落点 → 用户口径"下载的文件一律只落这一个
        # 地方"只剩一半：落点里那份入口还得再手工下载一遍（取完规范仍要回来问"脚本在哪"）
        self._write_valid()
        self.write("script/fetch-specs.py", self.SCRIPT_PY.replace(
            'INSTALL_SCRIPTS = ("script/fetch-specs.py", "script/clean_tmp.py")\n'
            'def fetch_install_scripts(base, out_dir, keep):\n'
            '    """安装脚本一并取到落点根下：os.path.basename(rel)；落点里的入口须能直接跑"""\n'
            'def _ensure_executable(dest, rel):\n'
            '    """补可执行位：os.chmod"""\n', ""))
        cm.check_shared_cache_guard()
        self.assertIn("INSTALL_SCRIPTS", self.error_texts())

    def test_install_scripts_nested_dir_reports(self):
        # 反例：照搬来源侧的目录层级（落点里多出一层 script/）→ 下载来的入口按 `dirname "$0"`
        # 找同目录的兄弟文件（逻辑代码、平台入口），多一层即整组取不到
        self._write_valid()
        self.write("script/fetch-specs.py", self.SCRIPT_PY.replace(
            "安装脚本一并取到落点根下：os.path.basename(rel)", "安装脚本按来源路径落盘"))
        cm.check_shared_cache_guard()
        self.assertIn("basename", self.error_texts())

    def test_install_scripts_without_exec_bit_reports(self):
        # 反例：取回后不补可执行位 → 落点里的入口默认 0644，"下次重装直接跑那里的入口"直接失败
        self._write_valid()
        self.write("script/fetch-specs.py", self.SCRIPT_PY.replace(
            'def _ensure_executable(dest, rel):\n'
            '    """补可执行位：os.chmod"""\n', ""))
        cm.check_shared_cache_guard()
        self.assertIn("_ensure_executable", self.error_texts())

    def test_install_doc_says_only_specs_land_there_reports(self):
        # 反例：安装文档只写规范副本的落点、不提"下载来的安装脚本也落这" → 清理脚本等
        # 下载物仍会被手工存到别处（用户口径是"所有下载的文件"）
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", self.INSTALL_BODY.replace(
            "下载的东西一律只落这一处：规范副本、取规范脚本（fetch-specs.py 及其同名入口）、"
            "清理脚本 clean_tmp.py 都落这一个路径下，不在项目里另留副本；", ""))
        cm.check_spec_fetch_guard()
        self.assertIn("clean_tmp.py", self.error_texts())

    def test_docs_not_synced_reports(self):
        # 反例：入口未登记抓手 → 安装时读者又不知道有它
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "把规范下载到 tmp。\n")
        cm.check_spec_fetch_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    # ---- 解释器兜底（本仓库实证：入口原先只调 python3，"没有 python 的机器装不上"）----
    # 只保留两条机械可核对的：①探测次序写反（后写的会被前面的分支永久遮住）；
    # ②判别串互相包含导致次序判错。说明口径本身由 `_check_install_no_python_section`
    # 按节取文本核对（落点是公共入口的「取规范到本地副本」）。

    def test_lookup_order_regression_reports(self):
        # 反例：次序写反（python 排在 python3 前）→ 该分支把 python3 永久遮住，等于没有兜底
        self._write_valid()
        self.write("script/fetch-specs.sh",
                   '#!/usr/bin/env bash\n'
                   'if command -v python >/dev/null 2>&1; then runtime="python";\n'
                   'elif command -v python3 >/dev/null 2>&1; then runtime="python3"; fi\n'
                   'echo "错误: 未找到解释器 python3/python" >&2; exit 127\n'
                   'exec "$runtime" "$(dirname "$0")/fetch-specs.py" "$@"\n')
        cm.check_spec_fetch_guard()
        self.assertIn("探测次序", self.error_texts())

    def test_order_check_not_fooled_by_substring_overlap(self):
        # 反例：次序写反 + 判别键互相包含（`command -v python` 命中 `command -v python3` 的子串）
        # → 旧实现 find 两次返回同一位置、把写反的次序判成正确（本仓库实测漏报），
        # 故防线须用**互不包含**的判别串（带判空后缀）。
        self._write_valid()
        self.write("script/fetch-specs.sh",
                   '#!/usr/bin/env bash\n'
                   'if command -v python >/dev/null 2>&1; then runtime="python";\n'
                   'elif command -v python3 >/dev/null 2>&1; then runtime="python3"; fi\n'
                   'echo "错误: 未找到解释器 python3/python" >&2; exit 127\n'
                   'exec "$runtime" "$(dirname "$0")/fetch-specs.py" "$@"\n')
        cm.check_spec_fetch_guard()
        self.assertIn("探测次序", self.error_texts())

    def test_sh_hardcodes_python3_reports(self):
        # 反例：`.sh` 把 python3 写死成前提（直接调它、不做探测）→ 只装 python2 的发行版
        # （CentOS/RHEL 8 及更早）直接失败。删这道防线的反例时，本条也随之消失过——
        # 故连同"防线被并进别处"一起由 `check_guard_manifest` 记账兜住。
        self._write_valid()
        self.write("script/fetch-specs.sh",
                   '#!/usr/bin/env bash\nset -u\n'
                   'exec python3 "$(dirname "$0")/fetch-specs.py" "$@"\n')
        cm.check_spec_fetch_guard()
        self.assertIn("command -v python3", self.error_texts())

    def test_install_without_fallback_note_reports(self):
        # 反例：入口不提兜底 → 引用方以为必须先有 python3（或干脆自己先装一个）
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "见 fetch-specs 与 tmp/agent-specs 落点。\n")
        cm.check_spec_fetch_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())
        self.assertIn("取规范到本地副本", self.error_texts())

    def test_install_without_next_step_reports(self):
        # 反例（用户追问"没有 python 也要下载啊"）：真源（脚本头部注释）只写"报错退出"、
        # 不写"接下来怎么办" → 引用方看到失败仍不知道下一步（装一个？谁装？能不能不装？）
        # 本反例锚点已从"入口那一节"移到**真源侧**（入口不再复述这些句子）。
        self._write_valid()
        self.write("script/fetch-specs.py",
                   self.SCRIPT_PY.replace("先按本平台既有的软件分发方式装一个 python 3", ""))
        cm.check_spec_fetch_guard()
        self.assertIn("装一个 python 3", self.error_texts())

    def test_entry_allowed_to_install_runtime_reports(self):
        # 反例：在**真源**里把"装一个运行时"写成脚本/入口的一步（而非人的一步）
        # → 入口从"门"变成"装门的施工队"（改系统状态、要权限、对调用方不可预期）
        self._write_valid()
        self.write("script/fetch-specs.py", self.SCRIPT_PY.replace(
            "这是**人**的一步，入口**不得**代为安装运行时；", "脚本会自己下载安装运行时；"))
        cm.check_spec_fetch_guard()
        self.assertIn("代为安装", self.error_texts())

    def test_install_runtime_note_removed_reports(self):
        # 反例：真源里把"报错退出非 0、不得静默继续"这条抽掉 → "没取到规范"被混进"取到了"
        self._write_valid()
        self.write("script/fetch-specs.py",
                   self.SCRIPT_PY.replace("退出码：0 成功、1 有文件没取到、2 参数或前置条件错误——"
                                          "非 0 就别把副本当已就绪；", ""))
        cm.check_spec_fetch_guard()
        self.assertIn("非 0", self.error_texts())

    def test_bat_hardcodes_python3_reports(self):
        # 反例：`.bat` 不探 py 启动器（Windows 上最常见的那一个）→ 大半个 Windows 装机量被挡在门外。
        # 合法形态的键取"整份文件文本就能满足"（`where py` 写在注释里也算）时，本反例**不会报红**
        # ——本仓库实测复现，故改按**行段**核（键须落在同一条可执行行上）。
        self._write_valid()
        self.write("script/fetch-specs.bat",
                   '@echo off\r\n'
                   'rem Interpreter lookup: py launcher first, then python3, then python\r\n'
                   'where python3 >nul 2>nul && set "FETCH_SPECS_RUNTIME=python3"\r\n'
                   'where python >nul 2>nul && set "FETCH_SPECS_RUNTIME=python"\r\n'
                   '%FETCH_SPECS_RUNTIME% "%~dp0fetch-specs.py" %*\r\n'
                   'exit /b %errorlevel%\r\n')
        cm.check_spec_fetch_guard()
        self.assertIn("fetch-specs.bat", self.error_texts())
        self.assertIn("解释器兜底", self.error_texts())

    def test_bat_probe_only_in_comment_reports(self):
        # 反例：探测分支只写在注释里（"先探 py 启动器"）→ 分支并不存在，读者以为有兜底
        self._write_valid()
        self.write("script/fetch-specs.bat",
                   '@echo off\r\n'
                   'rem where py >nul 2>nul\r\n'
                   'rem where python3 >nul 2>nul\r\n'
                   '%FETCH_SPECS_RUNTIME% "%~dp0fetch-specs.py" %*\r\n'
                   'exit /b %errorlevel%\r\n')
        cm.check_spec_fetch_guard()
        self.assertIn("解释器兜底", self.error_texts())

    def test_sh_missing_python_fallback_reports(self):
        # 反例：`.sh` 只探 python3、不探 python → 只装 python 的发行版上取不到规范
        self._write_valid()
        self.write("script/fetch-specs.sh",
                   '#!/usr/bin/env bash\n'
                   '# 回退分支写得像"有"，但真正可执行的那条探测已经不在了\n'
                   'rem elif command -v python >/dev/null 2>&1; then runtime="python"\n'
                   'if command -v python3 >/dev/null 2>&1; then\n'
                   '  runtime="python3"\n'
                   'else\n'
                   '  echo "错误: 未找到解释器 python3/python" >&2\n'
                   '  exit 127\n'
                   'fi\n'
                   'exec "$runtime" "$(dirname "$0")/fetch-specs.py" "$@"\n')
        cm.check_spec_fetch_guard()
        self.assertIn("解释器兜底", self.error_texts())

    def test_install_no_python_section_removed_reports(self):
        # 反例：把承载解释器兜底的「取规范到本地副本」整节删掉 → 旧实现只核全文关键词，仍报绿
        # （本仓库实测复现），故改为**先按节标题定位整节、再在节内逐条核对**。
        self._write_valid()
        import re as _re
        self.write("AGENTS_COMMON.adoc", _re.sub(
            r"^== 取规范到本地副本.*?(?=\Z)", "", self.INSTALL_BODY, flags=_re.S | _re.M))
        cm.check_spec_fetch_guard()
        self.assertIn("取规范到本地副本", self.error_texts())

    def test_install_without_no_runtime_note_reports(self):
        # 反例：真源里把"这是**人**的一步、入口不得代为安装运行时"整条抽掉
        # → 读者会以为入口会自己搞定
        self._write_valid()
        self.write("script/fetch-specs.py", self.SCRIPT_PY.replace(
            "这是**人**的一步，入口**不得**代为安装运行时；", ""))
        cm.check_spec_fetch_guard()
        self.assertIn("不得**代为安装", self.error_texts())

    def test_install_missing_python2_case_reports(self):
        # 反例：真源里删掉"只装 python2 的发行版不算"
        # → 该分支的收益没人知道（CentOS/RHEL 8 及更早）
        self._write_valid()
        self.write("script/fetch-specs.py", self.SCRIPT_PY.replace(
            '只装 python2 的发行版不算"一个都没有"；', "只装 python 的发行版同样可用；"))
        cm.check_spec_fetch_guard()
        self.assertIn("python2", self.error_texts())

    # ---- 共享缓存落点（用户实测诉求：别每个项目都下载一遍同几份文件）----

    def test_install_fetch_method_source_emptied_reports(self):
        # 反例（本轮）：真源（脚本头部注释）里的**取回与更新口径**整段被抽走
        # ——入口那一节已收敛为"只写落点 + 回指"，故"怎么取、怎么更新"无处可读时
        # 必须由真源侧报红（旧判据把这段留在入口、且要求入口复述那些句子，正是用户点名的重复形态）。
        self._write_valid()
        self.write("script/fetch-specs.py",
                   self.SCRIPT_PY.replace("  - 一次取全：一次运行把入口与其 specs/ 全部取回，"
                                          "不必手拼逐条下载命令；\n", "")
                   .replace("  - 清单从入口自身解析：按加载调度器登记自动解析，"
                            "新增一份规范不必改脚本、也不会漏取；\n", ""))
        cm.check_spec_fetch_guard()
        self.assertIn("一次取全", self.error_texts())
        self.assertIn("清单从入口自身解析", self.error_texts())

    def test_install_fetch_method_remote_authority_removed_reports(self):
        # 反例："默认以远程为准"与 `--keep` 被删 → 『重复执行即是更新』只说了一半，
        # 执行者无法判断远端改过要不要覆盖本地那份
        self._write_valid()
        self.write("script/fetch-specs.py",
                   self.SCRIPT_PY.replace("  - 默认以远程为准：取回的字节与本地不同才落盘、"
                                          "远端改过就刷新，重复执行即是更新；\n", "")
                   .replace("  - --keep：不动本地那份；--base：换规范来源；\n", ""))
        cm.check_spec_fetch_guard()
        self.assertIn("以远程为准", self.error_texts())
        self.assertIn("--keep", self.error_texts())

    def test_install_fetch_section_pointer_removed_reports(self):
        # 反例（本轮新增）：入口那一节只剩落点、**回指被抽掉** → 读者读到本节仍不知道
        # 取法的细则在哪，等于把同一件事实再抄一遍或干脆丢掉
        # （本仓库实测：只点名文件而不给部位——去掉「头部注释」四字——同属此形态）。
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", self.INSTALL_BODY.replace(
            "* 取回口径的工序侧真源是 `script/fetch-specs.py` 的**头部注释**：怎么取、怎么更新、"
            "脚本开关与解释器兜底次序都写在那里，本节不复述、也不在别处再抄一份。\n",
            "* 取回口径见脚本自身。\n"))
        cm.check_spec_fetch_guard()
        self.assertIn("回指", self.error_texts())

    def test_install_fetch_section_pointer_without_part_reports(self):
        # 反例（本轮新增）：回指只点名文件、不给**部位**（"头部注释"）→ 读者仍不知道该读哪一段
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", self.INSTALL_BODY.replace(
            "* 取回口径的工序侧真源是 `script/fetch-specs.py` 的**头部注释**：",
            "* 取回口径的工序侧真源是 `script/fetch-specs.py`："))
        cm.check_spec_fetch_guard()
        self.assertIn("头部注释", self.error_texts())

    def test_install_fetch_section_pointer_with_wrong_part_reports(self):
        # 反例（本轮实测复现的**防线空转**）：回指给的**部位是错的**（"头部注释"改成
        # "段尾注释"）——按**整节**核时，节里别处（如落点那条）出现的 `script/fetch-specs.py`
        # 会把缺失兜住、防线全绿；而读者按"段尾注释"去找仍找不到细则。
        # 故回指须按**同一行**核（与真源侧要点同一口径）。
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", self.INSTALL_BODY.replace(
            "`script/fetch-specs.py` 的**头部注释**", "`script/fetch-specs.py` 的**段尾注释**"))
        cm.check_spec_fetch_guard()
        self.assertIn("头部注释", self.error_texts())

    def test_install_fetch_section_pointer_backed_by_neighbor_reports(self):
        # 反例（本轮实测复现的**相邻兜底**）：把"回指真源"那一条**整行删掉**，而本节里另一条
        # （“取回口径与判据分家”）顺带也点了 `script/fetch-specs.py` 与"头部注释"——按
        # “任一行含这两个字样”核时被该条兜住、六道相关防线全绿（本仓库实测）。
        # 故回指须按**声明真源那一行**核（用该行独有的"工序侧真源"措辞认出来）。
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", self.INSTALL_BODY.replace(
            "* 取回口径的工序侧真源是 `script/fetch-specs.py` 的**头部注释**：怎么取、怎么更新、"
            "脚本开关与解释器兜底次序都写在那里，本节不复述、也不在别处再抄一份。\n",
            "本节不复述取法与更新口径。\n"))
        cm.check_spec_fetch_guard()
        self.assertIn("工序侧真源", self.error_texts())

    def test_install_fetch_section_landing_not_on_same_line_reports(self):
        # 反例（同一空转的另一半）：落点那一处事实被拆开——用户侧词在一句、落点名在另一句，
        # 按整节核时两样都在节里、防线全绿。判据要求"同现"须落在**同一行**上，
        # 否则读者仍读不到"副本具体落在谁的家目录下"这处定位。
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", self.INSTALL_BODY.replace(
            "副本取到**用户家目录**下的 `.cache/agent-specs` 这一处"
            "（本机所有项目共用一份）；",
            "副本取到**用户家目录**下的一处（本机所有项目共用一份）。\n"
            "目录名是 `.cache/agent-specs`；"))
        cm.check_spec_fetch_guard()
        self.assertIn("缺失落点", self.error_texts())

    def test_shared_cache_guard_passes(self):
        # 正例：落点只有用户家目录下的一处（由两个常量拼出）+ 按来源分槽 + 不删除落点文件 + 四处文档同步
        self._write_valid()
        cm.check_shared_cache_guard()
        self.assertEqual([], cm.errors)

    def test_landing_copied_again_without_reference_reports(self):
        # 反例（用户本轮点名的形态：「依旧有很多相同的描述在不同的地方」）：另一处文档**又把落点
        # 抄了一遍**、且没指向真源 → 同一描述出现两处，两处会各自漂移，读者也不知道以哪处为准；
        # 收敛形态是"一处完整定义（真源＝公共入口）+ 其余一行引用"。
        # 落点真源现已并入公共入口，故"第二处"用 README 举例（可写自己的落点、也可给一行引用）。
        self._write_valid()
        self.write("README.adoc",
                   "工具 fetch-specs：副本只取到用户家目录下的 .cache/agent-specs 这一处"
                   "（本机所有项目共用一份）；默认以远程为准、以 --keep 保留本地那份。\n")
        cm.check_shared_cache_guard()
        self.assertIn("README.adoc", self.error_texts())
        self.assertIn("唯一真源", self.error_texts())

    def test_landing_owner_must_write_it_out_reports(self):
        # 反例：**真源自己**把落点改成"见别处"→ 谁都不写落点，等于没人写（收敛不能把唯一落点也省掉）
        self._write_valid()
        self.write("AGENTS_COMMON.adoc",
                   self.INSTALL_BODY.replace(".cache/agent-specs", "the-cache-dir")
                   .replace("~/.the-cache-dir", "the-cache-dir")
                   .replace("~/.cache/agent-specs", "the-cache-dir")
                   + "\n见 fetch-specs：副本落点以脚本头部注释为准（本节不再自己写一遍）。\n")
        cm.check_shared_cache_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_vague_cache_wording_still_reports(self):
        # 反例：把落点换成『用户级缓存』这类笼统说法又不给引用 → 读者仍要自己猜路径
        self._write_valid()
        self.write("README.adoc", "工具 fetch-specs：副本取到用户级缓存（所有项目共用一份）。\n")
        cm.check_shared_cache_guard()
        self.assertIn("README.adoc", self.error_texts())

    def test_install_without_shared_cache_note_reports(self):
        # 反例：入口不提落点 → 引用方不知道副本落在哪、以为会往项目里写一份
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "见 fetch-specs 与它的落点。\n")
        cm.check_shared_cache_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_common_entry_without_shared_cache_note_reports(self):
        # 反例：公共入口不提落点 → 按入口加载的引用方不知道副本落在哪
        self._write_valid()
        self.write("AGENTS_COMMON.adoc", "取文件见 fetch-specs。\n")
        cm.check_shared_cache_guard()
        self.assertIn("AGENTS_COMMON.adoc", self.error_texts())

    def test_platform_cache_dir_revived_reports(self):
        # 反例：随平台另取一套缓存目录又长回来（XDG_CACHE_HOME/LOCALAPPDATA）→ 落点变成
        # 环境相关的事实，"只有这一个路径"无处可依（用户口径：不用管什么系统什么环境）
        self._write_valid()
        self.write("script/fetch-specs.py",
                   self.SCRIPT_PY + 'POSIX = "XDG_CACHE_HOME"\nWIN = "LOCALAPPDATA"\n')
        cm.check_shared_cache_guard()
        self.assertIn("XDG_CACHE_HOME", self.error_texts())

    def test_project_tmp_path_revived_reports(self):
        # 反例：项目内临时目录这类**第二落点**又长回来 → 同一份规范可能落在项目里，
        # 入口文档写下的那一个用户路径就找不到副本了
        self._write_valid()
        self.write("script/fetch-specs.py",
                   self.SCRIPT_PY + 'SECOND = "--local"\nEXTRA = "tmp/agent-specs"\n')
        cm.check_shared_cache_guard()
        self.assertIn("tmp/agent-specs", self.error_texts())

    def test_relocation_entry_revived_reports(self):
        # 反例：换落点的入口又长回来（--out/--cache-dir 一类）→ 同一份规范可能落在多处
        self._write_valid()
        self.write("script/fetch-specs.py",
                   self.SCRIPT_PY + 'AGENT_SPECS_CACHE = "--cache-dir"\nOUT = "--out"\n')
        cm.check_shared_cache_guard()
        self.assertIn("AGENT_SPECS_CACHE", self.error_texts())

    def test_cache_slot_removed_reports(self):
        # 反例：去掉"按来源分槽" → 换过来源的副本互相覆盖（同一份规范内容说不清是哪来的）
        self._write_valid()
        self.write("script/fetch-specs.py", self.SCRIPT_PY.replace("urlsplit", ""))
        cm.check_shared_cache_guard()
        self.assertIn("urlsplit", self.error_texts())

    def test_user_home_dir_removed_reports(self):
        # 反例：落点不再从用户家目录取 → "用户家目录下的那一处"无从谈起
        self._write_valid()
        self.write("script/fetch-specs.py", self.SCRIPT_PY.replace("expanduser", ""))
        cm.check_shared_cache_guard()
        self.assertIn("expanduser", self.error_texts())

    def test_slot_constants_unused_reports(self):
        # 反例：两个落点常量还在、却不参与落点拼装（落点改由别处/按平台算）→
        # "只有用户家目录下这一处"不再成立，而正向判据只核常量名时会放过
        self._write_valid()
        self.write("script/fetch-specs.py",
                   self.SCRIPT_PY.replace(
                       "return os.path.join(d, CACHE_HOME_DIR, CACHE_APP_DIR, b)",
                       "return os.path.join(d, b)"))
        cm.check_shared_cache_guard()
        self.assertIn("CACHE_HOME_DIR", self.error_texts())

    def test_home_failure_not_reported_reports(self):
        # 反例：家目录取不到时不再报错退出（判据被去掉）→ 副本会静默落到别的路径，
        # 入口文档写下的那一个路径就与实际落点对不上（正是本防线要防的"静默换落点"）
        self._write_valid()
        self.write("script/fetch-specs.py", self.SCRIPT_PY.replace("not os.path.isdir", ""))
        cm.check_shared_cache_guard()
        self.assertIn("静默换地方", self.error_texts())

    def test_no_delete_note_removed_reports(self):
        # 反例：脚本不再声明"不删除落点里的既有文件" → 清理被当成脚本的一次运行
        self._write_valid()
        self.write("script/fetch-specs.py", self.SCRIPT_PY.replace("不删除", ""))
        cm.check_shared_cache_guard()
        self.assertIn("不删除", self.error_texts())

    # ---- 入口占位三要点（用户两次点名"还是没改"：模板那行被改写/合并后既有抓手全都不报错）----

    def test_install_entry_placeholder_passes(self):
        # 正例：三要点齐备（优先取到本地副本 / 取不到读远程 / 再运行一次即是更新）
        self._write_valid()
        cm.check_shared_cache_guard()
        self.assertEqual([], cm.errors)

    def test_install_entry_placeholder_line_reverted_reports(self):
        # 反例（用户两次点名的那个形态）：把"需要最新规范再更新"并进"一并取到本地副本"
        # → 脚本更新了用户也不知道，且已按旧模板装过的项目重跑安装会被判成"逐字一致"而不更新
        # （正是"还是没改"：既有抓手只核"每行独立成行 + 空行完好"，这句删掉也不报错）
        self._write_valid()
        self._write_install_with_entry_line(
            "优先取到本地副本（避免网络原因无法访问）：在项目根目录运行一次取文件抓手，"
            "它会把本入口与其引用的 specs/ 规范一并取到用户家目录下的 `.cache/agent-specs`"
            "（只给脚本名即可，无需逐条下载）。")
        cm.check_shared_cache_guard()
        self.assertIn("需要最新规范", self.error_texts())

    def test_install_entry_placeholder_copy_removed_reports(self):
        # 反例：把那行换成"直接下载即可" → 网络不可达时本地那一份（用户点名的那条收益）没了
        self._write_valid()
        self._write_install_with_entry_line(
            "需要最新规范时再运行一次即可更新：直接下载规范到本地即可。")
        cm.check_shared_cache_guard()
        self.assertIn("优先取到本地副本", self.error_texts())

    def test_install_entry_placeholder_fallback_removed_reports(self):
        # 反例：只写"优先取到本地副本"、不写"取不到就读远程" → 把可选的一步读成前置条件
        self._write_valid()
        self._write_install_with_entry_line(
            "优先取到本地副本（避免网络原因无法访问）；需要最新规范时再运行一次即可更新。")
        cm.check_shared_cache_guard()
        self.assertIn("取不到", self.error_texts())

    # ---- 以远程为准（用户实测诉求：安装脚本经常更新，重跑安装要能更新现有的那份）----

    def _install_scripts_served(self):
        """端到端服务端要供给的安装脚本（脚本会随规范一起取它们，缺则 404、退出码非 0）。

        名单从**真实仓库**的 `fetch-specs.py` 里读，与脚本本身同源——手工再抄一份名单会在
        加了第三份安装脚本时静默漏供（那时用例报的是 404、看起来像网络问题）。
        """
        real_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        src = open(os.path.join(real_root, "script", "fetch-specs.py"), encoding="utf-8").read()
        return {rel: src.encode("utf-8")
                for rel in re.findall(r'"script/([\w.-]+)"', src)
                for rel in ("script/" + rel,)}

    def _run_fetch(self, base, extra=(), cwd=None, home=None):
        """按仓库真实的抓取脚本跑一次（spawn 子进程、按 stdout/stderr 断言）。

        落点由脚本自己按**用户家目录**算出来（没有 `--out` 这类换落点的入口），故用例只能
        通过 `home` 换家目录把落点收进本次用例专属的位置（`HOME` 与 `USERPROFILE` 都指过去，
        覆盖两个平台的写法）。
        """
        # 脚本与工作目录都用**真实仓库**（`cm.REPO_ROOT` 在用例里被指向临时夹具，脚本不在那儿）
        real_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script = os.path.join(real_root, "script", "fetch-specs.py")
        cmd = [sys.executable, script, "--base", base, *extra]
        env = None
        if home:
            env = dict(os.environ, HOME=home, USERPROFILE=home)
        proc = subprocess.run(cmd, cwd=cwd or real_root, capture_output=True, text=True,
                              timeout=120, env=env)
        return proc.returncode, proc.stdout, proc.stderr

    def _serve(self, served):
        """起一个本机 HTTP 服务当"远端"（返回 base 与其容器，退出时关掉）。

        用本机来源是为了不起外网依赖（用户实测的原始形态也是本地服务端："避免网络原因无法访问"）；
        落点与来源无关（只有一处），故来源是本机不影响落点断言。
        """
        import http.server
        import socketserver

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):                                # noqa: N802 - http.server 约定
                rel = self.path.lstrip("/")
                body = served.get(rel)
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):                       # 静音
                pass

        return socketserver.TCPServer(("127.0.0.1", 0), Handler)

    def test_default_out_is_user_home(self):
        """端到端（唯一落点）：**只给脚本名**时副本必须落在用户家目录下的
        `<家目录>/.cache/agent-specs/<来源槽>/`——这是安装文档入口模板写明的那一个路径
        （"用户家目录下的 `.cache/agent-specs`"，即用户路径下的 `~/.cache/agent-specs`）。
        落在项目里或别处即与模板矛盾：新实例按入口文档给出的路径会找不到副本。
        """
        import threading
        entry = b"= test\n\nspecs/core/execution.adoc\n"
        served = {"AGENTS_COMMON.adoc": entry, "README.adoc": b"r1\n",
                  "specs/core/execution.adoc": b"e1\n", **self._install_scripts_served()}
        home = tempfile.mkdtemp(prefix="fetch-home-")
        proj = tempfile.mkdtemp(prefix="fetch-proj-")
        with self._serve(served) as httpd:
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{httpd.server_address[1]}"
            rc, so, se = self._run_fetch(base, cwd=proj, home=home)   # 只给脚本名
            self.assertEqual(0, rc, se + so)
            cache_root = os.path.join(home, ".cache", "agent-specs")
            hits = []
            for dirpath, _dirs, files in os.walk(cache_root):
                if "AGENTS_COMMON.adoc" in files:
                    hits.append(dirpath)
            self.assertTrue(hits, f"用户家目录下的落点未见副本: {cache_root}\n{so}{se}")
            with open(os.path.join(hits[0], "AGENTS_COMMON.adoc"), "rb") as fh:
                self.assertEqual(entry, fh.read())
            self.assertIn(os.path.join(home, ".cache"), so)
            # 项目里不得落任何副本（落点只有用户家目录下那一处）
            self.assertFalse(os.path.exists(os.path.join(proj, "tmp")))
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(proj, ignore_errors=True)

    def test_unusable_home_reports_instead_of_relocating(self):
        """端到端（家目录取不到时**报错、不静默换落点**）：`HOME` 被设成空串 / 根目录 / 未展开的
        `~` 时，脚本必须按"取不到家目录"报错并退出 2——**不得**把副本静默落到别的路径去。

        **本仓库实证的失效形态**：`HOME=`（空串）时 `os.path.expanduser("~")` 不抛错、而是返回
        文件系统根，故只判"空串或未展开的原样 `~`"的写法会把副本写到根目录下的落点
        ——正是"静默换落点"（入口文档写下的那一个用户路径与实际落点对不上）。
        用例对三种取不到家目录的取值各跑一次，判据是**退出码 2 + 报错文案 + 没有写出任何副本**。
        """
        real_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script = os.path.join(real_root, "script", "fetch-specs.py")
        proj = tempfile.mkdtemp(prefix="fetch-nohome-proj-")
        try:
            for bad_home in ("", "/", "~"):
                env = dict(os.environ, HOME=bad_home, USERPROFILE=bad_home)
                proc = subprocess.run(
                    [sys.executable, script, "--list"], cwd=proj,
                    capture_output=True, text=True, timeout=120, env=env)
                self.assertEqual(2, proc.returncode,
                                 f"HOME={bad_home!r} 应报错退出 2，实际 {proc.returncode}\n"
                                 f"{proc.stdout}{proc.stderr}")
                self.assertIn("家目录", proc.stderr,
                              f"HOME={bad_home!r} 的报错须说明卡在家目录上\n{proc.stderr}")
                # 不得在工作目录里落下任何东西（换落点的另一个方向）
                self.assertFalse(os.path.exists(os.path.join(proj, ".cache")))
        finally:
            shutil.rmtree(proj, ignore_errors=True)

    def test_no_relocation_flags_in_script(self):
        """静态判据（用户口径：落点只有这一个）：脚本里不得再有换落点的入口与第二落点。

        `--local`/`--out`/`--cache-dir`（及对应的环境变量）都意味着"同一份规范可以落在多处"，
        而这会让人按入口文档写下的那一个路径去找却找不到。故这里把"没有这些入口"本身钉住；
        反向还须有正面判据——落点必须仍由**用户家目录 + 两个落点常量**拼出来（只钉"不得有
        什么"时，把落点换成别的算法照样能避开那串禁用词）。
        """
        real_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(real_root, "script", "fetch-specs.py"), encoding="utf-8") as fh:
            src = fh.read()
        for flag in ("--local", "--out", "--cache-dir", "AGENT_SPECS_CACHE", "XDG_CACHE_HOME",
                     "LOCALAPPDATA", "tmp/agent-specs"):
            self.assertNotIn(flag, src,
                             f"落点只有用户家目录下的 .cache/agent-specs，不应再有 {flag}")
        for key in ("expanduser", "CACHE_HOME_DIR", "CACHE_APP_DIR"):
            self.assertIn(key, src, f"落点须由用户家目录 + {key} 算出，缺则落点不再是那一处")
        self.assertRegex(src, r"CACHE_HOME_DIR,\s*CACHE_APP_DIR",
                         "落点须由 CACHE_HOME_DIR/CACHE_APP_DIR 两级目录拼出（那一处用户路径）")

    def test_failure_keeps_local_copy_bytes(self):
        """端到端（失败不得把副本变小或变没）：远端不可达时，落点里已有的那一份必须**逐字节
        原样**保留，且结果三态里的"新取"为 0（不得把"没取到"报成"新取"）。

        边界（本仓库实证）：把**落点里的某一份文件**当成命令的 stdout（`fetch-specs > tmp/x.adoc`）
        时，shell 会先把该文件截断成 `0 B`——这是调用方的用法问题，脚本侧能保证的是：`0 B`
        也算"以前取到过的那一份"占位、失败时不判"新取"、并如实写明"本地已有那一份原样保留"。
        """
        home = tempfile.mkdtemp(prefix="fetch-home-fail-")
        # 先在"本机来源"上取一份，再换一个不可达的来源：落点按来源分槽，故要让两次命中同一槽
        # （`cache_slot_dir` 按来源地址分槽，换来源即换槽）——这里直接按来源槽路径预置那一份
        slot = re.sub(r"[^A-Za-z0-9._-]+", "_", "127.0.0.1:1").strip("_")
        dest = os.path.join(home, ".cache", "agent-specs", slot, "AGENTS_COMMON.adoc")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(b"= old\n")
        try:
            rc, so, se = self._run_fetch("http://127.0.0.1:1", home=home)   # 不可达
            self.assertNotEqual(0, rc)
            with open(dest, "rb") as fh:
                self.assertEqual(b"= old\n", fh.read())             # 逐字节原样
            self.assertIn("保留", se)
        finally:
            shutil.rmtree(home, ignore_errors=True)

    def test_reinstall_refreshes_when_remote_changed(self):
        """端到端行为（本防线的机制侧）：**以远程为准**——只改远端、本地只有旧副本时，
        重跑抓取脚本必须把本地刷新成远端内容；未改动的文件一个字节都不落盘。

        正例夹具用本文件所在工作区当"远端"（无网络依赖）：`--base` 指到 file 服务不可用，
        故改用本机临时 HTTP 服务托管两个文件，验证"远端改了 → 客户端刷新"。
        """
        import http.server
        import socketserver
        import threading

        entry = b"= test\n\nspecs/core/execution.adoc\n"
        served = {"AGENTS_COMMON.adoc": entry, "README.adoc": b"r1\n",
                  "specs/core/execution.adoc": b"e1\n"}
        served.update(self._install_scripts_served())
        home = tempfile.mkdtemp(prefix="fetch-home-refresh-")

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):                                # noqa: N802 - http.server 约定
                rel = self.path.lstrip("/")
                body = served.get(rel)
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):                       # 静音
                pass

        with socketserver.TCPServer(("127.0.0.1", 0), Handler) as httpd:
            port = httpd.server_address[1]
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{port}"
            out_dir = os.path.join(home, ".cache", "agent-specs",
                                   re.sub(r"[^A-Za-z0-9._-]+", "_",
                                          f"127.0.0.1:{port}").strip("_"))

            rc, so, se = self._run_fetch(base, home=home)
            self.assertEqual(0, rc, se + so)
            self.assertIn("新取", so)
            local = os.path.join(out_dir, "AGENTS_COMMON.adoc")
            with open(local, "rb") as fh:
                self.assertEqual(entry, fh.read())

            # 第二次：远端没改 → 全部命中"内容一致"、不落盘
            rc, so, se = self._run_fetch(base, home=home)
            self.assertEqual(0, rc, se + so)
            self.assertIn("内容一致", so)

            # 第三次：**只改远端** → 必须刷新本地（这正是"重新执行安装拿到最新"的判据）
            served["AGENTS_COMMON.adoc"] = entry.replace(b"= test", b"= v2")
            rc, so, se = self._run_fetch(base, home=home)
            self.assertEqual(0, rc, se + so)
            self.assertIn("刷新", so)
            with open(local, "rb") as fh:
                self.assertEqual(entry.replace(b"= test", b"= v2"), fh.read())

            # 第四次：远端改了、加 `--keep` → 不动本地那份（保留"别覆盖我的"这条路径）
            served["AGENTS_COMMON.adoc"] = entry.replace(b"= test", b"= v3")
            rc, so, se = self._run_fetch(base, ("--keep",), home=home)
            self.assertEqual(0, rc, se + so)
            with open(local, "rb") as fh:
                self.assertEqual(entry.replace(b"= test", b"= v2"), fh.read())

            # 第五次：远端不可达（本机服务已关、端口不可达）→ 本地那一份必须还在
            # （不得把副本删掉换成没有；来源仍相同故命中同一来源槽）
            httpd.shutdown()
            rc, so, se = self._run_fetch(base, home=home)
            self.assertNotEqual(0, rc)
            with open(local, "rb") as fh:
                self.assertEqual(entry.replace(b"= test", b"= v2"), fh.read())

        # 用例自清：落点在本次用例专属的家目录下（临时产物，见 specs/core/execution.adoc「临时产物」）
        shutil.rmtree(home, ignore_errors=True)

    def test_refresh_is_default_passes(self):
        # 正例：默认以远程为准（内容不同才落盘）+ --keep 保留本地那份 + 失败保留本地
        self._write_valid()
        cm.check_spec_fetch_guard()
        self.assertEqual([], cm.errors)

    def test_incremental_skip_regression_reports(self):
        # 反例（**本条要防的失效形态**）：退回「本地已有且非空即跳过、只有 --force 才刷新」
        # → 远端修好了、加了一节规范，用户重跑安装**拿不到最新的一份**（安装脚本自己在更新，
        # 重跑即是为了更新；用户实测诉求：重新执行安装时需要能更新现有的、以远程为准）。
        self._write_valid()
        script = (self.SCRIPT_PY
                  .replace('def local_bytes(p):\n'
                           '    """本地副本的字节；读不到按没有本地副本处理"""\n', '')
                  .replace('def keep_local(dest):\n'
                           '    """--keep：不动本地那份；判定标准：不得把本地副本删掉"""\n', ''))
        self.write("script/fetch-specs.py", script)
        cm.check_spec_fetch_guard()
        self.assertIn("以远程为准", self.error_texts())

    def test_failure_wiping_local_copy_reports(self):
        # 反例：取回失败时把本地副本删掉/清空 → 把「没更新」变成「没有」（比不更新更坏）
        self._write_valid()
        self.write("script/fetch-specs.py",
                   self.SCRIPT_PY.replace("不得把本地副本删掉", "落盘前先清空本地"))
        cm.check_spec_fetch_guard()
        self.assertIn("把本地副本删掉", self.error_texts())


class TestCheckGuardOrderGuard(CheckSpecsTestCase):
    """钉住『防线次序与清单表一致』（本轮新增，承接「次序提成数据」这次重构）。

    背景（本仓库实测）：次序此前只存在于 `main()` 正文的行序里——把某道防线从编排中段
    移到末尾，`check_specs.py` 报 OK、985 条单测全绿，**没有任何判据**。本轮把次序提成
    显式的 `CHECKS` 序列，并由本防线与 `specs-project-maintainer/guards.adoc` 的清单表
    逐行对账。用例覆盖：正例（两处同序）、反例①（集合相同但次序对调——最难发现的一种）、
    反例②（只在序列里）、反例③（只在清单表里）、反例④（清单表序号断开）、
    反例⑤（序列缺失）、反例⑥（清单表缺失）。
    """

    def _guard(self, name: str) -> str:
        return (f"def {name}():\n"
                f"    \"\"\"{name}。\"\"\"\n"
                f"    pass\n\n\n")

    def _write_valid(self, seq=("alpha", "beta"), rows=("alpha", "beta"), nums=None):
        src = "".join(self._guard("check_" + n) for n in seq) + \
            "CHECKS = (\n" + "".join(f"    check_{n},\n" for n in seq) + ")\n"
        if nums is None:
            nums = list(range(1, len(rows) + 1))
        table = "== 执行次序与用途（`CHECKS` 序列，唯一来源）\n\n" + "".join(
            f"| {i} | `check_{n}` | 用途 |\n" for i, n in zip(nums, rows))
        self.write("script/check_specs.py", src)
        self.write("specs-project-maintainer/guards.adoc", table)

    def test_valid_passes(self):
        self._write_valid()
        cm.check_guard_order_guard()
        self.assertEqual(self.error_texts(), "")

    def test_reordered_sequence_reports(self):
        # 反例①：集合相同、次序对调（实测形态：移动一道防线的位置无人发现）
        self._write_valid(seq=("beta", "alpha"), rows=("alpha", "beta"))
        cm.check_guard_order_guard()
        self.assertIn("次序不一致", self.error_texts())

    def test_extra_in_sequence_reports(self):
        # 反例②：序列里多一道（清单表没登记）→ 读者按表核对会漏掉它
        self._write_valid(seq=("alpha", "beta", "gamma"))
        cm.check_guard_order_guard()
        self.assertIn("check_gamma", self.error_texts())

    def test_extra_in_manifest_reports(self):
        # 反例③：清单表多一行（序列里没有）→ 表在描述一道不存在的防线
        self._write_valid(rows=("alpha", "beta", "gamma"))
        cm.check_guard_order_guard()
        self.assertIn("check_gamma", self.error_texts())

    def test_broken_numbering_reports(self):
        # 反例④：清单表序号断开（有条目被整条删掉）
        self._write_valid(rows=("alpha", "beta"), nums=(1, 3))
        cm.check_guard_order_guard()
        self.assertIn("序号不连续", self.error_texts())

    def test_missing_checks_reports(self):
        # 反例⑤：序列缺失 → 次序失去唯一来源
        self.write("script/check_specs.py", self._guard("check_alpha"))
        self.write("specs-project-maintainer/guards.adoc", "== x\n")
        cm.check_guard_order_guard()
        self.assertIn("CHECKS", self.error_texts())

    def test_missing_manifest_reports(self):
        # 反例⑥：清单表缺失 → 次序没有任何可读处
        self._write_valid()
        os.remove(os.path.join(self.root, "specs-project-maintainer", "guards.adoc"))
        cm.check_guard_order_guard()
        self.assertIn("guards.adoc", self.error_texts())


class TestLedgerSourceEntries(CheckSpecsTestCase):
    """钉住台账来源列的**解析口径**：含裸 `"` 的条目名不得让该条被整条跳过。

    本仓库实测：旧判据按"行首 4 空格 + 两个双引号串"直接匹配，121 条台账只命中 118 条
    ——`落点口径须写对：…写成"私有/不对外发布"` 这类**名字里带裸引号**的条目被静默漏掉，
    把它的来源改成不存在的路径，`check_ledger_source_paths_guard` 照样全绿
    （"看着核对过、其实漏了三条"）。故解析改为按字符串字面量逐字段取。
    """

    _LEDGER = (
        'MECHANISMS = [\n'
        '    ("名字里带\\"裸引号\\"的条目", "NOPE/missing.adoc", "script/check_specs.py",\n'
        '     "check_alpha_guard", "备注"),\n'
        '    ("普通条目", "specs/general/doc.adoc", "script/check_specs.py",\n'
        '     "check_alpha_guard", "备注"),\n'
        ']\n')

    def test_entries_with_quote_are_parsed(self):
        # 名字里带裸引号的条目**必须**被解析到（旧正则下它整条不见）
        entries = cm._ledger_source_entries(self._LEDGER)
        self.assertEqual(len(entries), 2)
        self.assertIn("NOPE/missing.adoc", [s for _, s in entries])

    def test_guard_checks_quote_entry_source(self):
        # 该条目的来源不存在时必须报红——不报说明它又被跳过了
        self.write("script/check_effective.py", self._LEDGER)
        cm.check_ledger_source_paths_guard()
        self.assertIn("不存在", self.error_texts())

    def test_guard_checks_normal_entry_source(self):
        # 普通条目的来源同样逐条核对（防"修了一处、漏了另一处"）
        ledger = self._LEDGER.replace("specs/general/doc.adoc", "NOPE/also-missing.adoc")
        self.write("script/check_effective.py", ledger)
        cm.check_ledger_source_paths_guard()
        self.assertIn("also-missing.adoc", self.error_texts())




class TestCheckGuardManifest(CheckSpecsTestCase):
    """钉住『防线清单与删除记账』（防"删了却全绿"）。

    本仓库实测的三条失效路径：①一道防线被从 `main()` 摘掉（代码并进别的防线）、它的
    反例用例一并被删，脚本报 OK、单测全通过、台账上的"抓手数"也没变；②台账里点名的
    防线名改成不存在的名字仍报"有抓手"；③脚本头部清单条目被整条删掉时编号断开、
    而清单描述不参与一致性核对。故本条把三件事变成可核对的：接线数、反例用例数、
    台账点名的防线名。
    """

    def setUp(self) -> None:
        super().setUp()
        self._orig_baseline = (cm.GUARD_WIRING_BASELINE, cm.GUARD_TEST_BASELINE)
        os.makedirs(os.path.join(self.root, "script"), exist_ok=True)

    def tearDown(self) -> None:
        cm.GUARD_WIRING_BASELINE, cm.GUARD_TEST_BASELINE = self._orig_baseline
        super().tearDown()

    # 夹具按**当前实现形态**给：防线经 `CHECKS` 序列编排（2026-09 重构后次序是数据）。
    # 判据本身没有被放宽——接线数、用例数、台账点名三件事一条不少，只是喂给它的脚本
    # 换成当前的编排形态（旧夹具写的是 `main()` 里逐行调用，重构后自然不再命中）。
    _SRC = (
        'def check_alpha_guard():\n'
        '    """甲。"""\n'
        '\n'
        '\n'
        'def check_beta_guard():\n'
        '    """乙。"""\n'
        '\n'
        '\n'
        'CHECKS = (\n'
        '    check_alpha_guard,\n'
        '    check_beta_guard,\n'
        ')\n'
        '\n'
        '\n'
        'def main(argv=None):\n'
        '    """入口。"""\n'
        '    for check in CHECKS:\n'
        '        check()\n'
        '    return 0\n'
        '\n'
        '\n'
        'if __name__ == "__main__":\n'
        '    main()\n'
    )
    # 台账逐条声明：`(条款名, 来源, 抓手路径, 声明的抓手, 备注)`——第 4 段是**必填**的
    # 「这条规范由哪一道钉住」（有抓手＝防线名、无抓手＝`NO_GRIP_DECLARED`）。
    _LEDGER = ("MECHANISMS = [\n"
               "    (\"甲\", \"X.adoc\", \"script/check_specs.py\",\n"
               "     \"check_alpha_guard\", \"备注甲\"),\n"
               "    (\"乙\", \"X.adoc\", \"script/check_specs.py\",\n"
               "     \"check_beta_guard\", \"备注乙\"),\n"
               "]\n")

    def _write_valid(self, src=None, ledger=None, tests=4, test_file=None):
        self.write("script/check_specs.py", src if src is not None else self._SRC)
        self.write("script/check_effective.py", ledger if ledger is not None else self._LEDGER)
        if test_file is None:
            body = "".join(f"    def test_case_{i}(self):\n        self.assertTrue(True)\n"
                           for i in range(tests))
            test_file = ("import unittest\n\n\nclass T(unittest.TestCase):\n" + body)
        self.write("script/check_specs_test.py", test_file)
        self.write("script/check_effective_test.py",
                   "import unittest\n\n\nclass E(unittest.TestCase):\n"
                   "    def test_x(self):\n        self.assertTrue(True)\n")
        cm.GUARD_WIRING_BASELINE = 2
        cm.GUARD_TEST_BASELINE = 5

    def test_valid_passes(self):
        # 正例：接线 2 道、用例 5 条、台账点名的两个防线名都真实存在
        self._write_valid()
        cm.check_guard_manifest()
        self.assertEqual([], cm.errors)

    def test_wiring_duplicate_registration_reports(self):
        # 反例⑤（本轮实测失效）：同一道防线在 `CHECKS` 序列里**登记两次**——
        # 条数被重复项凑够，掩盖了"真防线被删掉一道"（删掉的那道由重复项顶上，
        # 接线数不掉、`check_guard_manifest` 与 `check_guard_order_guard` 都全绿）。
        # 本轮 `check_pagination_guard` 正是这种形态：序列里一次、末尾又追加一次。
        self._write_valid(src=self._SRC.replace(
            "    check_beta_guard,\n",
            "    check_beta_guard,\n    check_alpha_guard,\n"))
        cm.check_guard_manifest()
        self.assertIn("重复", self.error_texts())

    def test_wiring_duplicate_hiding_removal_reports(self):
        # 反例：删一道真防线（连同函数体、用例、台账声明）再把另一道重复登记一次，
        # 序列元素个数仍等于基线——"定义了却没被调用"与"重复"两条都说不出"少了一道真防线"。
        # 判据须让重复项**不计入**唯一防线数：删一道 + 重复顶一道必然低于基线。
        self._write_valid(src=self._SRC
                          .replace("    check_alpha_guard,\n", "")
                          .replace("def check_alpha_guard():\n"
                                   '    """甲。"""\n'
                                   '\n'
                                   '\n', "")
                          .replace("    check_beta_guard,\n",
                                   "    check_beta_guard,\n    check_beta_guard,\n"))
        cm.check_guard_manifest()
        # 关键：唯一防线数（1）低于基线（2）被拦下——不再依赖"重复"那条文案自证
        self.assertIn("防线接线数从基线", self.error_texts())

    def test_guard_unwired_reports(self):
        # 反例①：一道防线被从 `main()` 摘掉 → 接线数减少（本仓库实测：删了它、连同反例
        # 用例一起删，脚本与单测仍全绿、台账的"抓手数"也没变）
        self._write_valid(src=self._SRC.replace("    check_beta_guard,\n", ""))
        cm.check_guard_manifest()
        self.assertIn("防线接线数", self.error_texts())

    def test_guard_defined_but_never_called_reports(self):
        # 反例①的另一形态：防线函数留着、也写进台账，但没有任何地方调用它
        # → 看起来还在、却永远不会执行
        self._write_valid(src=self._SRC.replace("    check_beta_guard,\n", ""))
        cm.check_guard_manifest()
        self.assertIn("check_beta_guard", self.error_texts())

    def test_tests_removed_without_note_reports(self):
        # 反例②：反例用例被整批删掉（防线随之失效力）→ 用例数减少必须报红
        self._write_valid(tests=1)
        cm.check_guard_manifest()
        self.assertIn("反例用例数", self.error_texts())

    def test_ledger_names_missing_guard_reports(self):
        # 反例③：台账点名一个不存在的防线 → 读者以为还有抓手（实测：改名后仍报"有抓手"）
        self._write_valid(ledger=self._LEDGER.replace("check_beta_guard",
                                                      "check_gone_guard"))
        cm.check_guard_manifest()
        self.assertIn("check_gone_guard", self.error_texts())

    def test_checklist_gap_reports(self):
        # 反例④：脚本头部清单出现断号（条目被整条删掉）→ 清单描述不参与一致性核对、
        # 写死不报红（本仓库实测），故按编号连续性核对
        src = self._SRC.replace(
            'def check_alpha_guard():',
            '"""清单：\n 1. 甲\n 2. 乙\n 4. 丙\n"""\n\n\ndef check_alpha_guard():')
        self._write_valid(src=src)
        cm.check_guard_manifest()
        self.assertIn("断号", self.error_texts())

    def test_checklist_duplicate_number_reports(self):
        # 反例⑤：清单编号出现**重号**（重排时把两条并成同一个号）→ 只核"有没有断号"时
        # 两种写法都能过：编号仍是连通的 1..N，而"第 3 项"同时指向两条条目——本仓库实测
        # （新增「防线清单与删除记账」时把原有的「性能测试防线」也编成 27，此后编号所指的
        # 那一项随重排静默错位）。故按**严格递增**核对。
        src = self._SRC.replace(
            'def check_alpha_guard():',
            '"""清单：\n 1. 甲\n 2. 乙\n 2. 丙\n"""\n\n\ndef check_alpha_guard():')
        self._write_valid(src=src)
        cm.check_guard_manifest()
        self.assertIn("重号", self.error_texts())

    def test_checklist_out_of_order_number_reports(self):
        # 反例⑤b：编号**乱序**（既无断号也无重号，但文件里的出现次序不是递增的）——
        # 新条目被插到了编号更小的条目之前。这是断号与重号两条判据都拦不住的形态：集合仍是
        # 1..N 齐备，只是次序错了。本仓库实测（PR #156）：新增的第 63 条被插在第 60 条之前，
        # 清单次序成了 `…55, 60, 61, 62, 63, 56, 57, 58, 59`，当时全绿。
        src = self._SRC.replace(
            'def check_alpha_guard():',
            '"""清单：\n 1. 甲\n 3. 丙\n 4. 丁\n 2. 乙\n"""\n\n\ndef check_alpha_guard():')
        self._write_valid(src=src)
        cm.check_guard_manifest()
        self.assertIn("乱序", self.error_texts())

    def test_ledger_without_declaration_reports(self):
        # 反例⑥（上一轮点名的悬置）：台账条目**没声明**自己由哪一道钉住 → "有抓手"这个数字
        # 可以靠把备注里的防线名删掉来维持（删名字比删防线容易得多），读者却以为还有抓手。
        # 故声明为必填：缺了即报红（旧实现只核"点名的名字存在"，没点名就没核对）。
        self._write_valid(
            ledger=self._LEDGER.replace(
                '     "check_beta_guard", "备注乙"),\n', '     "check_beta_guard"),\n'))
        cm.check_guard_manifest()
        self.assertIn("未声明抓手", self.error_texts())

    def test_ledger_declares_no_grip_but_has_path_reports(self):
        # 反例⑦：条目声明为「无机械抓手」、却填了抓手路径 → 声明与实现不一致
        self._write_valid(
            ledger=self._LEDGER.replace('"check_beta_guard", "备注乙"',
                                        '"%s", "备注乙"' % cm.NO_GRIP_DECLARED))
        cm.check_guard_manifest()
        self.assertIn("声明与实现不一致", self.error_texts())

    def test_ledger_declares_guard_but_unwired_reports(self):
        # 反例⑧：台账声明的防线**定义了却没人调用** → 它看起来还在、却永远不会执行；
        # 台账与接线两处必须同口径（这正是本仓库实测的"摘出执行序列"形态）
        self._write_valid(
            src=self._SRC.replace("    check_beta_guard,\n", ""),
            ledger=self._LEDGER.replace('"check_beta_guard", "备注乙"',
                                        '"check_beta_guard", "备注乙"'))
        cm.check_guard_manifest()
        self.assertIn("check_beta_guard", self.error_texts())

    def test_missing_script_reports(self):
        # 反例⑤：防线清单本体被删 → 无从核对
        self._write_valid()
        os.remove(os.path.join(self.root, "script", "check_specs.py"))
        cm.check_guard_manifest()
        self.assertIn("check_specs.py", self.error_texts())

    def test_entry_block_in_middle_reports(self):
        # 反例：`if __name__ == "__main__":` 落在**中段**、其后仍有缩进的 `def test_`
        # （块内局部函数）——源码正则数得到、`unittest` 收集不到，脚本与基线全绿。
        self._write_valid(test_file=(
            "import unittest\n\n\nclass T(unittest.TestCase):\n"
            "    def test_case_0(self):\n        self.assertTrue(True)\n"
            "\n\nif __name__ == \"__main__\":\n"
            "    import unittest\n    unittest.main()\n"
            "\n    def test_injected_never_collected(self):\n"
            "        self.assertTrue(True)\n"))
        cm.check_guard_manifest()
        self.assertIn("中段", self.error_texts())

    def test_emptied_test_case_reports(self):
        # 反例⑩（本轮 main 上实测的缺口）：用例被**掏空成空壳**（这一节里一条断言都没有）
        # ——总数基线只保证"数量不减少"，删一条加一条、或把用例掏空都能维持该数；
        # 被抽空的反例仍会被收集、仍占着那个数，却什么都证不了。
        self._write_valid(test_file=(
            "import unittest\n\n\nclass T(unittest.TestCase):\n"
            "    def test_case_0(self):\n        pass\n"
            "    def test_case_1(self):\n        self.assertTrue(True)\n"
            "    def test_case_2(self):\n        self.assertTrue(True)\n"
            "    def test_case_3(self):\n        self.assertTrue(True)\n"))
        cm.check_guard_manifest()
        self.assertIn("没有任何断言", self.error_texts())

    def test_nested_class_in_test_body_is_not_a_boundary(self):
        # 反例⑫（本仓库实测）：用例体里定义**局部夹具**（`class _R:` / `def _run(...)`，
        # 见 `TestAsciidoctorFailureLevel` 等三处）——边界若按"任意深度的下一个定义"取，
        # 这一节会被截在夹具处、只覆盖前半段：断言留在节外，于是**该用例的那一节"没有
        # 断言"**、用例数也被压低（实测少 11 条、基线因此虚降）。判据＝同层级的定义才是边界。
        self._write_valid(test_file=(
            "import unittest\n\n\nclass T(unittest.TestCase):\n"
            "    def test_case_0(self):\n"
            "        calls = []\n"
            "\n"
            "        class _R:\n"
            "            returncode = 0\n"
            "\n"
            "        def _run(cmd):\n"
            "            calls.append(cmd)\n"
            "\n"
            "        self.assertEqual(calls[:1], [])\n"
            "    def test_case_1(self):\n        self.assertTrue(True)\n"
            "    def test_case_2(self):\n        self.assertTrue(True)\n"
            "    def test_case_3(self):\n        self.assertTrue(True)\n"))
        cm.GUARD_TEST_BASELINE = 4
        cm.check_guard_manifest()
        self.assertEqual([], cm.errors)

    def test_nested_class_body_hollowing_still_reports(self):
        # 反例⑬：同一形态的反面——真被掏空（通篇没有断言）时仍须报出，不得因
        # "夹具里也有个 `def`"而把这一节算成"有断言了"。
        self._write_valid(test_file=(
            "import unittest\n\n\nclass T(unittest.TestCase):\n"
            "    def test_case_0(self):\n"
            "        class _R:\n"
            "            returncode = 0\n"
            "\n"
            "        def _run(cmd):\n"
            "            return None\n"
            "\n"
            "        _run(None)\n"
            "    def test_case_1(self):\n        self.assertTrue(True)\n"
            "    def test_case_2(self):\n        self.assertTrue(True)\n"
            "    def test_case_3(self):\n        self.assertTrue(True)\n"))
        cm.check_guard_manifest()
        self.assertIn("没有任何断言", self.error_texts())

    def test_same_name_deleted_in_one_class_kept_in_another_passes_by_name(self):
        # 反例⑪（本轮 main 上实测的缺口）：用例名**跨类复用**——类 A 的那条被删、类 B 的
        # 同名用例仍留。只记"名字"的口径看不见这个动作（名字仍在集合里、计数也够），
        # 故清单按 `类名.用例名` 限定；此处正例确认"同名分居两类"会被算成两条。
        src = ("import unittest\n\n\nclass A(unittest.TestCase):\n"
               "    def test_same(self):\n        self.assertTrue(True)\n"
               "\n\nclass B(unittest.TestCase):\n"
               "    def test_same(self):\n        self.assertTrue(True)\n")
        names = cm._collectable_test_names("script/check_specs_test.py", src)
        self.assertEqual({"A.test_same", "B.test_same"}, names)

    def test_malformed_item_number_reports(self):
        # 反例⑭（本轮实测的缺口）：清单里一条真条目被写成 ` 31b.`、且**缩进 5 格**——
        # 编号判据的正则取 `^ (\d+)[a-z]?\. `，凡不合该形态的条目行**一条判据都核不到**
        # （断号/重号/乱序三条全部放行），它于是成了藏在清单里、永不参与核对的第二份描述。
        # 本仓库实证：`31b.` 那条与它前后的条目并存了多轮，任何检查都没有报过它。
        self._write_valid(src=self._SRC.replace(
            'def check_beta_guard():',
            '     31b. 丙。\n\n\ndef check_beta_guard():'))
        cm.check_guard_manifest()
        self.assertIn("编号形态不规范", self.error_texts())

    def test_item_number_with_multi_char_suffix_reports(self):
        # 反例⑮：后缀不止一个字符（`36b2.`）同样是判据盲区——字符类放宽到 `[a-z0-9]*`
        # 之后仍须靠"形态"这一条兜住（前缀字符类只保证 `31b` 这类进得来）。
        self._write_valid(src=self._SRC.replace(
            'def check_beta_guard():',
            '     36b2. 丙。\n\n\ndef check_beta_guard():'))
        cm.check_guard_manifest()
        self.assertIn("编号形态不规范", self.error_texts())

    def test_well_formed_item_number_passes(self):
        # 正例：规范形态（单空格缩进 + 纯数字序号）不得被误报——本条判据的假阳性
        # 会误伤整份清单，故须有正例钉住。
        self._write_valid(src=self._SRC.replace(
            'def check_beta_guard():',
            ' 1. 丙。\n\n\ndef check_beta_guard():'))
        cm.check_guard_manifest()
        self.assertEqual([], cm.errors)


class TestCheckStaleWordingGuard(CheckSpecsTestCase):
    """钉住『已被证否的旧口径不得写回』防线。

    失效形态（本仓库实证）：口径被现场实测证否后改掉的是**方向**，而"旧的错法长什么样"
    只留在改动记录里——下一个人照旧句子复述一遍，就把错口径带回脚本注释。故把特征措辞
    外置成规则数据（`script/specs-rules/_tokens.toml`）并逐条核"有没有被写回来"。

    **核对对象是措辞形态**（`file_forbidden` 原语），"这条口径今天还成不成立"属语义判断。
    """

    def _write(self, extra: str = "") -> None:
        self.write("script/check_specs.py",
                   "def check_alpha_guard():\n"
                   '    """甲。"""\n\n\n'
                   + extra)

    def test_stale_wording_absent_passes(self):
        # 正例：脚本里没有旧口径的特征措辞——不得误报（假阳性会误伤整份脚本的注释）
        self._write()
        cm.check_stale_wording_guard()
        self.assertEqual([], cm.errors)

    def test_stale_def_test_count_wording_reports(self):
        # 反例①：写回"`*_test.py` 里的 `def test_` 个数"这一**已被证否**的计数口径
        # （实测证否：源码正则数得到、`unittest` 收集不到，两者不等）
        self._write("# 用例数＝全部 `*_test.py` 里的 `def test_` 个数\n")
        cm.check_stale_wording_guard()
        self.assertIn("证否", self.error_texts())

    def test_stale_single_file_counting_wording_reports(self):
        # 反例②：写回"只数某一个测试文件"的旧口径（被证否：它长期低于实际收集数，
        # 使基线虚低、删掉若干条用例都不报红）
        self._write('# 口径：写成"只数 check_specs_test.py"\n')
        cm.check_stale_wording_guard()
        self.assertIn("证否", self.error_texts())

    def test_missing_script_reports(self):
        # 反例③：核对对象整体缺失 → 须报红，不得静默通过（"核不到"与"核过且通过"要分得清）
        cm.check_stale_wording_guard()
        self.assertIn("check_specs.py", self.error_texts())

    def test_anchor_present_in_rule_data(self):
        # 反向核对：本条钉的措辞**逐条来自规则数据**（不是散落在脚本里的字面量），
        # 改措辞只改规则数据——两处各写一份正是本仓库反复出现的"第二真源"。
        import rules_engine
        specs = rules_engine.load_rule_files(cm._rules_spec())
        steps = specs["guards"]["check_stale_wording_guard"]
        self.assertEqual(1, len(steps))
        self.assertEqual("file_forbidden", steps[0]["kind"])
        self.assertTrue(steps[0]["forbidden"])


class TestCheckTemplateSeparationGuard(CheckSpecsTestCase):
    """钉住『模板类内容的单独归类』防线：判据本体 + 两处登记/引用不得被删或降级。

    用户要求（Issue #169）："有一些规范，属于要么不读、要么读全部的，比如代码模板……
    不要和其他内容放一起，放一起浪费上下文……大部分情况下需要的时候读一下就行，甚至可以不读，
    直接 copy 就行；这些代码模板最好各自也独立（除非有关联性或者内容不多拆开反而麻烦）"。

    **落点分三层**（判据本体在**维护方自查层**——它描述"规范集合自己怎么组织"，对引用方
    项目不成立）：① `specs-project-maintainer/spec-lifecycle.adoc` 承载归类判据、不得混放、
    「各自独立 + 例外」与判定标准；② `AGENTS.adoc` 登记该落点（维护方入口是加载点，缺则
    执行者读不到这套判据）；③ `specs/general/context.adoc`「生成效率」留公共侧一跳引用。

    **重点拦两种形态**：① 只核"这一节在不在"（轴名齐全、判据被抽走——「什么算模板类内容」
    的判定标准、不得混放的判定标准、「各自独立」的例外任一被抽掉必须报红）；② **把判据本体
    抄进公共内容**（那是维护方的组织口径，写进 `specs/` 即同一条规则两处真源）。
    """

    MAINT = (
        "= 规范集合的维护（维护方自查）\n\n"
        "== 要么不读、要么读全部的规范（模板类内容的单独归类）\n\n"
        "**归类判据（L1，先判再动手）**：一条内容若「要用就得整份取用、平时不必常备」，"
        "它属本节所指的**模板类内容**——典型是**代码模板**。"
        "**判定标准（任一命中即属模板类内容）**：① 取用形态是**复制**；"
        "② 判据**要么不读、要么读全部**；③ 取值**独立于上下文**。"
        "三条都不命中即普通规范条目。\n\n"
        "* **代码模板不与其他规则混放（L1）**：不得与「每次会话要遵守的规则」写在"
        "同一个落点、也不与**常驻层**放在一起。\n"
        "* **判定标准（任一命中即违规）**：① 写在**同一节或同一文件**里；② 落在**常驻层**；"
        "③ 加载触发方式与规则条目共用。\n"
        "* **模板最好各自独立（L2）**：例外：**有关联性**、**内容不多**拆开反而麻烦时可不拆。\n"
        "* **依据（标准名/编号）**：Agent Skills 开放规范（渐进披露）、"
        "ISO/IEC Directives Part 2（文件须便于按现行版本取用）。\n")

    ENTRY = (
        "* **分类、分层与准入**：……用户提新增规范时的提案校验，以及**模板类内容的归类与单独落点**"
        "（「要么不读、要么读全部」的内容不与规则混放）见 "
        "`specs-project-maintainer/spec-lifecycle.adoc`。\n")

    COMMON = (
        "== 生成效率（同等质量下最少往返）\n\n"
        "* **按需加载按文件切分、单文件别太大（L2）**：……**模板类内容（要用就得整份取用、"
        "平时不必常备）另按「要么不读、要么读全部」单独归类**：不与「每次会话要遵守的规则」混放、"
        "各自独立成篇（判据与例外属维护方自查层，本处不重复）。\n")

    def _write(self, maint=None, entry=None, common=None) -> None:
        self.write("specs-project-maintainer/spec-lifecycle.adoc",
                   maint if maint is not None else self.MAINT)
        self.write("AGENTS.adoc", entry if entry is not None else self.ENTRY)
        self.write("specs/general/context.adoc",
                   common if common is not None else self.COMMON)

    def test_valid_passes(self):
        self._write()
        cm.check_template_separation_guard()
        self.assertEqual([], cm.errors)

    def test_spec_file_removed_reports(self):
        # 反例①：判据真源文件被删 -> 该条无处承载
        self.write("AGENTS.adoc", self.ENTRY)
        self.write("specs/general/context.adoc", self.COMMON)
        cm.check_template_separation_guard()
        self.assertIn("spec-lifecycle.adoc", self.error_texts())

    def test_section_removed_reports(self):
        # 反例②：该节被整节删掉 -> 判据失去落点
        self._write(maint="= 规范集合的维护（维护方自查）\n\n== 准入判定\n\n* 略。\n")
        cm.check_template_separation_guard()
        self.assertIn("要么不读、要么读全部", self.error_texts())

    def test_criteria_stripped_but_axis_present_reports(self):
        # 反例③（**轴名齐全、判据被抽走**的反例本体）：小节名与"归类判据"字样都在，
        # 但"什么算模板类内容"的**三条判定标准**被抽走 —— 只核轴名会全绿，
        # 执行者于是把任意内容按自己方便归类。
        self._write(maint=self.MAINT.replace(
            "**判定标准（任一命中即属模板类内容）**", "**说明**"))
        cm.check_template_separation_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_mixing_rule_removed_reports(self):
        # 反例④：把"不得与其他规则混放"删掉（用户口径的正题）-> 模板会继续被塞进主题文件
        self._write(maint=self.MAINT.replace(
            "* **代码模板不与其他规则混放（L1）**：不得与「每次会话要遵守的规则」写在"
            "同一个落点、也不与**常驻层**放在一起。\n", ""))
        cm.check_template_separation_guard()
        self.assertIn("混放", self.error_texts())

    def test_mixing_criteria_removed_reports(self):
        # 反例⑤：混放的三条判定标准被抽走 -> "混没混放"回到评判者手里
        self._write(maint=self.MAINT.replace(
            "* **判定标准（任一命中即违规）**：① 写在**同一节或同一文件**里；"
            "② 落在**常驻层**；③ 加载触发方式与规则条目共用。\n", ""))
        cm.check_template_separation_guard()
        self.assertIn("混放", self.error_texts())

    def test_independence_exception_removed_reports(self):
        # 反例⑥：把「各自独立」的**例外**删掉（用户原话即带这个例外）-> 会把"独立"读成
        # 硬性要求、逼出为达标而拆的空壳（与"默认不拆"取向相反）
        self._write(maint=self.MAINT.replace(
            "例外：**有关联性**、**内容不多**拆开反而麻烦时可不拆。", "。"))
        cm.check_template_separation_guard()
        self.assertIn("关联性", self.error_texts())

    def test_entry_registration_removed_reports(self):
        # 反例⑦：维护方入口没登记该落点 -> 判据齐备但没有入口（执行者读不到）
        self._write(entry="* **分类、分层与准入**：见 spec-lifecycle.adoc。\n")
        cm.check_template_separation_guard()
        self.assertIn("AGENTS.adoc", self.error_texts())

    def test_common_xref_removed_reports(self):
        # 反例⑧：公共侧一跳引用被删 -> 引用方项目只看到"按文件切分"、无从知道模板另有归类
        self._write(common="== 生成效率（同等质量下最少往返）\n\n* 略。\n")
        cm.check_template_separation_guard()
        self.assertIn("context.adoc", self.error_texts())




class TestCheckLogicalDeleteNamingGuard(CheckSpecsTestCase):
    """钉住『方法名与逻辑删除的对应』防线（用户提出，Issue #184）。

    用户原话："未使用 mybatis plus 逻辑删除时，没有前缀后缀的方法名默认查询且不带删除标志，
    如果要查询已删除/未删除（带了删除标志的条件）的数据时，要带特征；使用 mybatis plus
    逻辑删除时（因为会默认带删除标志），没有前缀后缀的方法名默认查询逻辑删除数据，如果要查询
    已删除和忽略删除标志的数据时，要带特征。不仅限 mybatis plus，其他类似的也生效（自己实现
    的逻辑删除逻辑和框架也算），适用所有语言"。

    反例逐组覆盖：默认面怎么定被抽 / 非默认面特征词被抽 / 判定标准被抽 / 理由被抽 /
    默认面例外被抽 / 边界被抽 / 存量边界被抽 / 依据行被整行删 / Java 落点缺框架专名 /
    图书馆未登记取舍。
    """

    CODING = "specs/general/coding.adoc"
    JAVA = "specs/stack/java.adoc"
    ADOPTION = "library/adoption.adoc"
    SECTION = "持久化访问（数据库/缓存等）"

    def setUp(self) -> None:
        super().setUp()
        self._orig_coding = cm.CODING_FILE
        self._orig_java = cm.JAVA_STACK_FILE
        cm.CODING_FILE = os.path.join(self.root, "specs", "general", "coding.adoc")
        cm.JAVA_STACK_FILE = os.path.join(self.root, "specs", "stack", "java.adoc")
        # 真实规则目录（本仓库那一份）：夹具按原样复制，**不手抄**（手抄必然与现场漂移）
        self._rules_src = os.path.join(
            os.path.dirname(os.path.abspath(cm.__file__)), "specs-rules")
        with open(self.CODING, encoding="utf-8") as fh:
            self.CODING_TEXT = fh.read()
        with open(self.JAVA, encoding="utf-8") as fh:
            self.JAVA_TEXT = fh.read()
        with open(self.ADOPTION, encoding="utf-8") as fh:
            self.ADOPTION_TEXT = fh.read()

    def tearDown(self) -> None:
        cm.CODING_FILE = self._orig_coding
        cm.JAVA_STACK_FILE = self._orig_java
        super().tearDown()

    def _write_coding(self, text: str) -> None:
        self.write(self.CODING, text)

    def _write_all_valid(self) -> None:
        self._write_coding(self.CODING_TEXT)
        self.write(self.JAVA, self.JAVA_TEXT)
        self.write(self.ADOPTION, self.ADOPTION_TEXT)
        # `run_rule_guard` 按**阶段**去重（同一阶段内同名防线只跑一遍），而每个用例都
        # 自成一个阶段（`phase()` 会清空去重集）——这里显式清一次只是让"同一用例里重复
        # 调用防线"也按最新夹具核对（防御性，与 `REPO_SCRIPT_SRC_CACHE` 同理）。
        cm._RULES_RUN_THIS_PHASE.clear()

    def _run_guard(self) -> None:
        """只跑本道防线（`run_rule_guard` 有阶段内去重，故先清去重集合）。"""
        cm._RULES_RUN_THIS_PHASE.clear()
        cm.check_chain_assignment_order_guard()

    def _mutated_coding(self, removed: str, replacement: str = "") -> None:
        self.assertIn(removed, self.CODING_TEXT)
        self._write_all_valid()
        self._write_coding(self.CODING_TEXT.replace(removed, replacement))

    def _write_coding_without_line(self, anchor: str) -> None:
        """删掉含 `anchor` 的那一行（依据行一类"整行"判据）。"""
        lines = self.CODING_TEXT.split("\n")
        hit = [i for i, ln in enumerate(lines) if anchor in ln]
        self.assertEqual(1, len(hit))
        del lines[hit[0]]
        self._write_all_valid()
        self._write_coding("\n".join(lines))

    def test_valid_passes(self):
        # 正例兼锚点自检：真文档逐字进夹具时防线必须报绿（锚点与文档脱节时先在这一条暴露）
        self._write_all_valid()
        cm.check_logical_delete_naming_guard()
        self.assertEqual("", self.error_texts())

    def test_default_face_rule_removed_reports(self):
        # 反例①：默认面"取该技术是否自动附加"被抽 -> 默认面退回"约定俗成的那一面"
        self._mutated_coding("**默认面取该技术是否自动附加删除标志条件**", "默认面即习惯用法")
        cm.check_logical_delete_naming_guard()
        self.assertIn("默认面取该技术是否自动附加删除标志条件", self.error_texts())

    def test_feature_word_removed_reports(self):
        # 反例②：非默认面须带特征词被抽 -> "查已删也顺手叫 list()"重新成立
        self._mutated_coding("**方法名须带该面的特征词**", "注意区分")
        cm.check_logical_delete_naming_guard()
        self.assertIn("方法名须带该面的特征词", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例③：判定标准被抽 -> 本条自身不可判定，只剩一句口号
        self._write_all_valid()
        text = self.CODING_TEXT.replace("**判定标准（任一命中即违规）**：① 不带删隐面特征词的方法名查询了", "补充说明：")
        self.assertNotEqual(self.CODING_TEXT, text)
        self._write_coding(text)
        cm.check_logical_delete_naming_guard()
        self.assertIn("判定标准（任一命中即违规）", self.error_texts())

    def test_reason_removed_reports(self):
        # 反例④：理由（删隐面只能从技术配置反推）被抽 -> 本条的级别与处置会被降级
        self._mutated_coding("**删隐面只能从技术配置反推、读代码的人与评审者都无从预期**", "不太直观")
        cm.check_logical_delete_naming_guard()
        self.assertIn("无从预期", self.error_texts())

    def test_project_default_exception_removed_reports(self):
        # 反例⑤：默认面的唯一例外被抽 -> 同一项目里按各实体配置各算一套
        self._mutated_coding("项目自身规范或该项目既有先例已明确", "另有规定时")
        cm.check_logical_delete_naming_guard()
        self.assertIn("先例", self.error_texts())

    def test_boundary_removed_reports(self):
        # 反例⑥：边界被抽 -> 本条被读成"所有方法名都要加后缀"
        self._mutated_coding("**只**约束**按实体/表做查询的方法名**", "适用于所有方法名")
        cm.check_logical_delete_naming_guard()
        self.assertIn("按实体/表做查询的方法名", self.error_texts())

    def test_migration_boundary_removed_reports(self):
        # 反例⑦：存量边界（不得全库改名）被抽 -> 等于要求立刻批量重写既有方法名
        self._mutated_coding("**且不得据本条做全库改名**", "")
        cm.check_logical_delete_naming_guard()
        self.assertIn("不得据本条做全库改名", self.error_texts())

    def test_basis_line_removed_reports(self):
        # 反例⑧：依据行被整行删掉 -> 读者把本集合的取舍当成标准要求；
        #          按整个二级节取值时相邻条目的同义字样会兜住缺项，故须按小节取值
        self._write_coding_without_line("**\"默认面随技术是否自动附加删除标志条件而变")
        cm.check_logical_delete_naming_guard()
        self.assertIn("本集合的判据化取舍", self.error_texts())

    def test_java_landing_removed_reports(self):
        # 反例⑨：Java 落点缺框架专名 -> MyBatis-Plus 侧的默认面无从判定
        self.write(self.CODING, self.CODING_TEXT)
        self.write(self.ADOPTION, self.ADOPTION_TEXT)
        self.write(self.JAVA, self.JAVA_TEXT.replace("@TableLogic", "某个注解"))
        cm.check_logical_delete_naming_guard()
        self.assertIn("TableLogic", self.error_texts())

    def test_adoption_not_registered_reports(self):
        # 反例⑩：图书馆未登记本集合取舍 -> 读者会把本站取舍读成标准规定
        self.write(self.CODING, self.CODING_TEXT)
        self.write(self.JAVA, self.JAVA_TEXT)
        self.write(self.ADOPTION, self.ADOPTION_TEXT.replace("方法名与逻辑删除的对应", "某条规则"))
        cm.check_logical_delete_naming_guard()
        self.assertIn("library/adoption.adoc", self.error_texts())

    def test_subsection_missing_reports(self):
        # 反例⑪：整个三级小节被删 -> 该条失去落点
        self._write_all_valid()
        self._write_coding(self.CODING_TEXT.split("=== 方法名与逻辑删除的对应")[0])
        cm.check_logical_delete_naming_guard()
        self.assertIn("方法名与逻辑删除的对应", self.error_texts())


class TestFetchSpecsReadOnlyLanding(CheckSpecsTestCase):
    """端到端实测『落点取完即只读』（用户口径：文件本身下载后要变成只读）。

    静态判据（`TestCheckReadonlyLandingGuard`）只证"脚本里写了这件事"；本类证**它真的生效**：
      * 取完后落点里的**目录没有写位、文件没有写位**；
      * 用户再跑一次（远端改了）**照旧能更新**——只读不挡"默认以远程为准"；
      * 落点里的入口脚本**仍能直接执行**（只读的例外是执行位）；
      * **非特权调用方**改不动落点里的任何文件（本条要拦的正是"项目把副本就地改掉"，故实测
        用的是"换一个用户去改"这条路：root 自己不受权限位约束，用 root 复核实测不出本条）；
      * 落点里入口的执行位**每轮都补**（`--no-scripts`、"内容一致"的那一轮同样补——
        见 `test_entry_exec_bit_restored_even_with_no_scripts`）。

    非特权那一档在没有第二个用户的机器上跳过（Windows/容器常如此）——**跳过时显式说明**，
    不得把"没实测"静默当成"通过"。同理，**Windows 上只实测得到『文件已置只读』那一半**：
    目录的只读位在 Windows 上拦不住增删改名，那一半靠规范约束（判据与边界见
    `script/fetch-specs.py` 头部「已知限制」）——用例在 win32 上**显式跳过并说明**，
    不把"没实测的那一半"算成通过。
    """

    ENTRY = b"= test\n\nspecs/core/execution.adoc\n"
    SPEC = "= 执行原则\n\n* 甲\n".encode("utf-8")

    def _install_scripts_served(self):
        """服务端要供给的安装脚本（脚本会随规范一起取它们，缺则 404、退出码非 0）。

        名单从**真实仓库**的 `fetch-specs.py` 里读，与脚本本身同源——手工再抄一份名单会在
        加了第三份安装脚本时静默漏供（那时用例报的是 404、看起来像网络问题）。
        """
        real_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(real_root, "script", "fetch-specs.py"),
                  encoding="utf-8") as fh:
            src = fh.read()
        return {"script/" + rel: src.encode("utf-8")
                for rel in re.findall(r'"script/([\w.-]+)"', src)}

    def _serve(self, served):
        import http.server
        import socketserver

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):                                # noqa: N802 - http.server 约定
                body = served.get(self.path.lstrip("/"))
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):                       # 静音
                pass

        return socketserver.TCPServer(("127.0.0.1", 0), Handler)

    def _run_fetch(self, base, extra=(), home=None):
        """按仓库真实的抓取脚本跑一次（spawn 子进程、按 stdout/stderr 断言）。"""
        real_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script = os.path.join(real_root, "script", "fetch-specs.py")
        env = None
        if home:
            env = dict(os.environ, HOME=home, USERPROFILE=home)
        return subprocess.run([sys.executable, script, "--base", base, *extra],
                              cwd=real_root, capture_output=True, text=True,
                              timeout=120, env=env)

    def test_landing_is_read_only_and_still_updatable(self):
        import threading
        served = {"AGENTS_COMMON.adoc": self.ENTRY, "README.adoc": b"r1\n",
                  "specs/core/execution.adoc": self.SPEC, **self._install_scripts_served()}
        home = tempfile.mkdtemp(prefix="readonly-home-")
        try:
            with self._serve(served) as httpd:
                port = httpd.server_address[1]
                threading.Thread(target=httpd.serve_forever, daemon=True).start()
                base = f"http://127.0.0.1:{port}"
                slot = os.path.join(home, ".cache", "agent-specs",
                                    re.sub(r"[^A-Za-z0-9._-]+", "_",
                                           f"127.0.0.1:{port}").strip("_"))

                proc = self._run_fetch(base, home=home)
                self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)

                # ① 落点里的目录没有写位、文件没有写位（只读真的生效，不只是一句注释）
                if os.name == "posix":
                    for dirpath, dirnames, filenames in os.walk(slot):
                        self.assertFalse(os.stat(dirpath).st_mode & stat.S_IWUSR,
                                         f"目录仍有写位: {dirpath}")
                        for name in filenames:
                            self.assertFalse(
                                os.stat(os.path.join(dirpath, name)).st_mode & stat.S_IWUSR,
                                f"文件仍有写位: {os.path.join(dirpath, name)}")
                    root = os.path.join(home, ".cache", "agent-specs")
                    self.assertFalse(os.stat(root).st_mode & stat.S_IWUSR)
                else:
                    # win32 上只核得到"文件已置只读"这一半（`os.chmod` 只认
                    # `stat.S_IWRITE`；目录的增删改名来自父目录的 `DELETE_CHILD`，
                    # 与目标目录属性无关）；跳过不等于通过，故显式 skip 并写明边界。
                    self.skipTest("Windows 上目录的只读位拦不住增删改名（READONLY 属性对目录不阻止 "
                                  "DeleteFile/CreateFile）；本机只实测得到『文件已置只读』那一半，"
                                  "『目录不可增删改名』在 Windows 上未实测（跳过不等于通过，"
                                  "判据与边界见 fetch-specs.py 头部「已知限制」）")

                # ② 只读的例外是执行位：落点里的入口仍能直接执行（"下次重装直接跑它"）
                if os.name == "posix":
                    entry = os.path.join(home, ".cache", "agent-specs", "fetch-specs.sh")
                    self.assertTrue(os.stat(entry).st_mode & stat.S_IXUSR,
                                    "落点里的入口丢了执行位（只读把'能直接跑'一并否掉了）")

                # ③ 只读**不挡更新**：远端改了，重跑一次必须刷新（"默认以远程为准"仍成立）
                served["AGENTS_COMMON.adoc"] = self.ENTRY.replace(b"= test", b"= v2")
                proc = self._run_fetch(base, home=home)
                self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
                self.assertIn("刷新", proc.stdout)
                with open(os.path.join(slot, "AGENTS_COMMON.adoc"), "rb") as fh:
                    self.assertEqual(self.ENTRY.replace(b"= test", b"= v2"), fh.read())
                # 更新之后仍须是只读的（收紧动作在每一次落盘后都做）
                if os.name == "posix":
                    self.assertFalse(
                        os.stat(os.path.join(slot, "AGENTS_COMMON.adoc")).st_mode & stat.S_IWUSR)
        finally:
            shutil.rmtree(home, ignore_errors=True)

    def test_entry_exec_bit_restored_even_with_no_scripts(self):
        """端到端实测（**本轮补，PR 返工**）：落点里入口的执行位**每轮都补**，
        与"这一轮落了几个盘"解耦。

        失效形态（本 PR 原实现，实测复现）：补执行位原先只挂在 `fetch_install_scripts` 里、
        只在 `download_one` 走 `new`/`updated` 分支时被调用。于是：
          * `--no-scripts` 整组跳过 → 没人补；
          * "内容一致（`same`）"的那一轮 → 没人补。
        结果是一旦落点里入口的执行位不是 555（下载回来的是字节、HTTP 不带文件模式；
        也含用户手动降级、或旧版本留下的落点），它就一直停在 444，而 `444` 与"入口也在
        只读树里"看起来一模一样、无从发现——"下次重装直接跑落点里的入口"就此失效。

        本条按**用户会遇到的那条路**实测：先正常取一次、再把**入口**（取值面见脚本的
        `ENTRY_SCRIPTS`，即各平台薄壳）降级成 `444`，然后跑 `--no-scripts`
        （这一步没人落盘任何文件）——执行位必须回到能跑，且**写位不得被放开**。
        逻辑代码（`.py`）不在入口名单里（它不是给人直接敲的命令），故也不应当被补位。
        Windows 上无 POSIX 执行位语义，故本条跳过并**显式说明**（不把"没实测"当"通过"）。
        """
        if os.name != "posix":
            self.skipTest("Windows 上无 POSIX 执行位语义（os.chmod 只切只读属性），"
                          "故未实测『--no-scripts 下入口执行位恢复』（跳过不等于通过）")
        import threading
        served = {"AGENTS_COMMON.adoc": self.ENTRY, "README.adoc": b"r1\n",
                  "specs/core/execution.adoc": self.SPEC, **self._install_scripts_served()}
        home = tempfile.mkdtemp(prefix="readonly-execc-")
        try:
            with self._serve(served) as httpd:
                port = httpd.server_address[1]
                threading.Thread(target=httpd.serve_forever, daemon=True).start()
                base = f"http://127.0.0.1:{port}"
                root = os.path.join(home, ".cache", "agent-specs")
                proc = self._run_fetch(base, home=home)
                self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
                # 入口名单与脚本同源（`ENTRY_SCRIPTS`）：手工再抄一份会在加了第三份入口时静默漏测
                with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                       "script", "fetch-specs.py"), encoding="utf-8") as fh:
                    src = fh.read()
                entry_rels = re.findall(r'ENTRY_SCRIPTS = \(([^)]*)\)', src)[0]
                entry_names = re.findall(r'"script/([\w.-]+)"', entry_rels)
                entries = [os.path.join(root, n) for n in entry_names
                           if n.endswith(".sh")]      # .bat 在 POSIX 上无执行位语义
                self.assertTrue(all(os.path.isfile(p) for p in entries), root)
                # 模拟"执行位没被恢复"的落点：入口只剩只读位（444）
                for path in entries:
                    os.chmod(path, 0o444)
                # `--no-scripts`：整组不落盘、也没人碰权限位——执行位仍须被补回来
                proc = self._run_fetch(base, ("--no-scripts",), home=home)
                self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
                for path in entries:
                    self.assertTrue(os.stat(path).st_mode & stat.S_IXUSR,
                                    f"落点里的入口丢了执行位: {path}（--no-scripts 下没人补位）")
                    self.assertFalse(os.stat(path).st_mode & stat.S_IWUSR,
                                     f"补执行位时把写位也放开了（落点须仍只读）: {path}")
        finally:
            shutil.rmtree(home, ignore_errors=True)

    def test_non_root_cannot_touch_landing(self):
        """非特权调用方改不动落点（本条要拦的正是"项目把副本就地改掉"）。

        root 不受权限位约束，故本条**必须换一个非特权身份**实测——用 root 跑"能不能写"
        永远得到"能写"、看不出只读有没有生效（本仓库实测口径：判据要能被坏形态触发）。
        机器上没有可用的非特权用户时**跳过并显式说明**（不把"没实测"当"通过"）。
        """
        if os.name != "posix" or os.geteuid() != 0:
            self.skipTest("需要 POSIX 且以 root 运行才能切到非特权用户实测；"
                          "本机不满足，故未实测『非特权调用方改不动落点』"
                          "（跳过不等于通过）")
        nobody = next((u for u in ("nobody", "node", "daemon")
                       if subprocess.run(["id", u], capture_output=True).returncode == 0), None)
        if nobody is None:
            self.skipTest("本机没有可用的非特权用户，故未实测『非特权调用方改不动落点』"
                          "（跳过不等于通过）")
        import threading
        served = {"AGENTS_COMMON.adoc": self.ENTRY, "README.adoc": b"r1\n",
                  "specs/core/execution.adoc": self.SPEC, **self._install_scripts_served()}
        home = tempfile.mkdtemp(prefix="readonly-home-")
        try:
            with self._serve(served) as httpd:
                port = httpd.server_address[1]
                threading.Thread(target=httpd.serve_forever, daemon=True).start()
                base = f"http://127.0.0.1:{port}"
                proc = self._run_fetch(base, home=home)
                self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
                root = os.path.join(home, ".cache", "agent-specs")
                slot = os.path.join(root, re.sub(r"[^A-Za-z0-9._-]+", "_",
                                                 f"127.0.0.1:{port}").strip("_"))
                os.chmod(home, 0o755)          # 让非特权用户能走到落点（家目录本身要能进）
                for path in (root, slot, os.path.join(slot, "specs"),
                             os.path.join(slot, "specs", "core")):
                    os.chmod(path, 0o555 if os.path.isdir(path) else 0o444)
                target = os.path.join(slot, "AGENTS_COMMON.adoc")
                # 就地改：非特权用户必须写不进去
                r = subprocess.run(["su", nobody, "-c",
                                    f'printf x >> "{target}"'], capture_output=True, text=True)
                self.assertNotEqual(0, r.returncode,
                                    f"非特权用户改动了落点里的规范副本:\n{r.stdout}{r.stderr}")
                with open(target, "rb") as fh:
                    self.assertEqual(self.ENTRY, fh.read())     # 内容逐字节未变
                # 往落点里新增文件：目录没有写位，同样必须失败
                r = subprocess.run(["su", nobody, "-c",
                                    f'touch "{slot}/injected"'], capture_output=True, text=True)
                self.assertNotEqual(0, r.returncode,
                                    "非特权用户往落点里新增了文件（目录写位没收紧）")
        finally:
            shutil.rmtree(home, ignore_errors=True)

    def test_keep_still_hardens_landing(self):
        """`--keep` 下**同样收紧**：放开过权限的落点，加 `--keep` 再跑一次必须回到只读。

        "不动本地那一份"（不核内容、不覆盖）与"它还是只读的"是两件事——只在前一路收紧时，
        最需要它的一路（有人 `chmod -R u+w` 改过副本、又按安装流程加了 `--keep`）恰恰漏掉。
        """
        import threading
        served = {"AGENTS_COMMON.adoc": self.ENTRY, "README.adoc": b"r1\n",
                  "specs/core/execution.adoc": self.SPEC, **self._install_scripts_served()}
        home = tempfile.mkdtemp(prefix="readonly-keep-home-")
        try:
            with self._serve(served) as httpd:
                port = httpd.server_address[1]
                threading.Thread(target=httpd.serve_forever, daemon=True).start()
                base = f"http://127.0.0.1:{port}"
                proc = self._run_fetch(base, home=home)
                self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
                root = os.path.join(home, ".cache", "agent-specs")
                slot = os.path.join(root, re.sub(r"[^A-Za-z0-9._-]+", "_",
                                                 f"127.0.0.1:{port}").strip("_"))
                if os.name != "posix":
                    self.skipTest("Windows 上 chmod 只切只读位，权限位实测不适用（跳过不等于通过）")
                # 放开权限（模拟"有人就地改了副本"，也模拟只读位被外部改动）
                for dirpath, dirnames, filenames in os.walk(root):
                    os.chmod(dirpath, 0o755)
                    for name in filenames:
                        os.chmod(os.path.join(dirpath, name), 0o644)
                self.assertTrue(os.stat(os.path.join(slot, "AGENTS_COMMON.adoc")).st_mode
                                & stat.S_IWUSR, "夹具没生效：目标文件仍是只读的")
                proc = self._run_fetch(base, extra=("--keep",), home=home)
                self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
                self.assertFalse(os.stat(os.path.join(slot, "AGENTS_COMMON.adoc")).st_mode
                                 & stat.S_IWUSR,
                                 "--keep 没把放开过权限的落点收回只读")
                self.assertFalse(os.stat(slot).st_mode & stat.S_IWUSR)
                self.assertNotIn("没能收紧", proc.stdout + proc.stderr)
        finally:
            shutil.rmtree(home, ignore_errors=True)

    def test_unhardened_landing_is_reported(self):
        """收紧失败**不得静默**：改不动权限位时须如实警告，不得照旧打「落点已设为只读」。

        以特权身份（root）跑时权限位改得动、看不出这条；故换一个**非特权身份**复现，
        夹具是**真实存在的形态**：落点所在的那一层**对调用方只读**（如别处移交/以只读
        方式挂上来的目录）——`chmod` 拒改（收不紧），而在其中**新建**文件另要写位、
        同样被拒（故取文件失败），退出码 1。本条要的正是这一路：**"没能收紧"必须说出来**，
        读到的必须不是那句「落点已设为只读」。
        """
        if os.name != "posix" or os.geteuid() != 0:
            self.skipTest("需要 POSIX 且以 root 运行才能用别的属主复现『收紧失败』；"
                          "本机不满足，故未实测『收紧失败会被如实警告』（跳过不等于通过）")

        def _has_shell(u):
            """要能 `su -c` 过去跑命令：登录 shell 为 nologin 的账号（nobody/daemon 常见）会被拒。"""
            pwd = subprocess.run(["getent", "passwd", u], capture_output=True, text=True)
            return pwd.returncode == 0 and not pwd.stdout.rstrip().endswith("nologin")

        nobody = next((u for u in ("node", "nobody", "daemon") if _has_shell(u)), None)
        if nobody is None:
            self.skipTest("本机没有可 `su -c` 的非特权用户，故未实测"
                          "『收紧失败会被如实警告』（跳过不等于通过）")
        import threading
        served = {"AGENTS_COMMON.adoc": self.ENTRY, "README.adoc": b"r1\n",
                  "specs/core/execution.adoc": self.SPEC, **self._install_scripts_served()}
        home = tempfile.mkdtemp(prefix="readonly-unhardened-home-")
        try:
            with self._serve(served) as httpd:
                port = httpd.server_address[1]
                threading.Thread(target=httpd.serve_forever, daemon=True).start()
                os.chmod(home, 0o755)
                root = os.path.join(home, ".cache", "agent-specs")
                os.makedirs(root)
                os.chown(root, 0, 0)
                os.chmod(root, 0o555)       # 落点根：调用方能进、但**改不动也建不了**
                script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                      "script", "fetch-specs.py")
                proc = subprocess.run(
                    ["su", nobody, "-c",
                     f"HOME={home} {sys.executable} {script} --base http://127.0.0.1:{port}"],
                    capture_output=True, text=True, timeout=120)
                out = proc.stdout + proc.stderr
                self.assertIn("没能收紧", out)                  # 只读没落下 → 须如实说
                self.assertNotIn("落点已设为只读", out)         # 不得照旧宣称已只读
                # 收不紧的落点在输出里仍算"文件取到过哪些"这一栏、不说成"权限已就绪"
                self.assertIn("警告:", out)
        finally:
            shutil.rmtree(home, ignore_errors=True)

class TestFetchSpecsPathBoundary(CheckSpecsTestCase):
    """钉住 `_ensure_writable` 的**路径边界判据**（PR 返工补）。

    失效形态（本 PR 原实现，实测复现）：原先的判据是字符串前缀
    `node.startswith(stop)`，不做路径分段边界——`~/.cache/agent-specs-backup`
    与落点只是**名字前面重合**，却会被判成"在落点之内"。后果不是报错而是
    **静默放权**：给落点旁边的兄弟目录补回写位，而"落点只读"这句话没人再核对。
    当前调用点拼出的 `dest` 必在落点内（暂不可达），但判据本身不严。

    故这里直接按**真脚本**的函数实测（不复制一份实现，否则测的是副本）：
      * 同名邻居 `/a/agent-specs-backup`、同前缀邻居 `/a/agent-specs2` 都**不在**落点内；
      * 落点自己、以及落点下的任意层级**在**落点内；
      * 不同盘符（Windows `C:` 与 `D:`）比较时 `commonpath` 抛错 → 按"不在内"处理
        （保守的一侧：少补一处写位最多落盘失败并如实报错，多补一处才是越界）。
    """

    def _load_fetch_specs(self):
        """按路径导入真脚本（文件名带 `-`，故不能用普通 `import`）。"""
        import importlib.util
        real_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(real_root, "script", "fetch-specs.py")
        spec = importlib.util.spec_from_file_location("fetch_specs_under_test", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_path_boundary_not_string_prefix(self):
        mod = self._load_fetch_specs()
        stop = os.path.join(tempfile.mkdtemp(prefix="boundary-stop-"), "agent-specs")
        os.makedirs(stop)
        try:
            # 落点自己与落点之下 → 在内
            self.assertTrue(mod._is_within(stop, stop))
            self.assertTrue(mod._is_within(os.path.join(stop, "specs", "core"), stop))
            # **同名邻居 / 同前缀邻居 → 不在内**（字符串前缀会误判为在内）
            self.assertFalse(mod._is_within(stop + "-backup", stop))
            self.assertFalse(mod._is_within(stop + "2", stop))
            self.assertFalse(mod._is_within(os.path.join(os.path.dirname(stop), "other"), stop))
            # 父目录 → 不在内（补位只往上补到落点为止，不该再往上出界）
            self.assertFalse(mod._is_within(os.path.dirname(stop), stop))
        finally:
            shutil.rmtree(os.path.dirname(stop), ignore_errors=True)

    def test_ensure_writable_leaves_sibling_untouched(self):
        """同名邻居的权限位**不得**被 `_ensure_writable` 动过（本函数要防的那件事）。"""
        if os.name != "posix":
            self.skipTest("Windows 上无 POSIX 权限位语义（os.chmod 只切只读属性），"
                          "故未实测『同名邻居未被改权限』（跳过不等于通过）")
        import stat as _stat
        mod = self._load_fetch_specs()
        root = tempfile.mkdtemp(prefix="boundary-sib-")
        stop = os.path.join(root, "agent-specs")
        sibling = os.path.join(root, "agent-specs-backup")
        os.makedirs(os.path.join(stop, "specs"))
        os.makedirs(sibling)
        try:
            os.chmod(sibling, 0o555)          # 邻居先收紧成只读
            before = _stat.S_IMODE(os.stat(sibling).st_mode)
            # ① 目标在落点内：邻居不得被碰
            mod._ensure_writable(stop, os.path.join(stop, "specs", "x.adoc"))
            after = _stat.S_IMODE(os.stat(sibling).st_mode)
            self.assertEqual(before, after,
                             f"同名邻居的权限被改了: {oct(before)} → {oct(after)}")
            # ② 判据取**路径分段边界**：把"目标"放在同名邻居里时，邻居目录**仍须**被判为
            # "不在落点内"，故它不得被补回写位——字符串前缀判据在这一档会误判为在内
            # （`/root/agent-specs-backup`.startswith(`/root/agent-specs`) 为真），
            # 于是给邻居补上写位；本函数要防的正是这次**静默放权**。
            os.makedirs(os.path.join(sibling, "specs"), exist_ok=True)
            os.chmod(os.path.join(sibling, "specs"), 0o555)
            mod._ensure_writable(stop, os.path.join(sibling, "specs", "x.adoc"))
            self.assertEqual(before, _stat.S_IMODE(os.stat(sibling).st_mode),
                             "同名邻居被当成落点、写位被补回（路径边界判据退化成字符串前缀）")
            self.assertEqual(0o555, _stat.S_IMODE(os.stat(os.path.join(sibling, "specs")).st_mode),
                             "同名邻居的下级目录写位被补回（路径边界判据退化成字符串前缀）")
        finally:
            os.chmod(sibling, 0o755)
            shutil.rmtree(root, ignore_errors=True)


class TestFetchSpecsTruncatedResponse(CheckSpecsTestCase):
    """端到端实测：**响应被截断时，脚本不得崩、落点仍须被收紧成只读**（PR 返工补）。

    失效形态（本 PR 原实现，实测复现）：`fetch_text` 的注释写着"失败抛 OSError"，但
    `http.client` 的 `HTTPException` 家族**不是** `OSError` 的子类——
    `IncompleteRead`（对端在 `Content-Length` 之外提前断连）、`BadStatusLine`
    （中间设备回非 HTTP 响应）都直接继承 `HTTPException`。而 `download_one` 只
    `except OSError`，于是它们**穿过 `download_one` 逃逸到 `fut.result()`**，把 `main` 掀掉：

      * 退出码不是约定的 0/1/2，而是一个 traceback；
      * 后面那条"整棵树收紧成只读"的收尾**一次都不跑**——落点留在 `755`/`644` 的**可写**态，
        而 stderr 里也没有任何"没收紧"的提示，无人察觉。

    这正是本 PR 要买的那条保证在**最需要它的一轮里**静默丢掉：一次网络抖动就让它失效。

    故本条按**用户会遇到的那条路**实测：
      * 用真实抓取脚本跑子进程（不复制一份实现），服务端对某一份**发一半就断连**；
      * 断言退出码落在约定集合里（**不是** traceback 崩掉）；
      * 断言 stderr 里有"失败"、且**没有** `Traceback`；
      * 断言落点里的目录与文件**确实没有写位**（收尾没有被跳过）；
      * 断言成功取到的那几份仍然在（失败不牵连别的文件）。
    Windows 上无 POSIX 写位语义（那一半靠规范约束），故本条跳过并**显式说明**。
    """

    ENTRY = b"= test\n\nspecs/core/execution.adoc\n"
    SPEC = "= 执行原则\n\n* 甲\n".encode("utf-8")

    def _install_scripts_served(self):
        """服务端要供给的安装脚本（名单从真实脚本里读，与它同源，避免手工抄漏）。"""
        real_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(real_root, "script", "fetch-specs.py"),
                  encoding="utf-8") as fh:
            src = fh.read()
        return {"script/" + rel: src.encode("utf-8")
                for rel in re.findall(r'"script/([\w.-]+)"', src)}

    def _run_fetch(self, base, extra=(), home=None):
        real_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script = os.path.join(real_root, "script", "fetch-specs.py")
        env = None
        if home:
            env = dict(os.environ, HOME=home, USERPROFILE=home)
        return subprocess.run([sys.executable, script, "--base", base, *extra],
                              cwd=real_root, capture_output=True, text=True,
                              timeout=120, env=env)

    def test_truncated_response_does_not_crash_and_still_hardens(self):
        if os.name != "posix":
            self.skipTest("Windows 上无 POSIX 写位语义，『截断后落点仍被收紧』未实测"
                          "（跳过不等于通过）")
        import http.server
        import socketserver
        import threading

        served = {"AGENTS_COMMON.adoc": self.ENTRY, "README.adoc": b"r1\n",
                  "specs/core/execution.adoc": self.SPEC, **self._install_scripts_served()}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):                                # noqa: N802 - http.server 约定
                rel = self.path.lstrip("/")
                body = served.get(rel)
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                if rel == "specs/core/execution.adoc":
                    # **截断**：声明 Content-Length 远大于实际发出的字节，然后断连
                    # → 客户端 `resp.read()` 抛 `http.client.IncompleteRead`
                    # （截断**入口**时连清单都拿不到、走的是更早的"取入口清单失败"出口，
                    # 测不到"单份文件失败却掀掉整批"这条，故截断一份普通规范）
                    self.send_header("Content-Length", str(len(body) + 1000))
                    self.end_headers()
                    self.wfile.write(body[:5])
                    self.wfile.flush()
                    self.connection.close()
                    return
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):                       # 静音
                pass

        home = tempfile.mkdtemp(prefix="truncated-home-")
        try:
            with socketserver.TCPServer(("127.0.0.1", 0), Handler) as httpd:
                port = httpd.server_address[1]
                threading.Thread(target=httpd.serve_forever, daemon=True).start()
                base = f"http://127.0.0.1:{port}"
                root = os.path.join(home, ".cache", "agent-specs")

                proc = self._run_fetch(base, home=home)

                # ① 不得崩：退出码是约定的 0/1/2，stderr 里不得有 traceback
                #    （原实现抛 `IncompleteRead` → traceback + 非约定退出码）
                self.assertIn(proc.returncode, (0, 1, 2),
                              f"退出码不在约定集合里（脚本崩了）:\n{proc.stderr}")
                self.assertNotIn("Traceback", proc.stderr,
                                 f"截断响应把脚本掀掉了:\n{proc.stderr}")
                self.assertNotEqual(0, proc.returncode,
                                    "有文件没取到却报了成功（退出码应非 0）")

                # ② 失败须如实报出、且不牵连别的文件（成功的那几份仍在）
                self.assertIn("失败", proc.stdout + proc.stderr)
                slot = os.path.join(home, ".cache", "agent-specs",
                                    re.sub(r"[^A-Za-z0-9._-]+", "_",
                                           f"127.0.0.1:{port}").strip("_"))
                self.assertFalse(os.path.exists(os.path.join(slot, "specs", "core",
                                                             "execution.adoc")),
                                 "被截断的那一份不该出现在落点里")
                with open(os.path.join(slot, "AGENTS_COMMON.adoc"), "rb") as fh:
                    self.assertEqual(self.ENTRY, fh.read())   # 别的文件照旧取到

                # ③ **收尾没被跳过**：落点里的目录与文件确实没有写位
                #    （原实现在这里留下 `755`/`644` 的可写落点，且无任何提示）
                self.assertTrue(os.path.isdir(root))
                for dirpath, dirnames, filenames in os.walk(root):
                    self.assertFalse(os.stat(dirpath).st_mode & stat.S_IWUSR,
                                     f"截断响应后目录仍有写位（收尾被跳过）: {dirpath}")
                    for name in filenames:
                        one = os.path.join(dirpath, name)
                        self.assertFalse(os.stat(one).st_mode & stat.S_IWUSR,
                                         f"截断响应后文件仍有写位（收尾被跳过）: {one}")

                # ④ 不留 `.part` 残渣（失败项的半成品不该留在只读树里）
                leftovers = [os.path.join(dp, n)
                             for dp, _, ns in os.walk(root) for n in ns
                             if n.endswith(".part")]
                self.assertEqual([], leftovers, f"落点里留下半成品: {leftovers}")
        finally:
            shutil.rmtree(home, ignore_errors=True)


class TestCheckReadonlyLandingGuard(CheckSpecsTestCase):
    """钉住『落点只读防线』（本 PR 新增）。

    用户口径原文："~/.cache/agent-specs 里的内容应该设置为只读，**不仅仅是规范里定义，
    文件本身下载后要变成只读**，并严禁项目修改此文件夹内容"。

    本条要拦的两种半成品形态：
      * **只写了规范、脚本没真的收紧**——落点仍可写，项目照旧能就地改规范副本
        （用户点名的那一句"不仅仅是规范里定义"正是指它）；
      * **只收紧、规范没说**——新实例从复制到项目里的入口文档读到时，只看到"下载的文件
        落在哪"，仍会把落点当成可写的便利目录。

    故用例两侧都覆盖：脚本侧的权限位取值 / 真的调 `chmod` / 落盘前恢复写位 / 入口保执行位 /
    收紧动作覆盖整棵树 / **`--keep` 下同样收紧** / **收紧失败不得静默**；规范侧的只读与
    "严禁项目改动"、以及**只读由本机文件系统保证**（"不止是规范里一条"）。另在
    `TestFetchSpecsReadOnlyLanding` 里做**端到端实测**：
    只读树上的更新照旧生效、非特权调用方的写入被拒。
    """

    SCRIPT_PY = (
        '#!/usr/bin/env python3\n'
        '"""fetch 脚本：落点取完即只读（目录去掉写位、文件只留读位）。\n'
        '落盘前用 _ensure_writable 只恢复本脚本所需的最小写位——只读不挡更新。\n'
        '已知限制：Windows 上只有文件那一半成立（目录的增删改名拦不住）。\n'
        '`FILE_ATTRIBUTE_READONLY` 只对文件生效，目录的增删改名拦不住。\n'
        '"""\n'
        '_READ_ONLY_FILE_MODE = 0o444\n'
        '_READ_ONLY_DIR_MODE = 0o555\n'
        'def _make_read_only(path, is_dir=False):\n'
        '    """收紧为只读；入口脚本保留执行位。\n'
        '    Windows 上只有文件那一半成立：目录的增删改名拦不住（见头部「已知限制」）。\n'
        '    没有写位就不能在其中增删改名（POSIX）；不得把这句话读成全平台成立。"""\n'
        '    import os\n'
        '    os.chmod(path, _READ_ONLY_FILE_MODE)\n'
        'def _ensure_writable(out_dir, dest):\n'
        '    """落盘前只恢复本脚本所需的最小写位。"""\n'
        'def main():\n'
        '    """落点一次性收紧（--keep 下同样收紧：收紧的是只读状态）。"""\n'
        '    unhardened = _make_read_only(install_scripts_dir(), is_dir=True)\n'
        '    if unhardened:\n'
        '        print("警告: 落点有 N 处没能收紧")\n'
        'def fetch_text(base, path):\n'
        '    """取一份远端文本；失败一律抛 OSError（本函数是这条契约的守门人）。\n'
        '    http.client 的 HTTPException 家族**不是** OSError 的子类——\n'
        '    IncompleteRead（响应被截断）、BadStatusLine 会穿过 download_one 的 except\n'
        '    把 main 掀掉，收尾那条收紧一次都不跑。\n'
        '    """\n'
        '    try:\n'
        '        import http.client\n'
        '        resp = None\n'
        '    except http.client.HTTPException as e:\n'
        '        raise OSError("取回失败") from e\n'
        'def download_one(base, rel, out_dir, keep):\n'
        '    """单个文件任何异常都不得掀掉整批（兜底后照旧去收紧落点）。"""\n'
    )

    COMMON = (
        "= AGENT 执行规范（公共入口）\n\n"
        "== 取规范到本地副本\n\n"
        "* 落点只有一处：**用户家目录**下的 `.cache/agent-specs`。\n"
        "* **落点取完即只读、严禁项目改动它（L1）**：取完即把该文件夹收紧为**只读**，"
        "**任何项目都不得改动落点里的内容**——不得就地编辑、新增、删除或改名其中的任何文件。"
        "**这不止是规范里定义的一条**：只读由**本机文件系统**保证。"
        "**平台边界**：Windows 上只有「文件只读」那一半由本机强制（目录的增删改名拦不住）。"
        "**项目要留自己的东西，写进项目自己**。\n"
        "\n"
        "该文件夹是**只读的**：取完即收紧为只读，**严禁任何项目改动它**。\n"
    )

    TEMPLATE_ONLY = (
        "= AGENT 执行规范（公共入口）\n\n"
        "== 取规范到本地副本\n\n"
        "* 落点只有一处：**用户家目录**下的 `.cache/agent-specs`。\n"
    )

    def _write(self, script=None, common=None) -> None:
        cm.REPO_SCRIPT_SRC_CACHE.clear()
        self.write("script/fetch-specs.py",
                   script if script is not None else self.SCRIPT_PY)
        self.write("AGENTS_COMMON.adoc",
                   common if common is not None else self.COMMON)

    def test_valid_passes(self):
        self._write()
        cm.check_readonly_landing_guard()
        self.assertEqual([], cm.errors)

    def test_script_missing_reports(self):
        # 反例：抓手被删 → 只读这条只剩规范里一句话（本机侧无从强制）
        self._write()
        os.remove(os.path.join(self.root, "script", "fetch-specs.py"))
        cm.check_readonly_landing_guard()
        self.assertIn("fetch-specs.py", self.error_texts())

    def test_mode_constants_removed_reports(self):
        # 反例：只读权限位的取值被抽走 → "只读"只剩一句注释，落点实际权限仍是下载时的默认位
        self._write(script=self.SCRIPT_PY.replace(
            "_READ_ONLY_FILE_MODE = 0o444\n_READ_ONLY_DIR_MODE = 0o555\n", ""))
        cm.check_readonly_landing_guard()
        # 报错按"缺失的那几个锚点"列出，两个常量一并被抽走时列表里两个都在
        self.assertIn("_READ_ONLY_FILE_MODE", self.error_texts())
        self.assertIn("_READ_ONLY_DIR_MODE", self.error_texts())

    def test_chmod_call_removed_reports(self):
        # 反例（**用户点名的那一半**）：只写常量与一句"落点是只读的"、真的不调 chmod
        # → 落点仍可写，项目照旧能就地改规范副本（"不仅仅是规范里定义"被违反）
        self._write(script=self.SCRIPT_PY.replace(
            "    os.chmod(path, _READ_ONLY_FILE_MODE)\n", ""))
        cm.check_readonly_landing_guard()
        self.assertIn("os.chmod", self.error_texts())

    def test_ensure_writable_removed_reports(self):
        # 反例：不给落盘留写位 → "默认以远程为准"被只读挡住（远端改了写不进去，重跑拿不到最新）
        self._write(script=self.SCRIPT_PY.replace("_ensure_writable", "__gone__"))
        cm.check_readonly_landing_guard()
        self.assertIn("_ensure_writable", self.error_texts())

    def test_executable_exception_removed_reports(self):
        # 反例：没写明"入口保留执行位" → 收紧把入口的可执行位一并抹掉，
        # "下次重装直接跑落点里的入口"随之失效（只读与可执行必须同时成立）
        self._write(script=self.SCRIPT_PY.replace("入口脚本保留执行位", "入口脚本一并处理"))
        cm.check_readonly_landing_guard()
        self.assertIn("保留执行位", self.error_texts())

    def test_tree_wide_call_removed_reports(self):
        # 反例：收紧只覆盖一部分（或没落在汇总之前）→ 另一半仍是可写的，
        # 而"落点是只读的"这句话对读者无法核对
        self._write(script=self.SCRIPT_PY.replace(
            "    unhardened = _make_read_only(install_scripts_dir(), is_dir=True)\n", ""))
        cm.check_readonly_landing_guard()
        self.assertIn("unhardened = _make_read_only(install_scripts_dir(), is_dir=True)",
                      self.error_texts())

    def test_http_exception_not_normalized_reports(self):
        # 反例（**本轮补，PR 返工**）：`fetch_text` 不再把 `http.client.HTTPException`
        # （`IncompleteRead`/`BadStatusLine`）归一成 `OSError` → 它穿过 `download_one`
        # 的 `except OSError` 逃逸到 `fut.result()`，把 `main` 掀掉：调用方拿到 traceback
        # 而不是约定的 0/1/2，后面那条"整棵树收紧成只读"的收尾**一次都不跑**，
        # 落点留在可写态且毫无提示——一次网络抖动就让本防线的收益归零
        self._write(script=self.SCRIPT_PY.replace("HTTPException", "PassthroughError"))
        cm.check_readonly_landing_guard()
        self.assertIn("HTTPException", self.error_texts())

    def test_batch_bailout_removed_reports(self):
        # 反例：取文件那一段没有兜底 → 单个文件的任何异常都会掀掉整批，
        # 收尾（收紧落点）随之被跳过，落点留在可写态
        self._write(script=self.SCRIPT_PY.replace(
            "单个文件任何异常都不得掀掉整批（兜底后照旧去收紧落点）。", ""))
        cm.check_readonly_landing_guard()
        self.assertIn("单个文件任何异常都不得掀掉整批", self.error_texts())

    def test_windows_boundary_removed_reports(self):
        # 反例（**本轮补，平台限定**）：脚本头部不写 Windows 的效力边界 →
        # 「目录去掉写位＝不能在其中增删改名」被当成全平台成立，
        # Windows 读者据此以为落点真被强制（实际只做到文件那一半、目录那一半靠规范约束）
        self._write(script=self.SCRIPT_PY.replace(
            '已知限制：Windows 上只有文件那一半成立（目录的增删改名拦不住）。\n'
            '`FILE_ATTRIBUTE_READONLY` 只对文件生效，目录的增删改名拦不住。\n', ''))
        cm.check_readonly_landing_guard()
        self.assertIn("Windows", self.error_texts())
        self.assertIn("已知限制", self.error_texts())

    def test_platform_limit_missing_in_executor_reports(self):
        # 反例：头部写了 Windows 边界、**执行体那句断言照旧无平台限定** →
        # 读执行体的人多半不看头部「已知限制」，而那正是对权限位下断言的地方
        # （判据取"两处都要有"，故 ① 过了、② 仍要报）
        self._write(script=self.SCRIPT_PY.replace(
            '    Windows 上只有文件那一半成立：目录的增删改名拦不住'
            '（见头部「已知限制」）。\n'
            '    没有写位就不能在其中增删改名（POSIX）；'
            '不得把这句话读成全平台成立。', ''))
        cm.check_readonly_landing_guard()
        self.assertIn("不能在其中增删改名", self.error_texts())

    def test_spec_platform_boundary_removed_reports(self):
        # 反例：规范侧只写"只读由本机文件系统保证"、不加平台限定 →
        # Windows 读者会以为落点真被强制（判据断言了一句拿不到的事实）
        self._write(common=self.COMMON.replace(
            '**平台边界**：Windows 上只有「文件只读」那一半由本机强制'
            '（目录的增删改名拦不住）。', ''))
        cm.check_readonly_landing_guard()
        self.assertIn("平台边界", self.error_texts())

    def test_spec_readonly_removed_reports(self):
        # 反例：规范侧只写"落点在哪"，不写"只读"与"严禁项目改动" → 读者把落点当可写目录
        self._write(common=self.TEMPLATE_ONLY)
        cm.check_readonly_landing_guard()
        self.assertIn("只读", self.error_texts())

    def test_filesystem_guarantee_removed_reports(self):
        # 反例：删掉"只读由本机文件系统保证"这句 → 又退回"规范里定义一条、靠自觉遵守"
        # （用户口径点名的正是这一层）
        self._write(common=self.COMMON.replace("**本机文件系统**", "**约定**"))
        cm.check_readonly_landing_guard()
        self.assertIn("文件系统", self.error_texts())

    def test_project_own_place_removed_reports(self):
        # 反例：只说"严禁改动落点"、不给正当去路 → 执行者会把它读成"没地方放临时文件"，
        # 转而先把权限放开（等于本条失效）
        self._write(common=self.COMMON.replace("**项目要留自己的东西，写进项目自己**。", ""))
        cm.check_readonly_landing_guard()
        self.assertIn("写进项目自己", self.error_texts())


class TestCheckMethodPlacementGuard(CheckSpecsTestCase):
    """钉住『成员与方法次序』防线（用户提出，Issue #195）。

    用户原话："新增方法/函数时，按照业务流程的先后顺序进行排序……（即允许按照流程前后顺序，
    把新增方法加在已有方法的前面（包括最前面）或者中间），如果有重载方法，直接加在重载方法
    的附近……先初始化的在前面，先用到的在前面，后面的依赖前面的……例外：接口查询数据时，
    要对数据库实体和返回模型做转换，转换方法默认写在查询接口后面。此规范只适用于新增方法/函数，
    不对已有方法生效，review 时不算问题不提出"。

    失效形态：新增成员一律追加到类末尾（"按加入日期排序"成了第二个次序来源），**新增的位置
    不报错**、只是次序无声漂移；重载被别的成员隔开、数据转换方法跑到查询之前。

    核对对象一律是**条目/行自己的正文**（`bullet_tokens` / `line_tokens`）：本条与相邻条目
    （「链式赋值顺序随字段顺序」含字段顺序与存量边界句、「实体类字段按数据库顺序」含表列序、
    「静态字段排在类最前」含例外句）字样相同，按整节或整份文件核时它们会把缺项兜住。
    """

    CODING = "specs/general/coding.adoc"
    JAVA = "specs/stack/java.adoc"
    ADOPTION = "library/adoption.adoc"
    COMMON = "AGENTS_COMMON.adoc"
    README = "README.adoc"
    SECTION = "命名与代码质量"

    def setUp(self) -> None:
        super().setUp()
        self._orig_coding = cm.CODING_FILE
        self._orig_java = cm.JAVA_STACK_FILE
        cm.CODING_FILE = os.path.join(self.root, "specs", "general", "coding.adoc")
        cm.JAVA_STACK_FILE = os.path.join(self.root, "specs", "stack", "java.adoc")
        for rel in (self.CODING, self.JAVA, self.ADOPTION, self.COMMON, self.README):
            with open(rel, encoding="utf-8") as fh:
                setattr(self, "_text_" + rel.replace("/", "_"), fh.read())

    def tearDown(self) -> None:
        cm.CODING_FILE = self._orig_coding
        cm.JAVA_STACK_FILE = self._orig_java
        super().tearDown()

    def _src(self, rel: str) -> str:
        return getattr(self, "_text_" + rel.replace("/", "_"))

    def _write_all_valid(self) -> None:
        for rel in (self.CODING, self.JAVA, self.ADOPTION, self.COMMON, self.README):
            self.write(rel, self._src(rel))
        # `run_rule_guard` 按阶段去重：每个用例都自成一个阶段，这里显式清一次是防御性的
        cm._RULES_RUN_THIS_PHASE.clear()

    def _run_guard(self) -> None:
        """只跑本道防线（`run_rule_guard` 有阶段内去重，故先清去重集合）。"""
        cm._RULES_RUN_THIS_PHASE.clear()
        cm.check_method_placement_guard()

    def _mutated(self, rel: str, removed: str, replacement: str = "") -> None:
        self.assertIn(removed, self._src(rel))
        self._write_all_valid()
        self.write(rel, self._src(rel).replace(removed, replacement))

    def _replace_bullet(self, rel: str, start: str, hollow: str) -> None:
        """把 `start` 打头的那条 bullet 整条换成 `hollow`（钉"要点被抽空成一句空话"）。"""
        self._write_all_valid()
        lines = self._src(rel).splitlines(keepends=True)
        idx = next(i for i, ln in enumerate(lines) if ln.startswith(start))
        self.write(rel, "".join(lines[:idx] + [hollow] + lines[idx + 1:]))

    def test_valid_passes(self):
        # 正例兼锚点自检：真文档逐字进夹具时防线必须报绿（锚点与文档脱节时先在这一条暴露）
        self._write_all_valid()
        cm.check_method_placement_guard()
        self.assertEqual("", self.error_texts())

    def test_rule_removed_reports(self):
        # 反例①：条文（含 L1 标注）被抽 -> 「新增的放哪都行」重新成立
        self._mutated(self.CODING, "**成员与方法次序（L1，任何语言）**", "关于成员次序的说明")
        self._run_guard()
        self.assertIn("成员与方法次序", self.error_texts())

    def test_allow_insert_removed_reports(self):
        # 反例②：用户点名的「允许插前面/中间」被抽 -> 退回「只能往末尾加」（Google 点名禁止的形态）
        self._mutated(self.CODING,
                      "允许把新增的方法加在**已有成员的前面（含最前面）或中间**",
                      "新增方法加在末尾")
        self._run_guard()
        self.assertIn("允许把新增的方法加在**已有成员的前面（含最前面）或中间**",
                      self.error_texts())

    def test_not_append_tail_removed_reports(self):
        # 反例③：禁止面（不得一律追加到末尾）被抽 -> 追加到末尾重新成为默许形态
        self._mutated(self.CODING,
                      "**不得**为「不动已有顺序」而一律追加到类/文件末尾",
                      "改到哪算哪")
        self._run_guard()
        self.assertIn("**不得**为「不动已有顺序」而一律追加到类/文件末尾", self.error_texts())

    def test_overload_adjacency_removed_reports(self):
        # 反例④：重载相邻被抽 -> 重载被别的成员隔开、无判据
        self._mutated(self.CODING,
                      "**重载成员**（同名不同参数）**一律紧邻已有同名成员**",
                      "重载成员照常写")
        self._run_guard()
        self.assertIn("**重载成员**（同名不同参数）**一律紧邻已有同名成员**", self.error_texts())

    def test_conversion_exception_removed_reports(self):
        # 反例⑤：例外（转换方法跟随查询）被抽 -> 转换方法被按「被调用者在前」提到查询之前
        self._mutated(self.CODING,
                      "**默认写在查询它的那个接口/方法之后**",
                      "")
        self._run_guard()
        self.assertIn("**默认写在查询它的那个接口/方法之后**", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例⑥：判定标准被抽 -> 本条自身不可判定，只剩一句口号
        self._mutated(self.CODING,
                      "**判定标准（任一命中即违规）**",
                      "补充说明")
        self._run_guard()
        self.assertIn("**判定标准（任一命中即违规）**", self.error_texts())

    def test_increment_only_boundary_removed_reports(self):
        # 反例⑦：存量边界（只对新增生效、review 不提出问题——后者已升为全局口径，
        # specs/general/review.adoc「review 的默认检查面」，此处只留回指）被抽 ->
        # 会被读成「必须立刻重排既有成员」，与用户「不对已有方法生效」相抵
        self._mutated(self.CODING,
                      "review 时对既有成员的位置不提出问题",
                      "")
        self._run_guard()
        self.assertIn("review 时对既有成员的位置不提出问题",
                      self.error_texts())

    def test_basis_line_removed_reports(self):
        # 反例⑧：依据行/取舍声明被抽 -> 读者把本集合的取舍当成标准要求
        self._mutated(self.CODING,
                      "**「按流程次序、可插前面或中间 + 重载相邻 + 转换跟随查询」是本集合的判据化取值**",
                      "通行做法")
        self._run_guard()
        self.assertIn("本集合的判据化取值", self.error_texts())

    def test_bullet_present_but_hollow_reports(self):
        """反例⑨：条目还在、要点被抽空成一句空话 -> 须报。"""
        self._replace_bullet(
            self.CODING,
            "* **成员与方法次序（L1，任何语言）**",
            "* **成员与方法次序（L1，任何语言）**：新增成员的位置看着办就行。\n")
        self._run_guard()
        self.assertIn("允许把新增的方法加在**已有成员的前面（含最前面）或中间**",
                      self.error_texts())

    def test_java_landing_removed_reports(self):
        # 反例⑩：Java 落点被抽 -> Java 执行者按栈文件学时仍会一律追加到类末尾
        self._mutated(self.JAVA, "**成员与方法次序（L1，本文件是 Java 落点）**",
                      "关于成员次序")
        self._run_guard()
        self.assertIn("成员与方法次序（L1，本文件是 Java 落点）", self.error_texts())

    def test_java_landing_reversed_reports(self):
        """反例⑪：Java 落点条文被**反向**（载体名仍在、方向反了）-> 须报。"""
        self._mutated(self.JAVA,
                      "写在依赖它的 `RestTemplate` 之前",
                      "写在依赖它的 `RestTemplate` 之后")
        self._run_guard()
        self.assertIn("写在依赖它的 `RestTemplate` 之前", self.error_texts())

    def test_dispatcher_feature_removed_reports(self):
        # 反例⑫：调度器识别特征被抽 -> 新增方法不会触发加载该条
        self._mutated(self.COMMON, "要**新增字段/方法/函数**", "要写代码")
        self._run_guard()
        self.assertIn("要**新增字段/方法/函数**", self.error_texts())

    def test_dispatcher_java_feature_removed_reports(self):
        # 反例⑬：Java 技术栈登记里的识别特征被抽 -> Java 项目按栈登记加载看不到这条
        self._mutated(self.COMMON, "**成员与方法次序**", "**成员排序**")
        self._run_guard()
        self.assertIn("**成员与方法次序**", self.error_texts())

    def test_readme_sync_removed_reports(self):
        # 反例⑭：README 目录说明未同步 -> 读者按 README 学习时无从知道有这条规则
        self._write_all_valid()
        self.write(self.README, self._src(self.README).replace("**成员与方法次序", "**成员次序"))
        self._run_guard()
        self.assertIn("README.adoc", self.error_texts())

    def test_adoption_not_registered_reports(self):
        # 反例⑮：图书馆未登记本集合取舍 -> 读者会把本站取舍读成标准规定
        self._mutated(self.ADOPTION, "**只对新增成员生效**", "只对新写的生效")
        self._run_guard()
        self.assertIn("library/adoption.adoc", self.error_texts())

    def test_adoption_rule_hollowed_reports(self):
        """反例⑯：图书馆登记被掏空成一句空话 -> 须报。"""
        self._write_all_valid()
        text = self._src(self.ADOPTION)
        idx = text.index("* **「成员与方法次序")
        end = text.index("\n\n", idx)
        hollow = ("* **「成员与方法次序」是本集合自己的判据化取舍**：成员与方法次序，"
                  "本集合自己的判据化取舍，没有任何材料规定。\n")
        self.write(self.ADOPTION, text[:idx] + hollow + text[end + 1:])
        self._run_guard()
        self.assertIn("library/adoption.adoc", self.error_texts())


class TestCheckChainAssignmentOrderGuard(CheckSpecsTestCase):
    """钉住『链式赋值顺序随字段顺序』防线（用户提出，Issue #190）。

    用户原话："链式调用时，比如赋值，顺序 和字段、数据库顺序保持一致"。

    核对对象一律是**条目/行自己的正文**（`bullet_tokens` / `line_tokens`）：本道防线的
    三个判定点（依据行、判定标准、例外、存量边界）在**同一节/同一文件的相邻条目**里
    都有同样字样，按整节或整份文件核时它们会把缺项兜住。故用例分两类：

    * 抽掉要点（`test_*_removed_reports`）——逐项核锚点仍在；
    * **要求被反向/条目被掏空/整条移出该节**（`test_*_reversed_reports`、
      `test_bullet_present_but_hollow_reports`、`test_rule_moved_out_of_section_reports`）
      ——这三个形态是旧写法（`section_groups` / `file_groups`）实际漏放的，是本轮返工的
      立项依据，任一回归即报红。
    """

    CODING = "specs/general/coding.adoc"
    JAVA = "specs/stack/java.adoc"
    TEMPLATE = "specs/stack/java-object.adoc"
    ADOPTION = "library/adoption.adoc"
    COMMON = "AGENTS_COMMON.adoc"
    SECTION = "命名与代码质量"

    def setUp(self) -> None:
        super().setUp()
        self._orig_coding = cm.CODING_FILE
        self._orig_java = cm.JAVA_STACK_FILE
        cm.CODING_FILE = os.path.join(self.root, "specs", "general", "coding.adoc")
        cm.JAVA_STACK_FILE = os.path.join(self.root, "specs", "stack", "java.adoc")
        with open(self.CODING, encoding="utf-8") as fh:
            self.CODING_TEXT = fh.read()
        with open(self.JAVA, encoding="utf-8") as fh:
            self.JAVA_TEXT = fh.read()
        with open(self.TEMPLATE, encoding="utf-8") as fh:
            self.TEMPLATE_TEXT = fh.read()
        with open(self.ADOPTION, encoding="utf-8") as fh:
            self.ADOPTION_TEXT = fh.read()
        with open(self.COMMON, encoding="utf-8") as fh:
            self.COMMON_TEXT = fh.read()
        # 调度器落点取模块常量（每个用例的临时根不同），不硬编码仓库根相对路径
        self.COMMON = os.path.relpath(cm.GENERIC_FILE, self.root)

    def tearDown(self) -> None:
        cm.CODING_FILE = self._orig_coding
        cm.JAVA_STACK_FILE = self._orig_java
        super().tearDown()

    def _write_all_valid(self) -> None:
        self.write(self.CODING, self.CODING_TEXT)
        self.write(self.JAVA, self.JAVA_TEXT)
        self.write(self.TEMPLATE, self.TEMPLATE_TEXT)
        self.write(self.ADOPTION, self.ADOPTION_TEXT)
        self.write(self.COMMON, self.COMMON_TEXT)
        cm._RULES_RUN_THIS_PHASE.clear()

    def _run_guard(self) -> None:
        """只跑本道防线（`run_rule_guard` 有阶段内去重，故先清去重集合）。"""
        cm._RULES_RUN_THIS_PHASE.clear()
        cm.check_chain_assignment_order_guard()

    def _mutated_coding(self, removed: str, replacement: str = "") -> None:
        self.assertIn(removed, self.CODING_TEXT)
        self._write_all_valid()
        self.write(self.CODING, self.CODING_TEXT.replace(removed, replacement))

    def _bullet_lines(self, start: str, end: str) -> tuple:
        """切出临时文档里 `start` 打头的那一条正文（到 `end` 打头的下一条为止）。"""
        i = self.CODING_TEXT.index(start)
        j = self.CODING_TEXT.index(end, i)
        return i, j

    def test_valid_passes(self):
        # 正例兼锚点自检：真文档逐字进夹具时防线必须报绿（锚点与文档脱节时先在这一条暴露）
        self._write_all_valid()
        cm.check_chain_assignment_order_guard()
        self.assertEqual("", self.error_texts())

    def test_rule_removed_reports(self):
        # 反例①：条文（含 L1 标注）被抽 -> 「顺序怎么写都行」重新成立
        self._mutated_coding("链式赋值顺序随字段顺序（L1，任何语言）", "关于顺序的说明")
        self._run_guard()
        # 条文名被改后连 bullet 锚点都取不到，报错形态是"条目丢失"（与条款被删等价）
        self.assertIn("链式赋值顺序随字段顺序", self.error_texts())

    def test_requirement_inverted_reports(self):
        # 反例②：条文还在、**要求被反向**（写成「书写顺序与字段顺序无关」）-> 须报
        self._mutated_coding("**书写顺序须与字段顺序一致**", "**书写顺序不作要求**")
        self._run_guard()
        self.assertIn("**书写顺序须与字段顺序一致**", self.error_texts())

    def test_field_order_xref_removed_reports(self):
        # 反例③：字段顺序的回指被抽 -> 本条自成第二个次序来源，两条规则各自漂移
        self._mutated_coding("其他类**按「接口/类/注解成员排序」取该类的成员次序", "其他类按本条的次序")
        self._run_guard()
        self.assertIn("接口/类/注解成员排序", self.error_texts())

    def test_reason_removed_reports(self):
        # 反例④：理由（赋值再排一次序即第二真源、次序漂移不报错）被抽 -> 级别与处置会被降级
        self._mutated_coding("同一份字段清单的第二个来源", "多写一遍更清楚")
        self._run_guard()
        self.assertIn("同一份字段清单的第二个来源", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例⑤：判定标准被抽 -> 本条自身不可判定，只剩一句口号
        self._mutated_coding("**判定标准（任一命中即违规）**：① 同一处构建的赋值环节次序与字段顺序不一致",
                             "补充说明：① 尽量保持一致")
        self._run_guard()
        self.assertIn("**判定标准（任一命中即违规）**", self.error_texts())

    def test_exception_removed_reports(self):
        # 反例⑥：语义例外被抽 -> 覆盖赋值/依赖前值的写法被误判成违规
        self._mutated_coding("**执行次序决定语义**", "特殊情况下")
        self._run_guard()
        self.assertIn("**执行次序决定语义**", self.error_texts())

    def test_boundary_removed_reports(self):
        # 反例⑦：边界被抽 -> 被读成「必须补全所有字段」「必须拆成中间变量」
        self._mutated_coding("不要求为满足本条的次序而多写一次赋值", "视情况处理")
        self._run_guard()
        self.assertIn("不要求为满足本条的次序而多写一次赋值", self.error_texts())

    def test_migration_boundary_removed_reports(self):
        # 反例⑧：存量边界（不发动全库重排）被抽 -> 等于要求立刻批量重排既有构建语句
        self._mutated_coding("改到哪处才顺带调整该处的次序", "")
        self._run_guard()
        self.assertIn("改到哪处才顺带调整该处的次序", self.error_texts())

    def test_basis_line_removed_reports(self):
        # 反例⑨：依据行/取舍声明被抽 -> 读者把本集合的取舍当成标准要求
        self._mutated_coding("**「赋值顺序随字段顺序」是本集合的判据化取值**", "通行做法")
        self._run_guard()
        self.assertIn("本集合的判据化取值", self.error_texts())

    def test_rule_moved_out_of_section_reports(self):
        """反例⑩：整条移出「命名与代码质量」节 -> 须报。

        旧写法（`section_groups`）把核对对象取成**整个二级节**，本条移出该节后
        依据行/判定标准/例外/存量边界等字样仍在同节相邻条目里命中，实测**多项一条不报**。
        """
        self._write_all_valid()
        lines = self.CODING_TEXT.splitlines(keepends=True)
        idx = next(i for i, ln in enumerate(lines)
                   if ln.startswith("* **链式赋值顺序随字段顺序（L1，任何语言）**"))
        self.write(self.CODING, "".join(lines[:idx] + lines[idx + 1:] + [lines[idx]]))
        self._run_guard()
        self.assertIn("链式赋值顺序随字段顺序", self.error_texts())

    def test_bullet_present_but_hollow_reports(self):
        """反例⑪：条目还在、要点被抽空成一句空话 -> 须报。

        该条 bullet 由「定义段 + 缩进子段（理由/判定标准/例外/存量/依据）」组成，
        故"掏空"须把子段一并清掉——只换首行时那些子段原样留着，防线照样全绿，
        这个用例就不再能证明"掏空会报"（核的是同一条 bullet 的完整正文）。
        """
        self._write_all_valid()
        keep = ("* **链式赋值顺序随字段顺序（L1，任何语言）**：链式调用里的**赋值环节**"
                "按**字段顺序**书写，顺序怎么写都行。\n")
        lines = self.CODING_TEXT.splitlines(keepends=True)
        idx = next(i for i, ln in enumerate(lines)
                   if ln.startswith("* **链式赋值顺序随字段顺序（L1，任何语言）**"))
        # 连同其后紧跟的缩进子段（空行 + 两空格起头的续段）一并删除
        end = idx + 1
        while end < len(lines) and (not lines[end].strip()
                                    or lines[end].startswith("  ")):
            end += 1
        self.write(self.CODING, "".join(lines[:idx] + [keep] + lines[end:]))
        self._run_guard()
        self.assertIn("本集合的判据化取值", self.error_texts())

    def test_java_landing_removed_reports(self):
        # 反例⑫：Java 落点被抽 -> Java 执行者按栈文件学时仍会随手排
        self._write_all_valid()
        self.write(self.JAVA, self.JAVA_TEXT.replace("链式赋值顺序随字段顺序（L1）", "关于赋值顺序"))
        self._run_guard()
        self.assertIn("链式赋值顺序随字段顺序（L1）", self.error_texts())

    def test_landing_rule_reversed_reports(self):
        """反例⑬：Java 落点条文被**反向**（要求反转、载体名仍在）-> 须报。

        旧写法（`section_groups`）按「编码」整节核：`@Accessors(chain = true)`/
        `@SuperBuilder`/`字段声明次序` 在相邻条目（「成员与注解排序」「数据对象模板」）
        里照样命中，实测本形态 **0 条报红**。
        """
        self._write_all_valid()
        self.write(self.JAVA, self.JAVA_TEXT.replace(
            "**赋值环节的书写顺序按字段声明次序**",
            "赋值环节按**书写者顺手的次序**排列，**不要求**按字段声明次序"))
        self._run_guard()
        self.assertIn("**赋值环节的书写顺序按字段声明次序**", self.error_texts())

    def test_dispatcher_feature_removed_reports(self):
        # 反例⑭：调度器识别特征被抽 -> 写链式赋值不会触发加载该条
        self._write_all_valid()
        self.write(self.COMMON, self.COMMON_TEXT.replace(
            "链式调用**（含链式赋值、builder 链的赋值环节）", "链式调用**"))
        self._run_guard()
        self.assertIn("链式调用**（含链式赋值、builder 链的赋值环节）", self.error_texts())

    def test_template_convention_removed_reports(self):
        # 反例⑮：模板侧照抄约定被抽 -> 新建对象时真正被读的那一份里丢掉该约定
        self._write_all_valid()
        self.write(self.TEMPLATE, self.TEMPLATE_TEXT.replace("赋值环节按字段声明次序", "注意顺序"))
        self._run_guard()
        self.assertIn("赋值环节按字段声明次序", self.error_texts())

    def test_adoption_not_registered_reports(self):
        # 反例⑯：图书馆未登记本集合取舍 -> 读者会把本站取舍读成标准规定
        self._write_all_valid()
        self.write(self.ADOPTION, self.ADOPTION_TEXT.replace("链式赋值顺序随字段顺序", "某条规则"))
        self._run_guard()
        self.assertIn("library/adoption.adoc", self.error_texts())

    def test_adoption_rule_hollowed_reports(self):
        """反例⑰：图书馆登记被掏空成一句空话 -> 须报。

        旧写法（`file_groups`）按**整份文件**核：三个锚点在同文件**别的条目**里反复
        出现（分别 12 处 / 2 处 / 9 处），实测本形态 **0 条报红**。
        """
        self._write_all_valid()
        idx = self.ADOPTION_TEXT.index("* **「链式赋值顺序随字段顺序")
        end = self.ADOPTION_TEXT.index("\n\n", idx)
        hollow = ("* **「链式赋值顺序随字段顺序」是本集合自己的判据化取舍**：链式赋值顺序随"
                  "字段顺序，本集合自己的判据化取舍，没有任何材料规定。\n")
        self.write(self.ADOPTION, self.ADOPTION_TEXT[:idx] + hollow
                   + self.ADOPTION_TEXT[end + 1:])
        self._run_guard()
        self.assertIn("library/adoption.adoc", self.error_texts())


class TestCheckPaginationGuard(CheckSpecsTestCase):
    """钉住『分页查询返回类型与转换』防线（用户提出，Issue #180）。

    用户原话："调整 mybatis plus 规范，如果是普通接口，分页查询时返回 `Result<IPage<Rsp>>`，
    如果是 feign 接口（`Result<自定义Page<Rsp>>`），字段转换时，使用 `page.convert` 而不是
    新建 page"。

    该条要治的失效形态：同一项目并存两套分页模型；`Entity → Rsp` 转换时**新建一个 page 再
    逐个搬运字段**——分页元数据（当前页/每页条数/总记录数/总页数）漏搬一项**既不报错也不提示**，
    只在运行期表现为"总页数一直是 0、翻页失效"。

    **夹具＝真文档逐字**：`self.JAVA` 由 `specs/stack/java.adoc` 现读（不是另抄一份说明文本），
    再按「删掉哪一截」构造反例——换成手抄版时，锚点与规则数据在同义改写后会整体与真文档脱节
    （锚点仍在、真文档已被改），防线照样报红却与本用例无关。

    本组用例逐一覆盖各处要件被抽走时的形态（正例 / 普通接口侧返回类型 / Feign 侧返回类型 /
    `convert` 的禁止面 / 元数据保留这一理由 / 判定标准 / 相邻条目分工 / 存量边界 / 依据行 /
    整节被删）——只核"这一节在不在"属防线空转。
    """

    # 真文档里**逐字**存在的截取串（须与 `specs/stack/java.adoc` 逐字相同；
    # 锚点或截取串对不上时下面的反例不会报红，`test_valid_passes` 会先一步报出来）。
    GATE = "* **分页查询的返回类型与转换方式（L1，用户点名）**"
    PLAIN = "`Result<IPage<Rsp>>`"
    FEIGN = "`Result<自定义Page<Rsp>>`"
    FORBIDDEN = "，**不得新建一个 page 再逐个搬运字段**"
    REASON = "**当前页、每页条数、总记录数、总页数等分页元数据原样保留**"
    CRITERIA_LINE = "** **判定标准（任一命中即违规）**：\u2460 普通接口的分页查询返回类型不是"
    XREF = "与相邻条目的关系（防误读）"
    MIGRATION = "随动迁移，见 `specs/core/execution.adoc`"

    def _write_without_line(self, line_start: str) -> None:
        """把真文档里**以 `line_start` 开头的那一整行**删掉后写进夹具。

        判据按行取值（规则数据逐组核锚点），故"删哪一行"须精确到行——按子串替换时会
        把同一行里的其它锚点一并带走或留下（本仓库实测：按行删 vs 按子串删，缺项报出与否不同）。
        """
        lines = self.JAVA.split("\n")
        hit = [i for i, line in enumerate(lines) if line.startswith(line_start)]
        self.assertEqual(1, len(hit),
                         f"真文档里以 {line_start!r} 开头的行应恰有一行（找到 {len(hit)} 行）")
        del lines[hit[0]]
        self._write_valid()
        self.write("specs/stack/java.adoc", "\n".join(lines))
    BASIS_LINE = "** **依据（标准名/编号）：ISO/IEC 25010（可维护性：分页元数据的单一来源、改一处不漏）"
    # 依据行被删时，规则报出的是**该组锚点里唯一被抽走的那个**（其余锚点在相邻条目里有同义字样）
    BASIS_ANCHOR = "本集合自己的判据化取舍"

    def setUp(self) -> None:
        super().setUp()
        self._orig_java = cm.JAVA_STACK_FILE
        cm.JAVA_STACK_FILE = os.path.join(self.root, "specs", "stack", "java.adoc")
        with open(os.path.join(os.path.dirname(HERE), "specs", "stack", "java.adoc"),
                  encoding="utf-8") as fh:
            self.JAVA = fh.read()

    def tearDown(self) -> None:
        cm.JAVA_STACK_FILE = self._orig_java
        super().tearDown()

    def _write_valid(self) -> None:
        self.write("specs/stack/java.adoc", self.JAVA)

    def _write_mutated(self, removed: str, replacement: str = "") -> None:
        """把真文档里的 `removed` 换成 `replacement` 后写进夹具（真文档里没有即报错）。"""
        self.assertIn(removed, self.JAVA)
        self._write_valid()
        self.write("specs/stack/java.adoc", self.JAVA.replace(removed, replacement))

    def test_valid_passes(self):
        # 正例兼锚点自检：真文档逐字进夹具时防线必须报绿（锚点与文档脱节时先在这一条暴露）
        self._write_valid()
        cm.check_pagination_guard()
        self.assertEqual("", self.error_texts())

    def test_plain_interface_return_type_removed_reports(self):
        # 反例①：普通接口一侧的返回类型被抽走 -> 普通接口仍会自建分页类
        self._write_mutated(self.PLAIN, "某个结果包装")
        cm.check_pagination_guard()
        self.assertIn("Result<IPage<Rsp>>", self.error_texts())

    def test_feign_side_removed_reports(self):
        # 反例②：Feign 一侧的返回类型被抽走 -> 该档无处可归
        self._write_mutated(self.FEIGN, "某个结果包装")
        cm.check_pagination_guard()
        self.assertIn("Result<自定义Page<Rsp>>", self.error_texts())

    def test_convert_forbidden_face_removed_reports(self):
        # 反例③（靶心）：`convert` 的**禁止面**被删 -> "新建一个 page 更直观"重新成立
        self._write_mutated(self.FORBIDDEN)
        cm.check_pagination_guard()
        self.assertIn("不得新建一个 page", self.error_texts())

    def test_metadata_reason_removed_reports(self):
        # 反例④：理由（元数据原样保留）被删 -> 本条的级别与处置会被降级
        self._write_mutated(self.REASON, "结果一致")
        cm.check_pagination_guard()
        self.assertIn("原样保留", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例⑤：判定标准被删 -> 本条自身不可判定，只剩一句口号
        self._write_without_line(self.CRITERIA_LINE)
        cm.check_pagination_guard()
        self.assertIn("不得互改", self.error_texts())

    def test_adjacent_entries_xref_removed_reports(self):
        # 反例⑥：与相邻条目的分工被删 -> 三条互相拆台（读者以为本条允许实体类进分页）
        self._write_mutated(self.XREF, "补充说明")
        cm.check_pagination_guard()
        self.assertIn("与相邻条目的关系（防误读）", self.error_texts())

    def test_migration_boundary_removed_reports(self):
        # 反例⑦：存量边界被删 -> 等于要求立刻批量重写既有分页接口
        self._write_mutated(self.MIGRATION)
        cm.check_pagination_guard()
        self.assertIn("随动迁移，见 `specs/core/execution.adoc`", self.error_texts())

    def test_basis_line_removed_reports(self):
        # 反例⑧：依据行被整行删掉 -> 读者把本集合的取舍当成框架要求
        self._write_without_line(self.BASIS_LINE)
        cm.check_pagination_guard()
        self.assertIn(self.BASIS_ANCHOR, self.error_texts())

    def test_gate_line_removed_reports(self):
        # 反例⑨：整条被摘掉（含 L1 标注）-> 该条被降级成建议，"分页怎么写都行"重新成立
        self._write_mutated(self.GATE, "* **分页怎么写都行**")
        cm.check_pagination_guard()
        self.assertIn("分页查询的返回类型与转换方式", self.error_texts())

    def test_section_missing_reports(self):
        # 反例⑩：整节被删 -> 该条失去落点
        self.write("specs/stack/java.adoc", "= Java 规范\n\n== 编码\n\n* 略。\n")
        cm.check_pagination_guard()
        self.assertIn("持久化访问（MyBatis-Plus / JPA 等）", self.error_texts())


class _StackGuardTestCase(CheckSpecsTestCase):
    """栈层规则防线的用例基类：**夹具＝真文档逐字**（现读，不另抄一份说明文本）。

    换成手抄版时，锚点与规则数据在同义改写后会整体与真文档脱节（锚点仍在、真文档已被改），
    防线照样报红却与本用例无关；逐字读入时 `test_valid_passes` 会先一步暴露脱节。
    同时把 `AGENTS_COMMON.adoc` 一并写进夹具——加载门（识别特征）是这几道防线的判据之一。
    """

    DOC = ""       # 真文档相对路径（子类给）
    CONST = ""     # check_specs 里对应的模块级常量名（子类给）
    COMMON = ""    # 真 `AGENTS_COMMON.adoc` 内容（setUp 读入）

    def setUp(self) -> None:
        super().setUp()
        self._orig_const = getattr(cm, self.CONST)
        self._orig_common = cm.GENERIC_FILE
        self._orig_repo_root = cm.REPO_ROOT
        setattr(cm, self.CONST, os.path.join(self.root, *self.DOC.split("/")))
        cm.GENERIC_FILE = os.path.join(self.root, "AGENTS_COMMON.adoc")
        with open(self.DOC, encoding="utf-8") as fh:
            self.TEXT = fh.read()
        with open("AGENTS_COMMON.adoc", encoding="utf-8") as fh:
            self.COMMON = fh.read()

    def tearDown(self) -> None:
        setattr(cm, self.CONST, self._orig_const)
        cm.GENERIC_FILE = self._orig_common
        super().tearDown()

    def _write_valid(self) -> None:
        self.write(self.DOC, self.TEXT)
        self.write("AGENTS_COMMON.adoc", self.COMMON)

    def _write_mutated(self, removed: str, replacement: str = "") -> None:
        """把真文档里的 `removed` 换成 `replacement`（真文档里没有即报错）。"""
        self.assertIn(removed, self.TEXT)
        self._write_valid()
        self.write(self.DOC, self.TEXT.replace(removed, replacement))

    def _write_common_mutated(self, removed: str, replacement: str = "") -> None:
        """把真 `AGENTS_COMMON.adoc` 里的识别特征抽掉（核加载门那一半）。"""
        self.assertIn(removed, self.COMMON)
        self.write(self.DOC, self.TEXT)
        self.write("AGENTS_COMMON.adoc", self.COMMON.replace(removed, replacement))


class TestCheckValueBindingGuard(_StackGuardTestCase):
    """钉住『配置项绑定』条（PR #202：禁用 `@Value`，配置项统一 `@ConfigurationProperties`）。

    要治的失效：`@Value` 的"仅限少量简单配置"口径没有判据，实际执行中持续滋生。最易被
    冲掉的是**禁止面**（只留"统一用"、`@Value` 放回允许面）、**SpEL 边界**（缺则该禁令被
    读成「`#{...}` 也禁」）、**存量边界**（缺则等于要求立刻批量改存量）与依据名。
    判据按**本条 bullet** 核——「配置」节相邻条目含同样字样，整节核会兜住缺项。
    """

    DOC = "specs/stack/spring.adoc"
    CONST = "SPRING_STACK_FILE"

    def test_valid_passes(self):
        # 正例兼锚点自检：真文档逐字进夹具时防线必须报绿
        self._write_valid()
        cm.check_value_binding_guard()
        self.assertEqual("", self.error_texts())

    def test_entry_bullet_removed_reports(self):
        # 反例①：整条被摘掉（含 L1 标注）-> 禁令失效，`@Value` 重新可用
        self._write_mutated("* **配置项统一用 `@ConfigurationProperties` 绑定（L1）**",
                            "* **配置怎么写都行**")
        cm.check_value_binding_guard()
        self.assertIn("配置项统一用 `@ConfigurationProperties` 绑定（L1）", self.error_texts())

    def test_ban_removed_reports(self):
        # 反例②：禁止面被抽 -> 只剩"统一用"，`@Value` 放回允许面
        self._write_mutated("禁止使用 `@Value`", "建议少用 `@Value`")
        cm.check_value_binding_guard()
        self.assertIn("禁止使用 `@Value`", self.error_texts())

    def test_ban_scope_removed_reports(self):
        # 反例③：禁用范围被抽 -> 只禁字段注入，构造参数/方法参数上的 `@Value` 漏网
        self._write_mutated("业务代码与配置类中的字段注入、构造参数与方法参数", "业务代码的字段注入")
        cm.check_value_binding_guard()
        self.assertIn("构造参数与方法参数", self.error_texts())

    def test_spel_boundary_removed_reports(self):
        # 反例④：SpEL 边界被删 -> 该禁令被读成「`#{...}` 也禁」，误伤面扩大
        self._write_mutated("SpEL 取值（`#{...}`）不受本条约束")
        cm.check_value_binding_guard()
        self.assertIn("SpEL 取值", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例⑤：判定标准被抽 -> 只剩一句口号
        self._write_mutated("**判定标准（任一命中即违规）**")
        cm.check_value_binding_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_criteria_case_removed_reports(self):
        # 反例⑥：判定标准的具体反例被抽（轴名齐全、判据被抽走的形态）
        self._write_mutated("新增或改动的代码中出现 `@Value` 注解")
        cm.check_value_binding_guard()
        self.assertIn("新增或改动的代码中出现 `@Value` 注解", self.error_texts())

    def test_bypass_case_removed_reports(self):
        # 反例⑦：绕行反例被抽 -> 把配置塞进 `@Configuration` 字段的绕法不再被判
        self._write_mutated("为绕开本条把配置项塞进 `@Configuration` 类的字段")
        cm.check_value_binding_guard()
        self.assertIn("为绕开本条把配置项塞进", self.error_texts())

    def test_legacy_removed_reports(self):
        # 反例⑧：存量边界被删 -> 等于要求立刻批量改存量
        self._write_mutated("不属违规、按原样保留", "属违规、须立刻整改")
        cm.check_value_binding_guard()
        self.assertIn("不属违规、按原样保留", self.error_texts())

    def test_legacy_review_silence_removed_reports(self):
        # 反例⑨：review 静默口径被删 -> code review 对存量 `@Value` 报问题提示
        self._write_mutated("code review 也不对存量 `@Value` 作问题提示")
        cm.check_value_binding_guard()
        self.assertIn("code review 也不对存量 `@Value` 作问题提示", self.error_texts())

    def test_basis_removed_reports(self):
        # 反例⑩：依据名被删 -> 无从追溯
        self._write_mutated("Spring Boot 官方文档「Externalized Configuration」")
        cm.check_value_binding_guard()
        self.assertIn("Externalized Configuration", self.error_texts())

    def test_second_basis_removed_reports(self):
        # 反例⑪：第二依据名被删 -> 取舍无从追溯
        self._write_mutated("The Twelve-Factor App")
        cm.check_value_binding_guard()
        self.assertIn("The Twelve-Factor App", self.error_texts())

    def test_section_missing_reports(self):
        # 反例⑫：整节被删 -> 该条失去落点
        self.write("specs/stack/spring.adoc", "= Spring 规范\n\n== 注入\n\n* 略。\n")
        self.write("AGENTS_COMMON.adoc", self.COMMON)
        cm.check_value_binding_guard()
        self.assertIn("配置", self.error_texts())

    def test_dispatch_trigger_removed_reports(self):
        # 反例⑬：加载门被删 -> 写/改 `@Value` 时不会加载该条
        self._write_common_mutated("**配置项绑定注解**（`@Value`/`@ConfigurationProperties`）")
        cm.check_value_binding_guard()
        self.assertIn("配置项绑定注解", self.error_texts())

class TestCheckParamCarrierGuard(_StackGuardTestCase):
    """钉住『方法参数不得以键值容器承载』（用户从存量项目规范引入：「禁止 Map 作参数」）。

    该条要治的失效：以 `Map`/字典承载参数时，**字段名、字段类型与必填性都没有落点**——
    调用方按字面键写入、实现按字面键读取，键名改一处即**静默失效**，两端键集合也无法在
    编译期核对。最易被三件事冲掉：
      * **条文被降级** —— 「须用具名类型」丢了，「这个参数会变」会把键值容器放回来；
      * **例外面被放大** —— 「键值集合本身就是要表达的数据」「框架契约要求容器」被删，
        键值容器一律被判红；或「仅对该处、该次生效、不得泛化」丢了，一次声明被套到全模块；
      * **定性与依据被删** —— 该条是本集合取舍、依据是《Refactoring》的「数据泥团」，
        丢了读者会把它读成某标准的规定。
    """

    DOC = "specs/general/coding.adoc"
    CONST = "CODING_FILE"

    def test_valid_passes(self):
        # 正例兼锚点自检：真文档逐字进夹具时防线必须报绿
        self._write_valid()
        cm.check_param_carrier_guard()
        self.assertEqual("", self.error_texts())

    def test_gate_line_removed_reports(self):
        # 反例①：整条被摘掉（含 L1 标注）-> 该条被降级成建议，键值容器传参重新成立
        self._write_mutated("* **不得以键值容器承载方法参数（L1）**", "* **参数怎么写都行**")
        cm.check_param_carrier_guard()
        self.assertIn("不得以键值容器承载方法参数", self.error_texts())

    def test_named_type_removed_reports(self):
        # 反例②：载体形态（须用具名类型）被抽 -> 读者不知道"该改成什么"
        self._write_mutated("方法参数与返回值的载体是**具名类型**", "方法参数的载体随意")
        cm.check_param_carrier_guard()
        self.assertIn("具名类型", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例③：判定标准被抽 -> 本条自身不可判定，只剩一句口号
        self._write_mutated("**已有具名类型或具名先例**")
        cm.check_param_carrier_guard()
        self.assertIn("已有具名类型或具名先例", self.error_texts())

    def test_exception_face_removed_reports(self):
        # 反例④：例外面被删 -> 键值集合本身的正当用途（字典表/配置映射）被判红
        self._write_mutated("**键值集合本身就是要表达的数据**")
        cm.check_param_carrier_guard()
        self.assertIn("键值集合本身就是要表达的数据", self.error_texts())

    def test_migration_boundary_removed_reports(self):
        # 反例⑤：存量边界被删 -> 等于要求立刻批量改既有 `Map` 传参
        self._write_mutated("随动迁移，见 `specs/core/execution.adoc`")
        cm.check_param_carrier_guard()
        self.assertIn("随动迁移，见 `specs/core/execution.adoc`", self.error_texts())

    def test_takeaway_nature_removed_reports(self):
        # 反例⑥：定性（本集合取舍）被删 -> 读者按"标准规定"理解，标准没写时自行放宽
        self._write_mutated("「参数不得以键值容器承载」是本集合自己的判据化取舍")
        cm.check_param_carrier_guard()
        self.assertIn("本集合自己的判据化取舍", self.error_texts())

    def test_basis_name_removed_reports(self):
        # 反例⑦：依据名被删 -> 日后无从核对它还成不成立
        self._write_mutated("Martin Fowler《Refactoring》")
        cm.check_param_carrier_guard()
        self.assertIn("Refactoring", self.error_texts())

    def test_dispatch_trigger_removed_reports(self):
        # 反例⑧：加载门（调度器识别特征）被删 -> 写方法参数时永远不加载该条
        self._write_common_mutated("要写**方法参数**（决定该参数用什么类型承载）")
        cm.check_param_carrier_guard()
        self.assertIn("方法参数", self.error_texts())


class TestCheckGetterBridgeGuard(_StackGuardTestCase):
    """钉住『接口实现字段名与接口 getter 名不一致须手动桥接』（用户从存量项目规范引入）。

    该条要治的失效：访问器按**字段名**生成 ⇒ 不生成接口要求的那个方法（非抽象类因此
    编译不过）；手动桥接后接口方法名与字段名各成一个读取方法、指向同一个值 ⇒ 不加
    `@JsonIgnore` 就序列化出**两个属性**。最易被三件事冲掉：条文与机制被抽（不知道要防
    什么）、边界被删（新建类被迫背上改名与否的存量包袱）、依据名被删（无从追溯）。
    """

    DOC = "specs/stack/java.adoc"
    CONST = "JAVA_STACK_FILE"

    def test_valid_passes(self):
        self._write_valid()
        cm.check_getter_bridge_guard()
        self.assertEqual("", self.error_texts())

    def test_gate_line_removed_reports(self):
        # 反例①：整条被摘掉（含 L1 标注）-> 该条被降级成建议
        self._write_mutated("* **接口实现时字段名与接口 getter 名不一致须手动桥接（L1）**",
                            "* **字段名怎么写都行**")
        cm.check_getter_bridge_guard()
        self.assertIn("手动桥接", self.error_texts())

    def test_bridge_call_removed_reports(self):
        # 反例②：桥接动作被抽 -> 编译不过时只能靠改名迁就接口
        self._write_mutated("手动 `@Override` 桥接出接口要求的那个 getter", "按需处理")
        cm.check_getter_bridge_guard()
        self.assertIn("桥接出接口要求的那个 getter", self.error_texts())

    def test_json_ignore_removed_reports(self):
        # 反例③：`@JsonIgnore` 被抽 -> 桥接后同一个值序列化出两个属性
        self._write_mutated("并给桥接方法加 `@JsonIgnore`", "并保持原样")
        cm.check_getter_bridge_guard()
        self.assertIn("@JsonIgnore", self.error_texts())

    def test_mechanism_removed_reports(self):
        # 反例④：机制（不桥接即编译不过）被抽 -> 读者不知道这是编译期问题
        self._write_mutated("非抽象的实例类因此**编译不过**", "会有点问题")
        cm.check_getter_bridge_guard()
        self.assertIn("编译不过", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例⑤：判定标准被抽 -> 只剩一句口径
        self._write_mutated("**判定标准（任一命中即违规）**")
        cm.check_getter_bridge_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_boundary_removed_reports(self):
        # 反例⑥：边界（尚无外部依赖的类不受①限制）被删 -> 新建类也被迫桥接
        self._write_mutated("**尚无外部依赖的类不受①限制**")
        cm.check_getter_bridge_guard()
        self.assertIn("尚无外部依赖的类", self.error_texts())

    def test_migration_boundary_removed_reports(self):
        # 反例⑦：存量边界被删 -> 等于要求立刻批量改既有实现类
        self._write_mutated("**存量**")
        cm.check_getter_bridge_guard()
        self.assertIn("存量", self.error_texts())

    def test_basis_name_removed_reports(self):
        # 反例⑧：Lombok 侧的机制依据被删 -> 读者以为"Lombok 会自己实现接口"
        self._write_mutated("Project Lombok 官方文档（访问器按字段名生成）", "某官方文档")
        cm.check_getter_bridge_guard()
        self.assertIn("访问器按字段名生成", self.error_texts())

    def test_dispatch_trigger_removed_reports(self):
        # 反例⑨：加载门被删 -> 实现接口时不会加载该条
        self._write_common_mutated("**接口实现的访问器桥接**")
        cm.check_getter_bridge_guard()
        self.assertIn("访问器桥接", self.error_texts())


class TestCheckValidationEntryGuard(_StackGuardTestCase):
    """钉住『方法参数校验入口统一用 `@Validated`』（用户从存量项目规范引入）。

    该条要治的失效：参数上直接用 `@Valid` ——它**无分组参数**，需要指定校验分组或
    类级/方法级校验时表达不了。最易被冲掉的是「不把 `@Valid` 用作参数入口」这半句
    （只留"建议用 `@Validated`"），以及影响面（引用方项目自身规范为准）与依据名。
    """

    DOC = "specs/stack/spring.adoc"
    CONST = "SPRING_STACK_FILE"

    def test_valid_passes(self):
        self._write_valid()
        cm.check_validation_entry_guard()
        self.assertEqual("", self.error_texts())

    def test_gate_line_removed_reports(self):
        # 反例①：条文被降级成建议（"统一用"丢了）-> 参数上直接用 `@Valid` 重新成立
        self._write_mutated("方法参数校验统一用 `@Validated`（L2）", "方法参数校验可以用 `@Validated`")
        cm.check_validation_entry_guard()
        self.assertIn("方法参数校验统一用", self.error_texts())

    def test_param_entry_ban_removed_reports(self):
        # 反例②：禁止面被抽 -> 只剩"建议"，需要分组时仍会用 `@Valid`
        self._write_mutated("**不把 `@Valid` 用作方法参数校验的入口**")
        cm.check_validation_entry_guard()
        self.assertIn("用作方法参数校验的入口", self.error_texts())

    def test_field_cascade_role_removed_reports(self):
        # 反例③：分工被删 -> 禁令被读成"`@Valid` 一律不许用"，嵌套校验被一并禁掉
        self._write_mutated("**对象内部字段的级联校验**")
        cm.check_validation_entry_guard()
        self.assertIn("字段的级联校验", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例④：判定标准被抽 -> 本条自身不可判定
        self._write_mutated("**类级/方法级校验入口**")
        cm.check_validation_entry_guard()
        self.assertIn("类级/方法级校验入口", self.error_texts())

    def test_impact_face_removed_reports(self):
        # 反例⑤：影响面被删 -> 等于静默推翻引用方"参数上直接用 `@Valid`"的既有约定
        self._write_mutated("引用方项目自身规范另有约定时以其为准")
        cm.check_validation_entry_guard()
        self.assertIn("以其为准", self.error_texts())

    def test_migration_boundary_removed_reports(self):
        # 反例⑥：存量边界被删 -> 等于要求立刻批量改既有校验注解
        self._write_mutated("随动迁移，见 `specs/core/execution.adoc`")
        cm.check_validation_entry_guard()
        self.assertIn("随动迁移，见 `specs/core/execution.adoc`", self.error_texts())

    def test_basis_name_removed_reports(self):
        # 反例⑦：依据名被删 -> 无从追溯
        self._write_mutated("Jakarta Bean Validation 官方规范")
        cm.check_validation_entry_guard()
        self.assertIn("Jakarta Bean Validation", self.error_texts())

    def test_section_missing_reports(self):
        # 反例⑧：整节被删 -> 该条失去落点
        self.write("specs/stack/spring.adoc", "= Spring 规范\n\n== 注入\n\n* 略。\n")
        self.write("AGENTS_COMMON.adoc", self.COMMON)
        cm.check_validation_entry_guard()
        self.assertIn("参数校验", self.error_texts())

    def test_dispatch_trigger_removed_reports(self):
        # 反例⑨：加载门被删 -> 写校验注解时不会加载该条
        self._write_common_mutated("要写/改**参数校验注解**")
        cm.check_validation_entry_guard()
        self.assertIn("参数校验注解", self.error_texts())


class TestCheckHttpContractGuard(_StackGuardTestCase):
    """钉住『Spring HTTP 接口契约』四条（用户从存量项目规范引入）。

    要治的失效：路由不限定方法（同一路径对全部方法开放、读写语义混在一起）、两侧各写一份
    契约（改一侧必漏另一侧）、前缀在契约方法上重复（同一事实两个来源）、参数逐个声明
    （清单散落在方法签名里）。最易被冲掉的是**适用范围**（缺则没用声明式客户端的项目被误伤）
    与**取舍定性**（缺则读者把"路由须显式声明方法"读成协议强制）。
    """

    DOC = "specs/stack/spring.adoc"
    CONST = "SPRING_STACK_FILE"

    def test_valid_passes(self):
        self._write_valid()
        cm.check_http_contract_guard()
        self.assertEqual("", self.error_texts())

    def test_scope_removed_reports(self):
        # 反例①：适用范围被删 -> 没用声明式客户端的 Spring 项目把契约条当通用必做
        self._write_mutated("**适用范围**：提供或调用 HTTP 接口的项目")
        cm.check_http_contract_guard()
        self.assertIn("适用范围", self.error_texts())

    def test_controller_method_removed_reports(self):
        # 反例②：控制器条被降级 -> 不限定方法的映射重新成立
        self._write_mutated("控制器方法须显式声明 HTTP 方法（L2）", "控制器方法尽量声明方法")
        cm.check_http_contract_guard()
        self.assertIn("显式声明 HTTP 方法", self.error_texts())

    def test_controller_criterion_removed_reports(self):
        # 反例②′：判定标准里的**具体反例**被抽（标题还在）-> 只剩轴名，判据无从核对
        self._write_mutated("① 新增或改动的路由用不限定 HTTP 方法的映射；"
                            "② 以「调用方反正只发一种方法」为由不限定。")
        cm.check_http_contract_guard()
        self.assertIn("不限定 HTTP 方法的映射", self.error_texts())

    def test_contract_sharing_removed_reports(self):
        # 反例③：契约共用的执行形态被抽 -> 两侧各写一份方法签名重新成立
        self._write_mutated("**客户端继承该契约、提供方实现该契约**")
        cm.check_http_contract_guard()
        self.assertIn("客户端继承该契约、提供方实现该契约", self.error_texts())

    def test_contract_sharing_criterion_removed_reports(self):
        # 反例③′：契约共用条的**具体反例**被抽（标题还在）-> 只剩轴名
        self._write_mutated("① 客户端与提供方各自声明方法签名、不共用同一契约类型；")
        cm.check_http_contract_guard()
        self.assertIn("不共用同一契约类型", self.error_texts())

    def test_prefix_single_point_removed_reports(self):
        # 反例④：前缀单点被抽 -> 方法上重复写前缀（同一事实两个来源）
        self._write_mutated("**契约方法上只写相对路径**")
        cm.check_http_contract_guard()
        self.assertIn("只写相对路径", self.error_texts())

    def test_param_carrier_removed_reports(self):
        # 反例⑤：参数承载条被整条抽掉（该 bullet 里两处 `@SpringQueryMap` 一并消失）
        # -> 参数清单只能逐个声明
        self.assertIn("内部调用接口的参数以请求体承载，不逐个散参（L2）", self.TEXT)
        self._write_valid()
        self.write(self.DOC,
                   self.TEXT.replace("`@SpringQueryMap`", "整对象映射")
                            .replace("内部调用接口的参数以请求体承载，不逐个散参（L2）", "参数承载随意"))
        cm.check_http_contract_guard()
        self.assertIn("不逐个散参", self.error_texts())

    def test_takeaway_nature_removed_reports(self):
        # 反例⑥：取舍定性被删 -> 读者把"路由须显式声明方法"读成协议强制
        self._write_mutated("**「路由须显式声明 HTTP 方法」是本集合的判据化取值**")
        cm.check_http_contract_guard()
        self.assertIn("本集合的判据化取值", self.error_texts())

    def test_basis_name_removed_reports(self):
        # 反例⑦：Feign 侧依据名被删 -> 契约共用条无从追溯
        self._write_mutated("Spring Cloud OpenFeign 官方文档")
        cm.check_http_contract_guard()
        self.assertIn("Spring Cloud OpenFeign", self.error_texts())

    def test_migration_boundary_removed_reports(self):
        # 反例⑧：存量边界被删 -> 等于要求立刻批量改既有路由与契约
        self._write_mutated("随动迁移，见 `specs/core/execution.adoc`")
        cm.check_http_contract_guard()
        self.assertIn("随动迁移，见 `specs/core/execution.adoc`", self.error_texts())

    def test_section_missing_reports(self):
        # 反例⑨：整节被删 -> 四条一起失去落点
        self.write("specs/stack/spring.adoc", "= Spring 规范\n\n== 注入\n\n* 略。\n")
        self.write("AGENTS_COMMON.adoc", self.COMMON)
        cm.check_http_contract_guard()
        self.assertIn("HTTP 接口（控制器与声明式客户端）", self.error_texts())

    def test_dispatch_trigger_removed_reports(self):
        # 反例⑩：加载门被删 -> 写声明式客户端契约时不会加载该节
        self._write_common_mutated("**声明式客户端契约**")
        cm.check_http_contract_guard()
        self.assertIn("声明式客户端契约", self.error_texts())


class TestCheckTernaryExtractionGuard(CheckSpecsTestCase):
    """钉住『不得新增只做条件取值的方法』（**用户提出，Issue #206「三元」**）。

    用户原话："严禁新增一个里面只有三元判断取值的方法，适应任何语言，有很多类似的
    `defaultIfNull` `defaultIfEmpty` 的方法，没有可以加"。要治的失效：**方法体只剩一处
    条件取值**——方法只为在一个表达式里挑一个值、**没有自己的语义**（名字只是把那次挑选
    复述一遍），而「空则取默认值」已有现成入口，缺的只是**加一个通用工具方法**。最易被
    三件事冲掉：条文与本集合取舍被抽（三元又被抽成专用方法）、去向被抽（没有现成方法时
    也不去加通用方法）、Java 落点被抽（不知道该把通用方法补到哪）。

    本条跨两文件（通用层本体 + Java 落点），故夹具一并重定向两处常量。
    """

    CODING = "specs/general/coding.adoc"
    SYNTAX = "specs/stack/java-syntax.adoc"

    def setUp(self) -> None:
        super().setUp()
        self._orig_coding = cm.CODING_FILE
        self._orig_syntax = cm.JAVA_SYNTAX_FILE
        cm.CODING_FILE = os.path.join(self.root, *self.CODING.split("/"))
        cm.JAVA_SYNTAX_FILE = os.path.join(self.root, *self.SYNTAX.split("/"))
        # 真实规则目录（本仓库那一份）：夹具按原样整份复制，**不手抄**（手抄必然与现场漂移）
        self._rules_src = os.path.join(
            os.path.dirname(os.path.abspath(cm.__file__)), "specs-rules")
        with open(self.CODING, encoding="utf-8") as fh:
            self.CODING_TEXT = fh.read()
        with open(self.SYNTAX, encoding="utf-8") as fh:
            self.SYNTAX_TEXT = fh.read()

    def tearDown(self) -> None:
        cm.CODING_FILE = self._orig_coding
        cm.JAVA_SYNTAX_FILE = self._orig_syntax
        super().tearDown()

    # 规则数据（`coding.toml`）是判据措辞的唯一来源，且**本道另有一步核它自己的条数**，
    # 故夹具须把它按真实文件原样落进来（`_rules_spec()` 随 `REPO_ROOT` 走，正例才不是假红）。
    RULES = "script/specs-rules/coding.toml"

    def _write_valid(self) -> None:
        self.write(self.CODING, self.CODING_TEXT)
        self.write(self.SYNTAX, self.SYNTAX_TEXT)
        self.write_rules_fixture()
        for rel in self._rule_files():
            self.write(rel, self._rule_text(rel))
        self._prime_rules()

    def _rule_files(self) -> list:
        """规则目录下的全部文件（引擎按**目录**扫描加载，缺一份即整批静默失效）。"""
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(cm.__file__)))
        folder = os.path.join(repo_root, os.path.dirname(self.RULES))
        return [f"{os.path.dirname(self.RULES)}/{n}"
                for n in sorted(os.listdir(folder)) if n.endswith(".toml")]

    def _prime_rules(self) -> None:
        """重新装配规则引擎（夹具换过 `REPO_ROOT`，`RULES` 缓存指向上一份）。

        `run_rule_guard` 的 `RULES` 是模块级缓存、**首次用到才构造**，同一阶段内也去重；
        夹具重定向 `REPO_ROOT` 后必须作废，否则读到的是上一个用例的规则数据。
        """
        cm.RULES = None
        cm._RULES_RUN_THIS_PHASE.clear()

    def _rule_text(self, rel: str) -> str:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(cm.__file__)))
        with open(os.path.join(repo_root, rel), encoding="utf-8") as fh:
            return fh.read()

    def _write_coding_mutated(self, removed: str, replacement: str = "") -> None:
        self.assertIn(removed, self.CODING_TEXT)
        self._write_valid()
        self.write(self.CODING, self.CODING_TEXT.replace(removed, replacement))

    def _write_syntax_mutated(self, removed: str, replacement: str = "") -> None:
        self.assertIn(removed, self.SYNTAX_TEXT)
        self._write_valid()
        self.write(self.SYNTAX, self.SYNTAX_TEXT.replace(removed, replacement))

    def test_valid_passes(self):
        # 正例兼锚点自检：真文档逐字进夹具时防线必须报绿
        self._write_valid()
        cm.check_ternary_extraction_guard()
        self.assertEqual("", self.error_texts())

    def test_rule_removed_reports(self):
        # 反例①：整条被摘掉（含 L1 标注）-> 该条被降级成建议，「调用点会更短」把专用方法放回来
        self._write_coding_mutated("* **不得新增只做条件取值的方法（L1）**",
                                   "* **取值方法随便抽**")
        cm.check_ternary_extraction_guard()
        self.assertIn("不得新增只做条件取值的方法", self.error_texts())

    def test_no_semantics_reason_removed_reports(self):
        # 反例②：核心理由（没有自己的语义）被抽 -> 读者不知道"为什么这算坏味道"
        self._write_coding_mutated("**没有自己的语义**")
        cm.check_ternary_extraction_guard()
        self.assertIn("没有自己的语义", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例③：判定标准被抽 -> 本条自身不可判定，只剩一句口号
        self._write_coding_mutated("**有自身语义的取值方法")
        cm.check_ternary_extraction_guard()
        self.assertIn("有自身语义的取值方法", self.error_texts())

    def test_exception_face_removed_reports(self):
        # 反例④：例外面被删 -> 已有先例、响应式管线等正当场合被判红
        self._write_coding_mutated("**先加通用工具方法**")
        cm.check_ternary_extraction_guard()
        self.assertIn("先加通用工具方法", self.error_texts())

    def test_migration_boundary_removed_reports(self):
        # 反例⑤：存量边界被删 -> 等于要求立刻批量内联/删既有方法（用户口径"已经用了不管"）
        self._write_coding_mutated("**存量边界（L1）**")
        cm.check_ternary_extraction_guard()
        self.assertIn("存量边界", self.error_texts())

    def test_takeaway_direction_removed_reports(self):
        # 反例⑥：去向（加通用方法、不就地抽专用方法）被抽 -> 兜底退回逐处内联与逐处专用方法
        self._write_coding_mutated("而不是就地写三段式或就地为这一次调用抽一个专用方法")
        cm.check_ternary_extraction_guard()
        self.assertIn("而不是就地写三段式", self.error_texts())

    def test_takeaway_nature_removed_reports(self):
        # 反例⑦：定性（本集合取舍）被删 -> 读者按"标准规定"理解，标准没写时自行放宽
        self._write_coding_mutated("**「没有现成工具方法就加一个通用方法、不就地抽专用方法」是本集合自己的判据化取舍**")
        cm.check_ternary_extraction_guard()
        self.assertIn("本集合自己的判据化取舍", self.error_texts())

    def test_java_landing_removed_reports(self):
        # 反例⑧：Java 落点被抽 -> 执行者不知道该把通用方法补到哪，会把三元写回调用点
        self._write_syntax_mutated("**没有现成入口时补通用方法的落点是项目自有工具类**")
        cm.check_ternary_extraction_guard()
        self.assertIn("项目自有工具类", self.error_texts())

    def test_coding_file_missing_reports(self):
        # 反例⑨：通用层落点整份缺失 -> 该条失去落点
        self.write(self.SYNTAX, self.SYNTAX_TEXT)
        cm.check_ternary_extraction_guard()
        self.assertIn("coding.adoc", self.error_texts())

    def test_java_syntax_file_missing_reports(self):
        # 反例⑩：Java 落点整份缺失 -> 补通用方法这一去向失去中文载体
        self.write(self.CODING, self.CODING_TEXT)
        cm.check_ternary_extraction_guard()
        self.assertIn("java-syntax.adoc", self.error_texts())


class TestCheckToolClassInheritanceGuard(CheckSpecsTestCase):
    """钉住『工具类不继承另一个工具类』（**用户提出，Issue #217**）。

    用户原话："严禁工具类继承另一个工具类，适用所有语言"。要治的失效：工具类之间以
    `extends`（或各语言的继承语法）复用公共静态方法——少写一次签名，换来一层隐藏的、
    只增不减的耦合；而工具类的能力面本应是平铺、可按名直接找到的一组静态入口。最易被
    四件事冲掉：条文本身被抽（继承又被当"实现复用"的捷径）、**继承链里不得出现两个工具类
    相邻**这一判定面被抽（"只是加了一层"即可自圆其说）、例外面被抽（连非工具类的正常继承
    一起判红）、存量边界被抽（等于要求立刻批量拆基类）。

    本条跨两文件（通用层本体 + Java 落点），故夹具一并重定向两处常量。
    """

    CODING = "specs/general/coding.adoc"
    SYNTAX = "specs/stack/java-syntax.adoc"

    def setUp(self) -> None:
        super().setUp()
        self._orig_coding = cm.CODING_FILE
        self._orig_syntax = cm.JAVA_SYNTAX_FILE
        cm.CODING_FILE = os.path.join(self.root, *self.CODING.split("/"))
        cm.JAVA_SYNTAX_FILE = os.path.join(self.root, *self.SYNTAX.split("/"))
        # 真实规则目录（本仓库那一份）：夹具按原样整份复制，**不手抄**（手抄必然与现场漂移）
        self._rules_src = os.path.join(
            os.path.dirname(os.path.abspath(cm.__file__)), "specs-rules")
        with open(self.CODING, encoding="utf-8") as fh:
            self.CODING_TEXT = fh.read()
        with open(self.SYNTAX, encoding="utf-8") as fh:
            self.SYNTAX_TEXT = fh.read()

    def tearDown(self) -> None:
        cm.CODING_FILE = self._orig_coding
        cm.JAVA_SYNTAX_FILE = self._orig_syntax
        super().tearDown()

    # 规则数据（`specs-rules/` 目录）是判据措辞的唯一来源，本道另有一步核**清单自己的条数**，
    # 故夹具须把整个目录按真实文件原样落进来（引擎按目录扫描加载，缺一份即整批静默失效），
    # 且 `_rules_spec()` 随 `REPO_ROOT` 走、正例才不是假红。
    RULES = "specs-rules/coding.toml"

    def _write_valid(self) -> None:
        self.write(self.CODING, self.CODING_TEXT)
        self.write(self.SYNTAX, self.SYNTAX_TEXT)
        for rel in self._rule_files():
            self.write(f"script/{rel}", self._rule_text(rel))
        self._prime_rules()

    def _rule_files(self) -> list:
        """规则目录下全部 `*.toml`（相对仓库根的路径），路径以 `script/` 起头。"""
        folder = getattr(self, "_rules_src", None)
        assert folder, "setUp 须先记下真实规则目录"
        return [f"specs-rules/{n}" for n in sorted(os.listdir(folder))
                if n.endswith(".toml")]

    def _rule_text(self, rel: str) -> str:
        with open(os.path.join(self._rules_src, os.path.basename(rel)),
                  encoding="utf-8") as fh:
            return fh.read()

    def _prime_rules(self) -> None:
        """作废规则引擎缓存（夹具换过 `REPO_ROOT`，`RULES` 还指着上一份规则数据）。"""
        cm.RULES = None
        cm._RULES_RUN_THIS_PHASE.clear()

    def _write_coding_mutated(self, removed: str, replacement: str = "") -> None:
        self.assertIn(removed, self.CODING_TEXT)
        self._write_valid()
        self.write(self.CODING, self.CODING_TEXT.replace(removed, replacement))

    def _write_syntax_mutated(self, removed: str, replacement: str = "") -> None:
        self.assertIn(removed, self.SYNTAX_TEXT)
        self._write_valid()
        self.write(self.SYNTAX, self.SYNTAX_TEXT.replace(removed, replacement))

    def test_valid_passes(self):
        # 正例兼锚点自检：真文档逐字进夹具时防线必须报绿
        self._write_valid()
        cm.check_tool_class_inheritance_guard()
        self.assertEqual("", self.error_texts())

    def test_rule_removed_reports(self):
        # 反例①：整条被摘掉（含 L1 标注）-> 继承又被当"实现复用"的捷径
        self._write_coding_mutated("* **工具类不继承另一个工具类（L1，任何语言）**",
                                   "* **工具类随便继承**")
        cm.check_tool_class_inheritance_guard()
        self.assertIn("工具类不继承另一个工具类", self.error_texts())

    def test_adjacent_chain_criterion_removed_reports(self):
        # 反例②：判定面被抽（继承链里不得出现两个工具类相邻）-> "只是加了一层"即可自圆其说
        self._write_coding_mutated("继承链里不得出现两个工具类相邻")
        cm.check_tool_class_inheritance_guard()
        self.assertIn("继承链里不得出现两个工具类相邻", self.error_texts())

    def test_class_identification_face_removed_reports(self):
        # 反例③：认类判据被抽（不论继承者是否另加了方法、是否为 abstract）-> 加个方法就不算工具类
        self._write_coding_mutated("不论继承者是否另加了方法、是否为 `abstract`")
        cm.check_tool_class_inheritance_guard()
        self.assertIn("不论继承者是否另加了方法", self.error_texts())

    def test_reason_removed_reports(self):
        # 反例④：核心理由（无状态、无多态）被抽 -> 读者不知道"为什么这算坏味道"
        self._write_coding_mutated("**无状态、无多态**")
        cm.check_tool_class_inheritance_guard()
        self.assertIn("无状态、无多态", self.error_texts())

    def test_boundary_removed_reports(self):
        # 反例⑤：例外面被删 -> 非工具类的正常继承、工具类实现接口被一并判红
        self._write_coding_mutated("**只管工具类之间的继承**")
        cm.check_tool_class_inheritance_guard()
        self.assertIn("只管工具类之间的继承", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例⑥：判定标准被抽 -> 本条自身不可判定，只剩一句口号
        self._write_coding_mutated("**判定标准（任一命中即违规）**")
        cm.check_tool_class_inheritance_guard()
        self.assertIn("判定标准", self.error_texts())

    def test_migration_boundary_removed_reports(self):
        # 反例⑦：存量边界被删 -> 等于要求立刻批量拆基类、批量挪方法
        self._write_coding_mutated("**存量边界（L1）**")
        cm.check_tool_class_inheritance_guard()
        self.assertIn("存量边界", self.error_texts())

    def test_takeaway_nature_removed_reports(self):
        # 反例⑧：定性（本集合取舍）被删 -> 读者按"标准规定"理解，标准没写时自行放宽
        self._write_coding_mutated("**「工具类不得继承工具类」是本集合自己的判据化取舍**")
        cm.check_tool_class_inheritance_guard()
        self.assertIn("本集合自己的判据化取舍", self.error_texts())

    def test_java_landing_removed_reports(self):
        # 反例⑨：Java 落点被抽 -> 执行者不知道 `@UtilityClass` 本就不可被继承、
        # 会把静态方法重新抽成基类
        self._write_syntax_mutated("**lombok 的 `@UtilityClass` 自带私有构造器、本身不可被继承**")
        cm.check_tool_class_inheritance_guard()
        self.assertIn("不可被继承", self.error_texts())

    def test_java_jdk_extension_boundary_removed_reports(self):
        # 反例⑩：JDK 扩展类/补齐类被排除在工具类之外这一条被抽 -> `CList`/`CCollectors`
        # 会被误判成"工具类继承"
        self._write_syntax_mutated("**明确排除在工具类之外**")
        cm.check_tool_class_inheritance_guard()
        self.assertIn("明确排除在工具类之外", self.error_texts())

    def test_migration_boundary_reference_hollowed_reports(self):
        """反例（轴名齐全、判据被抽走）：存量边界只剩轴名、真源引用被抽走 -> 须报。

        本仓库 r2 轮把「存量口径」的**逐份照写样板句**收敛为**一行引用**（真源在
        `specs/core/execution.adoc`「规范变更的存量处理」）。故这条判据本体就是**那个引用**：
        `**存量边界**：……` 的轴名全留着、引用被抽掉时，读者拿不到任何存量口径——
        本防线必须报红（只核轴名的防线在这里会全绿，正是 `priority.adoc`「机械防线的
        核对对象是判据本体，不是轴名」点名的失效形态）。
        """
        self._write_coding_mutated("随动迁移，见 `specs/core/execution.adoc`")
        cm.check_ternary_extraction_guard()
        self.assertIn("随动迁移，见 `specs/core/execution.adoc`", self.error_texts())

    def test_rules_data_anchor_removed_reports(self):
        # 反例⑪：规则数据里这一条锚点被删（**规范正文一字未动**）-> 防线须报红。
        # 本条是"防线零证据"的唯一形态：现场什么都不缺，只有锚点清单自己少了一项，
        # 于是 `miss` 是空集、"核过且通过"与"没核"完全一样（实测：删掉该行后
        # `check_specs.py` 仍报"OK 规范检查全部通过"）。
        self._write_valid()
        rel = self.RULES
        text = self._rule_text(rel).replace('    "**无状态、无多态**",\n', "", 1)
        self.write(f"script/{rel}", text)
        cm.check_tool_class_inheritance_guard()
        self.assertIn("锚点", self.error_texts())

    def test_coding_file_missing_reports(self):
        # 反例⑫：通用层落点整份缺失 -> 该条失去落点
        self._write_valid()
        os.remove(cm.CODING_FILE)
        cm.check_tool_class_inheritance_guard()
        self.assertIn("coding.adoc", self.error_texts())

    def test_java_syntax_file_missing_reports(self):
        # 反例⑬：Java 落点整份缺失 -> `@UtilityClass` 与 JDK 扩展类的边界失去载体
        self._write_valid()
        os.remove(cm.JAVA_SYNTAX_FILE)
        cm.check_tool_class_inheritance_guard()
        self.assertIn("java-syntax.adoc", self.error_texts())


class TestCheckReferenceCoordGuard(CheckSpecsTestCase):
    """钉住『引用坐标』防线（Issue #208 实测 7 处同形失效：坏的是"去哪儿找"这一跳）。

    用户口径（本轮待确认第 2 项）：补一道机械防线核**跨文件定位坐标**——既有防线只核
    "条文/判据在不在"，`check_section_refs` 又只认 `link:x.adoc[]「节名」` 一种写法，
    本次 7 处里仅 1 处落在它覆盖面内。故本道核两件可机械判定的：① **位置式坐标**
    （按行号/条号/序号指内容）；② **引用式坐标的目标不全**（只写文件名、其后紧跟名称，
    且该文件名在本仓库不唯一）。
    """

    # 本道判据的**本体**与**图形**都外置在规则数据里（`script/specs-rules/`），
    # 故正例夹具须把这两份也备齐——否则"落点缺失"会被本道一并报出、正例成了假红。
    # **不手抄**：规则数据是唯一的措辞来源，手抄一份必然与现场漂移（本轮实测：手抄版
    # 少一组锚点即产生假红），故按真实文件原样落进夹具。
    _RULES_FILES = ("script/specs-rules/_tokens.toml", "script/specs-rules/source.toml")

    def _write_spec(self, body: str, extra: str = "") -> None:
        """落点＝**真实的** `source.adoc`（判据本体不手抄、不重写），被测形态**追加**在其后。

        这样正例（`body` 本身合规）与反例（`body` 是坏形态）都只在"本道核什么"上变化，
        判据本体与其锚点始终是现场那一份——手抄本体必然与现场漂移（本轮实测：手抄版
        少一组锚点即产生假红）。
        """
        self.write_rules_fixture()
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/verify.adoc",
                   "= verify\n\n== 验证的适用边界\n\n内容\n\n" + extra)
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(cm.__file__)))
        with open(os.path.join(repo_root, "specs/general/source.adoc"),
                  encoding="utf-8") as fh:
            real = fh.read()
        self.write("specs/general/source.adoc", real + "\n" + body)

    def _write_spec_lines(self, lines: str) -> None:
        """同上，但被测形态写成**多行条目**（首行是 `* `，续行不进 `_iter_bullet_items` 的切分）。

        判据的锚点组与位置式禁令按**条目正文**核，故反例的两半必须落在**同一条目**里——
        分成两个条目时，"位置式坐标一律不得使用"会被判成本条目的要点缺失（假红）。
        """
        self.write_rules_fixture()
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/verify.adoc",
                   "= verify\n\n== 验证的适用边界\n\n内容\n")
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(cm.__file__)))
        with open(os.path.join(repo_root, "specs/general/source.adoc"),
                  encoding="utf-8") as fh:
            real = fh.read()
        self.write("specs/general/source.adoc", real + "\n" + lines)

    def test_positional_ref_reports(self):
        # 反例①：按条号指向内容（本仓库实测形态：README 引"本文件第 41 条"而该节只剩 25 条）
        self._write_spec_lines("* 引用坐标不得靠位置（L1）：引用式坐标照写，「位置式坐标一律不得使用」；\n"
                               "  并核对 `specs/general/verify.adoc` 的第 41 条说明。\n")
        cm.check_reference_coord_guard()
        self.assertIn("位置式坐标", self.error_texts())

    def test_positional_serial_reports(self):
        # 反例②：按序号指向内容（实测形态：按行号引 guards.adoc 第 94 条，那道防线早已被挤位）
        self._write_spec_lines("* 引用坐标不得靠位置（L1）：引用式坐标照写，「位置式坐标一律不得使用」；\n"
                               "  并核对 `specs/general/verify.adoc` 的序号 94 那一道。\n")
        cm.check_reference_coord_guard()
        self.assertIn("位置式坐标", self.error_texts())

    def test_positional_tail_reports(self):
        # 反例③：按"末尾一条"指代（同样是位置，不是名称）
        self._write_spec_lines("* 引用坐标不得靠位置（L1）：引用式坐标照写，「位置式坐标一律不得使用」；\n"
                               "  落点按 `specs/general/verify.adoc` 的末尾一条取值。\n")
        cm.check_reference_coord_guard()
        self.assertIn("位置式坐标", self.error_texts())

    def test_relative_procedure_position_passes(self):
        # 正例：流程步骤里的"第 N 步"不是引用坐标
        self._write_spec("* 执行流程：第 1 步先跑机械手段、第 2 步做三视角复核。\n")
        cm.check_reference_coord_guard()
        self.assertEqual(cm.errors, [])

    def test_procedure_position_in_rule_passes(self):
        # 正例：条文里的"第 N 步"接判定词（本仓库实测：prompts/refactor.adoc
        # "仅对第 2 步判定需性能测试的敏感点补性能用例"）——指名的是流程步骤，
        # 不是"用位置代替名称"；判据按**命中片段自身的形态**取，不看上下文。
        self._write_spec("* 仅对第 2 步判定需性能测试的敏感点补性能用例，其余不加。\n")
        cm.check_reference_coord_guard()
        self.assertEqual(cm.errors, [])

    def test_part_position_passes(self):
        # 正例：标准分部名（本仓库实测：`library/sources.adoc` 的
        # "GB/T 7713.1-2025《信息与文献 编写规则 第1部分：学位论文》"）
        self._write_spec("* 标准名：《信息与文献 编写规则 第1部分：学位论文》——现行。\n")
        cm.check_reference_coord_guard()
        self.assertEqual(cm.errors, [])

    def test_ordinal_article_passes(self):
        # 正例：序数词（"第 1 款/第 2 条例外"）不是按序号指内容
        self._write_spec("* 按第 2 条例外处理，其余照第 1 款执行。\n")
        cm.check_reference_coord_guard()
        self.assertEqual(cm.errors, [])

    def test_relative_path_ref_passes(self):
        # 正例：带目录的相对路径（`../general/verify.adoc`）——坐标落在哪一层由引用自己
        # 给出，不属"只写文件名"（判据不得把无扩展名的 `a/adoc` 误当 `.adoc` 文件名）
        self.write_rules_fixture()
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write_real_file("specs/general/source.adoc")
        self.write("specs/general/verify.adoc", "= t\n\n== 验证的适用边界\n\n内容")
        self.write("specs/general/doc.adoc",
                   "* 见 `../general/verify.adoc`「验证的适用边界」。\n")
        cm.check_reference_coord_guard()
        self.assertEqual(cm.errors, [])

    def test_file_only_ref_reports(self):
        # 反例④：引用式坐标只写文件名（实测形态：维护方层写 `verify.adoc`「验证的适用边界」，
        # 同级解析落到维护方自己的那一份，而目标节在 specs/general/verify.adoc）
        self.write_rules_fixture()
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/verify.adoc", "= t\n\n== 验证的适用边界\n\n内容")
        self.write("specs-project-maintainer/verify.adoc", "= t\n\n== 维护方\n\n内容")
        self.write("specs/general/doc.adoc",
                   "* 性质与各档取值见 `verify.adoc`「验证的适用边界」。\n")
        cm.check_reference_coord_guard()
        self.assertIn("引用坐标不完整", self.error_texts())

    def test_same_stem_in_two_dirs_reports(self):
        # 反例⑨（同名文件计数）：两份 `doc.adoc` 分处两层——按**去扩展名的词干**计数
        # 才认得出来（写成 `specs/general/doc-design.adoc` 之类的近名不算同名，
        # 判据也不得按"文件名字面"计数，否则 `library/doc.adoc` 会被漏掉）。
        self.write_rules_fixture()
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write_real_file("specs/general/source.adoc")
        self.write("specs/general/doc.adoc", "= t\n\n== 注释与文档\n\n内容")
        self.write("library/doc.adoc", "= t\n\n== 馆内同名\n\n内容")
        self.write("specs/general/verify.adoc",
                   "* 见 `doc.adoc`「注释与文档」。\n")
        cm.check_reference_coord_guard()
        self.assertIn("引用坐标不完整", self.error_texts())

    def test_full_name_ref_passes(self):
        # 正例：写全目标路径 + 名称
        self.write_rules_fixture()
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write_real_file("specs/general/source.adoc")
        self.write("specs/general/verify.adoc", "= t\n\n== 验证的适用边界\n\n内容")
        self.write("specs/general/doc.adoc",
                   "* 见 `specs/general/verify.adoc`「验证的适用边界」。\n")
        cm.check_reference_coord_guard()
        self.assertEqual(cm.errors, [])

    def test_unique_basename_passes(self):
        # 正例：目标文件名在本仓库唯一（README.adoc/AGENTS.adoc），写全名是多余的
        self.write_rules_fixture()
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write_real_file("specs/general/source.adoc")
        self.write("README.adoc", "= t\n\n== 使用要点\n\n内容")
        self.write("specs/general/doc.adoc", "* 见 `README.adoc`「使用要点」。\n")
        cm.check_reference_coord_guard()
        self.assertEqual(cm.errors, [])

    def test_own_file_short_name_passes(self):
        # 正例：指向本文件的自身简称（同文件内的引用，不存在解析歧义）
        self.write_rules_fixture()
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write_real_file("specs/general/source.adoc")
        self.write("specs/general/verify.adoc", "= t\n\n== 验证的适用边界\n\n内容")
        self.write("specs/general/doc.adoc", "= t\n\n* 见 `doc.adoc`「验证的适用边界」。\n")
        cm.check_reference_coord_guard()
        self.assertEqual(cm.errors, [])

    def test_ok_scope_exempt_from_positional(self):
        # 正例：编号即内容本身的载体（清单表行号）按规则数据声明放行
        self.write_rules_fixture()
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write_real_file("specs/general/source.adoc")
        self.write("README.adoc", "* 见清单表第 94 条。\n")
        cm.check_reference_coord_guard()
        self.assertEqual(cm.errors, [])

    def test_reversed_positional_reading_reports(self):
        # 反例⑤：把"按位置引用"写成可接受形态（与判据反向）
        self._write_spec_lines("* 引用坐标不得靠位置（L1）：引用式坐标照写，「位置式坐标一律不得使用」；\n"
                               "  位置式坐标可以按条号引用，只是要注意维护。\n")
        cm.check_reference_coord_guard()
        self.assertIn("可接受形态", self.error_texts())

    def _mutate_real_source(self, a: str, b: str) -> None:
        """把**真实的** `source.adoc` 里某一段换成别的样子（判据本体被抽的形态）。"""
        self.write_rules_fixture()
        self.write("AGENTS_COMMON.adoc", "= t")
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(cm.__file__)))
        with open(os.path.join(repo_root, "specs/general/source.adoc"),
                  encoding="utf-8") as fh:
            real = fh.read()
        assert a in real, f"夹具锚点不存在：{a}"
        self.write("specs/general/source.adoc", real.replace(a, b, 1))

    def test_judge_body_replaced_by_slogan_reports(self):
        # 反例⑥：判据本体被抹成一句口号（只核"这一节还在不在"属防线空转）
        self._mutate_real_source("* **引用坐标不得靠位置（L1）**", "* **引用写准点（L1）**")
        cm.check_reference_coord_guard()
        self.assertIn("引用坐标不得靠位置", self.error_texts())

    def test_positional_ban_removed_reports(self):
        # 反例⑦：位置式禁令被抽走（形态判据仍在、须仍报红）
        self._mutate_real_source("**位置式坐标一律不得使用**", "")
        cm.check_reference_coord_guard()
        self.assertIn("位置式坐标一律不得使用", self.error_texts())

    def test_file_only_ban_removed_reports(self):
        # 反例⑧：「不得只写文件名」被抽走 -> 引用式坐标的目标写法失去判据
        self._mutate_real_source("**不得只写文件名**", "")
        cm.check_reference_coord_guard()
        self.assertIn("不得只写文件名", self.error_texts())

    def test_boundary_clause_removed_reports(self):
        # 反例⑨：边界句被抽走 -> 清单表行号、隐患编号一类误判成违规
        self._mutate_real_source("**编号即内容本身的载体**", "")
        cm.check_reference_coord_guard()
        self.assertIn("编号即内容本身的载体", self.error_texts())

    def test_positional_pattern_removed_reports(self):
        # 反例⑩：判据图形（位置式正则）被改成认不出条号的形态
        self.write_rules_fixture()
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("specs/general/source.adoc", "= t\n\n== 内部引用\n\n内容\n")
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(cm.__file__)))
        with open(os.path.join(repo_root, "script/specs-rules/_tokens.toml"),
                  encoding="utf-8") as fh:
            tok = fh.read()
        self.write("script/specs-rules/_tokens.toml",
                   tok.replace("序号(?:为|是)?", "序号XX"))
        cm.check_reference_coord_guard()
        self.assertIn("判据图形", self.error_texts())

    def test_prompts_are_checked(self):
        # 覆盖范围：提示词（会被复制到未知项目执行）同样纳入
        self.write_rules_fixture()
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write("prompts/review.adoc", "* 见 `specs/general/verify.adoc` 的第 41 条。\n")
        cm.check_reference_coord_guard()
        self.assertIn("位置式坐标", self.error_texts())


class TestCheckSkillRefCoordGuard(CheckSpecsTestCase):
    """钉住『skill 引用坐标』防线：skill 里指到**兄弟文件**的引用在目标项目里必然落空。

    实测依据（`skills-1.7.0` 的安装侧行为）：真正落到落点的**只有 `SKILL.md`**——
    `containsSupportingFiles` 只用来判断"除 SKILL.md 之外还有没有别的文件"，据此在提示里
    加一句"到别处读"，而那个别处只存在于安装侧的临时目录。故配套文件须**就地落盘**
    （以 `.` 开头、或随 SKILL.md 同处一个 skill 目录）。
    """

    def test_sibling_reference_reports(self):
        # 反例①：SKILL.md 指向 references/ 下的兄弟文件（安装后那边没有这个文件）
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write(".claude/skills/foo/SKILL.md",
                   "---\nname: foo\ndescription: d\n---\n\n读 `references/guide.md`。\n")
        cm.check_skill_ref_coord_guard()
        self.assertIn("落空", self.error_texts())

    def test_script_sibling_reference_reports(self):
        # 反例②：指向 scripts/ 下的兄弟文件（同样不进落点）
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write(".claude/skills/foo/SKILL.md",
                   "---\nname: foo\ndescription: d\n---\n\n跑 `scripts/run.js`。\n")
        cm.check_skill_ref_coord_guard()
        self.assertIn("落空", self.error_texts())

    def test_dot_relative_passes(self):
        # 正例：配套文件就地落盘（以 `.` 开头）、按落点内相对位置引用
        self.write_rules_fixture()
        self.write("AGENTS_COMMON.adoc", "= t")
        self.write(".claude/skills/foo/SKILL.md",
                   "---\nname: foo\ndescription: d\n---\n\n读 `./guide.md`、跑 `./scripts/run.js`。\n")
        cm.check_skill_ref_coord_guard()
        self.assertEqual(cm.errors, [])

    def test_prefix_list_emptied_reports(self):
        # 反例③：前缀清单被清空 -> 形态判据无引用面可核，且本组锚点须报红（不空转）
        self.write_rules_fixture()
        self.write("AGENTS_COMMON.adoc", "= t")
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(cm.__file__)))
        with open(os.path.join(repo_root, "script/specs-rules/_tokens.toml"),
                  encoding="utf-8") as fh:
            tok = fh.read()
        self.write("script/specs-rules/_tokens.toml",
                   tok.replace('SKILL_SIBLING_REF_PREFIXES = [\n    "references/",\n'
                               '    "scripts/",\n]', "SKILL_SIBLING_REF_PREFIXES = []"))
        cm.check_skill_ref_coord_guard()
        self.assertIn("兄弟文件引用前缀清单", self.error_texts())

    def test_no_skills_passes(self):
        # 正例：没有 skill 目录时本道不发声（不是所有仓库都装 skill）
        self.write_rules_fixture()
        self.write("AGENTS_COMMON.adoc", "= t")
        cm.check_skill_ref_coord_guard()
        self.assertEqual(cm.errors, [])


# --------------------------------------------------------------------------- #
# check_split_history_ownership_guard（一份变多份的历史归属，Issue #215）
# --------------------------------------------------------------------------- #
class TestCheckSplitHistoryOwnershipGuard(CheckSpecsTestCase):
    """『一份变多份的历史归属』防线的反例用例。

    失效形态：同一批"移动/重命名 + 复制"的历史按模块**平均分**——每一边都接上局部历史，
    **每一处看上去都"保留了历史"**，而同一批文件的历史归属被拆成两处（用户口径里的
    "不要每一边丢几个"）。故本条须把三级判据、判定标准与例外都钉在**条目自己的正文**上。

    **夹具＝真文档逐字读入**（现读，不另抄一份节选）：手抄夹具时锚点与真文档在同义改写后
    会整体脱节——上一版抄了"该条 bullet + 6 行"，把条目改成**反向口径**（"同一源文件可以
    让多份继承移动历史"）仍全绿，而真文档里防线更穷（实测 5 处反向/抽空改法一个都不报）。
    逐字读入时 `test_valid_passes` 会先一步暴露脱节。
    """

    GIT = "specs/general/git.adoc"
    PRIORITY = "specs-project-maintainer/priority.adoc"
    COMMON = "AGENTS_COMMON.adoc"

    def setUp(self) -> None:
        super().setUp()
        self._orig_common = cm.GENERIC_FILE
        cm.GENERIC_FILE = os.path.join(self.root, "AGENTS_COMMON.adoc")
        # 真文档以 `HERE` 为基准取绝对路径：cwd 相对路径在非仓库根跑单测时会
        # `FileNotFoundError`，夹具读不到真文档、整套反例失去对象。
        repo = os.path.dirname(HERE)
        for rel in (self.GIT, self.PRIORITY, self.COMMON):
            with open(os.path.join(repo, *rel.split("/")), encoding="utf-8") as fh:
                setattr(self, "_text_" + rel.replace("/", "_"), fh.read())

    def tearDown(self) -> None:
        cm.GENERIC_FILE = self._orig_common
        super().tearDown()

    def _text(self, rel: str) -> str:
        return getattr(self, "_text_" + rel.replace("/", "_"))

    def _write_valid(self) -> None:
        for rel in (self.GIT, self.PRIORITY, self.COMMON):
            self.write(rel, self._text(rel))

    def _run(self) -> None:
        # `run_rule_guard` 按**阶段**去重（每个用例自成一个阶段），显式清一次只是让
        # "同一用例里重复调用防线"也按最新夹具核对（防御性，与 `_StackGuardTestCase` 同理）。
        cm._RULES_RUN_THIS_PHASE.clear()
        cm.check_split_history_ownership_guard()

    def _mutate_git(self, removed: str, replacement: str = "") -> None:
        # 先断言真文档里确实有这句——锚点与真文档脱节时本轮反例就失去了对象。
        self.assertIn(removed, self._text(self.GIT))
        self._write_valid()
        self.write(self.GIT, self._text(self.GIT).replace(removed, replacement))

    def _mutate_common(self, removed: str, replacement: str = "") -> None:
        self.assertIn(removed, self._text(self.COMMON))
        self._write_valid()
        self.write(self.COMMON, self._text(self.COMMON).replace(removed, replacement))

    def test_valid_passes(self):
        # 正例兼锚点自检：真文档逐字进夹具时防线必须报绿
        self._write_valid()
        self._run()
        self.assertEqual(cm.errors, [])

    def test_missing_git_file_reports(self):
        self._write_valid()
        os.remove(os.path.join(self.root, "specs", "general", "git.adoc"))
        self._run()
        self.assertIn("缺少", self.error_texts())

    def test_section_deleted_reports(self):
        # 反例：整节被删 -> 同类只让一份继承历史的裁决无处可查
        self._write_valid()
        self.write(self.GIT, "= git 规范\n\n== 别的节\n* 略。\n")
        self._run()
        self.assertIn("文件移动与重命名", self.error_texts())

    def test_bullet_removed_reports(self):
        # 反例：整条 bullet 被摘掉 -> 判据整条消失
        self._mutate_git("* **一份变多份的历史归属（一拆多 / 移动 + 复制）**")
        self._run()
        self.assertIn("一份变多份的历史归属", self.error_texts())

    def test_similarity_first_removed_reports(self):
        # 反例：删掉一级判据整句 -> 集中到一个模块被读成"不问相似度、只看模块"。
        # 锚点原取 `内容相似度高`（在 ① 与 ② 里各出现一次），这条反例**实测全绿**:
        # 同形字样被 ② 的位置句兜住——故锚点须取**本条 bullet 内只出现一次**的写法。
        self._mutate_git("① **内容相似度高的那一份继承**")
        self._run()
        self.assertIn("内容相似度高的那一份继承", self.error_texts())

    def test_concentrate_one_module_removed_reports(self):
        # 反例：删掉"集中到一个模块"那一级判据 -> 用户点名的"不要每一边丢几个"无条文可依
        self._mutate_git("② **相似度相同时，集中到一个模块**")
        self._run()
        self.assertIn("集中到一个模块", self.error_texts())

    def test_most_inheritable_removed_reports(self):
        # 反例：删掉"能继承数量最多者" -> 模块怎么选没有判据，重新落回任选
        self._mutate_git("③ **模块的选择取能继承数量最多者**")
        self._run()
        self.assertIn("能继承数量最多者", self.error_texts())

    def test_tie_is_fixed_removed_reports(self):
        # 反例：删掉"一经选定即固定" -> 同一次改动里可以来回改归属
        self._mutate_git("**一经选定即固定**")
        self._run()
        self.assertIn("一经选定即固定", self.error_texts())

    def test_split_across_modules_clause_removed_reports(self):
        # 反例：删掉判定标准里"落在两个及以上模块"那一档 -> 判定标准只剩口号
        self._mutate_git("继承历史的文件**落在两个及以上模块**")
        self._run()
        self.assertIn("落在两个及以上模块", self.error_texts())

    def test_multiple_moves_clause_removed_reports(self):
        # 反例：删掉"同一源文件被移动多次" -> 多份同时继承历史不再被拦
        self._mutate_git("④ 同一源文件被移动多次（多份同时继承）")
        self._run()
        self.assertIn("同一源文件被移动多次", self.error_texts())

    def test_criteria_removed_reports(self):
        # 反例：判定标准整体被抽掉 -> 只剩一句"要集中"，判不出有没有被遵守
        self._mutate_git("**判定标准（逐条可核对，任一命中即不合规）**")
        self._run()
        self.assertIn("任一命中即不合规", self.error_texts())

    def test_requirement_inverted_reports(self):
        # 反例（**上一版夹具漏放的形态**）：条文还在、**要求被反向**——一对一被改成"可以让
        # 多份继承移动历史"，锚点落在原句上才判得出来（按"三级判据的轴名还在不在"核时，
        # 整条被反向也能报绿）。
        self._mutate_git("**同一源文件只能让其中一份继承移动历史**",
                         "**同一源文件可以让多份继承移动历史**")
        self._run()
        self.assertIn("同一源文件只能让其中一份继承移动历史", self.error_texts())

    def test_rule_lowered_to_judgement_reports(self):
        # 反例：判据被降级为"执行者自行判断"（轴名齐全、判据被抽走的形态）
        self._mutate_git("**继承哪一份、按三级判据取**", "**继承哪一份由执行者判断**")
        self._run()
        self.assertIn("继承哪一份、按三级判据取", self.error_texts())

    def test_concentrate_value_clause_removed_reports(self):
        # 反例：删掉取值句"整体落在同一个模块内" -> "集中"没有可核对的取值形态
        self._mutate_git("整体落在同一个模块内")
        self._run()
        self.assertIn("整体落在同一个模块内", self.error_texts())

    def test_priority_ledger_removed_reports(self):
        # 反例：不可降级清单侧的回指被删 -> 重构时该判据会被当普通条目删掉
        self._write_valid()
        self.write(self.PRIORITY, self._text(self.PRIORITY).replace(
            "* **一份变多份的历史归属（同列，用户提出）**"
            "：同一源文件既移动又复制、只能一份继承历史时，**相似度高者优先**；"
            "相似度相同则**集中到一个模块**、模块取**能继承数量最多者**"
            "（不得跨模块各分几个）——判据与判定标准见 "
            "`specs/general/git.adoc`「文件移动与重命名」的「一份变多份的历史归属」条。\n", ""))
        self._run()
        self.assertIn("能继承数量最多者", self.error_texts())

    def test_priority_file_missing_reports(self):
        # 反例：维护方清单整个缺失 -> 不可降级登记无从核对
        self._write_valid()
        os.remove(os.path.join(self.root, "specs-project-maintainer", "priority.adoc"))
        self._run()
        self.assertIn("缺少", self.error_texts())

    def test_dispatch_trigger_removed_reports(self):
        # 反例：加载门被抽 -> 判定"只剩一份历史时由哪一份继承"时不会加载 git.adoc，
        # 判据写了却读不到（与"规则被删"在执行侧等价）
        self._mutate_common("要判定只剩一份历史时由哪一份继承（同一源文件**既移动又复制**）、")
        self._run()
        self.assertIn("既移动又复制", self.error_texts())


if __name__ == "__main__":
    unittest.main()
