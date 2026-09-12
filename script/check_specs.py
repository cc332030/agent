#!/usr/bin/env python3
"""
检查本规范集合的"规范性"（确定性检查，不依赖 AI）。

检查项（每项对应一个 check_ 函数，逐条见各函数 docstring 的判定口径）：
  1. 引用存在性：所有 `.adoc` 中的 `specs/...` 引用（反引号按仓库根、`link:` 按相对
     当前文件）都必须指向真实文件，避免规范间交叉引用悬空。
  2. 链接格式：内部 `link:` 须用相对路径，禁止根绝对路径与越出仓库根的写法。
  3. 节名引用存在性：`link:x.adoc[]「节名」` 引用的节必须真实存在，防改名后静默悬空。
  4. 技术栈一致：AGENTS_COMMON.adoc 技术栈层登记与 specs/stack/ 实际文件双向一致。
  5. 调度器登记完整性：被引用的规范文件必须都在加载调度器中登记（登记集合 ⊇ 被引用
     集合），防"只建文件不登记"导致规则实际失效。
  6. 私有约定误导入：禁止把项目私有强约束（C/IC 前缀、@Bean c 前缀等）当作通用规范。
  7. 历史来源声明：禁止指向旧文件/旧命名/旧位置的历史来源注记（会让引用悬空）。
  8. INSTALL 模板：INSTALL.adoc 的入口模板代码块须逐字保留（含换行空行），且入口文件名规则
     须兼容 `AGENTS.md`、默认 `AGENTS.adoc`（含已存在 `AGENTS.md` 时就地融合、不重命名）。
  9. 文档注水兜底：只拦机械可判定、必然成立的形态（纯占位段、完全逐字重复段）；
     "是否有价值、是否长篇大论"属语义判断，交人 review，不设字符数阈值以免误伤。
 10. 规范要点防线：根目录 AGENTS.adoc 必须仍含"完整性校验含干净子 agent 复核"底线。
 11. 规范优先级防线：specs/core/execution.adoc 必须有 L1/L2/L3 分级与最高关注项、
     （P1 git mv / P2 完整性校验 / P3 内容不减少 / P4 读取与上下文纪律 / P5 不可逆操作
     先确认）仍存在，且各项各自保持级别与"不可降级"定性，防被删/静默降级。
 12. 规范准入防线：specs-project-maintainer/spec-lifecycle.adoc 必须仍在，且分类归属（公共/项目）、
     分层判定、准入判定、提案校验、**定级口径（四问 + 条款类型判定表 + 归属对象 +
     归类举证 + 级别变更与复盘）、**读法形态（执行侧只给'怎么走'、依据归决策侧）与
     重构后的有效性核对**仍存在，并在加载调度器登记、
     AGENTS.adoc 有落点（定级口径与重构顺序被删，条目级别会重新混乱、规范会重新膨胀）。
 13. 提示词主侧重与优先级防线：PROMPTS.adoc 登记表 + 各提示词代码块的 `primary` +
     公共片段 `priority-rules` 的 L1/L2/L3 必须一致存在，防侧重/方向被删或降级。
 14. 自检防线：specs/general/self-check.adoc 必须仍在，且执行前自检清单、适用范围与
     知识边界要点不得被删；specs/core/execution.adoc 须保留其必加载层落点。
 15. 来源防线：specs/general/source.adoc 必须仍在，且"引用指向当前真实存在的目标"
     "外部标准只写名称/编号""不得编造""宁可不引"要点不得被删。
 16. Java 测试类命名防线：AGENTS_COMMON.adoc 的 Java 技术栈登记与 specs/stack/java-testing.adoc
     必须同时含四类后缀判据（`Tests`/`BootTests`/`PerfTests`/`IT`），防四类命名契约的口径在
     某一侧被删或漂移（两侧只说其中一半，别的项目按哪份都学不全）。
 17. 换行符防线：specs/general/encoding.adoc 必须仍按解释器分流行尾——`LF` 基准、`.bat`/`.cmd`
     必须 `CRLF`，且保留检出归一（`core.autocrlf`）与 `.gitattributes` 落盘约定；脚本技术栈
     文件（bash/python/powershell）也须各自写明行尾要求，防"Windows 批处理被写成 LF"这类
     跨平台失效的规则被删或只剩一句"统一行尾符"。
 18. 本仓库 git mv 自查：暂存区不得出现"删除 + 新增（未识别为 rename）"的疑似
     delete+create 形态（P1 在本仓库自身侧的那一半抓手；引用方侧仍靠其自检）。
 19. 从属者与能力自评防线：子 agent/被引用方"入口驱动加载、不靠自报"与"执行环境
     能力自评（无机制按降级路径、不空自评）"两条要点不得被删（两者都是"定义写了
     却不会被执行"的高发盲点）。
 20. 常驻层体积上限：必加载层（AGENTS_COMMON.adoc + specs/core/）总字节数不得超过
     RESIDENT_BUDGET；项目自身入口 AGENTS.adoc 不得超过 PROJECT_ENTRY_BUDGET（它同为
     每次会话无条件加载的常驻物）；且加载调度器"涉及即加载"条目数不得超过
     DISPATCHER_ITEMS_MAX（三者都是"越写越多、每次会话都付上下文"的机械抓手；
     体量与层级的语义判断仍由人复核）。
 21. 规范验证防线：specs/general/testing.adoc「验证与运行契约」的「验证总纲」「规范验证」
     （验证三视角：①完整性 + ②有效性与认知质量 + ③接纳面；每视角的判定标准与标准出处、
     ②的判据/依据/形态/性能四维、③的逐维判据、三视角由同一个干净子 agent 一并回答与
     各自留证），且 specs-project-maintainer/priority.adoc 的 P2 须仍声明三视角并指向这两节、
     AGENTS.adoc 的完整性校验落点须同步——防"改完规范只跑机械校验就算验证过"、把标准
     出处删掉（验证退化成"把脚本跑绿"）或把三视角拆成多次子 agent 派发。
 22. 接纳面防线：specs/general/testing.adoc 须仍含「运行契约」（公共内容被**未知项目加载**
     时的可控性：影响面/成本/可控性三维）且仍在调度器登记；verify.adoc 须引用它——
     公共内容会被未知项目加载，加得越多越易忘掉这个初衷（引用方出现不可控或未知效果）。
 23. 验证效力防线：specs/general/testing.adoc 的「验证的效力等级」须仍在——验证对象按
     "有没有确定性判据"分两档：确定项走机械校验（按判据本体验证、结论可判对错），概念项
     只能启发式复核（结论只到"未发现问题"、须标未确证/悬置、**不得当作阻断交付的条件**），
     且 priority.adoc / AGENTS.adoc / execution.adoc 三处口径须同源。防"把复核结论当依据、
     把'找不到问题'当成交付前置条件"（复核查不出不等于没有，卡在无判据的事上只能靠反复
     复核假装推进）。
 24. 任务生命周期防线：specs/core/execution.adoc 的「任务生命周期与节点自查」须仍在且
     七节点**以表格行**存在、并含"哪些节点不设"的独立声明（代码类改动不设复盘、不做
     三视角与全局核对）；specs/general/testing.adoc 的「验证的适用边界」须仍在且判据/两类
     改动/不得互串/更严一侧/每次换干净上下文齐备；specs-project-maintainer/spec-lifecycle.adoc 的
     「一条规范何时该拆分」「拆分后的自洽核对」须仍在且三条硬条件齐备；AGENTS.adoc 须有
     本仓库落点并指向这两处——防"到哪个节点查什么"重新无人负责、防概念性验证外溢到
     不需要它的任务（改一行代码被要求三视角）、防拆分成为新的失控源。
 25. 清单逐项与文档-脚本一致性：①准入判定自称"I 问"须与实际条目数一致（清单被增删
     而声明未同步）；②任务生命周期七节点须逐行在表中（节点被删则该节点要求失效）；
     ③`AGENTS.adoc`/`README.adoc` 点名的 `check_*` 与脚本名须在 `script/` 真实存在
     （防"声称有防线而防线已改名/删除"）；④子 agent 复核的**硬超时**与留证**三态台账**
     须仍在（防"卡死无人负责"与"查不出/没做无法分辨"退化成口号）。
 26. 公开面文档自足：README.adoc（公开站点首页由其渲染）/ PROMPTS.adoc / INSTALL.adoc
     不得出现维护方自查层『specs-project-maintainer/』的路径——引用方按同样方式解析，
     指向该层即死链（该层不随公共内容分发）；要说明"本仓库另有一层只对维护方成立"
     用文字描述即可，不给可点开的私有路径。
 27. 图书馆防线：仓库根 `library/`（**本仓库私有、不随规范分发**）须存在，入口
     `library/README.adoc` 被项目规范入口 `AGENTS.adoc` 登记；入口主题登记与实际主题
     文件**双向一致**；外部标准的**逐字引文锚点**仍在（依据不得被压成名称）；馆内引用
     **按仓库根可解析**（悬空引用等于依据链断在这里）。
 28. 公共内容覆盖面：`PUBLIC.adoc`（公共内容入口索引，维护方内容）须存在且被
     `AGENTS.adoc` 登记；两个公开入口（`INSTALL.adoc`、`AGENTS_COMMON.adoc`）须都在
     清单里；清单以反引号点名的文件须真实存在——公共内容有多个公开入口（接入时读的
     安装文档、公共片段、随规范分发的工具），覆盖面无清单会让检查漏掉半个公共内容、
     并把"自足"要求误加到只对维护方成立的文件上。
 29. AsciiDoc 语法：有 asciidoctor 时对**本仓库维护范围内的全部 .adoc** 做一次编译验证
     （`collect_adoc_files`：仓库根全部 .adoc + `specs/`/`specs-project-maintainer/`/
     `library/` 递归），并带 `--failure-level=WARN` 使 WARNING（含 `include::` 目标缺失）
     也返回非 0——否则语法"通过"而内容实际缺块。`CHANGELOG.adoc` 属只追加的历史记录，
     纳入语法编译但豁免引用/节名/链接格式/历史来源四类检查。

范围：只校验本仓库自己维护的规范、模板与工具（`.adoc` 文本、CI 配置、脚本行为、以及
**本仓库自身侧**的 git 暂存区状态行——后者是最高关注项 P1 在本仓库侧那一半的抓手，
只读 `git diff --cached --diff-filter=AD` 的状态行、不读工作区文件内容、非 git 目录跳过），
**不对引用方项目做任何代码/工作区检查**——引用方只使用公共内容（入口见 `PUBLIC.adoc`：
`AGENTS_COMMON.adoc` + `specs/`、安装时读的 `INSTALL.adoc`、公共片段 `prompts/_common.txt`、
随规范分发的 `script/clean_tmp.py`），其内部操作在本仓库的校验中不可见。

用法：
  python3 script/check_specs.py             # 阶段级进度 + 错误清单（默认）
  python3 script/check_specs.py --verbose   # 追加逐文件进度（排查某文件时用）
  python3 script/check_specs.py --help

退出码：0 通过，1 存在不规范项。
"""

import argparse
import os
import posixpath
import re
import shutil
import sys
import subprocess

# 兼容 Windows GBK 等非 UTF-8 终端，统一按 UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

# 必加载层体积预算（字节）：AGENTS_COMMON.adoc + specs/core/ 的**上限**（不是目标）。
# 常驻层每次会话无条件加载，故须有机械天花板；当前约 47 KB，留约 17% 余量，超限即要求
# 先归位（判归属/层级）、再新增，见 specs-project-maintainer/spec-lifecycle.adoc「规范集合的自身重构」。
RESIDENT_BUDGET = 56000
# 项目自身入口 AGENTS.adoc 的体积上限（字节）：它**同为每次会话无条件加载的常驻物**
# （项目根入口，先于 AGENTS_COMMON.adoc 被读），故须与本仓库自己的必加载层一并设限。
# 它是项目自身规范、不是公共内容（引用方不使用），故单列一个上限、不与 RESIDENT_BUDGET 合并。
PROJECT_ENTRY_BUDGET = 24000
# 加载调度器「涉及即加载」条目数上限（通用层/技术栈层/项目类型层/平台层合计）。
# 条目过多会让"该加载哪些"难以判全；当前约 30，留余量到 40。
DISPATCHER_ITEMS_MAX = 40

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# AGENTS_COMMON.adoc 是通用规范入口，位于仓库根目录（引用方以仓库根为基准解析
# 其内部 specs/... 引用，故下文对其链接解析用 base_dir=""）。
GENERIC_FILE = os.path.join(REPO_ROOT, "AGENTS_COMMON.adoc")
SPECS_DIR = os.path.join(REPO_ROOT, "specs")
# 项目自身维护层目录：只对"维护规范集合（或同类共享资产）的项目"生效的规范——
# 元规范（分类准入/定级/自身重构）、规范优先级与最高关注项、读取范围与长会话治理、
# 执行前自检、验证。它们由规范集合入口登记、随集合分发给维护同类集合的项目加载，
# **不在普通引用方项目加载**；与面向任意项目的公共内容（`specs/`）分目录隔离，
# 避免被误当公共规则执行或在精简中被顺手删掉。
PROJECT_SPECS_DIR = os.path.join(REPO_ROOT, "specs-project-maintainer")
# 安装文档（非规范本体，但属本仓库维护范围，且其内代码块模板须逐字保留，一并纳入机械校验）
INSTALL_FILE = os.path.join(REPO_ROOT, "INSTALL.adoc")
# 分类与准入规范（公共内容）：回答"一条规则属公共规范还是项目规范、属哪一层、
# 该不该收、新增提案如何校验"——它是规范集合的准入口径，被删则后续新增失去判定
# 依据，故与最高关注项、提示词方向一样加机械防线（见 check_spec_admission_guard）。
ADMISSION_FILE = os.path.join(PROJECT_SPECS_DIR, "spec-lifecycle.adoc")
# 执行前自检规范（公共内容）：把"动手前的自检"从自觉要求变成可核对动作（指令是否
# 逐字落实、触发的规范是否已实际加载、规划是否落盘、读取是否最小必要、证据是否已核实）。
# 它是"规范加载了却没被执行"这一风险的兜底关口，被删则加载防线失去自检环节。
SELF_CHECK_FILE = os.path.join(SPECS_DIR, "general", "self-check.adoc")
# 依据与来源真实性规范（公共内容）：内部引用须指向当前真实存在的目标、外部标准只写
# 名称/编号且不得编造、数据须有来源。来源一旦不实会污染整条下游引用链，故加机械防线。
SOURCE_FILE = os.path.join(SPECS_DIR, "general", "source.adoc")
# Java 测试规范（技术栈层）：其「测试类命名」是**全项目统一的命名契约**（后缀与构建工具的
# 执行边界绑定：`PerfTests`/`IT` 不得混入常规 test 阶段）。该契约由两处共同承载——调度器的
# Java 技术栈登记（检测到 Java 项目即加载）与规范正文；任一处漏掉某类后缀，引用方按另一处
# 学习就会漏掉该类测试。故机械钉住两侧的四类后缀判据。
JAVA_TEST_FILE = os.path.join(SPECS_DIR, "stack", "java-testing.adoc")
# 四类测试后缀（全项目统一命名契约，不得自创变体）
JAVA_TEST_SUFFIXES = ("Tests", "BootTests", "PerfTests", "IT")
# 验证规范（通用层）：其「验证总纲」「规范验证」两节是**改完规范后的语义复核定式**——
# 验证三视角（①完整性 / ②有效性与认知质量 / ③接纳面）、每视角的判定标准与标准出处、
# ②的判据/依据/形态/性能四维、③的逐维判据，并定式化"三视角由同一个干净子 agent 一并
# 回答、结论分栏、各自留证"。被删则"改完规范只跑机械校验就算验证过"、"验证了什么/依据
# 哪个标准"无从枚举（验证退化成"把脚本跑绿"、规则慢慢脱离初衷）、或三视角被拆成多次
# 子 agent 派发（重复读取与重复计费）都会重新出现。另有「验证的效力等级」节区分
# **确定项**（机械校验、结论可判对错）与**概念项**（启发式复核、只到"未发现问题"、
# 不得阻断交付）——防止把复核结论当依据、把"找不到问题"变成交付的隐性前置条件。
VERIFY_FILE = os.path.join(PROJECT_SPECS_DIR, "verify.adoc")
# 上下文规范（通用层）：其「运行契约」节是**公共内容被未知项目加载时的可控性**定式——
# 公共内容（AGENTS_COMMON.adoc + specs/ + prompts/ + 随规范分发的工具）会被**未知项目**
# 加载，本仓库看不到对方的项目结构、既有项目规范、依赖与工具链。它回答"加得越多、优化
# 越多"时最易忘掉的初衷：影响面（不静默推翻引用方约定）、成本（体积/时延/依赖可控）、
# 可控性（不默认改对方工作区、不依赖本仓库私有物、不阻断）。被删则该维度在验证中无人
# 负责，引用方出现"不可控或未知效果"时无判据可依。
CONTEXT_FILE = os.path.join(PROJECT_SPECS_DIR, "context.adoc")
# 编码与语言无关规范（通用层）：其「换行符（行尾）」是**跨平台行尾的权威口径**——
# 基准 LF、Windows 批处理（`.bat`/`.cmd`）必须 CRLF、CRLF 由 `.gitattributes` 声明而非
# 人工手动调整。行尾错配属"跨平台直接执行失败"（LF-only 的批处理在 Windows 上不可用），
# 且最易在"统一换行符"的精简中被压成一句空话，故机械钉住其判据与配套文件。
ENCODING_FILE = os.path.join(SPECS_DIR, "general", "encoding.adoc")
# 须各自写明行尾要求的脚本技术栈文件（引用方按各自栈文件学习，漏一处即学不全）
LINE_ENDING_STACK_FILES = (
    os.path.join(SPECS_DIR, "stack", "bash.adoc"),
    os.path.join(SPECS_DIR, "stack", "python.adoc"),
    os.path.join(SPECS_DIR, "stack", "powershell.adoc"),
)

# 配置类不写逻辑（跨语言，落点 specs/general/coding.adoc「类设计」）：与各家 Java 规范
# 一致的硬性约定——承载配置的类只保持 POJO 的基本功能，逻辑下沉到工具类/服务。它由
# 通用层条文（跨语言）+ Java/Spring 识别特征（`@ConfigurationProperties`）+ 公开说明
# （README）三处共同承载；漏任一处，读者按另一处学习就会漏掉该条，故机械钉住三处判据。
# （依据：Spring Boot 官方文档 Externalized Configuration；Google Java Style Guide 3.4.2
# 对 POJO 的定义；阿里巴巴 Java 开发手册的 POJO 类约定。）
CODING_FILE = os.path.join(SPECS_DIR, "general", "coding.adoc")
JAVA_STACK_FILE = os.path.join(SPECS_DIR, "stack", "java.adoc")
SPRING_STACK_FILE = os.path.join(SPECS_DIR, "stack", "spring.adoc")
# 必加载层执行原则（`specs/core/execution.adoc`）：其「任务生命周期与节点自查」是**任务
# 从提出到收尾各节点各查什么**的集中清单——任务节点此前散落各规范、没有统一清单，于是
# 出现"做完了才发现方向理解错"或"流程走完了但没人回头看规则是否有问题"。被删则
# "到哪个节点查什么"重新无人负责；同时它必须写明哪些节点**不设**（否则概念性验证会外溢
# 成所有任务的流程）。
EXECUTION_FILE = os.path.join(SPECS_DIR, "core", "execution.adoc")
# 本仓库自身规范入口（根目录 AGENTS.adoc，非通用规范，但属本仓库维护范围）
PROJECT_FILE = os.path.join(REPO_ROOT, "AGENTS.adoc")

# 公共任务提示词（非规范本体，但属本仓库维护范围）：登记入口、正文目录与公共片段。
# 提示词侧重点错即方向错（后续操作全做错），故对「主侧重 + 优先级」加机械防线，
# 防止调整/去重时把方向性内容删掉或降级；语义是否被削弱仍由人/子 agent 复核承担。
# 公共内容说明文档（介绍公共内容的范围与形态）：README.adoc。
README_FILE = os.path.join(REPO_ROOT, "README.adoc")
PROMPTS_FILE = os.path.join(REPO_ROOT, "PROMPTS.adoc")
PROMPTS_DIR = os.path.join(REPO_ROOT, "prompts")
COMMON_PROMPT_FILE = os.path.join(PROMPTS_DIR, "_common.txt")

# 图书馆（仓库根 `library/`，**本仓库私有内容、不随规范分发**）：规范条目与项目决策
# 背后的依据落点——外部标准原文摘录、"标准确实支持该条"的映射、当初的失效与实证。
# 它**不在公共内容里**（`specs/**` 会整个分发给未知项目，而图书馆天然含只对本项目
# 成立的内容：当初的失效、取舍、实证、选型理由），故落在仓库根、与 `prompts/` 同性质；
# 详见 AGENTS.adoc「依据图书馆」与 check_library_guard。
LIBRARY_DIR = os.path.join(REPO_ROOT, "library")
LIBRARY_INDEX = os.path.join(LIBRARY_DIR, "README.adoc")
# 入口必须登记的主题文件（"登记集合须与实际文件双向一致"只要靠这个常量即可成立：
# 实际多出未登记文件 → 报错；本常量里的文件缺失 → 也报错）
LIBRARY_TOPICS = ("sources.adoc",)
# 公共内容入口索引（维护方内容）：公共内容有多个公开入口（安装文档、通用规范入口 +
# specs/、公共片段、随规范分发的工具），只认单一口径会让检查漏掉半个公共内容。
# 本文件是那份清单，也是 check_public_content_coverage 的核对对象。
PUBLIC_FILE = os.path.join(REPO_ROOT, "PUBLIC.adoc")

# 误导入的私有约定特征（中性化后应消除）。
# 注意：只针对"被当作强制规范"的强约束表述，中性示例（如 `CList.of(...)` 作为
# 项目自有库举例、CStrUtils 等）允许保留，不在此列。
FORBIDDEN_PATTERNS = [
    (r"\bC[A-Z]\w*\b\s+(class|接口)", "疑似 C 前缀类名/接口误导入"),
    (r"\bIC[A-Z]\w*\b", "疑似 IC 前缀接口误导入"),
    (r"@Bean\s+\w*c\w*", "疑似 @Bean c 前缀私有约定误导入"),
]

# 『不保留无用的历史来源声明』的机械抓手：拦截文档里描述"之前是什么、后来改成什么"
# 的变更来源/历史来源陈述（如"早期版本…""原位于…迁移至此…""真正的 agents.md"等）。
# 这类陈述指向旧命名/旧位置，会让引用悬空、且属无用的历史包袱，故一律不得保留。
# 注意：只针对明确的"来源/变更"陈述句式，不得用单个通用词（如"重命名""早期"）
# 以免误伤 git 规范中"重命名必须用 git mv"等中性合理表述。
HISTORICAL_NOTE_PATTERNS = [
    (r"真正的 agents\.md", "指向旧 agents.md 命名的历史来源注记"),
    (r"(?:早期版本|之前的版本|原先)", "疑似'早期版本…'历史来源声明"),
    (r"原位于[^，。]*迁移至此", "疑似'原位于…迁移至此'变更来源声明"),
    (r"从通用规范中移除", "疑似规范迁移来源声明"),
    (r"原通用规范内的引用", "疑似旧规范引用迁移来源声明"),
]

errors = []


VERBOSE = False


def log(msg: str) -> None:
    """阶段级进度日志（始终输出）。立即 flush：既要给人看，也可能被 CI 与测试实时捕获。

    不打时间戳：本脚本是纯本地毫秒级校验，时间戳只会淹没真正重要的进度与结论
    （在单元测试输出中尤其明显），对排查没帮助。
    """
    print(msg, flush=True)


def detail(msg: str) -> None:
    """逐文件级进度日志（默认**不输出**，`--verbose` 时输出）。

    默认静默：全量检查会对每个文件逐条打印（26 个文件 × 多项检查），在 CI 日志与
    单元测试输出里数百行噪音会盖住真正有用的信息（进度小结与错误清单）。
    """
    if VERBOSE:
        print(msg, flush=True)


