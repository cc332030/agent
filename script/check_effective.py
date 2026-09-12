#!/usr/bin/env python3
"""『定义未执行』深度核验（单独手动执行）。

与 check_specs.py（每次改完规范必跑的完整性机械校验）不同，本脚本是**单独手动
执行**的体系化工具，回答一个 check_specs 回答不了的问题：

  规范里写的每条"必须/不得/严禁"条款，有多少是真正有可执行抓手（能被脚本或测试
  检测/拦住的）？有多少只是"文档定义、靠 agent 自觉遵守"——即"定义未执行"风险？

这类风险不会随每次调整暴露，故不随每次调整自动运行；由用户决定何时整体执行。

用法：
  python script/check_effective.py                 # 手动运行，输出抓手清单
  python script/check_effective.py --warn          # 有任何"无机械抓手"条款时以退出码 1 退出

说明：本脚本判定"抓手"只看机制文件/测试是否存在。若某强制条款无机械抓手，仅代表
它依赖 agent 遵守或人工 review，本身不一定是缺陷——脚本的作用是把这些风险点显式
列出来，供人工决定是否补充机制。

范围（重要）：本仓库的多数内容是给**其他项目**用的公共规范，故"有抓手"只认两类
可在本仓库机械校验的对象——① 公共内容本身（`AGENTS_COMMON.adoc`、`specs/` 的文本
与引用完整性）② 本仓库自身的维护工具与 CI。**引用方项目内部如何操作（含 delete+create
等）不在本仓库的可见范围**，不得记作"有抓手"（该铁律对其余项目靠遵守 + 各项目按
规范（`specs/general/git.adoc`）自行检查，本仓库只能把规范文本写清楚）。

**但边界不等于零抓手**：本仓库自己也是 git 工作区，其**暂存区状态行**可核对，故
`check_git_mv_selfcheck` 属"有抓手"——只覆盖本仓库自身侧那一半，引用方侧仍登记为
靠遵守（不许把两者混为一谈：把引用方侧记作"有抓手"是虚报，把自身侧记作"无抓手"
是漏报）。
"""

import argparse
import sys
from os import path

HERE = path.dirname(path.abspath(__file__))

# 输出列宽（中文按 2 字符宽对齐，避免手写空格导致清单错位）
NAME_WIDTH = 46

