#!/usr/bin/env python3
"""
fetch-specs.py - 把本规范集合（AGENTS_COMMON.adoc + specs/ + 任务提示词）批量取到本地副本。

定位：
  规范常部署于外网、网络可能不佳，AGENTS_COMMON.adoc「网络不佳时取本地副本」建议先把入口与其 specs/
  取到本地副本再读取。本脚本就是那个"取"的抓手：**一次运行把本次会话要用的规范全部取全**，
  目标项目无需自己拼文件清单、也无需逐条下载。

  文件清单**从入口自身解析**（解析 MANIFEST_FILE 的加载调度器里登记的 specs/... 条目），
  故新增一份规范时**不需要改本脚本**、也不会漏取。取到的副本**落到用户路径下的唯一落点**
  （见下「落点」），不在每个项目里各存一份。

  **提示词一并取**（用户口径：『我希望一键使用』）：只把规范取到本地、提示词还得回站点
  一份份点，那不叫一键。它们的清单同样来自**一处登记**——入口里指向提示词登记处
  （PROMPTS_INDEX_RE／`prompt_index_target`）那一行，登记处自己列着有哪些提示词
  （`prompt_targets`）；公共片段 `prompts/_common.txt` 不在清单里（它不是提示词），
  但缺了它提示词读不全，故随附随件走（`FOLLOWUP_FILES`）。

  **取到本地还不够，要能点名**（用户口径：『我要是能复制，我为什么还要下载下来』
  『没有命令 你不能加进去吗？就一句话的事情』）：取下来却还得打开文件、整段贴进会话，
  "取下来"没换来任何东西。故每轮在落点根下与 agent 命令位各生成一份**口令入口**
  （`<口令> <提示词名>`，名字/写形/命令位取配置 `[prompts]` 段），它把**装配好的整段**
  打给会话：`include::` 就地展开、`{主侧重}` 按该提示词自己的声明填好。入口是**脚本**、
  不抄提示词正文（抄了就是第二份，改一处必漂移），正文永远只有落点里那一份。

用法（在目标项目根目录执行，入口名随平台而异、只给脚本名即可）：
  fetch-specs                          # 取到落点（用户家目录下的 `<落点父目录>/<落点名>`，见下「落点」）
  fetch-specs --base <URL>             # 换规范来源（默认取配置 `[source].base_url`，同源镜像可用）
  fetch-specs --keep                   # 保留本地已有的非空副本（不动已取到的那一份）
  fetch-specs --force                  # 同默认（保留写法，与 --keep 相反）
  fetch-specs --list                   # 只打印将要取的文件清单，不下载
  fetch-specs --print-prompt <名>      # 装配好落点里那一份提示词并整段输出（口令入口用它；不联网、不写盘）

取回与更新口径（**本节是「怎么取、怎么更新」的真源**——公共入口 `AGENTS_COMMON.adoc`
「取规范到本地副本」只写落点那一处，其余回指本节；**同一句话不在两处各写一遍**）：
  - **先更新自身、再照新清单取全（同一轮生效）**：清单来自入口（`AGENTS_COMMON.adoc`）的调度器
    登记，而"怎么解析这份清单"是**本脚本自己**的取舍——清单解析口径改了、或新增的文件**不在旧清单
    的形态里**（新文件类型、新落点排布）时，**跑着旧脚本的那一轮只会照旧口径取**，新东西静默不进
    副本、也不报错（"看着取全了、其实少了几份"）。故每轮先取一次**远端的最新脚本自身**：与本轮
    真身（`__file__`）逐字节比较，不同就把它落地、**当场换到自己身上、自己重启，再照新脚本的清单
    口径取全**（原样参数、退出码来自重启后的那一轮，见 `hand_off_self`）——**一次运行即达成"更新
    即是更新"**，不留"下一轮才生效"的空窗（用户口径：「更新的时候，就要及时生效吧？还等下一次？」）。
    **按需中转、不留待换标记**：真身（`__file__`）可写时新版本**直接落到真身路径旁边的中转文件**
    （`_self_update_candidates`），重启换的是它、不必再经交接文件；只有**读得到真身、却换不动它**（真身
    目录只读、非属主）时才写下"待换的新版本在哪"（`hand_off_self` 消费的那个文件），**下一轮运行**
    读到即自己换、自己重启——这一步是**兜底**，不是常规路径。故**壳什么都不必做、仍是薄壳**
    （职责边界见 `specs/general/script.adoc`「跨环境脚本」）。**走文件而不是环境变量**：**子进程设
    的环境变量回不到调起它的父壳**（本仓库实证：交接当初走 `STALE_SELF_PATH`，壳那条路永远读不到、
    机制形同没有）。换不动/留不下标记时**如实警告**、不得静默（同「落点只读」那条的效力边界口径）；
    **"取最新脚本"因此是每轮必然的一步**：它不另立第二套真源、也不引入校验和——更新的判据与
    规范副本**同一条**（取回的字节与本地逐字节比较），只是对象换成了本脚本自己；
  - **一次取全**：一次运行把入口与其 `specs/`、以及提示词全部取回，调用方不必手拼逐条下载命令
    （清单从入口自身解析，见上「文件清单」）；
  - **取全这件事要核得出来**：提示词与规范、索引页**互不引用**，少一份不会有任何东西报错。
    故收尾按清单逐个核一遍（`report_prompts_missing`），缺的**报出名字并按失败计**——
    "看着取全了、其实少了几份"是本脚本最贵的一种失效形态；
  - **清单以外的附随件（索引页、提示词公共片段）也每轮核一遍**：常量 `FOLLOWUP_FILES` ＋ 执行体 `refresh_lagging_followups` 一并（**不在**清单里，不是规范副本、也不是提示词），
    而索引页列着本仓库有哪些文件、公共片段里装着提示词的公共步骤
    ——于是它与"脚本自己那一份"是**两件独立的事**：自更新只在
    **脚本变了**时才动手，脚本没变的那一轮一个字节都不写，
    索引页就会停在上一次脚本变动的那一版（人按站点找文件看到的是一份过期目录，且**没有任何
    输出**显示出它落后了）。故它按**规范副本同一条口径**办：每轮都取、按内容判、不同才落盘，
    落点与安装脚本同一处（落点根下；公共片段按它在仓库里的目录落进 `prompts/` 下）；
    **取不到不算失败**（本仓库以外的来源多半没有这些文件），网络失败只**如实警告**
    "本地那一份可能已落后"——不得静默；
  - **这一步的次序**：先认一个跑得起来的解释器 → **拉最新的本脚本** → 按**它**的清单取全 →
    最后取索引（用户口径：「更新顺序应该是 拉最新 py，执行 py，拉最新 toml 索引，拉取规范」）。
    落到 `main` 里就是那四步的先后：`--probe` 走到 `main` 早处即收工（不写盘、不换自身）→
    `update_self` 换上新版本、当轮重启 → `manifest_targets` → `refresh_lagging_followups`。
    **索引排在最后、且由已经换新的这一份自己算**：它列着什么取决于"谁在算"，用旧脚本算出来的
    索引就还是旧目录（新增/改名的文件静默不在里面）——两件事都做到，"索引与清单同步"才可核对。
  - **默认以远程为准**：每份文件按"取回的字节与本地不同才落盘"核对，远端改过就刷新，
    故**重复执行即是更新**；`--keep` 才回到"本地已有即不动"；
  - **取回失败保留本地已有的那一份**：报错并如实报失败，**不得**把本地副本删掉换成没有；
  - **退出码**：0 成功、1 有文件没取到、2 参数或前置条件错误——非 0 就别把副本当已就绪；
  - **解释器兜底**：两个平台入口按次序探测解释器（Linux/macOS 先 `python3` 再 `python`；
    Windows 先 `py` 启动器、再 `python3`、最后 `python`），取**第一个真的跑得起来的**——
    "在 PATH 上"不等于"跑得起来"（同类：`py` 启动器装上了、它默认的那个 python 3 却不在，
    这时它会报 `'py -3' is not recognized as an internal or external command`；Windows 应用商店的
    `python.exe` 是个只剩提示的垫片），探到的候选**先用 `--probe` 试跑一次这份脚本**（只到
    "这一份脚本在这个解释器底下跑起来了"为止：不打印清单、不联网取清单、不写盘、不取文件、
    不换自身、不重启），**退出码为 0 才算跑得起来**——"看起来没报错"不算：`py` 启动器在没装
    python 3 的 WinGet/Store 机器上以 49 退出、什么都没跑，而"退出码不是 127"会把这种空壳
    当成可用解释器；一处都没探到时
    **处置次序**是：**先按本平台既有的软件分发方式装一个 python 3**
    ——这是**人**的一步（或人已交互登录、能看见命令与报错的会话里 agent 的一步），入口**不得**代为安装运行时（改系统状态、要权限、对调用方不可预期）；
    **只装 python2 的发行版**（CentOS/RHEL 8 及更早、老 macOS 上 `python` 就是 python2）
    **不算"一个都没有"**——上一条的次序会取到它；
    不装运行时的替代路径是**直接读远程入口地址**——本规范在网络上就是这套文件；
    **不建议**改用 `curl … | python3 -`：**它同样要 python**。

环境变量：
  AGENT_SPECS_BASE   规范来源地址，等价于 --base（默认值在配置 `[source].base_url`）
  STALE_SELF_PATH    已撤掉的旧形态（**留作反例，不再使用**）：本轮取到的新版本路径当时靠环境
                     变量交给调用方的壳——**子进程设的环境变量回不到调起它的父壳**（本仓库实证：
                     壳那条路永远读不到），故改成走文件：路径写在本脚本自己的路径 + `.handoff`
                     后缀的那个文件里，换不动真身时由下一次运行自己读、自己换、自己重启
                     （见下「交接文件」）。

落点（**只有一处**：用户家目录下的 `<落点父目录>/<落点名>`＝`CACHE_HOME_DIR`/`CACHE_APP_DIR`）：
  **那几处取值与其余运行期取值全在配置里**（`script/specs-config.toml` 的 `[landing]` 等段，
  由同目录的 `pathconfig.py` 读入）——本脚本与判据侧取的是同一份，改落点只改配置一处；
  本节只讲**本脚本自己的取舍**（为什么不按平台换、为什么只进不出），不复述那几个字面值。
  - 落点**不按平台取目录**：不管什么系统、什么环境都是用户家目录下的这一个路径（用户口径），
    家目录取不到时报错退出、**不静默换地方**——换落点等于让「副本在哪」变成环境相关的事实，
    入口文档写下的那一个路径就与实际的落点对不上了（公共入口「取规范到本地副本」只写这一个落点）；
  - **家目录每轮现取、取到就按它算、不写死也不缓存**（用户口径：「个人目录需要实时去读，
    不要默认路径，取到后也不要写死，每次都去拿最新的目录」）：家目录在 Windows 上**不是**
    一块写死的路径——"个人目录为了不丢数据会被整体移到别的盘/别的路径"（如"我的文档"被
    重定向到 `D:\我的文档`），而 `%USERPROFILE%` 这类**环境变量是登录时按注册表读出来设上的**，
    进程内改了注册表它也不会跟着变。故**每一轮**都按 `_user_home_dir` 现取一遍：
    先问壳（Windows 上 `SHGetKnownFolderPath`＝注册表里**当刻**的 KnownFolder 取值，随改随取），
    取不到再退回环境变量/`expanduser("~")`；**不落任何缓存**（缓存即"下次还用旧目录"，正好
    是本条要防的形态），也**不在代码里写任何一条家目录字面值**——落点每次都是由"这一轮现取到的
    家目录"算出来的；
  - 落点下按来源地址分目录（见 `cache_slot_dir`）——换过 `--base` 取到的不同来源副本互不覆盖；
    且**只进不出**：本脚本不删除落点里的任何文件（含换源留下的旧副本），要清理由人来做
    （清理属不可逆操作，见 specs/core/execution.adoc「破坏性操作」）。
  - **安装脚本自己也落这里**（见 `INSTALL_SCRIPTS`）：规范副本进来源槽，取规范脚本与它的
    平台入口落**落点根下**——跨来源共用一份，下次重装直接跑落点里的入口，
    不必再手工下载一遍（用户口径：下载的文件一律只落这一个地方）。
  - **交接文件也落在脚本旁边**（`<脚本路径>.handoff`，见 `hand_off_self`）：它记着"待换的新版本
    在哪"，是**本脚本自己的状态**、不是规范副本；换完即删，且不参与落点的只读收紧那一套
    （它就在本脚本旁边，跟着脚本自己的可写性走）。**它只在换不动真身时才出现**——真身可写时
    新版本直接落在真身旁、同一轮就换上，不写标记（见上「取回与更新口径」）；
  - **落点取完即只读**（见 `_make_read_only`）：下载完把落点里的**目录去掉写位、文件
    只留读位**（取值即 `_READ_ONLY_DIR_MODE`/`_READ_ONLY_FILE_MODE`）——规范副本是**只读的
    参考物**，不是可改的工作区；只读让"落点被就地改过"从"看不出来"变成"当场失败"
    （可读不可写由本机文件系统保证，改它要显式先松权限——那一步是刻意的动作；
    **平台边界见「已知限制」**：Windows 上只有文件那一半由文件系统保证）。
    本脚本自己**按内容**判落盘，故只读**不挡更新**：内容不同时先按 `_ensure_writable`
    恢复写位再原子替换，之后重新收紧到只读（"只加不减"的例外见该函数与 `_make_read_only`）。
    **收紧失败会如实警告**（见 `_make_read_only` 的返回值与「已知限制」最后一条）——不得
    静默当成"落点已只读"。

  安装侧对落点的说明与"取回/更新"口径（用户读到的落点描述）以公共入口 `AGENTS_COMMON.adoc`
  「取规范到本地副本」为唯一真源，本节只讲**本脚本自己的取舍**，不复述那几句。

行为与副作用：
  - 只写「落点目录」，不写项目里其他位置；
  - **默认以远程为准**：每份清单内文件都按"取回的字节与本地不同才落盘"核对，远端改过就刷新
    （安装脚本会更新，重复执行安装时须能拿到最新的一份）；取回失败时**保留本地已有的那一份**
    并如实报失败，**不得**把本地副本删掉换成没有；
  - **附随文件（索引页、提示词公共片段）同样每轮核对**（见「取回与更新口径」）：它们不在清单里，
    故不随清单走，按内容判、取不到只警告（索引页落点与安装脚本同一处，公共片段落 `prompts/` 下）；
  - `--keep` 反过来：本地已有且非空即不动（只补缺失项），要最新内容就别加它；
  - 退出码：0 成功；1 有文件没取到（清单同时打印失败项）；2 参数或前置条件错误；
  - 网络请求带超时（见 `TIMEOUT_SECONDS`）、失败重试一次；
  - **临时产物留在工作目录 `tmp/` 下**（见 `specs/core/execution.adoc`「临时产物」）：新版本
    脚本在真身与落点都不可写时中转落在这里；运行前已存在的旧副本由本脚本自己按**同一套边界**
    清掉（`_clean_self_tmp`），本轮新写的那几份留着——调用方可能还要读它们。
    **这里是唯一的例外落点**：`tmp/` 内部按用途分层（同节「tmp/ 的布局与命名」），而本节这几份
    中转副本**不建任务目录**——它们是本脚本自己的状态、名字由 `SELF_UPDATE_SUFFIX` 钉死，
    且清理由 `_clean_self_tmp` 按名字白名单做，不经人手；入口脚本一律落**落点根下**、不进 `tmp/`；
  - `--keep` 之外**不做备份**：落点是那份文件自己的位置，被改动过的副本按"以远程为准"覆盖掉
    ——**须留本地改动时用 `--keep`**；
  - 并发受限（见 `DEFAULT_WORKERS`），不把对端打满；
  - 落盘完成后把落点收紧为**只读**（`_make_read_only`；本脚本为落盘所需的最小写位由
    `_ensure_writable` 临时恢复，之后重新收紧）——落点是只读的参考物，见上「落点」。
  - **"更新自身"会重跑一次**：换上新版脚本后当轮就 `os.execv` 重启（挂 `--self-updated` 作刹车，
    见 `_restart_with`）——重启后的那一轮按新脚本的清单口径取，用户侧看到的仍是**一次运行**。
  - **口令入口每轮重写一遍**（`write_prompt_entries`）：内容是现算的，按"内容不同才落盘 + 原子替换
    + 写完收只读"同一套纪律；**可用名单不烘进文本**，由入口在运行时按落点里 `prompts/` 现算
    ——烘进去的名单在提示词增删之后就成了一份会撒谎的清单，而落点已只读、没人会去改它。
    生成与否只看"这一轮认不认得提示词那一层"（登记处取不到时不生成空壳）。

== 输出（用户口径：「显示文件下载进度及其他明细，下载完成不要关闭窗口」）
  - **开跑先交代一轮的规模**：共取几份、来源、落点、并发（一份都还没回来时，这就是唯一的
    "它在干活"的信号）；
  - **每取完一份打一行进度**（`[3/27] 刷新 specs/stack/java.adoc -- 12.3 KB（1.2s）`，
    见 `_progress`）：份数、状态（新取/刷新/未变/保留/重试/失败）、体积、耗时——**逐份**、不攒到
    收尾，故卡住时看得见卡在哪一份。体积**超过 1 KB 就换单位**（`_size`：`6921 B` 打成
    `6.9 KB`）——几十份明细排成一屏时，`4222 B`/`6921 B`/`8980 B` 这种纯字节数要人数位数
    才比得出大小，换单位后量级一眼看出；1 KB 以下仍打 `B`（`0 B` 正是要看的那一档）；
  - **收尾给总账与明细**：共取几份、用时，以及按状态分组的清单（新取/刷新/内容一致/失败）；
  - **进度与警告走 stderr、结果走 stdout**：stdout 会被调用方重定向，进度混进去就成了噪音；
  - **跑完不关窗口是入口的事、不是本脚本的事**（职责边界见 `specs/general/script.adoc`
    「跨环境脚本」）：`fetch-specs.bat` / `fetch-specs.sh` 在**自己开了（或占着）终端**时
    结束停住等一次回车，管道重定向与 CI 里照旧立刻退出——本脚本自己不探测终端、也不等输入
    （它被别的程序调起时，"等一次回车"会变成一个不返回的命令）。入口的判据只看**标准输入
    挂在终端上**（`[ -t 0 ]`）：控制终端在重定向时照样可写，拿它当判据会让重定向那条路
    挂在那里等一次回车。

安全保证：
  - **只读远端、只写落点目录内**：落点不是调用方给的路径，而是本脚本按本机用户目录算出来的
    固定位置，故不存在"借参数写到任意位置"的越界面；
  - 不删除任何既有文件（含落点目录里的多余文件）——清理属不可逆操作，由人按项目规范做；
  - **落点里的内容只由本脚本写**：落点取完即只读，**任何项目都不得改动它**
    （要改就先把权限放开——那一步刻意、可见、须自担后果）。**项目只读、不改**：项目要留
    自己的东西写进项目自己，不得往落点里塞文件、也不得改落点里的规范副本——改了就是
    改了规范正文，而公共内容须自足（见 `specs/general/source.adoc`）。

已知限制：
  - 不做时间维度的过期判断：判据是**内容**而不是时间——每份文件都先把远端内容取到内存、
    与本地逐字节比较后才决定落不落盘，故没有"本地那份看起来还新、实际已经过期"这条失效；
    代价是每次运行都要把清单内文件（含本脚本自身）取一遍；
  - `--keep` 下本地副本可能落后于远端，此时**以落点里的旧副本为读到的内容**——是否要最新
    由调用方按任务判（入口「安装与更新」的流程一律按默认的"以远程为准"走）；
  - 内容比对只看字节：远端对同一份规范做格式等价改写（如仅换行/顺序）同样会落盘刷新；
  - 只读靠**本机文件系统**：以特权身份（root/管理员）运行时权限位仍可被绕过——那是本机
    自己的信任边界，脚本在权限位这一层能保证的是"非特权调用方改不动"（同机多用户下保护落点
    不被他人改动的机制是家目录权限，属操作系统范围）；**收紧失败（只读挂载/Windows/非属主）
    时脚本照常取文件、但如实警告"有 N 处没能收紧"**——不得静默当成"落点已只读"
    （见 `_make_read_only` 的返回值与 `main` 的输出）。
  - **Windows 上只做到一半**（**平台限定，别把下面这句当全平台成立**）：
    `os.chmod` 在 Windows 上只认 `stat.S_IWRITE`（`0o200`），其语义是给**文件**打
    `FILE_ATTRIBUTE_READONLY`——**文件**因此"下载后即只读"，就地编辑/追加被拒（用户口径里
    "文件本身下载后要变成只读"那一半成立）；
    但**目录的只读位拦不住增删改名**：删除权来自**父目录**的 `DELETE_CHILD`，与目标目录
    自己的属性无关，`os.chmod(0o555)` 只是把 READONLY 属性打到目录上、API 层仍可
    `CreateFile`/`DeleteFile`。故"目录去掉写位＝**不能在其中增删改名**"这句**仅在
    POSIX（Linux/macOS）成立**，Windows 上"严禁项目改动落点"靠**规范约束**而非文件系统
    （这正是把本条 L1 写进 `AGENTS_COMMON.adoc`「取规范到本地副本」的原因之一）。
    同理，`_ensure_executable` 补的执行位在 Windows 上无对应语义（`.bat` 按关联执行，属预期）。
  - **自更新在"读不到真身"这种跑法下换不动**（非属主 / 只读挂载 / 权限）：新版本照旧落地
    （落点根下那份就是"下次运行会读到的真身"），但**本轮这份脚本改不了**，故**如实警告**
    并留下待换标记，由下一轮接上（见 `_take_over_self`）。这是本机权限边界，不是脚本能绕的
    那一层——"看着换上了、其实没换"因此在这里被明确报出来，而不是静默。
    但**落点收尾收紧留下的只读位不算这一类**：安装脚本自己也在收紧范围内（收尾整棵树收紧），
    真身带着只读位时**换之前先把写位补回来**（`_take_over_self`／`hand_off_self`），不补位
    就是每轮 `[Errno 13]` 的死循环（本仓库实测：本轮失败留标记、下一轮换的还是同一个只读
    文件）；补位由收尾收紧收回，"落点取完即只读"不因此破。
"""

