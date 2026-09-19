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
    ("INSTALL 模板代码块逐字保留（换行/空行不丢失）", "INSTALL.adoc",            "script/check_specs.py",
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
     "check_review_guard", "check_review_guard 钉住判据条与两个方向的约束（去限定词后仍成立＝全局性 / 只有某一处能触发＝范围性 / 全局性问题不得写进范围性落点 / 全局备注不夹带范围性内容 / 范围性问题不上升为全局规范）仍在，并要求必加载层执行原则与 doc-design「信息归属」两处引用未断；『某次备注究竟属全局还是范围』属语义判断，交人/子 agent 复核"),
    ("文件移动/重命名必须 git mv（防历史断裂）", "specs/core/execution.adoc",       "script/check_specs.py",
     "check_git_mv_selfcheck",      "check_git_mv_selfcheck 覆盖**本仓库自身侧**（暂存区不得出现 delete+add 形态）；**引用方侧**本仓库看不到、仍靠遵守 + 各项目按 git 规范自检"),
    ("测试文件后缀式命名（禁 test_ 前戳）",       "specs/general/testing.adoc",      None,
     "无机械抓手",
     "无机械抓手：靠遵守；Java 测试类另须与源类同包路径、类名为「被测类名 + 测试类型后缀」（specs/stack/java-testing.adoc「测试类命名」：Tests/BootTests/PerfTests/IT），存量为随动迁移、不一次性收敛（specs/core/execution.adoc「规范变更的存量处理」）"),
    ("Java 测试类四类后缀命名契约（Tests/BootTests/PerfTests/IT）", "specs/stack/java-testing.adoc", "script/check_specs.py",
     "check_java_test_naming", "check_java_test_naming 钉住规范与 AGENTS_COMMON 调度器登记两侧都含四类后缀判据；「某项目某个类该用哪个后缀」属语义判断，交人/子 agent review"),
    ("Java 测试类拆分裁决（一个被测类可拆多个类，但同分类同属性须归一类、不得滥拆）", "specs/stack/java-testing.adoc", "script/check_specs.py",
     "check_java_test_naming", "check_java_test_naming 钉住规范侧三段判据（可拆声明 / 同分类同属性须归一类 / 禁止滥拆）与调度器侧同口径——「可拆但不得滥拆」是单一语义，只剩一半即被读成『每个场景一个类』或『一个被测类一个类』；「某次拆分是否真由分类驱动」属语义判断，交人/子 agent 复核"),
    ("校验范围只限公共内容与本仓库工具（不检查引用方项目工作区）", "AGENTS.adoc", "script/check_specs_test.py",
     "script/check_specs_test.py", "TestScopeStaysOnCommonContent 钉住 check_specs.py 不得读 git 工作区状态/HEAD"),
    ("最高关注项不得被删或降级（P1/P2/P3/P5/P6 条款 L1、P4 条款 L2、同列最高关注项）", "specs-project-maintainer/priority.adoc", "script/check_specs.py",
     "check_priority_guard", "check_priority_guard 钉住公共侧分级定义与最高关注项（含保留形态）、维护方侧 P1-P6 各自级别与『依据』行（P6 另钉正文口径：强制同 Agent 须在、旧口径『换外部来源』不得复活），以及 P1/读取/破坏性操作/来源真实性的必加载层落点；『条目级别是否与其实际后果相符』无机械抓手（等级越高验证越严：ISO/IEC Directives Part 2），由人/子 agent 复核承担"),
    ("定级口径（定级四问 + 条款类型判定表）不得被删", "specs-project-maintainer/spec-lifecycle.adoc", "script/check_specs.py",
     "check_spec_admission_guard", "check_spec_admission_guard 钉住『如何给一条规范定级』『与条款类型一一对应』『归属谁』『归类举证』『级别变更与复盘』五个节仍在（口径被删则级别重新混乱）"),
    ("定级方法论与元规范不得涨回常驻层（常驻层只放 L1 底线与最高关注项）", "specs-project-maintainer/priority.adoc", "script/check_specs.py",
     "check_priority_guard", "check_priority_guard 拦住常驻层再次出现『设级别』等定级方法论节；『常驻层体量是否反弹』属体量判断，交人/子 agent 复核"),
    ("规范集合自身重构须按固定顺序（先判归属 → 再判层级 → 再判重复 → 压缩表述）", "specs-project-maintainer/spec-lifecycle.adoc", "script/check_specs.py",
     "check_spec_admission_guard", "check_spec_admission_guard 钉住重构顺序三要点仍在（顺序颠倒会把放错位置的内容直接删掉）"),
    ("同一条规则的两种读法（执行侧只给'怎么走'、依据与取舍归思考/决策侧）", "specs-project-maintainer/spec-lifecycle.adoc", "script/check_specs.py",
     "check_spec_admission_guard", "check_spec_admission_guard 钉住「同一条规则有两种读法」节；常驻层侧由 check_priority_guard 钉住『怎么走』形态声明与各最高关注项的『依据』行（依据不得被整段删掉）；一句话里是否真的没夹解释属文风判断，交人/子 agent 复核"),
    ("重构后须核对规范有效性（两形态分离 / 可执行性不降级 / 可见性不丢）", "specs-project-maintainer/spec-lifecycle.adoc", "script/check_specs.py",
     "check_spec_admission_guard", "check_spec_admission_guard 钉住「重构后须核对规范有效性」节；判据是否真未被压成口号属语义判断，交人/子 agent 复核"),
    ("读取按最小必要、长会话简单任务在干净上下文执行（P4）", "specs/core/execution.adoc", "script/check_specs.py",
     "check_priority_guard", "check_priority_guard 钉住 P4 存在性与 execution.adoc 对 context.adoc 的引用；读取是否真越界属运行时行为，靠 agent 自检 + 人 review"),
    ("去重不得误删最高关注项的引用", "AGENTS.adoc", "script/check_specs.py",
     "check_priority_guard", "check_priority_guard：最高关注项的存在性机械钉住（引用是否被删由该防线兜底发现）"),
    ("从属者（子 agent/被引用方）加载由已加载入口驱动、不靠自报", "AGENTS_COMMON.adoc", "script/check_specs.py",
     "check_delegation_guard", "check_delegation_guard 钉住『从属者』机制仍在（否则子 agent/被派发任务可'没被告知'为由跳过加载）；'实际是否真按入口加载'属运行时行为，靠遵守 + 人 review"),
    ("改完规范须验证三视角：①完整性 + ②有效性与认知质量 + ③接纳面（同一子 agent）", "specs/general/testing.adoc", "script/check_specs.py",
     "check_verify_guard", "check_verify_guard 钉住公共「验证总纲」「规范验证」「验证的效力等级」「验证的适用边界」「运行契约」各节、三视角与标准出处、②的判据、'三视角合用一个干净子 agent'、'每次验证换干净上下文'，并核对维护方落点两处口径一致；「子 agent 是否真按三视角答全」属运行时行为，靠派发指令 + 人 review"),
    ("验证须能枚举\"验了什么、怎么算过、依据哪个标准\"（防退化成跑绿脚本、慢慢脱离初衷）", "specs/general/testing.adoc", "script/check_specs.py",
     "check_verify_guard", "check_verify_guard 钉住「验证总纲」节与标准出处（ISO/IEC Directives Part 2 / RFC 2119 / ISO 10007 / ISO/IEC/IEEE 25010 / IEEE 1028 须在）；「本次是否真逐项枚举」属运行时行为，靠留证 + 人 review"),
    ("公共内容不得声明机械防线的存在（防线属维护方、随规范分发即宣称与实际不符）", "specs-project-maintainer/spec-lifecycle.adoc", "script/check_specs.py",
     "check_no_mechanism_claims_in_public", "check_no_mechanism_claims_in_public 拦住『当前由某防线钉住』式声明句与裸防线名；该表述是否真在宣称防线由人/子 agent 复核"),
    ("公共内容须自足：不得引用引用方看不到的私有落点（一个文件可同时装公共与项目规则）", "AGENTS_COMMON.adoc + specs/", "script/check_specs.py",
     "check_public_content_is_self_contained", "check_public_content_is_self_contained 机械拦住公共内容里指向维护方自查层（specs-project-maintainer/）的引用——该层不随公共内容分发，引用方读到的只是死链；『某条规则是否真需自足表达』属语义判断，交人/子 agent 复核"),
    ("公共内容被未知项目加载时的可控性（影响面/成本/可控性）", "specs/general/testing.adoc", "script/check_specs.py",
     "check_adoption_guard", "check_adoption_guard 钉住「运行契约」节、三维判据与维护方承接清单登记；另由 check_public_content_has_no_private_refs 机械拦住\"公共内容把本仓库私有物当抓手引用\"（引用方读到的死链）；「某条具体规则落到未知项目里会不会静默推翻其约定」属语义判断，交人/子 agent 复核"),
    ("任务各节点须自查（提出/理解/方案/执行/验证/交付/复盘）", "specs/core/execution.adoc", "script/check_specs.py",
     "check_lifecycle_guard", "check_lifecycle_guard 钉住节点清单以表格行存在、并钉住『哪些节点不设』的独立声明；『某个节点上是否真的自查了』属运行时行为，靠 agent 遵守 + 人 review"),
    ("CI 校验链完整：流水线须跑全既定校验（含配套测试），测试文件须能被框架自动发现", "specs/general/ci-cd.adoc", "script/check_specs.py",
     "check_ci_cd_guard", "check_ci_cd_guard 钉住「校验链完整」节与『只跑主校验脚本』『能被测试框架自动发现』两要点（实证：CI 只跑 check-specs.py，配套测试长期零执行、其中一个测试文件因命名无法被自动发现）；『某个项目 CI 是否真跑全了』属运行时/配置判断，交人 review"),
    ("CI 触发路径须覆盖校验对象、上游依赖须实测可用、执行须有可判定超时", "specs/general/ci-cd.adoc", "script/check_specs.py",
     "check_ci_cd_guard", "check_ci_cd_guard 钉住「触发与作用范围」「依赖与外部资源可用性」「超时与资源」关键要点（实证：引用不存在的镜像在 Prepare 阶段失败、流水线长期 pending）；『具体取值是否合理』交人 review"),
    ("平台上的派发与复核须钉定 commit sha（分支名不是稳定标识）、确认执行者可用", "specs/platform/cnb.adoc + specs/general/collab.adoc", "script/check_specs.py",
     "check_ci_cd_guard", "check_ci_cd_guard 钉住 CNB 侧『派发与复核须钉定 commit sha』『压缩提交/强推会替换对象』『git fetch -f』『派发前确认执行者实际可用』『流水线不无界挂起』与 collab 侧『派发对象须钉定 commit sha』『派发前确认执行者可执行』；『本次是否真按 sha 取对象』属运行时行为，靠遵守 + 人 review"),
    ("验证须覆盖项目全部既定校验手段、验证对象须钉定 commit sha", "specs/general/verify.adoc", "script/check_specs.py",
     "check_ci_cd_guard", "check_ci_cd_guard 钉住验证侧『验证须覆盖项目的全部既定校验手段』『验证对象须钉定 commit sha』两要点；『本次是否真跑全了』属运行时行为，靠留证 + 人 review"),
    ("子 agent 复核须自带硬超时、到点视为失联并放弃（防任务永久挂起）", "specs/general/collab.adoc", "script/check_specs.py",
     "check_checklist_guard", "check_checklist_guard 钉住『硬超时』『超时的处置』两要点仍在（否则“派了就一直等”重新出现，实证为外部评审卡 1h+ 未回传）；『本次是否真的设了时限并在到点时放弃』属运行时行为，靠留证 + 人 review"),
    ("子任务强制同 Agent、不得点名外部 Agent/NPC", "specs/general/collab.adoc", "script/check_specs.py",
     "check_delegation_guard", "check_delegation_guard 钉住五处要求的多要素（同 Agent 判据 / 不得点名外部 NPC / 可核对的判定标准 / 同 Agent 不可用时的降级路径 / 优先一次性调用）仍在，并**双向**钉住口径：新口径须在、把外部来源重新放宽的旧口径措辞（备选/次选/(也)可换外部/优先同源）不得复活（含清单概览行与公共侧各落地处，禁止式表述与反例引用除外）；『本次派发是否真同 Agent、有无点名外部 NPC』属运行时行为（派发与评论的实际内容），机械无法判定，交人/子 agent 复核"),
    ("语义复核留证须是三态台账（通过 / 未发现问题 / 悬置，不得合并）", "specs/general/testing.adoc", "script/check_specs.py",
     "check_checklist_guard", "check_checklist_guard 钉住『三态』『悬置』两要点仍在；『具体某次留证是否真按三态分列』属产物内容判断，交人/子 agent 复核"),
    ("验证按改动性质取值（代码类走机械判据、规范类才做三视角与全局核对）", "specs/general/testing.adoc", "script/check_specs.py",
     "check_lifecycle_guard", "check_lifecycle_guard 钉住「验证的适用边界」节、两类改动、唯一判据问句、『不得互串』『取更严的一侧』与『每次验证换干净上下文』；『本次是否真按性质取值』属运行时行为，靠遵守 + 人 review"),
    ("规范何时该拆分（默认不拆、三条硬条件、拆后逐项自洽核对）", "specs-project-maintainer/spec-lifecycle.adoc", "script/check_specs.py",
     "check_lifecycle_guard", "check_lifecycle_guard 钉住「一条规范何时该拆分」与「拆分后的自洽核对」两节及三条硬条件、默认不拆、单独过准入九问；『某次拆分是否由实害驱动』属语义判断，交人/子 agent 复核"),
    ("执行环境能力先自评、无机制走降级路径且不空自评", "specs/general/self-check.adoc", "script/check_specs.py",
     "check_delegation_guard", "check_delegation_guard 钉住『环境能力自评』节仍在（否则环境无清空/无子 agent 时会照抄'已清洁上下文/已委派'）；'自评是否属实'属运行时行为，靠遵守 + 人 review"),
    ("常驻层体积与调度器条目数不得无上限膨胀", "AGENTS_COMMON.adoc", "script/check_specs.py",
     "check_budget_guard", "check_budget_guard 钉住必加载层字节上限与调度器条目数上限；'体量与层级的语义是否合理'仍交人/子 agent 复核"),
    ("单个规范文件的软阈值（超线只提醒、不强制拆分）",
     "specs-project-maintainer/spec-lifecycle.adoc「单个规范文件的软阈值」",
     "script/check_specs.py",
     "check_file_size_hint",
     "check_file_size_hint 钉住『超线须有提示』且『**不得**进 errors/退出码』两件事（提醒与硬上限的分界）、"
     "范围边界（常驻层与图书馆不吃本阈值）；"
     "『某个超线的文件到底该归位、该拆、还是确实不拆』属体量/层级的语义判断，交人/子 agent 复核"),
    ("提示词主侧重（方向前提）与优先级不得被删/降级", "PROMPTS.adoc", "script/check_specs.py",
     "check_prompts_primary", "check_prompts_primary 钉住 PROMPTS.adoc 主侧重登记、各提示词 primary 声明与 priority-rules 的 L1/L2/L3"),
    ("对外能力的可替换点须有唯一装配点、须有可用默认（接入成本是设计指标）", "specs/general/coding.adoc", "script/check_specs.py",
     "check_abstraction_adoption_guard", "check_abstraction_adoption_guard 钉住「抽象与接入成本」节的两条 L1（唯一装配点、可替换点须有可用默认或显式必填声明）与其判定特征、四条要点齐全、L1/L2 级别标注、依据行在、Spring「配置」侧引用承接；『某个抽象是否真的做到了唯一装配点』属引用方项目代码（本仓库不可见），交人/子 agent 复核"),
    ("既有实现与先例优先（先查项目已有能力与先例，禁止手写原生写法绕过）", "specs/general/coding.adoc", "script/check_specs.py",
     "check_reuse_precedent_guard", "check_reuse_precedent_guard 钉住通用层两条 L1 条文与典型反例（UUID 手写、集合判空手写）、Java 栈 java-syntax.adoc 优先级顺序（项目自有/已引入库须排在 JDK 之前）、java.adoc 的识别特征与 README 同步；『某次编码是否真的先查了先例』属引用方项目行为（本仓库不可见），交人/子 agent 复核"),
    ("跨语言执行脚本须放资源文件夹、扩展名取被调语言的扩展名，且按性能敏感度决定读取时机（不写字符串拼接/模板、热点路径不每次读）", "specs/general/coding.adoc", "script/check_specs.py",
     "check_external_script_guard", "check_external_script_guard 钉住通用层「跨语言执行脚本的落点（资源文件夹，不写字符串拼接/模板）」的四条 L1（落点／扩展名取被调语言，无通用扩展名时取该技术支持的文件形式如 MyBatis 的 `*.xml`／按资源读取后执行／加载时机：性能敏感路径首次读取一次并缓存、需求要求内容可变的不适用缓存）、可逐条核对的判定标准与典型反例、依据行，以及 Java 落点（`sql`/`lua` 放 `src/main/resources/`、Redis 用 `DefaultRedisScript` 按静态常量声明、MyBatis 的 `${}` 白名单、`EVALSHA` 复用）与 Java 侧加载时机、Spring 引用承接、调度器两处登记与 README 同步；『某次编码是否真的把脚本放进了资源文件夹、是否真的只读一次』属引用方项目代码（本仓库不可见），交人/子 agent 复核"),
    ("本仓库 changelog 除非主动声明，否则不新增、不修改（默认动作是不改）",
     "AGENTS.adoc「版本与变更记录」", "script/check_specs.py",
     "check_changelog_timing_guard",
     "check_changelog_timing_guard 钉住本仓库的默认动作条（除非主动声明否则一律不新增不修改）"
     "、『主动声明』的判据（用户本次明确要求新增/修改/整理/压缩 changelog 或改写其组织方式与条目形态）"
     "、未声明的越界形态（未提到该文件／只要求更新文档或 README／只说『改动了什么』／概括转述不算）"
     "与顺手补一条、以及与抓手登记；『某次是否真的自行新增或改写了条目、用户声明到底成不成立』"
     "属运行时行为与语义判断（提交内容与评论记录），机械无法判定，交人/子 agent 复核"),
    ("Maven 未配置过仓库/镜像且外网出口 IP 在中国大陆时，须用指定中央仓库",
     "specs/stack/maven.adoc",
     "script/check_specs.py",
     "check_maven_mirror_guard",
     "check_maven_mirror_guard 钉住该节仍在、指定仓库地址、**触发前提**（未配置过 Maven 仓库/镜像"
     "**且**外网出口 IP 在中国大陆——两半缺一即等于放行，只写『未配置过才做』会被读成无条件）、"
     "优先用该仓库、换源边界（**仅当它不可用**才可改用**在境内**的其他镜像站——该限定缺位即等于放行境外源）"
     "与『已配置过即不做』；配置方式不在本规范约定（按 Maven 官方机制自行完成），"
     "**实际是否真的用上了该仓库**属引用方运行时事实（构建日志与环境配置，本仓库不可见），交人/子 agent 复核"),
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
     "属引用方项目行为（测试类注释与性能测试文档的实际内容），交人/子 agent 复核"),
    ("代码质量（新产出即高质）：十项逐条自检须可判定（坏味道/职责与嵌套/命名/可读性/失败与边界/资源/并发/性能退化/测试与文档/交付前自检）",
     "specs/general/coding.adoc「代码质量（新产出即高质）」",
     "script/check_specs.py",
     "check_quality_guard",
     "check_quality_guard 钉住该节仍在、十项要点与判定标准、存量边界与依据行，以及调度器识别特征与图书馆依据主题 library/quality.adoc（坏味道与可读性依据＋同义性差异与取样状态）；"
     "**本条只钉要点文本仍在**——『某次交付的代码质量到底过不过』属引用方项目代码（本仓库不可见），交人/子 agent 复核"),
    ("生成效率：先定完成判据、一次做对做完、延后验证一次到位、失败一次查根因、按需读取、不重做已做完的事",
     "specs/general/context.adoc「生成效率（同等质量下最少往返）」",
     "script/check_specs.py",
     "check_generation_efficiency_guard",
     "check_generation_efficiency_guard 钉住该节仍在、十条要点与其判定标准（含『本轮交付之后是否需要再改同一批文件』的运行判据）、"
     "**边界条『效率不得越过质量』**与调度器识别特征；"
     "**本条只钉要点文本仍在**——『某次任务到底跑了几轮、有没有把可合并的动作拆开、有没有靠重试撞对』属运行时行为（执行日志与平台侧用量记录），交人/子 agent 复核"),
    ("token 纪律：利用率与节省不是一回事；输入须被用到、约束放外部、少复述多引用、不重复读贴、只记结论与取值；以不损害功能完整性/代码质量/验证完整为前提",
     "specs/general/context.adoc「token 纪律（提高利用率与节省开销）」",
     "script/check_specs.py",
     "check_generation_efficiency_guard",
     "check_generation_efficiency_guard 钉住该节仍在、概念区分的三句（不是一回事／手段大幅重叠／两者的取向）、"
     "利用率判据（答不出用途即无效输入）、约束放外部、少复述多引用、不重复读贴、只记结论与取值，"
     "**以及边界条『三件事不得为省 token 让步』（功能完整性／代码质量／验证完整）**与『不设必须量化 token 的要求』；"
     "**本条只钉要点文本仍在**——『某次任务有没有为省 token 少给信息、有没有复述已知内容』属产物内容与运行时行为，交人/子 agent 复核"),
    ("改动后的 review：每次改动都在同一轮内复核一次（按改动性质取值；规范类按五件事）",
     "specs/general/review.adoc「改动后的 review（每次改完都得复核一次）」",
     "script/check_specs.py",
     "check_after_change_review_guard",
     "check_after_change_review_guard 钉住该节仍在、『每次』与『按性质取值』、改完即审的固定动作（跑机械手段／比基线／核原话／留证）、"
     "『规范类改动不得只跑机械手段』与复核者不可用时的处置，以及依据行（IEEE 1028 / ISO 10007）；"
     "**本条只钉要点文本仍在**——『某次改动到底有没有复核、跑没跑机械手段』属运行时行为（提交内容与产物），交人/子 agent 复核"),
    ("改完规范必做五件事：机械手段必跑全、干净子 agent 三视角复核不可漏（有了就忽略、没有就加）、三态台账、复核者不可用时的降级留证",
     "specs/general/verify.adoc「改完规范必做的五件事（机械手段必跑，干净子 agent 复核不可漏）」",
     "script/check_specs.py",
     "check_after_change_review_guard",
     "check_after_change_review_guard 钉住该节仍在、五件事逐条（①机械手段先跑且跑全含『报红就地修复』②干净子 agent 三视角不可漏含『有了就忽略、没有就加』③三视角一次读取分栏④三态台账『不得合并』⑤降级路径『不得跳过复核／不得换外部来源／标注独立性边界』）、"
     "**只对规范类改动的边界**，以及维护方两处落点（specs-project-maintainer/verify.adoc 与 AGENTS.adoc）；"
     "**本条只钉要点文本仍在**——『某次到底跑没跑机械手段、有没有真的起一个干净子 agent、台账实际填没填』属运行时行为（提交内容、平台侧记录与产物正文），交人/子 agent 复核"),
    ("执行吞吐：独立调用须合并（禁试探式往返）、构建与校验输出一次取到、长流程不零信息空转",
     "specs/general/context.adoc「执行吞吐」",
     "script/check_specs.py",
     "check_throughput_guard",
     "check_throughput_guard 钉住该节仍在、L1 两条（独立调用必须合并＋试探式往返的判定标准／构建与校验的输出须一次取到）"
     "与 L2 五条（读到即沉淀不重复读／往返成本也要算／凭据固化为可复用形态／"
     "缓存与镜像就近且**已配置过即不覆盖不重配**／长流程不留零信息等待）、"
     "常驻层两处引用（最高关注项段落与「任务编排与上下文管理」）与调度器识别特征；"
     "**本条只钉要点文本仍在**——『某次任务到底往返了几轮、有没有把可合并的调用拆成多轮』"
     "属运行时行为（执行日志与平台侧用量记录），交人/子 agent 复核"),
    ("CNB 平台侧执行吞吐：一次唤起=一次完整加载、状态与用量按汇总先取再下钻、不空转等待",
     "specs/platform/cnb.adoc「执行吞吐（平台侧的两处特有代价）」",
     "script/check_specs.py",
     "check_throughput_guard",
     "check_throughput_guard 同时钉住平台侧该节仍在与四条要点（一次唤起=一次加载／"
     "状态先取汇总再下钻／不用零信息往返等长流程／AI 用量与请求明细是本平台的可观测面）；"
     "**本条只钉要点文本仍在**——『某次执行到底做了几轮状态查询、有没有空转等待』"
     "属运行时行为（平台操作记录与 AI 用量明细），交人/子 agent 复核"),
    ("文档中提及类型优先写类名 + import（不写类全名）", "specs/general/doc.adoc", "script/check_specs.py",
     "check_doc_type_notation_guard", "check_doc_type_notation_guard 钉住通用层「注释与文档」下的该条（**L2**：先短类名、需要解析时在就近代码示例里写一条 import，不得用类全名充当标识）与三个必要情形（同名类冲突／无代码示例可承载 import／**该类型不在本仓库的 classpath 内**——即用户口径的『除非不在 classpath 才能写类全名』，写成『不在本仓库/本项目内』即偏严、classpath 内但属他仓/外部的类型会被误禁）、三个例外边界（路径与坐标不是类型名、字符串与配置里必须全限定的场合（@ConditionalOnClass 类名、main-class、反射按名加载、import 本身）、文档自身的文本引用）、不做存量一次性替换的口径；Java 栈「javadoc」的落点（含 {@link}/@see 成员引用与配置/反射照常全限定的边界）与调度器两处识别特征。**为 L2 且判据是语义的（java.util.UUID 一类外部类型全限定属合规），本防线只钉条文与判据仍在、不扫存量文档**——「某处到底该不该写全限定」交人/子 agent 复核"),
    ("无参/必参/全参构造优先用 lombok、不手写构造方法", "specs/stack/java.adoc", "script/check_specs.py",
     "check_lombok_constructor_guard", "check_lombok_constructor_guard 钉住 Java 栈「编码」的条文与 L1、三种构造注解（`@NoArgsConstructor`/`@RequiredArgsConstructor`/`@AllArgsConstructor`）、并存写法、可逐条核对的判定标准、例外（注解表达不了的动作才可手写并写明原因）与存量边界，以及调度器识别特征与 README 同步；措辞回退成建议（尽量用/可手写）亦被拦下。『某个具体类该不该手写构造』属引用方项目代码（本仓库不可见）与语义判断，交人/子 agent 复核"),
    ("多层嵌套对象转换优先声明式映射、JVM 下优先 MapStruct（建议、非强制）", "specs/general/coding.adoc + specs/stack/java.adoc", "script/check_specs.py",
     "check_conversion_guard", "check_conversion_guard 按**建议层口径**钉住通用层「对象转换（多层嵌套对象的转换）」——首选声明式映射、判据是**目标式**的（同一转换只有一处来源、结构变化不静默漏字段）、等价路径（深拷贝/序列化中转/手工构建器）同样合规、除主动声明外优选声明式映射且手写须备注原因、**无嵌套（单层）不在本条范围内**（且不得被抄窄成按字段数判）、例外与边界、存量随动迁移与依据行；**反向钉住条文与栈层不得被写成强制面**（「不允许手写转换代码」「一律用」），并反向钉住通用层不得出现框架专名（`MapStruct`/`@Mapper`/`@Mapping`——替换主语测试）；Java 栈「对象转换（MapStruct）」的优先 MapStruct/建议不手写、`@Mapper` 声明形态、嵌套/集合由映射方法表达、不并存两套写法、非强制与例外；调度器两处识别特征与 README 同步、图书馆取向与如实取样状态登记。'某个具体转换该不该用映射库、该结构能否由映射声明表达'属引用方项目代码（本仓库不可见）与语义判断，交人/子 agent 复核"),
    ("持久化访问强制走统一入口与类型安全查询构造 API（不 new 构造器、不用字符串写列名）", "specs/general/coding.adoc", "script/check_specs.py",
     "check_persistence_access_guard", "check_persistence_access_guard 钉住通用层「持久化访问（数据库/缓存等）」的三条 L1（统一入口／优先类型安全·声明式查询构造 API／替代优先）、可逐条核对的判定标准（构造器 `new`／字符串写列名／绕过统一入口）、例外与边界（不禁止 mapper `*.xml` 承载）、存量随动迁移与依据行；Java 栈「持久化访问（MyBatis-Plus / JPA 等）」的四个 `IService` 成员方法（`lambdaQuery`/`lambdaUpdate`/`ktQuery`/`ktUpdate`）、禁止面（`new QueryWrapper` 及其子类含 `new LambdaQueryWrapper`）、`IService` 之外落点与例外口径；调度器两处识别特征与 README 同步。『某个具体类该不该 new 构造器、该条件能否由 lambda 形态表达』属引用方项目代码（本仓库不可见）与语义判断，交人/子 agent 复核"),
    ("配置类不写逻辑（配置类只保持 POJO 基本功能、逻辑下沉 utils/service）", "specs/general/coding.adoc", "script/check_specs.py",
     "check_config_class_guard", "check_config_class_guard 钉住通用层条文（含『任何情况都不允许』与去向）、判定标准、Java/Spring 识别特征与 README 同步；『某个具体配置类有没有夹带逻辑』属引用方项目代码（本仓库不可见），交人/子 agent 复核"),
    ("执行前自检（非平凡任务须逐项自检，防'加载了却没执行'）", "specs/general/self-check.adoc", "script/check_specs.py",
     "check_self_check_guard", "check_self_check_guard 钉住自检规范文件、适用边界与 execution.adoc 必加载层落点；自检是否真做属运行时行为，靠 agent 遵守 + 人 review"),
    ("不得编造事实与来源（引用真实、标准不编、宁可不引）", "specs/general/source.adoc", "script/check_specs.py",
     "check_source_guard", "check_source_guard 钉住来源规范要点；引用存在性另由 check_refs_exist/check_section_refs 兜底"),
    ("不可逆操作先确认（删除/清空/强推，P5）", "specs/core/execution.adoc", "script/check_specs.py",
     "check_priority_guard", "check_priority_guard 钉住 P5 存在性与「破坏性操作」落点；是否真确认属运行时行为，靠遵守 + 人 review"),
    ("换行符按解释器分流（LF 基准、.bat/.cmd 必须 CRLF、.gitattributes/.editorconfig 固定；仓库根缺这两个落盘口即补齐）", "specs/general/encoding.adoc", "script/check_specs.py",
     "check_line_ending_guard", "check_line_ending_guard 钉住编码规范的分流判据（LF 基准、`.bat`/`.cmd` CRLF、`core.autocrlf`/`.gitattributes`/`.editorconfig` 落盘口）与 bash/python/powershell 栈文件的行尾要求；某文件实际是否为 CRLF、仓库根是否已有 `.gitattributes`/`.editorconfig` 属引用方工作区状态，本仓库不可见，靠引用方 `git ls-files --eol` 自检"),
    ("代码安全底线（输入校验/输出编码/凭据不硬编码）", "specs/general/security.adoc", None,
     "无机械抓手",
     "无机械抓手：具体实现属引用方项目代码（本仓库不可见）；靠遵守 + 该项目的静态检查/SAST"),
    ("依据不得只剩名称：图书馆须可查到、可逐字核对、引用不悬空", "AGENTS.adoc", "script/check_specs.py",
     "check_library_guard", "check_library_guard 钉住图书馆（仓库根 library/，不在默认引用面内）入口与主题文件存在且被项目规范入口登记、入口登记与实际主题双向一致、外部标准逐字引文锚点仍在、馆内引用可解析（悬空即依据链断在这里）；『某条依据是否真的支持该条、依据找得全不全』属语义判断，交人/子 agent 复核"),
    ("馆无体量上限：引用方不全量下载即准确定位依据（主键为内容、非路径）", "AGENTS.adoc", "script/check_specs.py",
     "check_library_locating_guard", "check_library_locating_guard 钉住图书馆入口的『定位协议』要点（作者侧/取用侧之分、入口 = 常驻层的固定地址、三步取值、版本固化只是可选加固、不解析页面结构）、usage 侧的使用判据（取用侧只有 https、主键是内容不是路径、终止条件、不承载派生落点）、sources 侧的机制原文与如实取样状态（git 内容寻址 / RFC 7233，且须标站点与平台视图均未实测到 Range）、**『先取 commit 再拼地址』这一取用前置形态不得回退**、**馆内主题文件名不得过长（≤32 字符：名字不是检索键、却会被读进每次链接与目录列举）**、以及项目规范入口的口径；『该协议是否真的够用』属语义判断，交人/子 agent 复核"),
    ("依据该何时写、怎么反查（写入判据与关联协议）", "AGENTS.adoc", "script/check_specs.py",
     "check_library_guard", "check_library_guard 钉住『依据的写入与关联』主题（library/usage.adoc）的要点锚点：写入触发特征、不写判据、入库必写项、关联协议与**只取一份不遍历**的反查解析算法、**默认引用面与非引用面**的边界；『某条依据实际该不该写、写得够不够』属语义判断，交人/子 agent 复核"),
    ("落点口径须写对：不得把本仓库内容写成\"私有/不对外发布\"", "README.adoc", "script/check_specs.py",
     "check_ref_scope_wording_guard", "check_ref_scope_wording_guard 钉住本仓库维护范围内的 .adoc 不得出现\"本仓库私有…不随规范分发\"\"私有内容不随规范分发\"\"不随规范分发\"三类错误形态（平台事实：本仓库所有内容都会被发布，区别只在\"默认引用什么\"），并豁免引用/纠正该表述本身的句子与\"私有落点/私有抓手名\"这类自足性用语、豁免 CHANGELOG 历史条目；『某处该不该被引用方按入口加载』属判定，交人/子 agent 复核"),
    ("引文段落不得用裸 `>` 起头（会被解析成 callout list 而中断整份文档编译）", "AGENTS.adoc", "script/check_specs.py",
     "check_quote_line_guard", "check_quote_line_guard 钉住仓库维护范围内全部 .adoc 的引文行形态：行首 `> ` 即命中（该形态被 AsciiDoc 的 `listdef-callout` 吃掉、`index` 取空串后在 `List.calc_style()` 里 `assert False`，整份文件编译失败；页面侧 Asciidoctor.js 渲染成引用块、看不出问题）；行内 `>`（比较运算符、shell 重定向）不误伤；写引文用 `[quote]` + 正文行；『某段确实该是引文还是该改写成正文』属内容判断，交人/子 agent 复核"),
    ("变更日志条目须单行（版本号 | 日期 | 变更摘要，条目内不换行）", "CHANGELOG.adoc", "script/check_specs.py",
     "check_changelog_entry_guard", "check_changelog_entry_guard 钉住 CHANGELOG.adoc 的条目形态：条目行（`- 版本 | 日期 | 摘要`）之后不得紧跟续行、单条不得超长（实证失效：日志被当成追加区，同一条目被 heredoc/多次 append 续写成多行而与下一条粘连）；『条目是否记对了变更点、有没有漏记』属内容判断，交人/子 agent 复核"),
    ("变更日志排序方向恒为时间倒序（版本倒序即时间倒序）并以发布版本为一级分组、版本内按类型分组；两种条目形态（流水式/表格式）择一，表格式须有分组列/类型列/变更点/影响四列且影响列不得退化为变更点的同义重复、破坏性变更须逐行标注", "specs/general/changelog.adoc", "script/check_specs.py",
     "check_changelog_structure_guard",
     "check_changelog_structure_guard 钉住三处：①组织形态（**排序方向恒为时间倒序、版本倒序即时间倒序**——版本单调递增时二者一致，故不存在『两种要择一的排序』、正序即错；按版本分组为默认、版本号即发布标识、两种分组口径择一且**不并存**、类型闭集、空分组不写）；②表格形态的判据（四列列义、判据依赖关系与三条反向禁令（不得用类型分级代替破坏性变更标注 / 不得把影响写成变更点的同义重复 / 影响列写不出读者要做的动作即说明不该记）、破坏性变更逐行标注、表格里一条=一个变更点、要素齐备底线四项（类型/变更点/影响/标记））；③图书馆依据（Keep a Changelog / Conventional Commits / Conventional Changelog 三者齐备，且**如实标注是业界约定而非标准**——Keep a Changelog 自述没有标准格式）。实证失效（用户报告）：一个版本改了很多东西时单行流水式日志不可检索，用户对比两个 tag 后要求「根据模块和功能分类，做成一个表格」；反向失效是**换成表格后把影响列省掉**、**用类型列代替破坏性变更标注**，以及**把排序方向写成正序**或把『版本倒序』与『时间倒序』读成两种可择一的排序（用户口径：排序方式还是时间倒序、版本是越来越大的、版本倒序和时间倒序是一样的）。『某条条目是否真的写清了影响、表格是否真的可检索』属语义判断，交人/子 agent 复核"),
    ("提交信息须带类型前缀、破坏性变更须显式标注（`!` 或 `BREAKING CHANGE:` 页脚）", "specs/general/git.adoc", "script/check_specs.py",
     "check_commit_message_guard", "check_commit_message_guard 钉住「提交信息」节的形态（`<type>[(scope)]: <subject>` + 类型固定闭集）、可逐条核对的判定标准（首行无类型前缀即不合规）、破坏性变更须 `!` + `BREAKING CHANGE:` 页脚且**不得把某个类型默认为破坏性的**、正文写「为什么」与边界、以及**如实标注依据是业界约定而非标准**（Conventional Commits 自述 a lightweight convention on top of commit messages）；缺口来源：本集合早已把 Conventional Commits 1.0.0 原文收进图书馆，却只用它支撑变更日志的展示形态——提交信息这一「上游」空着，变更日志的「按类型分组」只能人工归类。『某条提交信息是否真的写清了影响』属语义判断，交人/子 agent 复核；『某次提交有没有带类型前缀』可由提交历史机械判定，属引用方项目的运行时事实（本仓库不可见），靠引用方的提交检查或人 review"),
    ("HTTP 方法与状态码按协议语义使用（安全方法不得产生状态变更、幂等与重试对齐、状态码不得一律包 200、错误响应可统一为 Problem Details）", "specs/general/coding.adoc", "script/check_specs.py",
     "check_http_semantics_guard", "check_http_semantics_guard 钉住「HTTP 接口语义」三处：①条文与级别（安全方法不得产生状态变更 **L1**、幂等与状态码 **L2**、Problem Details **L3 可选**——级别不得被顺手改动）；②适用范围（无 HTTP 接口的项目不适用，避免高频误伤）；③图书馆依据（RFC 9110 安全方法/幂等/状态码与 RFC 9457 的**逐字**引文、以及「判据化取值 vs 标准原文」的同义性差异如实标注）。缺口来源：此前只覆盖路径命名风格，方法与状态码语义未覆盖（`GET` 承载写操作会被爬虫/预取在无人操作时触发副作用；错误包成 `200` 会让重试、缓存、监控与网关策略全部失效）。『某个接口实际用的是哪个方法、返回什么状态码』属引用方项目代码与运行时行为（本仓库不可见），交人/子 agent 复核"),
    ("公共内容覆盖面须有清单且与实际一致（安装入口/公共片段/随规范分发的工具同样会被引用方取到）", "PUBLIC.adoc", "script/check_specs.py",
     "check_public_content_coverage", "check_public_content_coverage 钉住入口清单存在且被项目规范入口登记、两个公开入口都在清单里、清单点名的文件真实存在；『某文件到底算不算公共内容』属判定，交人/子 agent 复核"),
    ("安装取文件须有随规范分发的抓手：清单从入口自身解析、一次取全（不手拼逐条下载命令）", "AGENTS_COMMON.adoc + INSTALL.adoc", "script/check_specs.py",
     "check_spec_fetch_guard", "check_spec_fetch_guard 钉住随规范分发的抓取脚本与其同名平台入口（`.sh`/`.bat`）存在、清单从入口的调度器登记解析（退回手工清单即回到「新增规范就漏一份」）、增量语义、落点边界校验、「不是站点首页」的判据（站点对未命中路径回落 200 + HTML，只判状态码会把 HTML 存成规范）、退出码语义、薄壳三件事与 `.bat` 纯 ASCII+CRLF，以及 INSTALL/AGENTS_COMMON/README 三处登记同步；『取回的副本是否真的与远端一致、清单是否真的取全』属运行时行为，靠实测与留证（本仓库按逐字节比对复核）"),
    ("重新执行安装须能更新现有副本（安装脚本经常更新：以远程为准、内容不同才刷新，失败保留本地那一份）",
     "INSTALL.adoc + AGENTS_COMMON.adoc", "script/check_specs.py",
     "check_spec_fetch_guard",
     "check_spec_fetch_guard 钉住抓取脚本的默认语义是**以远程为准**（每份文件取回的字节与本地比较、"
     "不同才原子落盘；`--keep` 才回到「本地已有即不动」）与**取回失败保留本地已有的那一份**"
     "（不得把副本删掉换成没有），以及 INSTALL/AGENTS_COMMON/README 三处文档写明该语义——"
     "防退回「本地既有就跳过」：它把安装结果绑在「本地以前取过什么」上，远端修好了、加了一节规范，"
     "用户重跑安装仍旧什么都不做（用户实测诉求）；反向也拦「失败也把本地删掉」这把「没更新」"
     "变成「没有」的形态。『某次重跑是否真的取到了最新内容』属运行时行为（远端内容与落点字节），"
     "靠实测与留证（本仓库按逐字节比对、`--keep`/刷新三态各跑一遍复核）"),
    ("多模块项目的模块间依赖须有完整依赖关系文档（UML 表述、查依赖先读它、缺失即新增、不重复声明）", "specs/general/doc-design.adoc", "script/check_specs.py",
     "check_dependency_view_guard", "check_dependency_view_guard 钉住「依赖关系文档（模块间依赖的唯一视图）」节的要点（完整 / UML 优先 / 固定路径可直达 / 先查本文档 / 缺失即新增 / 同提交同步 / 不重复声明 / 与构建工具边界）与两处指向（加载调度器、依赖规范）；『某个项目的依赖视图是否真的完整、有没有过期』属引用方项目产物（本仓库不可见），交人/子 agent 复核"),
    ("安装文档入口占位须保留三要点：优先取到本地副本 / 取不到就直接读远程 / 需要最新规范时再运行一次即是更新",
     "INSTALL.adoc", "script/check_specs.py",
     "check_shared_cache_guard",
     "check_shared_cache_guard（内含 `_check_install_entry_placeholder_lines`）钉住安装文档模板那行的三个要点"
     "——缺『优先取到本地副本』则网络不可达时本地那份可读副本没有了、缺『取不到就读远程』则把可选的一步"
     "读成前置条件、缺『再运行一次即是更新』则用户重跑安装仍拿本地旧副本（而入口占位还会被判成与模板一致、"
     "连那几行都不更新——用户实测两次点名『还是没改』）；`check_install_codeblock` 只核每行独立成行 + 空行完好，"
     "拦不住措辞回退（本轮实测复现：把要点删掉/合并后 `check_specs.py` 仍报 OK）。**本条只钉『优先取到本地副本』、"
     "不钉具体落点**——落点是缓存优先、项目内 `tmp/` 兜底，落点调整不该反向要求改入口模板；"
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
     "名字仍报『有抓手』；清单两条被整条删掉仍报绿。『某次删除是否该被批准』属语义判断，"
     "交人/子 agent 复核"),
    ("入口文档须给『隔一次会话还认得回来』的清单：安装文档路径与取规范脚本路径、副本检索路径、取回与更新方式、要跨会话保留的本项目信息（外置落点须说明由平台缓存目录决定）",
     "specs/general/entry-doc.adoc + INSTALL.adoc", "script/check_specs.py",
     "check_entry_doc_manifest",
     "check_entry_doc_manifest 按**节标题 + 路径链 + 副本三件事**核入口模板（三节在、"
     "『规范与安装文档的位置』给出**三条路径**——规范入口/安装文档/取规范脚本（缺安装文档路径则"
     "新实例不知道去哪儿读安装与更新的做法、缺取规范脚本路径则不知道如何去下载规范，用户实测点名）、"
     "默认落点=用户级缓存且『所有项目共用』、"
     "项目内 `tmp/agent-specs`+`--local`、`fetch-specs`+『再运行一次』、外置落点须说明由平台缓存目录决定），"
     "并核承载判据的 specs/general/entry-doc.adoc（唯一持久落点/新实例只看到项目里的文件/与临时产物的分界/项目自身规范优先）；"
     "『本项目持久化到入口文档的信息』一节须是**指示形态**的提示（本仓库取『尚无…有则逐条追加』）"
     "而**不得预填**成待填清单（`- [ ] …` 一类）——预填会让每个照着模板装出来的项目都带着一份"
     "与它无关的空白清单，并与项目已填的内容打架（本轮实测：预填后旧实现只核标题、仍报绿）；"
     "模板只提示、不预填项目自己的内容，且**不要求逐字**（逐字由 check_install_codeblock 承担）；"
     "『某次安装是否真把项目信息写进了那一节』属运行时行为（目标项目文件），交人/子 agent 复核"),
    ("取规范入口的解释器兜底：不把「机器上有 python3」当前提，且入口不得代为安装运行时",
     "specs/general/script.adoc + INSTALL.adoc", "script/check_specs.py",
     "check_spec_fetch_guard",
     "check_spec_fetch_guard 钉住两个入口**按次序探测解释器、找不到就报错退出**"
     "（`_check_interpreter_fallback_entry_lines`：键须落在**同一条可执行行**上、次序只在"
     "候选代码行之间比较——只核全文关键词时，注释里写一句、或把某一级分支整条删掉都能骗过，"
     "本仓库实测复现；缺一即「没有 python 的机器上装不上规范」），以及安装文档的一组**处置次序**"
     "（`_check_install_no_python_section`：先按本平台既有软件分发方式装一个 python 3、"
     "只装 python2 不算「一个都没有」、入口不得代为安装运行时、报错退出非 0 不得静默继续、"
     "`curl … | python3 -` 那条远程执行形态同样要 python——删掉整节即报红）；"
     "反向钉住 `specs/general/script.adoc`「跨环境脚本」的边界条——**入口不得为「让逻辑跑起来」"
     "安装/下载/解压运行时**（改系统状态、要权限、对调用方不可预期；判据 ISO 9241-110），"
     "并钉住「可以做把逻辑层当命令直接跑的薄壳」这条，防把正当形态一并禁掉；"
     "『某台机器上到底有没有解释器、装了哪一个』属运行时事实（目标机环境），交人/子 agent 复核"),
    ("对外接口命名带所属域/项目前缀（Feign 接口的 `Api` 前须带该域固定前缀，先例优先、无先例取项目名词首组合）", "specs/general/coding.adoc + specs/stack/java.adoc", "script/check_specs.py",
     "check_api_naming_guard", "check_api_naming_guard 钉住通用层条文与 L1、先例优先、无先例取词规则与实例（`user-center` → `UcUserApi`、`open-user-center` → `OucUserApi`）、可逐条核对的判定标准与存量口径，以及 Java 栈落点（Feign、指向通用条）、加载调度器两处识别特征、README 目录说明与图书馆依据落点（含如实取样标注）；『某次是否真的给接口加了前缀、前缀是否真属该域/项目』属语义判断（取决于项目自身的域划分与既有先例），交人/子 agent 复核"),
    ("请求/响应类优先移动复用（给已有接口加内部调用接口时不新建一套，例外只有数据库实体类与含三方类型的类，本项目自身的依赖不算三方依赖）", "specs/general/coding.adoc", "script/check_specs.py",
     "check_api_contract_reuse_guard", "check_api_contract_reuse_guard 钉住通用层条文与 L1、两种例外（数据库实体类除声明外不移动 / 类里引用了第三方类型）、边界（**本项目自身的依赖不算三方依赖**——该字句缺位等于给出一个随时可套用的豁免口）、「移动而非复制、同步更新原引用」的动作、可逐条核对的判定标准（另建同构类 / 同名或仅差包名 / 复制不改原引用 / 以「依赖本项目其他模块」为由拒绝移动 / 移动数据库实体类而无声明）、存量随动迁移与依据行，以及调度器识别特征与 README 同步；『某次是否真的移动了类、是否真的跟随了项目先例』属引用方项目代码（本仓库不可见），交人/子 agent 复核"),
    ("HTTP 接口路径优先用中划线（kebab-case）（不得用下划线或驼峰；服务路由/网关前缀与已发布对外路径照旧）", "specs/stack/spring.adoc", "script/check_specs.py",
     "check_api_contract_reuse_guard", "check_api_contract_reuse_guard 钉住**唯一落点**（技术栈层 `spring.adoc`）的条文与 L1、禁止下划线与驼峰、两处照旧（服务路由/网关前缀、已发布且外部依赖的对外路径）、判定标准（出现 `_` / 路径片段用驼峰或大写 / 同一接口内混用）、存量随动迁移，以及**通用层不得出现「HTTP 接口路径」专条**（该判据只在 Web 框架语境下有定义）与调度器 Spring 条目的识别特征；『某个接口路径该怎么写、是否属两处照旧』属引用方项目代码与语义判断，交人/子 agent 复核"),
    ("索引页只在目录已承载实质文档时要求，空目录不建、索引只做导航", "specs/general/doc.adoc", "script/check_specs.py",
     "check_index_page_guard", "check_index_page_guard 钉住「索引页的触发判据」（已承载实质文档才建 / 空目录与仅有索引页自己的不建 / 索引只做导航不得复制上一级内容 / 模块级导航由模块 README 承担）与 specs/general/doc-module.adoc 的「按需」口径（doc/ 下有实质文档才放 README、无则不建）；实证失效：AI 把「每级目录须有索引页」读宽成「每个模块都建 doc/README.adoc」，批量生成 48 个同构空壳索引）；『某目录该不该有索引页』属语义判断，交人/子 agent 复核"),
    ("评论唤起新实例：评论即一次派发（要求须写清、可要求用干净上下文）", "specs/platform/cnb.adoc + specs/general/collab.adoc", "script/check_specs.py",
     "check_comment_dispatch_guard", "check_comment_dispatch_guard 钉住四处要点（平台层「评论唤起新实例（平台侧的派发入口）」节：入口形态/不放宽任何派发约束/一次评论=一次派发/干净上下文须显式要求且不是保证/仅点名不构成派发；通用层「派发入口」节同口径；AGENTS_COMMON.adoc 两处识别特征；README 目录说明同步），**重点拦『把该入口写成可放宽派发判据或可点名外部 Agent』与『把干净上下文写成默认』两种降级**；『某次派发是否真的按评论要求执行、是否真的用了干净上下文』属运行时行为（评论内容与执行者的实际读取范围），机械无法判定，交人/子 agent 复核"),
    ("改动范围边界：只改当前工作空间/当前项目，未声明即拒绝越界改动（引用 ≠ 授权）", "specs/general/scope.adoc + specs/platform/cnb.adoc", "script/check_specs.py",
     "check_scope_boundary_guard", "check_scope_boundary_guard 钉住两层同口径（通用层 scope.adoc 的「工作空间边界」与「平台上的仓库边界」两节 + 平台层 cnb.adoc 的当前项目口径与指向）+ 提示词公共片段 `scope-boundary` 同口径且两个提示词代码块内都引入；『某次是否真的改到了别的目录/别的仓库』属运行时行为（平台操作记录、实际提交内容、文件系统状态），机械无法判定，交人/子 agent 复核"),
    ("机械防线的核对对象是判据本体、不是轴名（只核『要求/依据/判定标准』等轴名齐备即属防线空转）", "specs-project-maintainer/priority.adoc", "script/check_specs.py",
     "check_criteria_not_axis_guard",
     "check_criteria_not_axis_guard 钉住「机械防线的核对对象是**判据本体**，不是轴名（L1）」一节的四组要点仍在该节的**自身**正文里，"
     "且在维护方入口 `AGENTS.adoc` 可加载：①核对对象（钉判定标准里能拿去核对的那句话，不是轴名/条目标题）；"
     "②失效形态『只核轴名齐备即属防线空转』；③逐条可核对的判定标准（被钉的是轴名 / 抽掉判据句后仍不报红 / 靠相邻条目字样兜住）；"
     "④必配反例用例（『轴名齐全、判据被抽走』的改造下防线必须报红）。本轮实测：维护方最高关注项 P7 的『要求』被压成两句骨架，"
     "『要求/依据/判定标准』三个轴名都还在、防线全绿，而可核对的判据被整段抽掉；教训当时只写在 `script/check_specs.py` 与配套测试的注释里、"
     "**没有进规范正文**——下一个维护者读规范时看不到、只能靠翻脚本注释（判据存在但不可见＝同构复发）。"
     "『某道防线具体钉的是不是判据本体』属语义判断（本通则只钉它自身在不在、要点齐不齐），交人/子 agent 复核"),
    ("压缩提交：用户可明确要求、执行者应当照做（内容零变化、只动本源分支、先确认无人在用旧对象、force-with-lease、声明新旧 sha 对应关系）", "specs/platform/cnb.adoc", "script/check_specs.py",
     "check_squash_commit_guard", "check_squash_commit_guard 钉住八处要点（节与定性 / 判据含内容零变化 / 作用域 / 禁止形态 / 先确认无人在用旧对象 / `--force-with-lease` 与「一般强推口径不适用」 / 与「NPC 禁合并」互不豁免 / 新旧 sha 对应关系声明 + 对象钉定侧的『合规动作』标注 + 调度器与 README 同步），**两边的降级都拦**（把条文删掉/降成建议、以及把用户可要求的压缩提交读成「强推违规」）；『某次压缩是否真的内容零变化、是否真没人基于旧 sha 工作、是否真的用了带租约强推』属运行时事实（git 记录与派发记录），机械无法判定，交人/子 agent 复核"),
    ("重命名与内容修改须分两个提交（P7）；且『合并成一个提交/压缩提交』的请求**未点名本条**时不覆盖它", "specs/general/git.adoc + specs/platform/cnb.adoc", "script/check_specs.py",
     "check_rename_split_guard", "check_rename_split_guard 钉住四处要点（git 规范「重命名与内容修改须分两个提交」整节的条目轴与要点、必加载层 `specs/core/execution.adoc` 的 P7 重申行、`AGENTS_COMMON.adoc`「最高优先级铁律」的登记、维护方清单 `specs-project-maintainer/priority.adoc` 的 P7 条目与级别），**并钉住与「压缩提交」的接口**：用户要求压缩提交/合并成一个提交而**未点名重命名与内容修改**时，压缩只作用于临时中间提交、这两个提交**原样保留**（平台层「压缩提交」须写同口径，防平台侧自行把『要压缩』读成『压回一个』）；例外的『声明』须点名重命名与内容修改、须预先声明（只说合并/压缩不算）；**并按「条目自身」而非「整节关键词」核对**——边界条与平台层接口条的判据（未点名/临时中间提交/原样保留/判定标准）须在**该条自己的正文**里，被抽空或搬进相邻条目即报错（否则相邻条款的字样会兜住已消失的要求；本仓库实测：仅留轴标题、正文另议时旧法静默通过）；『某次是否真的分成了两个提交、压缩是否真的没把它们压掉』属运行时事实（git 记录），机械无法判定，交人/子 agent 用 `git log --follow --name-status`、`git diff <改名提交>^ <改名提交> -M --stat`、`git log --diff-filter=R -M --name-status` 复核"),
    ("压缩/解决冲突后须保留与目标分支的合并关系（目标分支仍是本分支的祖先、合并提交保留双亲、压缩不吞掉合并提交）", "specs/platform/cnb.adoc", "script/check_specs.py",
     "check_merge_relationship_guard", "check_merge_relationship_guard 钉住根因形态（照抄目标分支文件内容后另起单亲提交→目标分支不是祖先→平台仍报 code_conflict）、可核对判据（`git merge-base` 等于目标分支最新提交、`git merge --no-ff` 保留双亲 / `git rev-list --parents -n1`）、`--is-ancestor` 为假这一假绿信号、以及『压缩不吞掉合并提交（它是已并入的凭据）』；『某次合并是否真的建了双亲关系』属运行时事实（git 记录），机械无法在静态文本上判定，交人/子 agent 用 `git merge-base --is-ancestor` 与 `git rev-list --parents` 复核"),
    ("CNB NPC（CI/CD 执行者）严禁合并 PR、人工要求或直授也必须拒绝", "specs/platform/cnb.adoc", "script/check_specs.py",
     "check_npc_merge_guard", "check_npc_merge_guard 钉住六处要点（禁令本体 / 无豁免含『授权不免除』 / 可逐条核对的判定标准 / 与「冲突处理」不矛盾的边界 / 提示词公共片段 `delivery` 同口径 L1 条 / 公开提示词入口 PROMPTS.adoc 同步）；『某次是否真的执行了合并』属运行时行为（平台操作记录与评论实际内容），机械无法判定，交人/子 agent 复核"),
    ("提示词取值路径与装配状态：不得给『渲染视图下已展开』这类与路径绑不上的笼统说法", "PROMPTS.adoc + prompts/_common.txt", "script/check_specs.py",
     "check_prompt_delivery_surface_guard", "check_prompt_delivery_surface_guard 钉住公共片段「查看与复制方式」的按路径判据（装配过的：IDE 预览/asciidoctor/站点页面内渲染；未装配的：远程原始文件地址/本地读取——直出仓库字节、**逐字节一致**）、各提示词读取说明的判定口径、PROMPTS.adoc「取值路径与装配状态」的三行判据表与『不是三种版本的提示词』『L1 实证话术』两条、以及维护方入口的口径与抓手名；**本仓库实证**：把站点原始文件地址当渲染视图、据此以为片段已展开（实测该地址与工作区逐字节一致、指令仍在）；『某次取值实际是否装配过』属运行时事实，交人/子 agent 用 curl 原始文件地址逐字节比对复核"),
    ("不得自行发评论唤起自己：评论派发的\"下一次\"只能由人发起（防无限派发）", "specs/platform/cnb.adoc + specs/general/collab.adoc", "script/check_specs.py",
     "check_self_dispatch_guard", "check_self_dispatch_guard 钉住五处要点（平台层「评论唤起新实例（平台侧的派发入口）」的 L1 本体与判定标准四态（新增评论指向本次唤起名 / 以\"分两步更清楚\"自我豁免 / 实际发出 / 转交他人代发）+ 判据钉在\"这条评论发出去没有\"+ 正当形态（先停 + 一次\"停下确认\"、由人另发评论）；通用层「派发入口」的同口径条；两个提示词代码块内的同口径步骤；PROMPTS.adoc 与 README.adoc 的登记同步；调度器两处识别特征），**并钉住该禁令的适用面**（用户澄清\"这个只适用于 cnb\"）：平台层须写明\"须由与执行者相同的 Agent 承担验证\"**只在本平台成立**、**本平台之外不适用**、环境不提供同 Agent 子执行者时**不得援引该条拒做或把任务停在中间**且**验证与交付不因此缺失**；通用层须写明\"**不是无条件成立的规则、以平台层写明为前提**\"；`specs/general/verify.adoc` 须标注\"**适用面由平台层限定**\"——**重点拦\"把禁令删掉/降级成建议\"、\"把转由他人代发删掉\"、\"把适用面删掉（该要求被外推成平台无关的强制前提）\"三种降级**；\"某次执行里是否真的发了这条评论\"属运行时行为（平台上的评论列表），机械无法判定，交人/子 agent 复核"),
    ("开发流程：先查现状/先调研最佳方案/先定基线（既有用例先跑通并留证、清单还要先核『够不够用』）、大范围改动先确认、不得绕开既有体系另写一套、老用例不得为迁就改动而改判", "specs/core/execution.adoc + specs/general/planning.adoc + specs/general/testing.adoc", "script/check_specs.py",
     "check_dev_flow_guard", "check_dev_flow_guard 钉住必加载层四条底线（动手前先摸清现状与最佳方案／不得绕开既有体系另写一套／大范围改动先确认／改动前先定基线，含『清单够不够用』的基线完整性要素）与生命周期两节点、通用层 planning.adoc 的展开与依据（含基线完整性 L2 条：先 review 既有用例、只补本次直接相关面、无关存量缺口不阻断）、verify.adoc 验证侧的『跑的那套够不够用』、testing.adoc 的『重构后须同时满足既有用例与新用例』『兼容性无法满足时先确认』『基线里的用例须按用例设计复核』、公共片段 `baseline-and-compat`/`compat` 与两个提示词的 include、调度器与 PROMPTS/README 登记；『某次是否真的先跑了基线、是否真的没改老用例』属运行时行为（改动记录、提交内容与测试统计），机械无法判定，交人/子 agent 复核"),
    ("运行环境须与项目声明一致（jdk1.8、python2 等；换别的版本也能跑通也不得换，声明不可得时标未确证）",
     "specs/general/ci-cd.adoc", "script/check_specs.py",
     "check_runtime_env_guard",
     "check_runtime_env_guard 钉住条文与 L1、判据两句、声明落点（不另立第二真源）、降级路径（未声明先确认 / 不可得标未确证不得记为通过）、依据行，以及必加载层、验证、基线三处引用与调度器识别特征、维护方与图书馆落点；『某次到底用了哪个版本』属运行时事实（引用方环境与提交记录），机械无法判定，交人/子 agent 复核"),
    ("评论不得删除：任何情况下不得删除 Issue/PR 的评论（含 NPC 生成的）",
     "specs/platform/cnb.adoc + specs/core/execution.adoc + specs/general/collab.adoc", "script/check_specs.py",
     "check_comment_preservation_guard",
     "check_comment_preservation_guard 钉住三处落点（平台层「评论不得删除（L1）」：禁令本体含 NPC 生成的评论、不可逆与留证落点的理由、编辑同效、更正而非抹掉的正当处置、四条判定标准、与临时产物清理和禁合并的边界；通用层「派发入口」的平台无关同口径条；必加载层「破坏性操作」写明本条**不是**『先确认即可执行』的一类）与调度器识别特征、README 目录说明同步；**重点拦『把禁令删掉』与『降级成先确认即可删』两种降级**；『某次是否真的删了评论』属运行时行为（平台评论列表），机械无法判定，交人/子 agent 复核"),
    ("脚本头部注释（文档头）先行：动手先把用途/用法/参数/环境变量/行为边界/关键约定与设计决策写进文档头（细节不随维护丢失）",
     "specs/general/script.adoc", "script/check_specs.py",
     "check_script_header_guard",
     "check_script_header_guard 钉住通用层「脚本头部注释（文档头）」的九条要点（文档头先行、脚本必须写文档头、条目含关键约定与设计决策、设计决策写成『决策 + 理由 + 边界』、取值写抽象描述或常量名而不写硬编码数值、决策留头部/文件级文档注释不落进方法体、超出块注释容量的内容移交独立文档并一行回指、篇幅不设上限、入口注释不复述逻辑层契约）、技术栈落点（`specs/stack/python.adoc` 用模块 docstring 承载且不另起块注释、bash/batch/powershell 各写明入口注释只写入口自己）、调度器识别特征与 README 同步、图书馆依据（adoption 登记为本站取舍并标未确证、sources 有 PEP 257/25010/29148/MADR 主题段与同义性差异）；『某份脚本的文档头是否真的先行、是否真的写了决策理由』属运行时/引用方行为（本仓库不可见），交人/子 agent 复核"),
    ("脚本文档的承载位置与协作粒度：脚本默认单打独斗、各脚本相互独立，文档随脚本落盘、不逐脚本另建独立文档（多行文档注释 → 多行块注释 → 普通注释）",
     "specs/general/script.adoc + specs/general/coding.adoc", "script/check_specs.py",
     "check_script_selfdoc_guard",
     "check_script_selfdoc_guard 钉住「脚本文档的承载位置与协作粒度（默认写进脚本自身）」的五处要点（脚本默认单打独斗且多脚本彼此独立、承载方式的**三级优先级**、默认写在脚本里不另建独立文档、唯一例外是内容超容量时的移交并给判定标准、大规模团队式协作是例外不是默认）、`specs/general/coding.adoc`「注释」的脚本例外条（缺则原文会被读成'脚本也要按类/方法那套、文档另建'）、技术栈落点（python 模块 docstring 且单文件脚本同样不另建文档；bash/batch/powershell 三个无机制栈各写明用多行块注释承载、批处理限 `rem`；powershell 用基于注释的帮助）、调度器识别特征与 README 同步；**本条只钉要点文本仍在**——『某个项目的脚本实际把文档写在哪、有没有为单个脚本另建文档』属引用方项目代码与本仓库不可见的执行行为，交人/子 agent 复核"),
    ("跨环境脚本：一份跨平台逻辑 + 各平台薄壳入口（逻辑不得写两遍、入口不得承载逻辑、参数与退出码原样传递、不拿裸 shell 当逻辑层）",
     "specs/general/script.adoc", "script/check_specs.py",
     "check_cross_platform_script_guard",
     "check_cross_platform_script_guard 钉住通用层「跨环境脚本（入口 + 跨平台逻辑 + 实现语言取舍）」的要点（逻辑只写一份放跨平台逻辑脚本；入口层不得承载逻辑并给可判定判据；参数与退出码原样转交/原样返回；不得在另一平台重写逻辑；入口按各自平台规范落盘；实现语言取舍的默认优先级与『不拿裸 shell 当逻辑层』；不假设逻辑脚本所处目录；**入口与逻辑脚本同处一目录、主名相同**；**入口语言按平台默认具备者选**（Windows `.bat`/`.cmd`、Linux/macOS `.sh`）；**调用方不加前后命令**（只给脚本名即可跑，必要参数除外）；入口不设前置步骤、不得为跑逻辑自加命令或给逻辑脚本塞参数）与技术栈三个脚本栈文件的引用承接与各栈落点/命名/入口语言要点、调度器识别特征、README 同步、图书馆同义性差异；『某项目的脚本是否真的这么分层』属引用方项目代码（本仓库不可见），交人/子 agent 复核"),
    ("Windows 批处理（`.bat`/`.cmd`）的专属规则有独立栈文件：行尾 CRLF、纯 ASCII 不写 BOM、块语句延迟展开、`exit /b %errorlevel%` 原样返回退出码、不混写 PowerShell 语法",
     "specs/stack/batch.adoc + AGENTS_COMMON.adoc", "script/check_specs.py",
     "check_cross_platform_script_guard",
     "check_cross_platform_script_guard 钉住批处理栈文件存在、承载 BATCH_STACK_KEYS 全部要点（编码/行尾、薄壳与 `exit /b %errorlevel%`、延迟展开、引号与 `%~1`、`@echo off`、未定义变量、不混写 PowerShell 语法）、指向通用层「跨环境脚本」节，以及 powershell.adoc 反向指向它（引用不复制）与调度器技术栈层登记；『某个项目的 .bat 是否真的这么写』属引用方项目代码（本仓库不可见），交人/子 agent 复核"),
    ("交付形态与报告落点：不得只冒一句过程性叙述、不得只交付不汇报", "prompts/_common.txt + PROMPTS.adoc", "script/check_specs.py",
     "check_delivery_guard", "check_delivery_guard 钉住 `delivery` 片段的报告落点（过程性叙述不得作为独立评论发出）+ **输出通道只有两条**（最终汇报 / 必须停下确认，且『除这两条之外的任何中间话一律不发』——只写例外形态不写默认动作时，执行者会自造第三条通道、判据回到执行者手里）与交付形态两态（有改动却未提交未推送 / 无改动却未说明）、两个提示词内的『交付即汇报』步骤（同含两条通道）、以及 PROMPTS.adoc 与 README.adoc 的登记同步；**本轮实测失效**：一轮 NPC 任务唯一对外的输出就是一句过程性叙述、既无汇报也无任何提交，旧版片段只写『有改动必须提交推送』、恰漏『无改动也是完成态』与『过程性叙述不得外发』；『某次是否真的只发了一句、是否真的漏了提交』属运行时行为（评论内容与推送记录），交人/子 agent 复核"),
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
