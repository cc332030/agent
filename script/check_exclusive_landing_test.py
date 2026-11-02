"""反例用例：『并行改动的独占落点』两道防线。

`check_git_attributes_merge_guard`（只增不改的落点须配 `merge=union`）与
`check_ledger_table_generated_guard`（逐行登记表须是生成物）。两道判据的**共用失效形态**
是同一条：判据只核"配了 / 生成了"这一件动作；配错路径、配到有序行表上、手改了生成物，
都不会有人发现——故每个用例都对应一种"看着做了、其实没做"的形态。
"""

import os
import unittest

from check_specs_test import CheckSpecsTestCase, cm  # 与被测模块**同一个实例**

# 夹具里"生成器"的最小版：只认「现场＝重算结果」这一件事（真生成器另有登记表与片段定位，
# 那一层由现场仓库自己的用例核）。它的产出就是表体本身（登记项用段标记时是标记之间的
# 那一段；这里只覆盖"整节重出"这一种形态）。
_FIXTURE_GEN = (
    "import os\n\n\n"
    "DELIM = " + repr(chr(34) * 3) + "\n\n\n"
    "def stale_files(root):\n"
    "    out = []\n"
    "    for rel, text in render(root).items():\n"
    "        p = os.path.join(root, *rel.split('/'))\n"
    "        with open(p, encoding='utf-8', newline='') as fh:\n"
    "            if fh.read() != text:\n"
    "                out.append(rel)\n"
    "    return sorted(out)\n\n\n"
    "def render(root):\n"
    "    p = os.path.join(root, 'script', 'check_specs.py')\n"
    "    with open(p, encoding='utf-8') as fh:\n"
    "        head = fh.read().split(DELIM)[1]\n"
    "    rows = [ln.strip() for ln in head.splitlines()"
    " if ln[:1] == ' ' and ln[1:2].isdigit()]\n"
    "    out = []\n"
    "    for ln in rows:\n"
    "        out.append('| ' + ln.replace('. ', ' | ', 1) + '\\n')\n"
    "    p2 = os.path.join(root, 'specs-project-maintainer', 'guards.adoc')\n"
    "    with open(p2, encoding='utf-8', newline='') as fh:\n"
    "        head_text = fh.read().split('| 1 ', 1)[0]\n"
    "    return {'specs-project-maintainer/guards.adoc': head_text + ''.join(out) + '|===\\n'}\n"
)


class TestCheckGitAttributesMergeGuard(CheckSpecsTestCase):
    """钉住『只增不改的落点须配 `merge=union`』：配没配、配得对不对、配了之后形态对不对。"""

    SPEC = """== 冲突处理

* **只增不改的落点按路径声明合并策略（L1）**：行集合型落点（即**只增不改**的行集合）
  一律以 `merge=union` 声明，**落盘口**是仓库配置，判定标准三条；
  在配了合并策略的落点里，新增一律按顺序追加、**不去动别人的行**——两边改到同一行时
  合并策略帮不上忙；**有序行表**不得配 union。
"""

    def _setup(self, attrs, spec=None):
        self.write("specs/general/version-control.adoc", spec or self.SPEC)
        self.write(".gitattributes", attrs)
        self.write("script/specs-rules/other.toml", 'K = "v"\n')
        self.write("specs-project-maintainer/ledger/x.adoc", "| 一行\n")
        self._write_source_management("concurrent")

    def test_union_configured_passes(self):
        # 正例：清单点名的落点都声明了 union，落点里只有"追加式"的行
        self._setup("script/specs-rules/*.toml merge=union\n"
                    "specs-project-maintainer/ledger/*.adoc merge=union\n")
        cm.check_git_attributes_merge_guard()
        self.assertNotIn("merge=union` 的要点", self.error_texts())
        self.assertNotIn("没有覆盖", self.error_texts())

    def test_no_union_at_all_reports(self):
        # 反例①：一条 union 都没有——全靠人工解冲突
        self._setup("* text eol=lf\n")
        cm.check_git_attributes_merge_guard()
        self.assertIn("一条 `merge=union` 都没有", self.error_texts())

    def test_union_on_wrong_path_reports(self):
        # 反例②：配了、但配的不是清单点名的落点——等于没配
        self._setup("docs/*.adoc merge=union\n")
        cm.check_git_attributes_merge_guard()
        self.assertIn("没有覆盖清单点名的落点", self.error_texts())

    def test_ordered_table_in_landing_reports(self):
        # 反例③：配了 union，落点里却是有序行表（位置即含义）——union 只解一半
        self._setup("script/specs-rules/*.toml merge=union\n"
                    "specs-project-maintainer/ledger/*.adoc merge=union\n")
        self.write("specs-project-maintainer/ledger/x.adoc",
                   "\n".join(f"{i}. 第{i}项" for i in range(1, 8)) + "\n")
        cm.check_git_attributes_merge_guard()
        self.assertIn("有序行表", self.error_texts())

    def test_missing_spec_points_report(self):
        # 反例④：配置配对了，而判据本体被删成一句"配了就行"——配错也无人发现
        self._setup("script/specs-rules/*.toml merge=union\n"
                    "specs-project-maintainer/ledger/*.adoc merge=union\n",
                    spec="== 冲突处理\n\n* 配 `merge=union` 即可。\n")
        cm.check_git_attributes_merge_guard()
        self.assertIn("merge=union` 的要点", self.error_texts())

    def test_not_declared_passes_without_union(self):
        # 反例⑥（可选档）：本项目**没声明启用**——一条 union 都没有也不算问题：
        # 那一套做法的全部代价（分份、合并策略、生成器）只为"未完工分支并存"付，
        # 单线顺序开发的项目不必为它铺开文件；判据取值仍须在（下一个用例核这一点）。
        self._setup("* text eol=lf\n")
        self._write_source_management("conventional")
        cm.check_git_attributes_merge_guard()
        self.assertNotIn("一条 `merge=union` 都没有", self.error_texts())

    def test_not_declared_still_needs_spec_points(self):
        # 反例⑦：没声明启用 **不等于** 可以把这一档的判据连取值一起删——规则可以不用，
        # 但不能不存在；删了它，下一次有人想启用时连"该怎么做"都无处可读。
        self._setup("script/specs-rules/*.toml merge=union\n",
                    spec="== 冲突处理\n\n* 配 `merge=union` 即可。\n")
        self._write_source_management("conventional")
        cm.check_git_attributes_merge_guard()
        self.assertIn("merge=union` 的要点", self.error_texts())

    def test_missing_gitattributes_reports(self):
        # 反例⑤：仓库根没有 `.gitattributes`——行尾与合并两类取值都没有落盘口
        self.write("specs/general/version-control.adoc", self.SPEC)
        cm.check_git_attributes_merge_guard()
        self.assertIn("缺少 `.gitattributes`", self.error_texts())