def phase(name: str) -> None:
    """标记一个检查阶段的开始。"""
    log(f"▶ {name}...")


def phase_done() -> None:
    """标记当前阶段结束。"""
    log("  ✓ 完成")


def err(msg: str, path: str = "", line: int = 0) -> None:
    loc = path
    if line:
        loc = f"{path}:{line}"
    errors.append(f"[不规范] {loc}: {msg}")


def collect_adoc_files():
    """收集纳入检查的 .adoc 文件。

    口径：**本仓库维护范围内的全部 .adoc** = `specs/` 下全部规范文件（含
    `specs-project-maintainer/`）+ 仓库根的全部 .adoc（通用规范入口
    `AGENTS_COMMON.adoc`、项目自身规范 `AGENTS.adoc`、安装文档 `INSTALL.adoc`、
    公共内容入口索引 `PUBLIC.adoc`、说明文档 `README.adoc`/`PROMPTS.adoc`、
    变更记录 `CHANGELOG.adoc`）+ 图书馆 `library/` 下的全部 .adoc + 任务提示词
    `prompts/` 下的全部 .adoc（会被复制给未知项目执行，见 `PUBLIC.adoc`）——即
    "随规范集合维护的全部文档"，**不止 specs/ 一个目录**。
    （下文各检查的 docstring 一律以本口径为准。）

    为什么必须收全：本集合是**语法编译、引用存在性、节名引用、链接格式**等检查的
    覆盖范围，漏收一个目录即该目录下全部文档脱离这些口径（悬空引用/悬空节名/错格式
    链接都无人发现）。历史缺陷正是如此：`library/**` 与根 `PUBLIC.adoc`/`README.adoc`/
    `PROMPTS.adoc` 曾同时不在本集合内，三口径对它们整体失效（实测 `library/README.adoc`
    就有 3 处悬空节名无人拦）；`prompts/**` 同样漏收过——而它是要复制给未知项目执行的
    产物，其自身的死链/悬空引用会随分发一起流出。故此处以"仓库根全部 .adoc + 各目录
    递归"一次收全，新增目录/新文件自动纳入，不再靠逐项登记（漏登记即漏检查）。
    """
    result = []
    # 目录一律**由 REPO_ROOT 现场推导**（不直接引用可能被重定向的模块常量）：
    # 各检查/单测会把 REPO_ROOT 指向临时根，现场推导才能保证"只收本仓库内的文件"，
    # 不会把真实仓库的目录（如真实 library/）漏收进来。
    root_dir = os.path.abspath(REPO_ROOT)
    for sub in ("specs", "specs-project-maintainer", "library", "prompts"):
        d = os.path.join(root_dir, sub)
        for dirpath, _, files in os.walk(d):
            for f in files:
                if f.endswith(".adoc"):
                    result.append(os.path.join(dirpath, f))
    # 仓库根：全部 .adoc（含 AGENTS.adoc / INSTALL.adoc / PUBLIC.adoc / README.adoc /
    # PROMPTS.adoc / CHANGELOG.adoc / AGENTS_COMMON.adoc；library/、prompts/ 已由上面收，不重复）
    if os.path.isdir(root_dir):
        for f in sorted(os.listdir(root_dir)):
            if f.endswith(".adoc"):
                result.append(os.path.join(root_dir, f))
    # 统一归一化为**仓库根相对 POSIX 路径**（如 `library/README.adoc`、`specs/…`）：
    # 这是全仓库通用的规范写法，也让"某文件在不在检查集合里"可被直接核验。
    return [os.path.relpath(f, root_dir).replace("\\", "/") for f in result]


def _rel_of(path: str) -> str:
    """把任意（绝对或仓库根相对的）文件路径归一化为**仓库根相对 POSIX 路径**。

    检查集合里的元素一律是仓库根相对形式（见 collect_adoc_files），而常量
    （GENERIC_FILE、PROMPTS_FILE 等）是绝对路径；两处混用时先经本函数归一化，
    再比较/打开，避免绝对/相对两种写法互相认不出。
    """
    if os.path.isabs(path):
        return os.path.relpath(path, REPO_ROOT).replace("\\", "/")
    return path.replace("\\", "/")


# **历史记录文件**：`CHANGELOG.adoc` 是**只追加的变更历史**，按定义会保留旧路径、旧文件名
# 与"原位于…迁移至…"这类历史陈述（见 specs/general/changelog.adoc）。故它虽有语法形态、
# 须纳入语法编译（防模板/换行被破坏），但**引用存在性、节名引用、链接格式、历史来源声明**
# 四类检查对它一律不适用——历史条目里的旧路径"查不到"是记录本身，不是悬空/违规。
HISTORICAL_FILES = ("CHANGELOG.adoc",)


def _is_historical(rel: str) -> bool:
    """该仓库根相对路径是否属"历史记录文件"（不参与引用/节名/历史来源检查）。"""
    return rel in HISTORICAL_FILES


def check_asciidoctor_syntax():
    """若环境有 asciidoctor，做一次语法编译验证。

    用 shutil.which 跨平台检测（Windows `where` / Linux `command -v` 通用），
    避免因命令不存在而误判为"跳过"。CI 中应在运行本脚本前安装 asciidoctor，
    使语法验证真正执行。

    **必须带 `--failure-level=WARN`**：asciidoctor 默认对 WARNING/ERROR **仍返回 0**
    （只把问题打到 stderr），故只看 `returncode != 0` 会漏报这类问题——最典型的是
    `include::` 目标缺失、`image::` 找不到：它们只发 WARNING，语法"通过"但内容实际
    缺块。加此开关后 WARNING 及以上即返回非 0，防线才真正生效（判据：asciidoctor 的
    `--failure-level`，取值域 INFO/WARN/ERROR/FATAL，默认 FATAL=不因告警失败）。
    老版本 asciidoctor 不支持该开关（会以非 0 退出并打印 unknown option）时，**降级
    为显式告警**而不是静默通过——降级路径本身要被看见。
    """
    phase("AsciiDoc 语法编译验证")
    if shutil.which("asciidoctor") is None:
        log("  提示: 未检测到 asciidoctor，跳过语法编译验证"
            "（CI 中请先在运行本脚本前安装，见 workflow）。")
        return
    # 固定口径：WARNING 及以上即视为失败（含 include 目标缺失、image 找不到）
    failure_level = "--failure-level=WARN"
    files = collect_adoc_files()
    unsupported = False   # 一旦确认本机 asciidoctor 不认 --failure-level，后续一律降级
    for i, rel in enumerate(files, 1):
        path = os.path.join(REPO_ROOT, *rel.split("/"))
        detail(f"  [{i}/{len(files)}] 检查 {rel}")
        base_cmd = ["asciidoctor", "-o", "-", "-a", "outfilesuffix=.html", path]
        cmd = base_cmd if unsupported else [base_cmd[0], failure_level] + base_cmd[1:]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            err(f"asciidoctor 超时 (30s)，文件可能过大或 asciidoctor 卡死: {rel}")
            continue
        # 老版本 asciidoctor 不认 --failure-level：显式降级（只告警一次），不静默通过
        if not unsupported and r.returncode != 0 \
                and "unrecognized option" in (r.stderr or ""):
            unsupported = True
            log("  警告: 本机 asciidoctor 不支持 --failure-level，"
                "WARNING 级问题（含 include 目标缺失）本次无法拦截；"
                "请升级 asciidoctor（>= 1.5.7）")
            try:
                r = subprocess.run(base_cmd, capture_output=True, text=True, timeout=30)
            except subprocess.TimeoutExpired:
                err(f"asciidoctor 超时 (30s)，文件可能过大或 asciidoctor 卡死: {rel}")
                continue
        if r.returncode != 0:
            err(f"asciidoctor 语法/告警: {r.stderr.strip()}", rel)
    phase_done()


def _is_dir_ref(ref: str) -> bool:
    """判断一个引用是否为**目录型引用**（以 `/` 结尾，如 `specs/`、`script/`）。

    目录型引用**不再整体跳过**——它有确定的判据（该目录是否存在），跳过会让
    "目录被改名/删除后引用悬空"完全无人发现（原实现把目录型与占位符混为一类跳过，
    等于把"可能误报"换成了"必然漏报"）。存在性由 check_refs_exist / check_library_guard
    按 os.path.isdir 核对。
    """
    return ref.endswith("/")


def _is_placeholder_ref(ref: str) -> bool:
    """判断一个引用是否为**占位符/示例**（非真实具体文件，无法核对存在性）。

    只含真正的占位形态：`...` 省略、`**` 整目录通配（如 `specs/**`）、`<...>` 尖括号
    占位。**目录型引用（`specs/`）不在此列**——见 _is_dir_ref（它有确定的判据）。
    """
    return (ref.endswith("...")
            or ref.endswith("**")          # 整目录通配（如 `specs/**`），非具体文件
            or "<" in ref or ">" in ref)


def _ref_base(f: str) -> str:
    """某规范文件内 `link:` 引用的解析基准（相对仓库根目录，根文件为空串）。

    **基准口径与渲染者一致（单一说明，不留第二套说法）**：本仓库的 `.adoc` 由站点
    `index.html` 用 **Asciidoctor.js（浏览器端现渲染）** 渲染，其 `link:` 目标按
    **文档源所在目录**解析。站点渲染的文档在**仓库根**，故 `link:` 相对仓库根解析——
    即 `link:INSTALL.adoc[]` 在站点上解析为 `/INSTALL.adoc`（仓库根的 `INSTALL.adoc`）。
    本函数对**仓库根文件**返回空串（基准=仓库根）正是为与之一致。

    为何"根文件约定按仓库根书写"：AsciiDoc 的 `link:` 没有"仓库根"概念，只有"文档
    所在目录"；对位于仓库根的文件两者恰好等价（`../` 会越出仓库根、无法表达"根级
    相对"），故根级跨文件引用统一按仓库根基准书写。**其余文件**（`specs/`、`library/`
    等）按其所在目录解析（与 IDE/浏览器相对语义一致）；图书馆内的引用由
    `_lib_resolve` 按"仓库根优先、再本文件目录"解析，与本节同为**仓库根基准**。

    记录性风险（已随本节说明消解）：若有人把此处的基准“修正”成"一律按本文件目录"，
    会去把 `README.adoc` 里的根级 `link:` 改成 `../` 形态——那反而把**站点上的链接**
    弄死（站点渲染的文档就在仓库根，`../` 会越出站点根）。故改动基准前须先改渲染者。
    """
    if os.path.isabs(f):
        rel = _rel_of(f)  # 绝对路径 → 仓库根相对
    elif os.path.dirname(f) == "":
        rel = f  # 已是仓库根相对形式（collect_adoc_files 的返回值）
    else:
        # 既非绝对、也非仓库根相对：按"相对 REPO_ROOT"解释（调用方偶有这种写法）
        rel = _rel_of(os.path.join(REPO_ROOT, f))
    d = os.path.dirname(rel)
    if d in ("", "."):
        return ""  # 仓库根文件：引用按从仓库根开始的路径解析
    return d.replace("\\", "/")


def extract_specs_refs(text: str, base_dir: str = ""):
    """提取文中所有指向仓库内具体文件的引用，归一化为从仓库根开始的相对路径。

    `base_dir` 为当前文件所在目录（相对仓库根，POSIX 分隔，根文件为空串），用于
    解析 link: 的相对目标。兼容两类写法：

      * 反引号包裹：`` `specs/general/coding.adoc` `` / `` `specs-project-maintainer/priority.adoc` ``
        ——按**从仓库根开始**的相对路径解析（AGENTS_COMMON.adoc 加载调度 / 正文里惯例用这种写法）。
      * AsciiDoc 超链接：`link:xxx[]`——按**相对当前文件所在目录**解析（IDE 与
        浏览器相对语义一致），目标可能是 `../general/x.adoc` 等含 `../` 的形式。

    排除：占位符、外部 scheme 链接、页内锚点、根绝对路径及越出仓库根的相对路径。
    **目录型引用（以 `/` 结尾）保留**（不是"排除"）：它由调用方按 os.path.isdir 核对
    存在性——原实现把目录型一并跳过，导致 `link:../script/[]` 这类目录被改名后无人发现。
    """
    refs = []
    # 反引号：根目录相对（含目录型 `specs/`、`script/`；占位形态除外）
    for r in re.findall(r"`((?:specs(?:-project)?|library|script|prompts)/[^`\s]*)`", text):
        if _is_placeholder_ref(r):
            continue
        refs.append(r)
    # link:：相对当前文件目录
    for raw in re.findall(r"\blink:([^\[]+)\[", text):
        t = raw.strip()
        if not t or t.startswith("#"):
            continue
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", t):  # 外部 scheme 链接
            continue
        if t.startswith("/"):  # 根绝对路径，格式检查单独报告，此处不参与存在性
            continue
        is_dir = t.endswith("/")
        resolved = posixpath.normpath(posixpath.join(base_dir, t))
        if resolved == ".." or resolved.startswith("../"):
            continue  # 越出仓库根，格式检查单独报告
        if _is_placeholder_ref(resolved):
            continue
        if is_dir and not resolved.endswith("/"):
            resolved += "/"  # 保留目录型标记，供调用方按目录核对
        refs.append(resolved)
    # 去重并保持顺序
    seen, out = set(), []
    for r in refs:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def check_refs_exist():
    """校验所有 spec 文件（含 AGENTS_COMMON.adoc）中的 `specs/...` 引用真实存在。

    覆盖两类引用：
      * AGENTS_COMMON.adoc 加载调度器登记/引用的文件；
      * 各 spec 文件之间互相引用的文件（此前只查 AGENTS_COMMON.adoc，
        会漏掉 spec 间交叉引用悬空，如 java-testing.adoc 引用已不存在的
        specs/stack/testing.adoc）。
    """
    phase("引用文件存在性检查")
    files = collect_adoc_files()
    for i, rel in enumerate(files, 1):
        base = _ref_base(rel)
        detail(f"  [{i}/{len(files)}] 检查 {rel}")
        if _is_historical(rel):
            continue  # 变更历史按定义保留旧路径，存在性检查对它不适用
        with open(os.path.join(REPO_ROOT, *rel.split("/")), encoding="utf-8") as fh:
            text = fh.read()
        refs = extract_specs_refs(text, base)
        for ref in refs:
            # 维护方自查层（specs-project-maintainer/）不随公共内容分发给普通引用方项目：
            # 其中指向 `specs/` 的引用在引用方可能不存在（引用方并未引入这些文件），
            # 属设计预期而非悬空；故只校验其指向本层自身的引用（见 check_dispatcher_registry
            # 的登记口径）。这些文件**在本仓库内**的引用仍由 check_link_refs /
            # check_section_refs 逐条核对。
            if rel.startswith("specs-project-maintainer" + os.sep) \
                    and not ref.startswith("specs-project-maintainer/"):
                continue
            # 图书馆（仓库根 library/，本仓库私有）引用公共内容/维护方落点属正常，
            # 反向引用（公共内容引用图书馆）已由 check_public_content_is_self_contained
            # 拦下；故图书馆自身的非 library 引用不在此重复报错。
            if rel.startswith("library" + os.sep) \
                    and not ref.startswith("library/"):
                continue
            if _is_dir_ref(ref):
                # 目录型引用：核对**目录**是否存在（不再整体跳过——目录被改名/删除
                # 同样是引用悬空，且原实现正因跳过而对它完全无覆盖）
                d = os.path.join(REPO_ROOT, *ref.rstrip("/").split("/"))
                if not os.path.isdir(d):
                    err(f"引用了不存在的目录: {ref}", rel)
                continue
            target = os.path.join(REPO_ROOT, *ref.split("/"))
            if not os.path.isfile(target):
                err(f"引用了不存在的文件: {ref}", rel)
            else:
                # 检查被引用文件是否真的存在且可读
                try:
                    open(target, encoding="utf-8").close()
                except Exception as e:  # noqa
                    err(f"文件无法读取: {ref} ({e})", rel)
    phase_done()


def check_stack_consistency():
    """AGENTS_COMMON.adoc 技术栈层登记 vs specs/stack/ 实际文件，双向一致。"""
    phase("技术栈一致性检查")
    with open(GENERIC_FILE, encoding="utf-8") as fh:
        text = fh.read()
    # 提取登记的技术栈文件：specs/stack/xxx.adoc（AGENTS_COMMON.adoc 内部 specs/... 从仓库根解析，base_dir=""）
    registered = set(extract_specs_refs(text, ""))
    registered_stack = {r for r in registered
                        if r.startswith("specs/stack/") and not r.endswith("/")}

    actual = set()
    stack_dir = os.path.join(SPECS_DIR, "stack")
    if os.path.isdir(stack_dir):
        for f in os.listdir(stack_dir):
            if f.endswith(".adoc"):
                actual.add(f"specs/stack/{f}")

    log(f"  已登记: {len(registered_stack)} 个, 实际存在: {len(actual)} 个")

    # 登记了但不存在（已被上一项覆盖，这里再明确提示栈语义）
    for r in registered_stack - actual:
        err(f"技术栈层登记了不存在的栈文件: {r}", "AGENTS_COMMON.adoc")
    # 实际存在但未登记（防止漏加载）
    for a in actual - registered_stack:
        err(f"specs/stack/ 存在但未在技术栈层登记（可能漏加载）: {a}", "AGENTS_COMMON.adoc")
    phase_done()


def check_dispatcher_registry():
    """调度器登记完整性：被引用的规范文件必须都在调度器中登记。

    背景：AGENTS_COMMON.adoc 的加载调度器是规范文件的**唯一登记处**。若某规范
    文件被其他规范引用、却未在调度器登记，按调度器执行时它永远不会被加载，
    其中规则实际失效（如 doc-module.adoc 曾被 doc.adoc / doc-design.adoc /
    doc-lifecycle.adoc 引用但未登记）。本检查用机械方式钉住
    「调度器登记集合 ⊇ 被引用集合」，使『写文件』与『登记调度器』成为同一动作。
    """
    phase("调度器登记完整性检查")
    with open(GENERIC_FILE, encoding="utf-8") as fh:
        registered = set(extract_specs_refs(fh.read(), ""))
    referenced = set()
    for rel in collect_adoc_files():
        # 只统计**公共规范内容**（`AGENTS_COMMON.adoc` + `specs/`）内部文件的引用：
        # 调度器是公共规范内容的登记处。维护方私有落点（`specs-project-maintainer/`、
        # 根 `library/`、`PUBLIC.adoc`、根 `README.adoc`/`PROMPTS.adoc`/`CHANGELOG.adoc`、
        # `prompts/`）**不在公共内容里、也不由公共调度器登记**（各由 `AGENTS.adoc` 登记），
        # 把它们的引用算进来即为误报。
        if rel != "AGENTS_COMMON.adoc" and not rel.startswith("specs/"):
            continue
        base = _ref_base(rel)
        with open(os.path.join(REPO_ROOT, *rel.split("/")), encoding="utf-8") as fh:
            referenced |= set(extract_specs_refs(fh.read(), base))
    # 只核对**公共规范内容**（`specs/`）的目标：非 `specs/` 的引用（根文档、`prompts/`、
    # `library/` 等）不由公共调度器登记，报"未登记"即为误报。`specs-project-maintainer/`
    # 虽在 `specs-project/…` 命名空间之外，但其 §登记由 AGENTS.adoc 单独承担，此处一并排除。
    non_public = ("specs-project-maintainer/", "library/")
    missing = sorted(r for r in referenced - registered
                     if r.startswith("specs/")
                     and not r.endswith("/")   # 目录型引用不是"待登记文件"
                     and not r.startswith(non_public))
    log(f"  调度器登记 {len(registered)} 个, 被引用 {len(referenced)} 个")
    for m in missing:
        err(f"规范文件被引用但未在加载调度器登记（不会被加载、其中规则实际失效）: {m}",
            "AGENTS_COMMON.adoc")
    phase_done()


def check_forbidden_patterns():
    """检查是否误导入私有强约束约定。"""
    phase("私有约定误导入检查")
    files = collect_adoc_files()
    checked = 0
    total_lines = 0
    for i, rel in enumerate(files, 1):
        # AGENTS_COMMON.adoc 作为加载器允许出现中性示例路径，跳过其私有约定命中
        with open(os.path.join(REPO_ROOT, *rel.split("/")), encoding="utf-8") as fh:
            lines = fh.readlines()
        total_lines += len(lines)
        found_in_file = False
        for j, line in enumerate(lines, 1):
            for pat, desc in FORBIDDEN_PATTERNS:
                if re.search(pat, line):
                    if not found_in_file:
                        detail(f"  [{i}/{len(files)}] 检查 {rel}")
                        found_in_file = True
                    err(f"{desc}", rel, j)
        checked += 1
    log(f"  扫描 {checked} 个文件, 共 {total_lines} 行")
    phase_done()


def check_historical_notes():
    """检查『不保留无用的历史来源声明』是否被遵守（机械抓手）。

    规范要求：不得添加指向旧文件/旧命名/旧位置的历史来源注记（旧文件可能已无法
    追溯、会让引用悬空），引用一律直接指向当前有效的地址。本检查扫描所有规范文件，
    拦截描述"之前是什么、后来改成什么"的变更来源/历史来源陈述（早期版本、原位于…
    迁移至此、真正的 agents.md 等），使该条规范真正有可执行抓手、而非仅靠自觉。
    """
    phase("历史来源声明检查")
    files = collect_adoc_files()
    checked = 0
    for i, rel in enumerate(files, 1):
        if _is_historical(rel):
            continue  # 变更历史本身就是历史陈述，本检查对它不适用
        found_in_file = False
        with open(os.path.join(REPO_ROOT, *rel.split("/")), encoding="utf-8") as fh:
            for j, line in enumerate(fh.readlines(), 1):
                for pat, desc in HISTORICAL_NOTE_PATTERNS:
                    if re.search(pat, line):
                        if not found_in_file:
                            detail(f"  [{i}/{len(files)}] 检查 {rel}")
                            found_in_file = True
                        err(f"{desc}（『不保留无用的历史来源声明』），应删除或改为直接指向当前有效表述", rel, j)
        checked += 1
    log(f"  扫描 {checked} 个文件")
    phase_done()