# 强制条款 → 可执行抓手映射。
# (条款名, 来源规范文件, 抓手相对路径[None=暂无机械抓手], 备注)
MECHANISMS = [
    ("规范调整后须真正验证（要点防线）",       "AGENTS.adoc",                 "script/check_specs.py",      "check_specs 的 check_principle_guard 校验该条仍存在"),
    ("内部链接须用相对路径、禁根绝对",           "specs/general/doc.adoc",           "script/check_specs.py",      "check_link_refs"),
    ("规范引用文件必须真实存在",                 "AGENTS.adoc",                 "script/check_specs.py",      "check_refs_exist"),
    ("技术栈登记与文件一致",                     "AGENTS_COMMON.adoc",        "script/check_specs.py",      "check_stack_consistency"),
    ("私有工程约定不入全局规范",                 "specs/general/*.adoc",            "script/check_specs.py",      "check_forbidden_patterns"),
    ("不保留无用的历史来源声明",                 "AGENTS.adoc",                 "script/check_specs.py",      "check_historical_notes"),
    ("禁止无意义/划水/凑字数的文档",            "specs/general/doc.adoc",           "script/check_specs.py",      "check_filler_docs（占位段/完全重复段）"),
    ("文档须高质量（准确/完整/可执行/有价值/简洁/可验证）", "specs/general/doc.adoc",   "script/check_specs.py",      "可验证性由 check_refs_exist/check_link_refs/check_section_refs 兜底，其余交人 review"),
    ("INSTALL 模板代码块逐字保留（换行/空行不丢失）", "INSTALL.adoc",            "script/check_specs.py",      "check_install_codeblock"),
    ("临时产物清理脚本可用",                     "specs/core/execution.adoc",       "script/clean_tmp.py",        "存在清理脚本"),
    ("完整性校验配套测试",                       "AGENTS.adoc",                 "script/check_specs_test.py", "20+ 用例"),
    ("定义未执行核验配套测试",                   "AGENTS.adoc",                 "script/check_effective_test.py", "本工具的自测"),
    ("变更日志只记影响、不记过程（重点优先、拒细枝末节）", "specs/general/changelog.adoc", "script/check_specs.py", "check_section_refs 钉住「应当记录/不应当记录/条目书写」三节引用不悬空；条目内容的详略判断交人 review"),
    ("文件移动/重命名必须 git mv（防历史断裂）", "specs/core/execution.adoc",       "script/check_specs.py",      "check_git_mv_selfcheck 覆盖**本仓库自身侧**（暂存区不得出现 delete+add 形态）；**引用方侧**本仓库看不到、仍靠遵守 + 各项目按 git 规范自检"),
    ("测试文件后缀式命名（禁 test_ 前戳）",       "specs/general/testing.adoc",      None,                         "无机械抓手：靠遵守；Java 测试类另须与源类同包路径、类名为「被测类名 + 测试类型后缀」（specs/stack/java-testing.adoc「测试类命名」：Tests/BootTests/PerfTests/IT），存量为随动迁移、不一次性收敛（specs/core/execution.adoc「规范变更的存量处理」）"),
    ("Java 测试类四类后缀命名契约（Tests/BootTests/PerfTests/IT）", "specs/stack/java-testing.adoc", "script/check_specs.py", "check_java_test_naming 钉住规范与 AGENTS_COMMON 调度器登记两侧都含四类后缀判据；「某项目某个类该用哪个后缀」属语义判断，交人/子 agent review"),
    ("校验范围只限公共内容与本仓库工具（不检查引用方项目工作区）", "AGENTS.adoc", "script/check_specs_test.py", "TestScopeStaysOnCommonContent 钉住 check_specs.py 不得读 git 工作区状态/HEAD"),
    ("最高关注项不得被删或降级（P1/P2/P3/P5 条款 L1、P4 条款 L2、同列最高关注项）", "specs-project-maintainer/priority.adoc", "script/check_specs.py", "check_priority_guard 钉住公共侧分级定义与最高关注项（含保留形态）、维护方侧 P1-P5 各自级别与『依据』行，以及 P1/读取/破坏性操作/来源真实性的必加载层落点；『条目级别是否与其实际后果相符』无机械抓手（等级越高验证越严：ISO/IEC Directives Part 2），由人/子 agent 复核承担"),
    ("定级口径（定级四问 + 条款类型判定表）不得被删", "specs-project-maintainer/spec-lifecycle.adoc", "script/check_specs.py", "check_spec_admission_guard 钉住『如何给一条规范定级』『与条款类型一一对应』『归属谁』『归类举证』『级别变更与复盘』五个节仍在（口径被删则级别重新混乱）"),
    ("定级方法论与元规范不得涨回常驻层（常驻层只放 L1 底线与最高关注项）", "specs-project-maintainer/priority.adoc", "script/check_specs.py", "check_priority_guard 拦住常驻层再次出现『设级别』等定级方法论节；『常驻层体量是否反弹』属体量判断，交人/子 agent 复核"),
    ("规范集合自身重构须按固定顺序（先判归属 → 再判层级 → 再判重复 → 压缩表述）", "specs-project-maintainer/spec-lifecycle.adoc", "script/check_specs.py", "check_spec_admission_guard 钉住重构顺序三要点仍在（顺序颠倒会把放错位置的内容直接删掉）"),
    ("同一条规则的两种读法（执行侧只给'怎么走'、依据与取舍归思考/决策侧）", "specs-project-maintainer/spec-lifecycle.adoc", "script/check_specs.py", "check_spec_admission_guard 钉住「同一条规则有两种读法」节；常驻层侧由 check_priority_guard 钉住『怎么走』形态声明与各最高关注项的『依据』行（依据不得被整段删掉）；一句话里是否真的没夹解释属文风判断，交人/子 agent 复核"),
    ("重构后须核对规范有效性（两形态分离 / 可执行性不降级 / 可见性不丢）", "specs-project-maintainer/spec-lifecycle.adoc", "script/check_specs.py", "check_spec_admission_guard 钉住「重构后须核对规范有效性」节；判据是否真未被压成口号属语义判断，交人/子 agent 复核"),
    ("读取按最小必要、长会话简单任务在干净上下文执行（P4）", "specs/core/execution.adoc", "script/check_specs.py", "check_priority_guard 钉住 P4 存在性与 execution.adoc 对 context.adoc 的引用；读取是否真越界属运行时行为，靠 agent 自检 + 人 review"),
    ("去重不得误删最高关注项的引用", "AGENTS.adoc", "script/check_specs.py", "check_priority_guard：最高关注项的存在性机械钉住（引用是否被删由该防线兜底发现）"),
    ("从属者（子 agent/被引用方）加载由已加载入口驱动、不靠自报", "AGENTS_COMMON.adoc", "script/check_specs.py", "check_delegation_guard 钉住『从属者』机制仍在（否则子 agent/被派发任务可'没被告知'为由跳过加载）；'实际是否真按入口加载'属运行时行为，靠遵守 + 人 review"),
    ("改完规范须验证三视角：①完整性 + ②有效性与认知质量 + ③接纳面（同一子 agent）", "specs/general/testing.adoc", "script/check_specs.py", "check_verify_guard 钉住公共「验证总纲」「规范验证」「验证的效力等级」「验证的适用边界」「运行契约」各节、三视角与标准出处、②的判据、'三视角合用一个干净子 agent'、'每次验证换干净上下文'，并核对维护方落点两处口径一致；「子 agent 是否真按三视角答全」属运行时行为，靠派发指令 + 人 review"),
    ("验证须能枚举\"验了什么、怎么算过、依据哪个标准\"（防退化成跑绿脚本、慢慢脱离初衷）", "specs/general/testing.adoc", "script/check_specs.py", "check_verify_guard 钉住「验证总纲」节与标准出处（ISO/IEC Directives Part 2 / RFC 2119 / ISO 10007 / ISO/IEC/IEEE 25010 / IEEE 1028 须在）；「本次是否真逐项枚举」属运行时行为，靠留证 + 人 review"),
    ("公共内容不得声明机械防线的存在（防线属维护方、随规范分发即宣称与实际不符）", "specs-project-maintainer/spec-lifecycle.adoc", "script/check_specs.py", "check_no_mechanism_claims_in_public 拦住『当前由某防线钉住』式声明句与裸防线名；该表述是否真在宣称防线由人/子 agent 复核"),
    ("公共内容须自足：不得引用引用方看不到的私有落点（一个文件可同时装公共与项目规则）", "AGENTS_COMMON.adoc + specs/", "script/check_specs.py", "check_public_content_is_self_contained 机械拦住公共内容里指向维护方自查层（specs-project-maintainer/）的引用——该层不随公共内容分发，引用方读到的只是死链；『某条规则是否真需自足表达』属语义判断，交人/子 agent 复核"),
    ("公共内容被未知项目加载时的可控性（影响面/成本/可控性）", "specs/general/testing.adoc", "script/check_specs.py", "check_adoption_guard 钉住「运行契约」节、三维判据与维护方承接清单登记；另由 check_public_content_has_no_private_refs 机械拦住\"公共内容把本仓库私有物当抓手引用\"（引用方读到的死链）；「某条具体规则落到未知项目里会不会静默推翻其约定」属语义判断，交人/子 agent 复核"),
    ("任务各节点须自查（提出/理解/方案/执行/验证/交付/复盘）", "specs/core/execution.adoc", "script/check_specs.py", "check_lifecycle_guard 钉住节点清单以表格行存在、并钉住『哪些节点不设』的独立声明；『某个节点上是否真的自查了』属运行时行为，靠 agent 遵守 + 人 review"),
    ("子 agent 复核须自带硬超时、到点视为失联并放弃（防任务永久挂起）", "specs/general/collab.adoc", "script/check_specs.py", "check_checklist_guard 钉住『硬超时』『超时的处置』两要点仍在（否则“派了就一直等”重新出现，实证为外部评审卡 1h+ 未回传）；『本次是否真的设了时限并在到点时放弃』属运行时行为，靠留证 + 人 review"),
    ("语义复核留证须是三态台账（通过 / 未发现问题 / 悬置，不得合并）", "specs/general/testing.adoc", "script/check_specs.py", "check_checklist_guard 钉住『三态』『悬置』两要点仍在；『具体某次留证是否真按三态分列』属产物内容判断，交人/子 agent 复核"),
    ("验证按改动性质取值（代码类走机械判据、规范类才做三视角与全局核对）", "specs/general/testing.adoc", "script/check_specs.py", "check_lifecycle_guard 钉住「验证的适用边界」节、两类改动、唯一判据问句、『不得互串』『取更严的一侧』与『每次验证换干净上下文』；『本次是否真按性质取值』属运行时行为，靠遵守 + 人 review"),
    ("规范何时该拆分（默认不拆、三条硬条件、拆后逐项自洽核对）", "specs-project-maintainer/spec-lifecycle.adoc", "script/check_specs.py", "check_lifecycle_guard 钉住「一条规范何时该拆分」与「拆分后的自洽核对」两节及三条硬条件、默认不拆、单独过准入九问；『某次拆分是否由实害驱动』属语义判断，交人/子 agent 复核"),
    ("执行环境能力先自评、无机制走降级路径且不空自评", "specs/general/self-check.adoc", "script/check_specs.py", "check_delegation_guard 钉住『环境能力自评』节仍在（否则环境无清空/无子 agent 时会照抄'已清洁上下文/已委派'）；'自评是否属实'属运行时行为，靠遵守 + 人 review"),
    ("常驻层体积与调度器条目数不得无上限膨胀", "AGENTS_COMMON.adoc", "script/check_specs.py", "check_budget_guard 钉住必加载层字节上限与调度器条目数上限；'体量与层级的语义是否合理'仍交人/子 agent 复核"),
    ("提示词主侧重（方向前提）与优先级不得被删/降级", "PROMPTS.adoc", "script/check_specs.py", "check_prompts_primary 钉住 PROMPTS.adoc 主侧重登记、各提示词 primary 声明与 priority-rules 的 L1/L2/L3"),
    ("执行前自检（非平凡任务须逐项自检，防'加载了却没执行'）", "specs/general/self-check.adoc", "script/check_specs.py", "check_self_check_guard 钉住自检规范文件、适用边界与 execution.adoc 必加载层落点；自检是否真做属运行时行为，靠 agent 遵守 + 人 review"),
    ("不得编造事实与来源（引用真实、标准不编、宁可不引）", "specs/general/source.adoc", "script/check_specs.py", "check_source_guard 钉住来源规范要点；引用存在性另由 check_refs_exist/check_section_refs 兜底"),
    ("不可逆操作先确认（删除/清空/强推，P5）", "specs/core/execution.adoc", "script/check_specs.py", "check_priority_guard 钉住 P5 存在性与「破坏性操作」落点；是否真确认属运行时行为，靠遵守 + 人 review"),
    ("换行符按解释器分流（LF 基准、.bat/.cmd 必须 CRLF、.gitattributes 固定）", "specs/general/encoding.adoc", "script/check_specs.py", "check_line_ending_guard 钉住编码规范的分流判据与 bash/python/powershell 栈文件的行尾要求；某文件实际是否为 CRLF 属引用方工作区状态，本仓库不可见，靠引用方 `git ls-files --eol` 自检"),
    ("代码安全底线（输入校验/输出编码/凭据不硬编码）", "specs/general/security.adoc", None, "无机械抓手：具体实现属引用方项目代码（本仓库不可见）；靠遵守 + 该项目的静态检查/SAST"),
]