class TestCheckLedgerTableGeneratedGuard(CheckSpecsTestCase):
    """钉住『逐行登记表须是生成物』：现场＝重算结果、节头写明是生成物、生成器在。"""

    RULES = ('[tokens.not_collision_catalog]\n'
             'sections = [\n'
             '  ["specs-project-maintainer/guards.adoc", "检查项编号",\n'
             '   "script/check_specs.py", "检查项编号表的表体", "", ""],\n'
             ']\n')

    HEAD = """== 检查项编号（生成物）

**这一段整段是生成物**：由 `script/gen_derived.py` 现算；`check_ledger_table_generated_guard`
核「现场与重算结果**逐字节一致**」。**判定标准**：手改即红。派生件与本体同一次产出。
**重算**：`python3 script/gen_derived.py --write`。

%(body)s"""

    SRC = ('"""\n 1. 甲\n 2. 乙\n"""\n\nimport os\n')

    def _setup(self, body="| 1 | 甲\n| 2 | 乙\n"):
        self._write_source_management("concurrent")
        self.write("script/gen_derived.py", _FIXTURE_GEN)
        self.write("script/check_specs.py", self.SRC)
        self.write("script/specs-rules/ledger.toml", self.RULES)
        self.write("specs-project-maintainer/guards.adoc",
                   self.HEAD % {"body": body + "|===\n"})
        cm.REPO_ROOT = self.root

    def _run(self):
        cm.check_ledger_table_generated_guard()

    def test_in_sync_passes(self):
        # 正例：现场＝重算结果
        self._setup()
        self._run()
        self.assertNotIn("重算结果不一致", self.error_texts())

    def test_hand_edited_reports(self):
        # 反例①：手改了表（少一行）——两处已漂移，按表核对的人看不到新条目
        self._setup("| 1 | 甲\n")
        self._run()
        self.assertIn("重算结果不一致", self.error_texts())

    def test_missing_generator_reports(self):
        # 反例②：生成器不在——逐行登记表退回成手抄的第二份
        self.write("specs-project-maintainer/guards.adoc", self.HEAD % {"body": ""})
        self._run()
        self.assertIn("gen_derived.py", self.error_texts())

    def test_not_declared_needs_no_generator(self):
        # 反例④（可选档）：没声明启用时**不要求本仓库上生成器**——那份表仍可以人工维护，
        # 不必为它建 `script/gen_derived.py`（判据取值由正例另行核：规则可以不用、不能不存在）。
        self._setup()
        self._write_source_management("conventional")
        os.remove(os.path.join(self.root, "script", "gen_derived.py"))
        self._run()
        self.assertNotIn("缺少 `script/gen_derived.py`", self.error_texts())

    def test_section_head_missing_note_reports(self):
        # 反例③：节头没写"这是生成物、怎么重算"——读者当手写表，下一轮照旧手改
        self._write_source_management("concurrent")
        self.write("script/gen_derived.py", _FIXTURE_GEN)
        self.write("script/check_specs.py", self.SRC)
        self.write("script/specs-rules/ledger.toml", self.RULES)
        self.write("specs-project-maintainer/guards.adoc",
                   "== 检查项编号\n\n| 1 | 甲\n| 2 | 乙\n")
        cm.REPO_ROOT = self.root
        self._run()
        self.assertIn("节头", self.error_texts())


if __name__ == "__main__":
    unittest.main()
