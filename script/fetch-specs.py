#!/usr/bin/env python3
"""
fetch-specs.py - 把本规范集合（AGENTS_COMMON.adoc + specs/）批量取到本地副本。

定位：
  规范常部署于外网、网络可能不佳，AGENTS_COMMON.adoc「网络不佳时取本地副本」建议先把入口与其 specs/
  取到本地副本再读取。本脚本就是那个"取"的抓手：**一次运行把本次会话要用的规范全部取全**，
  目标项目无需自己拼文件清单、也无需逐条下载。

  文件清单**从入口自身解析**（解析 MANIFEST_FILE 的加载调度器里登记的 specs/... 条目），
  故新增一份规范时**不需要改本脚本**、也不会漏取。取到的副本**落到用户路径下的唯一落点**
  （见下「落点」），不在每个项目里各存一份。

用法（在目标项目根目录执行，入口名随平台而异、只给脚本名即可）：
  fetch-specs                          # 取到落点（用户家目录下的 `<落点父目录>/<落点名>`，见下「落点」）
  fetch-specs --base <URL>             # 换规范来源（默认 https://agent.c332030.com，同源镜像可用）
  fetch-specs --keep                   # 保留本地已有的非空副本（不动已取到的那一份）
  fetch-specs --force                  # 同默认（保留写法，与 --keep 相反）
  fetch-specs --list                   # 只打印将要取的文件清单，不下载

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
  - **一次取全**：一次运行把入口与其 `specs/` 全部取回，调用方不必手拼逐条下载命令
    （清单从入口自身解析，见上「文件清单」）；
  - **默认以远程为准**：每份文件按"取回的字节与本地不同才落盘"核对，远端改过就刷新，
    故**重复执行即是更新**；`--keep` 才回到"本地已有即不动"；
  - **取回失败保留本地已有的那一份**：报错并如实报失败，**不得**把本地副本删掉换成没有；
  - **退出码**：0 成功、1 有文件没取到、2 参数或前置条件错误——非 0 就别把副本当已就绪；
  - **解释器兜底**：两个平台入口按次序探测解释器（Linux/macOS 先 `python3` 再 `python`；
    Windows 先 `py -3`、再 `python3`、最后 `python`），一个都没有时报一句错并退出非 0、
    **不静默继续**；此时**处置次序**是：**先按本平台既有的软件分发方式装一个 python 3**
    ——这是**人**的一步（或人已交互登录、能看见命令与报错的会话里 agent 的一步），入口**不得**代为安装运行时（改系统状态、要权限、对调用方不可预期）；
    **只装 python2 的发行版**（CentOS/RHEL 8 及更早、老 macOS 上 `python` 就是 python2）
    **不算"一个都没有"**——上一条的次序会取到它；
    不装运行时的替代路径是**直接读远程入口地址**——本规范在网络上就是这套文件；
    **不建议**改用 `curl … | python3 -`：**它同样要 python**。

环境变量：
  AGENT_SPECS_BASE   规范来源地址，等价于 --base（默认取仓库站点）
  STALE_SELF_PATH    已撤掉的旧形态（**留作反例，不再使用**）：本轮取到的新版本路径当时靠环境
                     变量交给调用方的壳——**子进程设的环境变量回不到调起它的父壳**（本仓库实证：
                     壳那条路永远读不到），故改成走文件：路径写在本脚本自己的路径 + `.handoff`
                     后缀的那个文件里，换不动真身时由下一次运行自己读、自己换、自己重启
                     （见下「交接文件」）。

落点（**只有一处**：用户家目录下的 `<落点父目录>/<落点名>`＝`CACHE_HOME_DIR`/`CACHE_APP_DIR`）：
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

== 输出（用户口径：「显示文件下载进度及其他明细，下载完成不要关闭窗口」）
  - **开跑先交代一轮的规模**：共取几份、来源、落点、并发（一份都还没回来时，这就是唯一的
    "它在干活"的信号）；
  - **每取完一份打一行进度**（`[3/27] 刷新 specs/stack/java.adoc -- 12.3 KB（1.2s）`，
    见 `_progress`）：份数、状态（新取/刷新/未变/保留/重试/失败）、字节、耗时——**逐份**、不攒到
    收尾，故卡住时看得见卡在哪一份；
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
import os
import re
import shutil
import stat
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid

DEFAULT_BASE = "https://agent.c332030.com"


class _GUID(ctypes.Structure):
    """Win32 `GUID`（与 `uuid.UUID` 同构的 16 字节，见 `_guid_of`）。"""
    _fields_ = (("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16), ("Data4", ctypes.c_uint8 * 8))


# 落点父目录：用户家目录下的这一层（落点只有这一个，不另按平台取目录）
CACHE_HOME_DIR = ".cache"
# 落点目录名：落点父目录下的这一层（`CACHE_HOME_DIR/CACHE_APP_DIR` 即那条用户路径）
CACHE_APP_DIR = "agent-specs"
# 入口 + 顶层说明文件；specs/ 下的文件从入口的调度器登记解析得到
MANIFEST_FILE = "AGENTS_COMMON.adoc"
OPTIONAL_FILES = ("README.adoc",)
# 与本脚本同处的安装脚本：一并取到落点**根下**（不在来源槽里）——跨来源共用一份。
# 用户口径是"下载的文件一律只落这一个地方"，故下载完就不必再来第二次；
# 薄壳也一并取回：只取逻辑代码时，落点里那份没法直接跑（入口层三件事见 specs/general/script.adoc）。
INSTALL_SCRIPTS = ("script/fetch-specs.py", "script/fetch-specs.sh", "script/fetch-specs.bat")
# 其中**入口**（各平台的薄壳）：落点取的字节不带文件模式，故取完给它们补回可执行位
# （见 `_ensure_executable`）。逻辑代码**不在内**——它不是给人直接敲的命令，
# 落点里唯一的入口是入口脚本（见 specs/general/script.adoc「入口脚本须能直接执行」）。
ENTRY_SCRIPTS = ("script/fetch-specs.sh", "script/fetch-specs.bat")
SPECS_REF_RE = re.compile(r"specs/[A-Za-z0-9_./-]+\.adoc")
TIMEOUT_SECONDS = 30
DEFAULT_WORKERS = 4
# "待换的新版本在哪"的交接文件后缀（写在**本脚本自己的路径**之后）：见 `hand_off_self`。
# 走文件而不是环境变量：**子进程设的环境变量回不到调起它的壳**（本仓库实证），
# 而"换掉自己并且还能接着跑"这件事必须跨进程可见。
SELF_HANDOFF_SUFFIX = ".handoff"
# 更新自身的工作目录：`tmp/` 下（临时产物见 specs/core/execution.adoc「临时产物」）。
SELF_TMP_DIR = "tmp"
# 新版本脚本的文件名后缀（与本轮真身同名不同后缀，见 `_self_update_candidates`）
SELF_UPDATE_SUFFIX = ".update"
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
# 明细」）。故不画进度条，只用**已取份数 + 状态 + 字节 + 耗时**这几项事实——它们与本轮
# 结果一一对应，人核对明细时不必再认第二套数字。
_PROGRESS_LOCK = threading.Lock()
# 本轮已取完的份数（进度行的分子；`main` 每轮开头清零，同一进程内跑两次不接着数）
_DONE = 0


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
                        help="规范来源地址（默认 https://agent.c332030.com）")
    parser.add_argument("--keep", action="store_true",
                        help="保留本地已有的非空副本（不动已取到的那一份、只补缺失项）")
    parser.add_argument("--force", action="store_true",
                        help="忽略本地副本、强制重取（与 --keep 相反，即默认行为）")
    parser.add_argument("--no-scripts", action="store_true",
                        help="只取规范副本，不把安装脚本（本脚本与其平台入口）取到落点"
                             "（脚本的**自身更新**不受它影响：那一件是本脚本自己、不是落点里的物）")
    parser.add_argument("--list", action="store_true",
                        help="只打印将要取的文件清单，不下载")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help="并发请求数（默认 4）")
    # 内部开关（不是给调用方用的参数）：自更新"换上了、自己重启"后由**本脚本自己**挂在
    # 命令行末尾，作为重启链上的刹车——`hand_off_self` 见到它就不再换、不再重启（防无限套娃）。
    # 写法隐去、不进 `--help`：它是实现细节，调用方加它只会跳过自更新这一版（见 `_restart_with`）。
    parser.add_argument("--self-updated", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def fetch_text(base, path):
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
        raise OSError("取回的是站点 HTML 页面（该路径在规范站点上不存在，站点回落到首页）")
    return text


def manifest_targets(base):
    """从入口自身解析要取的文件清单。

    入口（AGENTS_COMMON.adoc）的加载调度器**唯一登记**了全部公共规范文件，故清单以它为准：
    新增规范文件时它必然被登记，清单随之自动变全（手工维护清单的失效形态正是漏项）。
    返回 (清单, 缺失的可选文件)；入口文件本身必然在清单里。
    """
    text = fetch_text(base, MANIFEST_FILE)
    specs = sorted(set(SPECS_REF_RE.findall(text)))
    if not specs:
        raise OSError(f"未能在 {MANIFEST_FILE} 中解析出任何 specs/ 清单")
    targets = [MANIFEST_FILE] + list(specs)
    return targets, list(OPTIONAL_FILES)


def target_path(out_dir, rel):
    """落点内路径（相对清单里的仓库路径）。

    安装脚本那一组的 `rel` 带来源侧的目录（`script/fetch-specs.py`），而落点根下只放
    文件名——见 `fetch_install_scripts`。
    """
    if rel in INSTALL_SCRIPTS:
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
    """
    local = os.path.abspath(__file__)
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
        print(f"更新: 已取到更新的取规范脚本 {os.path.getsize(target)} B（{why}）", file=sys.stderr)
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
    _leave_handoff_note(target)
    return None


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
    note = f"{os.path.abspath(__file__)}{SELF_HANDOFF_SUFFIX}"
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
    candidates.append((install_scripts_dir(), os.path.basename(INSTALL_SCRIPTS[0]), real is None,
                       "落点根下"))
    candidates.append((os.path.join(cwd, SELF_TMP_DIR), os.path.basename(INSTALL_SCRIPTS[0]), False,
                       "工作目录 tmp/ 下"))
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
    note = f"{os.path.abspath(__file__)}{SELF_HANDOFF_SUFFIX}"
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
    if _real_script() != os.path.abspath(__file__):
        # 真身不是本轮这个文件：**不在脚本里代它重启**——那会把调用方的排布改掉
        # （见 `_take_over_self`）。标记留着，真身下次跑起来自然接上。
        print(f"说明: 新版本({fresh})等真身下次跑起来时自己接上——本轮这一份不是它在用的那一份，"
              "不在脚本里代它重启", file=sys.stderr)
        return
    try:
        # 同 `_take_over_self`：真身多半带着收尾收紧留下的只读位，先补写位再换（补位只为
        # 换这一步，重启后的那一轮收尾收回）——不补位时只读位把它拒掉、标记永远消费不掉，
        # "重跑一次即用上"就成了每轮复发的死循环（本仓库实测：Windows 上每轮 [Errno 13]）。
        _chmod_report(os.path.abspath(__file__), _WRITABLE_FILE_MODE)
        shutil.copyfile(fresh, os.path.abspath(__file__))
        os.chmod(os.path.abspath(__file__), os.stat(os.path.abspath(__file__)).st_mode | stat.S_IXUSR)
    except OSError as e:
        print(f"警告: 已取到更新的取规范脚本({fresh})，但换不上去({e})——本轮按本地这一份继续；"
              f"重跑一次、或手工把它换过来即用上（见 specs/general/script.adoc「跨环境脚本」）",
              file=sys.stderr)
        return
    _discard_handoff_note(note)
    print("更新: 已换成上一轮取到的新版取规范脚本，本轮按它的清单口径取全", file=sys.stderr)
    _restart_with(os.path.abspath(__file__), "--self-updated")


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
        _progress(total, rel, "保留", f"{len(before)} B（--keep：不动本地那份）",
                  time.monotonic() - started)
        return rel, "keep", "已存在（--keep）"
    last_err = None
    for attempt in (1, 2):          # 失败重试一次，避免偶发抖动让整批失败
        try:
            data = fetch_text(base, rel).encode("utf-8")
            if before is not None and data == before:
                _progress(total, rel, "未变", f"{len(data)} B（与远程一致）",
                          time.monotonic() - started)
                return rel, "same", f"{len(data)} B（与远程一致）"
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            _ensure_writable(out_dir, dest)
            tmp = f"{dest}.part"
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, dest)
            _make_read_only(dest, is_dir=False)
            _progress(total, rel, "刷新" if before is not None else "新取", f"{len(data)} B",
                      time.monotonic() - started)
            return rel, ("updated" if before is not None else "new"), f"{len(data)} B"
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
    for rel in INSTALL_SCRIPTS:
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
    `~/.cache/agent-specs-backup` 会被判成在 `~/.cache/agent-specs` 之内——
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
    return os.path.join(shared_cache_dir(), CACHE_HOME_DIR, CACHE_APP_DIR)


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
            f"{CACHE_HOME_DIR}/{CACHE_APP_DIR}")
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
    return os.path.join(home_dir, CACHE_HOME_DIR, CACHE_APP_DIR, slot)