def check_install_codeblock():
    """校验 INSTALL.adoc 的入口模板代码块逐字保留 + 入口文件名规则与 `AGENTS.md` 兼容。

    背景一（模板逐字）：AI 读取 INSTALL.adoc 在目标项目创建入口文档时，若模板代码块内的
    换行/空行被折叠、行被合并，会导致生成文档样式改变。为让『逐字原样保留』成为
    可执行约束而非靠自觉，本检查扫描 INSTALL.adoc 的模板代码块，逐一确认每段必备
    行都各自独立成行（未被合并/折叠），且必备行之间的空行分隔完好。

    背景二（兼容 `AGENTS.md`）：平台与生态对 agent 规范文档的**默认命名是 `AGENTS.md`**
    （CodeBuddy、Cursor 等平台的固有约定），只认 `AGENTS.adoc` 会让安装规则在既有
    `AGENTS.md` 的项目上落不了地（重命名会打断平台识别、删旧建新会丢内容），而安装文档
    的体积上限又不允许把兼容说明写成大段（见本文件检查项 22）。故把"默认 `AGENTS.adoc`、
    已存在 `AGENTS.md` 时就地融合且不重命名、不另建"钉成机械可核对的判据，防止这条兼容
    规则在后续维护中被删掉或只说"兼容"却无做法。
    """
    phase("INSTALL 入口模板代码块检查")
    if not os.path.isfile(INSTALL_FILE):
        log("  未找到 INSTALL.adoc，跳过")
        phase_done()
        return
    with open(INSTALL_FILE, encoding="utf-8") as fh:
        lines = fh.readlines()

    # 定位模板代码块定界（首个 ``----`` 为开，其后下一个 ``----`` 为闭）
    delim = [i for i, l in enumerate(lines) if l.strip() == "----"]
    if len(delim) < 2:
        err("INSTALL.adoc 未找到完整的模板代码块定界符 `----`（需一对）",
            os.path.relpath(INSTALL_FILE, REPO_ROOT))
        phase_done()
        return
    open_i, close_i = delim[0], delim[1]
    body = lines[open_i + 1:close_i]

    # 必备内容：每行必须各自独立成行（不得与其它行合并/折叠）。
    REQUIRED_LINES = [
        "= Agent 规范入口",
        "本项目的 agent 执行规范入口为：",
        "https://agent.c332030.com/AGENTS_COMMON.adoc",
        "读取该入口及其引用的 specs/ 规范，并持续遵守其全部要求。",
        "规范属强制约束：**开工前必须先读取规范再执行**，不得因未读取/记不全而跳过或放宽任何条款。",
    ]
    found = {s: False for s in REQUIRED_LINES}
    for raw in body:
        line = raw.rstrip("\n").rstrip("\r")
        if line in found:
            found[line] = True
    for s, ok in found.items():
        if not ok:
            err(f"INSTALL.adoc 模板代码块缺失或行被合并/改写：未找到独立成行的『{s}』"
                "（模板须逐字原样保留，不得折叠换行）",
                os.path.relpath(INSTALL_FILE, REPO_ROOT))

    # 入口文件名规则：默认 AGENTS.adoc，且兼容已存在的 AGENTS.md（就地融合、不重命名/不另建）
    with open(INSTALL_FILE, encoding="utf-8") as fh:
        install_text = fh.read()
    for key, desc in (
            ("AGENTS.adoc", "默认入口文件名"),
            ("AGENTS.md", "平台默认命名须被兼容（已存在时就地融合）"),
            ("不重命名", "已存在 AGENTS.md 时不得重命名/迁移成 AGENTS.adoc（会打断平台识别）"),
            ("不另建", "已存在 AGENTS.md 时不得再另建一个 AGENTS.adoc（双入口会分叉）")):
        if key not in install_text:
            err(f"INSTALL.adoc 入口文件名规则被破坏：缺失『{key}』（{desc}）——"
                "只认单一扩展名会让安装规则在已有其他命名的项目上落不了地",
                os.path.relpath(INSTALL_FILE, REPO_ROOT))

    # 必备行之间须有恰当的空行分隔，确保样式不变（防止空行被吞掉导致段落粘连）
    indices = [i for i, raw in enumerate(body) if raw.rstrip("\n\r") in found]
    for a, b in zip(indices, indices[1:]):
        gap = b - a
        # 『入口为：』与 URL 之间、URL 与『读取…』之间需空行，其余相邻段落之间同样应留空行
        if gap < 2:
            prev = body[a].rstrip("\n\r")
            nxt = body[b].rstrip("\n\r")
            err(f"INSTALL.adoc 模板代码块中『{prev}』与『{nxt}』之间缺少空行"
                "（空行被吞会导致样式变化，须逐字保留）",
                os.path.relpath(INSTALL_FILE, REPO_ROOT))
    phase_done()


def check_link_refs():
    """校验内部文档链接 link: 的格式：须用相对路径，禁止根绝对、禁止越出仓库根。

    背景：AsciiDoc 的 link: 目标既在 IDE 里解析、也在浏览器/站点里解析。若写成
    根绝对路径 `link:/specs/...`，站点按仓库根解析看似正确，但 IDE 会把 `/` 当
    文件系统盘符根解析，导致 IDE 无法跳转；只有写相对当前文件所在目录的相对路径
    （如 `link:../general/x.adoc`）才能让 IDE 与浏览器按同一相对语义一致跳转。
    """
    phase("文档链接格式检查")
    files = collect_adoc_files()
    for i, rel in enumerate(files, 1):
        if _is_historical(rel):
            continue  # 变更历史按定义保留旧路径与旧写法，链接格式检查对它不适用
        base = _ref_base(rel)
        found_in_file = False
        with open(os.path.join(REPO_ROOT, *rel.split("/")), encoding="utf-8") as fh:
            for j, line in enumerate(fh.readlines(), 1):
                for m in re.finditer(r"\blink:([^\[]+)\[", line):
                    target = m.group(1).strip()
                    # 外部链接（带 scheme）与页内锚点（#...）除外
                    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", target) or target.startswith("#"):
                        continue
                    if not found_in_file:
                        detail(f"  [{i}/{len(files)}] 检查 {rel}")
                        found_in_file = True
                    if target.startswith("/"):
                        err("内部链接禁止用根绝对路径（link:/specs/... 在 IDE 中会按文件系统根解析、无法跳转），"
                            f"应改为相对路径（如 link:../specs/...[]），实际为 link:{target}[", rel, j)
                        continue
                    resolved = posixpath.normpath(posixpath.join(base, target))
                    if resolved == ".." or resolved.startswith("../") or os.path.isabs(resolved):
                        err(f"链接目标越出仓库根: link:{target}[", rel, j)
    phase_done()


def _collect_section_names(path: str):
    """收集一个 .adoc 文件的所有节标题文本（去掉 `=` 前缀）。

    AsciiDoc 节标题形如 `== 设计文档`、`=== 信息归属（同一信息只写一处）`。
    返回节标题正文集合，并收录别名以便引用方按习惯省略括号说明：
      * 完整标题；
      * 去掉括号后缀的简化名（`信息归属（同一信息只写一处）` → `信息归属`）；
      * 括号内的文字（`分类与懒加载（加载调度器）` → `加载调度器`）。
    `----` 代码块内的行不采集（如 INSTALL.adoc 模板首行 `= Agent 规范入口` 并非节）。
    """
    names = set()
    in_block = False
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip() == "----":
                in_block = not in_block
                continue
            if in_block:
                continue
            m = re.match(r"^(=+)\s+(.+?)\s*$", line)
            if not m:
                continue
            title = m.group(2)
            names.add(title)
            simple = re.sub(r"[（(].*$", "", title).strip()
            if simple:
                names.add(simple)
            for inner in re.findall(r"[（(]([^（）()]+)[）)]", title):
                if inner.strip():
                    names.add(inner.strip())
    return names


def check_section_refs():
    """校验『{文件}「节名」』式引用指向的节真实存在（机械抓手）。

    背景：规范间常以 `link:xxx.adoc[]「某节名」` 形式引用具体小节。文件存在性由
    check_refs_exist 覆盖，但**节名是否真实存在不会被任何检查发现**——某节被改名
    后，其余文件的引用会静默悬空（check_specs.py 原先的检查死角）。本检查按
    `link:<目标>[]「<节名>」` 的写法，解析目标文件、核对节名真实存在，让『节名引用
    不悬空』成为可执行约束，规范改名/重整时自动兜住。

    同一 link 后并列多个「节名」（如 `link:x.adoc[]「A」「B」`）时**逐个校验**。
    仅校验能在仓库内解析、且目标为 .adoc 的引用；占位符/目录/外部链接跳过。
    """
    phase("节名引用存在性检查")
    files = collect_adoc_files()
    checked = 0
    intra_checked = 0
    for i, rel in enumerate(files, 1):
        if _is_historical(rel):
            continue  # 变更历史按定义保留旧节名引用，节名检查对它不适用
        base = _ref_base(rel)
        found_in_file = False
        own_names = _collect_section_names(os.path.join(REPO_ROOT, *rel.split("/")))
        with open(os.path.join(REPO_ROOT, *rel.split("/")), encoding="utf-8") as fh:
            for j, line in enumerate(fh.readlines(), 1):
                # 匹配 `link:目标[]` 及其后连续出现的「节名」（同一行内，可并列多个）
                for m in re.finditer(r"\blink:([^\[]+)\[\]((?:\s*「[^」]+」)+)", line):
                    target = m.group(1).strip()
                    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", target) or target.startswith(("#", "/")):
                        continue
                    if not target.endswith(".adoc") or _is_placeholder_ref(target):
                        continue
                    resolved = posixpath.normpath(posixpath.join(base, target))
                    if resolved == ".." or resolved.startswith("../"):
                        continue
                    path = os.path.join(REPO_ROOT, *resolved.split("/"))
                    if not os.path.isfile(path):
                        continue  # 文件不存在由 check_refs_exist 报告
                    names = _collect_section_names(path)
                    for sec in re.findall(r"「([^」]+)」", m.group(2)):
                        section = sec.strip()
                        if not found_in_file:
                            detail(f"  [{i}/{len(files)}] 检查 {rel}")
                            found_in_file = True
                        checked += 1
                        simple = re.sub(r"[（(].*$", "", section).strip()
                        if section not in names and simple not in names:
                            err(f"引用了不存在的节名: {resolved}「{section}」"
                                f"（该节可能已改名/删除，须同步更新引用）", rel, j)
                # 补充：『同文件「节名」』式自然语言指向——写"同文件"即声明该节在
                # 本文件内，若本文件无此节则指向悬空（check_section_refs 原先只认
                # `link:x.adoc[]「节」` 写法，拦不住这类指向；曾出现实测悬空引用）。
                for m2 in re.finditer(r"同文件「([^」]+)」", line):
                    section = m2.group(1).strip()
                    simple = re.sub(r"[（(].*$", "", section).strip()
                    intra_checked += 1
                    if section not in own_names and simple not in own_names:
                        err(f"「同文件「{section}」」指向的节在本文件不存在"
                            f"（该节可能在其他文件，须改写成 link:<文件>[]「{section}」"
                            "或就地补节）", rel, j)
    log(f"  校验 {checked} 处节名引用（含 {intra_checked} 处同文件指向）")
    phase_done()


# 『文档不得注水』的机械可判定形态（保守口径，只拦"必然成立"的形态，避免误伤
# 简短但有实质内容的条目——语义判断不在机械检查范围，由人 review 承担）。
# 占位词：整段除它之外没有任何实质内容时，才算"无实质内容的占位段"。
# 判定刻意**不含字符数阈值**——"参考：""内容为：" 这类短引导句是正常文档写法，
# 按字数判注水必然误伤；短不等于水，篇幅问题属语义判断、交人 review。
FILLER_PLACEHOLDER_WORDS = ("此处", "本段", "待补", "待完善", "待补充", "后续补充",
                            "内容同上", "详见上文", "TODO", "略")
FILLER_DUP_MIN_CHARS = 12       # 判重段落的实质字符下限（只滤掉"重复标点/符号行"，短而真实的重复条目仍应报）
FILLER_MIN_SUBSTANCE_CHARS = 4  # 段落"实质字符"下限：低于此值视为格式分隔行（如 `：`、`——`），不判注水
# 承载实质内容的行结构：列表条目、表格行、链接、块属性、注释行
MEANINGFUL_LINE_PAT = re.compile(r"^\s*(?:\*|\d+\.|\||\[|<|link:|include::)")
# 判"是否只剩占位词"时需忽略的标点与格式符
FILLER_NOISE_PAT = re.compile(r"[\s*`\-—、。，,：:；;（）()\[\]\"\'“”~…]")


def _iter_blocks(path: str):
    """按 AsciiDoc 块结构切分正文，逐块产出 (起始行号, 行列表, 是否含承载行)。

    代码块（`----` 定界）内容、节标题与块属性行不计入段落；空行分段。列表/表格等
    结构行归入所在段，并标记该段是否"含承载实质内容的行"——只有**整段都没有承载行**
    时才可能是注水段（避免把正常规则条目误判为注水）。
    """
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()
    in_block = False
    para, start, meaningful = [], 0, False
    for i, raw in enumerate(lines, 1):
        line = raw.rstrip("\n").rstrip("\r")
        if line.strip() == "----":
            in_block = not in_block
            continue
        if in_block:
            continue
        stripped = line.strip()
        if not stripped:
            if para:
                yield start, para, meaningful
                para, start, meaningful = [], 0, False
            continue
        if re.match(r"^=+\s+", stripped) or stripped.startswith(":") or stripped.startswith("["):
            if para:
                yield start, para, meaningful
                para, start, meaningful = [], 0, False
            continue
        if not para:
            start = i
        para.append(line)
        if MEANINGFUL_LINE_PAT.match(line):
            meaningful = True
    if para:
        yield start, para, meaningful


def _para_metrics(para: list) -> tuple:
    """统计段落：去格式符后的实质字符数、条目数、是否含列表标记。"""
    texts, items, has_bullet = set(), 0, False
    for line in para:
        s = line.strip()
        if re.match(r"^\s*(?:[*]|\d+\.)\s+", line):
            has_bullet = True
            items += 1
        norm = FILLER_NOISE_PAT.sub("", s)
        if norm:
            texts.add(norm)
    return len("".join(sorted(texts))), items, has_bullet


def _placeholder_only(text: str) -> bool:
    """整段是否"只剩占位词、没有别的实质内容"。

    去掉占位词与标点、格式符后若不再剩任何字符，即判为占位段（如"此处待补充""（略）"）；
    只要还留有别的字词（"参考：""内容为：""第 3 步：略"）就不算——短引导句与
    "标题词 + 后接内容"都是正常文档写法，机械检查不得误伤。按词长从长到短去除，
    避免先去掉短词（"待补"）导致长词（"待补充"）只被去掉前缀、残留无关字符。
    """
    rest = text
    for word in sorted(FILLER_PLACEHOLDER_WORDS, key=len, reverse=True):
        rest = rest.replace(word, "")
    return FILLER_NOISE_PAT.sub("", rest) == ""


def _substance_chars(text: str) -> int:
    """段落的"实质字符"数（去掉标点/格式符后剩下的字数）。

    用于滤掉纯格式行（如 `：`、`——`、`***`）——它们既非占位也非内容，
    判注水属误报，故低于下限时不参与占位段/重复段判定。
    """
    return len(FILLER_NOISE_PAT.sub("", text))


def check_filler_docs():
    """『文档不得注水』机械兜底（只拦机械可判定、必然成立的形态）。

    背景：规范要求"禁止无意义、划水、凑字数"，若只停留在文档里的要求、无任何抓手，
    则属"定义未执行"。本检查保守地钉住两类必然成立、且不误伤正常内容的形态：
      1) 纯占位段：整段除占位词外无任何实质内容（"此处待补充"这类占位）；
      2) 同段重复：同一文件内出现**完全逐字相同且承载实质内容**的段落（凑数堆砌）。
    "内容是否有价值、是否长篇大论、是否流水账"属语义判断，不作机械判定——交人
    review 承担；机械检查只盯"必然成立"的形态，避免把简短但真实的条目判成注水。
    """
    phase("文档注水检查")
    files = collect_adoc_files()
    for i, rel in enumerate(files, 1):
        detail(f"  [{i}/{len(files)}] 检查 {rel}")
        seen_paras = set()
        for lineno, para, meaningful in _iter_blocks(os.path.join(REPO_ROOT, *rel.split("/"))):
            text = " ".join(p.strip() for p in para).strip()
            # 0) 纯格式行（`：`、`——`、`***` 等）：无实质字符，不判注水（防误报）
            if _substance_chars(text) < FILLER_MIN_SUBSTANCE_CHARS:
                continue
            # 1) 纯占位段：整段无承载行，且除占位词外没有实质内容
            if not meaningful and _placeholder_only(text):
                err(f"疑似注水：无实质内容的占位段『{text[:30]}』"
                    "（『文档不得注水』），补上可核对的实质内容或删除", rel, lineno)
                continue
            # 2) 同段重复：逐字相同且承载实质内容的段落（凑数堆砌）——**对全部段落判重**，
            #    不只判"含列表/表格行"的段落：否则同段重复出现在节标题分隔的两处时会被漏掉
            if _substance_chars(text) >= FILLER_DUP_MIN_CHARS:
                if text in seen_paras:
                    err(f"疑似注水：与上文完全重复的段落『{text[:30]}』"
                        "（『文档不得注水』），合并去重", rel, lineno)
                    continue
                seen_paras.add(text)
    phase_done()


def check_principle_guard():
    """校验规范"要点防线"仍在（防『定义完整性校验却不执行/被意外误删』）。

    作为逐层防线：一旦根目录 AGENTS.adoc「规范调整」里"调整后须做完整性校验、且含干净
    子 agent 复核、不得只定义不执行"这条底线被删除或改写，check_specs.py 即可通过
    低耗机械校验发现，从而用测试用例钉住这类"难在定稿时发现"的坑。

    判定：根目录 AGENTS.adoc 必须同时含有『子 agent』与『完整性』两个关键词，否则视为
    完整性校验机制被破坏。
    """
    phase("规范要点防线检查")
    path = os.path.join(REPO_ROOT, "AGENTS.adoc")
    rel = os.path.relpath(path, REPO_ROOT).replace("\\", "/")
    if not os.path.isfile(path):
        err("缺少 Agent 项目自身规范入口 AGENTS.adoc，无法核验『调整后须做完整性校验』要点防线是否存在", rel)
        return
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    for key in ("子 agent", "完整性"):
        if key not in text:
            err(f"规范要点防线被破坏：{rel} 缺失『{key}』——『调整规范后必须真正执行完整性校验』这条底线可能被删除/改写", rel)
    phase_done()


def check_priority_guard():
    """『规范优先级防线』：最高关注项、分级定义与落点必须仍在、且级别未被改动。

    背景：规范按业界做法（RFC 2119 / ISO shall-should-may / 关键性分级）分 **L1 强制 /
    L2 建议 / L3 允许** 三级，并单列"最高关注项"（不可降级）。最大的风险是**重构/去重时
    把最高关注项删掉或降级**——这正是本仓库发生过的问题（同一最高关注项在多处出现被
    AI 判为"重复"而合并）。本检查机械钉住：

      * **公共侧**（`specs/core/execution.adoc`）：分级定义（L1/L2/L3）与最高关注项
        （含"一处完整定义 + 其余一行引用"的保留形态、"强调用升级别+引用"的做法）仍在；
      * **维护方侧**（`specs-project-maintainer/priority.adoc`）：P1-P5 清单仍在，且各自
        保持原级别（P1/P2/P3/P5 条款本身为 L1、P4 条款本身为 L2 且同列最高关注项）、
        『依据』行仍在；
      * `specs/core/execution.adoc` 仍保留 `git mv` 铁律、读取范围、破坏性操作与来源
        真实性的落点。

    只钉"存在性与级别"，不改写内容——语义是否被削弱仍由人/子 agent 复核承担。
    """
    phase("规范优先级防线检查")
    rel_exec = "specs/core/execution.adoc"
    exec_path = os.path.join(REPO_ROOT, *rel_exec.split("/"))
    if not os.path.isfile(exec_path):
        err(f"缺少 {rel_exec}——分级定义与最高关注项的公共落点丢失", rel_exec)
        phase_done()
        return
    with open(exec_path, encoding="utf-8") as fh:
        exec_text = fh.read()
    # 公共侧：分级定义与最高关注项（含保留形态）必须仍在
    for key, desc in (("L1 强制", "分级定义之一（违反即视为未完成、不可豁免）"),
                      ("L2 建议", "分级定义之一（有正当理由可偏离、须留痕）"),
                      ("L3 允许", "分级定义之一（可选做法）"),
                      ("最高关注项", "最高关注项的公共落点（不可降级、重构首保）"),
                      ("不可降级", "最高关注项只能加强不得削弱的声明"),
                      ("一行引用", "保留形态：一处完整定义 + 其余一行引用（防复制正文）"),
                      ("强调", "强调的正确做法（升级别 + 单一定义 + 显式引用）")):
        if key not in exec_text:
            err(f"规范优先级防线被破坏：{rel_exec} 缺失『{key}』（{desc}）——"
                "分级与最高关注项的公共口径不得被删或降级", rel_exec)
    # 最高关注项 P1/P5 的必加载层落点仍须保留
    if "git mv" not in exec_text:
        err(f"规范优先级防线被破坏：{rel_exec} 缺失 `git mv` 铁律——"
            "最高关注项 P1 的必加载层落点被删除/改写", rel_exec)
    if "破坏性操作" not in exec_text:
        err(f"规范优先级防线被破坏：{rel_exec} 缺失「破坏性操作」——"
            "最高关注项（不可逆操作先确认）的必加载层落点被删除/改写", rel_exec)
    if "不得顺口编造" not in exec_text:
        err(f"规范优先级防线被破坏：{rel_exec} 缺失来源真实性（不得编造事实与来源）——"
            "最高关注项的必加载层落点被删除/改写", rel_exec)
    if "范围控制" not in exec_text:
        err(f"规范优先级防线被破坏：{rel_exec} 缺失读取范围与长会话治理（「范围控制」）——"
            "最高关注项的必加载层落点被删除/改写", rel_exec)

    # 维护方侧：P1-P5 清单与级别
    rel_priority = "specs-project-maintainer/priority.adoc"
    path = os.path.join(REPO_ROOT, *rel_priority.split("/"))
    if not os.path.isfile(path):
        err(f"缺少维护方最高关注项清单 {rel_priority}——不可降级清单无处承载", rel_priority)
        phase_done()
        return
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    for pid, name, level in (("P1", "git mv", "L1，最高"), ("P2", "完整性", "L1，最高"),
                             ("P3", "内容不得减少", "L1，最高"),
                             ("P4", "读取与上下文纪律", "L2 建议"),
                             ("P5", "不可逆操作与来源真实性", "L1，最高")):
        if pid not in text:
            err(f"规范优先级防线被破坏：{rel_priority} 缺失最高关注项 {pid}（{name}）——"
                "最高关注项不得被删除或降级", rel_priority)
        else:
            m = re.search(rf"^===\s*{pid}\.", text, re.M)
            if m is None:
                err(f"规范优先级防线被破坏：{rel_priority} 未找到最高关注项 {pid}"
                    f"（{name}）的小标题『=== {pid}. 』——结构被改写会导致级别核对失效",
                    rel_priority)
                continue
            seg = text[m.start():].split("\n===")[0]
            if f"要求（{level}" not in seg:
                err(f"规范优先级防线被破坏：{rel_priority} 的最高关注项 {pid}（{name}）"
                    f"须标明『要求（{level}』——级别不得被静默改动"
                    "（P1/P2/P3/P5 为 L1 铁律，P4 条款本身为 L2 建议）", rel_priority)
            if "**依据**" not in seg:
                err(f"规范优先级防线被破坏：{rel_priority} 的最高关注项 {pid}（{name}）"
                    "缺失『**依据**』行——依据可压缩为标准名/编号，但不得整段删除"
                    "（检索不到依据，就无从判断它是『拍脑袋』还是『有出处』）", rel_priority)
        if "不可降级" not in text:
            err(f"规范优先级防线被破坏：{rel_priority} 缺失『不可降级』声明——"
                "最高关注项须明确只能加强、不得削弱", rel_priority)
    # 维护方层须由维护方的项目规范入口登记（否则不会被加载、其中规则实际失效）
    if not os.path.isfile(PROJECT_FILE):
        err("缺少 AGENTS.adoc——维护方自查层的登记入口丢失", "AGENTS.adoc")
    else:
        with open(PROJECT_FILE, encoding="utf-8") as fh:
            own = fh.read()
        for rel in ("specs-project-maintainer/priority.adoc",
                    "specs-project-maintainer/spec-lifecycle.adoc",
                    "specs-project-maintainer/verify.adoc",
                    "specs-project-maintainer/context.adoc"):
            if rel not in own:
                err(f"{rel} 未在维护方项目规范入口 AGENTS.adoc 登记"
                    "（不会被加载、其中规则实际失效）", "AGENTS.adoc")