import argparse
import concurrent.futures
import ctypes
import http.client
import importlib.util
import os
import re
import shutil
import stat
import sys
import threading
import time
import urllib.parse
import tomllib
import urllib.request
import uuid

# 运行期配置的落点：**先看本脚本旁边**、再看仓库里的 `script/` 下。
#
# 为什么就近优先（本仓库实测的失效形态）：薄壳与逻辑代码会被**一起取到落点根下**
# （`<落点>/fetch-specs.py`），落点里没有 `script/` 那一层——只按 `script/` 定位时，
# 从落点跑起来的那一份找不到配置、直接退出。就近优先则在两种跑法下都成立（项目里跑、
# 落点里跑），而且落点里的那份配置正是"与本脚本同一版"的那一份（预置的读取）。
CONFIG_BESIDE_SCRIPT = "specs-config.toml"
CONFIG_IN_SCRIPTS_DIR = "script/specs-config.toml"
# 读取层自己的文件名：**读配置这件事只有一份实现**（`pathconfig.py`），执行侧、判据侧、
# 落点里分发出去的那一份，走的都是它。下面按"配置在旁边"那条路把它就地加载起来
# （本脚本在落点里跑时没有 `script/` 了，只能按文件路径加载）。
PATHCONFIG_MODULE = "pathconfig.py"


def _this_file():
    """**本轮这份逻辑代码自己的路径**：`__file__` 不给时退到 `sys.argv[0]`（见下）。

    `__file__` 不是每个跑法都有——被 `exec(compile(...))` 跑起来时（`python3 - < x.py`、
    调用方自己读出来再执行这一类）整个模块里没有 `__file__`，一读就 `NameError`。
    而那正是一条**运行期**报错：它出现在离真正要说的事很远的一行（本机实测的第 395 行正是
    这么炸的，真正的成因在更早、被同一句 `NameError` 盖住了）。故这一层给一次兜底：
    `__file__` 在就用它，不在就用 `sys.argv[0]`——那正是"调用方手里这一份"。两样都没有时
    返回空串（下面的路径拼接与 `isfile` 对此都按"没有"处理，后续报错自己会说清缺什么）。
    """
    here = globals().get("__file__") or (sys.argv[0] if sys.argv else "")
    return os.path.abspath(here) if here else ""


def _config_candidates():
    """配置的两处可能落点：**本脚本旁边**优先，其次仓库的 `script/` 下（相对入口层两级）。"""
    here = os.path.dirname(_this_file())
    return (os.path.join(here, CONFIG_BESIDE_SCRIPT),
            os.path.join(os.path.dirname(here), *CONFIG_IN_SCRIPTS_DIR.split("/")))


def _module_beside(config_file, filename):
    """在 `config_file` 同处找 `filename` 并返回全路径；不在时返回 `None`。"""
    candidate = os.path.join(os.path.dirname(os.path.abspath(config_file)), filename)
    return candidate if os.path.isfile(candidate) else None


