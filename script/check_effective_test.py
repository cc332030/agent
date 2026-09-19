#!/usr/bin/env python3
"""check_effective.py 的单元测试（纯 stdlib unittest）。

覆盖 evaluate() 的抓手判定（正例/反例）与机制清单的完整性。注入临时 root，
不依赖真实仓库。
"""

import importlib.util
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))

_SPEC = importlib.util.spec_from_file_location(
    "check_effective", os.path.join(HERE, "check_effective.py"))
eff = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(eff)  # type: ignore[union-attr]


class TestEvaluate(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def _mk(self, rel: str) -> None:
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write("")

    def test_mechanisms_are_unique_and_nonempty(self):
        names = [m[0] for m in eff.MECHANISMS]
        self.assertEqual(len(names), len(set(names)))
        self.assertGreaterEqual(len(names), 5)

    def test_grip_file_present_is_has_grip(self):
        self._mk("script/check_specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(statuses["内部链接须用相对路径、禁根绝对"], "has-grip")

    def test_grip_file_missing_is_grip_missing(self):
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(statuses["内部链接须用相对路径、禁根绝对"], "grip-missing")

    def test_none_grip_is_no_grip(self):
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(statuses["测试文件后缀式命名（禁 test_ 前戳）"], "no-grip")

    def test_git_mv_grip_is_self_side_only(self):
        # git mv 铁律：**引用方侧**本仓库看不到其操作（不得冒充抓手），但**本仓库自身侧**
        # 的暂存区可核对（check_git_mv_selfcheck / check_specs.py）——两侧须分清，
        # 既不能把引用方侧记作"有抓手"（虚报），也不能把自身侧记作"无抓手"（漏报）。
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(statuses["文件移动/重命名必须 git mv（防历史断裂）"], "grip-missing")
        self._mk("script/check_specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(statuses["文件移动/重命名必须 git mv（防历史断裂）"], "has-grip")

    def test_delegation_and_capability_have_mechanical_grip(self):
        # 从属者适配、环境能力自评：要点存在性由 check_delegation_guard 钉住
        self._mk("script/check_specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(
            statuses["从属者（子 agent/被引用方）加载由已加载入口驱动、不靠自报"], "has-grip")
        self.assertEqual(
            statuses["执行环境能力先自评、无机制走降级路径且不空自评"], "has-grip")

    def test_spec_verification_three_lenses_has_mechanical_grip(self):
        # 改完规范的语义复核三视角（①完整性 + ②有效性与认知质量 + ③接纳面）由
        # check_verify_guard 钉住
        self._mk("script/check_specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(
            statuses["改完规范须验证三视角：①完整性 + ②有效性与认知质量 + ③接纳面（同一子 agent）"],
            "has-grip")

    def test_verification_enumerability_has_mechanical_grip(self):
        # "验了什么、怎么算过、依据哪个标准"须能枚举——由「验证总纲」节与标准出处钉住
        self._mk("script/check_specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(
            statuses['验证须能枚举"验了什么、怎么算过、依据哪个标准"（防退化成跑绿脚本、慢慢脱离初衷）'],
            "has-grip")

    def test_adoption_surface_has_mechanical_grip(self):
        # 公共内容被未知项目加载的可控性（影响面/成本/可控性）由 check_adoption_guard 钉住
        self._mk("script/check_specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(
            statuses["公共内容被未知项目加载时的可控性（影响面/成本/可控性）"], "has-grip")

    def test_resident_budget_has_mechanical_grip(self):
        # 常驻层体积/调度器条目数上限由 check_budget_guard 钉住
        self._mk("script/check_specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(statuses["常驻层体积与调度器条目数不得无上限膨胀"], "has-grip")

    def test_scope_guard_has_mechanical_grip(self):
        # "校验范围只限公共内容与本仓库工具"由 check_specs_test 的用例钉住
        self._mk("script/check_specs_test.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(
            statuses["校验范围只限公共内容与本仓库工具（不检查引用方项目工作区）"], "has-grip")

    def test_self_check_has_mechanical_grip(self):
        # 自检规范的要点由 check_self_check_guard 机械钉住（存在性/落点/登记）
        self._mk("script/check_specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(
            statuses["执行前自检（非平凡任务须逐项自检，防'加载了却没执行'）"], "has-grip")

    def test_source_truthfulness_has_mechanical_grip(self):
        # 来源真实性要点由 check_source_guard 机械钉住
        self._mk("script/check_specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(
            statuses["不得编造事实与来源（引用真实、标准不编、宁可不引）"], "has-grip")

    def test_library_has_mechanical_grip(self):
        # "依据不得只剩名称"由 check_library_guard 钉住（图书馆存在/入口登记/逐字引文/引用可解析）
        self._mk("script/check_specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(
            statuses["依据不得只剩名称：图书馆须可查到、可逐字核对、引用不悬空"], "has-grip")

    def test_java_test_split_ruling_has_mechanical_grip(self):
        # 测试类拆分裁决（可拆 + 同分类同属性须归一类 + 禁止滥拆）由 check_java_test_naming 钉住
        self._mk("script/check_specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(
            statuses["Java 测试类拆分裁决（一个被测类可拆多个类，但同分类同属性须归一类、不得滥拆）"],
            "has-grip")

    def test_config_class_guard_has_mechanical_grip(self):
        # "配置类不写逻辑"由 check_config_class_guard 钉住（条文/判定标准/识别特征/公开说明同步）
        self._mk("script/check_specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(
            statuses["配置类不写逻辑（配置类只保持 POJO 基本功能、逻辑下沉 utils/service）"],
            "has-grip")

    def test_external_script_guard_has_mechanical_grip(self):
        # "跨语言执行脚本须放资源文件夹、扩展名取被调语言，且按性能敏感度决定读取时机"
        # 由 check_external_script_guard 钉住（通用层四条 L1 + 判定标准与反例 +
        # Java/Spring 落点与加载时机 + 调度器登记与 README 同步）
        self._mk("script/check_specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(
            statuses["跨语言执行脚本须放资源文件夹、扩展名取被调语言的扩展名，"
                     "且按性能敏感度决定读取时机（不写字符串拼接/模板、热点路径不每次读）"],
            "has-grip")

    def test_api_naming_guard_has_mechanical_grip(self):
        # 对外接口命名带所属域/项目前缀由 check_api_naming_guard 钉住
        # （通用层条文与判据 + Java 栈 Feign 落点 + 调度器识别特征 + README 与图书馆依据）
        self._mk("script/check_specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(
            statuses["对外接口命名带所属域/项目前缀（Feign 接口的 `Api` 前须带该域固定前缀，"
                     "先例优先、无先例取项目名词首组合）"], "has-grip")

    def test_delivery_guard_has_mechanical_grip(self):
        # 交付形态与报告落点（不得只冒一句、不得只交付不汇报）由 check_delivery_guard 钉住
        self._mk("script/check_specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(
            statuses["交付形态与报告落点：不得只冒一句过程性叙述、不得只交付不汇报"], "has-grip")
    def test_dev_flow_has_mechanical_grip(self):
        # 开发流程（现状/最佳方案/基线、大动先确认、不另写一套、老用例不得改判）
        # 由 check_dev_flow_guard 钉住
        self._mk("script/check_specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(
            statuses["开发流程：先查现状/先调研最佳方案/先定基线（既有用例先跑通并留证、"
                     "清单还要先核『够不够用』）、大范围改动先确认、不得绕开既有体系另写一套、"
                     "老用例不得为迁就改动而改判"],
            "has-grip")

    def test_maven_mirror_guard_has_mechanical_grip(self):
        # Maven 仓库与镜像（含不可用时的换源边界）由 check_maven_mirror_guard 钉住
        self._mk("script/check_specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(
            statuses["Maven 未配置过仓库/镜像且外网出口 IP 在中国大陆时，须用指定中央仓库"],
            "has-grip")

    def test_destructive_op_has_mechanical_grip(self):
        # P5 的存在性与必加载层落点由 check_priority_guard 机械钉住
        self._mk("script/check_specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(
            statuses["不可逆操作先确认（删除/清空/强推，P5）"], "has-grip")


    def test_performance_guard_has_mechanical_grip(self):
        # 性能测试的测量与记录要点由 check_performance_guard 钉住
        self._mk("script/check_specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(
            statuses["性能测试：测量须可核对（离散度与样本量、公平比较、计时区间与消费结果）、记录须有落点（方案组合与成绩、优化日志、瓶颈归因与方向、迭代至收敛）"], "has-grip")


class TestNewQualityAndReviewGrips(unittest.TestCase):
    """本轮新增五条的抓手判定（代码质量 / 生成效率 / token 纪律 / 改动后 review / 五件事）。

    这五条都是"要点文本仍在"型抓手（`check_specs.py` 的三道新防线），故正例＝
    `script/check_specs.py` 在；反例＝文件不存在时须判 `grip-missing`（不得冒充）。
    """

    def setUp(self) -> None:
        self.root = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def _mk(self, rel: str) -> None:
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write("")

    def test_quality_guard_has_mechanical_grip(self):
        self._mk("script/check_specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(
            statuses["代码质量（新产出即高质）：十项逐条自检须可判定（坏味道/职责与嵌套/命名/"
                     "可读性/失败与边界/资源/并发/性能退化/测试与文档/交付前自检）"],
            "has-grip")

    def test_generation_efficiency_has_mechanical_grip(self):
        self._mk("script/check_specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(
            statuses["生成效率：先定完成判据、一次做对做完、延后验证一次到位、失败一次查根因、"
                     "按需读取、不重做已做完的事"], "has-grip")

    def test_token_discipline_has_mechanical_grip(self):
        self._mk("script/check_specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(
            statuses["token 纪律：利用率与节省不是一回事；输入须被用到、约束放外部、"
                     "少复述多引用、不重复读贴、只记结论与取值；"
                     "以不损害功能完整性/代码质量/验证完整为前提"], "has-grip")

    def test_change_review_has_mechanical_grip(self):
        self._mk("script/check_specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(
            statuses["改动后的 review：每次改动都在同一轮内复核一次"
                     "（按改动性质取值；规范类按五件事）"], "has-grip")

    def test_after_change_five_things_has_mechanical_grip(self):
        self._mk("script/check_specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(
            statuses["改完规范必做五件事：机械手段必跑全、干净子 agent 三视角复核不可漏"
                     "（有了就忽略、没有就加）、三态台账、复核者不可用时的降级留证"],
            "has-grip")

    def test_reinstall_refresh_has_mechanical_grip(self):
        # 「重新执行安装须能更新现有副本（以远程为准）」由 check_spec_fetch_guard 钉住
        self._mk("script/check_specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(
            statuses["重新执行安装须能更新现有副本（安装脚本经常更新：以远程为准、内容不同才刷新，"
                     "失败保留本地那一份）"], "has-grip")

    def test_grip_missing_is_reported_not_faked(self):
        # 反例：抓手文件不存在时须判 grip-missing（不得冒充"有抓手"）
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(
            statuses["改完规范必做五件事：机械手段必跑全、干净子 agent 三视角复核不可漏"
                     "（有了就忽略、没有就加）、三态台账、复核者不可用时的降级留证"],
            "grip-missing")

if __name__ == "__main__":
    unittest.main(verbosity=2)