def check_spec_admission_guard():
    """『规范准入防线』：分类/准入规范、其调度器登记与提案校验要点不得被删或降级。

    背景：规范集合的增删改须有完整口径——一条规则属公共规范还是项目规范、属哪一层、
    该不该收（准入判定）、**该定哪一级（定级四问与条款类型判定表）**、新增提案如何校验
    与升级，以及**规范集合自身如何重构瘦身（先判归属 → 再判层级 → 再判重复 → 压缩表述）**。
    该口径集中在 specs-project-maintainer/spec-lifecycle.adoc（维护方自查层，写规范时才加载），一旦被
    "精简/去重"顺手删掉，后续新增规范就失去判定依据、级别重新混乱、集合重新膨胀。
    故用机械方式钉住其**存在性与关键要点**，并确认它真的在加载调度器登记（登记才可能被
    加载）、在 `AGENTS.adoc` 留下维护落点。

    只钉"存在性与登记"，不改写内容——口径是否被实质削弱仍由人/子 agent 复核承担。
    """
    phase("规范准入防线检查")
    rel_admission = os.path.relpath(ADMISSION_FILE, REPO_ROOT).replace("\\", "/")
    if not os.path.isfile(ADMISSION_FILE):
        err(f"缺少规范分类与准入文件 {rel_admission}——"
            "新增/调整规范条目将失去分类、分层与准入判定的依据", rel_admission)
        phase_done()
        return
    with open(ADMISSION_FILE, encoding="utf-8") as fh:
        text = fh.read()
    # 要点须仍在：公共/项目归属判定、准入判定、提案校验（是否已有标准/已有条目/升级举一反三）
    for key, desc in (
            ("归属判定", "公共/项目归属判定（对谁成立 + 自足性判据）"),
            ("准入判定", "该不该收进规范集合的准入判定"),
            ("已有标准", "提案校验之「检查是否已有标准」"),
            ("已有本项目条目", "提案校验之「检查是否已有条目（不重复收）」"),
            ("举一反三", "提案校验之「升级与举一反三」"),
            ("规范集合的自身重构", "规范自身的瘦身与归位（重构顺序与删/移/留速查）"),
            ("同一条规则有两种读法", "执行侧只给『怎么走』、依据与取舍归思考/决策侧（读的形态判据）"),
            ("归属判定", "公共/项目归属判定（对谁成立 + 自足性判据）"),
            ("重构后须核对规范有效性", "重构不丢内容之外还须保证有效性（两形态分离/可执行性不降级/可见性不丢）")):
        if key not in text:
            err(f"规范准入防线被破坏：{rel_admission} 缺失『{key}』（{desc}）——"
                "准入与提案校验口径不得被删或降级", rel_admission)
    # 定级口径须以**节标题**存在（条目"该定哪一级"的判定依据；被删或降为正文一句，
    # 条目级别就再无判定依据、会重新回到"凭感觉/看关键词"，正是本仓库出现过的混乱来源）。
    for sec, desc in (("如何给一条规范定级", "定级口径四问"),
                      ("与条款类型一一对应", "条款类型与级别的判定表"),
                      ("归属谁", "分级与强制对象的正交判定"),
                      ("归类举证", "定级结论的对象/依据/类型/结论留痕"),
                      ("级别变更与复盘", "级别变更须说明理由 + 定期复盘六查")):
        if not re.search(rf"^==+\s*{re.escape(sec)}", text, re.M):
            err(f"规范准入防线被破坏：{rel_admission} 缺失节『{sec}』（{desc}）——"
                "定级口径被删后条目级别再无判定依据、级别会重新混乱", rel_admission)
    # 重构顺序（先判归属 → 再判层级 → 再判重复）不得被删或颠倒：顺序颠倒会把
    # "放错位置的内容"直接删掉（本该移走却被当冗余删除）。
    for key in ("先判归属", "再判层级", "再判重复"):
        if key not in text:
            err(f"规范准入防线被破坏：{rel_admission} 缺失重构顺序要点『{key}』——"
                "规范自身重构的判断顺序不得被删或改写", rel_admission)
    # 维护方层须由维护方项目规范入口登记（未登记则永不被加载、其中规则实际失效）
    with open(PROJECT_FILE, encoding="utf-8") as fh:
        if rel_admission not in fh.read():
            err(f"规范准入文件 {rel_admission} 未在 {os.path.relpath(PROJECT_FILE, REPO_ROOT)} "
                "登记（不会被加载、其中规则实际失效）",
                os.path.relpath(PROJECT_FILE, REPO_ROOT))
    phase_done()

def check_lifecycle_guard():
    """『任务生命周期防线』：节点自查、验证边界与拆分判据不得被删或降级。

    背景（三处"只在文本上成立、执行时不会真的发生"的机制缺口）：

      * **节点自查无清单**：任务从提出到收尾会经过若干节点（提出/理解/方案/执行/验证/
        交付/复盘），此前这些节点散落在各规范里、**没有统一清单**，于是"做完了才发现
        方向理解错"，或"流程走完了但没人回头看规则本身是否有问题"（规则因此慢慢脱离
        初衷）。节点与"到点该查什么"定式化在 `specs/core/execution.adoc`
        「任务生命周期与节点自查」。
      * **验证没有边界**：验证机制本身也是会被加载执行的规则——用错对象就是把不可控的
        验证义务强加给不需要它的任务。**代码类改动**只应按机械判据判过不过（能过就能过），
        **规范类改动**才做三视角与全局核对；无此边界就会两头落空（改一行代码要求三视角、
        改一条规范只跑机械校验）。判据定式化在公共 `specs/general/testing.adoc`「验证与运行契约」
        「验证的适用边界」。
      * **拆分无判据**：拆分会多出一个没人维护、判据空转的东西（比不拆更坏），
        故须有"何时该拆"的硬条件与"拆完是否自洽"的核对，定式化在
        `specs-project-maintainer/spec-lifecycle.adoc`「一条规范何时该拆分」「拆分后的自洽核对」。

    只钉"节与要点仍在、且各处口径指向一致"，判据是否被实质削弱仍由人/子 agent 复核承担。
    """
    phase("任务生命周期防线检查")
    rel_exec = os.path.relpath(EXECUTION_FILE, REPO_ROOT).replace("\\", "/")
    if not os.path.isfile(EXECUTION_FILE):
        err(f"缺少必加载层文件 {rel_exec}——任务节点的自查清单失去集中落点", rel_exec)
    else:
        with open(EXECUTION_FILE, encoding="utf-8") as fh:
            text = fh.read()
        if not re.search(r"^==+\s*任务生命周期与节点自查", text, re.M):
            err(f"任务生命周期防线被破坏：{rel_exec} 缺失「任务生命周期与节点自查」节——"
                "各节点该查什么必须可枚举，否则任务只能靠'做完才发现读错方向'", rel_exec)
        # 节点须以**表格行**形态存在（`| **节点**（L1）`）：只匹配关键词会被
        # "方案改/验证项"之类的改写蒙混过去——节点清单是本节的核心，必须行级钉住。
        for node, desc in (
                ("提出", "用户表述不清先澄清，不自行假设后开工"),
                ("理解", "规范是否已实际加载 + 最小必要信息集 + 主侧重"),
                ("方案", "规划落盘 + 去重删减前先核覆盖完整性"),
                ("执行", "加载由入口驱动 + 环境能力先自评 + 读取不越界"),
                ("验证", "按改动性质选范围 + 严格执行/尽力而为 + 全局核对"),
                ("交付", "交付形态按执行环境区分 + 落盘同步"),
                ("复盘", "三视角评有效性 + 核规则初衷 + 核是否该拆分")):
            if not re.search(rf"^\|\s*\*\*{node}\*\*", text, re.M):
                err(f"任务生命周期防线被破坏：{rel_exec} 缺失节点行『{node}』（{desc}）——"
                    "节点清单被删/改写后'到哪个节点查什么'重新无人负责", rel_exec)
        # 节点清单必须含"哪些节点不设"的**独立声明**（否则概念性验证会外溢到代码类任务）：
        # 只匹配"代码类改动"会被验证节点行里的同一措辞蒙混过去，须按声明行钉住。
        if not re.search(r"^\*\s*\*\*哪些节点不设", text, re.M) or "代码类改动" not in text:
            err(f"任务生命周期防线被破坏：{rel_exec} 未写明哪些节点**不设**（代码类改动"
                "不设复盘、不做三视角与全局验证）——概念性验证会外溢成所有任务的流程",
                rel_exec)
    # 验证边界：公共口径在 specs/general/testing.adoc「验证与运行契约」，须与节点清单同源
    rel_verify = os.path.join("specs", "general", "testing.adoc").replace(os.sep, "/")
    v_path = os.path.join(REPO_ROOT, *rel_verify.split("/"))
    if not os.path.isfile(v_path):
        err(f"缺少验证规范文件 {rel_verify}——验证的适用边界失去集中落点", rel_verify)
    else:
        with open(v_path, encoding="utf-8") as fh:
            vtext = fh.read()
        if not re.search(r"^==+\s*验证的适用边界", vtext, re.M):
            err(f"任务生命周期防线被破坏：{rel_verify} 缺失「验证的适用边界」节——"
                "不先判改动性质，验证范围就无处取值（规范类改动只跑机械校验、"
                "代码类改动被要求三视角），两头失效会重新出现", rel_verify)
        for key, desc in (
                ("效力等级", "验证结论须按对象标效力（确定项可判对错、概念项只到未发现）"),
                ("代码类改动", "A 类：按机械判据判过不过（能过就能过）"),
                ("规范类改动", "B 类：三视角深度验证 + 全局核对"),
                ("会不会被未知项目加载", "唯一判据：改动是否会被未知项目加载/改变别人行为"),
                ("先判改动性质", "先判性质、再选范围（不得因改动小就降级）"),
                ("不得互串", "过度验证与跳过验证都禁止"),
                ("取**更严的一侧**", "两类改动同批时取更严一侧，代码部分仍按机械判据")):
            if key not in vtext:
                err(f"任务生命周期防线被破坏：{rel_verify} 缺失『{key}』（{desc}）——"
                    "验证边界不得被删或降级", rel_verify)
        if "每次验证都换一个干净上下文" not in vtext:
            err(f"任务生命周期防线被破坏：{rel_verify} 未要求**每次验证换一个干净上下文**——"
                "复用发起改动/上一轮验证的上下文等于自己复核自己，会只找'是否已改'",
                rel_verify)
    # 拆分判据：拆是加载面的膨胀源，判据不得被删
    rel_adm = os.path.relpath(ADMISSION_FILE, REPO_ROOT).replace("\\", "/")
    if os.path.isfile(ADMISSION_FILE):
        with open(ADMISSION_FILE, encoding="utf-8") as fh:
            atext = fh.read()
        for sec, desc in (("一条规范何时该拆分", "拆分硬条件（默认不拆、三条同时成立）"),
                          ("拆分后的自洽核对", "拆完逐项核对（引用可达/无矛盾/不失完整性/登记同步）")):
            if not re.search(rf"^==+\s*{re.escape(sec)}", atext, re.M):
                err(f"任务生命周期防线被破坏：{rel_adm} 缺失节『{sec}』（{desc}）——"
                    "拆分若无判据，就会为'看起来更整齐'多出一个没人维护的东西", rel_adm)
        for key, desc in (
                ("判据与用处不同", "硬条件一：判据形态或加载时机不同（同类条目不得拆）"),
                ("不拆就真的坏", "硬条件二：须能指出实害，'更整齐'不构成理由"),
                ("拆后每一半都自足", "硬条件三：每半都有判据、落点、加载方式"),
                ("默认不拆", "取向：按需才拆，不为对称、不为好看而拆"),
                ("单独过准入九问", "拆分不豁免准入判定（有落点/成本可接受尤其）")):
            if key not in atext:
                err(f"任务生命周期防线被破坏：{rel_adm} 缺失『{key}』（{desc}）", rel_adm)
    # 三处口径同源：执行原则（节点清单）→ AGENTS.adoc（本仓库落点）→ verify.adoc（边界判据）
    if not os.path.isfile(PROJECT_FILE):
        err("缺少 AGENTS.adoc：任务生命周期的本仓库落点无处承载", "AGENTS.adoc")
        phase_done()
        return
    with open(PROJECT_FILE, encoding="utf-8") as fh:
        own = fh.read()
    for key, desc in (("验证的适用边界", "本仓库落点须指向公共边界节的判据"),
                      ("验证的效力等级", "本仓库落点须指向效力等级口径"),
                      ("一条规范何时该拆分", "本仓库落点须指向拆分判据"),
                      ("specs-project-maintainer/verify.adoc", "维护方的验证义务落点")):
        if key not in own:
            err(f"任务生命周期防线被破坏：AGENTS.adoc 缺失『{key}』（{desc}）——"
                "本仓库维护口径须与公共口径一致", "AGENTS.adoc")
    phase_done()


def check_line_ending_guard():
    """『换行符防线』：跨平台行尾规则（LF 基准 + Windows 批处理 CRLF）不得被删或弱化。

    背景：行尾错配是**跨平台直接失效**的一类问题——`.bat`/`.cmd` 被写成 LF 在 Windows 上
    会直接执行失败（`goto`/标签、`if`/`for` 复合语句、行尾注释与续行都可能失效），而
    "在 Unix 上编辑 Windows 批处理"又极常见，故这类规则最容易被"统一换行符、不用管平台"
    式的精简删成一句空话。故机械钉住 encoding.adoc 中的**分流判据**（LF 基准、`.bat`/`.cmd`
    必须 CRLF、`core.autocrlf`/`.gitattributes` 检出归一），并要求 bash/python/powershell
    三个脚本栈文件各自写明行尾要求（引用方按各自栈文件学习，漏一处即学不全）。

    只钉"判据存在"，不改写内容——行尾规则是否被实质削弱仍由人/子 agent 复核承担。
    """
    phase("换行符防线检查")
    rel = os.path.relpath(ENCODING_FILE, REPO_ROOT).replace("\\", "/")
    if not os.path.isfile(ENCODING_FILE):
        err(f"缺少编码与语言无关规范文件 {rel}——"
            "跨平台换行符（LF 基准与 Windows 批处理 CRLF）失去集中落点", rel)
    else:
        with open(ENCODING_FILE, encoding="utf-8") as fh:
            text = fh.read()
        for key, desc in (
                ("换行符", "行尾规则的权威小节"),
                ("以 LF 为基准", "仓库基准行尾（防被改成 CRLF 基准）"),
                (".bat", "Windows 批处理必须 CRLF 的对象"),
                ("CRLF", "Windows 批处理的行尾要求"),
                ("core.autocrlf", "检出归一化依据（不靠人工手动调整）"),
                (".gitattributes", "行尾策略的权威落盘口")):
            if key not in text:
                err(f"换行符防线被破坏：{rel} 缺失『{key}』（{desc}）——"
                    "跨平台行尾规则不得被删或弱化", rel)
    # 脚本技术栈文件各自须写明行尾要求（引用方按各自栈文件加载）
    for stack_file in LINE_ENDING_STACK_FILES:
        srel = os.path.relpath(stack_file, REPO_ROOT).replace("\\", "/")
        if not os.path.isfile(stack_file):
            err(f"缺少脚本技术栈文件 {srel}——其行尾要求无处承载", srel)
            continue
        with open(stack_file, encoding="utf-8") as fh:
            stext = fh.read()
        if "行尾" not in stext and "CRLF" not in stext:
            err(f"换行符防线被破坏：{srel} 未写明行尾要求——"
                "引用方按该栈文件学习时学不到行尾规则", srel)
    with open(GENERIC_FILE, encoding="utf-8") as fh:
        if rel not in set(extract_specs_refs(fh.read(), "")):
            err(f"编码与语言无关规范 {rel} 未在加载调度器登记（不会被加载、其中规则实际失效）",
                "AGENTS_COMMON.adoc")
    phase_done()


def check_java_test_naming():
    """『Java 测试类命名防线』：四类测试后缀的判据不得在任一处被删或漂移。

    背景：Java 测试类名为「被测类名 + 测试类型后缀」，后缀**与构建工具的执行边界绑定**——
    `Tests`/`BootTests` 纳入常规 `test` 阶段，`PerfTests`/`IT` 独立执行（`IT` 还须与 Maven
    Failsafe 的默认 includes 约定对齐）。命名契约由两处共同承载：调度器的 Java 技术栈登记
    （检测到 Java 项目即加载）与 `specs/stack/java-testing.adoc` 正文；任一处漏掉某类后缀，
    引用方按另一处学习就会漏掉该类测试（写不出、或写错后误跑/误跳过）。故机械钉住**两侧都
    含四类后缀判据**（含 `IT` 与 Maven Failsafe 的对齐依据），防"精简/去重"时口径漂移。

    只钉"四类后缀判据在两侧都存在"，后缀的语义与取舍是否被实质削弱仍由人/子 agent 复核承担。
    """
    phase("Java 测试类命名防线检查")
    rel = os.path.relpath(JAVA_TEST_FILE, REPO_ROOT).replace("\\", "/")
    if not os.path.isfile(JAVA_TEST_FILE):
        err(f"缺少 Java 测试规范文件 {rel}——"
            "测试类命名契约（Tests/BootTests/PerfTests/IT 四类后缀）失去落点", rel)
    else:
        with open(JAVA_TEST_FILE, encoding="utf-8") as fh:
            text = fh.read()
        for suffix in JAVA_TEST_SUFFIXES:
            if suffix not in text:
                err(f"Java 测试类命名防线被破坏：{rel} 缺失测试类型后缀『{suffix}』——"
                    "四类命名契约不得被删或降级", rel)
        for key, desc in (("测试类命名", "四类后缀的权威定义节"),
                          ("被测类名", "『被测类名 + 测试类型后缀』的命名口径"),
                          ("常规", "类别与执行阶段的绑定口径")):
            if key not in text:
                err(f"Java 测试类命名防线被破坏：{rel} 缺失『{key}』（{desc}）", rel)
    # 调度器的 Java 技术栈登记须与该契约一致（只说一半会让引用方学不全）
    with open(GENERIC_FILE, encoding="utf-8") as fh:
        generic = fh.read()
    java_line = next((ln for ln in generic.splitlines() if "stack/java-testing.adoc" in ln), "")
    if not java_line:
        err(f"Java 测试规范 {rel} 未在加载调度器登记（不会被加载、其中命名契约实际失效）",
            "AGENTS_COMMON.adoc")
    else:
        missing = [s for s in JAVA_TEST_SUFFIXES if f"`{s}`" not in java_line]
        if missing:
            err("Java 测试类命名防线被破坏：AGENTS_COMMON.adoc 的 Java 技术栈登记未写明"
                f"『{'/'.join(missing)}』后缀——调度器与该命名契约口径漂移"
                "（引用方照调度器学习会漏掉该类测试）", "AGENTS_COMMON.adoc")
    phase_done()