def _import_pathconfig(module_path):
    """按**文件路径**加载读取层（`pathconfig.py`），返回模块。

    为什么按文件路径加载而不是 `import`：本脚本从落点跑时，读取层就躺在它旁边，
    那里没有 `script/` 这一层、也不在 `sys.path` 上。`sys.modules` 先登记再执行——
    模块互相 import 时不会重复执行。

    **加载期间不写字节码缓存**（`sys.dont_write_bytecode`）：这一处发生在 **import 期**，
    而 `--probe` 的判据是"这个解释器跑不跑得起来"——它必须**不写盘**（入口每探一个候选
    就跑一次，探一遍不能顺手把落点改一遍）。默认开着的 `__pycache__` 会让每次 `--probe`
    都在落点根下留一份目录：落点收尾把整棵树收紧成只读之后，这一步还会静默失败
    （`OSError` 被解释器自己吞掉），"落点是只读的"从此多出一条看不见的例外。
    """
    name = os.path.splitext(PATHCONFIG_MODULE)[0]
    spec = importlib.util.spec_from_file_location(f"_{name}", module_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    saved = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = saved
    return module


def _find_pathconfig():
    """读取层（`pathconfig.py`）的落点：与**配置**同处——就近那份配置旁边优先，其次仓库 `script/`。"""
    for candidate in _config_candidates():
        if os.path.isfile(candidate):
            module = _module_beside(candidate, PATHCONFIG_MODULE)
            if module:
                return module
    return None


def _announce_install_group_missing():
    """缺"读取层/配置"时的**出路那几句**：说清缺的是整组，以及**哪一行**能把它取回来。

    为什么单列：读取层与配置是一整组分发出去的（`INSTALL_SCRIPTS`），故任何一样缺，实际
    要做的都是"把这一组取到落点根下"——而**取它这一步恰好不需要它们**（`fetch-specs.py`
    自己就能跑）。只说"缺配置"时，人要么去翻文档、要么手工造一份配置，两条都不通。
    本机实测：`fetch-specs.bat` 走到这一处报 config 找不到，读者手里那份脚本其实好好的、
    跑一次 `--no-scripts` 之外的正常取文件即可把它补回来——故这里的路必须写明。

    名字带前导下划线：本脚本里只在本模块内用的辅助函数一律是这个形状，`print_` 开头的
    公开名在这里会读成"给调用方用的输出接口"。文案是终端输出，不写 markdown 记号：
    两个星号在终端里就是两个星号，人读到的是一行带星号的句子。
    """
    print("说明: 读取层与配置是一整组随安装脚本分发的——缺任何一样，"
          "本脚本都会停在这一步。它是与它们同批取回的，故补齐的办法不是在落点里手工造一份，"
          f"而是取一次安装脚本：在本脚本所在的仓库里跑 {os.path.basename(_this_file())}，"
          "或按公共入口「安装与更新」那一节把整组重新取一遍。",
          file=sys.stderr)


def _load_pathconfig():
    """读运行期配置（`script/specs-config.toml`，随规范一起分发到落点根下）。

    读的是**同目录的 `pathconfig.py`**——那是唯一的读取实现：再在本脚本里内联一份，
    取值一旦加键/改结构，两份读取层必然各自漂移，而"改配置不改变行为"这种形态检查不出来。

    **配置或读取层缺失即报错退出、不退回脚本里写死的默认值**：退回默认值等于把配置文件
    变成可选装饰，两份来源又回来了。故这里直接抛给调用方——`main` 尚未开始，退出码按
    "参数或前置条件错误"给。
    """
    module_path = _find_pathconfig()
    if module_path is None:
        # 报"缺读取层"而不提配置，等于让人只补一样：两者只要缺一样，本脚本都跑不起来，
        # 且它们本来就在同一份分发名单里（本机实测：本轮连 config 与 pathconfig 一起齐了才通）。
        print(f"错误: 找不到运行期配置的读取层 {PATHCONFIG_MODULE}——路径与运行期取值只有"
              f" {CONFIG_BESIDE_SCRIPT} 这一处来源（读取层须与它同处）", file=sys.stderr)
        _announce_install_group_missing()
        raise SystemExit(2)
    pathconfig = _import_pathconfig(module_path)
    if pathconfig is None:
        print(f"错误: 无法加载读取层 {module_path}", file=sys.stderr)
        raise SystemExit(2)
    # 配置的落点由读取层定位（就近优先：本脚本旁边 → 仓库 `script/` 下）——定位只有一处实现
    config_path = (pathconfig.config_beside_module()
                   or pathconfig.config_path(os.path.dirname(os.path.dirname(_this_file()))))
    if not os.path.isfile(config_path):
        print(f"错误: {pathconfig.missing_config_message(CONFIG_BESIDE_SCRIPT)}", file=sys.stderr)
        _announce_install_group_missing()
        raise SystemExit(2)
    try:
        return pathconfig.load_file(config_path)
    except pathconfig.ConfigError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        raise SystemExit(2)


# 路径与运行期取值**只在配置里**（`script/specs-config.toml`，唯一真源）：落点那两层目录名、
# 来源默认地址、入口/有则取的文件清单、安装脚本名单、网络超时与并发、临时产物与交接文件后缀
# ——全都从那里读，本脚本不再各写一份（用户口径：『路径信息应该是唯一真源，不能每个地方写一份』
# 『配置的路径可以再定义』）。改动任一处只需改配置：执行侧与判据侧都经同一个读取层取值，
# 文档侧只引一句，三处不会各自漂移。
_PATHCONFIG = _load_pathconfig()
DEFAULT_BASE = _PATHCONFIG.base_url


class _GUID(ctypes.Structure):
    """Win32 `GUID`（与 `uuid.UUID` 同构的 16 字节，见 `_guid_of`）。"""
    _fields_ = (("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16), ("Data4", ctypes.c_uint8 * 8))


# 落点父目录：用户家目录下的这一层（落点只有这一个，不另按平台取目录）
CACHE_HOME_DIR = _PATHCONFIG.landing_home_dir
# 落点目录名：落点父目录下的这一层（`CACHE_HOME_DIR/CACHE_APP_DIR` 即那条用户路径）
CACHE_APP_DIR = _PATHCONFIG.landing_app_dir
# 落点那两层的**分段形式**：拼本机路径一律用它（按平台分隔符；两段各拼一次的地方
# 自然分成两份，上一轮就散在好几处）
LANDING_REL = _PATHCONFIG.landing_rel
# 落点写给人看的那一串（报错与 `--list` 里引用它）：与 `LANDING_REL` 同出一处、只是形态不同
LANDING_NAME = _PATHCONFIG.landing_name
# 入口 + 顶层说明文件；specs/ 下的文件从入口的调度器登记解析得到
MANIFEST_FILE = _PATHCONFIG.manifest_entry
OPTIONAL_FILES = _PATHCONFIG.manifest_optional
# 与本脚本同处的安装脚本：一并取到落点**根下**（不在来源槽里）——跨来源共用一份。
# 用户口径是"下载的文件一律只落这一个地方"，故下载完就不必再来第二次；
# 薄壳也一并取回：只取逻辑代码时，落点里那份没法直接跑（入口层三件事见 specs/general/script.adoc）。
INSTALL_SCRIPTS = _PATHCONFIG.install_scripts
# 其中**入口**（各平台的薄壳）：落点取的字节不带文件模式，故取完给它们补回可执行位
# （见 `_ensure_executable`）。逻辑代码**不在内**——它不是给人直接敲的命令，
# 落点里唯一的入口是入口脚本（见 specs/general/script.adoc「入口脚本须能直接执行」）。
ENTRY_SCRIPTS = _PATHCONFIG.entry_scripts
# 提示词公共片段：**任务提示词清单里只有提示词本身**（`prompts/` 下非 `_` 前缀的 `.adoc`），
# 而它们用 `include::_common.txt[tag=…]` 引这一份——故它随附随件走（见 `FOLLOWUP_FILES`）。
COMMON_PROMPT_REL = "prompts/_common.txt"
# 提示词所在的目录（`COMMON_PROMPT_REL` 与清单里的提示词都在它下面）
PROMPT_DIR = os.path.dirname(COMMON_PROMPT_REL)

# 『提示词一并取全』那几条共用的两份**本轮现算**的状态：提示词的登记处（入口里那一行）
# 与"清单里列着的提示词实际取到了哪几份"。**不按落点里的文件判在不在**：落点是跨来源共用
# 的只进不出池子，按它判会把"上一轮取到、这一轮没取到"读成"取全了"。
_PROMPTS_INDEX = None
# 登记处的正文（本轮取到的那一份）：口令入口的清单从它现算，故与它一起按轮次现取现清。
_PROMPTS_INDEX_TEXT = ""
_PROMPTS_TAKEN = set()

# 站点索引页与**提示词的公共片段**：它们**不在取回清单里**（索引页不是规范副本、
# `prompts/_common.txt` 不是任务提示词），但缺了任何一份，取到的东西都**用不起来**——
# 索引页列着本仓库有哪些文件（不跟着更新时，人按站点找文件会得到一份过期的目录）；
# 公共片段是提示词用 `include::_common.txt[tag=…]` 引的那几段，缺了它，提示词读入时
# 补不齐公共步骤（见 `PROMPTS.adoc`「访问与解析」）。
# **清单只看"该有哪些文件"、不看"怎么用它们"**：提示词是复制即用的，故提示词在清单里；
# 片段是"被别的东西引用"的，故在附随件里。取不到不算失败（本仓库以外的来源多半没有它们）。
FOLLOWUP_FILES = ("index.html", COMMON_PROMPT_REL)
# 口令入口（『就一句话的事情』）：提示词取下来之后，**点名就能跑**——写入口文件这件事不靠人手。
# 文件名主干、口令写形、落到哪些 agent 平台的命令位，全部取自配置（`[prompts]` 段，唯一真源）；
# 本脚本只留"怎么生成"这一层。入口是**脚本**（能带参数，`<口令> review` 即可），不是把提示词
# 内容抄进去的模板——抄进去等于在落点里放第二份提示词正文，改一处必漂移。
PROMPT_COMMAND_NAME = _PATHCONFIG.prompt_command_name
PROMPT_COMMAND_USAGE = _PATHCONFIG.prompt_command_usage
PROMPT_COMMAND_DIRS = _PATHCONFIG.prompt_command_dirs
# 入口文件的两套后缀：`.sh`/`.bat` 落**落点根下**（跟安装脚本同一处，`<落点>/<name>.sh <名>`），
# `.md` 落 agent 平台的**命令位**（平台按 `<name>.md` 认，YAML front matter 给一句说明）。
PROMPT_COMMAND_SHELL_NAME = PROMPT_COMMAND_NAME + ".sh"
PROMPT_COMMAND_BAT_NAME = PROMPT_COMMAND_NAME + ".bat"
PROMPT_COMMAND_AGENT_NAME = PROMPT_COMMAND_NAME + ".md"
# 口令入口（`.sh`）运行时找解释器的候选次序（空白分隔）：与取规范入口 `fetch-specs.sh` 同一条
# ——入口**不烘**生成时的 `sys.executable`，落点可被搬去另一台机器，绝对路径那时就失效了。
PROMPT_SHELL_INTERPRETERS = ("python3", "python")
# `use-prompt.bat` 的候选次序：Windows 上解释器多叫 `py`/`python3`/`python`（同
# `fetch-specs.bat` 的探测次序），三个都试、认第一个跑得起来的。
PROMPT_WINDOWS_INTERPRETERS = ("py", "python3", "python")
SPECS_REF_RE = re.compile(r"specs/[A-Za-z0-9_./-]+\.adoc")
# 提示词的**登记处**：入口文档里那一行指向它（如 `PROMPTS.adoc`），任务提示词的清单从它解析
# （该文件自己声明"登记表在本文"，行形态是 `link:prompts/<名>.adoc[…`——格式由它维护）。
PROMPTS_INDEX_RE = re.compile(r"[A-Za-z0-9_.\-/]*PROMPTS\.adoc")
PROMPT_DOC_RE = re.compile(r"prompts/[A-Za-z0-9_.\-/]+\.adoc")
TIMEOUT_SECONDS = _PATHCONFIG.timeout_seconds
DEFAULT_WORKERS = _PATHCONFIG.workers
# "待换的新版本在哪"的交接文件后缀（写在**本脚本自己的路径**之后）：见 `hand_off_self`。
# 走文件而不是环境变量：**子进程设的环境变量回不到调起它的壳**（本仓库实证），
# 而"换掉自己并且还能接着跑"这件事必须跨进程可见。
SELF_HANDOFF_SUFFIX = _PATHCONFIG.self_handoff_suffix
# 更新自身的工作目录：`tmp/` 下（临时产物见 specs/core/execution.adoc「临时产物」）。
SELF_TMP_DIR = _PATHCONFIG.tmp_dir
# 新版本脚本的文件名后缀（与本轮真身同名不同后缀，见 `_self_update_candidates`）
SELF_UPDATE_SUFFIX = _PATHCONFIG.self_update_suffix
# 落点取完即**只读**：目录只留"进入 + 列出 + 读"（5=rwx+r-x），文件只留读位（4=r--）。
# 用绝对值（两个独立的十进制常量）而不是 `0o` 字面量：权限位取值是**本脚本的取舍**，
# 写成常量便于核对与单测（见 specs/general/script.adoc「注释里的取值：写常量名」）。
_READ_ONLY_FILE_MODE = 0o444        # r--r--r--
_READ_ONLY_DIR_MODE = 0o555         # r-xr-xr-x
# 本脚本为"落盘"所需的最小写位：文件补回用户写位（6=rw-），目录补回用户写+执行（7=rwx）。
_WRITABLE_FILE_MODE = 0o644
_WRITABLE_DIR_MODE = 0o755

EXIT_OK = 0
EXIT_INCOMPLETE = 1
EXIT_USAGE = 2

# 进度行**逐份**打（取完一份打一行）：一份规范只有几 KB 到几百 KB，下载本身没有可插针的
# 中间态；而"卡住时看得见卡在哪一份"正是要买的东西（用户口径：「显示文件下载进度及其他
# 明细」）。故不画进度条，只用**已取份数 + 状态 + 体积 + 耗时**这几项事实——它们与本轮
# 结果一一对应，人核对明细时不必再认第二套数字。
_PROGRESS_LOCK = threading.Lock()
# 本轮已取完的份数（进度行的分子；`main` 每轮开头清零，同一进程内跑两次不接着数）
_DONE = 0

# 体积的打印档位（`_size`）：**超过 1 KB 就换单位**，故 `4222 B` 打成 `4.2 KB`、`6921 B`
# 打成 `6.9 KB`——人一眼就知道是"几 K 的东西"还是"几百 K 的大件"，不必自己数位数。
# 十进制（1 KB = 1000 B）而不是 1024：明细是给人看量级的、不是给容差判定的，且下载体积的
# 通行写法就是十进制（`ls -h` 那套 1024 换算是另一套口径，同一屏里混两种更难看懂）。
# `B` 档只在 1 KB 以下出现（`0 B`、`512 B`）——`0 B` 正是"文件被截断成空"那类失效要看的一档。
_SIZE_UNITS = ("KB", "MB", "GB", "TB")


def _size(num_bytes):
    """把字节数打成**人读的体积**（`4222` → `4.2 KB`，`538` → `538 B`）。

    只留一位小数（`12.3 MB` 这精度对"这份规范多大"够了）：明细行要的是量级，不是逐字节的账；
    要逐字节核对的场合本来就看落点里的文件本身。

    **升档判据是"进位后仍不到 1000"**：999 999 B 打成 `1000.0 KB` 而不是 `1.0 MB`，
    免掉"取整后跳档、看着像四舍五入出错"那类别扭读数。
    """
    if num_bytes < 1000:
        return f"{int(num_bytes)} B"
    size = float(num_bytes)
    for unit in _SIZE_UNITS:
        size /= 1000
        if size < 1000 or unit == _SIZE_UNITS[-1]:
            return f"{size:.1f} {unit}"


def _progress(total, rel, state, detail, seconds, counts=True):
    """打**一行**进度（`[3/27] 刷新 specs/stack/java.adoc -- 12.3 KB（1.2s）`）。

    `total` 为 0（总数没算出来）时省掉分母；`rel` 原样打印——它就是失败清单里定位用的那
    一个名字（见 `main`），两处同一个名字才有可核对性。

    `counts=False` 只打明细、**不推进分子**：分子是"这一轮已经有几份取完了"，重试那一行
    不是某一份的终态（它接着还要再取一次），数进去收尾就会出现 `[48/47]`。

    **写 stderr、逐行 flush**：进度与既有的警告/说明同一路，stdout 仍只留落点与结果
    （调用方会拿 stdout 做重定向，进度混进去就是"结果里多了一堆噪音"）；管道与重定向有
    缓冲，攒到进程结束才吐等于"卡住时什么都看不见"（见 `_flush`）。

    并发 worker 各自取完即打、由锁串行化——攒到收尾统一打就等于没有进度。
    """
    global _DONE
    # 计数与写出放在**同一段临界区**里、直接写 stderr（不经 `_flush`）：`threading.Lock`
    # 不可重入，`_progress` 持锁后再调一个自己也取锁的函数就是自锁——本仓库实测：第一份取完
    # 就整轮挂住，而进度行一行都没打出来（分母与行要原子，正好就是这一段的边界）。
    with _PROGRESS_LOCK:
        prefix = f"[{_DONE}/{total}]" if total else "[--]"
        if counts:
            _DONE += 1
        sys.stderr.write(f"  {prefix} {state} {rel} -- {detail}（{seconds:.1f}s）\n")
        sys.stderr.flush()


def _flush(text):
    """立刻写 stderr 并 flush：管道/重定向下有缓冲，不 flush 等于没有进度。

    与 `_progress` 共用同一把锁：`main` 里那几行说明不能插进某一份的进度行中间。
    **只给"不持锁的调用方"用**（`main`）；`_progress` 已在锁内，直接写 stderr。
    """
    with _PROGRESS_LOCK:
        sys.stderr.write(text)
        sys.stderr.flush()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="fetch-specs",
        description="把 agent 规范集合（AGENTS_COMMON.adoc + specs/）取到本地副本",
    )
    parser.add_argument("--base",
                        default=os.environ.get("AGENT_SPECS_BASE", DEFAULT_BASE),
                        help="规范来源地址（默认取配置 [source].base_url）")
    parser.add_argument("--keep", action="store_true",
                        help="保留本地已有的非空副本（不动已取到的那一份、只补缺失项）")
    parser.add_argument("--force", action="store_true",
                        help="忽略本地副本、强制重取（与 --keep 相反，即默认行为）")
    parser.add_argument("--no-scripts", action="store_true",
                        help="只取规范副本，不把安装脚本（本脚本与其平台入口）取到落点"
                             "（脚本的**自身更新**不受它影响：那一件是本脚本自己、不是落点里的物）")
    parser.add_argument("--list", action="store_true",
                        help="只打印将要取的文件清单，不下载（入口拿它判「这个解释器跑不跑得"
                             "起来」，不走自更新：探一遍不该换脚本、也不该重启）")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help="并发请求数（默认 4）")
    # 内部开关（不是给调用方用的参数）：自更新"换上了、自己重启"后由**本脚本自己**挂在
    # 命令行末尾，作为重启链上的刹车——`hand_off_self` 见到它就不再换、不再重启（防无限套娃）。
    # 写法隐去、不进 `--help`：它是实现细节，调用方加它只会跳过自更新这一版（见 `_restart_with`）。
    parser.add_argument("--self-updated", action="store_true", help=argparse.SUPPRESS)
    # 同上：入口探测解释器时用它跑一遍（走到 `main` 早处即收工：不联网、不写盘、不换自身）。
    parser.add_argument("--probe", action="store_true", help=argparse.SUPPRESS)
    # 口令入口（`<落点>/<口令>.sh <提示词名>`）用的两件：点哪一份、落点在哪。它们只服务
    # "把本地那份提示词装配好打印出来"，**不联网、不写盘**（见 `print_prompt`）。
    parser.add_argument("--print-prompt", metavar="名", help=argparse.SUPPRESS)
    parser.add_argument("--landing", metavar="目录", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def fetch_text(base, path, missing_ok=False):
    """取一份远端文本（UTF-8 解码）。**失败一律抛 OSError**（本函数是这条契约的守门人）。

    **判据不只看状态码**：站点对**任何未命中的路径**都回落成首页 HTML 并返回 200，
    只判状态码会把"不存在的内容"当成取到了（实测：请求本仓库并不存在的 `LICENSE`
    返回 200 + 首页 HTML 18 KB，写进落点后看起来像一份取到的文件）。故文本类产物
    再核一条：**必须是 UTF-8 文本、且不是站点首页**（首页含 SPA 骨架 `<!DOCTYPE html>`
    与站点标题），命中即按取不到处理。

    **网络层异常要在这里归一成 OSError**（本仓库实证的失效形态）：`http.client` 的
    `HTTPException` 家族**不是** `OSError` 的子类——`IncompleteRead`（响应被截断：对端在
    `Content-Length` 之外提前断连、代理/网络抖动）、`BadStatusLine`（对端回了非 HTTP 响应、
    多为中间设备插话）都直接继承 `HTTPException`。`download_one` 只 `except OSError`，
    于是这些异常会**穿过整个 `download_one` 逃逸到 `fut.result()`**，把 `main` 掀掉：
    调用方拿到的是 traceback（不是约定的 0/1/2 退出码）、后面那条"整棵树收紧成只读"的收尾
    **一次都不跑**——落点停在 `755` 而无人察觉，恰好把本 PR 要买的那条保证在"最需要它"的
    一轮里静默丢掉（本仓库实证：截断响应下 `stat` 出落点根 `755`、stderr 是 traceback）。
    故这里先把 `HTTPException` 包成 `OSError`：退出码与"失败项保留本地那一份"的处置都回到
    既有那条路上（`download_one` 的重试与失败分类据此照旧生效）。
    """
    url = f"{base.rstrip('/')}/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "agent-specs-fetch/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            raw = resp.read()
    except http.client.HTTPException as e:
        # IncompleteRead / BadStatusLine 等：不是 OSError，会穿掉 download_one 的 except
        raise OSError(f"取回失败（HTTP 层异常）: {e!r}") from e
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise OSError(f"不是 UTF-8 文本: {e}") from e
    if text.lstrip().lower().startswith("<!doctype html") or "<html" in text[:200].lower():
        # `missing_ok`：**站点首页本身就是这一份的内容**时（如索引页）认下它。
        # 判据仍是"这一份是不是站点首页"——首页是**唯一**既能当"未命中回落"、又能是
        # "真实内容"的形态，故由调用方点名要不要；点名的场合只该是附随文件
        # （`FOLLOWUP_FILES`），规范副本一律按取不到处理（本仓库实证：请求不存在的
        # `LICENSE` 返回 200 + 首页 HTML 18 KB，写进落点后看起来像一份取到的文件）。
        if not missing_ok:
            raise OSError("取回的是站点 HTML 页面（该路径在规范站点上不存在，站点回落到首页）")
    return text


def prompt_index_target(base, entry_text):
    """从入口自身认出**提示词的登记处**（`PROMPTS.adoc`）。

    入口里指向它的那一行是**一处登记**：提示词从此在本仓库有了"目录在哪"的可解析落点
    （此前只有人点站点链接才找得到，脚本拿不到清单、也就只能取规范）。解析不到时**不报错**
    ——来源可能只是本规范集合的一个镜像、没有提示词那一层；那时照旧只取规范（如实说明跳过）。
    返回 `(登记处路径, 登记处正文)`，解析不到时返回 `(None, "")`。
    """
    m = PROMPTS_INDEX_RE.search(entry_text)
    if not m:
        return None, ""
    return m.group(0), fetch_text(base, m.group(0))


def prompt_targets(index_text):
    """从**提示词的登记处**解析要取的任务提示词。

    口径与规范清单同一条：**登记在哪、就取哪些**，不按目录扫——扫描会把草稿、素材与
    "只对本项目生效"的命令一并取到调用方手里；登记表里那一串 `link:prompts/<名>.adoc[…]`
    是提示词自己的目录（哪些是任务提示词、叫什么），故清单以它为准。
    公共片段 `_common.txt` **不在这里**：它不是任务提示词，但缺了它提示词读不全，
    故随附随件走（见 `FOLLOWUP_FILES`）。
    """
    return sorted(set(m for m in PROMPT_DOC_RE.findall(index_text)
                      if not os.path.basename(m).startswith("_")))


def manifest_targets(base):
    """从入口自身解析要取的文件清单。

    入口（AGENTS_COMMON.adoc）的加载调度器**唯一登记**了全部公共规范文件，故清单以它为准：
    新增规范文件时它必然被登记，清单随之自动变全（手工维护清单的失效形态正是漏项）。
    **提示词同样在清单里**：用户口径是"一键使用"——只把规范取到本地、提示词还得回站点找，
    那不是一键。它们的清单来自入口所指的**提示词登记处**（`PROMPTS.adoc`，见
    `prompt_index_target`／`prompt_targets`），与规范走同一套"登记即清单"的口径。
    返回 (清单, 缺失的可选文件)；入口文件本身必然在清单里。
    """
    global _PROMPTS_INDEX, _PROMPTS_INDEX_TEXT
    text = fetch_text(base, MANIFEST_FILE)
    specs = sorted(set(SPECS_REF_RE.findall(text)))
    if not specs:
        raise OSError(f"未能在 {MANIFEST_FILE} 中解析出任何 specs/ 清单")
    index, index_text = prompt_index_target(base, text)
    _PROMPTS_INDEX = index
    _PROMPTS_INDEX_TEXT = index_text
    prompts = prompt_targets(index_text) if index else []
    # 两件事分开说：**认不出登记处**（来源多半没有提示词那一层，跳过合理）与**认出了却一份
    # 都解析不出来**（登记表写法变了、或本页还没登记任何提示词——那时"不取提示词"是静默的
    # 漏取，不是合理跳过）。同一句话盖住两种时，后一种没人会发现。
    if not index:
        print(f"说明: 未能在 {MANIFEST_FILE} 里认出提示词的登记处，本轮只取规范、不取提示词"
              f"（来源 {base} 可能没有提示词那一层）", file=sys.stderr)
    elif not prompts:
        print(f"说明: {index} 里没有登记任何提示词，本轮只取规范"
              "（该文件是提示词的登记处：一条都没解析出来时，先看它的登记表写法有没有变）",
              file=sys.stderr)
    targets = [MANIFEST_FILE]
    if index:
        targets.append(index)
    targets += list(specs) + list(prompts)
    return targets, list(OPTIONAL_FILES)


def target_path(out_dir, rel):
    """落点内路径（相对清单里的仓库路径）。

    安装脚本那一组的 `rel` 带来源侧的目录（`script/fetch-specs.py`），而落点根下只放
    文件名——见 `fetch_install_scripts`。
    """
    if rel in (*INSTALL_SCRIPTS, CONFIG_IN_SCRIPTS_DIR):
        return os.path.join(out_dir, os.path.basename(rel))
    return os.path.join(out_dir, *rel.split("/"))


def local_bytes(dest):
    """本地副本的字节（不存在或读不到时按"没有本地副本"处理）。

    读不到**不等于失败**：默认语义是"以远程为准"，读不到就走"本地没有、按新取落盘"，
    报错只该出现在"远端也取不到"那一侧（否则一次权限问题会把可自愈的情形报成失败）。
    """
    try:
        with open(dest, "rb") as fh:
            return fh.read()
    except OSError:
        return b""


def update_self(base, out_dir, cwd):
    """把**本脚本自身的最新版**取回来并**当场换上去、接着由它干完这一轮**。

    **本函数只在"换上了"时回来**（新版本已落到真身路径、作为真身真的跑起来了）；没换成、
    或远端那份与本轮一致时返回 `None`——调用方照本地这一份继续。

    为什么要有这一步（"清单从入口解析"这件事的自身盲区）：清单来自入口的调度器登记，
    而**解析口径**在本脚本里——远端若改了脚本（新文件类型、新落点排布），跑着旧脚本的那一轮
    只会照旧口径取，新东西静默不进副本（用户口径：更新自身，避免有的没进索引）。
    故每轮先取一次"远端的最新脚本"，与本地这份（`__file__`，即本轮真身）逐字节比较：
    内容一致即当轮无事；不同则把取到的那份**落盘**并**立刻生效**。

    **怎么算"立刻"（用户口径：「更新的时候，就要及时生效吧？还等下一次？」）**：分两步——
      1. **先办正事**（每一轮、任何跑法都成立）：新版本被**落到本次真正在跑的那份脚本的路径**
         （真身可写时就是真身自己旁边；真身读不到时＝"调用方手里这份就是真身"，落点根下那份
         即它的真身），且**写到"真身那一份"上去**——故**无论有没有重启**，"这一轮接下来按哪份
         清单取"已经是新版（壳再次调起、或本脚本下次被跑，读到的都是它）；
      2. **再换本身**（本轮就把新脚本跑起来）：换得动真身、且真身就是本轮这份文件，则立即
         `os.execv` 重启（原样参数、退出码来自重启后的那一轮，见 `_restart_with`）——本轮就
         按新脚本的清单口径取全，不留"下一轮才生效"的空窗。两个平台入口都用 `exec`/绝对路径
         把这份逻辑代码当命令直接跑，故"**本轮这份文件**"与"**真身**"
         在正常跑法下**是同一个文件**（见 `_real_script`）——直跑与经壳调起都走这一条；
         只有 `sys.argv[0]` 确实指向别处（如 `python3 - < x.py`）时才**不在脚本里重启**
         （那时“代真身重启”会把调用方的排布改掉）。
    读不到真身（非属主 / 只读挂载 / 权限）时**换不动**：新版本照旧落地（落点根下那份**就是**
    "下次运行会读到的真身"），并**如实警告**"这一轮仍按旧口径取"（见下，不得静默）。

    **落盘路径按写位取**（判据不是平台名，见 `_self_update_candidates`）：
      * 本轮真身的目录可写 → 落在它旁边（`<目录>/.<脚本名>.<pid>.update`）——直接跑
        `python3 fetch-specs.py`、或经壳调起时都在这一处，换起来不必跨目录；
      * 只有**落点根下**可写（`<落点根>/fetch-specs.py` 是本脚本自己写的那份）→ 落在落点根下
        的**真身同名文件**——它本身就是"下次运行会读到的真身"，故拷过去即已成事；
      * 两处都不可写（只读挂载、非属主）→ 还有工作目录 `tmp/` 兜底；连它也不可写时
        **不落盘、如实警告并继续**：更新自身取不到就别取，本轮照旧把规范副本取到手
        （不得把一个可以自愈的情形报成整批失败）。
    写位在真正落盘时才探测（`_first_writable_dir`）——**只读的 `/usr/local/bin`** 这种
    "看着能写、实际不能"的目录不会留下一串报错。

    **读得到却换不动时**（只读目录、非属主）才写下待换标记（`_leave_handoff_note`），
    由**下一轮运行**消费——那时"下一轮"是唯一可行的路，且警告里如实说明。此时**也不覆盖
    真身**（写不进去）；落点根下那份（"下次的真身"）已换成功。

    只在**非 `--keep`、非 `--list`** 时调用（两者的语义分别是"不动本地那份"与"只看清单、不下载"，
    换上刚取到的新脚本与之相抵；真要最新脚本时不加它——与规范副本同一条口径）。
    **但它只管"脚本自己这一份"**：清单以外的附随文件（索引页、提示词公共片段）与脚本是两件事，由
    `refresh_lagging_followups` **每轮**另行核对——脚本没变的那一轮这里直接返回，那时
    "索引页落后了没有"没有任何人去问（本会话实测的缺口）。反过来，**索引也等它**：那一步由
    `main` 排在取完清单之后，算它的是**已经换新的这一份自己**（用旧脚本算出来的索引还是旧目录）。
    """
    return _refresh_self(base, out_dir, cwd)


def refresh_lagging_followups(base):
    """把**跟不上清单的附随文件**取回来（`FOLLOWUP_FILES`：站点索引页、提示词公共片段）——**每轮都做**。

    为什么这件不能交给自更新的那条路（本会话实测的缺口，用户点名「避免漏规范」）：
    `update_self` 只在**脚本自身变了**时才动手（"远端那份与本轮真身逐字节不同"），脚本没变
    的那一轮它**一个字节都不写**。而索引页（`index.html`：站点的目录页）与脚本是**两件事**
    ——新增、删除、重命名一份文件时，索引页与规范正文一起变了，脚本却可能一个字都不变。
    于是"每轮都取最新"只覆盖了规范副本与脚本，**索引页停在上一次脚本变动的那一版**：
    人按站点找文件，看到的是一份过期目录（看着齐全、其实少了几份），且**没有任何输出**
    显示出它没跟着更新。故这一件事按"与规范副本同一条口径"办：**每轮都取、按内容判、
    不同才落盘**（同一套落盘动作：先取到内存、再原子替换、写后收紧成只读）。

    落点与安装脚本同一处（落点根下、跨来源共用一份，见 `install_scripts_dir`），不按来源
    分槽：它是"脚本自己那一份"，换来源时跟着换即可（索引页不是规范副本）。

    取不到**不算失败**（`missing_ok=True` 放行"站点首页"这一形态；网络失败只警告）：
    本仓库以外的来源多半根本没有这个文件，把"没有这一份"报成整批失败会让一次成功的取文件
    看起来像失败（同 `OPTIONAL_FILES` 的口径）。**但"本地那一份可能已落后"须如实说出来**
    ——静默跳过时，读者无从知道手里那份索引是旧的。

    **提示词的那一半按"缺了就说不全"办**：公共片段（`prompts/_common.txt`）不在任务提示词
    清单里（它不是提示词），而提示词的公共步骤全在它里面——缺了它，取到的那几份提示词
    读到未装配形态时**补不齐公共片段**（见 `PROMPTS.adoc`「访问与解析」）。故它随附随件
    每轮核一次；而"清单里列着、实际没取到"的那几份，按清单逐个核一遍后**如实报出名字**：
    索引页与提示词之间互不引用，少一份既不报红、也没人发现，那正是"取全了"这句话最贵的
    一种失效形态（本仓库实证过：看着取全了、其实少了几份）。
    """
    out_dir = install_scripts_dir()
    for rel in FOLLOWUP_FILES:
        print(f"CALC-INDEX-BY-v2", file=sys.stderr)  # noqa: E501
        dest = target_path(out_dir, rel)
        before = local_bytes(dest) if os.path.isfile(dest) else None
        # 取不到**不算失败**，但网络类异常须在这里收住：`HTTPException` 不是 `OSError`
        # 的子类，放它出去会掀掉整批、连收尾那次"落点收紧成只读"都跑不到（见 `fetch_text`）。
        # 成功那一侧只包**网络与解码**这一段：`try` 罩住整段时，落盘那一步自己抛的
        # `OSError`（权限、只读挂载）会被同一组 `except` 接走，落到"取不到——原样保留、
        # 它可能已落后"那两句上——报了一句不成立的话，真正的成因（写不进去）一个字都不说。
        try:
            data = fetch_text(base, rel, missing_ok=True).encode("utf-8")
        except (OSError, http.client.HTTPException) as e:
            if before is None:
                print(f"说明: 附随文件 {rel} 取不到（{e}）——本站点没有这一份，跳过",
                      file=sys.stderr)
            else:
                print(f"警告: 附随文件 {rel} 取不到（{e}）——本地那一份**原样保留**，"
                      "它可能已经落后于远端", file=sys.stderr)
            continue
        if before == data:
            continue
        # 落盘这一段的失败另有成因（写位、只读挂载、原子替换），故单列一条处置：
        # 它的结论是"取到了、但落不下去"，不是"取不到"。
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            _ensure_writable(out_dir, dest)
            tmp = f"{dest}.part"
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, dest)
        except OSError as e:
            print(f"警告: 附随文件 {rel} 已取到、但落盘失败（{e}）——远端与本地不同，"
                  "落点里这一份仍是旧的", file=sys.stderr)
            continue
        # 中转件**无论成败都清掉**：`.part` 不在落点应有的形态里（同 `download_one`），
        # 留一份下来既不是"取到的文件"，也不在索引里，只会在落点里越积越多。
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        _make_read_only(dest, is_dir=False)
        print(f"更新: 附随文件 {rel} 已按远端刷新（{_size(len(data))}）——"
              + ("索引页与清单同步，按站点找文件不会看到过期目录" if rel.endswith(".html")
                 else "提示词的公共片段已就位，未装配形态下可照它补齐后再执行"),
              file=sys.stderr)


def prompts_missing(base):
    """登记处列着的提示词里，**这一轮没取到**的那几份——返回 `(缺的清单, 可否核对)`。

    为什么单列这一步：提示词与规范、索引页**互不引用**，少一份不会有任何东西报错——
    而"我说取全了"这句话的全部分量就在这一处（漏掉的正是调用方最想要的那一份时，
    他通常要等到真正去用它才发现，那时已经不在取文件这一步了）。
    判据是**这一轮取到了哪几份**（`_PROMPTS_TAKEN`），不是"落点里在不在"——落点是跨来源
    共用的只进不出池子，按它判会把"上一轮取到、这一轮没取到"读成"取全了"。
    登记处本身取不到时返回 `([], False)`：这一轮的清单都算不出来，无从逐项核。
    """
    if not _PROMPTS_INDEX:
        return [], True
    try:
        index_text = fetch_text(base, _PROMPTS_INDEX)
    except (OSError, http.client.HTTPException):
        return [], False
    return [rel for rel in prompt_targets(index_text) if rel not in _PROMPTS_TAKEN], True


def report_prompts_missing(base):
    """把"提示词没取全"如实报出来（缺的名字逐个列出）——**在失败明细之前**打，返回是否取全。

    结论写在明细前面才读得通：它是"要不要重跑"的那句话，而明细只是佐证。
    **"核不了"与"取全了"必须分得清**：登记处本身取不到时，这一轮按**没取全**计（不是
    "取全"——把没核到的写成取全了，正是本条要防的那种"看着齐全"）。
    """
    missing, checkable = prompts_missing(base)
    if not checkable:
        print(f"警告: 核不到提示词是否取全——{_PROMPTS_INDEX} 取不到（这一轮按没取全计，"
              "不当成取全了）", file=sys.stderr)
        return False
    if missing:
        print(f"警告: 提示词有 {len(missing)} 份这一轮没取到（{_PROMPTS_INDEX} 里列着它们）："
              f"{'、'.join(missing)}——照着用时会缺这几份", file=sys.stderr, flush=True)
        return False
    return True


def prompt_names_from_landing(landing):
    """落点里**实际有哪几份**提示词（按目录现算）——口令入口的"可用名单"取自它。

    为什么按目录而不按登记处：入口要能在**断网**下判"这一份在不在"，而登记处是远端文件；
    落点里 `prompts/` 下非 `_` 前缀的 `.adoc` 与登记处列着的本就是同一批（取的时候按登记取）。
    """
    d = os.path.join(landing, *PROMPT_DIR.split("/"))
    if not os.path.isdir(d):
        return []
    return sorted(f[:-len(".adoc")] for f in os.listdir(d)
                  if f.endswith(".adoc") and not f.startswith("_"))


def prompt_entry_script():
    """`.sh` 形态的口令入口：正文一个字都不抄，只记"该跑哪一份"。

    为什么是脚本而不是"把提示词正文填进模板"：那样落点里就有了**第二份提示词正文**
    ——改一处必漂移，而落点里那份还看不出是旧的。脚本只记"该跑哪一份"，正文始终只有
    落点里那一份（用户口径：取下来就是为了**不用再复制**，点名即用）。

    **可用名单在现场算、不烘进文本**：烘进去的名单在提示词增删之后就是一份会撒谎的清单
    （而落点已收紧只读，没人会去改它）；名单的判据只有一处——落点里 `prompts/` 下有哪些。
    """
    usage = PROMPT_COMMAND_USAGE.format(name=PROMPT_COMMAND_NAME)
    # 解释器**现在算、不烘进文件**：入口生成时的 `sys.executable` 是"生成这一刻这台机器"上的
    # Python，落点却是家目录下跨来源共用、可被整个搬去另一台机器的（换机器、换 venv、改名后
    # 那一行直接 `no such file`）。故这里只留候选次序，由入口在运行时逐个试跑（`--probe`）。
    # 次序与取规范入口同一条（`fetch-specs.sh`）：先 `python3` 再 `python`，Windows 上多一个
    # `py`；空白分隔是刻意的约定——候选名里不会有空格。
    interp = " ".join(PROMPT_SHELL_INTERPRETERS)
    return f"""#!/bin/sh
# {usage}——把落点里那一份提示词**装配好**整段输出（include:: 已就地展开）。
#
# 由取规范脚本生成（落点根下的 {os.path.basename(INSTALL_SCRIPTS[0])}），**不要手改**：
# 重跑取规范会覆盖它。本文件不抄提示词正文——正文只有落点里那一份，改它不必改这里。
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
NAME=${{1:-}}
if [ -z "$NAME" ] || [ "$NAME" = "-h" ] || [ "$NAME" = "--help" ]; then
    echo "用法: {usage}" >&2
    echo "可用的提示词名（落点里现有的）:" >&2
    for f in "$HERE"/{PROMPT_DIR}/*.adoc; do
        [ -e "$f" ] || continue
        b=${{f##*/}}
        case "$b" in _*) continue ;; esac
        echo "  ${{b%.adoc}}" >&2
    done
    exit 2
fi
# 解释器逐个试跑（`--probe`：只证"这一份脚本在它底下跑得起来"，不联网、不写盘），
# 认第一个真的跑得起来的——生成时那台机器上的绝对路径搬去别的机器就失效了。
PY=
for c in {interp}; do
    if command -v "$c" >/dev/null 2>&1 \
        && "$c" "$HERE/{os.path.basename(INSTALL_SCRIPTS[0])}" --probe >/dev/null 2>&1; then
        PY=$c
        break
    fi
done
if [ -z "$PY" ]; then
    echo "错误: 未找到可用的解释器（{interp}），无法输出提示词 $NAME" >&2
    exit 127
fi
exec "$PY" "$HERE/{os.path.basename(INSTALL_SCRIPTS[0])}" --print-prompt "$NAME" --landing "$HERE"
"""


def prompt_entry_bat():
    """`.bat` 形态的口令入口（与 `sh` 那份同一件事；Windows 上按关联执行）。

    解释器同样**现场试跑、不烘路径**（同 `.sh` 那份的理由：落点可被搬去另一台机器），
    次序是 Windows 上的常见命名 `py` → `python3` → `python`。
    """
    interp = " ".join(PROMPT_WINDOWS_INTERPRETERS)
    usage = PROMPT_COMMAND_USAGE.format(name=PROMPT_COMMAND_NAME)
    return f"""@echo off
rem {usage}——把落点里那一份提示词装配好整段输出。
rem 由取规范脚本（{os.path.basename(INSTALL_SCRIPTS[0])}）生成，不要手改：重跑取规范会覆盖它。
rem 本文件不抄提示词正文——正文只有落点里那一份，改它不必改这里。
setlocal
set "HERE=%~dp0"
if "%~1"=="" goto usage
if "%~1"=="-h" goto usage
if "%~1"=="--help" goto usage
set "PY="
for %%R in ({interp}) do (
    if not defined PY (
        %%~R "%HERE%{os.path.basename(INSTALL_SCRIPTS[0])}" --probe >nul 2>nul
        if not errorlevel 1 set "PY=%%~R"
    )
)
if not defined PY (
    echo 错误: 未找到可用的解释器（{interp}），无法输出提示词 %~1 1>&2
    exit /b 127
)
"%PY%" "%HERE%{os.path.basename(INSTALL_SCRIPTS[0])}" --print-prompt "%~1" --landing "%HERE%"
exit /b %ERRORLEVEL%
:usage
echo 用法: {usage} 1>&2
echo 可用的提示词名就在落点根下的 {PROMPT_DIR}/ 里（`_` 前缀的是公共片段，不是提示词） 1>&2
exit /b 2
"""


def prompt_entry_agent():
    """agent 平台命令位的 `<name>.md`：点名之后**照落点里那一份做**，不在这里抄正文。

    平台只认自己目录下的命令，故这一段是"命令名"的落点；但它只负责**领到哪里去**。
    取不到就停：空壳命令被当成"提示词已加载"是本条最贵的失效形态。

    **路径写全、不写"PATH 上的 `<name>`"**：落点根下生成的是 `{PROMPT_COMMAND_SHELL_NAME}`
    ——`<name>.sh` 那个名字本身**没有**进 PATH，让读者去敲 `{PROMPT_COMMAND_NAME} <名>` 时
    他得到的是 "command not found"，而这个 `.md` 又不会自己跑命令（它只是指令）。故第 2 步
    给出**本机上真的存在的那个路径**（家目录现取，与落点同一条口径）。
    """
    usage = PROMPT_COMMAND_USAGE.format(name=PROMPT_COMMAND_NAME)
    landing = install_scripts_dir()
    sh_path = os.path.join(landing, PROMPT_COMMAND_SHELL_NAME)
    bat_path = os.path.join(landing, PROMPT_COMMAND_BAT_NAME)
    return f"""---
description: 跑本地落点里的任务提示词（{usage}；正文由取规范脚本取到本机，本文件只负责把它装好）
---

执行本命令：

1. 先看调用参数里的提示词名（如 `review`、`refactor`）；没给就问一句要哪一份，
   并把落点 `{PROMPT_DIR}/` 下现有的名字列出来（`_` 前缀的是公共片段，不是提示词）。
2. 运行落点根下的入口（Linux/macOS：`{sh_path}`；Windows：`{bat_path}`），
   参数就是第 1 步那个名字——`<入口> <提示词名>`。它不在 PATH 上，故**写全路径**。
3. 它输出的是**装配好的整段提示词**（`include::` 已在落点内就地展开）。把那段输出当任务指令执行。
4. **取不到就停**：退出码非 0、或没有输出时，如实说明"提示词 `<名>` 不在本机落点里"，
   先补取再来——**不得**凭命令名或印象自己编一份步骤顶上。
"""


def resolve_prompt_command_dirs():
    """把配置里的命令位取值填好：`{home}`/`{name}` 是**本轮现取**的家目录与口令名主干。

    `{home}` 现取、不写死、不缓存（与落点同一条口径）；家目录取不到、或配置里仍留着未填的
    占位符时，**那一项整个不生成**——拼不出来就不猜路径，绝不把 `{home}/...` 这个字面量
    当成目录建出来（占位符留在路径里时，入口会落到一个没人会去的目录，而"已生成"那句话
    照旧打了出来）。
    """
    try:
        home = _user_home_dir()
    except (OSError, ValueError):
        home = ""
    if not home or home == "~":
        return []
    out = []
    for pattern in PROMPT_COMMAND_DIRS:
        d = pattern.replace("{home}", home).replace("{name}", PROMPT_COMMAND_NAME)
        if "{" in d or "}" in d:
            continue
        out.append(d)
    return out



def prompt_entries():
    """本轮要生成的口令入口：`[(落点全路径, 平台, 生成函数)]`，服务的是**登记处列着的**那些提示词。

    不另列一份清单：加一份提示词不必改任何一处（入口的可用名单在运行时按落点现算）。落点根下两套
    （`sh`/`bat`，与安装脚本同一处）+ 每个 agent 命令位一套（`md`）。家目录取不到时只生成
    落点根下那两套：命令位要拼家目录，拼不出来不猜路径（与落点同一条口径，不静默换地方）。
    """
    targets = [(os.path.join(install_scripts_dir(), PROMPT_COMMAND_SHELL_NAME), "sh",
                prompt_entry_script),
               (os.path.join(install_scripts_dir(), PROMPT_COMMAND_BAT_NAME), "bat",
                prompt_entry_bat)]
    for d in resolve_prompt_command_dirs():
        targets.append((os.path.join(d, PROMPT_COMMAND_AGENT_NAME), "md", prompt_entry_agent))
    return targets


def write_prompt_entries(index_text):
    """生成口令入口各一份——**每轮重写**（内容是现算的），与安装脚本同一套落盘纪律。

    `index_text` 只用来判"这一轮认不认得提示词这一层"（登记处取不到时不生成空入口）。

    内容不同才写、原子替换、写完收紧成只读：与规范副本、索引页同一条口径（"以远程/现算为准"）。
    返回 `(写入的清单, 告警清单)`——写不进去时**如实告警**，不静默。
    """
    written, problems = [], []
    if not index_text:
        return written, problems
    for dest, _platform, render in prompt_entries():
        data = render().encode("utf-8")
        if os.path.isfile(dest) and local_bytes(dest) == data:
            # **内容一致的那一轮也要补在位**：清缓存/解压工具会把执行位吃掉，而这一步
            # "内容没变"就跳过——不在这里补齐时，口令成了 `Permission denied`，而输出里
            # 一个字都没说它跑不了（同 `ensure_landing_executables` 的口径：补位与
            # "这一轮落了哪几个盘"解耦）。只对落点根下那两份（`.sh`/`.bat`）做。
            _prompt_entry_mode(dest)
            continue
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            _ensure_writable(os.path.dirname(dest), dest)
            tmp = f"{dest}.part"
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, dest)
        except OSError as e:
            problems.append(f"{dest}（{e}）")
            continue
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        _prompt_entry_mode(dest)
        written.append(dest)
    return written, problems