def resolve_out_dir(args):
    """定出本次落点：`shared_cache_dir()` 与两个落点常量拼出的那一处，其下按来源分槽。

    **不曾保留的备选做法**（撤掉它们正是本函数的全部内容）：按平台各取一套缓存目录、
    留一批换落点的参数与环境变量、缓存不可得或来源指向本机时自动退回项目内临时目录
    ——每一种都会让"副本在哪"变成环境相关的事实（理由与用户口径见脚本头部「落点」）。
    """
    return cache_slot_dir(shared_cache_dir(), args.base)


def main(argv=None):
    global _DONE
    _DONE = 0
    args = parse_args(argv)
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

    base = args.base
    # **先更新自身、再照新清单取全**（见头部「取回与更新口径」）：脚本自己的清单解析口径若在
    # 远端变过，跑着旧脚本的这一轮只会照旧口径取——新东西静默不进副本（用户口径："更新自身
    # 避免有的没进索引"）。故这一步在**取清单之前**，且**换上了就当场重启、当轮即生效**
    # （用户口径：「更新的时候，就要及时生效吧？还等下一次？」）——`update_self` 只在
    # **没换成**（远端一致 / 真身换不动 / 无处落盘）时返回，那几种情形它已各自如实警告完毕。
    # 只在非 `--keep` 与 `--list` 时做（`--list` 是"只看清单、不下载"）。
    if not args.keep and not args.list:
        # 先清掉**上一轮**留下的旧副本（本轮的还没写，见 `_clean_self_tmp`）；
        # `keep` 只传本轮认得的那一份（`tmp/` 兜底落点上的同名中转件）——不带后缀的那份
        # 不能按名字认，否则用户从落点复制过来的同名文件会被静默删掉。
        tmp_fallback = os.path.join(os.getcwd(), SELF_TMP_DIR, os.path.basename(INSTALL_SCRIPTS[0]))
        _clean_self_tmp(os.getcwd(), keep=[tmp_fallback])
        update_self(base, out_dir, os.getcwd())

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
        print(f"# 落点: {out_dir}（用户家目录下的 {CACHE_HOME_DIR}/{CACHE_APP_DIR}）")
        scripts_dir = install_scripts_dir()
        for rel in INSTALL_SCRIPTS:
            print(f"{rel}  ->  {target_path(scripts_dir, rel)}")
        print(f"# 安装脚本 {len(INSTALL_SCRIPTS)} 份，落点根下: {scripts_dir}"
              f"{'（--no-scripts 时不取）' if args.no_scripts else ''}")
        return EXIT_OK

    # `--force` 与默认同为"以远程为准"，此处只保留它的写法（与 `--keep` 相反）；
    # `--keep` 下 `download_one` 自己判"本地已有即不动"
    total = len(targets) + len(optional) + (0 if args.no_scripts else len(INSTALL_SCRIPTS))
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
    if failed:
        for rel, _, why in failed:
            print(f"  [失败] {rel} -- {why}", file=sys.stderr)
        print("提示: 失败项**保留本地已有的那一份**（本地原本没有才算真缺）、重试本脚本即可补取；"
              "失败项若显示为 `0 B`，先见脚本头部「原子替换抵不住的那条路径」"
              "（多为把落点里的文件当成命令 stdout 的用法所致）。", file=sys.stderr)
        return EXIT_INCOMPLETE
    if not fresh and not updated and not args.keep:
        print("说明: 清单内文件与远程逐字节一致，落点未改动（判据是内容，不是时间）。")
    if updated:
        print("提示: 本地副本**已被远程内容覆盖**（落点是本脚本自己的那份）——"
              "要留本地改动请先备份、或下次加 --keep。")
    print(f"规范已就绪：读取落点下的 {MANIFEST_FILE} 及其引用的 specs/ 规范，并持续遵守。")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