def check_git_mv_selfcheck():
    """『本仓库自身侧 git mv 自查』：把最高关注项 P1 从"口号"变成本仓库可机械核对的一项。

    背景：最高关注项 P1（文件移动/重命名必须 `git mv`）此前被登记为**无机械抓手**——
    因为铁律作用于**引用方项目的工作区**，本仓库看不到。但这只对"引用方"成立：
    **本仓库自己也有工作区**，其暂存内容可以核对。故在本仓库侧补上这一半：核对暂存区
    （`git diff --cached -M --name-status --diff-filter=AD`）是否同时出现删除与新增——
    那是 delete+create 误用的典型形态（历史会断链，且事后无法恢复）。

    实现边界（防止把校验扩到引用方，违反 `AGENTS.adoc`「校验范围」）：

      * 只查 **git 暂存区**（`git diff --cached`，不读工作区文件内容、不做逐文件比较）；
      * 无 git 仓库、无暂存内容、git 不可用 → 一律**跳过、不报错**（保持确定性与幂等）；
      * 发现疑似形态只提示并给出复核命令，**不自动改工作区**（修复由人工/agent 按 git
        规范执行，规范集合不代改引用方与自己的工作区）；
      * 真删真增（非移动）属合法改动，故本条给出的是"须复核"提示。

    **改写式移动（本仓库实证）**：把 `specs/library/` 搬到仓库根 `library/` 时，入口
    文件同时被整篇重写（去掉"分发给引用方/可关闭"口径、换登记处）——**内容相似度实测
    11%**（命令 `git diff --cached -M10% --summary` 输出 `rename ... (11%)`）、低于 git
    默认 50% 阈值，索引里就只剩"删除 + 新增"，看起来像违规的 delete+create，其实正是
    `git mv` 后正常改写。

    **阈值取值理由（说明它不是个案反推）**：`-M` 判据是 **"临时相似度索引"**——git 用
    一个近似算法（默认按 blob 大小建索引、对候选只做逐块指纹比对，故 2~3 行的短文
    **返回 0% 相似度属正常**，见 git 官方文档 `git-diff` 的 `--find-renames` 与
    `diff.renames`）；再叠加"移动后又被大幅改写"（**重写与移动常常同时发生**，本仓库即
    一例），默认阈值下**必然**漏检真移动。故所取阈值只需落在"真移动的下界"之下，不必
    精确：**真 delete+create 是"两个文件内容无关"，相似度接近 0；而 `git mv` + 改写
    实测仍有 11%**。取 10% 属保守取值（比实测低、给常见重写留余量），且本检查**只对
    "暂存区同时存在删除与新增"这一形态发声**——它是**提示须人工复核**（见下第 3 条），
    不是"判违规"，故阈值不是 P1 的效力边界：P1 的判定标准仍在规范文本（`git mv` 铁律
    + `git diff --cached -M --summary` 复核），本阈值只决定"要不要提醒人来看一眼"。
    """
    phase("本仓库 git mv 自查（P1 自身侧抓手）")
    if not os.path.isdir(os.path.join(REPO_ROOT, ".git")):
        phase_done()
        return
    try:
        out = subprocess.run(
            # -M10%：改写式移动（内容大幅重写）也能被识别为 rename，避免把合规的
            # `git mv` + 改写误判成 delete+create（默认阈值 50% 会漏掉这类）
            ["git", "diff", "--cached", "-M10%", "--name-status", "--diff-filter=AD"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        phase_done()
        return
    if out.returncode != 0:
        phase_done()
        return
    deleted, added = set(), set()
    for line in out.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0][0]
        if status == "D":
            deleted.add(parts[-1])
        elif status == "A":
            added.add(parts[-1])
    if deleted and added:
        err("暂存区同时存在删除与新增（未识别为 rename）——这些改动若是文件移动/重命名，"
            "须改用 `git mv`（最高关注项 P1：delete+create 会使历史永久断链）；"
            "若确为真删真增（非移动），用 `git diff --cached -M10% --summary` 复核后可忽略本提示",
            "git 暂存区")
    phase_done()


def check_budget_guard():
    """『常驻层体积上限』：必加载层体积与调度器条目数不得无声膨胀。

    背景：必加载层（`AGENTS_COMMON.adoc` + `specs/core/`）**每次会话无条件加载**，是
    最直接的"注意力预算"消耗者；规范自己写着"常驻层只放底线""篇幅越大越易挤爆上下文"，
    但此前**只有方向、没有机械抓手**——每次新增都"礼貌地"往常驻层加一点，几十次之后
    体量翻倍而无人发现（本仓库已发生过一次，靠人 review 才拦下）。故把预算写成机械上限：
    超限即报错，须"先归位、再新增"。

    上限不是目标、是**天花板**：只在明显膨胀时报警，正常增删不误伤（数值留有余量）。
    """
    phase("常驻层体积上限检查")
    total = 0
    for rel in ("AGENTS_COMMON.adoc", "specs/core/execution.adoc"):
        path = os.path.join(REPO_ROOT, *rel.split("/"))
        if not os.path.isfile(path):
            err(f"缺少必加载层文件 {rel}", rel)
            continue
        total += os.path.getsize(path)
    if total > RESIDENT_BUDGET:
        err(f"常驻层体积超限：必加载层（AGENTS_COMMON.adoc + specs/core/）共 {total} 字节，"
            f"超出上限 {RESIDENT_BUDGET} 字节——常驻层只放 L1 底线、最高关注项与其引用落点，"
            "方法论/依据论证/示例/元规范须移到通用层（用到才加载）；请先按 "
            "specs-project-maintainer/spec-lifecycle.adoc「规范集合的自身重构」判归属与层级，"
            "再决定该项是否真该常驻", "AGENTS_COMMON.adoc + specs/core/")
    # 项目自身入口 AGENTS.adoc 同为每次会话无条件加载的常驻物，单列上限（不并入
    # RESIDENT_BUDGET——它是项目自身规范、引用方不使用，口径不同）。
    entry_path = os.path.join(REPO_ROOT, "AGENTS.adoc")
    if os.path.isfile(entry_path):
        entry_size = os.path.getsize(entry_path)
        if entry_size > PROJECT_ENTRY_BUDGET:
            err(f"项目入口 AGENTS.adoc 体积超限：{entry_size} 字节，超出上限 "
                f"{PROJECT_ENTRY_BUDGET} 字节——它同为每次会话无条件加载的常驻物，"
                "只放本项目的加载说明与校验范围；方法论/依据论证/示例须移到 specs/ 用到才加载",
                "AGENTS.adoc")
    rel_common = "AGENTS_COMMON.adoc"
    with open(os.path.join(REPO_ROOT, rel_common), encoding="utf-8") as fh:
        text = fh.read()
    m = re.search(r"== 分类与懒加载（加载调度器）(.*?)== 规范文件登记完整性", text, re.S)
    if m is None:
        err(f"{rel_common} 未找到「分类与懒加载（加载调度器）」节——调度器结构被改写，"
            "条目数上限失去抓手", rel_common)
    else:
        count = m.group(1).count("\n  ** ")
        if count > DISPATCHER_ITEMS_MAX:
            err(f"加载调度器条目数超限：「涉及即加载」条目共 {count} 个，"
                f"超出上限 {DISPATCHER_ITEMS_MAX}——条目过多会让每次执行都难以判全"
                "『该加载哪些』；请先归并同类条目（一条覆盖一个主题族），再新增", rel_common)
    phase_done()


def check_delegation_guard():
    """『从属者与能力自评防线』：两类"定义了却不会被执行"的机制要点必须仍在。

    背景（AI 执行侧的两处盲点，均源自"规范只对直接执行者说话"的假设）：

      * **从属者盲区**：规范一直被"直接执行者"读取，但实际加载者常是**子 agent、
        被主 agent 派发的分步任务、由任务原文引用规范的引用方**——它们若以"我没被
        派发这份规范"为由跳过加载，规范整体形同不存在。故须有"加载由已加载入口驱动、
        不靠自报；上级已读不构成下级免责"的机制（`AGENTS_COMMON.adoc`）。
      * **无机制自欺**：自检与长会话治理大量依赖执行环境能力（能否清空上下文、能否
        派发子 agent），环境不提供时若无"先判能力、缺失走降级路径、不空自评"的机制，
        就会出现"照抄'已清洁上下文'/'已委派'"的假自检（`specs/general/self-check.adoc`）。
      * **执行者来源失控**："缺独立复核"时最容易抓来的是**外部来源的执行者**（外部 NPC、
        另一个产品）——它看不到本执行者已加载的规范，判据是否一致、耗时多久都不可核对
        （本项目实证：镜像不存在致派发即 error、另一次 1 h+ 未回传）。故须有"**子任务一律
        由与执行者相同的 Agent 承担（不得点名外部 Agent/NPC）；同 Agent 不可用时降级为
        执行者本人串行 + 如实标悬置，且优先一次性调用**"的机制（`specs/general/collab.adoc`，
        维护方侧落点 `specs-project-maintainer/verify.adoc`）。
    """
    phase("从属者与能力自评防线检查")
    for rel, key, desc in (
        ("AGENTS_COMMON.adoc", "从属者", "入口驱动加载（子 agent/被引用方不靠自报）"),
        ("specs/general/self-check.adoc", "环境能力自评", "无机制时按降级路径、不得空自评"),
    ):
        path = os.path.join(REPO_ROOT, *rel.split("/"))
        if not os.path.isfile(path):
            err(f"缺少文件 {rel}——{desc} 无处承载", rel)
            continue
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if key not in text:
            err(f"从属者与能力自评防线被破坏：{rel} 缺失『{key}』机制——{desc}；"
                "该类要点属'定义了却不会执行'的高发盲点，不得删除或并入他处而失去痕迹", rel)
    # 执行者来源选择：『**强制同 Agent**』的五处要点——(a) 子任务必须与执行者同 Agent、
    # (b) **不得点名外部 Agent/NPC**（含判定标准）、(c) 同 Agent 不可用时的降级路径（本
    # 地串行/标悬置、不换外部来源）、(d) 优先一次性调用、(e) 三视角与维护方落点同口径。
    # 此处只钉"要求文本仍在"——"本次是否真按同 Agent 派发、有没有点名外部 NPC"属运行时
    # 行为（评论/派发的实际内容），机械无法判定，交人/子 agent 复核；但"要求被抽掉"必须
    # 拦住（本项目已有两次外部 NPC 实证：派发即失败、1 h+ 未回传）。**每条要求须同时命中
    # 多处要素**，否则别处一句同名字样即可让检查假绿（与 check_checklist_guard 同口径）。
    for rel, keys, desc in (
        ("specs/general/collab.adoc", ("子任务必须由与执行者相同的 Agent 承担",
                                       "不得点名外部 Agent / 外部 NPC",
                                       "同一 Agent 身份"),
         "子任务一律同 Agent（同 Agent 身份 + 同入口/调度器），不得点名外部 Agent/NPC"),
        ("specs/general/collab.adoc", ("判定标准", "派发目标", "交换面", "回传面"),
         "『不得点名外部 NPC』须给出可核对的判定标准，否则只剩一句口号"),
        ("specs/general/collab.adoc", ("降级路径（L1）", "不换任何外部来源",
                                       "由执行者本人（主 agent）串行承担"),
         "同 Agent 不可用也不得换外部来源，须降级为执行者本人串行或如实标悬置"),
        ("specs/general/collab.adoc", ("优先一次性调用",),
         "派发优先一次性、边界明确、可超时，不交有自主探查权的执行者"),
        ("specs/general/testing.adoc", ("强制同 Agent", "不得点名外部 Agent"),
         "三视角复核口径须与协作规范同口径（强制同 Agent、不得点名外部 NPC）"),
        ("specs-project-maintainer/verify.adoc", ("子 Agent 强制与执行者同 Agent",),
         "维护方落点：强制同 Agent、外部复核者不作为备选"),
    ):
        path = os.path.join(REPO_ROOT, *rel.split("/"))
        if not os.path.isfile(path):
            err(f"缺少文件 {rel}——{desc} 无处承载", rel)
            continue
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        missing = [k for k in keys if k not in text]
        if missing:
            err(f"执行者来源选择防线被破坏：{rel} 缺失要点 {missing}——{desc}；"
                "该要点防的是'缺复核时随手抓一个不可核对的外部执行者'，"
                "不得删除或并入他处而失去痕迹", rel)
    phase_done()


def check_adoption_guard():
    """『接纳面防线』：公共内容被未知项目加载时的可控性（运行契约）不得被删。

    背景：本仓库最有价值的初衷是——**这套规范会被未知项目加载**。规范加得越多、优化
    越多，越容易只对着"本仓库自己"看，忘掉引用方看不到本仓库的脚本、结构与取舍，于是
    出现"引用方加载后产生不可控或未知效果"。故"运行契约"（影响面 / 成本 / 可控性三维）
    **随公共内容**落在 `specs/general/testing.adoc`「验证与运行契约」（引用方也需要它：
    项目自己维护规范/共享资产时同样要问"落到未知项目会怎样"）；维护方自己的清单落在
    `specs-project-maintainer/context.adoc`。被删则该维度在验证中重新无人负责。

    只钉"节与三维要点仍在、两处口径同源"，语义是否被削弱仍由人/子 agent 复核承担。
    """
    phase("接纳面防线检查（未知项目加载）")
    rel_pub = os.path.join("specs", "general", "testing.adoc").replace(os.sep, "/")
    pub_path = os.path.join(REPO_ROOT, *rel_pub.split("/"))
    if not os.path.isfile(pub_path):
        err(f"缺少验证与运行契约文件 {rel_pub}——公共内容被未知项目加载时的可控性"
            "（运行契约）失去集中落点", rel_pub)
    else:
        with open(pub_path, encoding="utf-8") as fh:
            text = fh.read()
        if not re.search(r"^==+\s*运行契约", text, re.M):
            err(f"接纳面防线被破坏：{rel_pub} 缺失「运行契约」节——"
                "公共内容被未知项目加载时的可控性不得无人负责", rel_pub)
        for key, desc in (
                ("① 影响面", "不静默推翻引用方既有约定、冲突次序写明"),
                ("② 成本", "加载体积/时延开销/依赖要求可控且可说清"),
                ("③ 可控性", "不默认改动引用方工作区、不依赖引用方看不到的私有物、不阻断正常路径"),
                ("降级路径", "引入的机制/依赖须有不可用时的降级路径"),
                ("不得让引用方依赖本仓库私有物", "条目不得引用引用方看不到的私有脚本名/结构"),
                ("ISO 9241-110", "标准出处：可控、可预期、不阻断"),
                ("接纳面须留证", "新增/调整公共内容时逐维留证，未核对不得计入验证通过")):
            if key not in text:
                err(f"接纳面防线被破坏：{rel_pub} 缺失『{key}』（{desc}）——"
                    "未知项目加载的可控性判据不得被删或降级", rel_pub)
    # 维护方自己的承接清单：不得缺、且须指向公共判据
    rel_m = "specs-project-maintainer/context.adoc"
    m_path = os.path.join(REPO_ROOT, *rel_m.split("/"))
    if not os.path.isfile(m_path):
        err(f"缺少维护方接纳面清单 {rel_m}——维护方在新增公共内容时的核对职责无人承载", rel_m)
    else:
        with open(m_path, encoding="utf-8") as fh:
            mtext = fh.read()
        for key, desc in (("运行契约", "维护方的核对落点"),
                          ("影响面", "三维之一"),
                          ("成本", "三维之一"),
                          ("可控性", "三维之一")):
            if key not in mtext:
                err(f"接纳面防线被破坏：{rel_m} 缺失『{key}』（{desc}）", rel_m)
        if not os.path.isfile(PROJECT_FILE) or rel_m not in open(
                PROJECT_FILE, encoding="utf-8").read():
            err(f"{rel_m} 未在维护方项目规范入口 AGENTS.adoc 登记"
                "（不会被加载、其中规则实际失效）", "AGENTS.adoc")
    check_public_content_has_no_private_refs()
    check_public_content_is_self_contained()
    phase_done()



def check_ci_cd_guard():
    """『CI/CD 与平台协作防线』：CICD 校验链完整性与 CNB 对象钉定要点不得被删或降级。

    背景：来自 CI 内 agent 的踩坑报告——①CI 只跑主校验脚本、**配套测试从未在 CI 执行**
    （其中一个测试文件因命名无法被自动发现、用例长期零执行）；②触发路径与校验对象不一致；
    ③流水线引用**不存在的镜像/制品**，在 Prepare 阶段即失败；④任务长期停在 pending、
    **无可判定超时**；⑤同一分支多次推送 / 压缩提交强推后，复核按分支名取到**过期对象**、
    结论错位；⑥派发对象未钉定 commit sha。这些失效在"编写/调优流水线"与"在平台上协作"
    时反复出现，属**可机械钉住的关键判据**，故设本防线。

    只钉"节与要点仍在"，语义是否被削弱仍由人/子 agent 复核承担。
    """
    phase("CI/CD 与平台协作防线检查")
    # ① CI/CD 规范：校验链完整 / 触发范围 / 依赖可用 / 超时
    rel_ci = "specs/general/ci-cd.adoc"
    ci_path = os.path.join(REPO_ROOT, *rel_ci.split("/"))
    if not os.path.isfile(ci_path):
        err(f"缺少 CI/CD 规范文件 {rel_ci}——"
            "流水线校验链完整性与超时等判据失去集中落点", rel_ci)
    else:
        with open(ci_path, encoding="utf-8") as fh:
            text = fh.read()
        for key, desc in (
                ("校验链完整", "流水线须跑全既定校验（含配套测试），防‘定义未执行’"),
                ("只跑主校验脚本", "把‘只跑主脚本’显式判为验证不完整"),
                ("须能被测试框架自动发现", "测试文件命名/位置须落在框架发现规则内"),
                ("触发路径须覆盖校验对象", "改了却不跑＝漏检"),
                ("须先确认实际可用", "上游镜像/制品/工具须实测可用，不得凭名称假设"),
                ("须有可判定的超时", "不得让流水线无限挂在 pending"),
                ("不在 CI 中调用会给出非确定性结论的外部 AI", "非确定性不得阻塞构建")):
            if key not in text:
                err(f"CI/CD 防线被破坏：{rel_ci} 缺失『{key}』（{desc}）——"
                    "踩坑判据不得被删或降级", rel_ci)
    # ② CNB 平台规范：对象钉定与可追溯 / 执行者可用性
    rel_cnb = "specs/platform/cnb.adoc"
    cnb_path = os.path.join(REPO_ROOT, *rel_cnb.split("/"))
    if not os.path.isfile(cnb_path):
        err(f"缺少 CNB 平台规范文件 {rel_cnb}——"
            "平台上的对象钉定与协作判据失去集中落点", rel_cnb)
    else:
        with open(cnb_path, encoding="utf-8") as fh:
            text = fh.read()
        for key, desc in (
                ("派发与复核须钉定 commit sha", "分支名不是稳定标识，须钉 sha"),
                ("压缩提交/强推会替换对象", "旧 sha 作废、结论须在新 sha 上重核"),
                ("git fetch -f", "取对象前须强刷 ref，防本地缓存旧 sha"),
                ("派发前确认执行者实际可用", "镜像/制品 not found 时任务从未真正开始"),
                ("流水线不无界挂起", "平台 job/step 须可判定超时")):
            if key not in text:
                err(f"CNB 平台防线被破坏：{rel_cnb} 缺失『{key}』（{desc}）——"
                    "平台协作的踩坑判据不得被删或降级", rel_cnb)
    # ③ 相应的通用侧落点：验证须覆盖全部校验手段、验证对象钉定 sha（verify.adoc）
    rel_v = "specs/general/verify.adoc"
    v_path = os.path.join(REPO_ROOT, *rel_v.split("/"))
    if os.path.isfile(v_path):
        with open(v_path, encoding="utf-8") as fh:
            vtext = fh.read()
        for key, desc in (
                ("验证须覆盖项目的全部既定校验手段", "‘存在测试’≠‘测试被执行’"),
                ("验证对象须钉定 commit sha", "验证/复核前须先取定 sha")):
            if key not in vtext:
                err(f"CI/CD 防线被破坏：{rel_v} 缺失『{key}』（{desc}）", rel_v)
    # ④ 协作侧落点：派发对象钉定与执行者可用性（collab.adoc）
    rel_c = "specs/general/collab.adoc"
    c_path = os.path.join(REPO_ROOT, *rel_c.split("/"))
    if os.path.isfile(c_path):
        with open(c_path, encoding="utf-8") as fh:
            ctext = fh.read()
        for key, desc in (
                ("派发对象须钉定 commit sha", "派发指令须写明具体 sha"),
                ("派发前确认执行者可执行", "确认镜像/制品实际可取")):
            if key not in ctext:
                err(f"CI/CD 防线被破坏：{rel_c} 缺失『{key}』（{desc}）", rel_c)
    phase_done()

def check_self_check_guard():
    """『自检防线』：执行前自检规范与其必加载层落点不得被删或降级。

    背景：规范按"懒加载"设计，**加载是规则生效的前提**——"文件里写了某条必须"不等于
    本次执行加载并遵守了它。self-check.adoc 把"动手前的自检"从一句无判定标准的自觉
    要求，变成可逐项核对的动作（指令、规范加载、规划落盘、读取范围、证据、收尾），
    是加载防线的兜底关口。"精简/去重"时它最容易被当成"软要求"删掉，故机械钉住其
    **存在性与关键要点**，并确认 specs/core/execution.adoc（必加载层）留有落点。

    只钉"存在性与关键词"，不改写内容——清单是否被实质削弱仍由人/子 agent 复核承担。
    """
    phase("自检防线检查")
    rel = os.path.relpath(SELF_CHECK_FILE, REPO_ROOT).replace("\\", "/")
    if not os.path.isfile(SELF_CHECK_FILE):
        err(f"缺少执行前自检规范文件 {rel}——"
            "动手前的自检关口丢失（规范是否被实际加载与遵守将无兜底）", rel)
    else:
        with open(SELF_CHECK_FILE, encoding="utf-8") as fh:
            text = fh.read()
        for key, desc in (
                ("执行前自检清单", "动手前逐项自检的清单"),
                ("非平凡任务", "自检适用范围界定（防被'只对大任务'架空）"),
                ("不得顺口编造", "知识边界（不知道就说不知道、去查证）"),
                ("完成前自检", "交付前的对照核验")):
            if key not in text:
                err(f"自检防线被破坏：{rel} 缺失『{key}』（{desc}）——"
                    "自检要点不得被删或降级", rel)
    # 公共层（`specs/general/`）的规范文件由调度器登记；自检机制同时须有必加载层落点
    # （执行原则里的一行引用），否则"动手前自检"不会被任何入口触发。
    with open(GENERIC_FILE, encoding="utf-8") as fh:
        if rel not in set(extract_specs_refs(fh.read(), "")):
            err(f"自检规范 {rel} 未在加载调度器登记（不会被加载、其中规则实际失效）",
                "AGENTS_COMMON.adoc")
    rel_exec = "specs/core/execution.adoc"
    exec_path = os.path.join(REPO_ROOT, rel_exec)
    if not os.path.isfile(exec_path):
        err(f"缺少 {rel_exec}，自检的必加载层落点丢失", rel_exec)
    else:
        with open(exec_path, encoding="utf-8") as fh:
            if "自检" not in fh.read():
                err(f"自检防线被破坏：{rel_exec} 缺失对「执行前自检」的落点——"
                    "自检要求未挂到必加载层，实际不会被触发", rel_exec)
    phase_done()


def check_verify_guard():
    """『规范验证防线』：验证口径（三视角/效力等级/总纲/规范验证）与其维护方落点不得被删。

    背景：规范改动的验收有两层——**机械校验**（确定性项）与**语义复核**（确定性脚本
    覆盖不到的概念判断）。语义复核的**规则**（三视角：①完整性 + ②有效性与认知质量 +
    ③接纳面；效力等级：确定项 / 概念项；判准：严格执行 / 尽力而为）属**公共内容**，
    落点为 `specs/general/testing.adoc`「验证与运行契约」（对任何项目成立，且引用方也
    确实需要"改完规范怎么验"）。本仓库侧的落点（维护方要做什么、要钉住哪些抓手）落在
    `specs-project-maintainer/verify.adoc` 与根目录 `AGENTS.adoc`。

    被删则"改完规范只跑机械校验就算验证过"、"验证了什么/依据哪个标准"无从枚举、或把
    三视角拆成多次子 agent 派发都会重新出现。

    只钉"节与要点仍在、标准出处仍在、三处口径指向一致"，判据是否被实质削弱仍由人/子
    agent 复核承担。
    """
    phase("规范验证防线检查")
    rel_public = os.path.join("specs", "general", "testing.adoc").replace(os.sep, "/")
    path_public = os.path.join(REPO_ROOT, *rel_public.split("/"))
    if not os.path.isfile(path_public):
        err(f"缺少公共验证规范文件 {rel_public}——验证三视角、效力等级与运行契约失去落点",
            rel_public)
    else:
        with open(path_public, encoding="utf-8") as fh:
            pub = fh.read()
        for pat, desc in ((r"^==+\s*验证与运行契约", "「验证与运行契约」节（验证的公共口径）"),
                          (r"^==+\s*规范验证", "「规范验证」节（改完规范后的语义复核定式）"),
                          (r"^==+\s*验证总纲", "「验证总纲」节（验证什么、怎么算过、标准出自哪里）"),
                          (r"^==+\s*验证的效力等级", "「验证的效力等级」节（确定项/概念项与结论强度）"),
                          (r"^==+\s*验证的适用边界", "「验证的适用边界」节（先判改动性质）"),
                          (r"^==+\s*运行契约", "「运行契约」节（未知项目加载的可控性）")):
            if not re.search(pat, pub, re.M):
                err(f"规范验证防线被破坏：{rel_public} 缺失{desc}——验证的公共定式不得被删或降级",
                    rel_public)
        for key, desc in (
                ("判据本体验证", "确定项：机械校验按**判据本身**核对，不按引用形式近似"),
                ("概念项", "概念项：无确定性判据，只能启发式复核"),
                ("只能启发式复核", "概念项的可用手段：换角度/换机器/换样本增加独立核对"),
                ("未发现问题", "概念项的结论强度：只到'未发现问题'，不写成'通过'"),
                ("悬置", "未确证部分须逐项标悬置并写明已复核角度"),
                ("不得当作阻断交付的条件", "概念项不得作为交付的隐性前置条件"),
                ("①完整性", "视角一：对象在改动前后是否等价（核对未丢规则）"),
                ("②有效性与认知质量", "视角二：规范本体是否说得对、说得清、跑得动、判得了"),
                ("③接纳面", "视角三：被未知项目加载后的影响面/成本/可控性"),
                ("同一个干净子 agent", "三视角合用一个子 agent 一并回答（一次读取、结论分栏）"),
                ("每次验证都换一个干净上下文", "不复用发起改动/上一轮验证的上下文"),
                ("三态台账", "留证形态：通过 / 未发现问题 / 悬置三态分列、不得合并"),
                ("严格执行", "判准维度：严格执行（须逐次达成并给证据）"),
                ("尽力而为", "判准维度：尽力而为（须尝试、须说明、不记通过）"),
                ("如何验证", "验证对象不止规范文件（会被执行的产物同样要验）"),
                ("读的形态", "②的形态项：执行侧只给怎么走（重构最易丢的一条）"),
                ("ISO/IEC Directives Part 2", "标准出处：要求须可验证（防自造一套说法）"),
                ("RFC 2119", "标准出处：用语强度（要求与建议不得混用）"),
                ("ISO 10007", "标准出处：配置管理与变更控制"),
                ("ISO/IEC/IEEE 25010", "标准出处：质量特性（含性能效率）"),
                ("IEEE 1028", "标准出处：软件评审")):
            if key not in pub:
                err(f"规范验证防线被破坏：{rel_public} 缺失『{key}』（{desc}）——"
                    "验证的判定标准与标准出处不得被删或降级", rel_public)
    # 维护方落点：specs-project-maintainer/verify.adoc 须存在且含"三视角/悬置/超时"三要点
    rel_m = "specs-project-maintainer/verify.adoc"
    path_m = os.path.join(REPO_ROOT, *rel_m.split("/"))
    if not os.path.isfile(path_m):
        err(f"缺少维护方验证落点 {rel_m}——维护方自己的验证义务（三视角动作、硬超时、"
            "三态台账）失去集中落点", rel_m)
    else:
        with open(path_m, encoding="utf-8") as fh:
            mtext = fh.read()
        for key, desc in (("硬超时", "派发子 agent 必须自带可判定的时限"),
                          ("悬置", "查不出的部分如实标悬置、写明已复核角度"),
                          ("三态台账", "留证按三态分列、不得合并"),
                          ("完整性校验", "改完规范必做的完整性校验动作"),
                          ("check_checklist_guard", "维护方侧的具名抓手（文档↔脚本一致）")):
            if key not in mtext:
                err(f"规范验证防线被破坏：{rel_m} 缺失『{key}』（{desc}）——"
                    "维护方的验证义务不得被删或降级", rel_m)
    # 最高关注项 P2 的落点须指向公共验证口径
    rel_p2 = "specs-project-maintainer/priority.adoc"
    p2_path = os.path.join(REPO_ROOT, *rel_p2.split("/"))
    if not os.path.isfile(p2_path):
        err(f"缺少 {rel_p2}——最高关注项 P2 的落点丢失", rel_p2)
    else:
        with open(p2_path, encoding="utf-8") as fh:
            p2_text = fh.read()
        for key, desc in (("②有效性与认知质量", "P2 须声明语义复核的第二视角"),
                          ("③接纳面", "P2 须声明语义复核的第三视角（未知项目加载）"),
                          ("同一个干净子 agent", "P2 须声明三视角合用一个子 agent"),
                          ("验证的效力等级", "P2 须指向效力等级口径（结论强度按对象分档）"),
                          ("未发现问题", "P2 须声明复核结论只到'未发现问题'"),
                          ("悬置", "P2 须声明未确证部分标悬置（写明已复核角度）"),
                          ("不得当作阻断交付的条件", "P2 须声明概念项不得阻断交付")):
            if key not in p2_text:
                err(f"规范验证防线被破坏：{rel_p2} 的 P2 缺失『{key}』（{desc}）——"
                    "最高关注项 P2 的语义复核退化为只查完整性", rel_p2)
    # 本仓库落点：AGENTS.adoc 的完整性校验动作须与公共口径同源
    rel_own = "AGENTS.adoc"
    own_path = os.path.join(REPO_ROOT, *rel_own.split("/"))
    if os.path.isfile(own_path):
        with open(own_path, encoding="utf-8") as fh:
            own_text = fh.read()
        for key, desc in (("②有效性与认知质量", "本仓库的完整性校验动作须含第二视角"),
                          ("③接纳面", "本仓库的完整性校验动作须含第三视角"),
                          ("三视角合用一个子 agent", "本仓库须声明三视角合一次派发"),
                          ("未发现问题", "本仓库落点须区分'未发现问题'与'通过'")):
            if key not in own_text:
                err(f"规范验证防线被破坏：{rel_own} 的完整性校验动作缺失『{key}』（{desc}）——"
                    "本仓库维护口径须与公共口径一致", rel_own)


def check_public_content_has_no_private_refs():
    """公共内容不得把**本仓库私有物当成可执行抓手/可读文档**引用（③可控性的机械抓手）。

    背景（接纳面失效的机械可判定形态）：公共内容（`AGENTS_COMMON.adoc` + `specs/`）
    会被**未知项目**加载，而引用方**看不到本仓库的维护入口与工具**——本仓库根
    `AGENTS.adoc`、`PROMPTS.adoc`、`script/check_*.py` 等。公共内容一旦把"检查由
    `script/check_specs.py` 钉住""见根目录 `AGENTS.adoc`"这类话写进去，引用方读到的
    就是**死链**：既加载不到、也无法据此执行（属 `specs-project-maintainer/spec-lifecycle.adoc`
    「规范集合的自身重构」"删"所禁的形态）。

    判定只认**"被当成本仓库私有物引用"**这一机械可判定的形态，两条同时成立才算命中：

      * 命中点出现在**维护动作/抓手声明**语境（同一行含"本仓库/本项目自身/校验脚本/
        check_specs/check_effective/工具声明"等词），且
      * 点名了本仓库私有物（`script/check_*.py`、`script/clean_tmp.py`、`PROMPTS.adoc`，
        或根目录 `AGENTS.adoc`）。

    **刻意不拦**的合法用法（避免误伤，均为规范有意为之）：
      * `AGENTS.adoc` 作为"**引用方项目自己的**项目规范"被提及（`AGENTS_COMMON.adoc`
        「访问与解析」与 `spec-lifecycle.adoc`「公共规范还是项目规范」正需这样写）；
      * `CHANGELOG.adoc`/`CHANGELOG.md` 作为**通用默认文件名**被列举（doc-design 的
        "变更日志统一集中一处"正是给任意项目定的默认名）；
      * 根 `AGENTS.adoc` 与 `script/`、`README.adoc` 等**项目自身内容**本身（不属公共内容，
        可以自由引用私有物）。

    只拦"名字与语境同时命中"的形态，"该表述是否真在引它"仍由人/子 agent 复核承担。
    """
    phase("公共内容私有引用检查（③可控性）")
    # 私有物名 → 说明；匹配时要求同行出现"维护语境"词，避免把合法提及误判为引用
    private_names = ("script/check_specs.py", "script/check_effective.py",
                     "script/clean_tmp.py", "PROMPTS.adoc", "AGENTS.adoc")
    context_words = ("本仓库", "本项目自身", "校验脚本", "机械校验", "工具声明",
                     "check_specs", "check_effective", "check_priority_guard",
                     "check_principle_guard", "check_verify_guard",
                     "check_adoption_guard", "check_source_guard",
                     "check_filler_docs", "CI 拦下")
    for f in [_rel_of(GENERIC_FILE)] + collect_adoc_files():
        rel = _rel_of(f)
        if rel == "AGENTS.adoc":
            continue  # 根 AGENTS.adoc 是项目自身内容，允许引用私有物
        if rel != "AGENTS_COMMON.adoc" and not rel.startswith("specs/"):
            continue  # 只检查公共内容（AGENTS_COMMON.adoc + specs/）；specs-project-maintainer/ 属维护方自有
        path = os.path.join(REPO_ROOT, *rel.split("/"))
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for j, line in enumerate(fh.readlines(), 1):
                if not any(w in line for w in context_words):
                    continue
                for name in private_names:
                    if f"`{name}" in line or f"link:{name}" in line:
                        err(f"公共内容不得把本仓库私有物『{name}』当作抓手/文档引用——"
                            "引用方看不到它、读到的只是死链；请改成自足的通用表述"
                            "（'维护规范集合的项目须自行设机械防线'一类）", rel, j)
    phase_done()


def check_public_content_is_self_contained():
    """『公共内容自足性防线』：公共内容（`AGENTS_COMMON.adoc` + `specs/`）不得引用私有落点。

    背景（本次重构暴露的真实缺陷）：**一个文件可以同时装着公共规则与项目自身规则**，
    而当它躺在公共侧（`specs/`）时，其中的项目自身落点就成了**引用方读不到的死链**——
    "本仓库的优先级见 `specs-project/priority.adoc`"这类话，引用方既没有该文件、
    也没有加载它的入口，读到的规范"只成立一半"。故把"公共内容自足"变成机械可判定的形态：

      * 公共内容里出现的路径引用，只能指向 `AGENTS_COMMON.adoc` 与 `specs/` 下的文件；
      * **不得出现指向维护方自查层（`specs-project-maintainer/`）的引用**——该层不随公共
        内容分发，引用方拿不到；公共内容里的规则必须在本文件与 `specs/` 内自足表达。

    覆盖对象是"自足受限集合"的两类（见 `PUBLIC.adoc`「自足要求的适用范围」）：
      * ①**会被入口取到的**——`AGENTS_COMMON.adoc` 与 `specs/**`；
      * ②**会被复制到未知项目执行的**——`prompts/*.adoc`。它们同样在未知项目里执行，
        其中指向本仓库私有落点的路径同样是引用方读不到的死链（`PUBLIC.adoc` 明写
        "机械检查按『公共内容』口径覆盖它们"——此前该承诺不成立：`prompts/` 既不在
        检查集合、也不在本条过滤范围内）。
    边界：`prompts/_common.txt` 亦属②类（公共片段），但它不是 `.adoc`、不进
    `collect_adoc_files`，故不在本条覆盖内——其自足性目前无机械抓手，属已知缺口。

    与 check_public_content_has_no_private_refs 的分工：那条拦"把本仓库私有物（脚本名、
    工具声明）当抓手引用"，本条拦"把私有**规范文件**当规则正文引用"（悬空引用）。

    只钉"引用指向的位置是否随公共内容分发"，该表述是否真需自足仍由人/子 agent 复核承担。
    """
    phase("公共内容自足性检查（不引用私有落点）")
    for f in [_rel_of(GENERIC_FILE)] + collect_adoc_files():
        rel = _rel_of(f)
        if rel == "AGENTS.adoc":
            continue  # 根 AGENTS.adoc 是项目自身内容，可引用任意私有落点
        # 自足受限集合 = ①会被入口取到的（AGENTS_COMMON.adoc + specs/**）
        #              ∪ ②会被复制到未知项目执行的（prompts/**，见 PUBLIC.adoc）
        if rel != "AGENTS_COMMON.adoc" and not rel.startswith("specs/") \
                and not rel.startswith("prompts/"):
            continue  # 其余（library/、README 等）不属本条的约束对象
        path = os.path.join(REPO_ROOT, *rel.split("/"))
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for j, line in enumerate(fh.readlines(), 1):
                if "specs-project-maintainer/" in line:
                    err("公共内容不得引用维护方自查层『specs-project-maintainer/』——"
                        "该层不随公共内容分发，引用方看不到该文件（读到的规则只成立一半）；"
                        "请把这条规则在公共内容里自足表达，或把它移出公共内容", rel, j)
    phase_done()


def check_public_facing_docs_stay_self_contained():
    """『公开面文档自足性防线』：会被**分发给引用方/在公开站点渲染**的文档不得指向维护方自查层。

    背景（本轮重构暴露的真实缺陷）：`specs/` 被刚性地拦住了指向 `specs-project-maintainer/`
    的引用，但 `README.adoc`（公开站点首页由它渲染）、`PROMPTS.adoc`（公开提示词入口）与
    `INSTALL.adoc`（引用方安装文档）**同样会被未知项目看到**——它们里的 `link:` 与仓库相对
    路径，引用方按同样方式解析，指向维护方自查层就是**死链**（该层不随公共内容分发、也没有
    引用方侧入口）；而它们又最能"顺手"把维护类元规范写进去（本轮就发生过：README 新增了
    8 处指向维护方层的链接）。

    判定：这几份公开面文档中**不得出现**维护方自查层的目录名（`specs-project-maintainer/`）。
    规则正文要在公开文档里说明"本仓库另有一层只对维护方成立"是允许的，用**文字描述**即可，
    但**不得给出该层文件的可点开路径**。

    只钉"公开面文档有没有指向该层的路径"，这些文档其余内容的取舍仍由人/子 agent 复核承担。
    """
    phase("公开面文档自足性检查（README/PROMPTS/INSTALL 不指向维护方层）")
    for rel in ("README.adoc", "PROMPTS.adoc", "INSTALL.adoc"):
        path = os.path.join(REPO_ROOT, rel)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for j, line in enumerate(fh.readlines(), 1):
                if "specs-project-maintainer/" in line:
                    err("公开面文档不得给出维护方自查层『specs-project-maintainer/』的路径——"
                        "本文件会被引用方阅读/在公开站点渲染，该层不随公共内容分发，"
                        "引用方读到的是死链；请改为文字描述（'本仓库另有一层只对维护方成立'）"
                        "或删掉该链接", rel, j)
    phase_done()


def check_no_mechanism_claims_in_public():
    """公共内容不得**声明机械防线的存在**（防"机械防线随规范分发"的错觉）。

    背景：机械防线（校验脚本、防线名、项目自身的检查流程）是**维护规范集合的那一方**
    才有的东西：公共内容会被**未知项目**加载，那个项目里既没有本仓库的脚本、也没有
    本仓库的"防线"，更无从执行。故公共内容里凡**声明"存在某道防线 / 由某道防线钉住"**
    的句子，都是**没有承载价值的元信息**——引用方既拿不到它、也不该依赖它，属
    `specs-project-maintainer/spec-lifecycle.adoc`「规范集合的自身重构」"删"所指的"本仓库工具名、
    脚本名、仓库结构写进公共内容"，与**宣称与实际不符**（规范文本说"已由机械防线钉住"，
    而引用方没有任何抓手）。

    与"要求"的边界（**不得误伤**）：公共内容里**要求**维护规范集合的项目"设机械防线"
    是**通用规则**（任何维护规范集合的项目都成立），保留不动；被拦的是**声明防线已存在**
    的句子与**裸防线名**，机制是两条同时成立的形态判定：

      * **① 有限期限定词**（"当前/目前/已由/另有/本仓库/本项目的"）**且**含"防线"
        （不含"应/须/要求"这类要求语气）；
      * **② 裸防线名**：出现 `check_<小写动词>` 形式的脚本函数名（即本仓库 `script/`
        里实际定义的那些 `check_*`），公共内容一律不得写——它是私有抓手名，
        引用方看不到、也无法据此执行。

    同时检查 `AGENTS_COMMON.adoc` 之外的**公共内容说明文档**（`README.adoc` 介绍公共
    内容的范围与形态、`PROMPTS.adoc` 是公开入口）：它们面向的读者与公共内容相同，
    声称"某防线钉住公共内容"同样与实际不符。
    只拦"形态同时成立"的句子，"该表述是否真在宣称防线"仍由人/子 agent 复核承担。
    """
    phase("公共内容不得声明机械防线检查（元信息）")
    claim_words = ("当前", "目前", "已由", "另有", "本仓库", "本项目")
    for f in [_rel_of(GENERIC_FILE), _rel_of(PROMPTS_FILE), _rel_of(README_FILE)] \
            + collect_adoc_files():
        rel = _rel_of(f)
        if rel == "AGENTS.adoc":
            continue  # 根 AGENTS.adoc 是项目自身内容，可以声明本仓库防线
        path = os.path.join(REPO_ROOT, *rel.split("/"))
        if not os.path.isfile(path):
            continue
        if rel != "AGENTS_COMMON.adoc" and not rel.startswith("specs/") \
                and rel not in ("README.adoc", "PROMPTS.adoc"):
            continue  # 只检查公共内容与其说明文档；specs-project-maintainer/ 属维护方自有，可点名自家防线
        with open(path, encoding="utf-8") as fh:
            for j, line in enumerate(fh.readlines(), 1):
                if "防线" in line and any(w in line for w in claim_words) \
                        and not any(w in line for w in ("应", "须", "要求")):
                    err("公共内容不得声明机械防线的存在（如'当前由某防线钉住''本仓库另有防线'）——"
                        "机械防线属维护规范集合的那一方，引用方既拿不到也不该依赖它；"
                        "请删掉该声明的元信息，或改成自足的通用表述"
                        "（'维护规范集合的项目应自行设机械防线'一类）", rel, j)
                m = re.search(r"check_[a-z]+_[a-z_]+", line)
                if m:
                    err(f"公共内容不得出现裸防线名『{m.group(0)}』——"
                        "它是私有抓手名，引用方看不到、也无法据此执行；"
                        "请删掉或改为通用表述（'机械防线'/'机械校验'）", rel, j)
    phase_done()


def check_source_guard():
    """『来源防线』：依据与来源真实性规范及其要点不得被删或降级。

    背景：给出来源是为让读者"知其所以然"，但**来源一旦不实，危害大于不给**——一个
    虚构的标准号或已删除的文件引用会污染整条下游引用链。source.adoc 把"引用与事实"
    的要求集中成可核对条款，故机械钉住其**存在性与关键要点**，防"精简/去重"时被顺手删掉。

    只钉"存在性与关键词"，不改写内容——条款是否被实质削弱仍由人/子 agent 复核承担。
    """
    phase("来源防线检查")
    rel = os.path.relpath(SOURCE_FILE, REPO_ROOT).replace("\\", "/")
    if not os.path.isfile(SOURCE_FILE):
        err(f"缺少依据与来源真实性规范文件 {rel}——"
            "引用真实性与『不得编造』失去集中落点", rel)
    else:
        with open(SOURCE_FILE, encoding="utf-8") as fh:
            text = fh.read()
        for key, desc in (
                ("真实存在", "内部引用须指向当前真实存在的目标"),
                ("不得编造", "标准编号/名称与事实不得凭印象生成"),
                ("宁可不引", "无法确证时的正确做法（不给不错）"),
                ("不附链接", "外部标准只写名称/编号、不附链接")):
            if key not in text:
                err(f"来源防线被破坏：{rel} 缺失『{key}』（{desc}）——"
                    "来源真实性要点不得被删或降级", rel)
    with open(GENERIC_FILE, encoding="utf-8") as fh:
        if rel not in set(extract_specs_refs(fh.read(), "")):
            err(f"来源真实性规范 {rel} 未在加载调度器登记（不会被加载、其中规则实际失效）",
                "AGENTS_COMMON.adoc")
    phase_done()


# 提示词「主侧重（方向前提）」与「优先级规则」的机械防线口径：

#   * 每个提示词的侧重点用一段**块级短语**承载，形如 `**主侧重（…）**：**检查修复问题**——…`；
#     两侧分别锚定「主侧重」标签与「方向」标签，中间即侧重内容本身。
PRIMARY_LABEL = "主侧重"
PRIMARY_LINE = re.compile(
    r"\*\*主侧重[^*]*\*\*\s*[:：]\s*\*\*([^*]+)\*\*[^\n]*方向")
# 登记表侧重列：`| **<侧重>** | 主侧重片段 \`primary\``；侧重内容两侧的引号/星号
# 只为排版强调，比对时统一剥掉，避免"同一侧重、写法不同"被误判为未登记。
PRIMARY_ADOC = re.compile(
    r"\|\s*\*\*([^*|]+?)\*\*\s*\|\s*主侧重片段 `primary`")
# 提示词正文的「主侧重（方向性前提，先读）」段：`**主侧重（…）**：**<侧重>**——…`。
# 用更宽的行内锚点扫描，确保侧重值出现在正文说明段（而非仅在片段占位符里）。
PRIMARY_ANY = re.compile(
    r"\*\*主侧重[^*\n]*\*\*\s*[:：]\s*\*\*([^*|\n]+?)\*\*")


def _normalize_primary(text: str) -> str:
    """归一化侧重方向文本：去掉排版用的引号/星号/空白，便于登记表与正文比对。"""
    return text.strip().strip('"\'“”*').strip()
#   优先级规则归并用语（RFC 2119 / ISO shall-should-may 的对应关系），三级定义缺一即防线被破坏。
PRIORITY_TERMS = {
    "L1": ("必须", "严禁"),
    "L2": ("应当",),
    "L3": ("可以",),
}


def _iter_prompt_files():
    """列出公共任务提示词文档（`prompts/` 下非 `_` 前缀的 .adoc）。"""
    if not os.path.isdir(PROMPTS_DIR):
        return []
    return sorted(os.path.join(PROMPTS_DIR, f)
                  for f in os.listdir(PROMPTS_DIR)
                  if f.endswith(".adoc") and not f.startswith("_"))



def check_checklist_guard():
    """『清单逐项与文档-脚本一致性防线』：把"可机械核对却被漏掉"的判定点补成抓手。

    背景：独立复核指出当前防线只钉"集合级关键短语存在性"，两类失效因此漏过——
    ①**清单被少列一项**（如准入判定号称"八问"、实际条目已增删；七节点表少一行）；
    ②**文档声称的抓手与脚本实际实现不一致**（`AGENTS.adoc`/`README.adoc` 号称某
    `check_*` 存在，而脚本里已改名/删除 —— 属"定义了却不执行"的另一面：
    声称有防线而防线不存在）。

    故本防线做两件确定性核对（均只看本仓库维护的文本，不触碰引用方工作区）：
      * **清单逐项**：准入判定的条目数须与其自称的"九问"一致；任务生命周期的七节点
        须逐个在表中出现；两张复核表的三视角/三维标签须齐全；
      * **文档↔脚本一致性**：`AGENTS.adoc`、`README.adoc` 里以反引号给出的
        `check_*` / 脚本名，须在 `script/` 下真实存在（改脚本名即须同步文档）。

    只钉"项数与名字对不对得上"，条文强弱仍由人/子 agent 复核承担。
    """
    phase("清单逐项与文档-脚本一致性防线检查")

    # 1) 准入判定：自称"九问"则条目须为 9 条
    rel_sl = "specs-project-maintainer/spec-lifecycle.adoc"
    sl_path = os.path.join(REPO_ROOT, *rel_sl.split("/"))
    if os.path.isfile(sl_path):
        with open(sl_path, encoding="utf-8") as fh:
            sl = fh.read()
        m = re.search(r"== 准入判定.*?(?=\n== )", sl, re.S)
        if m is None:
            err(f"{rel_sl} 未找到「准入判定」节——准入清单的项数失去抓手", rel_sl)
        else:
            items = re.findall(r"^\. \*\*", m.group(0), re.M)
            claim = re.search(r"准入判定\*\*（([一二三四五六七八九十]+)问", m.group(0))
            if claim is None:
                err(f"{rel_sl} 的「准入判定」未声明项数（形如『九问』）——"
                    "项数不写就无法核对该收的条目有没有被少列", rel_sl)
            else:
                num_map = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
                           "七": 7, "八": 8, "九": 9, "十": 10}
                want = num_map.get(claim.group(1))
                if want is not None and len(items) != want:
                    err(f"{rel_sl}「准入判定」自称 {claim.group(1)}问、实际列出 "
                        f"{len(items)} 条——清单被增删而声明未同步（读者按声明核对会漏项）",
                        rel_sl)

    # 2) 任务生命周期：七节点须逐个在表中出现
    rel_ex = "specs/core/execution.adoc"
    ex_path = os.path.join(REPO_ROOT, *rel_ex.split("/"))
    if os.path.isfile(ex_path):
        with open(ex_path, encoding="utf-8") as fh:
            ex = fh.read()
        m = re.search(r"== 任务生命周期与节点自查.*?(?=\n== )", ex, re.S)
        if m is None:
            err(f"{rel_ex} 未找到「任务生命周期与节点自查」节", rel_ex)
        else:
            for node in ("提出", "理解", "方案", "执行", "验证", "交付", "复盘"):
                if f"| **{node}**" not in m.group(0):
                    err(f"{rel_ex}「任务生命周期与节点自查」表中缺少节点『{node}』——"
                        "节点被删则该节点的自查要求实际失效", rel_ex)
            # 效力标法须写明（防"哪些节点 L1、哪些仅公共内容改动"再次含混）
            for key in ("仅公共内容改动", "哪些节点不设"):
                if key not in m.group(0):
                    err(f"{rel_ex}「任务生命周期与节点自查」缺少『{key}』——"
                        "节点效力标法（哪些节点对任何任务成立、哪些仅公共内容改动）"
                        "不得被含糊掉", rel_ex)

    # 3) 复核机制的可执行性：硬超时与三态留证须仍在（防"防卡死"与"留证"退化回口号）
    rel_v = "specs-project-maintainer/verify.adoc"
    v_path = os.path.join(REPO_ROOT, *rel_v.split("/"))
    if os.path.isfile(v_path):
        with open(v_path, encoding="utf-8") as fh:
            vtext = fh.read()
        # 钉"整条要求仍在"而非"关键词出现过一次"——须同时命中该条的多处要素，
        # 否则别处一句"三态"字样即可让检查假绿（这正是本防线要防的失效模式）。
        for keys, desc in ((("三态台账", "悬置", "未发现问题", "不得合并"),
                            "留证须按三态台账（通过/未发现问题/悬置）分列、不得合并"),
                           (("通过**（附判据与取值）", "悬置**（附"),
                            "三态各自的附带信息（判据取值 / 未确证原因与剩余风险）")):
            missing = [k for k in keys if k not in vtext]
            if missing:
                err(f"{rel_v} 缺失三态台账要素 {missing}——{desc}，留证会退化成散文结论"
                    "（\"查不出\"与\"没做\"无法分辨）", rel_v)
    rel_c = "specs/general/collab.adoc"
    c_path = os.path.join(REPO_ROOT, *rel_c.split("/"))
    if os.path.isfile(c_path):
        with open(c_path, encoding="utf-8") as fh:
            ctext = fh.read()
        for keys, desc in ((("硬超时", "到点即视为失联", "不得无限等待"),
                            "派发子 agent 须自带可判定的时限，到点视为失联（防任务永久挂起）"),
                           (("超时的处置", "放弃该子 agent", "如实"),
                            "超时后须放弃 + 如实标悬置，不得无限等待、不得写成已通过"),
                           (("时限取值须有判据", "一次性、边界明确、可超时"),
                            "时限取值须有判据、优先选可超时的一次性派发形式")):
            missing = [k for k in keys if k not in ctext]
            if missing:
                err(f"{rel_c} 缺失硬超时要素 {missing}——{desc}；语义复核会再次卡死且无人负责",
                    rel_c)

    # 4) 文档↔脚本一致性：文档里点名的 check_* / 脚本名须真实存在
    script_names = set()
    script_dir = os.path.join(REPO_ROOT, "script")
    if os.path.isdir(script_dir):
        script_names = set(os.listdir(script_dir))
    with open(os.path.join(REPO_ROOT, "script", "check_specs.py"), encoding="utf-8") as fh:
        self_src = fh.read()
    defined = set(re.findall(r"^def (check_[a-z_]+)\(", self_src, re.M))
    # 校验范围含**维护方内容**（AGENTS.adoc、PUBLIC.adoc）：它们同样会点名 `check_*` 与
    # 脚本名，改名/删除后不同步即"声称有防线而防线不存在"。
    for rel in ("AGENTS.adoc", "PUBLIC.adoc", "README.adoc"):
        path = os.path.join(REPO_ROOT, *rel.split("/"))
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for name in sorted(set(re.findall(r"`(check_[a-z_]+|clean_tmp\.py|check_specs\.py|"
                                          r"check_effective\.py)`", text))):
            if name.endswith(".py"):
                if name not in script_names:
                    err(f"{rel} 点名了不存在的脚本 `{name}`——"
                        "文档声称的抓手与 script/ 实际不一致", rel)
            elif name not in defined:
                err(f"{rel} 点名了脚本中未定义的 `{name}`——"
                    "防线的声称与实现不一致（改名/删除后未同步文档）", rel)
    phase_done()


