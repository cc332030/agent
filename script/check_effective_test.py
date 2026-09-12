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

    def test_config_class_guard_has_mechanical_grip(self):
        # "配置类不写逻辑"由 check_config_class_guard 钉住（条文/判定标准/识别特征/公开说明同步）
        self._mk("script/check_specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(
            statuses["配置类不写逻辑（配置类只保持 POJO 基本功能、逻辑下沉 utils/service）"],
            "has-grip")

    def test_destructive_op_has_mechanical_grip(self):
        # P5 的存在性与必加载层落点由 check_priority_guard 机械钉住
        self._mk("script/check_specs.py")
        statuses = {r["name"]: r["status"] for r in eff.evaluate(self.root)}
        self.assertEqual(
            statuses["不可逆操作先确认（删除/清空/强推，P5）"], "has-grip")


if __name__ == "__main__":
    unittest.main(verbosity=2)