def _prompt_entry_mode(dest):
    """给口令入口定权限位：`.sh`/`.bat` **可执行 + 只读**（与安装脚本同一套），`.md` 只读。

    执行位是口令能不能被点名的全部——写完就收紧成只读，故"补位"必须在收紧之前、且
    **每一轮都做**（`write_prompt_entries` 在内容一致时也会走到这里）。
    """
    if dest.endswith((".sh", ".bat")):
        _chmod_report(dest, _WRITABLE_FILE_MODE | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    _make_read_only(dest, is_dir=False)


# 行内的 `include::<文件>[tag=…]` 一律认（**不锚行首**）：公共片段的说明里就写着这个指令的
# 形态，锚行首时形态一变就整份不装配，而"装配没装配"只能靠肉眼发现（本仓库实测：写在本行
# 之前的说明文字挡住了匹配，十六处片段一处都没展开、返回码却是 0）。
INCLUDE_RE = re.compile(
    r"include::(?P<rel>[^\[\n:]+)\[(?:tag=(?P<tag>[^\]]+)|lines=(?P<lines>[^\]]*))?\]")


def _tag_block(text, tag):
    """取公共片段里 `// tag::<tag>[]` 与 `// end::<tag>[]` 之间的正文（含两端之间的空行）。"""
    m = re.search(r"// tag::" + re.escape(tag) + r"\[\](.*?)// end::" + re.escape(tag) + r"\[\]",
                  text, re.S)
    return m.group(1).strip("\n") if m else None


def assemble_prompt(text, base_dir, depth=0, root=None):
    """把 `include::` 就地展开——**取到的是原始文件，命令入口必须自己装**。

    不展开就少半份题面（本仓库实证：公共步骤一条都不在正文里，读到的人照着做会漏步）。
    行为按 AsciiDoc 的两条取值实现：`tag=` 取标记段、`lines=` 取行区间或 `a..b`；引用的
    文件找不到 / 标记不存在时**保留原指令**（`registry_text` 里"看着装过了"比"少了几段"
    更难发现，故宁可让它显眼地留在输出里）。嵌套按 `depth` 限深，防互引成环。

    `root` 是**落点根**：提示词落在来源槽里，而公共片段 `prompts/_common.txt` 是附随件、
    落在落点根下的同一相对目录——只按引用方所在目录找时，那十六处片段一个都装不上
    （本仓库实测）。故取文件的次序是"引用方所在目录 → 落点根下的同一相对路径"。
    """
    if depth > 8:
        return text
    root = base_dir if root is None else root

    pkg = os.path.basename(base_dir)

    def repl(m):
        rel = m.group("rel").strip()
        # 取文件三处依序：引用方所在目录 → 落点根下拼**同一包内相对路径** → 落点根下按原路径。
        # 中间那一处是关键：提示词与公共片段同在 `prompts/` 包内，而片段是附随件、落在落点根下
        # ——槽里的提示词写的是 `_common.txt`，根下那份却在 `prompts/_common.txt`
        # （本仓库实测：少了这一处，十六处片段一个都装不上，而返回码仍是 0）。
        candidates = [os.path.join(base_dir, *rel.split("/")),
                      os.path.join(root, pkg, *rel.split("/")),
                      os.path.join(root, *rel.split("/"))]
        target = next((c for c in candidates if os.path.isfile(c)), None)
        if target is None:
            return m.group(0)
        with open(target, encoding="utf-8") as fh:
            sub = fh.read()
        tag, lines = m.group("tag"), m.group("lines")
        if tag:
            block = _tag_block(sub, tag.strip())
            if block is None:
                return m.group(0)
            return assemble_prompt(block, os.path.dirname(target), depth + 1, root)
        if lines:
            spec = lines.strip()
            rows = sub.splitlines()
            if ".." in spec:
                a, _, b = spec.partition("..")
                try:
                    picked = rows[int(a) - 1:int(b)] if b.strip() else rows[int(a) - 1:]
                except ValueError:
                    return m.group(0)
            else:
                try:
                    picked = [rows[int(spec) - 1]]
                except ValueError:
                    return m.group(0)
            return assemble_prompt("\n".join(picked), os.path.dirname(target), depth + 1, root)
        return assemble_prompt(sub, os.path.dirname(target), depth + 1, root)

    return INCLUDE_RE.sub(repl, text)


def _prompt_root(path, base):
    """这份提示词对应的**落点根**（附随件 `prompts/_common.txt` 那一处）：来源槽的上一层。

    `base` 本身是落点根（老版本把提示词放在根下、或用户自己复制过来的）时就用它自己——
    故判据是"这份文件在不在 base 的下一层"，不是"base 看起来像不像一个槽名"。
    """
    parent = os.path.dirname(os.path.abspath(path))
    while parent and os.path.abspath(parent) != os.path.abspath(os.sep):
        if os.path.abspath(parent) == os.path.abspath(base):
            return base
        if os.path.dirname(parent) == os.path.abspath(base):
            return os.path.abspath(base)
        parent = os.path.dirname(parent)
    return base


def _prompt_slot_dirs(root):
    """可能放着提示词的目录：**落点根下**（附随件 `prompts/_common.txt` 在那）与**每个来源槽**。

    提示词属规范副本那一份（取回清单里、按来源分槽），安装脚本与口令入口在落点根下——
    两处都可能命中（用户从落点复制过来的、或者老版本落在根下的），故两个都找一遍。
    """
    dirs = [root]
    if os.path.isdir(root):
        for child in sorted(os.listdir(root)):
            slot = os.path.join(root, child)
            if os.path.isdir(slot) and not child.startswith("."):
                dirs.append(slot)
    return dirs


PRIMARY_DECL_RE = re.compile(r"\*\*主侧重[^*]*\*\*\s*[:：]\s*\*\*([^*\n]+?)\*\*")
PLACEHOLDER = "{主侧重}"


def fill_primary(body):
    """把片段里的 `{主侧重}` 换成提示词自己声明的那一个值（值只在提示词正文里，一处）。

    取不到声明时**原样留着**——宁可显眼地留一个占位符，也不替它猜一个方向：方向选错比漏步更糟。
    """
    m = PRIMARY_DECL_RE.search(body)
    if not m:
        return body
    return body.replace(PLACEHOLDER, m.group(1).strip())


def print_prompt(name, landing=None):
    """把落点里那一份提示词**装配好**整段打到 stdout——口令入口的执行体（不联网、不写盘）。

    判据只有一条：输出的必须是**可直接执行的那一整段**（`include::` 已就地展开）。取不到时
    如实报错并返回非 0——"取不到"不得变成"输出了半份"，那正是让口令看起来能用、实际漏步的形态。
    """
    base = landing or shared_cache_dir()
    path = None
    # 提示词落在**来源槽**里（规范副本那一份，按来源分槽），口令入口却在落点根下
    # ——故按"落点根 → 各来源槽"的顺序现找：来源换过几次时，先找到的那份就是这一轮的。
    for slot in _prompt_slot_dirs(base):
        candidate = os.path.join(slot, *PROMPT_DIR.split("/"), name + ".adoc")
        if os.path.isfile(candidate):
            path = candidate
            break
    if path is None:
        print(f"错误: 落点里没有这份提示词 {name!r}（找过 "
              f"{'、'.join(_prompt_slot_dirs(base))}）——先跑一次取规范脚本把它取下来",
              file=sys.stderr)
        return EXIT_USAGE
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    body = assemble_prompt(text, os.path.dirname(path),
                           root=_prompt_root(path, base))
    # `{主侧重}` 是片段里的占位符，取值只在提示词自己的「主侧重」段（值不同、不得混用）：
    # 装配时补上——不补的话，命令吐出来的是一份还带着 `{主侧重}` 的题面，照做的人不知道
    # 该按哪个方向干（本仓库实测：片段本身只有占位符，一个字的方向都不含）。
    body = fill_primary(body)
    # 装配完仍留着 include:: 的，说明有片段没取到：**说出来**，不静默当装配完成
    left = INCLUDE_RE.findall(body)
    if left:
        print(f"警告: 装配后仍留有 {len(left)} 处 include:: 未展开（明细见正文）——公共片段可能"
              f"没取全，先重跑取规范脚本（{os.path.basename(INSTALL_SCRIPTS[0])}）", file=sys.stderr)
    sys.stdout.write(body)
    if not body.endswith("\n"):
        sys.stdout.write("\n")
    return EXIT_OK


def _refresh_self(base, out_dir, cwd):
    """把**最新版的脚本自身**取回并落地——`update_self` 的执行体（本函数只管"脚本自己这一份"）。

    口径同规范副本：取回远端那份、与本地逐字节比较、**不同才落盘**；落点由
    `_self_update_candidates` 按**写位**产出（真身旁 → 落点根下 → `tmp/`），
    落盘后交 `_take_over_self` 换上并当轮重启。**清单以外的附随文件不在这里**
    （见 `refresh_lagging_followups`：它与脚本是两件独立的事，不挂在"脚本变没变"上）。

    以下取值与边界是本脚本自更新的全部约定（`update_self` 的文档头讲"为什么要做"，
    这里讲"怎么做、换不动怎么办"）：

    读不到真身（非属主 / 只读挂载 / 权限）时**换不动**：新版本照旧落地（落点根下那份**就是**
    "下次运行会读到的真身"），并**如实警告**"这一轮仍按旧口径取"（见下，不得静默）。

    **落盘路径按写位取**（判据不是平台名，见 `_self_update_candidates`）：
      * 本轮真身的目录可写 → 落在它旁边（`<目录>/.<脚本名>.<pid>.update`）——直接跑
        `python3 fetch-specs.py`、或经壳调起时都在这一处，换起来不必跨目录；
      * 只有**落点根下**可写（`<落点根>/fetch-specs.py` 是本脚本自己写的那份）→ 落在落点根下
        的**真身同名文件**——它本身就是"下次运行会读到的真身"，故拷过去即已成事；
      * 两处都不可写（只读挂载、非属主）→ 还有工作目录 `tmp/` 兜底；连它也不可写时
        **不落盘、如实警告并继续**：更新自身取不到就别取，本轮照旧把规范副本取到手
        （不得把一个可以自愈的情形报成整批失败）。
    写位在真正落盘时才探测（`_first_writable_dir`）——**只读的 `/usr/local/bin`** 这种
    "看着能写、实际不能"的目录不会留下一串报错。

    **读得到却换不动时**（只读目录、非属主）才写下待换标记（`_leave_handoff_note`），
    由**下一轮运行**消费——那时"下一轮"是唯一可行的路，且警告里如实说明。此时**也不覆盖
    真身**（写不进去）；落点根下那份（"下次的真身"）已换成功。
    """
    local = _this_file()
    try:
        data = fetch_text(base, INSTALL_SCRIPTS[0]).encode("utf-8")
    except (OSError, http.client.HTTPException) as e:
        print(f"警告: 取回最新脚本失败({e})——本轮照旧按本地这一份的清单口径取", file=sys.stderr)
        return None
    try:
        with open(local, "rb") as fh:
            if fh.read() == data:
                return None
    except OSError:
        pass                        # 读不到本地那份（权限等）：照"不同"处理，取回的那份仍写出去
    # 落盘**逐处试**（不是先选一处、写不进去就放弃）：写位是按 `os.access`/"最近可写的祖先"
    # 估的，而真实可写性与它不总一致（ACL、只读挂载、祖先可写而这一级建不出来）——第一处
    # 写失败时后面那几处**可能写得进去**，那时"无处落盘"是假结论、待换标记也就白丢了。
    failed = None
    for target, why in _self_update_candidates(out_dir, cwd):
        try:
            _ensure_writable(out_dir, target)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as fh:
                fh.write(data)
            _chmod_report(target, _WRITABLE_FILE_MODE | stat.S_IXUSR)
        except OSError as e:
            failed = e
            continue
        print(f"更新: 已取到更新的取规范脚本 {_size(os.path.getsize(target))}（{why}）", file=sys.stderr)
        return _take_over_self(local, target)
    if failed is None:
        print("警告: 最新脚本已取到、但无处落盘——本轮照旧按本地这一份的清单口径取",
              file=sys.stderr)
    else:
        print(f"警告: 最新脚本已取到、但无处落盘({failed})——本轮照旧按本地这一份的清单口径取",
              file=sys.stderr)
    return None


def _take_over_self(local, target):
    """把刚落盘的新版本**换到正在跑的这份脚本身上**：成事即回来（此函数不返回），
    换不动则**如实警告 + 留下待换标记**（`hand_off_self` 消费）并返回 `None`。

    三条判据（"读得到真身"是自更新这件事的**能力边界**，做不到就明说）：

      * **读不到真身**（非属主 / 只读 / 权限）：既比不出差异、也换不动——只留下待换标记
        并如实警告"这一轮仍按旧口径取，重跑一次即用上"（`os.access` 只是**尝**
        ——ACL/只读挂载在权限位上仍显可写，真写才失败，见 `_first_writable_dir`）；
      * **真身不在本轮这个文件上**（`sys.argv[0]` 指向别处）——**这个进程不是它**，别人那份
        动不得（真写上去会把调用方自己的排布改掉），只留标记、不换不发：真身那一份已经由
        上一处的落盘换成了新版（`_self_update_candidates` 按 `sys.argv[0]` 定落点），它下次跑起来
        就是新版；
      * **真身就是本轮这个文件**：补回真身的写位、拷上去、`os.execv` **当轮重启**——换得动
        即本函数不返回，换不动（真属主/只读挂载那一层）则退回"留标记 + 如实警告"。

    **换成功这条路上没有交接文件**：真身已经换成新版、本轮已由新版接着跑完，下一轮读到它
    就是新版，标记只会白留一份（故这条路上顺手清掉既有的那份）。
    """
    real = _real_script()
    if real is None:
        print("警告: 已取到更新的取规范脚本，但读不到真身、这一轮换不上去——本轮仍按旧口径取；"
              "重跑一次即用上（见 specs/general/script.adoc「跨环境脚本」）", file=sys.stderr)
    elif os.path.abspath(real) != local:
        print(f"警告: 已取到更新的取规范脚本，但真身是 {real}（本轮这份是壳另起的临时副本）"
              "——不在脚本里代它重启；重跑一次即由真身接上", file=sys.stderr)
    else:
        # 换之前先确认"这一份读得成一整份"（判据在 `_readable_as_script`）：`_real_script` 认的
        # 是"`sys.argv[0]` 指向一个存在的文件"，而"存在"不等于"写完过"——同一目录里正有一份
        # 写到一半的同名文件时，拷过去即把 `exec` 的目标换成半份源码（本机实测：报出来的是
        # 源码中间那一行的 `AttributeError`、路径还是这份脚本，看着像配置读错了）。
        if not _readable_as_script(target):
            print(f"警告: 已取到更新的取规范脚本({target})，但它读不成一份完整的脚本"
                  "（多半还在写、或已被截断）——本轮不换、按本地这一份继续；"
                  "重跑一次即可", file=sys.stderr)
            return None
        try:
            # 真身在落点里、带着收尾收紧留下的只读位（main 收尾把安装脚本自己也收紧了）：
            # 不补写位直接 copyfile 会被只读位拒掉（Windows 上即 [Errno 13]，且**每轮复发**
            # ——本轮失败留标记，下一轮 `hand_off_self` 换的还是同一个只读文件）。故
            # **先补写位再换**（与 `_ensure_writable` 同一条"只加不减的例外"：补位只为换
            # 这一步，重启后的那一轮收尾会把只读位收紧回去，见 main）。
            _chmod_report(local, _WRITABLE_FILE_MODE)
            shutil.copyfile(target, local)
            os.chmod(local, os.stat(local).st_mode | stat.S_IXUSR)
        except OSError as e:
            print(f"警告: 已取到更新的取规范脚本({target})，但换不上去({e})——本轮按本地这一份继续；"
                  "重跑一次、或手工把它换过来即用上（见 specs/general/script.adoc「跨环境脚本」）",
                  file=sys.stderr)
        else:
            _discard_handoff_note(f"{local}{SELF_HANDOFF_SUFFIX}")
            print("更新: 已就地换上新版取规范脚本，本轮即按它的清单口径取全", file=sys.stderr)
            _restart_with(local, "--self-updated")     # 成事即不返回
    # 真身这回换不动：新版本落在 `target`，标记只能指向它——**上一轮那份标记要一并清掉**。
    # 不带 `keep` 时它指向的中转件刚被 `_clean_self_tmp` 收走（那一轮没留下新版本），留着就是
    # 一条指向空处的标记：下一轮 `hand_off_self` 读到"文件不在"、丢掉标记就返回，本轮这次
    # 自更新于是白做——远端已经是最新、`update_self` 见内容一致直接返回，标记再没人补上
    # （本仓库实测：脚本停在旧版，直到远端再变一次）。
    _discard_handoff_note(f"{local}{SELF_HANDOFF_SUFFIX}")
    _leave_handoff_note(target)
    return None


def _readable_as_script(path):
    """`path` 是否读得成**一整份**`.py`（能编译即算；读不到也按"读不成"处理）。

    只判这一层：本函数不是语法评审——"这一份写得对不对"由测试与判据管，这里要挡的是
    "换上去的那份其实还没写完/被截断"。原文读出来再编译（不用 `compile(open(...).read())`
    一行写完：那样出错时连报的是哪一份都拼不出来）。

    判的是**要被拷过去的那一份**（`target`），不是本轮正在跑的这份：换完还要 `shutil.copyfile`
    读它一遍，这里多读一次换来"读的时候它是完整的、拷的时候还是它"这句话。

    **按字节读、再交给 `compile`**：文本模式下 `utf-8` 不认 BOM（带 BOM 的 `.py` 会
    `UnicodeDecodeError`），换行也会被就地转成平台那一套——而 `execv` 重启后解释器读的是
    盘上原样的字节。读写两边按同一种形态判，才不会"这里说读得成、那里跑不起来"。
    """
    try:
        with open(path, "rb") as fh:
            source = fh.read()
    except OSError:
        return False
    try:
        compile(source, path, "exec")
    except (SyntaxError, ValueError):
        return False
    return True


def _real_script():
    """**真正的脚本文件**在哪：`sys.argv[0]` 指向的那个（读不到时返回 None）。

    为什么与 `__file__` 分开：两者在本脚本的正常跑法下**是同一个文件**（两个平台入口都用
    `exec`/绝对路径把这份逻辑代码当命令直接跑，`sys.argv[0]` 即它自己），但**不保证相等**
    ——`python3 - < x.py`、或调用方自己拷一份到别处再跑时，`sys.argv[0]` 才是"调用方手里
    那一份"。"换完能不能当场接着跑"取决于这两者是不是同一个文件（见 `_take_over_self`）。
    """
    try:
        argv0 = sys.argv[0]
    except (IndexError, AttributeError):
        return None
    if not argv0 or not os.path.isfile(argv0):
        return None                 # 读不到"调用方手里那一份"：换不动它，别猜
    return os.path.abspath(argv0)


def _restart_with(script, *extra):
    """用**当前解释器**把 `script` 与**原样的参数**重新跑起来（退出码来自重启后的那一轮）。

    `--self-updated` 是这条链上的刹车：带上它即表示"这一轮已经是重启后的新一轮"，
    `hand_off_self` 见到就不再换、不再重启（否则收尾那份标记会让重启无限套娃）。
    重启起不来（解释器不可执行等）时**如实警告并继续**——那一轮按**已经换好的**新脚本继续跑
    本来也对，不得把一次重启失败报成整批失败。
    """
    try:
        os.execv(sys.executable, [sys.executable, script, *sys.argv[1:], *extra])
    except OSError as e:
        print(f"警告: 已换上新版取规范脚本，但重启失败({e})——本轮的取文件照旧、按已换上的新版继续",
              file=sys.stderr)


def _leave_handoff_note(target):
    """把"待换的新版本在这儿"留给**下一次运行**（判定与消费见 `hand_off_self`）。

    **只在换不动真身时才写这条标记**：真身与 `target` 同一个目录时它压根不写（那种情形本脚本
    自己就换得动，`_take_over_self` 已就地换成、并当场重启）；真身读不到/不是本轮这份文件、
    或真身只读换不动时，新版本也只能落在别处（落点根下、`tmp/`），才需要下一轮来接这一棒。
    """
    note = f"{_this_file()}{SELF_HANDOFF_SUFFIX}"
    try:
        _ensure_writable(os.path.dirname(note), note)
        with open(note, "w", encoding="utf-8") as fh:
            fh.write(target + "\n")
        _chmod_report(note, _WRITABLE_FILE_MODE)
    except OSError as e:
        print(f"警告: 新版本已取到，但留不下待换的标记({e})——本轮的取文件照旧；"
              f"手工把 {target} 换过来即用上", file=sys.stderr)
        return
    print(f"说明: 新版本落在一处、但换不动本轮这份脚本，标记已留在 {note}；"
          "下一轮运行读到它即自动换上并按新脚本的清单口径取全", file=sys.stderr)


def _self_update_candidates(out_dir, cwd):
    """新版本脚本**可以落在哪几处**，按次序产出 `(落盘路径, 说明)`。

    说明里带后缀 `（= 真身）` 表示**它本身就是真身**——那种落法拷过去即已成事
    （见 `_take_over_self`），不必再经交接文件这一棒。

    **按次序**取，**先看真身**：

    判据是**写位**而不是"这是哪个平台的哪个目录"：同一条规则在两种跑法下都成立
    （项目里的源码、与落点里那份入口），而平台名一写进来就变成环境相关的事实
    （见 `shared_cache_dir` 对"落点只有一处"的同一层取舍）。

      * **真身那份（`sys.argv[0]`）所在的目录可写** → 落在它旁边
        （`.<真身名>.<pid>.update`）：这是"下一轮会读到的那份"自己，最快也最合适的一处
        （直接跑、经壳调起都走这一条：两个入口都用 `exec`/绝对路径调这份逻辑代码，
        `sys.argv[0]` 就是真身——见 `specs/general/script.adoc`「跨环境脚本」）；
      * **真身读不到**（`sys.argv[0]` 不是一份真实文件、如 `python3 - < x.py` 或壳给的临时副本）
        ——那时的真身是落点根下那份，故**直接落在落点根下，用它的文件名**：拷过去即已成事；
      * 前两处都不可写（只读挂载、非属主）→ 工作目录 `tmp/` 兜底；三处都不可写才返回 None，
        那时**不落盘、如实警告**，本轮照旧把规范副本取到手。

    第二、三处**都不是真身**，故要留交接标记（`_leave_handoff_note`）交下一轮去换。

    **只产出"看着能写"的那几处**（判据同下）；写位是按 `os.access`/"最近可写的祖先"估的，
    与真实可写性不总一致，故**真正落盘由 `update_self` 逐处试**——第一处写失败时后面那几处
    可能写得进去（本仓库实证：祖先可写、而 `tmp/` 这一级建不出来），那时"无处落盘"是假结论。
    """
    real = _real_script()
    candidates = []
    if real:
        candidates.append((os.path.dirname(os.path.abspath(real)), os.path.basename(real), True,
                           "真身所在目录"))
    # **读不到真身时落点根下那份就是真身**（见 `_real_script`），故 `is_real` 跟着它走：
    # 标错成"不是真身"时，落下去的名字是**原样文件名**（不带 `.update` 尾巴）、下面那句
    # 待换标记写不写得进也没有人去核——落点根的上一级（家目录下的那一层）可写而落点根
    # 不可写时，标记写不进去、原样文件名又把**正在跑的这份脚本**原地覆盖掉：`exec` 读到的
    # 是一个还没写完的文件（本机实测：`AttributeError` 指向源码中间那一行、路径还是落点里
    # 那份）。而它标对成"真身"时，落下去的是中转名、标记也是下面那句"写不进去就明说"。
    candidates.append((install_scripts_dir(), os.path.basename(INSTALL_SCRIPTS[0]),
                       real is None, "落点根下"))
    candidates.append((os.path.join(cwd, SELF_TMP_DIR), os.path.basename(INSTALL_SCRIPTS[0]),
                       False, "工作目录 tmp/ 下"))
    for on_dir, name, is_real, kind in candidates:
        # 判据是**这一处自己**写不写得进去，而**落盘仍落在本来的位置**——借祖先的写位把文件
        # 落到祖先里，等于把"下一次会读到的那份"放到一个谁也不会去读的地方。
        #
        # `_first_writable_dir` 用来判"**已经存在**的那一段"可写（`/usr/local/bin` 那种
        # 看着能写、实际不能的目录由此挡掉），而这一处**可能还没建出来**（落点根下、`tmp/`
        # 都是本轮现建的）：未建出来时按"最近的已存在祖先可写即算这一处可写"判——建不建得成
        # 由真正落盘那一步说了算（失败即如实警告，见 `update_self`）。
        if os.path.isdir(on_dir):
            writable = os.access(on_dir, os.W_OK)
        else:
            writable = _first_writable_dir(on_dir) is not None
        if not writable:
            continue
        suffix = f".{name}.{os.getpid()}{SELF_UPDATE_SUFFIX}" if is_real else name
        where = f"{kind}（= 真身）" if is_real else kind
        yield os.path.join(on_dir, suffix), where


def _first_writable_dir(directory):
    """`directory` 及其最近的已存在祖先里**第一个当前可写**的（没有则 None）。

    写位在**真正要落盘时**才探测：文件系统级只读（`/usr/local/bin` 一类）不靠权限位体现，
    看权限位会以为写得进去、真写时才失败（那条失败会以警告的形式出现在每一次运行里）。
    """
    node = os.path.abspath(directory)
    while True:
        if os.path.isdir(node) and os.access(node, os.W_OK):
            return node
        parent = os.path.dirname(node)
        if parent == node:
            return None
        node = parent


def hand_off_self():
    """把**上一轮留下的新版本**换成自己，然后照旧跑下去（带上原样的参数与退出码）。

    这是自更新的**兜底路径**，不是常规路径：常规路径里脚本自己就换得动、当轮即重启（见
    `_take_over_self`），压根不写这条标记；只有**真身读不到、或真身换不动**（只读挂载、非属主）
    时才留下标记，由"能写的下一次"来接这一棒。

    新版本在哪不用环境变量传（**子进程改了环境变量，调起它的壳读不到**——本仓库实证：
    壳那条路读 `STALE_SELF_PATH` 永远为空）：本脚本把自己的路径 + 后缀（`SELF_HANDOFF_SUFFIX`）
    写成一个**同目录的文件**，下一次运行（无论是壳再调一次、还是本脚本自己重启）读到它即换。
    写成文件还有个副作用是对的——"待换的新版本"这件事因此**跨进程可见**，重跑一次就能接上。

    判据是 `os.replace`/拷贝换得动：换不动（只读挂载、非属主）就**如实警告并继续**，守住既有口径
    ——"文件已取到"与"权限改不动"是两件事，不得把一个可自愈的情形报成失败（同 `_make_read_only`）。
    """
    note = f"{_this_file()}{SELF_HANDOFF_SUFFIX}"
    if not os.path.isfile(note):
        return
    try:
        with open(note, encoding="utf-8") as fh:
            fresh = fh.read().strip()
    except OSError as e:
        print(f"警告: 读不到上一轮留下的新版本路径({note}): {e}", file=sys.stderr)
        return
    if not fresh or not os.path.isfile(fresh):
        _discard_handoff_note(note)
        return
    if "--self-updated" in sys.argv:
        # 重启过来的这一轮：文件已经换过，剩下的"新版本路径"记一笔提示即可
        _discard_handoff_note(note)
        return
    if _real_script() != _this_file():
        # 真身不是本轮这个文件：**不在脚本里代它重启**——那会把调用方的排布改掉
        # （见 `_take_over_self`）。标记留着，真身下次跑起来自然接上。
        print(f"说明: 新版本({fresh})等真身下次跑起来时自己接上——本轮这一份不是它在用的那一份，"
              "不在脚本里代它重启", file=sys.stderr)
        return
    # 与 `_take_over_self` 同一条前提：**要拷过去的那份读得成一整份才换**。标记指向的
    # 新版本同样可能是写到一半/被截断的那一份（落盘那一步自己也可能被打断），换上去即把
    # `exec` 的目标换成半份源码——兜底路径与常规路径必须是同一道闸。
    if not _readable_as_script(fresh):
        print(f"警告: 上一轮留下的新版本({fresh})读不成一份完整的脚本（多半还在写、或已被截断）"
              "——本轮不换、按本地这一份继续；重跑一次即可", file=sys.stderr)
        return
    try:
        # 同 `_take_over_self`：真身多半带着收尾收紧留下的只读位，先补写位再换（补位只为
        # 换这一步，重启后的那一轮收尾收回）——不补位时只读位把它拒掉、标记永远消费不掉，
        # "重跑一次即用上"就成了每轮复发的死循环（本仓库实测：Windows 上每轮 [Errno 13]）。
        _chmod_report(_this_file(), _WRITABLE_FILE_MODE)
        shutil.copyfile(fresh, _this_file())
        os.chmod(_this_file(), os.stat(_this_file()).st_mode | stat.S_IXUSR)
    except OSError as e:
        print(f"警告: 已取到更新的取规范脚本({fresh})，但换不上去({e})——本轮按本地这一份继续；"
              f"重跑一次、或手工把它换过来即用上（见 specs/general/script.adoc「跨环境脚本」）",
              file=sys.stderr)
        return
    _discard_handoff_note(note)
    print("更新: 已换成上一轮取到的新版取规范脚本，本轮按它的清单口径取全", file=sys.stderr)
    _restart_with(_this_file(), "--self-updated")


def _discard_handoff_note(note):
    """用过即清（读不到/删不掉都只当它不在，不得因此中断一轮取文件）。"""
    try:
        os.remove(note)
    except OSError:
        pass


def _clean_self_tmp(cwd, keep=()):
    """把上次"更新自身"留在工作目录 `tmp/` 里的旧副本清掉。

    清理**只碰本脚本自己放进去的那几份**（`SELF_UPDATE_SUFFIX` 结尾的中转件，以及落点里不带
    后缀、本轮被复制到 `tmp/` 那一份，由调用方经 `keep` 给出全路径）：清理本身是破坏性动作，
    脚本不做"顺手清空 `tmp/`"这种事（见 specs/core/execution.adoc「破坏性操作」）。边界判据
    只有一条——**目标是 `listdir` 列出的那一项、且名字/全路径在白名单里**；不拼外部输入，故
    不存在 `../` 或绝对路径这类越界面。`tmp/` 自身是符号链接时整条跳过——那种情形下"落点还在
    `tmp/` 内"只是字面上成立，实际删的是链接指向的外部目录（见 specs/general/script.adoc「安全」）。

    **不带后缀的那份不能按名字认**：`tmp/` 下同名的 `fetch-specs.py` 可能是用户从落点复制过来
    参考/试跑的一份普通文件（多项目共用落点、只有它会带这个短名），按名字删会把人的东西静默删掉
    ——上一版由清理脚本的两步确认兜住这一步，现在没有确认，故判据改成"只认本轮自己认得的那一份"
    （`keep` 里的全路径），其余同名的**一律不碰**。

    不借外部的清理脚本：清理脚本是引用方项目自己的东西，本脚本在自己的工作目录里不该假定
    它在、更不该按"先找它、找不到再自己删"分两条判据（同一件事两套实现必然漂移）。

    **本轮新写的那几份不清**：它们可能就是调用方的壳正要换上去的源（删了等于把刚做好的事抹了），
    故本函数只清**运行前已存在**的旧副本——由调用方在进入本轮、取回新版本**之前**调用。
    """
    tmp = os.path.join(cwd, SELF_TMP_DIR)
    if os.path.islink(tmp) or not os.path.isdir(tmp):
        return
    protected = {os.path.abspath(p) for p in keep}
    for name in os.listdir(tmp):
        victim = os.path.join(tmp, name)
        if not (name.endswith(SELF_UPDATE_SUFFIX)
                or os.path.abspath(victim) in protected):
            continue
        if os.path.isdir(victim) and not os.path.islink(victim):
            continue                # 同名的是目录：不是本脚本落的那几份，不碰（rmtree 是另一件事）
        try:
            os.remove(victim)
        except OSError:
            pass


def download_one(base, rel, out_dir, keep, total=0):
    """取一份文件、按**内容**决定落不落盘。返回 (rel, 状态, 说明)。

    `total` 只用于进度行的分母（0＝未知，不印分母）；进度行是本函数唯一的对外输出，
    不另返回一份"人看的文本"——同一件事两个来源必然漂移。
    

    状态取值：`new`（本地没有，新落盘）/ `updated`（远端内容不同，已刷新）/ `same`
    （内容一致，不动）/ `keep`（`--keep` 下本地已有非空，未核内容）/ `fail`。

    **默认以远程为准**（安装脚本会更新，重复执行安装时须能拿到最新的一份）：先把远端内容
    取到内存、与本地逐字节比较，不同才落盘。放弃"本地已有就跳过"是因为它把安装的**结果**
    绑在"本地以前取过什么"上——远端修好了、加了一节规范，重复执行安装仍旧什么都不做
    （本仓库实证：安装规则与抓取脚本本身都在持续更新）。判据因此是**内容**、不是时间。

    **先取到内存、再原子落盘**（临时文件 + `os.replace`）：直接以 `wb` 覆盖既有文件时，
    取到一半失败会把原本完好的本地副本截断成半份——那比"没更新"更坏（副本看起来在、
    内容却是坏的）。原子替换保证**要么整份新内容、要么原样保留旧内容**；再加上"取回失败
    即保留本地那一份、只报失败"，故脚本在任何一次失败下都不会把副本变小或变没。

    **注意原子替换抵不住的那条路径（本仓库实证）**：调用方若用 `fetch-specs > tmp/x.adoc`
    把**落点里的某一份文件**当成命令的 stdout（重定向先清空目标、再执行命令），失败时
    命令没写出新内容——本地那份被 shell 截断成 `0 B`，且 `0 B` 在后续任何 `open()` 里
    都读得通、不像"没有"。这是调用方的用法问题，故：①判据取"本地**存在**"而不是"本地
    非空"（如上），`0 B` 那份同样算"以前取到过的那一份"、失败时照样只报失败、不被当成
    "新取"；②输出里如实写明失败项"本地已有那一份原样保留"，让 `0 B` 的成因一眼可查。

    **落点取完即只读**（`_make_read_only`）：落盘前先用 `_ensure_writable` 把本脚本为
    "写这一份"所需的写位补回来（上一轮取完已收紧成只读），写完再 `_make_read_only`
    收紧回去——只读**不挡更新**，它挡的是"落点被就地改过"。

    `--keep` 恢复旧的增量语义（本地已有且非空即不取、只补缺失项）：需要"不动我本地那份"
    时用；要最新内容按默认走即可。
    """
    started = time.monotonic()
    dest = target_path(out_dir, rel)
    # 本地已有那份（不是"非空"那份）：判据是**本地存在**——空文件同样是"以前取到过的那一份"
    # 的位置，取回失败必须把它保住（否则 `> dest` 截断留下的空文件会被当成"本地没有"，
    # 失败一次即把副本变成 `0 B`，而 `0 B` 的文件在任何 `open()` 里都读得通、不像"没有"）
    before = local_bytes(dest) if os.path.isfile(dest) else None
    if keep and before:
        _progress(total, rel, "保留", f"{_size(len(before))}（--keep：不动本地那份）",
                  time.monotonic() - started)
        return rel, "keep", "已存在（--keep）"
    last_err = None
    for attempt in (1, 2):          # 失败重试一次，避免偶发抖动让整批失败
        try:
            data = fetch_text(base, rel).encode("utf-8")
            if before is not None and data == before:
                _progress(total, rel, "未变", f"{_size(len(data))}（与远程一致）",
                          time.monotonic() - started)
                return rel, "same", f"{_size(len(data))}（与远程一致）"
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            _ensure_writable(out_dir, dest)
            tmp = f"{dest}.part"
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, dest)
            _make_read_only(dest, is_dir=False)
            _progress(total, rel, "刷新" if before is not None else "新取", _size(len(data)),
                      time.monotonic() - started)
            return rel, ("updated" if before is not None else "new"), _size(len(data))
        except (OSError, http.client.HTTPException) as e:
            # 网络类错误统一按 OSError 处理；`HTTPException`（IncompleteRead/BadStatusLine）
            # 在下面再兜一次——`fetch_text` 已把网络层归一成 OSError，这里兜的是"别的调用点
            # 将来直接拿 `http.client` 抛出的异常"这一路，**单个文件绝不该掀掉整批**
            # （掀掉整批的后果是收尾那段收紧一次都不跑，落点留在可写态，见 `fetch_text`）
            last_err = e
            try:
                if os.path.exists(f"{dest}.part"):
                    os.remove(f"{dest}.part")
            except OSError:
                pass
            if attempt == 1:
                # 重试也是"明细"的一部分：卡在同一个文件上重试时，人要知道是哪一份、为什么
                _progress(total, rel, "重试", str(last_err), time.monotonic() - started,
                          counts=False)
                continue
            break
    detail = (f"{last_err}（本地已有那一份原样保留）" if before is not None
              else str(last_err))
    _progress(total, rel, "失败", detail, time.monotonic() - started)
    return rel, "fail", detail