# 图书馆（仓库根 `library/`，**本仓库私有内容、不随规范分发**）：其价值全在"依据真的
# 能查到、真的对得上"——入口登记的主题文件必须真实存在，外部标准的**逐字引文**必须仍在
# （少一句就意味着"依据被压成名称"）。图书馆不在公共内容里，故"内容会被分发"一类约束
# 不再适用；剩下的是**本仓库自己的完整性**：有没有、登记是否双向一致、引文还在不在、
# 文件里的引用是否真能解析（引用方看不到这里，引用悬空只有本仓库自己能发现）。
# 判定只认机械可判定的形态：文件/片段存在性与引用可解析性；"该依据是否真的支持该条、
# 依据找得全不全"属语义判断，交人/子 agent 复核承担（见 specs/general/verify.adoc「验证总纲」）。
# **取样来源标记**：图书馆的每条外部依据都须带"它是怎么被取回的"标记——这是"不划水、
# 不造假"的判据落点。三类标记缺任一类，就意味着某类依据的**可信度边界**无从判断
# （"官方文本已取回"可复取比对 vs "官方网页已取回"仅题名可对 vs "未逐字取回"不引其字句）。
# 常量化后由 check_library_guard 机械钉住：标记整体被删（依据被悄悄压成"看起来很权威的
# 名称"）即报错——grep 在 sources.adoc 命中只说明文档正文举例还在，不等于防线覆盖到它。
LIBRARY_SOURCE_MARKERS = (
    "官方文本已取回",
    "官方网页已取回",
    "未逐字取回",
)


