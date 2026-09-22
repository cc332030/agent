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

# 台账条目"没有机械抓手"的**唯一合法声明措辞**（有抓手条目须点名具体那一道防线或
# 工具/测试文件路径）。它与 `MECHANISMS` 同处——`script/check_specs.py` 的
# `check_guard_manifest` 会 import 它来核对"声明与实现是否一致"（常量定义在使用侧，
# 校验侧引用，避免两处各写一份字面值）。
NO_GRIP_DECLARED = "无机械抓手"

# 强制条款 → 可执行抓手映射。
# (条款名, 来源规范文件, 抓手相对路径[None=暂无机械抓手], 声明钉住本条的防线名, 备注)
#
# `grip_name` 是**逐条声明**：这条规范到底由哪一道防线钉住。它是本台账最容易被
# 改坏的一格——只写 `grip`（文件路径）时，判据是"script/check_specs.py 这个文件在不在"，
# 于是"有抓手 105"这个数字可以靠**把备注里的防线名删掉**来维持（删名字比删防线容易得多），
# 读者也会以为有抓手、而实际那一道早没了。
# 取值：有抓手条目填**具体那一道** `check_*_guard`（`check_guard_manifest` 会核它真实存在
# 且真的会被调用）；随规范分发的**工具文件**或配套测试文件等同理填其路径本身（须与 `grip`
# 一致、文件真实存在）；无抓手条目填「无机械抓手」（对应 `grip=None`）。同一道防线钉住
# 多条时逐条照写（不合并、不省略）。
MECHANISMS = [
    ("规范调整后须真正验证（要点防线）",       "AGENTS.adoc",                 "script/check_specs.py",
     "check_principle_guard",      "check_specs 的 check_principle_guard 校验该条仍存在"),
    ("内部链接须用相对路径、禁根绝对",           "specs/general/doc.adoc",           "script/check_specs.py",
     "check_link_refs",      "check_link_refs"),
    ("规范引用文件必须真实存在",                 "AGENTS.adoc",                 "script/check_specs.py",
     "check_refs_exist",      "check_refs_exist"),
    ("技术栈登记与文件一致",                     "AGENTS_COMMON.adoc",        "script/check_specs.py",
     "check_stack_consistency",      "check_stack_consistency"),
    ("私有工程约定不入全局规范",                 "specs/general/*.adoc",            "script/check_specs.py",
     "check_forbidden_patterns",      "check_forbidden_patterns"),
    ("不保留无用的历史来源声明",                 "AGENTS.adoc",                 "script/check_specs.py",
     "check_historical_notes",      "check_historical_notes"),
    ("禁止无意义/划水/凑字数的文档",            "specs/general/doc.adoc",           "script/check_specs.py",
     "check_filler_docs",      "check_filler_docs（占位段/完全重复段）"),
    ("文档须高质量（准确/完整/可执行/有价值/简洁/可验证）", "specs/general/doc.adoc",   "script/check_specs.py",
     "check_refs_exist",      "可验证性由 check_refs_exist/check_link_refs/check_section_refs 兜底，其余交人 review"),
    ("入口模板代码块逐字保留（换行/空行不丢失）", "AGENTS_COMMON.adoc", "script/check_specs.py",
     "check_install_codeblock",      "check_install_codeblock"),
    ("临时产物清理脚本可用",                     "specs/core/execution.adoc",       "script/clean_tmp.py",
     "script/clean_tmp.py",        "存在清理脚本"),
    ("完整性校验配套测试",                       "AGENTS.adoc",                 "script/check_specs_test.py",
     "script/check_specs_test.py", "20+ 用例"),
    ("定义未执行核验配套测试",                   "AGENTS.adoc",                 "script/check_effective_test.py",
     "script/check_effective_test.py", "本工具的自测"),
    ("变更日志只记影响、不记过程（重点优先、拒细枝末节）", "specs/general/changelog.adoc", "script/check_specs.py",
     "check_section_refs", "check_section_refs 钉住「应当记录/不应当记录/条目书写」三节引用不悬空；条目内容的详略判断交人 review"),
    ("发现的问题/事项备注落点与表述按适用范围判定（全局性问题不进范围性落点，全局备注也不夹带范围性内容）", "specs/general/review.adoc", "script/check_specs.py",
     "check_review_guard", "check_review_guard 钉住判据条与两个方向的约束（去限定词后仍成立=全局性 / 只有某一处能触发=范围性 / 全局性问题不得写进范围性落点 / 全局备注不夹带范围性内容 / 范围性问题不上升为全局规范）仍在，并要求必加载层执行原则与 doc-design「信息归属」两处引用未断；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("文件移动/重命名必须 git mv（防历史断裂）", "specs/core/execution.adoc",       "script/check_specs.py",
     "check_git_mv_selfcheck",      "check_git_mv_selfcheck 覆盖**本仓库自身侧**（暂存区不得出现 delete+add 形态）；**引用方侧**本仓库看不到、仍靠遵守 + 各项目按 git 规范自检"),
    ("测试文件后缀式命名（禁 test_ 前戳）",       "specs/general/testing.adoc",      None,
     "无机械抓手",
     "无机械抓手：靠遵守；Java 测试类另须与源类同包路径、类名为「被测类名 + 测试类型后缀」（specs/stack/java-testing.adoc「测试类命名」：Tests/BootTests/PerfTests/IT），存量为随动迁移、不一次性收敛（specs/core/execution.adoc「规范变更的存量处理」）"),
    ("Java 测试类四类后缀命名契约（Tests/BootTests/PerfTests/IT）", "specs/stack/java-testing.adoc", "script/check_specs.py",
     "check_java_test_naming", "check_java_test_naming 钉住规范与 AGENTS_COMMON 调度器登记两侧都含四类后缀判据；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("Java 测试类拆分裁决（一个被测类可拆多个类，但同分类同属性须归一类、不得滥拆）", "specs/stack/java-testing.adoc", "script/check_specs.py",
     "check_java_test_naming", "check_java_test_naming 钉住规范侧三段判据（可拆声明 / 同分类同属性须归一类 / 禁止滥拆）与调度器侧同口径——「可拆但不得滥拆」是单一语义，只剩一半即被读成『每个场景一个类』或『一个被测类一个类』；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("校验范围只限公共内容与本仓库工具（不检查引用方项目工作区）", "AGENTS.adoc", "script/check_specs_test.py",
     "script/check_specs_test.py", "TestScopeStaysOnCommonContent 钉住 check_specs.py 不得读 git 工作区状态/HEAD"),
    ("最高关注项不得被删或降级（P1/P2/P3/P5/P6 条款 L1、P4 条款 L2、同列最高关注项）", "specs-project-maintainer/priority.adoc", "script/check_specs.py",
     "check_priority_guard", "check_priority_guard 钉住公共侧分级定义与最高关注项（含保留形态）、维护方侧 P1-P6 各自级别与『依据』行（P6 另钉正文口径：强制同 Agent 须在、旧口径『换外部来源』不得复活），以及 P1/读取/破坏性操作/来源真实性的必加载层落点；『条目级别是否与其实际后果相符』无机械抓手（等级越高验证越严：ISO/IEC Directives Part 2），由人/子 agent 复核承担"),
    ("定级口径（定级四问 + 条款类型判定表）不得被删", "specs-project-maintainer/spec-lifecycle.adoc", "script/check_specs.py",
     "check_spec_admission_guard", "check_spec_admission_guard 钉住『如何给一条规范定级』『与条款类型一一对应』『归属谁』『归类举证』『级别变更与复盘』五个节仍在（口径被删则级别重新混乱）"),
    ("定级方法论与元规范不得涨回常驻层（常驻层只放 L1 底线与最高关注项）", "specs-project-maintainer/priority.adoc", "script/check_specs.py",
     "check_priority_guard", "check_priority_guard 拦住常驻层再次出现『设级别』等定级方法论节；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("规范集合自身重构须按固定顺序（先判归属 → 再判层级 → 再判重复 → 压缩表述）", "specs-project-maintainer/spec-lifecycle.adoc", "script/check_specs.py",
     "check_spec_admission_guard", "check_spec_admission_guard 钉住重构顺序三要点仍在（顺序颠倒会把放错位置的内容直接删掉）"),
    ("同一条规则的两种读法（执行侧只给'怎么走'、依据与取舍归思考/决策侧）", "specs-project-maintainer/spec-lifecycle.adoc", "script/check_specs.py",
     "check_spec_admission_guard", "check_spec_admission_guard 钉住「同一条规则有两种读法」节；常驻层侧由 check_priority_guard 钉住『怎么走』形态声明与各最高关注项的『依据』行（依据不得被整段删掉）；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("重构后须核对规范有效性（两形态分离 / 可执行性不降级 / 可见性不丢）", "specs-project-maintainer/spec-lifecycle.adoc", "script/check_specs.py",
     "check_spec_admission_guard", "check_spec_admission_guard 钉住「重构后须核对规范有效性」节；判据是否真未被压成口号语义判断（见 GUARD_CHECK_LIMITS）"),
    ("读取按最小必要、长会话简单任务在干净上下文执行（P4）", "specs/core/execution.adoc", "script/check_specs.py",
     "check_priority_guard", "check_priority_guard 钉住 P4 存在性与 execution.adoc 对 context.adoc 的引用；运行时事实（见 GUARD_CHECK_LIMITS）"),
    ("去重不得误删最高关注项的引用", "AGENTS.adoc", "script/check_specs.py",
     "check_priority_guard", "check_priority_guard：最高关注项的存在性机械钉住（引用是否被删由该防线兜底发现）"),
    ("从属者（子 agent/被引用方）加载由已加载入口驱动、不靠自报", "AGENTS_COMMON.adoc", "script/check_specs.py",
     "check_delegation_guard", "check_delegation_guard 钉住『从属者』机制仍在（否则子 agent/被派发任务可'没被告知'为由跳过加载）；运行时事实（见 GUARD_CHECK_LIMITS）"),
    ("改完规范须验证三视角：①完整性 + ②有效性与认知质量 + ③接纳面（同一子 agent）", "specs/general/verify.adoc", "script/check_specs.py",
     "check_verify_guard", "check_verify_guard 钉住公共「验证总纲」「规范验证」「验证的效力等级」「验证的适用边界」「运行契约」各节、三视角与标准出处、②的判据、'三视角合用一个干净子 agent'、'每次验证换干净上下文'，并核对维护方落点两处口径一致；运行时事实（见 GUARD_CHECK_LIMITS）"),
    ("验证须能枚举\"验了什么、怎么算过、依据哪个标准\"（防退化成跑绿脚本、慢慢脱离初衷）", "specs/general/verify.adoc", "script/check_specs.py",
     "check_verify_guard", "check_verify_guard 钉住「验证总纲」节与标准出处（ISO/IEC Directives Part 2 / RFC 2119 / ISO 10007 / ISO/IEC/IEEE 25010 / IEEE 1028 须在）；运行时事实（见 GUARD_CHECK_LIMITS）"),
    ("公共内容不得声明机械防线的存在（防线属维护方、随规范分发即宣称与实际不符）", "specs-project-maintainer/spec-lifecycle.adoc", "script/check_specs.py",
     "check_no_mechanism_claims_in_public", "check_no_mechanism_claims_in_public 拦住『当前由某防线钉住』式声明句与裸防线名；该表述是否真在宣称防线由人/子 agent 复核"),
    ("公共内容须自足：不得引用引用方看不到的私有落点（一个文件可同时装公共与项目规则）", "AGENTS_COMMON.adoc + specs/", "script/check_specs.py",
     "check_public_content_is_self_contained", "check_public_content_is_self_contained 机械拦住公共内容里指向维护方自查层（specs-project-maintainer/）的引用——该层不随公共内容分发，引用方读到的只是死链；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("公共内容被未知项目加载时的可控性（影响面/成本/可控性）", "specs/general/verify.adoc", "script/check_specs.py",
     "check_adoption_guard", "check_adoption_guard 钉住「运行契约」节、三维判据与维护方承接清单登记；另由 check_public_content_has_no_private_refs 机械拦住\"公共内容把本仓库私有物当抓手引用\"（引用方读到的死链）；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("任务各节点须自查（提出/理解/方案/执行/验证/交付/复盘）", "specs/core/execution.adoc", "script/check_specs.py",
     "check_lifecycle_guard", "check_lifecycle_guard 钉住节点清单以表格行存在、并钉住『哪些节点不设』的独立声明；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("CI 校验链完整：流水线须跑全既定校验（含配套测试），测试文件须能被框架自动发现", "specs/general/ci-cd.adoc", "script/check_specs.py",
     "check_ci_cd_guard", "check_ci_cd_guard 钉住「校验链完整」节与『只跑主校验脚本』『能被测试框架自动发现』两要点（实证：CI 只跑 check-specs.py，配套测试长期零执行、其中一个测试文件因命名无法被自动发现）；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("校验手段依赖的工具须在本地实际装齐、不得因缺工具而静默跳过（声明的校验手段不得『从未执行却报绿』）",
     "specs/general/ci-cd.adoc", "script/check_specs.py",
     "check_toolchain_present_guard",
     "check_toolchain_present_guard 钉住三处落点同口径（公共条文 `specs/general/ci-cd.adoc`「校验链完整（定义未执行防线）」的条文本体/L1/判定标准/降级路径/安装方式 + 本仓库落点 `AGENTS.adoc` 点名 `check_asciidoctor_syntax`、缺工具即报错与安装命令 + CI 的安装步骤**与同一步骤内的装后校验**——按「登记处只留一层」的口径，处理器次序与效力边界只由公共条文承载、本仓库落点不复述，CI 判据按**每步实际执行的命令**取值、不看步骤名与注释），并钉住 `check_asciidoctor_syntax` **缺处理器即报错**（不再走『跳过』分支）、覆盖范围与 `collect_adoc_files` 同源（`_collect_adoc_files` 单一实现、根由 `ADOC_ROOTS` 给定）与 `--failure-level=WARN` 的效力边界；**本仓库实证**：脚本里写着 AsciiDoc 语法段、环境长期没有处理器、该段走跳过分支而 `check_specs.py` 始终报 OK；『某次是否真的装了工具、某台机器上装没装成』属运行时事实，交人/子 agent 实跑复核；本条为**新增**，台账条数 116→117（有抓手 114、无机械抓手 3，均含上游本轮删除 `check_orm_boundary_guard` 后的口径）。"
     "**本轮（Issue #173）补第二道**：`check_asciidoctor_stub_guard` 钉住『语法段不得只剩壳』"
     "——上面这道钉的是探测代码与 CI 安装步骤的**文本**，而『真的编了每一份 .adoc』本身"
     "没有 CI 级断言：实测把 `check_asciidoctor_syntax` 的函数体换成 `phase(...); "
     "phase_done(); return 0` 后脚本仍报 OK、本道照样全绿（探测代码不在那个函数里）。"
     "新道把『函数体真的探测 + 缺工具即 `err(` + 按 `ADOC_ROOTS` 逐个 `_adoc_compile_cmd`』"
     "与『CI 有一步真的执行 `check_specs.py`』变成可核对的；『某次 CI 里那 N 份 .adoc "
     "真的都被编译了』仍属运行时事实，交人/子 agent 复核"),
    ("CI 触发路径须覆盖校验对象、上游依赖须实测可用、执行须有可判定超时", "specs/general/ci-cd.adoc", "script/check_specs.py",
     "check_ci_cd_guard", "check_ci_cd_guard 钉住「触发与作用范围」「依赖与外部资源可用性」「超时与资源」关键要点（实证：引用不存在的镜像在 Prepare 阶段失败、流水线长期 pending）；『具体取值是否合理』交人 review"),
    ("平台上的派发与复核须钉定 commit sha（分支名不是稳定标识）、确认执行者可用", "specs/platform/cnb.adoc + specs/general/collab.adoc", "script/check_specs.py",
     "check_ci_cd_guard", "check_ci_cd_guard 钉住 CNB 侧『派发与复核须钉定 commit sha』『压缩提交/强推会替换对象』『git fetch -f』『派发前确认执行者实际可用』『流水线不无界挂起』与 collab 侧『派发对象须钉定 commit sha』『派发前确认执行者可执行』；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("验证须覆盖项目全部既定校验手段、验证对象须钉定 commit sha", "specs/general/verify.adoc", "script/check_specs.py",
     "check_ci_cd_guard", "check_ci_cd_guard 钉住验证侧『验证须覆盖项目的全部既定校验手段』『验证对象须钉定 commit sha』两要点；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("子 agent 复核须自带硬超时、到点视为失联并放弃（防任务永久挂起）", "specs/general/collab.adoc", "script/check_specs.py",
     "check_checklist_guard", "check_checklist_guard 钉住『硬超时』『超时的处置』两要点仍在（否则“派了就一直等”重新出现，实证为外部评审卡 1h+ 未回传）；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("子任务强制同 Agent、不得点名外部 Agent/NPC", "specs/general/collab.adoc", "script/check_specs.py",
     "check_delegation_guard", "check_delegation_guard 钉住五处要求的多要素（同 Agent 判据 / 不得点名外部 NPC / 可核对的判定标准 / 同 Agent 不可用时的降级路径 / 优先一次性调用）仍在，并**双向**钉住口径：新口径须在、把外部来源重新放宽的旧口径措辞（备选/次选/(也)可换外部/优先同源）不得复活（含清单概览行与公共侧各落地处，禁止式表述与反例引用除外）；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("语义复核留证须是三态台账（通过 / 未发现问题 / 悬置，不得合并）", "specs/general/verify.adoc", "script/check_specs.py",
     "check_checklist_guard", "check_checklist_guard 钉住『三态』『悬置』两要点仍在；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("验证按改动性质取值（代码类走机械判据、规范类才做三视角与全局核对）", "specs/general/verify.adoc", "script/check_specs.py",
     "check_lifecycle_guard", "check_lifecycle_guard 钉住「验证的适用边界」节、两类改动、唯一判据问句、『不得互串』『取更严的一侧』与『每次验证换干净上下文』；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("规范何时该拆分（默认不拆、三条硬条件、拆后逐项自洽核对）", "specs-project-maintainer/spec-lifecycle.adoc", "script/check_specs.py",
     "check_lifecycle_guard", "check_lifecycle_guard 钉住「一条规范何时该拆分」与「拆分后的自洽核对」两节及三条硬条件、默认不拆、单独过准入九问；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("执行环境能力先自评、无机制走降级路径且不空自评", "specs/general/self-check.adoc", "script/check_specs.py",
     "check_delegation_guard", "check_delegation_guard 钉住『环境能力自评』节仍在（否则环境无清空/无子 agent 时会照抄'已清洁上下文/已委派'）；运行时事实（见 GUARD_CHECK_LIMITS）"),
    ("常驻层体积与调度器条目数不得无上限膨胀", "AGENTS_COMMON.adoc", "script/check_specs.py",
     "check_budget_guard", "check_budget_guard 钉住必加载层字节上限与调度器条目数上限；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("单个规范文件的软阈值（超线只提醒、不强制拆分）",
     "specs-project-maintainer/spec-lifecycle.adoc「单个规范文件的软阈值」",
     "script/check_specs.py",
     "check_file_size_hint",
     "check_file_size_hint 钉住『超线须有提示』且『**不得**进 errors/退出码』两件事（提醒与硬上限的分界）、"
     "范围边界（常驻层与图书馆不吃本阈值）；"
     "『某个超线的文件到底该归位、该拆、还是确实不拆』属体量/层级的语义判断"),
    ("提示词主侧重（方向前提）与优先级不得被删/降级", "PROMPTS.adoc", "script/check_specs.py",
     "check_prompts_primary", "check_prompts_primary 钉住 PROMPTS.adoc 主侧重登记、各提示词 primary 声明与 priority-rules 的 L1/L2/L3"),
    ("对外能力的可替换点须有唯一装配点、须有可用默认（接入成本是设计指标）", "specs/general/coding.adoc", "script/check_specs.py",
     "check_abstraction_adoption_guard", "check_abstraction_adoption_guard 钉住「抽象与接入成本」节的两条 L1（唯一装配点、可替换点须有可用默认或显式必填声明）与其判定特征、四条要点齐全、L1/L2 级别标注、依据行在、Spring「配置」侧引用承接；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("既有实现与先例优先（先查项目已有能力与先例，禁止手写原生写法绕过）", "specs/general/coding.adoc", "script/check_specs.py",
     "check_reuse_precedent_guard", "check_reuse_precedent_guard 钉住通用层两条 L1 条文与典型反例（UUID 手写、集合判空手写）、Java 栈 java-syntax.adoc 优先级顺序（项目自有/已引入库须排在 JDK 之前）、java.adoc 的识别特征与 README 同步；『某次编码是否真的先查了先例』语义判断（见 GUARD_CHECK_LIMITS）"),
    ("跨语言执行脚本须放资源文件夹、扩展名取被调语言的扩展名，且按性能敏感度决定读取时机（不写字符串拼接/模板、热点路径不每次读）", "specs/general/coding.adoc", "script/check_specs.py",
     "check_external_script_guard", "check_external_script_guard 钉住通用层「跨语言执行脚本的落点（资源文件夹，不写字符串拼接/模板）」的四条 L1（落点／扩展名取被调语言，无通用扩展名时取该技术支持的文件形式如 MyBatis 的 `*.xml`／按资源读取后执行／加载时机：性能敏感路径首次读取一次并缓存、需求要求内容可变的不适用缓存）、可逐条核对的判定标准与典型反例、依据行，以及 Java 落点（`sql`/`lua` 放 `src/main/resources/`、Redis 用 `DefaultRedisScript` 按静态常量声明、MyBatis 的 `${}` 白名单、`EVALSHA` 复用）与 Java 侧加载时机、Spring 引用承接、调度器两处登记与 README 同步；『某次编码是否真的把脚本放进了资源文件夹、是否真的只读一次』语义判断（见 GUARD_CHECK_LIMITS）"),
    ("本仓库 changelog 的默认动作是不新增、不修改：用户本次明确要求才写（不再要求『主动声明』这种额外声明），"
     "未要求时一律不写、不改；用户要求移除时删指定条目、保留其余与既有版本号不动、不得自造新版本号顶上",
     "AGENTS.adoc「版本与变更记录」", "script/check_specs.py",
     "check_changelog_timing_guard",
     "check_changelog_timing_guard 钉住本仓库的默认动作条（默认动作是不新增、不修改／不再要求『主动声明』这种额外声明，用户直接说『记一条/改 changelog』即算）"
     "、未要求的越界形态（未提到该文件／只要求更新文档或 README／只说『改动了什么』／只要求『调整项目规范』）"
     "、顺手补一条、用户要求移除时的处置（删指定条目、既有版本号不动、不得自造新版本号顶上，含防『同版本号换个说法记一遍』）"
     "以及与抓手登记；『某次是否真的自行新增或改写了条目、用户要求到底成不成立』"
     "属运行时行为与语义判断（提交内容与评论记录），机械无法判定"),
    ("规范保持通用（规则与实例分离）：本仓库默认不写实例——用户原话、本机路径、`tmp/` 文件名、轮次与日期、内部代号"
     "一律不进规范文件、公共内容与提示词；实例只登记在图书馆（`library/adoption.adoc`／`library/sources.adoc`）与 `CHANGELOG.adoc`",
     "AGENTS.adoc「规范组织与自身重构（本仓库落点）」", "script/check_specs.py",
     "check_rule_instance_separation_guard",
     "check_rule_instance_separation_guard 钉住本仓库该条（**规范保持通用**／默认动作是「不写」／实例的登记落点／失效形态与出处）"
     "与它在 check_effective 的登记；『某条新加的判据里到底有没有夹带实例』属语义判断（实例是自由文本），"
     "机械核不出来，交人/子 agent 复核"),
    ("规则以对象定义、不给具体操作：写规范时只定义「是什么、取什么值」（取值写成带占位符的形态，如 `mvn -T <核心数>`），"
     "「这个量怎么得到」属执行动作、不进规范；新增、修复、review 三类动作都按此判定，例外只在按定义做不出唯一动作时开口",
     "specs-project-maintainer/spec-lifecycle.adoc「以对象定义规则、不给具体操作」", "script/check_specs.py",
     "check_declarative_rule_guard",
     "check_declarative_rule_guard 钉住本条判据本体（定义与取法的分界／只定义取值不定义取法含三条判定标准／"
     "兜底不写具体写法／例外只在有歧义时开口／生效面为新增·修复·review／抽掉专有名词的判定标准／依据行），"
     "并核两处已按新口径收敛的落点（`specs/stack/maven.adoc` 与 `prompts/_common.txt` 的 `build-parallel` 片段）；"
     "『某条新写的规则里到底算不算多写了取法』属语义判断（见 GUARD_CHECK_LIMITS），交人/子 agent 复核"),
    ("Java 序列化：已实现 `Serializable` 的类型须显式声明 `serialVersionUID`（缺省 `1L`）、局部变量优先 `val`、链式调用一律换行",
     "specs/stack/java.adoc「序列化（`Serializable`）」+ specs/general/coding.adoc「表达式与调用写法」",
     "script/check_specs.py",
     "check_java_serial_guard",
     "check_java_serial_guard 钉住三处判据本体（不是轴名——只核『这几节在不在』属防线空转）：① 序列化——已声明实现 `Serializable` 的类型**必须显式声明** `serialVersionUID`（含父类已实现）、`lombok.config` 实时取值、缺省 `1L`、`@Serial`（JDK 14+）、**不得为未实现者补字段或顺手加 `implements Serializable`**、不得以抑制代替显式声明、判定标准与存量口径、依据行含『1L 属本集合取值』；② 局部变量——**优先 `val`、确实可变才 `var`**（`var` 是例外档不是并列选项）、用 `var` 却没重新赋值即违规、例外与未引入 lombok 时按 `var` 兜底、字段不得使用、依据与『属本集合取值』定性；③ 链式调用——**一律换行、长度不是判据**、同行两处及以上环节即违规、例外、只改形态不改语义的边界、依据与『严于通行风格（按行宽）』定性；并钉调度器三处识别特征（含通用层『所有语言』）与图书馆两处依据落点。**本条防的不是『没写规则』而是『写了规则却仍留裁量点』**——裁量点（要不要加 UID / `val` 还是 `var` / 多短算短）留给临场发挥时，同一项目里会并存两种形态；『某个类该不该算已实现 `Serializable`、某条链是否真的拆到了每一环节』属语义判断（见 GUARD_CHECK_LIMITS）"),
    ("弃用类/API 一律改用替代者（替代者优先取升级类/同名新类），且默认不动依赖与版本",
     "specs/general/coding.adoc「警告与弃用」+ specs/general/dependency.adoc「升级与废弃」",
     "script/check_specs.py",
     "check_deprecated_api_guard",
     "check_deprecated_api_guard 钉住两处**同向**落点的判据本体（不是轴名——只核『警告与弃用』这一节在不在属防线空转）："
     "① 代码侧 `coding.adoc`——**不得使用被弃用的类/API、须改用替代者**（标识弃用的形态：`@Deprecated`/`deprecated`/文档标注废弃）、"
     "**替代者优先取升级后的新类、或同名新类**、判定标准三条（直接使用弃用者／以『旧写法也能跑』自我豁免／替代者选成同类弃用者）、"
     "例外（替代者在依赖面内不存在时写明理由保持原状）与 **『默认不调整依赖、也不动依赖版本』**；"
     "② 依赖侧 `dependency.adoc`——**弃用迁移默认不动依赖面**并回指 `coding.adoc`、判定标准（改动里出现依赖清单/版本变化却未走升级流程即违规）；"
     "另**单独拦**『存量条（内部弃用不迁移）未写明不构成对新代码的豁免』——两条同处一节，后条抵消前条是最易发生的读法。"
     "**本条防的不是『没写规则』而是『替代者取向被抽掉、或借迁移顺手改依赖版本』**——"
     "『某个类算不算被弃用、某个替代者是否等价』属语义判断（见 GUARD_CHECK_LIMITS）"),
    ("Java 字段接口只加 get、不加 set（只约束接口；下游可能加 `@Accessors(chain = true)`，接口里的 setter 会让下游编译不过）",
     "specs/stack/java.adoc「编码」", "script/check_specs.py",
     "check_java_interface_accessor_guard",
     "check_java_interface_accessor_guard 钉住 Java 栈「编码」的**判据本体**（不是轴名——只核『这一节在不在』属防线空转）：**只约束接口**（`interface` 与「类不适用本条」须同现——判定面被放大到类上会把正常的 lombok setter 判红）、**允许 get / 禁止 set** 两侧、**理由与后果**（下游可能加 `@Accessors(chain = true)` ⇒ **编译不过**——缺则读者不知道要防什么，遇到『接口不加 set 怎么写入』会把 setter 补回去）、**判定标准四条**（接口里声明了 set，含接口上的 lombok 访问器注解 / 以『没法写入』为由补 setter 而未走主动声明 / 自我豁免）、**存量口径**（用户点名『已经有的不管，也不告警』：不视违规、不告警、不整改、随动迁移）、**豁免面与范围**（除非主动声明、仅对该处生效、不得泛化）与依据行，并反向钉住通用层不得出现框架专名 `@Accessors`、技术栈层是判据的唯一落点；另钉调度器识别特征、README 同步与图书馆两处落点。**本条防的不是『没写规则』而是『判定面被放大或理由被抽掉』**——『某个接口算不算字段接口』属语义判断（见 GUARD_CHECK_LIMITS）"),
    ("Java 数据对象模板：新建时整段照抄；补注解不加 `@Accessors`、无参不加 `@AllArgsConstructor`、集合默认加 `@Singular`",
     "specs/stack/java.adoc「编码」+ specs/stack/java-object.adoc（模板文件）", "script/check_specs.py",
     "check_java_object_template_guard",
     "check_java_object_template_guard 钉住两处结构：① **模板文件** `specs/stack/java-object.adoc`（**模板、不是规范文件**——"
     "『要么不读、要么整份读完』的整段清单）须写明自身定位与触发特征（『没有以上目的时不加载』）、五项注解齐备、"
     "**三条照抄约定各自回指判据本体**（取值只列一次、理由与判定标准只在 `specs/stack/java.adoc`「编码」写一份："
     "模板文件自称『不重复那些判据』，在此再抄一份即第二真源；**两档生效面取值与依据行亦只回指、不复述**）；"
     "② **判据本体**在 `specs/stack/java.adoc`「编码」的『数据对象模板』条**自己的正文里**，本条承载三处取值的取值/机制/判定标准；"
     "**核对面须防兜底**：按整份文件核时同文件相邻条目的同样字样会兜住缺项、按整条 bullet 核时同一 bullet 末尾的"
     "依据行会兜住清单缺项——故取『条目正文』与『清单句』两级（`bullet_tokens` 的 `anchor`/`until`）；"
     "**模板侧另有反向核对**（`file_forbidden`）：机制、判定标准、取舍声明与两档生效面取值**不得**在模板侧再抄一份；"
     "③ 加载门（调度器技术栈层登记 + 识别特征）与 README 目录说明（须写条目名 + 『模板文件、非规范文件』，只留子串会被路径兜住）。"
     "**本条防的是『模板文件被并回规范』『判据本体被抽走只剩一份清单』『取值在模板侧另抄一份』三种失效**——"
     "『某个类算不算数据对象、代码里到底标没标这些注解』属语义判断与运行时事实（见 GUARD_CHECK_LIMITS）"),
    ("Maven 未配置过仓库/镜像且外网出口 IP 在中国大陆时，须用指定中央仓库",
     "specs/stack/maven.adoc",
     "script/check_specs.py",
     "check_maven_mirror_guard",
     "check_maven_mirror_guard 钉住该节仍在、指定仓库地址、**触发前提**（未配置过 Maven 仓库/镜像"
     "**且**外网出口 IP 在中国大陆——两半缺一即等于放行，只写『未配置过才做』会被读成无条件）、"
     "优先用该仓库、换源边界（**仅当它不可用**才可改用**在境内**的其他镜像站——该限定缺位即等于放行境外源）"
     "与『已配置过即不做』；配置方式不在本规范约定（按 Maven 官方机制自行完成），"
     "**实际是否真的用上了该仓库**属引用方运行时事实（构建日志与环境配置，本仓库不可见）"),
    ("Maven 既有的构建并行度配置以配置为准，没配过时默认按核心数启用多线程构建",
     "specs/stack/maven.adoc「构建并行度」",
     "script/check_specs.py",
     "check_maven_parallel_guard",
     "check_maven_parallel_guard 钉住该节仍在、默认值口径（没配过就默认开 `-T`、**取值按当前构建设备的核心数**"
     "——**不得写死 `-T 1C`**，`C` 是 core multiplied、不必然等于当前设备核心数）、"
     "既有配置优先（`.mvn/maven.config` 优先探测、不得覆盖不得重复追加）、并行只到模块粒度、"
     "构建并行与测试并行是两件事（`forkCount`/`reuseForks` 显式写）与依据名，"
     "以及三处落点（调度器识别特征、图书馆官方原文与本站取舍、提示词公共片段 `build-parallel` 与两个提示词的引入）"
     "——缺『以配置为准』这一半时执行者会去改引用方的构建配置（用户点名要防的一面）；"
     "**『某次构建到底有没有真的并行、取了几核』属引用方运行时事实（构建日志与命令，本仓库不可见）**"),
    ("性能测试：测量须可核对（离散度与样本量、公平比较、计时区间与消费结果）、记录须有落点（方案组合与成绩、优化日志、瓶颈归因与方向、迭代至收敛）",
     "specs/general/testing.adoc「性能测试」",
     "script/check_specs.py",
     "check_performance_guard",
     "check_performance_guard 钉住该节仍在、测量那一半（对比测试含当前实现作基准／排除初始化干扰／测量口径可核对／"
     "至少 3 次有效采样并报离散度且差异小于离散度视为无显著差异／公平比较／计时区间与消费结果／按性能敏感度判定是否要做）、"
     "记录那一半（落点／每次运行的必留证据四项／成绩取数与方案组合矩阵／优化日志／只记结果不记过程／闭环迭代至收敛／"
     "瓶颈归因与方向／结论落点与时效／优化不得改变行为）与两处落点（调度器加载项与识别特征、Java 栈的承载与执行边界）、"
     "以及图书馆依据主题 library/performance.adoc（JMH 与 ISO 编号＋本站取舍的分界锚点）；"
     "**本条只钉要点文本仍在**——『某次测试到底采了几次、成绩是不是真的可复现、有没有真的回头复测瓶颈』"
     "语义判断（见 GUARD_CHECK_LIMITS）"),
    ("代码质量（新产出即高质）：十项逐条自检须可判定（坏味道/职责与嵌套/命名/可读性/失败与边界/资源/并发/性能退化/测试与文档/交付前自检）",
     "specs/general/coding.adoc「代码质量（新产出即高质）」",
     "script/check_specs.py",
     "check_quality_guard",
     "check_quality_guard 钉住该节仍在、十项要点与判定标准、存量边界与依据行，以及调度器识别特征与图书馆依据主题 library/quality.adoc（坏味道与可读性依据＋同义性差异与取样状态）；"
     "「失败与边界」那一项的**条件例外**（`Enum.valueOf` 一类查找式 API 允许空 `catch`：准入三条 + 两类扩大方向的排除）另由 `check_java_enum_valueof_catch_guard` 逐条钉住（判据本体在本条、Java 落点与加载门在那边）；"
     "**本条只钉要点文本仍在**——『某次交付的代码质量到底过不过』语义判断（见 GUARD_CHECK_LIMITS）"),
    ("生成效率：先定完成判据、一次做对做完、延后验证一次到位、失败一次查根因、按需读取、不重做已做完的事",
     "specs/general/context.adoc「生成效率（同等质量下最少往返）」",
     "script/check_specs.py",
     "check_generation_efficiency_guard",
     "check_generation_efficiency_guard 钉住该节仍在、十条要点与其判定标准（含『本轮交付之后是否需要再改同一批文件』的运行判据）、"
     "**边界条『效率不得越过质量』**与调度器识别特征；"
     "**本条只钉要点文本仍在**——『某次任务到底跑了几轮、有没有把可合并的动作拆开、有没有靠重试撞对』运行时事实（见 GUARD_CHECK_LIMITS）"),
    ("token 纪律：利用率与节省不是一回事；输入须被用到、约束放外部、少复述多引用、不重复读贴、只记结论与取值；以不损害功能完整性/代码质量/验证完整为前提",
     "specs/general/context.adoc「token 纪律（提高利用率与节省开销）」",
     "script/check_specs.py",
     "check_generation_efficiency_guard",
     "check_generation_efficiency_guard 钉住该节仍在、概念区分的三句（不是一回事／手段大幅重叠／两者的取向）、"
     "利用率判据（答不出用途即无效输入）、约束放外部、少复述多引用、不重复读贴、只记结论与取值，"
     "**以及边界条『三件事不得为省 token 让步』（功能完整性／代码质量／验证完整）**与『不设必须量化 token 的要求』；"
     "**本条只钉要点文本仍在**——『某次任务有没有为省 token 少给信息、有没有复述已知内容』属产物内容与运行时行为"),
    ("改动后的 review：每次改动都在同一轮内复核一次（按改动性质取值；规范类按五件事）",
     "specs/general/review.adoc「改动后的 review（每次改完都得复核一次）」",
     "script/check_specs.py",
     "check_after_change_review_guard",
     "check_after_change_review_guard 钉住该节仍在、『每次』与『按性质取值』、改完即审的固定动作（跑机械手段／比基线／核原话／留证）、"
     "『规范类改动不得只跑机械手段』与复核者不可用时的处置，以及依据行（IEEE 1028 / ISO 10007）；"
     "**本条只钉要点文本仍在**——『某次改动到底有没有复核、跑没跑机械手段』运行时事实（见 GUARD_CHECK_LIMITS）"),
    ("精炼性：同一描述只写一处（重复面是必查项、收敛形态、与内容不减少的边界）",
     "specs/general/review.adoc「精炼性（同一描述只写一处）」+ prompts/_common.txt `delivery` 片段",
     "script/check_specs.py",
     "check_refinement_guard",
     "check_refinement_guard 钉住**判据本体**七组要点（重复面是必查项 L1 且与『没查过』分得清／判定标准『以完整表述出现』『改一处要记得改 N 处』／收敛形态『一处完整定义 + 其余位置只留一行引用』／与 P3 的边界『删的只能是重复表述、须留下可达的引用、无法确定的一律保留』／两类不得被当成重复收敛（最高关注项与其引用、各自的承接）／篇幅与重复是两件事／依据行 ISO 10007 与 ISO/IEC/IEEE 29148），并钉住**两处动作落点**——① 改完即审的固定动作里要真的核重复面（否则精炼性于每次改动都不生效）② 提示词公共片段 `delivery` 的「重复面的处理」（review/refactor 两个提示词都 include，一处维护两处生效）；"
     "**机械抓手两道**（都在 `script/specs-rules/duplicate.toml`，阈值与例外理由写在规则数据里）：`check_duplicate_scan_guard`（逐字重复扫描——全仓逐字重合超阈值即报红，**是下界**）与 `check_pointer_no_verbatim_guard`（**自称回指的行不得同时复述取值**——补前者的下界：阈值 40 只报『长度极显著』的重合，而回指句顺手抄取值的公共子串常只有二十几字，前者核不出来）；"
     "**本条只钉要点文本仍在**——『这次到底查了几处、收敛了哪些、有没有把必要内容当重复删掉』语义判断（见 GUARD_CHECK_LIMITS）"),
    ("信息密度：每句须承载（与「精炼性」的分工、判定标准、与 P3 的边界、适用面、依据行）",
     "specs/general/doc.adoc「信息密度（每句须承载）」+ library/sources.adoc「GB/T 7713 系列」",
     "script/check_specs.py",
     "check_info_density_guard",
     "check_info_density_guard 钉住**判据本体**七组要点（与「精炼性」的分工『同一描述有几处』对照『单处里有多少句是废话』且明写『仍可能通篇是废话』／每一句都要有承载 L2 含四条判定标准『复述·空话·同义反复·可有可无的铺垫』／限定语不得降格为表意不明／与 P3 的边界『内容不减少优先』『只有这一句没有承载才是』『压成口号属违反 P3』／适用面『不适用于代码与测试断言』／存量随动迁移／依据行 GB/T 7713.2-2022、GB/T 7713.1-2025、ISO/IEC Directives Part 2、ISO/IEC/IEEE 29148），并钉住**两处入口互引**（`doc.adoc`「简洁」条正文里那半句、`review.adoc`「精炼性」的『与「信息密度」的分工』一行——只核节名不核这半句属防线空转）与**图书馆依据落点**（`library/sources.adoc` 的 GB/T 7713 系列主题段须含标准号、『已废止』换版关系与『同义性』取舍面）；"
     "**本条只钉要点文本仍在**——『某次产出里到底有没有废话』语义判断（见 GUARD_CHECK_LIMITS）"),
    ("SQL 写法（同表同类操作合并、独立成文件、带库名）",
     "specs/general/sql.adoc「SQL 写法」（SQL 写法的唯一真源；SQL 是跨语言写法，不埋在技术栈文件里）",
     "script/check_specs.py",
     "check_alter_merge_guard",
     "check_alter_merge_guard 钉住**判据本体**六组要点"
     "（规则本体「同类操作」的定义与「目标数据库支持」前提、合并不了时的例外与须写明原因、"
     "可逐条核对的判定标准、依据行 MySQL 官方文档、存量边界；"
     "**本轮追加一组**：**DML 合并 + 「用户主动写的除外」例外（不改、不告警）+ 例外只适用于 DML**"
     "（DDL 一定会锁表、故 DDL 侧无例外））"
     "与**加载门**（调度器**通用层**登记 `specs/general/sql.adoc` + 识别特征 `ALTER TABLE`/`.sql`/库名/`INSERT`、`specs/stack/java.adoc`「跨语言执行脚本（SQL / Lua 等）」的**一跳引用**、登记路径须能被取回脚本的 `specs/*.adoc` 清单解析命中——本轮实测的失效形态是「文件建对了、判据也齐，但登记与引用两处都没接上」，判据存在而执行者走不到它）、**图书馆依据落点**"
     "（`library/sources.adoc` 的 MySQL 官方文档条目（ALTER TABLE 与 Online DDL）"
     "与「官方材料并未规定必须合并」的同义性标注）"
     "——**同一事项只有一个真源**：用户追加的另两条写法（SQL 须独立成文件、写库名）"
     "及其依据**不在这里再钉一份**（判据本体由 `check_external_script_guard` 钉，见"
     "`specs-project-maintainer/spec-lifecycle.adoc`「新增规范的提案校验」的"
     "「同一事项不得留两处真源」）；只核「有没有这条」属防线空转；"
     "**本条只钉要点文本仍在**——「某条迁移到底该不该合并、有没有真的按表合并输出、"
     "某次改的是不是用户主动写的 DML」语义判断（见 GUARD_CHECK_LIMITS）"),
    ("改完规范必做五件事：机械手段必跑全、干净子 agent 三视角复核不可漏（有了就忽略、没有就加）、三态台账、复核者不可用时的降级留证",
     "specs/general/verify.adoc「改完规范必做的五件事（机械手段必跑，干净子 agent 复核不可漏）」",
     "script/check_specs.py",
     "check_after_change_review_guard",
     "check_after_change_review_guard 钉住该节仍在、五件事逐条（①机械手段先跑且跑全含『报红就地修复』②干净子 agent 三视角不可漏含『有了就忽略、没有就加』③三视角一次读取分栏④三态台账『不得合并』⑤降级路径『不得跳过复核／不得换外部来源／标注独立性边界』）、"
     "**只对规范类改动的边界**，以及维护方两处落点（specs-project-maintainer/verify.adoc 与 AGENTS.adoc）；"
     "**本条只钉要点文本仍在**——『某次到底跑没跑机械手段、有没有真的起一个干净子 agent、台账实际填没填』运行时事实（见 GUARD_CHECK_LIMITS）"),
    ("执行吞吐：独立调用须合并（禁试探式往返）、构建与校验输出一次取到、长流程不零信息空转",
     "specs/general/context.adoc「执行吞吐」",
     "script/check_specs.py",
     "check_throughput_guard",
     "check_throughput_guard 钉住该节仍在、L1 两条（独立调用必须合并＋试探式往返的判定标准／构建与校验的输出须一次取到）"
     "与 L2 五条（读到即沉淀、不重复读，**含判定标准『同一路径在一次任务里被读第二次即违规』**／"
     "缓存与镜像就近且**已配置过即不覆盖不重配**／长流程不留零信息等待）、"
     "常驻层两处引用（最高关注项段落与「任务编排与上下文管理」）与调度器识别特征；"
     "**本条只钉要点文本仍在**——『某次任务到底往返了几轮、有没有把可合并的调用拆成多轮』"
     "运行时事实（见 GUARD_CHECK_LIMITS）"),
    ("CNB 平台侧执行吞吐：一次唤起=一次完整加载、状态与用量按汇总先取再下钻、不空转等待",
     "specs/platform/cnb.adoc「执行吞吐（平台侧的两处特有代价）」",
     "script/check_specs.py",
     "check_throughput_guard",
     "check_throughput_guard 同时钉住平台侧该节仍在与四条要点（一次唤起=一次加载／"
     "状态先取汇总再下钻／不用零信息往返等长流程／AI 用量与请求明细是本平台的可观测面）；"
     "**本条只钉要点文本仍在**——『某次执行到底做了几轮状态查询、有没有空转等待』"
     "运行时事实（见 GUARD_CHECK_LIMITS）"),
    ("文档中提及类型优先写类名 + import（不写类全名）", "specs/general/doc.adoc", "script/check_specs.py",
     "check_doc_type_notation_guard", "check_doc_type_notation_guard 钉住通用层「注释与文档」下的该条（**L2**：先短类名、需要解析时在就近代码示例里写一条 import，不得用类全名充当标识）与三个必要情形（同名类冲突／无代码示例可承载 import／**该类型不在本仓库的 classpath 内**——即用户口径的『除非不在 classpath 才能写类全名』，写成『不在本仓库/本项目内』即偏严、classpath 内但属他仓/外部的类型会被误禁）、三个例外边界（路径与坐标不是类型名、字符串与配置里必须全限定的场合（@ConditionalOnClass 类名、main-class、反射按名加载、import 本身）、文档自身的文本引用）、不做存量一次性替换的口径；Java 栈「javadoc」的落点（含 {@link}/@see 成员引用与配置/反射照常全限定的边界）与调度器两处识别特征。**为 L2 且判据是语义的（java.util.UUID 一类外部类型全限定属合规），本防线只钉条文与判据仍在、不扫存量文档**——「某处到底该不该写全限定」交人/子 agent 复核"),
    ("无参/必参/全参构造优先用 lombok、不手写构造方法", "specs/stack/java.adoc", "script/check_specs.py",
     "check_lombok_constructor_guard", "check_lombok_constructor_guard 钉住 Java 栈「编码」的条文与 L1、三种构造注解（`@NoArgsConstructor`/`@RequiredArgsConstructor`/`@AllArgsConstructor`）、并存写法、可逐条核对的判定标准、例外（注解表达不了的动作才可手写并写明原因）与存量边界，以及调度器识别特征与 README 同步；措辞回退成建议（尽量用/可手写）亦被拦下。『某个具体类该不该手写构造』语义判断（见 GUARD_CHECK_LIMITS）"),
    ("数据库实体类不得作为接口的请求/响应参数（L1，跨语言；用户声明可豁免、存量不管）",
     "specs/general/coding.adoc「数据契约的载体（数据库实体类不进对外契约）」",
     "script/check_specs.py",
     "check_entity_dto_guard",
     "check_entity_dto_guard 钉住通用层「数据契约的载体（数据库实体类不进对外契约）」的**判据本体**"
     "（不是轴名——只核『这一节在不在』属防线空转）：不得作为对外契约的请求参数与响应值（L1，且级别"
     "须标在这一条上）、**必须点名请求参数与返回值两侧**、**嵌套面**（入参/返回值里不得嵌套，"
     "含集合元素/对象字段/分页包装体）、**识别判据**（按『以表结构为来源』判对象、**不看类名**）、"
     "**给出去路**（载体取该接口自己的请求/响应类）、**判定标准四条**、**两条边界**（纯内部调用不在"
     "范围内 / 持久化自身的出口不受约束）、**冲突次序**（项目自身规范可加严或收窄、以项目自身规范为准）、"
     "**存量口径（用户点名『已经用了不管』**：不视违规、不告警、不要求整改、随动迁移不发动全库改造）、"
     "**豁免面与范围**（除非用户主动声明、仅对该次该处生效、不得泛化）与依据行；并反向钉住两件事——"
     "**通用层不得出现框架专名**（`@Entity`/`MyBatis`，替换主语测试）、**技术栈层不得另立第二真源**；"
     "另钉调度器识别特征（须落在『要判定对外接口的请求/响应参数与返回值用什么类承载』这一可判读条件上，"
     "不得只写『数据契约』这类口号）与图书馆取向登记（本集合更严取舍、如实标注外部材料未规定）。"
     "『某个接口算不算对外』『某次改动是否真的只动了新增接口』属语义判断与运行时事实（见 GUARD_CHECK_LIMITS）"),
    ("多层嵌套对象转换优先声明式映射、JVM 下优先 MapStruct（建议、非强制）", "specs/general/coding.adoc + specs/stack/java.adoc", "script/check_specs.py",
     "check_conversion_guard", "check_conversion_guard 按**建议层口径**钉住通用层「对象转换（多层嵌套对象的转换）」——首选声明式映射、判据是**目标式**的（同一转换只有一处来源、结构变化不静默漏字段）、等价路径（深拷贝/序列化中转/手工构建器）同样合规、除主动声明外优选声明式映射且手写须备注原因、**无嵌套（单层）不在本条范围内**（且不得被抄窄成按字段数判）、例外与边界、存量随动迁移与依据行；**反向钉住条文与栈层不得被写成强制面**（「不允许手写转换代码」「一律用」），并反向钉住通用层不得出现框架专名（`MapStruct`/`@Mapper`/`@Mapping`——替换主语测试）；Java 栈「对象转换（MapStruct）」的优先 MapStruct/建议不手写、`@Mapper` 声明形态、嵌套/集合由映射方法表达、不并存两套写法、非强制与例外；调度器两处识别特征与 README 同步、图书馆取向与如实取样状态登记。'某个具体转换该不该用映射库、该结构能否由映射声明表达'语义判断（见 GUARD_CHECK_LIMITS）"),
    ("数据访问边界：IService 成员方法只许在本子类内用、实体 Mapper 只由其对应实体的 Service 调用、跨表业务另建 BizService、调库前先判空（集合返回空集合）", "specs/stack/java.adoc + specs/stack/spring.adoc", None,
     "无机械抓手",
     "无机械抓手：判据是语义判断（某个调用点算不算跨类调 `IService` 成员方法、某次查询算不算补充性单表查询——见 GUARD_CHECK_LIMITS），机械只核文本会空转、且与 `check_persistence_access_guard` 成第二真源，故不设机械抓手，靠遵守 + 人/子 agent 复核。原 `check_orm_boundary_guard` 已删（删除记账见 `specs-project-maintainer/guards.adoc`「已删除的防线（删除记账，按次序留档）」）"),
    ("持久化访问强制走统一入口与类型安全查询构造 API（不 new 构造器、不用字符串写列名）", "specs/general/coding.adoc", "script/check_specs.py",
     "check_persistence_access_guard", "check_persistence_access_guard 钉住通用层「持久化访问（数据库/缓存等）」的三条 L1（统一入口／优先类型安全·声明式查询构造 API／替代优先）、可逐条核对的判定标准（构造器 `new`／字符串写列名／绕过统一入口）、例外与边界（不禁止 mapper `*.xml` 承载）、存量随动迁移与依据行；Java 栈「持久化访问（MyBatis-Plus / JPA 等）」的四个 `IService` 成员方法（`lambdaQuery`/`lambdaUpdate`/`ktQuery`/`ktUpdate`）、禁止面（`new QueryWrapper` 及其子类含 `new LambdaQueryWrapper`，**并入 `Wrappers` 一族静态构造方法**——`Wrappers.lambdaQuery()` 一类同样绕过统一入口）、`IService` 之外的落点（Mapper 注解/映射文件、Mapper 默认方法）与例外口径；调度器两处识别特征与 README 同步。『某个具体类该不该 new 构造器、该条件能否由 lambda 形态表达』语义判断（见 GUARD_CHECK_LIMITS）"),
    ("配置类不写逻辑（配置类只保持 POJO 基本功能、逻辑下沉 utils/service）", "specs/general/coding.adoc", "script/check_specs.py",
     "check_config_class_guard", "check_config_class_guard 钉住通用层条文（含『任何情况都不允许』与去向）、判定标准、Java/Spring 识别特征与 README 同步；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("执行前自检（非平凡任务须逐项自检，防'加载了却没执行'）", "specs/general/self-check.adoc", "script/check_specs.py",
     "check_self_check_guard", "check_self_check_guard 钉住自检规范文件、适用边界与 execution.adoc 必加载层落点；运行时事实（见 GUARD_CHECK_LIMITS）"),
    ("不得编造事实与来源（引用真实、标准不编、宁可不引）", "specs/general/source.adoc", "script/check_specs.py",
     "check_source_guard", "check_source_guard 钉住来源规范要点；引用存在性另由 check_refs_exist/check_section_refs 兜底"),
    ("不可逆操作先确认（删除/清空/强推，P5）", "specs/core/execution.adoc", "script/check_specs.py",
     "check_priority_guard", "check_priority_guard 钉住 P5 存在性与「破坏性操作」落点；运行时事实（见 GUARD_CHECK_LIMITS）"),
    ("换行符按解释器分流（LF 基准、.bat/.cmd 必须 CRLF、.gitattributes/.editorconfig 固定；仓库根缺这两个落盘口即补齐）", "specs/general/encoding.adoc", "script/check_specs.py",
     "check_line_ending_guard", "check_line_ending_guard 钉住编码规范的分流判据（LF 基准、`.bat`/`.cmd` CRLF、`core.autocrlf`/`.gitattributes`/`.editorconfig` 落盘口）与 bash/python/powershell 栈文件的行尾要求；某文件实际是否为 CRLF、仓库根是否已有 `.gitattributes`/`.editorconfig` 属引用方工作区状态，本仓库不可见，靠引用方 `git ls-files --eol` 自检"),
    ("代码安全底线（输入校验/输出编码/凭据不硬编码）", "specs/general/security.adoc", None,
     "无机械抓手",
     "无机械抓手：具体实现语义判断（见 GUARD_CHECK_LIMITS）"),
    ("依据不得只剩名称：图书馆须可查到、可逐字核对、引用不悬空", "AGENTS.adoc", "script/check_specs.py",
     "check_library_guard", "check_library_guard 钉住图书馆（仓库根 library/，不在默认引用面内）入口与主题文件存在且被项目规范入口登记、入口登记与实际主题双向一致、外部标准逐字引文锚点仍在、馆内引用可解析（悬空即依据链断在这里）；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("馆无体量上限：引用方不全量下载即准确定位依据（主键为内容、非路径）", "AGENTS.adoc", "script/check_specs.py",
     "check_library_locating_guard", "check_library_locating_guard 钉住图书馆入口的『定位协议』要点（作者侧/取用侧之分、入口 = 常驻层的固定地址、三步取值、版本固化只是可选加固、不解析页面结构）、usage 侧的使用判据（取用侧只有 https、主键是内容不是路径、终止条件、不承载派生落点）、sources 侧的机制原文与如实取样状态（git 内容寻址 / RFC 7233，且须标站点与平台视图均未实测到 Range）、**『先取 commit 再拼地址』这一取用前置形态不得回退**、**馆内主题文件名不得过长（≤32 字符：名字不是检索键、却会被读进每次链接与目录列举）**、以及项目规范入口的口径；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("依据该何时写、怎么反查（写入判据与关联协议）", "AGENTS.adoc", "script/check_specs.py",
     "check_library_guard", "check_library_guard 钉住『依据的写入与关联』主题（library/usage.adoc）的要点锚点：写入触发特征、不写判据、入库必写项、关联协议与**只取一份不遍历**的反查解析算法、**默认引用面与非引用面**的边界；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("落点口径须写对：不得把本仓库内容写成\"私有/不对外发布\"", "README.adoc", "script/check_specs.py",
     "check_ref_scope_wording_guard", "check_ref_scope_wording_guard 钉住本仓库维护范围内的 .adoc 不得出现\"本仓库私有…不随规范分发\"\"私有内容不随规范分发\"\"不随规范分发\"三类错误形态（平台事实：本仓库所有内容都会被发布，区别只在\"默认引用什么\"），并豁免引用/纠正该表述本身的句子与\"私有落点/私有抓手名\"这类自足性用语、豁免 CHANGELOG 历史条目；『某处该不该被引用方按入口加载』属判定"),
    ("引文段落不得用裸 `>` 起头（会被解析成 callout list 而中断整份文档编译）", "AGENTS.adoc", "script/check_specs.py",
     "check_quote_line_guard", "check_quote_line_guard 钉住仓库维护范围内全部 .adoc 的引文行形态：行首 `> ` 即命中（该形态被 AsciiDoc 的 `listdef-callout` 吃掉、`index` 取空串后在 `List.calc_style()` 里 `assert False`，整份文件编译失败；页面侧 Asciidoctor.js 渲染成引用块、看不出问题）；行内 `>`（比较运算符、shell 重定向）不误伤；写引文用 `[quote]` + 正文行；『某段确实该是引文还是该改写成正文』语义判断（见 GUARD_CHECK_LIMITS）"),
    ("变更日志条目须单行（版本号 | 日期 | 变更摘要，条目内不换行）", "CHANGELOG.adoc", "script/check_specs.py",
     "check_changelog_entry_guard", "check_changelog_entry_guard 钉住 CHANGELOG.adoc 的条目形态：条目行（`- 版本 | 日期 | 摘要`）之后不得紧跟续行、单条不得超长（实证失效：日志被当成追加区，同一条目被 heredoc/多次 append 续写成多行而与下一条粘连）；『条目是否记对了变更点、有没有漏记』语义判断（见 GUARD_CHECK_LIMITS）"),
    ("变更日志排序方向恒为时间倒序（版本倒序即时间倒序）并以发布版本为一级分组、版本内按类型分组；两种条目形态（流水式/表格式）择一，表格式须有分组列/类型列/变更点/影响四列且影响列不得退化为变更点的同义重复、破坏性变更须逐行标注", "specs/general/changelog.adoc", "script/check_specs.py",
     "check_changelog_structure_guard",
     "check_changelog_structure_guard 钉住三处：①组织形态（**排序方向恒为时间倒序、版本倒序即时间倒序**——版本单调递增时二者一致，故不存在『两种要择一的排序』、正序即错；按版本分组为默认、版本号即发布标识、两种分组口径择一且**不并存**、类型闭集、空分组不写）；②表格形态的判据（四列列义、判据依赖关系与三条反向禁令（不得用类型分级代替破坏性变更标注 / 不得把影响写成变更点的同义重复 / 影响列写不出读者要做的动作即说明不该记）、破坏性变更逐行标注、表格里一条=一个变更点、要素齐备底线四项（类型/变更点/影响/标记））；③图书馆依据（Keep a Changelog / Conventional Commits / Conventional Changelog 三者齐备，且**如实标注是业界约定而非标准**——Keep a Changelog 自述没有标准格式）。实证失效（用户报告）：一个版本改了很多东西时单行流水式日志不可检索，用户对比两个 tag 后要求「根据模块和功能分类，做成一个表格」；反向失效是**换成表格后把影响列省掉**、**用类型列代替破坏性变更标注**，以及**把排序方向写成正序**或把『版本倒序』与『时间倒序』读成两种可择一的排序（用户口径：排序方式还是时间倒序、版本是越来越大的、版本倒序和时间倒序是一样的）。『某条条目是否真的写清了影响、表格是否真的可检索』语义判断（见 GUARD_CHECK_LIMITS）"),
    ("提交信息须带类型前缀、破坏性变更须显式标注（`!` 或 `BREAKING CHANGE:` 页脚）", "specs/general/git.adoc", "script/check_specs.py",
     "check_commit_message_guard", "check_commit_message_guard 钉住「提交信息」节的形态（`<type>[(scope)]: <subject>` + 类型固定闭集）、可逐条核对的判定标准（首行无类型前缀即不合规）、破坏性变更须 `!` + `BREAKING CHANGE:` 页脚且**不得把某个类型默认为破坏性的**、正文写「为什么」与边界、以及**如实标注依据是业界约定而非标准**（Conventional Commits 自述 a lightweight convention on top of commit messages）；缺口来源：本集合早已把 Conventional Commits 1.0.0 原文收进图书馆，却只用它支撑变更日志的展示形态——提交信息这一「上游」空着，变更日志的「按类型分组」只能人工归类。『某条提交信息是否真的写清了影响』属语义判断；『某次提交有没有带类型前缀』可由提交历史机械判定，属引用方项目的运行时事实（本仓库不可见），靠引用方的提交检查或人 review"),
    ("HTTP 方法与状态码按协议语义使用（安全方法不得产生状态变更、幂等与重试对齐、状态码不得一律包 200、错误响应可统一为 Problem Details）", "specs/general/coding.adoc", "script/check_specs.py",
     "check_http_semantics_guard", "check_http_semantics_guard 钉住「HTTP 接口语义」三处：①条文与级别（安全方法不得产生状态变更 **L1**、幂等与状态码 **L2**、Problem Details **L3 可选**——级别不得被顺手改动）；②适用范围（无 HTTP 接口的项目不适用，避免高频误伤）；③图书馆依据（RFC 9110 安全方法/幂等/状态码与 RFC 9457 的**逐字**引文、以及「判据化取值 vs 标准原文」的同义性差异如实标注）。缺口来源：此前只覆盖路径命名风格，方法与状态码语义未覆盖（`GET` 承载写操作会被爬虫/预取在无人操作时触发副作用；错误包成 `200` 会让重试、缓存、监控与网关策略全部失效）。『某个接口实际用的是哪个方法、返回什么状态码』语义判断（见 GUARD_CHECK_LIMITS）"),
    ("公共内容覆盖面须有清单且与实际一致（安装入口/公共片段/随规范分发的工具同样会被引用方取到）", "PUBLIC.adoc", "script/check_specs.py",
     "check_public_content_coverage", "check_public_content_coverage 钉住入口清单存在且被项目规范入口登记、两个公开入口都在清单里、清单点名的文件真实存在；『某文件到底算不算公共内容』属判定"),
    ("安装取文件须有随规范分发的抓手：清单从入口自身解析、一次取全（不手拼逐条下载命令）", "AGENTS_COMMON.adoc", "script/check_specs.py",
     "check_spec_fetch_guard", "check_spec_fetch_guard 钉住随规范分发的抓取脚本与其同名平台入口（`.sh`/`.bat`）存在、清单从入口的调度器登记解析（退回手工清单即回到「新增规范就漏一份」）、增量语义、落点边界校验、「不是站点首页」的判据（站点对未命中路径回落 200 + HTML，只判状态码会把 HTML 存成规范）、退出码语义、薄壳三件事与 `.bat` 纯 ASCII+CRLF，以及 AGENTS_COMMON/README 两处登记同步；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("重新执行安装须能更新现有副本（安装脚本经常更新：以远程为准、内容不同才刷新，失败保留本地那一份）",
     "AGENTS_COMMON.adoc", "script/check_specs.py",
     "check_spec_fetch_guard",
     "check_spec_fetch_guard 钉住抓取脚本的默认语义是**以远程为准**（每份文件取回的字节与本地比较、"
     "不同才原子落盘；`--keep` 才回到「本地已有即不动」）与**取回失败保留本地已有的那一份**"
     "（不得把副本删掉换成没有），以及 AGENTS_COMMON/README 两处文档写明该语义——"
     "防退回「本地既有就跳过」：它把安装结果绑在「本地以前取过什么」上，远端修好了、加了一节规范，"
     "用户重跑安装仍旧什么都不做（用户实测诉求）；反向也拦「失败也把本地删掉」这把「没更新」"
     "变成「没有」的形态。『某次重跑是否真的取到了最新内容』运行时事实（见 GUARD_CHECK_LIMITS）"
     "靠实测与留证（本仓库按逐字节比对、`--keep`/刷新三态各跑一遍复核）"),
    ("多模块项目的模块间依赖须有完整依赖关系文档（UML 表述、查依赖先读它、缺失即新增、不重复声明）", "specs/general/doc-design.adoc", "script/check_specs.py",
     "check_dependency_view_guard", "check_dependency_view_guard 钉住「依赖关系文档（模块间依赖的唯一视图）」节的要点（完整 / UML 优先 / 固定路径可直达 / 先查本文档 / 缺失即新增 / 同提交同步 / 不重复声明 / 与构建工具边界）与两处指向（加载调度器、依赖规范）；『某个项目的依赖视图是否真的完整、有没有过期』语义判断（见 GUARD_CHECK_LIMITS）"),
    ("入口占位须保留三要点：优先取到本地副本 / 取不到就直接读远程 / 需要最新规范时再运行一次即是更新",
     "AGENTS_COMMON.adoc", "script/check_specs.py",
     "check_shared_cache_guard",
     "check_shared_cache_guard（内含 `_check_install_entry_placeholder_lines`）钉住入口模板那行的三个要点"
     "——缺『优先取到本地副本』则网络不可达时本地那份可读副本没有了、缺『取不到就读远程』则把可选的一步"
     "读成前置条件、缺『再运行一次即是更新』则用户重跑安装仍拿本地旧副本（而入口占位还会被判成与模板一致、"
     "连那几行都不更新——用户实测两次点名『还是没改』）；`check_install_codeblock` 只核每行独立成行 + 空行完好，"
     "拦不住措辞回退（本轮实测复现：把要点删掉/合并后 `check_specs.py` 仍报 OK）。**本条只钉『优先取到本地副本』、"
     "不钉具体落点**——入口占位那一行只说『取到本地副本』，落点路径在下一行单独写；"
     "『取不到/更新』的实际行为由 `script/check_specs_test.py` 的端到端用例（本机 HTTP 服务当远端）与人工复核承担"),
    ("防线清单与删除记账：防线个数、反例用例个数、台账点名的防线名三者都不得在无记账的情况下减少（清单本身不得出现断号）",
     "AGENTS.adoc + script/check_effective.py", "script/check_specs.py",
     "check_guard_manifest",
     "check_guard_manifest 把三件事变成可核对的：①`main()` 里直接接线的防线个数不得低于 "
     "`GUARD_WIRING_BASELINE`（**删一道防线必须记账**——改基线这个动作让删除在 diff 里可见）；"
     "②`check_specs_test.py` 的反例用例数不得低于 `GUARD_TEST_BASELINE`（反例用例是防线的实际"
     "效力来源，被删时防线的效力随之消失）；③台账**逐条声明**的抓手须真实存在且真的会被"
     "调用——『定义了但没人调』的防线看起来还在、却永远不会执行，**且没声明就没核对**"
     "（旧判据只核『备注里点名的名字存在』，于是『有抓手』这个数字可以靠把备注里的防线名"
     "删掉维持——删名字比删防线容易得多）；④脚本头部清单不得出现断号。"
     "实证失效（本轮实测复现）：一道防线被从 `main()` 摘掉、它的 8 条反例用例一并被删，"
     "`check_specs.py` 报 OK、单测全通过、台账上的『抓手数』也没变；台账里的防线名改成不存在的"
     "名字仍报『有抓手』；清单两条被整条删掉仍报绿。『某次删除是否该被批准』语义判断（见 GUARD_CHECK_LIMITS）"
     "交人/子 agent 复核"),
    ("入口文档须给『隔一次会话还认得回来』的清单：安装与取回口径的落点路径与取规范脚本路径、副本检索路径、取回与更新方式、要跨会话保留的本项目信息（落点只有用户家目录下的一处）",
     "specs/general/entry-doc.adoc + AGENTS_COMMON.adoc", "script/check_specs.py",
     "check_entry_doc_manifest",
     "check_entry_doc_manifest 分两处核：①**判据真源** specs/general/entry-doc.adoc"
     "（唯一持久落点/新实例只看到项目里的文件/与临时产物的分界/项目自身规范优先/『唯一真源』声明）；"
     "②**入口模板** AGENTS_COMMON.adoc「安装与更新」只核**路径链与副本两要点**（规范入口与"
     "取规范脚本两条路径齐；缺取规范脚本路径则新实例不知道"
     "如何去下载规范，用户实测点名；落点=用户家目录/用户路径下的 `.cache/agent-specs`，按**要点**核"
     "『用户侧词的任一写法 + 落点名同现』、不核某一种写法的字面值；`fetch-specs`+『再运行一次』；"
     "下载来的**安装脚本**（取规范脚本与其平台入口、清理脚本）同样落这一处——"
     "用户口径是『所有下载的文件』，故 `check_shared_cache_guard` 另钉住脚本侧那几件"
     "（`INSTALL_SCRIPTS` 清单、落点里只保留文件名、落点里的入口须能直接跑），"
     "公共入口侧则钉住『下载的文件一律只落这一处』这条要点），"
     "**不核模板的小节结构**——模板写成什么样**以用户手工编辑的形态为准**（用户点名不要 "
     "`= Agent 规范入口` 标题与『规范与安装文档的位置/规范副本的位置/本项目持久化到入口文档的信息』"
     "三节；上一版判据按节标题核，结果是把用户删掉的三节又『补』了回去，等于拿机械判据盖掉用户的"
     "手工编辑，故已撤）。落点那一档曾核字面值，核字面值时一次措辞精炼就让判据空转（本轮实测："
     "`~/.cache/agent-specs` 的写法被旧判据判为缺失），故改按要点核；"
     "**『取回与更新方式』那一档只在模板那一段内核，且模板里本来就有 `fetch-specs`+"
     "『再运行一次』——故它管不到「取规范到本地副本」一节被抽空**；该节现已收敛为『只写落点 + "
     "回指真源』，故『怎么取、怎么更新』由 `check_spec_fetch_guard` 收尾调用的 "
     "`_check_install_no_python_section` 核**真源那一侧**（`script/fetch-specs.py` 的头部注释："
     "一次取全 / 清单从入口自身解析 / 以远程为准 / `--keep` / `--base` / 解释器兜底与处置次序）"
     "写全，并核入口那一节**仍有落点与指向真源（及其部位）的回指**。用户口径是『这一节重复了』"
     "——同一件事实写两处即两处漂移，故判据**不得**再要求入口复述那些句子"
     "（要求复述=把重复判成合规）；反向：入口只剩指针、真源被抽空，两种形态都报红。"
     "『某次安装是否真把项目信息写进入口文档』运行时事实（见 GUARD_CHECK_LIMITS）"),
    ("安装流程的幂等更新：用户手工编辑过的模板内容不自动改回（用户改过的以用户改过的为准）",
     "AGENTS_COMMON.adoc「安装与更新」的「本流程可重复执行、且以远程为准」", "script/check_specs.py",
     "check_install_repeat_update_guard",
     "check_install_repeat_update_guard 钉住该节的三项要点——**用户手工编辑过的模板内容一律照原文"
     "保留**、**不自动改回**、不一致时**在汇报里指出等用户定**；缺它时『与最新模板不一致即就地"
     "更新为最新模板』会孤立生效。实证失效：上一轮实施据此把用户手工删掉的标题与三节『补』了回去，"
     "用户点名『我手动删的，你不要给我补上去』『以我的为准』——只在脚本注释里写『模板形态以用户"
     "手工编辑为准』挡不住下一次，实施者读的是安装流程本身。『某次安装是否真的没改回用户的手写』"
     "运行时事实（见 GUARD_CHECK_LIMITS）"),
    ("模板类内容须单独归类：要么不读、要么读全部的内容（代码模板）不与规则混放、各自独立（例外：有关联性或内容不多暂不拆）",
     "specs-project-maintainer/spec-lifecycle.adoc + AGENTS.adoc + specs/general/context.adoc", "script/check_specs.py",
     "check_template_separation_guard",
     "check_template_separation_guard 分栏核三处落点的**判据本体**：①真源在维护方自查层"
     "『要么不读、要么读全部的规范』（归类判据与三条判定标准、不得混放与其逐条判定标准、"
     "『各自独立』与例外、依据行）；②`AGENTS.adoc` 登记该落点（缺则执行者读不到这套判据）；"
     "③`specs/general/context.adoc`「生成效率」的公共侧一跳引用（公共侧只给方向、不写判据本体，"
     "避免同一条规则两处真源）。判据本体落在**维护方层**是归属判定：它描述的是『规范集合自己"
     "怎么组织』，对引用方项目不成立，写进公共内容即放错受众。"
     "『某份内容到底算不算模板类内容』语义判断（见 GUARD_CHECK_LIMITS）"),
    ("取规范入口的解释器兜底：不把「机器上有 python3」当前提，且入口不得代为安装运行时",
     "specs/general/script.adoc + AGENTS_COMMON.adoc", "script/check_specs.py",
     "check_spec_fetch_guard",
     "check_spec_fetch_guard 钉住两个入口**按次序探测解释器、找不到就报错退出**"
     "（`_check_interpreter_fallback_entry_lines`：键须落在**同一条可执行行**上、次序只在"
     "候选代码行之间比较——只核全文关键词时，注释里写一句、或把某一级分支整条删掉都能骗过，"
     "本仓库实测复现；缺一即「没有 python 的机器上装不上规范」），以及**取回与处置口径的真源**"
     "（`_check_install_no_python_section` 核 `script/fetch-specs.py` 的**头部注释**：先按本平台"
     "既有软件分发方式装一个 python 3、只装 python2 不算「一个都没有」、入口不得代为安装运行时、"
     "报错退出非 0 不得静默继续、`curl … | python3 -` 那条远程执行形态同样要 python——"
     "真源侧被抽掉即报红；同时核公共入口那一节**仍有落点与指向真源（及其部位）的回指**，"
     "入口只剩一枚指针同样报红）——同一件事实只写一处，不得要求入口复述；"
     "反向钉住 `specs/general/script.adoc`「跨环境脚本」的边界条——**入口不得为「让逻辑跑起来」"
     "安装/下载/解压运行时**（改系统状态、要权限、对调用方不可预期；判据 ISO 9241-110），"
     "并钉住「可以做把逻辑层当命令直接跑的薄壳」这条，防把正当形态一并禁掉；"
     "『某台机器上到底有没有解释器、装了哪一个』运行时事实（见 GUARD_CHECK_LIMITS）"),
    ("对外接口命名带所属域/项目前缀（Feign 接口的 `Api` 前须带该域固定前缀，先例优先、无先例取项目名词首组合）", "specs/general/coding.adoc + specs/stack/java.adoc", "script/check_specs.py",
     "check_api_naming_guard", "check_api_naming_guard 钉住通用层条文与 L1、先例优先、无先例取词规则与实例（`user-center` → `UcUserApi`、`open-user-center` → `OucUserApi`）、可逐条核对的判定标准与存量口径，以及 Java 栈落点（Feign、指向通用条）、加载调度器两处识别特征、README 目录说明与图书馆依据落点（含如实取样标注）；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("分页查询的返回类型与转换（普通接口 `Result<IPage<Rsp>>`、Feign 接口 `Result<自定义Page<Rsp>>`、字段转换走 `page.convert` 而不是新建 page）",
     "specs/stack/java.adoc", "script/check_specs.py",
     "check_pagination_guard",
     "check_pagination_guard 钉住**判据本体**（不是轴名——只核『有没有这一条』属防线空转）："
     "`specs/stack/java.adoc`「持久化访问（MyBatis-Plus / JPA 等）」里该条的两侧返回类型"
     "（普通接口 `Result<IPage<Rsp>>` / Feign 接口 `Result<自定义Page<Rsp>>` 并跟随先例）、"
     "`convert` 的**禁止面**（不得新建 page 再逐个搬运字段）、保留分页元数据这一理由"
     "（当前页/每页条数/总记录数/总页数——缺理由则本条的级别与处置被降级）、"
     "可逐条核对的判定标准（普通接口侧不合格 / Feign 侧 `new` page / 两侧先例互改 / 自我豁免）、"
     "与相邻条目的分工（元素不得是实体类、字段转换优先声明式映射）与存量随动迁移、"
     "依据行须如实写明这是本集合的取舍。失效形态：同一项目并存两套分页模型；"
     "**新建 page 时漏搬总页数既不报错也不提示、只在运行期表现为翻页失效**。"
     "『某个分页接口算不算普通接口、该处该不该用自定义 page』语义判断（见 GUARD_CHECK_LIMITS）"),
    ("方法名与逻辑删除的对应（查询方法名即删隐面）——默认面取该技术是否自动附加删除标志条件、非默认面须带特征词，同一实体同一删隐面不得并存两个名字",
     "specs/general/coding.adoc + specs/stack/java.adoc", "script/check_specs.py",
     "check_logical_delete_naming_guard",
     "check_logical_delete_naming_guard 钉住**判据本体**（不是轴名——只核『有没有这一条』属防线空转）："
     "`specs/general/coding.adoc`「持久化访问（数据库/缓存等）」三级小节里的默认面取值"
     "（不自动附加＝含已删 / 自动附加＝只取未删）、非默认面须带特征词、可逐条核对的四条判定标准、"
     "理由（删隐面只能从技术配置反推）、默认面的唯一例外（项目自身规范或既有先例、项目内只保留一种）、"
     "边界（只管按实体/表查询的方法名；显式参数形态与特征词等同）、存量随动迁移与依据行；"
     "Java 落点只给框架专名（`@TableLogic` 自动附加、`@SQLDelete` 不自动附加）并把判据回指通用层；"
     "图书馆侧登记本集合取舍。失效形态：同一条 `list()` 在未启用逻辑删除的库里返回含已删数据、"
     "在启用的库里返回只含未删数据，**名字一个字都没变**。"
     "『某个方法算不算按实体查询、这个名字算不算带了特征』语义判断（见 GUARD_CHECK_LIMITS）"),
    ("请求/响应类优先移动复用（给已有接口加内部调用接口时不新建一套，例外只有数据库实体类与含三方类型的类，本项目自身的依赖不算三方依赖）", "specs/general/coding.adoc", "script/check_specs.py",
     "check_api_contract_reuse_guard", "check_api_contract_reuse_guard 钉住通用层条文与 L1、两种例外（数据库实体类除声明外不移动 / 类里引用了第三方类型）、边界（**本项目自身的依赖不算三方依赖**——该字句缺位等于给出一个随时可套用的豁免口）、「移动而非复制、同步更新原引用」的动作、可逐条核对的判定标准（另建同构类 / 同名或仅差包名 / 复制不改原引用 / 以「依赖本项目其他模块」为由拒绝移动 / 移动数据库实体类而无声明）、存量随动迁移与依据行，以及调度器识别特征与 README 同步；『某次是否真的移动了类、是否真的跟随了项目先例』语义判断（见 GUARD_CHECK_LIMITS）"),
    ("HTTP 接口路径优先用中划线（kebab-case）（不得用下划线或驼峰；服务路由/网关前缀与已发布对外路径照旧）", "specs/stack/spring.adoc", "script/check_specs.py",
     "check_api_contract_reuse_guard", "check_api_contract_reuse_guard 钉住**唯一落点**（技术栈层 `spring.adoc`）的条文与 L1、禁止下划线与驼峰、两处照旧（服务路由/网关前缀、已发布且外部依赖的对外路径）、判定标准（出现 `_` / 路径片段用驼峰或大写 / 同一接口内混用）、存量随动迁移，以及**通用层不得出现「HTTP 接口路径」专条**（该判据只在 Web 框架语境下有定义）与调度器 Spring 条目的识别特征；『某个接口路径该怎么写、是否属两处照旧』语义判断（见 GUARD_CHECK_LIMITS）"),
    ("索引页只在目录已承载实质文档时要求，空目录不建、索引只做导航", "specs/general/doc.adoc", "script/check_specs.py",
     "check_index_page_guard", "check_index_page_guard 钉住「索引页的触发判据」（已承载实质文档才建 / 空目录与仅有索引页自己的不建 / 索引只做导航不得复制上一级内容 / 模块级导航由模块 README 承担）与 specs/general/doc-module.adoc 的「按需」口径（doc/ 下有实质文档才放 README、无则不建）；实证失效：AI 把「每级目录须有索引页」读宽成「每个模块都建 doc/README.adoc」，批量生成 48 个同构空壳索引）；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("评论唤起新实例：评论即一次派发（要求须写清、可要求用干净上下文）", "specs/platform/cnb.adoc + specs/general/collab.adoc", "script/check_specs.py",
     "check_comment_dispatch_guard", "check_comment_dispatch_guard 钉住四处要点（平台层「评论唤起新实例（平台侧的派发入口）」节：入口形态/不放宽任何派发约束/一次评论=一次派发/干净上下文须显式要求且不是保证/仅点名不构成派发；通用层「派发入口」节同口径；AGENTS_COMMON.adoc 两处识别特征；README 目录说明同步），**重点拦『把该入口写成可放宽派发判据或可点名外部 Agent』与『把干净上下文写成默认』两种降级**；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("改动范围边界：只改当前工作空间/当前项目，未声明即拒绝越界改动（引用 ≠ 授权）", "specs/general/scope.adoc + specs/platform/cnb.adoc", "script/check_specs.py",
     "check_scope_boundary_guard", "check_scope_boundary_guard 钉住两层同口径（通用层 scope.adoc 的「工作空间边界」与「平台上的仓库边界」两节 + 平台层 cnb.adoc 的当前项目口径与指向）+ 提示词公共片段 `scope-boundary` 同口径且两个提示词代码块内都引入；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("机械防线的核对对象是判据本体、不是轴名（只核『要求/依据/判定标准』等轴名齐备即属防线空转）", "specs-project-maintainer/priority.adoc", "script/check_specs.py",
     "check_criteria_not_axis_guard",
     "check_criteria_not_axis_guard 钉住「机械防线的核对对象是**判据本体**，不是轴名（L1）」一节的四组要点仍在该节的**自身**正文里，"
     "且在维护方入口 `AGENTS.adoc` 可加载：①核对对象（钉判定标准里能拿去核对的那句话，不是轴名/条目标题）；"
     "②失效形态『只核轴名齐备即属防线空转』；③逐条可核对的判定标准（被钉的是轴名 / 抽掉判据句后仍不报红 / 靠相邻条目字样兜住）；"
     "④必配反例用例（『轴名齐全、判据被抽走』的改造下防线必须报红）。本轮实测：维护方最高关注项 P7 的『要求』被压成两句骨架，"
     "『要求/依据/判定标准』三个轴名都还在、防线全绿，而可核对的判据被整段抽掉；教训当时只写在 `script/check_specs.py` 与配套测试的注释里、"
     "**没有进规范正文**——下一个维护者读规范时看不到、只能靠翻脚本注释（判据存在但不可见=同构复发）。"
     "『某道防线具体钉的是不是判据本体』语义判断（见 GUARD_CHECK_LIMITS）"),
    ("压缩提交：用户可明确要求、执行者应当照做（内容零变化、只动本源分支、规则本体工具无关；平台侧另含先确认无人在用旧对象、force-with-lease、声明新旧 sha 对应关系）", "specs/general/version-control.adoc + specs/platform/cnb.adoc", "script/check_specs.py",
     "check_squash_commit_guard", "check_squash_commit_guard 钉住平台层「压缩提交」的追加口径（节 / 作用域只动本源分支 / 禁止形态的平台侧追加 / 先确认无人在用旧对象 / `--force-with-lease` 与「一般强推口径不适用」 / 与「NPC 禁合并」互不豁免 / 新旧 sha 对应关系声明 + 对象钉定侧的『合规动作』标注）**并钉住规则归属**：通用层 `specs/general/version-control.adoc` 承载工具无关本体、平台层须指向它（用户口称『版本管理』、未点名 git/CNB，规则本体留在平台层会让非 CNB/非 git 的引用方读不到）；**两边的降级都拦**（把条文删掉/降成建议、以及把用户可要求的压缩提交读成「强推违规」）；『某次压缩是否真的内容零变化、是否真没人基于旧 sha 工作、是否真的用了带租约强推』运行时事实（见 GUARD_CHECK_LIMITS）"),
    ("重命名与内容修改须分两个提交（P7）；且『合并成一个提交/压缩提交』的请求**未点名本条**时不覆盖它", "specs/general/git.adoc + specs/platform/cnb.adoc", "script/check_specs.py",
     "check_rename_split_guard", "check_rename_split_guard 钉住四处要点（git 规范「重命名与内容修改须分两个提交」整节的条目轴与要点、必加载层 `specs/core/execution.adoc` 的 P7 重申行、`AGENTS_COMMON.adoc`「最高优先级铁律」的登记、维护方清单 `specs-project-maintainer/priority.adoc` 的 P7 条目与级别），**并钉住与「压缩提交」的接口**：用户要求压缩提交/合并成一个提交而**未点名重命名与内容修改**时，压缩只作用于临时中间提交、这两个提交**原样保留**（平台层「压缩提交」须写同口径，防平台侧自行把『要压缩』读成『压回一个』）；例外的『声明』须点名重命名与内容修改、须预先声明（只说合并/压缩不算）；**并按「条目自身」而非「整节关键词」核对**——边界条与平台层接口条的判据（未点名/临时中间提交/原样保留/判定标准）须在**该条自己的正文**里，被抽空或搬进相邻条目即报错（否则相邻条款的字样会兜住已消失的要求；本仓库实测：仅留轴标题、正文另议时旧法静默通过）；『某次是否真的分成了两个提交、压缩是否真的没把它们压掉』属运行时事实（git 记录），机械无法判定，交人/子 agent 用 `git log --follow --name-status`、`git diff <改名提交>^ <改名提交> -M --stat`、`git log --diff-filter=R -M --name-status` 复核"),
    ("压缩/解决冲突后须保留与目标分支的合并关系（目标分支仍是本分支的祖先、合并提交保留双亲、压缩不吞掉合并提交）", "specs/platform/cnb.adoc", "script/check_specs.py",
     "check_merge_relationship_guard", "check_merge_relationship_guard 钉住根因形态（照抄目标分支文件内容后另起单亲提交→目标分支不是祖先→平台仍报 code_conflict）、可核对判据（`git merge-base` 等于目标分支最新提交、`git merge --no-ff` 保留双亲 / `git rev-list --parents -n1`）、`--is-ancestor` 为假这一假绿信号、以及『压缩不吞掉合并提交（它是已并入的凭据）』；『某次合并是否真的建了双亲关系』属运行时事实（git 记录），机械无法在静态文本上判定，交人/子 agent 用 `git merge-base --is-ancestor` 与 `git rev-list --parents` 复核"),
    ("冲突与压缩提交：先解冲突、再压缩（最终只有一个提交），且解冲突后须核查是否丢内容（**工具无关**——版本管理工具，不限 git/CNB）", "specs/general/version-control.adoc + specs/general/git.adoc + specs/platform/cnb.adoc", "script/check_specs.py",
     "check_conflict_resolution_guard",
     "check_conflict_resolution_guard 钉住三处（用户口称『版本管理』、未点名 git/CNB，故规则本体必须在通用层）：① **通用层 `specs/general/version-control.adoc`「冲突处理」**——三件要点（①先解冲突、再压缩、最终只有一个提交，含反向判据『拿还有冲突当不做压缩的理由』『拿要压缩当不解冲突的理由』；②**触发面写全**：『只被要求压缩、没被要求解决冲突也要先解冲突』——用户只要求压缩、没提解决冲突而分支实际有冲突时同样须先解冲突，含判定标准四态【用户本轮点名】；③解决冲突后须核查是否丢内容，含失效形态『整体取一侧收尾、不做逐处对照』与随对象定的三档核查判据）+ 工具无关性声明（点名 git 之外的版本管理工具如 SVN）+「压缩提交」节写明**压缩不等于解冲突**；② **git 层 `specs/general/git.adoc`「冲突与压缩提交（git 侧落地）」**（**按节取文本**——别处也提 `rename`、`--ours`，全文匹配会把『本节被掏空、命令搬到别处』读成齐备）——`--ours`/`--theirs` 取一侧这一失效、`git diff --name-status`/`rename` 强制核对、『最终只有一个提交』的 git 侧命令；③ **平台层 `specs/platform/cnb.adoc`**——只留追加口径且须**指向通用层规则本体**、交付形态按本平台表达，且**「冲突处理」与「压缩提交」两节都须写全触发面**（『只被要求压缩提交』时冲突处置不豁免、含祖先关系可核对判据与『解冲突不是合并』的边界；「压缩提交」节另须**按该节自己的正文**写明『先解冲突、不得留在原地只做压缩』的接口条——台账声明了本节写全触发面，那就得真的核到它）；另加调度器与 README 同步。**按节取文本**（同文件别处也提到『冲突』与『压缩』，全文匹配会把『条文从本节删了、别处还提了一句』读成齐备）；『某次解冲突是否真的两侧内容一条未丢、最终是否真的只有一个提交』属运行时事实（git 记录），机械只钉『要求文本仍在』，交人/子 agent 复核"),
    ("CNB NPC（CI/CD 执行者）严禁合并 PR、人工要求或直授也必须拒绝", "specs/platform/cnb.adoc", "script/check_specs.py",
     "check_npc_merge_guard", "check_npc_merge_guard 钉住八处要点（禁令本体 / 无豁免含『授权不免除』 / 可逐条核对的判定标准含本平台实际合并入口 `cnb pulls merge-pull` / 与「冲突处理」不矛盾的边界 / **按执行环境保证**『与谁在跑无关、不得把「我知道这条规则」当保证、人以外的自动步骤不构成人工』 / **本仓库实证失效**记录与固定形态『最后一个动作的默认读法是交付到 PR 分支为止』 / 提示词公共片段 `delivery` 同口径 L1 条 / **题面开头 `intro-rules` 的『合并提交 = 把提交历史压成一个合规提交，不是合并 PR』** / 公开提示词入口 PROMPTS.adoc 同步）；**动作侧的 `check_merge_state_guard` 是第二道**（核**提交说明与分支状态**：提交说明里出现合并动作 + 已合并的话术即报红、源分支 HEAD 不等于并发唤起时钉定的 sha 即报红、本分支历史出现合并提交即报红）——这是本条**唯一**能覆盖『动作真没做』的一半：文本侧再全也只证规则写着。**本仓库实证**：曾把用户的『压缩提交』读成『合并 PR』、跳过其真正要求的那件事直接合并并回『已合并 ✅』，而当时三道文本防线**全部报 OK**；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("提示词取值路径与装配状态：不得给『渲染视图下已展开』这类与路径绑不上的笼统说法", "PROMPTS.adoc + prompts/_common.txt", "script/check_specs.py",
     "check_prompt_delivery_surface_guard", "check_prompt_delivery_surface_guard 钉住公共片段「查看与复制方式」的按路径判据（装配过的：IDE 预览/asciidoctor/站点页面内渲染；未装配的：远程原始文件地址/本地读取——直出仓库字节、**逐字节一致**）、各提示词读取说明的判定口径、PROMPTS.adoc「取值路径与装配状态」的三行判据表与『不是三种版本的提示词』『L1 实证话术』两条、以及维护方入口的口径与抓手名；**本仓库实证**：把站点原始文件地址当渲染视图、据此以为片段已展开（实测该地址与工作区逐字节一致、指令仍在）；『某次取值实际是否装配过』属运行时事实，交人/子 agent 用 curl 原始文件地址逐字节比对复核"),
    ("不得自行发评论唤起自己：评论派发的\"下一次\"只能由人发起（防无限派发）", "specs/platform/cnb.adoc + specs/general/collab.adoc", "script/check_specs.py",
     "check_self_dispatch_guard", "check_self_dispatch_guard 钉住五处要点（平台层「评论唤起新实例（平台侧的派发入口）」的 L1 本体与判定标准四态（新增评论指向本次唤起名 / 以\"分两步更清楚\"自我豁免 / 实际发出 / 转交他人代发）+ 判据钉在\"这条评论发出去没有\"+ 正当形态（先停 + 一次\"停下确认\"、由人另发评论）；通用层「派发入口」的同口径条；两个提示词代码块内的同口径步骤；PROMPTS.adoc 与 README.adoc 的登记同步；调度器两处识别特征），**并钉住该禁令的适用面**（用户澄清\"这个只适用于 cnb\"）：平台层须写明\"须由与执行者相同的 Agent 承担验证\"**只在本平台成立**、**本平台之外不适用**、环境不提供同 Agent 子执行者时**不得援引该条拒做或把任务停在中间**且**验证与交付不因此缺失**；通用层须写明\"**不是无条件成立的规则、以平台层写明为前提**\"；`specs/general/verify.adoc` 须标注\"**适用面由平台层限定**\"——**重点拦\"把禁令删掉/降级成建议\"、\"把转由他人代发删掉\"、\"把适用面删掉（该要求被外推成平台无关的强制前提）\"三种降级**；运行时事实（见 GUARD_CHECK_LIMITS）"),
    ("需求先找参照物：调整内容（含新增）时须先检索现成可参照的业界标准/通行设计范式/本项目先例，有更优的设计用更优的、查不到须说出查证方式并标未确证", "specs/general/planning.adoc", "script/check_specs.py",
     "check_dev_flow_guard", "check_dev_flow_guard 钉住 planning.adoc「需求先找参照物（L1）」的条与三类判定标准（说不出参照物与检索动作 / 有标准可循却自造一套说法 / 有更优设计却按原口述照收且未说明理由）、必加载层的一行重申、公共片段 `baseline-and-compat` 与两个提示词题面的同口径句、PROMPTS 与 README 的登记；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("规范收录侧须先找参照物、别自己造：提案校验须查现成业界标准与更优设计（存在比用户口述更优的设计时按更优的设计收）", "specs-project-maintainer/spec-lifecycle.adoc", "script/check_specs.py",
     "check_spec_admission_guard", "check_spec_admission_guard 钉住「新增规范的提案校验」的三处要点（先找参照物、别自己造 / 存在比用户口述更优的设计时按更优的设计收 / 检查是否已有标准与本项目条目）；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("开发流程：先查现状/先调研最佳方案/先定基线（既有用例先跑通并留证、清单还要先核『够不够用』）、大范围改动先确认、不得绕开既有体系另写一套、老用例不得为迁就改动而改判", "specs/core/execution.adoc + specs/general/planning.adoc + specs/general/testing.adoc", "script/check_specs.py",
     "check_dev_flow_guard", "check_dev_flow_guard 钉住必加载层四条底线（动手前先摸清现状与最佳方案／不得绕开既有体系另写一套／大范围改动先确认／改动前先定基线，含『清单够不够用』的基线完整性要素、**基线的适用边界**：规范类必做/代码类默认不做（除大规模重构或会改动大部分内容）/移动重命名不算）与生命周期两节点、通用层 planning.adoc 的展开与依据（含「基线的适用边界」条与基线完整性 L2 条：先 review 既有用例、只补本次直接相关面、无关存量缺口不阻断）、verify.adoc 验证侧的『跑的那套够不够用』、testing.adoc 的『重构后须同时满足既有用例与新用例』『兼容性无法满足时先确认』『基线里的用例须按用例设计复核』、公共片段 `baseline-and-compat`/`compat` 与两个提示词的 include、调度器与 PROMPTS/README 登记；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("运行环境须与项目声明一致（jdk1.8、python2 等；换别的版本也能跑通也不得换，声明不可得时标未确证）",
     "specs/general/ci-cd.adoc", "script/check_specs.py",
     "check_runtime_env_guard",
     "check_runtime_env_guard 钉住条文与 L1、判据两句、声明落点（不另立第二真源）、降级路径（未声明先确认 / 不可得标未确证不得记为通过）、依据行，以及必加载层、验证、基线三处引用与调度器识别特征、维护方与图书馆落点；『某次到底用了哪个版本』运行时事实（见 GUARD_CHECK_LIMITS）"),
    ("评论不得删除：任何情况下不得删除 Issue/PR 的评论（含 NPC 生成的）",
     "specs/platform/cnb.adoc + specs/core/execution.adoc + specs/general/collab.adoc", "script/check_specs.py",
     "check_comment_preservation_guard",
     "check_comment_preservation_guard 钉住三处落点（平台层「评论不得删除（L1）」：禁令本体含 NPC 生成的评论、不可逆与留证落点的理由、编辑同效、更正而非抹掉的正当处置、四条判定标准、与临时产物清理和禁合并的边界；通用层「派发入口」的平台无关同口径条；必加载层「破坏性操作」写明本条**不是**『先确认即可执行』的一类）与调度器识别特征、README 目录说明同步；**重点拦『把禁令删掉』与『降级成先确认即可删』两种降级**；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("脚本头部注释（文档头）先行：动手先把用途/用法/参数/环境变量/行为边界/关键约定与设计决策写进文档头（细节不随维护丢失）",
     "specs/general/script.adoc", "script/check_specs.py",
     "check_script_header_guard",
     "check_script_header_guard 钉住通用层「脚本头部注释（文档头）」的九条要点（文档头先行、脚本必须写文档头、条目含关键约定与设计决策、设计决策写成『决策 + 理由 + 边界』、取值写抽象描述或常量名而不写硬编码数值、决策留头部/文件级文档注释不落进方法体、超出块注释容量的内容移交独立文档并一行回指、篇幅不设上限、入口注释不复述逻辑层契约）、技术栈落点（`specs/stack/python.adoc` 用模块 docstring 承载且不另起块注释、bash/batch/powershell 各写明入口注释只写入口自己）、调度器识别特征与 README 同步、图书馆依据（adoption 登记为本站取舍并标未确证、sources 有 PEP 257/25010/29148/MADR 主题段与同义性差异）；『某份脚本的文档头是否真的先行、是否真的写了决策理由』属运行时/引用方行为（本仓库不可见）"),
    ("脚本文档的承载位置与协作粒度：脚本默认单打独斗、各脚本相互独立，文档随脚本落盘、不逐脚本另建独立文档（多行文档注释 → 多行块注释 → 普通注释）",
     "specs/general/script.adoc + specs/general/coding.adoc", "script/check_specs.py",
     "check_script_selfdoc_guard",
     "check_script_selfdoc_guard 钉住「脚本文档的承载位置与协作粒度（默认写进脚本自身）」的五处要点（脚本默认单打独斗且多脚本彼此独立、承载方式的**三级优先级**、默认写在脚本里不另建独立文档、唯一例外是内容超容量时的移交并给判定标准、大规模团队式协作是例外不是默认）、`specs/general/coding.adoc`「注释」的脚本例外条（缺则原文会被读成'脚本也要按类/方法那套、文档另建'）、技术栈落点（python 模块 docstring 且单文件脚本同样不另建文档；bash/batch/powershell 三个无机制栈各写明用多行块注释承载、批处理限 `rem`；powershell 用基于注释的帮助）、调度器识别特征与 README 同步；**本条只钉要点文本仍在**——『某个项目的脚本实际把文档写在哪、有没有为单个脚本另建文档』语义判断（见 GUARD_CHECK_LIMITS）"),
    ("跨环境脚本：一份跨平台逻辑 + 各平台薄壳入口（逻辑不得写两遍、入口不得承载逻辑、参数与退出码原样传递、不拿裸 shell 当逻辑层）",
     "specs/general/script.adoc", "script/check_specs.py",
     "check_cross_platform_script_guard",
     "check_cross_platform_script_guard 钉住通用层「跨环境脚本（入口 + 跨平台逻辑 + 实现语言取舍）」的要点（逻辑只写一份放跨平台逻辑脚本；入口层不得承载逻辑并给可判定判据；参数与退出码原样转交/原样返回；不得在另一平台重写逻辑；入口按各自平台规范落盘；实现语言取舍的默认优先级与『不拿裸 shell 当逻辑层』；不假设逻辑脚本所处目录；**入口与逻辑脚本同处一目录、主名相同**；**入口语言按平台默认具备者选**（Windows `.bat`/`.cmd`、Linux/macOS `.sh`）；**调用方不加前后命令**（只给脚本名即可跑，必要参数除外）；入口不设前置步骤、不得为跑逻辑自加命令或给逻辑脚本塞参数）与技术栈三个脚本栈文件的引用承接与各栈落点/命名/入口语言要点、调度器识别特征、README 同步、图书馆同义性差异；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("Windows 批处理（`.bat`/`.cmd`）的专属规则有独立栈文件：行尾 CRLF、纯 ASCII 不写 BOM、块语句延迟展开、`exit /b %errorlevel%` 原样返回退出码、不混写 PowerShell 语法",
     "specs/stack/batch.adoc + AGENTS_COMMON.adoc", "script/check_specs.py",
     "check_cross_platform_script_guard",
     "check_cross_platform_script_guard 钉住批处理栈文件存在、承载 BATCH_STACK_KEYS 全部要点（编码/行尾、薄壳与 `exit /b %errorlevel%`、延迟展开、引号与 `%~1`、`@echo off`、未定义变量、不混写 PowerShell 语法）、指向通用层「跨环境脚本」节，以及 powershell.adoc 反向指向它（引用不复制）与调度器技术栈层登记；语义判断（见 GUARD_CHECK_LIMITS）"),
    ("数据字典按作用域归档、只引名称、新增与调整内容时即生效", "specs/general/terminology.adoc + AGENTS_COMMON.adoc", "script/check_specs.py",
     "check_data_dictionary_guard",
     "check_data_dictionary_guard 钉住通用层《数据字典》的判据本体（不是轴名——只核『这一节在不在』属防线空转）：只引名称不引定义、**作用域分档表逐档在表里**（判定按表行 `| <档位>`，含**当前文档档=定义写在该文档开头**——用户点名的那句）、每档只一处、分档判据可核对、条目形态照 ISO 1087 且定义与使用说明分列、反膨胀判定标准、**每次新增与调整内容时都须判定**（用户原话「每次新增、调整内容时都应该生效」）、图书馆等不在默认引用面内的落点按其自身规则走；并钉住四处落点同口径（调度器登记与识别特征、`doc.adoc`「文档组织与导航」与 `encoding.adoc`「术语统一」两处互引）；**本条防的不是『没写规则』而是『写了规则却仍然膨胀、仍然各写一遍』**——『某个名称到底该归哪一档、某处是否真的复述了定义』语义判断（见 GUARD_CHECK_LIMITS）"),
    ("交付形态与报告落点：不得只冒一句过程性叙述、不得只交付不汇报", "prompts/_common.txt + PROMPTS.adoc", "script/check_specs.py",
     "check_delivery_guard", "check_delivery_guard 钉住 `delivery` 片段的报告落点（过程性叙述不得作为独立评论发出）+ **输出通道只有两条**（最终汇报 / 必须停下确认，且『除这两条之外的任何中间话一律不发』——只写例外形态不写默认动作时，执行者会自造第三条通道、判据回到执行者手里）与交付形态两态（有改动却未提交未推送 / 无改动却未说明）、两个提示词内的『交付即汇报』步骤（同含两条通道）、以及 PROMPTS.adoc 与 README.adoc 的登记同步、**`_common.txt` 的每个片段都须被某份提示词 `include`**（防『定义了但没人 include』的死内容——本轮实测：`no-self-dispatch` 片段写好、两个提示词只在末句复述其大意，include 一次都没有，该 L1 在装配层为空）；**本轮实测失效**：一轮 NPC 任务唯一对外的输出就是一句过程性叙述、既无汇报也无任何提交，旧版片段只写『有改动必须提交推送』、恰漏『无改动也是完成态』与『过程性叙述不得外发』；语义判断（见 GUARD_CHECK_LIMITS）"),
]