def fetch_install_scripts(base, out_dir, keep, total=0):
    """把安装脚本一并取到落点**根下**。返回与 `download_one` 同形的结果列表。

    清单由 `INSTALL_SCRIPTS` 给出（相对来源根，本仓库里就是 `script/` 下那几个），
    落点里**只保留文件名**（`<落点根>/fetch-specs.py`）——目录层级是来源侧的排布，
    照搬会在落点里多出一层 `script/`，且下载来的入口按逻辑代码的相对位置取同目录的
    兄弟文件（见 `fetch-specs.sh` 的 `dirname "$0"`），多一层即整组取不到。
    `--no-scripts` 时调用方不调本函数。语义与规范副本一致：**以远程为准**、失败保留
    本地已有那一份（判据与理由见 `download_one`——同一套"内容不同才落盘 + 原子替换"）。
    """
    results = []
    for rel in (*INSTALL_SCRIPTS, CONFIG_IN_SCRIPTS_DIR):
        results.append(download_one(base, rel, out_dir, keep, total))
    # 执行位不在这里补：本函数的返回结果与"补位"无关，且 `--no-scripts` 时整组不跑
    # （那里正是漏补的形态），统一由 `ensure_landing_executables` 在每轮收尾无条件补
    return results


def ensure_landing_executables(out_dir):
    """把落点根下的安装脚本入口**逐个**补上可执行位——与"这一轮取了几个文件"无关。

    补位动作**必须独立于落盘分支**（本仓库实证的失效形态）：`_ensure_executable` 原先只挂在
    `fetch_install_scripts` 里、只在 `download_one` 走 `new`/`updated` 分支时被调用，于是
    `--no-scripts`（整组跳过）以及"内容一致（`same`）"的那一轮都没有人补位——落点里那份
    入口的执行位一旦不是 555（取回的是字节、不带文件模式；也含用户手动降级、旧版本留下的
    落点），之后每次运行都停在 `444`，而 `444` 看起来与"入口也在只读树里"完全一样、
    无从发现（"下次重装直接跑落点里的入口"就此失效）。

    故本函数在**每一轮收尾**无条件跑一遍：判据是"落点根下**应当**能直接跑的那几个"
    （名单＝`ENTRY_SCRIPTS`，与"哪个是入口"同源——`_ensure_executable` 自己按它筛），
    不是"这一轮落了哪几个盘"。
    """
    for rel in ENTRY_SCRIPTS:
        _ensure_executable(target_path(out_dir, rel), rel)