def _lib_resolve(target: str):
    """把馆内引用的写法解析为**仓库根相对路径**（单一基准），无法解析/越界则返回 None。

    基准口径（与反引号写法一致，见 check_library_guard 的"引用可解析"条）：
      1. 先按**仓库根**解析（`CHANGELOG.adoc`、`AGENTS_COMMON.adoc`、`specs/general/doc.adoc`）
         —— 与 Asciidoctor.js 渲染的文档站一致（`link:` 按文档源所在目录解析，文档在仓库根）；
      2. 未命中再按**本文件所在目录**解析（`../specs/...` 这类真正离开 `library/` 的写法）。

    **同一写法只有一个基准**：历史实现里反引号按仓库根、`link:` 按本文件目录，
    结果同一句引用 `CHANGELOG.adoc` 的两种写法在"文件存在/不存在"上给出相反结论。
    """
    t = target.strip()
    if not t or t.startswith("#"):
        return None
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", t):
        return None
    if t.startswith("/"):
        return None                       # 根绝对路径：格式问题单独报，不进存在性核对
    is_dir = t.endswith("/")
    repo_rel = posixpath.normpath(t).replace("\\", "/")
    if repo_rel != ".." and not repo_rel.startswith("../"):
        if is_dir:
            if os.path.isdir(os.path.join(REPO_ROOT, *repo_rel.split("/"))):
                return repo_rel + "/"
        elif os.path.isfile(os.path.join(REPO_ROOT, *repo_rel.split("/"))):
            return repo_rel
    local = posixpath.normpath(posixpath.join("library", t)).replace("\\", "/")
    if local == ".." or local.startswith("../"):
        return repo_rel                  # 越出仓库根：返回仓库根解析结果，交由存在性判定报错
    return local + "/" if (is_dir and not local.endswith("/")) else local


def _check_library_target(m: str, desc: str, rel: str, j: int, allow_escape: bool = False):
    """核对一条馆内引用的落点是否为**本仓库内真实存在的文件/目录**。

    `m` 为写法（反引号内的路径或 `link:` 目标）；`desc` 为报错里的引用描述。
    """
    if _is_placeholder_ref(m):
        return
    is_dir = bool(m.endswith("/"))
    resolved = _lib_resolve(m)
    if resolved is None:
        return
    if resolved == ".." or resolved.startswith("../"):
        if allow_escape:
            err(f"{desc} 越出仓库根——馆内引用须指向本仓库内的真实文件", rel, j)
        return
    if is_dir:
        if not os.path.isdir(os.path.join(REPO_ROOT, *resolved.rstrip("/").split("/"))):
            err(f"{desc} 指向不存在的目录——悬空引用等于依据链断在这里", rel, j)
        return
    if not os.path.isfile(os.path.join(REPO_ROOT, *resolved.split("/"))):
        err(f"{desc} 指向不存在的文件——"
            "悬空引用等于依据链断在这里（公共内容里的死链与它无关："
            "图书馆是本仓库私有内容，读者就在本仓库内）", rel, j)


# 根级文件名白名单（馆内以 `xxx.adoc` / `xxx.py` 形态引用本仓库根或已知目录下的文件时，
# 只有在此列内的写法才被当作"路径"核对存在性——防止把普通词/文件名约定当路径误报）。
_LIB_ROOT_FILES = ("AGENTS.adoc", "AGENTS_COMMON.adoc", "AGENTS.md", "PUBLIC.adoc",
                   "README.adoc", "PROMPTS.adoc", "CHANGELOG.adoc", "INSTALL.adoc",
                   "check_specs.py", "check_effective.py", "clean_tmp.py",
                   "_common.txt", "review.adoc", "refactor.adoc")
LIBRARY_QUOTE_ANCHORS = (
    "Software Reviews and Audits",
    "IEEE Standard for Information Technology--Systems Design--Software Design Descriptions",
    "Software and systems engineering — Software testing — Part 4: Test techniques",
    "Systems and software Quality Requirements and Evaluation (SQuaRE) — Product quality model",
    "ISO/IEC Directives, Part 2 — Principles and rules for the structure and drafting",
    "Ergonomics of human-system interaction — Part 110: Interaction principles",
    "Key words for use in RFCs to Indicate Requirement Levels",
    "Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words",
    "UTF-8, a transformation format of ISO 10646",
    "Date and Time on the Internet: Timestamps",
    "The OAuth 2.0 Authorization Framework",
    "Best Current Practice for OAuth 2.0 Security",
    "The 'Basic' HTTP Authentication Scheme",
    "Digital Identity Guidelines: Authentication and Lifecycle Management",
    "Deserialization of Untrusted Data",
    "Observable Timing Discrepancy",
    "Generation of Error Message Containing Sensitive Information",
    "Active Debug Code",
    "Dependency specification for Python Software Packages",
    "Style Guide for Python Code",
    "Docstring Conventions",
    "**/IT*.java",
    "**/*ITCase.java",
    "**/*TestCase.java",
    "MAJOR version when you make incompatible API changes",
    "In many IETF documents, several words",
    "when they are in all capitals as shown below",
) + LIBRARY_SOURCE_MARKERS


def check_library_guard():
    """『图书馆防线』：依据须查得到、对得上、引用不悬空（本仓库私有内容）。

    背景：规范正文刻意只给"怎么走"（规则 + 判定标准 + 依据名），但依据**不能只存在
    名称**——规则执行久了就退化成"只记得是这么做的"，无法判断它还成不成立、无法据以
    取舍与举一反三。图书馆（仓库根 `library/`）就是依据的落点：外部标准的**原文摘录**、
    "这条标准确实支持这条规则"的映射、当初的失效与实证。

    **落点**：图书馆属**本仓库私有内容**（不随规范分发给引用方），故它落在仓库根而不是
    `specs/` 下——`specs/**` 会整个分发给未知项目，而图书馆天然含只对本项目成立的内容。
    由此本条**不检查"自足性 / 是否夹带私有落点"**（那是对公共内容的要求：私有内容本来
    就可以引用自己仓库的任何落点），只检查它作为"依据落点"是否真的可用。

    故本条钉住四件确定项（都是机械可判定的）：
      * **存在与登记**：图书馆入口存在，且**被本仓库项目规范入口 `AGENTS.adoc` 登记**
        （未登记即无触发特征，读者不知道何时该读它，图书馆等于不存在）；
      * **登记双向一致**：以**入口「主题登记」表解析出的集合 `::` 磁盘实际主题文件集合**
        为准（README 的登记表是唯一索引，`LIBRARY_TOPICS` 只是"已知必须有"的下限补丁，
        不是第二真源）——登记了不存在的主题、或存在未登记的主题文件，都报错；
      * **逐字引文仍在**：所登记外部标准的关键片段（题名、模板片段、代码模式等）仍在
        图书馆内——少一句就意味着依据被压成了名称；
      * **引用可解析**：图书馆文件里的引用**一律按仓库根基准**解析——反引号写法
        （`specs|library|script|...` 带目录前缀，以及**根级文件名** `AGENTS.adoc`/
        `PROMPTS.adoc` 等，见 `_LIB_ROOT_FILES` 白名单）、`link:` 目标、`../` 相对写法
        三种**同一基准**：先按仓库根解析，命中即通过；未命中再按"本文件所在目录"解析
        （`../specs/...` 这类真正离开 `library/` 的写法）——**同一写法只有一个基准**，
        不出现"反引号按仓库根、link: 按本文件目录"两套口径（历史缺陷：同一句引用
        `CHANGELOG.adoc` 的两种写法结论相反）。目录型写法核目录、其余核文件。

    "该依据是否真的支持该条、依据找得全不全、有没有把解释当原文"属语义判断，交人/
    子 agent 复核承担。
    """
    phase("图书馆防线检查")
    if not os.path.isfile(LIBRARY_INDEX):
        err("缺少图书馆入口 library/README.adoc——"
            "规范条目与项目决策背后的依据将只剩名称、无从核对"
            "（本仓库为根目录 library/，见 AGENTS.adoc「依据图书馆」）",
            "library/README.adoc")
        phase_done()
        return

    with open(LIBRARY_INDEX, encoding="utf-8") as fh:
        index_text = fh.read()
    with open(PROJECT_FILE, encoding="utf-8") as fh:
        project_entry = fh.read()

    # 1) 项目规范入口登记：图书馆入口须在 AGENTS.adoc 被登记
    if "library/README.adoc" not in project_entry:
        err("图书馆未在本仓库项目规范入口（AGENTS.adoc）登记——"
            "读者无从知道何时该加载它，依据实际不可达"
            "（写文件与登记是同一个动作）",
            "AGENTS.adoc")

    # 2) 入口登记的主题 ↔ 主题目录实际文件，双向一致
    registered = set(re.findall(r"link:([^\[\]]+\.adoc)\[", index_text))
    actual = set()
    if os.path.isdir(LIBRARY_DIR):
        actual = {f for f in os.listdir(LIBRARY_DIR)
                  if f.endswith(".adoc") and f != "README.adoc"}
    for r in sorted(registered):
        if not os.path.isfile(os.path.join(LIBRARY_DIR, r)):
            err(f"图书馆入口登记了不存在的主题文件: {r}——"
                "读者按入口找不到依据（登记与实际不一致）", "library/README.adoc")
    for a in sorted(actual - registered):
        err(f"图书馆存在未登记的主题文件: {a}——"
            "未登记即不会被读者发现，依据实际不可达（写文件与登记是同一个动作）",
            "library/README.adoc")
    # 下限补丁（已知局限性）：`LIBRARY_TOPICS` 只保证"这几个主题必须有"，不表达"应有哪些
    # 主题"——主题集合的完整来源仍是入口登记表（上一步已双向核对）。故"某主题该不该有、
    # 有没有被悄悄漏掉"属语义判断，交人/子 agent 复核；此处不做也不假装做。
    for t in LIBRARY_TOPICS:
        if t not in actual:
            err(f"图书馆缺少主题文件: {t}", "library/README.adoc")

    # 3) 逐字引文锚点：依据不得只剩名称
    texts = {}
    for f in sorted(actual):
        with open(os.path.join(LIBRARY_DIR, f), encoding="utf-8") as fh:
            texts[f] = fh.read()
    blob = "\n".join(texts.values())
    missing = [q for q in LIBRARY_QUOTE_ANCHORS if q not in blob]
    if missing:
        err(f"图书馆缺失逐字引文锚点 {missing}——依据被压成名称后将无从核对"
            "（判据：所引标准的关键片段须能在馆内逐字找到）",
            "library/README.adoc")

    # 4) 引用可解析：馆内引用按仓库根基准解析（悬空引用 = 依据链断在这里）
    for f in sorted(actual) + ["README.adoc"]:
        path = os.path.join(LIBRARY_DIR, f)
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
        rel = f"library/{f}"
        for j, line in enumerate(lines, 1):
            # 反引号写法：`specs/...`（按仓库根解析；`library/...` 同基准）。
            # **也收根级文件名写法**（`AGENTS.adoc`、`PUBLIC.adoc`、`README.adoc` 等）：
            # 馆内很自然地会写"登记与维护说明见 `AGENTS.adoc`"，漏收即这类引用悬空
            # 无人发现（实测：把 `AGENTS.adoc` 改成不存在的名字，检查原本不报）。
            # 只认**扩展名在册**的根级文件名（下方白名单），避免把普通词当路径。
            for m in re.findall(r"`((?:(?:specs|library|specs-project-maintainer|script|"
                                r"prompts)/[^`\s]*)|(?:[A-Za-z0-9_.-]+\.(?:adoc|py|txt|md|"
                                r"yml|yaml|json|sh|bat|cmd)))`", line):
                if "/" not in m and m not in _LIB_ROOT_FILES:
                    continue                   # 非根级文件名白名单内 → 当普通词，不核
                if _is_placeholder_ref(m):
                    continue
                _check_library_target(m, f"图书馆内的引用 `{m}`", rel, j)
            # link: 写法：**与反引号同一基准**（见 _lib_resolve）。
            # 馆内 link: 很自然会写根级名（`link:AGENTS_COMMON.adoc[]`、`link:CHANGELOG.adoc[]`），
            # 原实现只按"本文件所在目录"解析 → 同一句引用两种写法结论相反：
            # 文件存在时 link: 形态误报（解析成 library/xxx，不存在）、文件缺失时不报（漏报）。
            for raw in re.findall(r"\blink:([^\[]+)\[", line):
                target = raw.strip()
                if not target or target.startswith("#"):
                    continue
                if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", target):
                    continue
                if target.startswith("/"):
                    err(f"图书馆内的链接 link:{target}[] 是根绝对路径——"
                        "馆内引用按仓库根基准的相对写法书写，不用根绝对路径", rel, j)
                    continue
                _check_library_target(target, f"图书馆内的链接 link:{target}[]", rel, j,
                                      allow_escape=True)
    phase_done()


def _split_adoc_sections(text: str):
    """把一份 .adoc 文本按**二级节**切成 `[(节标题, 节正文含标题行), …]`。

    只认同级 `== ` 标题；`===` 及更深层归入所属二级节正文（本函数只用于"按节取
    表格/清单区"这类粗粒度定位，不解析完整文档树）。代码块（`----` 定界）内的
    伪标题不计入——否则块内示例会把节切碎、定位错段。
    """
    lines = text.split("\n")
    sections = []
    cur_title, cur_lines, in_block = None, [], False
    for line in lines:
        if line.strip() == "----":
            in_block = not in_block
        is_head = (not in_block) and re.match(r"^==\s+\S", line)
        if is_head:
            if cur_title is not None:
                sections.append((cur_title, "\n".join(cur_lines)))
            cur_title, cur_lines = line[2:].strip(), [line]
        elif cur_title is not None:
            cur_lines.append(line)
    if cur_title is not None:
        sections.append((cur_title, "\n".join(cur_lines)))
    return sections


def _names_in_zone(zone_body: str, rel: str) -> bool:
    """某节区里是否**以表格行**点名了 `rel`（行锚 `|` + 该行内任一点名形式）。

    用途：区分"在「入口清单」表里"（= 该文件确在覆盖面内）与"在正文/反向举例段被
    提一句"（= 说明性提及）。只靠 `rel in 全文` 判"在清单里"会把正文提及也算进去，
    "某入口被悄悄移出表格"这类改动因此不会被拦下。

    **点名形式**取表格行内任一种（这是"内容在不在表里"这一件判据，不该绑死某一种
    排版）：反引号（`` | `INSTALL.adoc` | ... ``）、`link:` 文本（`| link:x[INSTALL.adoc] |`）、
    裸文件名（`| INSTALL.adoc |`）。历史缺陷：原实现只认"反引号 + 文件名字面"，于是
    把同一格改成 AsciiDoc 惯用的 `link:` 文本写法（表格结构、所在节、覆盖面均未变，
    纯排版）后，**明明列在表里却报"未列进表"**——判据把"行的位置"与"文件名的排版"
    混成了一件。
    """
    # **限定在"文件"这一列**（表格第 2 格）：表格是 `| 入口 | 文件 | 说明`，
    # 若只在**说明列**里顺带提到某文件（如"见 `AGENTS.adoc`（另见 INSTALL.adoc 的说明）"），
    # 那不是"它被列进了清单"——按"整行任一点名"判定会把说明列的提及也算命中（实测：
    # 把 `INSTALL.adoc` 那行改成"文件列写别的、说明列提一句 INSTALL.adoc"，检查不报）。
    # 故取"第一个 `|` 之后、**第二个 `|` 之前**"这一段（= 文件列）来判。
    for line in zone_body.split("\n"):
        if not line.startswith("|"):
            continue
        for cell in line.split("|")[1:]:
            c = cell.strip()
            # 该格须**本身就是这个文件名的点名**（允许包裹反引号、或 `link:xxx[]` 文本形态、
            # 或裸文件名），而不是"说明句里顺带提到它"——判据是"格内去掉点名后无实质剩余"。
            probe = c
            probe = re.sub(r"`\s*" + re.escape(rel) + r"\s*`", "", probe)
            probe = re.sub(r"link:\S*?\[" + re.escape(rel) + r"\]", "", probe)
            probe = re.sub(r"\b" + re.escape(rel) + r"\b", "", probe)
            if not c or probe == c:
                continue
            rest = probe
            # 去掉纯排版残留（包裹括号、`link:` 空壳、反引号、空白、顿号/逗号等连接符）
            rest = re.sub(r"link:\S*?\[\s*\]", "", rest)
            rest = rest.strip(" \t`（）()［］[]·、,，,。;；:：")
            if not rest:
                return True
    return False


def check_public_content_coverage():
    """『公共内容覆盖面防线』：公共内容的入口清单须完整、且与实际文件一致。

    背景：公共内容此前只有一句口头定义（"`AGENTS_COMMON.adoc` + `specs/`"），而
    `INSTALL.adoc`（接入时读）、`prompts/_common.txt`（AI 以纯文本读取公共片段）与
    `script/clean_tmp.py`（随规范分发的通用工具）**同样会被引用方取到**——覆盖面界定
    不清的后果是双向的：机械检查漏掉半个公共内容（这些文件的死链无人拦），而"自足"
    要求又被误加到只对维护方成立的文件上（误报）；维护方自己也会按错的口径判断
    "加一条规则会不会改变别人的行为"。

    故把清单固化成 link:PUBLIC.adoc[]（公共内容入口索引，维护方内容），本检查钉住
    它的确定项：
      * `PUBLIC.adoc` 存在，且被本仓库项目规范入口 `AGENTS.adoc` 登记（未被登记即
        维护方读不到它，清单等于没有）；
      * 清单里以反引号点名的路径**真实存在**（改名/删除后须同步清单，否则覆盖面
        界定与实际不符）；
      * 公共内容的两个公开入口（`INSTALL.adoc`、`AGENTS_COMMON.adoc`）**都列进
        「入口清单」表**（漏一个即半个公共内容不在覆盖面内；**表**才是覆盖面的定义处
        ——只靠"全文里出现过"判定，会把正文里提一句也算命中，"某入口被移出表格"就
        不会被发现）。

    "某文件到底算不算公共内容"属判定，交人/子 agent 复核承担（清单本身可被修改，
    但修改要过归类举证）。
    """
    phase("公共内容覆盖面检查（入口清单与实际一致）")
    if not os.path.isfile(PUBLIC_FILE):
        err("缺少公共内容入口索引 PUBLIC.adoc——"
            "公共内容有多个公开入口（安装文档、通用规范入口 + specs/、公共片段、"
            "随规范分发的工具），没有清单则覆盖面界不清：检查会漏掉半个公共内容、"
            "自足要求会被误加到只对维护方成立的文件上（见 AGENTS.adoc「校验范围」）",
            "PUBLIC.adoc")
        phase_done()
        return
    with open(PUBLIC_FILE, encoding="utf-8") as fh:
        listing = fh.read()
    with open(PROJECT_FILE, encoding="utf-8") as fh:
        project_entry = fh.read()
    if "PUBLIC.adoc" not in project_entry:
        err("公共内容入口索引未在本仓库项目规范入口（AGENTS.adoc）登记——"
            "维护方无从知道公共内容有哪些入口", "AGENTS.adoc")
    # 两个公开入口须**列进「入口清单」表**：`rel not in listing` 判的是**全文**，
    # 正文里提一句（如"'为什么需要本索引'里举例说 INSTALL.adoc 也会被读到"）同样命中，
    # 于是"某入口被移出表格、只剩正文提到"这种改动**不会被发现**——而表格才是覆盖面
    # 的定义处（实测：把 `INSTALL.adoc` 那行从表里删掉、只在正文保留一句 `INSTALL.adoc`，
    # 检查仍全绿）。故本条须按**表格区**判定，与下面按节切的核对口径一致。
    sections_pre = _split_adoc_sections(listing)
    list_bodies = [b for t, b in sections_pre if "入口清单" in t]
    for rel in ("INSTALL.adoc", "AGENTS_COMMON.adoc"):
        if rel not in listing:
            err(f"公共内容入口清单未列出 {rel}——"
                "漏一个入口即半个公共内容不在覆盖面内"
                "（自足检查漏的是它的死链）", "PUBLIC.adoc")
        elif not any(_names_in_zone(b, rel) for b in list_bodies):
            err(f"公共内容入口清单未把 {rel} 列进「入口清单」表——"
                "只出现在正文/反向举例段不算在覆盖面内"
                "（覆盖面界定失效后，它的死链与自足性都无人核对）", "PUBLIC.adoc")
    # **按节切表格/清单区**判定（不再全文 re.findall + 硬编码豁免）：
    #   ① 入口清单表所在节：其中以反引号点名的路径即"公共内容入口"，须真实存在；
    #   ② "不属公共内容"那一段的反向举例：它点名的文件同样须真实存在（是**真实存在的
    #      非公共内容**，不是"随便写写"）——故一并核对，**不再靠硬编码 5 个 .adoc 名跳过**；
    #      新增任何合法反向举例都自动纳入核对，不必回来改白名单（"以豁免补判据不足"）。
    # 全文扫描的失效模式：别节/正文里出现的任意 .adoc 名（如示例、历史叙述）都会被当成
    # "清单点名"，只能靠硬编码豁免来掩盖——判据不足而非判据。
    def _names_in(section_body: str):
        return sorted(set(re.findall(r"`([A-Za-z0-9_./-]+\.(?:adoc|py|txt))`",
                                     section_body)))

    def _check_names(names, desc):
        for m in names:
            if not os.path.isfile(os.path.join(REPO_ROOT, *m.split("/"))):
                err(f"{desc}点名了不存在的文件 `{m}`——"
                    "清单与实际不一致，覆盖面界定失效", "PUBLIC.adoc")

    sections = _split_adoc_sections(listing)
    list_secs = [(t, b) for t, b in sections if "入口清单" in t]
    non_public_secs = [(t, b) for t, b in sections if "不属公共内容" in b]
    if not list_secs:
        err("PUBLIC.adoc 未找到「公共内容入口清单」节——"
            "覆盖面界定的判据失去落点（本检查按节切表格区核对，节名被改写即报错）",
            "PUBLIC.adoc")
    for t, b in list_secs:
        _check_names(_names_in(b), "公共内容入口清单")
    for t, b in non_public_secs:
        _check_names(_names_in(b), "「不属公共内容」一段")
    phase_done()