def display_width(text: str) -> int:
    """按终端显示宽度计算字符串宽度（CJK 字符按 2 列计）。"""
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in text)


def _pad(text: str, width: int = NAME_WIDTH) -> str:
    """条款名右侧补空格到统一列宽，保证多行清单左对齐。"""
    return text + " " * max(0, width - display_width(text))


def evaluate(root: str = HERE) -> list:
    """逐条判定抓手状态。root 可注入以便测试（不依赖真实仓库）。

    判定仍只看**抓手文件在不在**（这是"有无机械抓手"的机械判据）；`grip_name` 的
    存在性、可调用性与一致性由 `script/check_specs.py` 的 `check_guard_manifest` 核对
    ——两处分工不同：这里判"有没有"，那里判"说的是不是那一道"。
    """
    rows = []
    for name, source, grip, grip_name, note in MECHANISMS:
        if grip is None:
            status = "no-grip"
        elif path.isfile(path.join(root, grip)):
            status = "has-grip"
        else:
            status = "grip-missing"
        rows.append({
            "name": name, "source": source, "grip": grip,
            "grip_name": grip_name,
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
    parser.add_argument(
        "--list", action="store_true",
        help="只打印台账逐条（条款 -> 抓手 -> 备注，不打印分栏清单）——"
             "供按依据名反查「这条规范由谁钉住」时取用")
    args = parser.parse_args(argv)

    # 默认按仓库根（script/ 的上级）解析抓手相对路径
    root = path.dirname(HERE)
    rows = evaluate(root)
    if args.list:
        # 逐条台账：依据名反查的入口（与 `check_specs.py` 的防线清单表分工——
        # 那张表答"有哪些防线、按什么次序跑"，本输出答"某条规范有没有抓手"）。
        for r in rows:
            grip = r["grip"] or NO_GRIP_DECLARED
            print(f"{r['name']}\t{r['source']}\t{grip}\t{r['note']}")
        return 0
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