def display_width(text: str) -> int:
    """按终端显示宽度计算字符串宽度（CJK 字符按 2 列计）。"""
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in text)


def _pad(text: str, width: int = NAME_WIDTH) -> str:
    """条款名右侧补空格到统一列宽，保证多行清单左对齐。"""
    return text + " " * max(0, width - display_width(text))


def evaluate(root: str = HERE) -> list:
    """逐条判定抓手状态。root 可注入以便测试（不依赖真实仓库）。"""
    rows = []
    for name, source, grip, note in MECHANISMS:
        if grip is None:
            status = "no-grip"
        elif path.isfile(path.join(root, grip)):
            status = "has-grip"
        else:
            status = "grip-missing"
        rows.append({
            "name": name, "source": source, "grip": grip,
            "status": status, "note": note,
        })
    return rows


def main(argv: list[str] | None = None) -> int:
    """命令行入口：解析参数、输出抓手清单并按 --warn 决定退出码。"""
    parser = argparse.ArgumentParser(
        description="『定义未执行』深度核验：列出规范强制条款对应的可执行抓手")
    parser.add_argument(
        "--warn", action="store_true",
        help="存在『无机械抓手』的强制条款时以退出码 1 退出（默认仅展示清单，始终返回 0）")
    args = parser.parse_args(argv)

    # 默认按仓库根（script/ 的上级）解析抓手相对路径
    root = path.dirname(HERE)
    rows = evaluate(root)
    by_status = {"has-grip": [], "no-grip": [], "grip-missing": []}
    for r in rows:
        by_status[r["status"]].append(r)

    print("定义未执行核验：规范强制条款 <-> 可执行抓手")
    print("=" * 70)
    print("\n[有机械抓手]（存在脚本/测试可检测或拦住）")
    for r in by_status["has-grip"]:
        print(f"  [+] {_pad(r['name'])} <-  {r['grip']} ({r['note']})")
    print("\n[无机械抓手]（定义未执行风险，仅靠遵守/人工）")
    for r in by_status["no-grip"]:
        print(f"  ! {_pad(r['name'])} --  {r['source']} ({r['note']})")
    if by_status["grip-missing"]:
        print("\n[抓手缺失]（声明了抓手但文件不存在）")
        for r in by_status["grip-missing"]:
            print(f"  !! {_pad(r['name'])} <-  {r['grip']} 不存在！")

    print("\n" + "=" * 70)
    print(f"共 {len(rows)} 条，有抓手 {len(by_status['has-grip'])}、"
          f"无机械抓手 {len(by_status['no-grip'])}、"
          f"抓手缺失 {len(by_status['grip-missing'])}。")
    if args.warn and by_status["no-grip"]:
        print("检测到无机械抓手的强制条款（--warn 触发非零退出）。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