def check_config_class_guard():
    """『配置类不写逻辑防线』：配置类只保持 POJO 的基本功能，逻辑下沉到 utils/service。

    背景（本项目已发生多次的真实失效）：`@ConfigurationProperties` 一类承载配置的类被写成
    "顺手的服务"——在配置类里取默认值、做条件判断、拼装派生值，于是配置项的实际行为分散在
    配置类中，既看不见也测不到。规则来自用户的硬性要求：**配置类不得含任何逻辑，任何情况
    都不允许**；这不是某个技术栈的偏好，而是与各家公开规范一致的跨语言约定（Spring Boot
    Externalized Configuration 把配置类定义为绑定配置的 holder；Google Java Style Guide
    3.4.2 把 POJO 定义为"只有行为、没有逻辑"的数据持有者；阿里巴巴 Java 开发手册的
    POJO 类约定）。故本条**跨语言**收在通用编码规范，并按技术栈补识别特征。

    本防线钉住**四处要点**（提示词/README 同步的理由见 `check_npc_merge_guard`）：
      * **通用层条文**：`specs/general/coding.adoc`「类设计」须有「配置类不写逻辑」条，
        含"任何情况都不允许"（防被降级成建议）与"识别特征：以 Config/Properties 等命名"；
      * **判定标准可执行**：同条须给出可逐条核对的形态（条件分支/循环、计算与对外访问、
        `@Bean` 装配形态），否则只剩一句口号、无法判定；
      * **Java/Spring 识别特征**：`@ConfigurationProperties` 与 `@Configuration` 须被点名
        （只按类名识别会漏掉命名不规范的配置类，而 lombok 访问器注解的类此前只覆盖了
        纯数据结构类一侧）；
      * **公开说明同步**：`README.adoc` 的目录说明须让读者知道这条存在（漏了这层，读者
        按 README 学习时根本不知道有这条规则）。

    只钉"要求文本仍在且落在该落点"——"某个具体配置类有没有夹带逻辑"属引用方项目代码，
    本仓库看不到，交人/子 agent 复核承担。
    """
    phase("配置类不写逻辑防线检查")
    # (a)(b) 通用层条文 + 判定标准
    rel_coding = os.path.relpath(CODING_FILE, REPO_ROOT).replace("\\", "/")
    if not os.path.isfile(CODING_FILE):
        err(f"缺少文件 {rel_coding}——『配置类不写逻辑』的通用层落点丢失"
            "（该条跨语言，须收在通用编码规范而非某一技术栈）", rel_coding)
    else:
        text = open(CODING_FILE, encoding="utf-8").read()
        for keys, desc in (
            (("配置类不写逻辑", "任何情况都不允许", "ConfigurationProperties"),
             "条文：须有『配置类不写逻辑』条、写明『任何情况都不允许』（无例外），"
             "并点名 `@ConfigurationProperties` 一类承载配置的类"),
            (("POJO", "工具类或服务"),
             "边界与去向：须写明配置类只保持 POJO 的基本功能、逻辑下沉到工具类或服务"
             "（不写去向则逻辑无处安放，执行者只能塞回去）"),
            (("判定标准", "条件分支", "对外部对象"),
             "判定标准：须给出可逐条核对的形态（条件分支/循环、计算与对外访问、"
             "`@Bean` 装配形态），否则只剩一句口号、无法判定"),
            (("存量处理", "随动迁移"),
             "存量边界：该条严于框架常规用法（Spring 官方允许配置类里放派生 getter），"
             "须指向「规范变更的存量处理」（随动迁移、不发动全库改造），"
             "否则等于静默推翻引用方既有做法"),
            (("识别特征", "Config", "Properties", "Options", "Settings"),
             "识别特征：须按 Config/Properties/Options/Settings 等命名识别，"
             "否则命名不规范的配置类会被漏过"),
        ):
            missing = [k for k in keys if k not in text]
            if missing:
                err(f"配置类不写逻辑防线被破坏：{rel_coding} 缺失要点 {missing}——{desc}；"
                    "该条是用户明确要求的硬性约定（无例外），不得删除、不得降级为建议",
                    rel_coding)
    # (c) 技术栈识别特征：Java / Spring 两侧
    for path, keys, desc in (
        (JAVA_STACK_FILE,
         ("配置类识别特征", "@ConfigurationProperties", "不得含任何逻辑"),
         "Java 栈文件须补『标注 `@ConfigurationProperties` 的类一律属配置类』的识别特征"
         "（只按类名识别会漏掉命名不规范的配置类）"),
        (SPRING_STACK_FILE,
         ("配置类不写逻辑", "@Configuration", "工具类或 Service", "判定标准",
          "边界", "严于", "存量处理"),
         "Spring 栈文件须在「配置」节点名 `@ConfigurationProperties` 与 `@Configuration`"
         "两类配置类、给出判定标准，并写明与框架既有做法的边界（该条严于 Spring 常规用法、"
         "存量随动迁移）——否则拿'官方本来允许'当豁免或用它推翻引用方既有做法"),
    ):
        rel = os.path.relpath(path, REPO_ROOT).replace("\\", "/")
        if not os.path.isfile(path):
            err(f"缺少技术栈文件 {rel}——『配置类不写逻辑』的技术栈落点丢失", rel)
            continue
        text = open(path, encoding="utf-8").read()
        missing = [k for k in keys if k not in text]
        if missing:
            err(f"配置类不写逻辑防线被破坏：{rel} 缺失要点 {missing}——{desc}", rel)
    # (d) 公开说明同步（README 的目录说明）
    rel_readme = os.path.relpath(README_FILE, REPO_ROOT).replace("\\", "/")
    if os.path.isfile(README_FILE) and "配置类不写逻辑" not in open(
            README_FILE, encoding="utf-8").read():
        err(f"{rel_readme} 的目录说明未同步『配置类不写逻辑』——"
            "本条新增了通用层条文，读者按 README 学习时无从知道有这条规则",
            rel_readme)
    phase_done()


def check_prompts_primary():
    """『提示词主侧重与优先级防线』：侧重方向与分级规则不得被删或降级。

    背景：提示词的**侧重点是最核心、方向性的内容**——后续所有操作与要求都依据它，
    方向错了后面全做错。故提示词显式标注「主侧重（方向前提）」并按业界共识
    （RFC 2119 / RFC 8174、ISO/IEC Directives Part 2）引入 L1/L2/L3 优先级，指明
    哪里是重点。本检查机械钉住（调整/去重不得让它们消失或降级）：

      * `PROMPTS.adoc` 登记表仍标注每个提示词的**主侧重**（`| **主侧重** | 主侧重片段 `primary` …`）；
      * 每个提示词代码块内仍注入 `primary`（主侧重）与 `priority-rules`（优先级）片段；
      * 公共片段 `priority-rules` 仍含 L1/L2/L3 三级关键字与 RFC 2119 / ISO 依据；
      * 侧重点与登记表双向一致（防两个提示词的侧重被复制成同一个 = 方向混用）。

    只钉"存在性与一致性"，不改写内容——语义是否被削弱仍由人/子 agent 复核承担。
    """
    phase("提示词主侧重与优先级防线检查")
    rel_prompts = os.path.relpath(PROMPTS_FILE, REPO_ROOT).replace("\\", "/")

    if not os.path.isfile(PROMPTS_FILE):
        err(f"缺少提示词登记入口 {rel_prompts}——提示词的主侧重与优先级无处登记",
            rel_prompts)
        phase_done()
        return
    with open(PROMPTS_FILE, encoding="utf-8") as fh:
        registry_text = fh.read()

    # 登记表须用「主侧重片段 primary」明确标出侧重列（防登记表被改成无方向信息的清单）
    if "主侧重片段 `primary`" not in registry_text:
        err(f"提示词登记表未标注主侧重（缺少『主侧重片段 `primary`』）——"
            "侧重点属方向性内容，登记时不得省略", rel_prompts)

    registered = {}
    for name in PRIMARY_ADOC.findall(registry_text):
        registered[_normalize_primary(name)] = True

    files = _iter_prompt_files()
    if not files:
        err("prompts/ 下未找到任何任务提示词文档（除 `_` 前缀公共片段外）",
            "prompts/")

    primaries = []
    for f in files:
        rel = os.path.relpath(f, REPO_ROOT).replace("\\", "/")
        with open(f, encoding="utf-8") as fh:
            text = fh.read()
        # 1) 侧重方向须显式声明（放在正文最前，含"方向"字样）
        m = PRIMARY_LINE.search(text)
        if not m:
            err("提示词未显式声明『主侧重（方向前提）』——侧重点是最核心、方向性的内容，"
                "不得省去（须形如 `**主侧重（…）**：**<侧重>**——…方向…`）", rel)
            primary = None
        else:
            primary = m.group(1).strip()
            primaries.append(_normalize_primary(primary))
            # 正文说明段的侧重值须与方向性声明一致（防两处侧重写成两个＝方向自相矛盾）
            for other in PRIMARY_ANY.findall(text):
                if _normalize_primary(other) != _normalize_primary(primary) \
                        and _normalize_primary(other) != "本任务唯一主侧重":
                    err(f"提示词内主侧重写法不一致（『{primary}』与『{other.strip()}』）——"
                        "侧重须独此一个方向、不得自相矛盾", rel)
        # 2) 登记表须登记该提示词的侧重，且与正文一致（防同名/防侧重被复制混用）
        if primary is not None and _normalize_primary(primary) not in registered:
            err(f"提示词主侧重『{primary}』未在 {rel_prompts} 登记表中标注"
                "（登记表与正文须一致）", rel_prompts)
        # 3) 代码块内须注入 primary 与 priority-rules 两个公共片段
        for tag in ("primary", "priority-rules"):
            if f"include::_common.txt[tag={tag}]" not in text:
                err(f"提示词代码块未注入公共片段 `{tag}`——"
                    f"{'主侧重（方向）' if tag == 'primary' else '优先级规则'}缺失，"
                    "AI 无法据此判断重点", rel)

    # 4) 侧重方向不得雷同：两个提示词侧重不同（review=检查修复、refactor=重构），
    #    复制成同一个即方向混用。判定用**实际读到的侧重集合**，而非登记表条目数
    #    （登记表有两行、侧重却写成同一个时，条数相同但方向已混用）。
    if len(set(primaries)) < len(primaries):
        err(f"提示词主侧重出现重复：{sorted(set(primaries))}——"
            "各提示词侧重不同、须独立声明，复制成同一个即方向混用", rel_prompts)

    # 5) 公共片段 priority-rules 须仍在，且含三级分级与业界依据
    rel_common = os.path.relpath(COMMON_PROMPT_FILE, REPO_ROOT).replace("\\", "/")
    if not os.path.isfile(COMMON_PROMPT_FILE):
        err(f"缺少提示词公共片段 {rel_common}——优先级规则（L1/L2/L3）无处定义", rel_common)
    else:
        with open(COMMON_PROMPT_FILE, encoding="utf-8") as fh:
            common = fh.read()
        if "tag=priority-rules" not in common.replace("::", "=") and "tag::priority-rules" not in common:
            err(f"公共片段 {rel_common} 缺少 `priority-rules` 片段——"
                "提示词无法引入业界共识的优先级规则", rel_common)
        else:
            block = common.split("tag::priority-rules[]", 1)[-1].split("end::priority-rules[]", 1)[0]
            for level in ("L1 强制", "L2 建议", "L3 允许"):
                if level not in block:
                    err(f"公共片段 `priority-rules` 缺失分级定义『{level}』——"
                        "优先级被删/降级后 AI 无法判断哪里是重点", rel_common)
            for level, terms in PRIORITY_TERMS.items():
                if not any(t in block for t in terms):
                    err(f"公共片段 `priority-rules` 缺失 {level} 的判定用语（{'/'.join(terms)}）", rel_common)
            if "RFC 2119" not in block or "ISO" not in block:
                err("公共片段 `priority-rules` 未给业界共识依据（RFC 2119 / ISO）——"
                    "提示词要求按业界共识加载优先级规则，依据须保留", rel_common)
            if "不可降级" not in block:
                err("公共片段 `priority-rules` 缺失『不可降级』要求——"
                    "L1 须不可协商、不得被降级", rel_common)
    phase_done()


def check_env_marker_guard():
    """『环境标志与专用口径防线』：环境专用口径不得脱离标志、也不得漏掉中性口径。

    背景：任务提示词会被**未知项目**复制执行，但执行环境差异很大（本地人工 / CI 流水线 /
    CNB 平台 NPC 唤起）。把"某个环境才成立的做法"当成通用要求写进提示词，会让其它环境
    照着做而失败（本仓库实证：同一份提示词在两个环境里的工作区、默认分支、包管理器可用
    性都不同）。故新增"环境专用口径"必须**挂在可实测的标志上**、并**保留未命中时的中性
    口径**；"标志存在"也不能靠印象，须实际执行命令核对。本防线钉住三件确定性的事：

      * 公共片段里 `env-guard` 片段仍在，且仍写明标志（`printenv CNB_EVENT`）、
        触发条件（含 `@<Agent名>`）与**中性口径**；
      * 每个任务提示词代码块仍 `include` 该片段（否则环境判断不会被执行）；
      * 提示词登记入口 `PROMPTS.adoc` 仍登记该片段的标志——**登记处即本文件**，
        新增环境专用口径而不登记，后来者无从知道它何时生效。

    只钉"存在性与登记"，片段措辞的语义强弱仍由人/子 agent 复核承担。
    """
    phase("环境标志与专用口径防线检查")
    rel_common = os.path.relpath(COMMON_PROMPT_FILE, REPO_ROOT).replace("\\", "/")
    if not os.path.isfile(COMMON_PROMPT_FILE):
        err(f"缺少提示词公共片段 {rel_common}——环境标志与专用口径无处承载", rel_common)
        phase_done()
        return
    common = open(COMMON_PROMPT_FILE, encoding="utf-8").read()
    if "tag::env-guard[]" not in common.replace("::", "=") and "tag::env-guard[]" not in common:
        err(f"公共片段 {rel_common} 缺少 `env-guard`——环境专用口径失去开关与中性口径", rel_common)
    else:
        block = common.split("tag::env-guard[]", 1)[-1].split("end::env-guard[]", 1)[0]
        for key, desc in (("printenv", "标志须是可实测的命令，不得只写‘某环境’这类无法判定的描述"),
                          ("@<Agent名>", "标志的触发条件（NPC 唤起评论）须写清"),
                          ("中性口径", "未命中标志时的口径须写清，防环境专用做法被当通用要求")):
            if key not in block:
                err(f"公共片段 `env-guard` 缺失『{key}』——{desc}", rel_common)
    rel_prompts = os.path.relpath(PROMPTS_FILE, REPO_ROOT).replace("\\", "/")
    if not os.path.isfile(PROMPTS_FILE) or "env-guard" not in open(
            PROMPTS_FILE, encoding="utf-8").read():
        err(f"{rel_prompts} 未登记 `env-guard` 及其标志——新增环境专用口径须在登记处写明"
            "何时生效，否则后来者无从判断", rel_prompts)
    for f in _iter_prompt_files():
        rel = os.path.relpath(f, REPO_ROOT).replace("\\", "/")
        if "include::_common.txt[tag=env-guard]" not in open(f, encoding="utf-8").read():
            err(f"提示词 {rel} 未注入公共片段 `env-guard`——"
                "环境判断不会被执行（环境专用口径会在错误的环境里生效）", rel)
    phase_done()


def check_npc_merge_guard():
    """『NPC 禁合并防线』：NPC/CI 执行者不得合并、且不因人工授权豁免的要点不得被删。

    背景（一条**"用户明确要求也不照做"**的硬约束，最容易被"顺手满足用户"的惯性冲掉）：
    CNB 平台上的 NPC（CI/CD 环境里被评论唤起的 agent）**严禁合并合并请求**，**即使人工
    明确要求或直接授权也必须拒绝**。本项目实证反例：曾出现"AI 在对话中被直接授权后实际
    执行了合并"——**授权被当成豁免**，自动化执行者替人承担了不可逆且合规相关的动作。
    故把这条的服务侧要求与判定标准钉在公共内容 `specs/platform/cnb.adoc`，并在会被未知
    项目复制执行的提示词公共片段 `delivery` 里同口径落一条（`prompts/_common.txt`）。

    本防线钉住**七处要点**（每条须同时命中多处要素，否则别处一句同名字样即可假绿——与
    `check_delegation_guard` / `check_checklist_guard` 同口径）：(a) 主体禁令（CNB NPC
    严禁合并）；(b) **无豁免**（人工要求/直授也必须拒绝，含"授权不免除该禁令"）；(c)
    **判定标准**（可逐条核对：执行了合并动作 / 以授权为由豁免 / 转交他人顶替）；(d)
    **边界**（只禁合并——推送分支/解决分支内冲突/同步目标分支不算合并，不误伤「冲突处理」）；
    (e) **同文件既有规则不得被新节顶掉**（「分支与合并请求统一」「冲突处理」两节与其判据
    都须仍在——本轮实测犯过：新增节点把「冲突处理」整段替换掉，规则凭空消失而其余检查
    全绿）；(f) 提示词公共片段 `delivery` 的同口径 L1 条；(g) 公开提示词入口 `PROMPTS.adoc`
    的公共约定同步（提示词会被未知项目复制执行，漏了这层则复制出去的那份没有这条）。

    只钉"要求文本仍在"——"某次是否真的执行了合并"属运行时行为（平台操作记录/评论实际
    内容），机械无法判定，交人/子 agent 复核；但"要求被抽掉/被降级成建议"必须拦住。
    """
    phase("NPC 禁合并防线检查")
    # (a)-(d) 公共内容侧：specs/platform/cnb.adoc
    rel = "specs/platform/cnb.adoc"
    path = os.path.join(REPO_ROOT, *rel.split("/"))
    if not os.path.isfile(path):
        err(f"缺少文件 {rel}——『NPC 禁合并』要求无处承载（平台层规范缺失）", rel)
    else:
        text = open(path, encoding="utf-8").read()
        for keys, desc in (
            (("合并请求的合并主体", "NPC 禁合并", "严禁合并"),
             "主体禁令：CNB NPC/CI 执行者一律不得合并合并请求（须有节名与禁令本身）"),
            (("人工要求", "直接授权", "必须拒绝", "授权不免除"),
             "无豁免：人工明确要求/直接授权也必须拒绝，且写明『授权不免除该禁令』"),
            (("判定标准", "合并动作", "豁免", "顶替"),
             "判定标准：须给出可逐条核对的违规形态（执行了合并/以授权为由豁免/转交他人顶替），"
             "否则只剩一句口号、无法判定"),
            (("不是合并", "解决冲突", "同步目标分支"),
             "边界：明确『推送分支/解决分支内冲突/同步目标分支都不是合并』，"
             "避免与「冲突处理」节的自动解决冲突自相矛盾、也不误伤合法操作"),
            (("== 分支与合并请求统一", "只能修改同一个分支"),
             "同文件既有规则不得被新节顶掉（本轮实测犯过：新增节点把「冲突处理」整段"
             "替换掉，规则凭空消失而 check_specs.py 全绿——文件只是变短、无引用悬空）："
             "「分支与合并请求统一」须在且含『只能修改同一个分支』"),
            (("== 冲突处理", "自动解决冲突"),
             "同文件既有规则不得被新节顶掉：「冲突处理」须在且含『自动解决冲突』"),
        ):
            missing = [k for k in keys if k not in text]
            if missing:
                err(f"NPC 禁合并防线被破坏：{rel} 缺失要点 {missing}——{desc}；"
                    "本条是『用户明确要求也不照做』的唯一一类操作，最易被『顺手满足用户』冲掉，"
                    "不得删除、不得降级为建议（L1）", rel)
    # (e) 提示词公共片段：prompts/_common.txt 的 delivery 片段
    rel_common = os.path.relpath(COMMON_PROMPT_FILE, REPO_ROOT).replace("\\", "/")
    if not os.path.isfile(COMMON_PROMPT_FILE):
        err(f"缺少提示词公共片段 {rel_common}——『合并一律不做』无处承载", rel_common)
    else:
        common = open(COMMON_PROMPT_FILE, encoding="utf-8").read()
        block = common.split("tag::delivery[]", 1)[-1].split("end::delivery[]", 1)[0] \
            if "tag::delivery[]" in common else ""
        for keys, desc in (
            (("合并一律不做", "无环境区分"),
             "公共片段 `delivery` 须含『合并一律不做（L1，无环境区分）』一条"),
            (("直接授权", "也必须拒绝", "授权不免除"),
             "公共片段须写明人工直授也必须拒绝、授权不免除（提示词会被复制到未知项目执行）"),
        ):
            missing = [k for k in keys if k not in block]
            if missing:
                err(f"NPC 禁合并防线被破坏：{rel_common} 的 `delivery` 片段缺失要点 {missing}——"
                    f"{desc}；提示词会被未知项目复制执行，漏了这层则复制出去的那份没有这条禁令",
                    rel_common)
    # (f) 公开提示词入口：PROMPTS.adoc 的公共约定
    rel_prompts = os.path.relpath(PROMPTS_FILE, REPO_ROOT).replace("\\", "/")
    if not os.path.isfile(PROMPTS_FILE):
        err(f"缺少公开提示词入口 {rel_prompts}——公共约定无处登记", rel_prompts)
    elif "合并一律不做" not in open(PROMPTS_FILE, encoding="utf-8").read():
        err(f"{rel_prompts} 的公共约定未同步『合并一律不做（L1）』——"
            "登记处与实际口径不一致，后来者按登记处读会漏掉这条禁令", rel_prompts)
    phase_done()


def main(argv=None) -> int:
    """命令行入口：解析参数、顺序执行全部检查、汇总错误并返回退出码。

    参数：`-v/--verbose` 打开逐文件进度日志（默认只打阶段级进度与最终结论）。
    """
    global VERBOSE
    parser = argparse.ArgumentParser(
        description="本规范集合的完整性机械校验（引用/链接/节名/栈登记/调度器/私有约定/"
                    "历史来源/INSTALL 模板/文档注水/git mv/要点防线/规范准入/自检/来源/任务生命周期/"
                    "换行符/Java 测试类命名/公共内容不得声明机械防线/图书馆/公共内容覆盖面/"
                    "环境标志与专用口径/配置类不写逻辑/CI-CD 与平台协作 + AsciiDoc 语法）")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="输出逐文件进度（默认静默，仅打印阶段进度与错误清单）")
    args = parser.parse_args(argv)
    VERBOSE = args.verbose

    log(f"检查根目录: {REPO_ROOT}")
    log(f"共发现 {len(collect_adoc_files())} 个 .adoc 文件")
    print()

    check_refs_exist()
    check_link_refs()
    check_section_refs()
    check_stack_consistency()
    check_dispatcher_registry()
    check_forbidden_patterns()
    check_historical_notes()
    check_install_codeblock()
    check_filler_docs()
    check_principle_guard()
    check_priority_guard()
    check_spec_admission_guard()
    check_self_check_guard()
    check_git_mv_selfcheck()
    check_budget_guard()
    check_delegation_guard()
    check_verify_guard()
    check_lifecycle_guard()
    check_adoption_guard()
    check_ci_cd_guard()
    check_no_mechanism_claims_in_public()
    check_public_facing_docs_stay_self_contained()
    check_source_guard()
    check_line_ending_guard()
    check_java_test_naming()
    check_library_guard()
    check_public_content_coverage()
    check_prompts_primary()
    check_env_marker_guard()
    check_npc_merge_guard()
    check_config_class_guard()
    check_checklist_guard()
    check_asciidoctor_syntax()

    print()
    if errors:
        log(f"发现 {len(errors)} 个规范性问题：")
        for e in errors:
            print("  - " + e)
        return 1
    log("OK 规范检查全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