def _ensure_executable(dest, rel):
    """给落点里的**入口**补上可执行位——**落点里的那份也要能直接跑**。

    本仓库里 `fetch-specs.sh` 带可执行位（见 specs/general/script.adoc「入口脚本须能直接
    执行」），但 HTTP 取回的是字节、不带文件模式，落点里那份默认是 `0644`：入口「安装与更新」要
    "下次重装直接跑落点里的入口"就会失败。

    **只补入口，不给逻辑代码"顺手"补位**（取值面见 `ENTRY_SCRIPTS`）：逻辑代码是入口
    "按同目录相对位置取到的兄弟文件"（见 `fetch-specs.sh` 的 `dirname "$0"`），不是给人
    直接敲的命令；给它补位会让落点里看起来有好几个"命令"、而落点里唯一的入口是入口脚本
    （见 specs/general/script.adoc「入口脚本须能直接执行」——一条逻辑代码 + 各平台薄入口）。
    `.bat` 在 Windows 上按关联执行，不靠权限位。

    **只加不减**（已有执行位不动，也不去"收紧"任何文件的权限）；补位后按"只读树"重新取
    权限，让"入口能跑"与"落点只读"同时成立。

    **调用点**在 `ensure_landing_executables`（每轮收尾无条件跑），不在 `download_one` 的
    `new`/`updated` 分支里——那里的"没落盘就不补位"正是上面那条失效形态的成因。
    """
    if rel not in ENTRY_SCRIPTS:
        return
    try:
        mode = os.stat(dest).st_mode
        if not mode & stat.S_IXUSR:
            # 权限补不上（只读挂载、Windows 等）不该把"取到了文件"报成失败
            _chmod_report(dest, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        pass
    # 收紧为**只读 + 可执行**：补位后重新按"只读树"取权限，让"入口能跑"与"落点只读"同时成立
    _make_read_only(dest, is_dir=False)


def _make_read_only(path, is_dir=False):
    """把一个文件或一棵目录树收紧成**只读**（目录去掉写位、文件只留读位）。

    **效力按平台分**（判据与实测见脚本头部「已知限制」的 Windows 一条，此处不复述理由）：
    POSIX 上"目录没有写位＝不能在其中增删改名"成立；**Windows 上只有文件那一半成立**，
    目录的增删改名拦不住（READONLY 属性对目录不阻止 `DeleteFile`/`CreateFile`），
    另一半靠规范约束——**不得**把"不能在其中增删改名"读成全平台成立。

    这是"落点取完即只读"的执行体（口径见脚本头部「落点」与「安全保证」）：
      * **目录**取 `_READ_ONLY_DIR_MODE`——POSIX 上没有写位就**不能在其中增删改名**（新建文件、
        删除文件、重命名都要目录写位），但"进入 + 列出 + 读其中的文件"仍然可用；
      * **文件**在 `_READ_ONLY_FILE_MODE` 上加**它自己已有的执行位**——入口脚本先去写位、
        **保留执行位**（否则"落点里的入口也要能直接跑"与只读互相打架，二者必须同时成立）。
        执行位取自当前权限、**不按扩展名重判**：补执行位是 `_ensure_executable` 的事
        （判据在那一处），本函数只负责"去掉写位"这一件事——同一件事两个判据即两处真源。

    **权限补不上不算"取文件失败"**（单点抛错由 `_chmod_report` 吞掉，与
    `_ensure_executable` 同口径）：只读挂载、Windows、或用户不是文件属主时 `chmod` 会失败，
    而"文件已取到"这件事仍然成立——报成失败会让调用方把一次成功当失败。

    **但"收紧"本身不能静默**：函数返回**没改成只读的节点数**，调用方按它出警告——用户口径
    要的正是"文件本身下载后要变成只读"，只把这句话写进注释、实际没改成，等于本条收益为零；
    静默时调用方与人都以为落点已只读（本仓库实证口径：判据不能只活在一句声明里）。
    返回 0 即落点确已只读；非 0 时调用方**保留落点、照常取文件**，只把"没收紧"如实说出来。
    """
    failed = 0
    if is_dir:
        # 自底向上：先把内容收紧，再收紧目录本身（顺序反了会因目录已无写位而改不动内容）
        for dirpath, dirnames, filenames in os.walk(path, topdown=False):
            for name in filenames:
                one = os.path.join(dirpath, name)
                if not _chmod_report(one, _read_only_file_mode(one)):
                    failed += 1
            for name in dirnames:
                if not _chmod_report(os.path.join(dirpath, name), _READ_ONLY_DIR_MODE):
                    failed += 1
            if not _chmod_report(dirpath, _READ_ONLY_DIR_MODE):
                failed += 1
    else:
        if not _chmod_report(path, _read_only_file_mode(path)):
            failed += 1
    return failed


def _read_only_file_mode(path):
    """只读文件的权限位：`_READ_ONLY_FILE_MODE` + 该文件**已有的**执行位（见 `_make_read_only`）。"""
    try:
        return _READ_ONLY_FILE_MODE | (os.stat(path).st_mode
                                       & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    except OSError:
        return _READ_ONLY_FILE_MODE


def _chmod_report(path, mode):
    """`chmod` 一次，返回是否改成了——**不抛**（单个文件改不动不该中断整批收紧）。

    调用方按"这一处改没改成功"决定要不要出警告（见 `_make_read_only`）：权限位改不上
    与"文件没落盘"是两件事，不能因为一个 `chmod` 抛错就把整批收紧停在那里。

    平台边界：Windows 上 `os.chmod` 只切只读属性、无 POSIX 权限位语义，故这里返回 `True`
    不等于"目录真的写不进去"——效力边界见脚本头部「已知限制」的 Windows 一条。
    """
    try:
        os.chmod(path, mode)
        return True
    except OSError:
        return False


def _is_within(node, stop):
    """`node` 是否**真的**在 `stop` 之内（路径边界，不是字符串前缀）。

    `node.startswith(stop)` 是字符串前缀、不做路径分段边界（本仓库实证）：
    `<落点>-backup` 会被判成在 `<落点>` 之内——
    两个目录只是名字前面重合，前者并不是落点的一部分。此判据误报时的后果不是"报错"而是
    **静默放权**：给落点旁边的兄弟目录补回写位，而"落点只读"这句话没人再核对。
    故按路径分段比：`os.path.commonpath` 相等才算在内（commonpath 已按分段归一，
    `/a/bc` 与 `/a/b` 得到 `/a`、不相等）。

    `OSError` 按"不在内"处理：不同盘符（Windows 的 `C:` 与 `D:`）比较时 commonpath 会抛错，
    那本来就说明两者不在同一条路径上；此时**不补位**是保守的一侧（补不上写位最多落盘失败并
    如实报错，多补一处写位才是越界）。
    """
    try:
        common = os.path.commonpath([os.path.abspath(node), os.path.abspath(stop)])
    except (OSError, ValueError):
        return False
    return common == os.path.abspath(stop)


def _ensure_writable(out_dir, dest):
    """把"本脚本写这一份"所需的写位补回来——上一轮取完已把落点收紧成只读。

    **只补必要的那几处**：目标文件所在的那条链上的目录（`out_dir` 到 `dest` 的父目录）
    补回用户写+执行位，目标文件（若已存在）补回用户写位。**只加不减**的例外正在此处——
    它不改变"落点对外是只读的"这一事实：补位只为落盘这一步，写完由 `_make_read_only`
    立刻收紧回去（见脚本头部「落点」）。

    Windows 上 `chmod` 基本无语义（`os.chmod` 只切只读位），故整段吞掉 OSError：
    "补不上"不等于"写不了"，真写不了时随后的写操作自会报错、由 `download_one` 如实报失败。
    """
    parent = os.path.dirname(dest)
    node = os.path.abspath(parent)
    stop = os.path.abspath(out_dir)
    while node and node != stop and _is_within(node, stop):
        _chmod_report(node, _WRITABLE_DIR_MODE)
        node = os.path.dirname(node)
    _chmod_report(stop, _WRITABLE_DIR_MODE)
    if os.path.isfile(dest):
        _chmod_report(dest, _WRITABLE_FILE_MODE)


def install_scripts_dir():
    """安装脚本的落点：落点**根下**（不在来源槽里）。

    规范副本按来源分槽（换过 `--base` 的副本互不覆盖），但安装脚本**跨来源共用一份**
    ——"下载的东西一律只落这一个地方"这条要对得上：同一个人从哪个来源取，落点里都是
    同一份入口，下次重装直接跑它即可（见脚本头部「落点」）。
    """
    return os.path.join(shared_cache_dir(), *LANDING_REL)


def _user_home_dir():
    """**当刻的**用户个人目录——每轮现取、不写死、不缓存（用户口径见脚本头部「落点」）。

    为什么不能只用 `os.path.expanduser("~")`：它读的是 `USERPROFILE` 一类**环境变量**，而
    环境变量由**登录时**按注册表设上、进程内不会跟随——"个人目录被移到别处"（用户实际做法：
    把"我的文档"这类目录整体重定向到另一块盘，免重装丢数据）之后，同一个会话里读到的仍是
    旧的一份。故取值次序是：

      1. **问壳要**（仅 Windows）：`SHGetKnownFolderPath(FOLDERID_Profile)`——KnownFolder 的
         路径存在注册表里、由壳每次**现算**，改过即取到新值。用 `ctypes` 直接调，不为一个路径
         引入依赖；分岔判据是 `ctypes.windll` 在不在（`os.name` 跟着**跑脚本的解释器**走，
         与"这台机器是不是 Windows"不是一件事）；
      2. 取不到（非 Windows、壳那条路失败）→ 环境变量/`expanduser("~")` 那一套；
      3. 退路给出的值也只在**确实存在且不是根目录**时才算数——拿着一个"看着像家目录"的值去
         建落点，正是本条要防的"落到别处还不自知"；
      4. **壳答了、但答出的路径已不存在**（旧家目录刚被挪走）→ 按取不到论、**不退环境变量**：
         退回 `expanduser("~")` 恰好拿到"登录时设上的那条旧路径"，落点会退回被迁走的那一处。

    取不到时返回空串或原样的 `~`：**校验不在这里**，由 `shared_cache_dir` 统一判并报错
    ——"取不到"是一种失败，不是另选一处。
    """
    shell = _shell_known_folder("Profile")
    if shell is _SHELL_MISSING:
        return ""                         # 壳的答案已随迁移失效：不给退路，让调用方报错
    return shell or os.path.expanduser("~")


# FOLDERID_Profile：Windows 壳里"用户个人目录"这一个 KnownFolder 的 GUID
# （`{5E6C858F-0E22-4760-9AFE-EA3317B67173}`）。GUID 是系统侧的既定标识，不是可配取值。
KNOWN_FOLDER_PROFILE = "5E6C858F-0E22-4760-9AFE-EA3317B67173"

# 『壳答出了一个路径、但那个路径当下已经不存在』——与『壳说不出话』(None) 是两件事：
# 前者说明个人目录已经迁走、旧路径没了，此时退回环境变量只会拿回登录时的那条旧值。
_SHELL_MISSING = object()


def _shell_known_folder(name):
    """Windows 壳登记的 KnownFolder `name` 的**当刻**路径。

    三种返回：路径（已存在）／`None`（壳说不出话：非 Windows、壳不可用、HRESULT 非 0）／
    `_SHELL_MISSING`（壳答出了路径，但那路径当下已不存在——旧家目录被挪走了）。

    `SHGetKnownFolderPath` 取的是**注册表里此刻的值**（个人目录被重定向后即时可见），
    这正是不用环境变量的理由（见 `_user_home_dir`）。

    **"取不到"一律返回 `None`、不抛**：这条是**优先**取值、不是前置条件——壳不可用（精简镜像、
    服务账户、非 Windows）时交给退路，报错只在**退路也取不到**时由调用方给；在这里抛错会把
    一次可自愈的情形报成整批失败。返回前还要求它是**一个已存在的目录**（同 `shared_cache_dir`
    的判据）；答了却不存在的情形**不能**当成"没取到"交给退路（见 `_user_home_dir`）。
    """
    try:
        windll = ctypes.windll            # 非 Windows 上没有这个属性：这一句即分岔
    except AttributeError:
        return None
    if name != "Profile":
        return None                       # 只登记了这一处（见 `KNOWN_FOLDER_PROFILE`）
    # 出参是 `PWSTR*`：用 `c_void_p` 接地址、再 `cast` 成宽字符串。
    # 不用 `POINTER(c_wchar_p)`：那个写法把"指针的值"当成对象交给解释器管，壳分配的那块内存
    # 既不在 Python 的堆上、也没有类型信息，读出来是一串垃圾地址（本仓库实测：读到
    # `character U+1433bfa0 is not in range`）——`c_void_p` 只存地址，语义与 Win32 的
    # `PWSTR*` 完全一致。
    out = ctypes.c_void_p()
    try:
        hresult = windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(_guid_of(KNOWN_FOLDER_PROFILE)), 0, None, ctypes.byref(out))
        if hresult != 0:
            return None
        path = ctypes.cast(out, ctypes.c_wchar_p).value
    except (OSError, ValueError, AttributeError, ctypes.ArgumentError):
        # `ctypes.ArgumentError` 不是 `ValueError`：参数类型对不上时它直接漏出去，
        # 壳那条路就成了一次会把整批打断的失败。
        return None
    finally:
        # 壳分给我们的这块内存由我们释放（`SHGetKnownFolderPath` 的约定）；释放失败不作数
        if out:
            try:
                windll.ole32.CoTaskMemFree(out)
            except (OSError, AttributeError):
                pass
    if not path:
        return None
    return path if os.path.isdir(path) else _SHELL_MISSING


def _guid_of(text):
    """把 `{...}` 形态的 GUID 文本摊成 Win32 的 `GUID` 结构（16 字节、四段定长）。"""
    raw = uuid.UUID(text.replace("{", "").replace("}", "")).bytes_le
    return _GUID.from_buffer_copy(raw)


def shared_cache_dir():
    """落点所在的那一层目录：**用户的家目录**（每一轮现取，见 `_user_home_dir`）。

    **落点只有一处**（用户口径：不管什么系统、什么环境，都是用户家目录下
    `CACHE_HOME_DIR/CACHE_APP_DIR` 那一个路径），故这里不按平台另取一套缓存目录：
    家目录取不到时直接报错，由调用方如实说明卡在哪一步——**不静默换一个落点**：
    换落点等于让"副本在哪"变成环境相关的事实，入口文档写下的那一个路径就与实际的落点
    对不上了，"再运行一次即是更新"也无从核对。

    **判据要判"是不是真的家目录"、不能只判空串**（本仓库实证）：`HOME` 被设成空串时
    `os.path.expanduser("~")` 不会抛错，而是返回文件系统根——只判"空串或未展开的原样 `~`"
    会让副本静默落到根目录下的落点（正是上面要防的"静默换落点"）。故除空串与未展开的
    原样 `~` 外，还须拒掉根目录本身，且要求展开后的路径**确实是一个已存在的目录**
    ——三条任一不成立即按取不到家目录报错，不换地方。

    **取值只来自本节这一处、且每次调用都现取**（`_user_home_dir`）：落点因此永远是"这一轮
    个人目录所在的那一处"，个人目录被移走之后下一轮即跟着走——不在模块级算一次就存着用
    （那正是"写死"的另一副面孔：同一次运行里个人目录变了，落点却还停在上一次算出来的地方）。
    """
    home = _user_home_dir()
    if not home or home == "~" or os.path.abspath(home) == os.path.abspath(os.sep) \
            or not os.path.isdir(home):
        raise ValueError(
            f"本机取不到用户家目录（展开得到 {home!r}），无法定位用户家目录下的 "
            f"{LANDING_NAME}")
    return home


def cache_slot_dir(home_dir, base):
    """某个来源地址在落点里的专属子目录（按来源分槽）。

    换过 `--base` 时（站点挂了换同源镜像、内网走自建地址）取到的副本**内容不同却同名**，
    直接覆盖会把上一来源的副本悄悄改掉、也无法解释"为什么同一份规范这次不一样"。
    故按来源地址分槽：来源相同则命中同一份、来源不同则各存各的（见
    specs/general/dependency.adoc「构建可重现」——同一清单在任意环境应得到同一份内容）。
    散列按来源地址的规范形态（scheme + 主机 + 端口 + 路径）取值，`https://a.com` 与
    `https://a.com/` 落到同一槽。
    """
    parsed = urllib.parse.urlsplit(base)
    slot = parsed.netloc + parsed.path.rstrip("/")
    slot = re.sub(r"[^A-Za-z0-9._-]+", "_", slot).strip("_") or "default"
    return os.path.join(home_dir, *LANDING_REL, slot)


def resolve_out_dir(args):
    """定出本次落点：`shared_cache_dir()` 与两个落点常量拼出的那一处，其下按来源分槽。

    **不曾保留的备选做法**（撤掉它们正是本函数的全部内容）：按平台各取一套缓存目录、
    留一批换落点的参数与环境变量、缓存不可得或来源指向本机时自动退回项目内临时目录
    ——每一种都会让"副本在哪"变成环境相关的事实（理由与用户口径见脚本头部「落点」）。
    """
    return cache_slot_dir(shared_cache_dir(), args.base)


def main(argv=None):
    global _DONE, _PROMPTS_INDEX, _PROMPTS_INDEX_TEXT, _PROMPTS_TAKEN
    _DONE = 0
    args = parse_args(argv)
    base = args.base
    # `--probe`：入口拿它判「这个解释器跑不跑得起来」（见头部「解释器兜底」）。判据只是
    # **这一份脚本在这个解释器底下跑得起来**，故它到此为止：不换自身、不重启（入口每探一个
    # 候选就换一次脚本、重启一轮，是探测不该有的副作用），也不取任何东西——连清单都不取：
    # 清单要联网，装机时网络不通恰恰是最常见的形态，拿它当判据会把「没有可用 python」误报成
    # 「python 跑不起来」（脚本不联网就跑到这里，证明这个解释器能跑）。
    #
    # 它排在 `hand_off_self` **之前**、且只做一句判断就返回：探针走这两条路都会**写盘**。
    # `hand_off_self` 消费上一轮的交接标记（换脚本 + 当场重启），`resolve_out_dir` 在家目录
    # 取不到时去 `_shell_known_folder` 起一次子进程；探针在 `.sh` 入口那里每跑一次就跟着跑
    # 一次，`update_self` 中途失败留下的标记会被探针吃掉——"探一遍不换脚本"就此不成立
    # （本仓库实测：标记被消费、脚本却没换，下一次真跑才补上）。
    if args.probe:
        print(f"# 探针通过：{sys.executable}")
        return EXIT_OK

    # 口令入口的执行体（`<落点>/<口令>.sh <名>`）：只读落点里那一份、装配好打出来，
    # **不联网、不写盘、不换自身**——它排在自更新之前，正是为了这两条（点一次口令不该
    # 顺手把落点改一遍，也不该在断网时罢工）。
    if args.print_prompt:
        return print_prompt(args.print_prompt, args.landing)

    # 上一轮留下的新版本：先换上它、再照它的清单口径干活（见 `hand_off_self`）
    hand_off_self()
    try:
        out_dir = resolve_out_dir(args)
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return EXIT_USAGE

    if args.workers < 1:
        print("错误: --workers 至少为 1", file=sys.stderr)
        return EXIT_USAGE

    # **先更新自身、再照新清单取全**（见头部「取回与更新口径」）：脚本自己的清单解析口径若在
    # 远端变过，跑着旧脚本的这一轮只会照旧口径取——新东西静默不进副本（用户口径："更新自身
    # 避免有的没进索引"）。故这一步在**取清单之前**，且**换上了就当场重启、当轮即生效**
    # （用户口径：「更新的时候，就要及时生效吧？还等下一次？」）——`update_self` 只在
    # **没换成**（远端一致 / 真身换不动 / 无处落盘）时返回，那几种情形它已各自如实警告完毕。
    # 只在非 `--keep` 与 `--list` 时做（`--list` 是"只看清单、不下载"）。
    # 顺序即口径（**这一串的次序就是"更新顺序"本身**）：入口先认一个**跑得起来**的解释器
    # （`--probe` 走到早处即收工，见上），故到这里执行的一定是一份真能跑的 python；再**先更新
    # 自身**、拿**新的**自己算清单与索引；最后照清单取全（含清单以外的附随文件）。
    # 判据是"什么时候取索引用哪一份脚本"——用旧脚本来算，新增的文件名就静默不在索引里
    # （用户口径：「既然现在有规范的索引了」）。
    if not args.keep and not args.list:
        # 先清掉**上一轮**留下的旧副本（本轮的还没写，见 `_clean_self_tmp`）；
        # `keep` 只传本轮认得的那一份（`tmp/` 兜底落点上的同名中转件）——不带后缀的那份
        # 不能按名字认，否则用户从落点复制过来的同名文件会被静默删掉。
        tmp_fallback = os.path.join(os.getcwd(), SELF_TMP_DIR, os.path.basename(INSTALL_SCRIPTS[0]))
        _clean_self_tmp(os.getcwd(), keep=[tmp_fallback])
        update_self(base, out_dir, os.getcwd())

    # 这两份状态**每轮现算**：`update_self` 换上自己后当场重启、本轮由新进程从零开始，
    # 故到这里它们只属于这一轮（同一进程内跑两轮也不接上一轮的数，见 `manifest_targets`）。
    # 函数首行那句 `global` 是它们唯一的声明处（下面还有一处分派给 `manifest_targets`）。
    _PROMPTS_INDEX, _PROMPTS_INDEX_TEXT, _PROMPTS_TAKEN = None, "", set()
    try:
        targets, optional = manifest_targets(base)
    except Exception as e:                                  # noqa: BLE001 - 网络与解析都按同一路径报错
        print(f"错误: 取入口清单失败（{base}/{MANIFEST_FILE}）: {e}", file=sys.stderr)
        # 同一次失败里也要说清"本地那份还在不在"——只报"取清单失败"时，调用方无法判断
        # 落点里那份是"过期的旧副本"还是"根本没取到过"（见脚本头部「取回失败保留本地那一份」）
        print("说明: 本地落点里已有的那一份**原样保留**（本次未落盘任何文件）；"
              "要确认它是哪一版可对比远端内容，重试本脚本即可补取。", file=sys.stderr)
        return EXIT_USAGE

    # 顶层说明文件是"有则取"：取不到不算失败（仓库未放该文件时站点会回落到首页 HTML，
    # 由 fetch_text 判为取不到并跳过——不得把首页 HTML 当成"取到的说明文件"存进落点）
    if args.list:
        for rel in sorted(targets + optional):
            print(rel)
        print(f"# 共 {len(targets)} 份（必取）+ {len(optional)} 份（有则取），来源 {base}")
        print(f"# 落点: {out_dir}（用户家目录下的 {LANDING_NAME}）")
        scripts_dir = install_scripts_dir()
        for rel in INSTALL_SCRIPTS:
            print(f"{rel}  ->  {target_path(scripts_dir, rel)}")
        print(f"# 安装脚本 {len(INSTALL_SCRIPTS)} 份，落点根下: {scripts_dir}"
              f"{'（--no-scripts 时不取）' if args.no_scripts else ''}")
        if _PROMPTS_INDEX_TEXT:
            print(f"# 口令入口: {scripts_dir}（{PROMPT_COMMAND_SHELL_NAME} / "
                  f"{PROMPT_COMMAND_BAT_NAME}）；点名写法 "
                  + PROMPT_COMMAND_USAGE.format(name=PROMPT_COMMAND_NAME)
                  + "（可用名单由落点里 prompts/ 现算）")
        return EXIT_OK

    # `--force` 与默认同为"以远程为准"，此处只保留它的写法（与 `--keep` 相反）；
    # `--keep` 下 `download_one` 自己判"本地已有即不动"
    total = len(targets) + len(optional) + (0 if args.no_scripts else len(INSTALL_SCRIPTS)) + len(FOLLOWUP_FILES)
    # 开跑前先交代**这一轮取多少份、从哪来、落到哪**：一份都还没回来时这几行是唯一的
    # "它在干活"的信号；进度行的分子分母以这里的 `total` 为口径。
    started = time.monotonic()
    _flush(f"取规范开始：共 {total} 份（来源 {base}，落点 {out_dir}，并发 {args.workers}）\n")
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(download_one, base, rel, out_dir, args.keep, total)
                   for rel in sorted(targets)]
        # 按完成先后收结果（顺序不影响处置：结果按 `rel` 分类，不按落盘次序）
        for fut in concurrent.futures.as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as e:      # noqa: BLE001 - 单个文件任何异常都不得掀掉整批
                # 兜底：`download_one` 已把网络/解析异常归成 `fail` 分类，能到这的只剩
                # 实现层意外（如 `fetch_text` 漏归一的异常类型）。**仍按失败项如实报**，
                # 且**照旧往下走去收紧落点**——收尾被跳过时落点会留在可写态而无人察觉
                # （本仓库实证：截断响应逃逸 `IncompleteRead` → 整脚本带 traceback 退出、
                # 落点根停在 `755`），那恰好把"取完即只读"这条在最需要它的一轮里丢掉。
                # 这里拿不到 `rel`（future 与结果一一对应、但异常不带 rel），故按 "?" 报
                # 由下游"失败项数"体现——重跑一次即可从 `[失败]` 行看到具体是哪一份。
                # 这一格照旧算**这一份的终态**（它不会再回来），分子要跟着走——否则收尾的
                # 「共取 N 份」与最后一行的 `[n/total]` 对不上。
                _progress(total, "?", "失败", f"取回时发生意外异常: {e!r}", 0.0)
                results.append(("?", "fail", f"取回时发生意外异常: {e!r}"))
    for rel in optional:
        try:
            results.append(download_one(base, rel, out_dir, args.keep, total))
        except Exception as e:          # noqa: BLE001 - 同上（README.adoc 等有则取项）
            _progress(total, rel, "失败", f"取回时发生意外异常: {e!r}", 0.0)
            results.append((rel, "fail", f"取回时发生意外异常: {e!r}"))
    # 安装脚本落**落点根下**（不在来源槽里）：这是"下载的文件一律只落这一个地方"里
    # 「安装脚本」那一半——取完规范就不必再手工下载一遍入口（见脚本头部「落点」）。
    # 清单在 `INSTALL_SCRIPTS`，与本脚本同处 `script/`；`--no-scripts` 时整组跳过。
    if not args.no_scripts:
        results.extend(fetch_install_scripts(base, install_scripts_dir(), args.keep, total))
    # 索引**每轮都核一遍**：它不在清单里，`update_self` 又只在脚本自己变了时才动手——不单列
    # 这一步时，"每轮取最新"只覆盖到规范副本与脚本，索引会停在上一次脚本变动的那一版
    # （看着齐全、其实少了几份，见 `refresh_lagging_followups`）。
    # 它排在这一串的**最后**、算它的也是**这一份已经更新过的自己**：它列着什么，取决于
    # "谁在算"——步骤提到前面，读者按站点找文件时看到的那一份就还是旧脚本算出来的
    # （新增/改名的文件静默不在索引里）。`--list` 不取文件，故也不取它。
    # 清单里列着的提示词**这一轮取到了哪几份**：判据是这一轮的结果，不是"落点里在不在"
    # ——落点只进不出、跨来源共用，按它在不在判会把上一轮的结果读成本轮的。失败项不进集合
    # （"远端没有这一份"与"落盘失败"都以 `fail` 记，见 `download_one`）。
    _PROMPTS_TAKEN.update(r[0] for r in results
                          if _PROMPTS_INDEX and r[0].startswith(PROMPT_DIR + "/")
                          and r[1] != "fail")
    if not args.list:
        refresh_lagging_followups(base)
        # **口令入口**（用户口径：『没有命令 你不能加进去吗？就一句话的事情』）：提示词取到了
        # 但还得人肉复制，等于没取——故落点根下与各 agent 命令位各生成一份，`<口令> <名>` 即可
        # 把装配好的整段打给会话。生成与否取自"这一轮认不认得提示词那一层"（`_PROMPTS_INDEX_TEXT`），
        # 可用名单则由入口在运行时按落点现算。
        made, problems = write_prompt_entries(_PROMPTS_INDEX_TEXT)
        for line in problems:
            print(f"警告: 口令入口落盘失败 {line}——" + PROMPT_COMMAND_USAGE.format(
                name=PROMPT_COMMAND_NAME) + " 可能跑不了（其余照常）", file=sys.stderr)
        if made:
            print(f"口令入口: 已生成 {len(made)} 份（落点根下与 agent 命令位）——"
                  "口令 " + PROMPT_COMMAND_USAGE.format(name=PROMPT_COMMAND_NAME)
                  + " 即可把落点里那一份提示词装配好整段输出，不必再打开文件复制")

    # 落点取完即**只读**（见脚本头部「落点」与「安全保证」）：整个落点根（规范副本的来源槽
    # + 安装脚本）**一次收紧**——只收紧一部分时另一半仍是可写的，"落点是只读的"这句话
    # 对读者就无法核对。**收紧失败不算取文件失败**（`_make_read_only` 吞掉 OSError，
    # 与 `_ensure_executable` 同口径）：只读挂载、Windows 或非属主时改不动权限位，
    # 而"文件已取到"这件事仍然成立；`--no-scripts` 时只收紧规范副本那一侧（落点根下没有
    # 本脚本放进去的东西，但规范副本仍在）。`--keep` 下这个动作同样做：它收紧的是**只读状态**，
    # 与"这批文件要不要更新"无关（上一轮已收紧过时是幂等重设，不改变任何内容）。
    # 返回没改成只读的节点数：0 即落点确已只读；非 0 时下面的输出**如实警告**（见
    # 脚本头部「已知限制」——非特权调用方/只读挂载/Windows 上权限位可能改不动）。
    # `--keep` 下也要警告：只读树上若有人放开过权限，"不动本地那份"不等于"它还是只读的"。
    unhardened = _make_read_only(install_scripts_dir(), is_dir=True)
    # 入口执行位**每轮无条件补一次**，且必须在整棵树收紧**之后**：收紧只"去掉写位"、
    # 保留既有执行位（`_read_only_file_mode`），故补位与收紧的先后不影响结果，
    # 但放在后面能让"落点根下那几个入口此刻真的能跑"这件事落在同一段收尾里、单个动作可核对。
    # 判据见 `ensure_landing_executables`：它与"这一轮落了哪几个盘"解耦——`--no-scripts`
    # 与"内容一致（same）"的那一轮同样要补。
    ensure_landing_executables(install_scripts_dir())

    fresh = [r for r in results if r[1] == "new"]
    updated = [r for r in results if r[1] == "updated"]
    same = [r for r in results if r[1] == "same"]
    kept = [r for r in results if r[1] == "keep"]
    failed = [r for r in results if r[1] == "fail"]

    # 收尾先说一句**总账**：进度行是逐份的流水账，看完那一屏需要一行能核对"这批是不是
    # 全取到了"的结论，它也是失败清单之前的第一眼。
    print(f"落点: {out_dir}")
    if not args.no_scripts:
        print(f"安装脚本: {install_scripts_dir()}（落点根下）")
    print(f"来源: {base}")
    print(f"共取 {len(results)} 份，用时 {time.monotonic() - started:.1f}s")
    if unhardened:
        print(f"警告: 落点有 {unhardened} 处**没能收紧成只读**"
              "（多为只读挂载、调用方非属主、落点所在目录已不可写，或 Windows）——"
              "「落点是只读的」这一条在这些环境下不由权限位保证，"
              "请按规范照旧只读、不改（见脚本头部「已知限制」）。", file=sys.stderr)
    else:
        print("落点已设为只读——项目只读、不改：不得改动落点里的任何文件"
              "（要改先显式放开权限，那一步刻意、可见、须自担后果）")
    if args.keep:
        # `--keep` 下"新取"是**没取回来**的那些（本地没有、只留了个空文件占位）：不并进
        # "已有保留"里，否则 `--keep` 结果会把"一份都没拿到"报成"全部保留"（本仓库实证）
        print(f"结果: 已保留 {len(kept) + len(same)}、新取 {len(fresh)}、失败 {len(failed)}"
              f"（共 {len(results)}；--keep：不动已取到的那些）")
        for rel, _, why in fresh:
            print(f"  [新取] {rel} -- {why}（本地原本没有）")
    else:
        print(f"结果: 新取 {len(fresh)}、刷新 {len(updated)}、内容一致 {len(same)}、"
              f"失败 {len(failed)}（共 {len(results)}；以远程为准）")
    if updated:
        for rel, _, why in updated:
            print(f"  [刷新] {rel} -- {why}")
    # 提示词那一半先核一遍（**在失败清单之前**）：少的那几份的本轮明细就混在下面的
    # `[失败]` 行里，结论写在明细前面才读得通（它是"要不要重跑"的那句话）。
    prompts_complete = report_prompts_missing(base)
    if failed:
        for rel, _, why in failed:
            print(f"  [失败] {rel} -- {why}", file=sys.stderr)
        print("提示: 失败项**保留本地已有的那一份**（本地原本没有才算真缺）、重试本脚本即可补取；"
              "失败项若显示为 `0 B`，先见脚本头部「原子替换抵不住的那条路径」"
              "（多为把落点里的文件当成命令 stdout 的用法所致）。", file=sys.stderr)
        return EXIT_INCOMPLETE
    if prompts_complete is False:
        # 没取全的提示词已在 `report_prompts_missing` 里按名字报过；这里只给一句结论。
        print("提示: 提示词没取全——重试本脚本即可补取（清单以提示词登记处为准）。",
              file=sys.stderr)
        return EXIT_INCOMPLETE
    if not fresh and not updated and not args.keep:
        print("说明: 清单内文件与远程逐字节一致，落点未改动（判据是内容，不是时间）。")
    if updated:
        print("提示: 本地副本**已被远程内容覆盖**（落点是本脚本自己的那份）——"
              "要留本地改动请先备份、或下次加 --keep。")
    print(f"规范已就绪：读取落点下的 {MANIFEST_FILE} 及其引用的 specs/ 规范，并持续遵守。")
    if _PROMPTS_INDEX:
        print(f"提示词已就绪：{_PROMPTS_INDEX} 登记的那几份在落点下的 "
              f"{os.path.dirname(COMMON_PROMPT_REL)}/（公共片段 {COMMON_PROMPT_REL} 与它们同处）"
              "——用哪一份就点名哪一份："
              + PROMPT_COMMAND_USAGE.format(name=PROMPT_COMMAND_NAME)
              + "（落点根下的 "
              f"{PROMPT_COMMAND_SHELL_NAME} / {PROMPT_COMMAND_BAT_NAME}），它把 `include::` "
              "就地装配好整段输出，直接当任务指令用；也可直接读落点里那一份，"
              "但那是**原始文件**、`include::` 尚未展开，须按公共片段的说明补齐后再执行。")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
