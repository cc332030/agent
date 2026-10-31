#!/usr/bin/env python3
"""规则校验引擎：把"规则数据"（配置文件）与"校验实现"（脚本）隔离。

定位与用途
----------
本仓库的 `check_specs.py` 里每道防线都在做同一件事：**在指定文本的指定范围内，逐组核对
"须同时命中的锚点"**。此前锚点、节名、文件路径与"缺失它为什么会失效"的说明**全部硬编码
在防线的函数体里**——于是任何一条规范措辞调整都要改脚本（规则一变就改代码），
且同一套"取节 → 逐组核锚点 → 报错"的实现被复制了近百遍。

本模块把两类东西分开：

* **规则数据**（`script/specs-rules/` 目录）：要核哪个文件、哪一节、哪些锚点分组、
  缺失时的说明——**改规则只改规则文件，不改脚本**；规则文件**一类规则一个**（按被测
  落点切分），加载侧**按目录自动扫描**（加一个规则文件不必动脚本）；
* **校验实现**（本模块 + 各防线函数）：只有一套通用的
  "读文件 / 取节 / 核锚点 / 报错"原语，不承载任何具体规范措辞。

**边界（L1）**：本模块只做**机械可判定**的事（某段文本里有没有某个锚点、某个文件在不在）。
"这条规则今天还成不成立""内容是不是废话"属**语义判断**，不得由本模块判定
（判据见 `specs-project-maintainer/guards.adoc`「机械防线的核对对象是」。

用法
----
    from rules_engine import Rules, load_rules

    rules = Rules(load_rules(path), ctx)      # ctx 见下「上下文契约」
    rules.run("<防线名>")                     # 按防线名跑该防线的规则

上下文契约（`ctx`）
-------------------
调用方须提供三件事，本模块**不直接读仓库**（便于单测注入夹具）：

* `ctx.err(msg, path="", line=0)`——报一条违规；
* `ctx.read(rel)`——按仓库根相对路径读文本，读不到返回 `None`；
* `ctx.section(text, title)`——取某二级节的正文（取不到返回空串）；
* `ctx.bullet(section, prefix)`——取节内以 `* **<prefix>` 开头的 bullet（取不到返回 `None`）。

行为与副作用
------------
只读文件、只把违规写进 `ctx.err`，不写任何文件、不依赖网络与第三方库、无全局状态。

关键约定与设计决策
------------------
* **规则数据用 TOML、不用 Python 字面量**：TOML 是**纯数据格式**（无 import、无可执行
  代码、无表达式），改措辞时不可能"顺手改出脚本行为"——这正是"规则与脚本隔离"要买的东西。
  它与我们数据的形态也对得上：一类规则一个文件、逐条是 `[[guards.<防线名>]]` 表，
  **同名键（重复防线名）由 TOML 自己的语法直接拒绝**，不比等加载期才发现。
  放弃了两条：①"数据写成 `.py` 常量"（数据与代码仍在同一模块里，改规则仍要动脚本）；
  ②JSON（纯数据性同样成立，但**长锚点串的多行可读性差**、报错只给行列不指位置，
  且与仓库其余配置的写法不统一）。
* **一类规则一个文件 + 按目录自动扫描**：规则文件按**被测落点**切分（不把所有文件的
  规则堆进一个文件——堆在一起时定位慢、且多个改动方在同一文件里各改一段、冲突面同源），
  加载侧只登记**目录**、按目录自动扫描（脚本里不出现规则文件名清单）。
  放弃了"单文件 + 逐个登记文件名"：那会让"加一条规则"又要动脚本。
* **锚点分组是 `[名称, [锚点...], 缺失说明]`**：名称与说明**给人看**、锚点**给机器核**。
  判定标准（何时算违规）与数据分离是刻意的：引擎只回答"命中与否"这一件确定的事。
* **取节失败即报错、不静默跳过**：节被改名/删除时须报红——"核不到"与"核过且通过"必须分得清。
* **配置文件缺失或 JSON 非法即致命错**：不退回硬编码——否则"配置丢了但脚本照跑"
  会让整批规则静默失效（`specs/general/verify.adoc`「验证的效力等级」的确定项不得空转）。
* **TOML 没有 null**：数据里"不指定某字段"一律写成**缺键**——写 `file = ""` 才是
  "显式指明了一个空路径"（引擎按"键不存在" 取默认值，故 `null` 不参与判据）。
* **兜底与已知限制**：本引擎不解析 AsciiDoc 结构，仅按行取节与做子串命中——
  锚点若被拆行或改写措辞，机械侧判不出"语义仍在"，那属语义复核的范围。
"""

import functools
import hashlib
import os
import re
import tomllib

# 规则数据的默认落点：与脚本同目录的规则**目录**——一类规则一个文件，脚本只登记该
# 目录、按目录自动扫描加载（新增规则文件不必改脚本）。
RULES_DIR_NAME = "specs-rules"

# 规则文件的后缀：**纯数据格式 TOML**（标准库 `tomllib` 可读，无需第三方依赖）。
# 取 `.toml` 而不是 `.json`：多行长锚点串可读性更好、重复表头由语法直接拒绝，
# 且与仓库其余配置文件的写法统一（用户口径）。
RULES_FILE_SUFFIX = ".toml"
def default_rules_spec(script_dir: str) -> str:
    """返回规则数据的默认落点（规则**目录**，与脚本同目录）。

    加载侧登记的是这个**目录**（不是文件名清单）：新增一个规则文件不必改脚本，
    `load_rule_files` 会按目录自动扫描并把它们合并成一个数据集。
    """
    return os.path.join(script_dir, RULES_DIR_NAME)


class RulesError(RuntimeError):
    """规则数据本身的问题（文件缺失、JSON 非法、结构不符、kind 未知）——属致命错。"""


# ---------------------------------------------------------------------------
# 步骤实现：每种 `kind` 一个函数，签名统一为 (rules, step)。
# 每个函数只做"取文本 → 核锚点 → 报错"，不承载任何具体规范措辞（措辞全在 step 里）。
# ---------------------------------------------------------------------------

# 步骤的默认消息模板：配置文件可覆盖（`message`/`missing_*_message`），
# 缺省时用这里的通用模板——避免每条规则重复抄同一句话（信息密度条：同一描述只写一处）。
DEFAULTS = {
    "missing_file_message": "缺少 {file}——该条的落点无处承载（文件被删则判据一并消失）",
    "missing_section_message": "缺少 {file}「{section}」——该条的判据失去落点",
    "missing_bullet_message": "缺少 {file} 的 `* **{bullet}` 条目——条目级判据须落在该 bullet 正文上",
    "anchor_count_message": "规则数据里 `{file}` 的 `* **{bullet}` 一条只剩 {have} 项锚点（基线 {min}）"
                            "——锚点被删时规范正文一字不少、防线却少核一项，"
                            "报绿与「核过且通过」看起来一样；删锚点须与调基线一并发生",
    "missing_line_message": "缺少 {file} 的对应条目——没有登记行则该条实际失效",
    "missing_block_message": "缺少 {file} 的 `{marker}` 片段——该边界在提示词侧失去落点",
    "file_message": "缺少 {file}——该条的落点无从核对",
    "dup_message": "{a}:{line_a} 与 {b}:{line_b} 逐字重合 {overlap} 字：`{frag}`",
    "dup_missing_files_message": "逐字重复扫描的落点不足（{file}）——少于两个可核对文档时该防线空转",
    "missing_files_message": "{file} 一份都取不到——落点整个缺失时该判据空转（不得当成'没有内容就是通过'）",
}


# 报错文案里允许出现的占位符：`_check_groups` 按这几个名字填值。
# 文案里写了别的名字（如把 `{file}` 写成 `{rel_exec}`）`_fill` 填不进去，
# 报错正文就会原样带着 `{rel_exec}` 给读者看——加载期一律拒绝。
# 可用占位符（加载期校验 `message` 里不得出现白名单外的名字）。
# `ref`/`overlap`/`frag`/`line` 供 `dispatcher_no_verbatim` 报告"与哪个文件重合了多少字、
# 重合的片段是什么、在第几行"——写错的占位符会原样留在报错正文里，故同样在加载期拦住。
# `a`/`b`/`line_a`/`line_b` 供 `duplicate_scan` 报告"哪两处、各自在第几行"。
PLACEHOLDERS = ("file", "missing", "desc", "hit", "cite", "ref", "overlap", "frag", "line",
                "a", "b", "line_a", "line_b")


def _fill(msg, **kw):
    """把 `{占位符}` 填进文案（占位符名限 `PLACEHOLDERS`，加载期已校验）。"""
    for key, value in kw.items():
        msg = msg.replace("{" + key + "}", str(value))
    return msg


def _msg(step, key):
    """取步骤的自定义消息，缺省时用 `DEFAULTS` 里的通用模板。"""
    return step.get(key, DEFAULTS[key])


def _fmt_groups(missing, groups):
    """把"哪一组、缺了哪些锚点、为什么"整理成人可读的一行（说明取自规则数据）。"""
    parts = []
    for name, miss, why in missing:
        parts.append(f"{name}（缺 {miss}）——{why}")
    return "；".join(parts)


def _check_groups(err, rel, scope_desc, text, groups, prefix="", template=None):
    """核一组 `[名称, [锚点...], 说明]`；任一锚点缺失即报错（同组任一缺失即整组不成立）。

    `template` 给出该防线的原始报错文案（含 `{file}`/`{missing}`/`{desc}` 占位符）——
    报错文案是"为什么会失效"的承载，逐字保留，缺省时才用通用文案。
    逐组报错（每组一条）与原始实现一致：一组缺失不等于整批只有一条。
    """
    for name, tokens, why in groups:
        miss = [t for t in tokens if t not in text]
        if not miss:
            continue
        if template:
            msg = _fill(template, file=rel, missing=miss, desc=why)
        else:
            msg = f"{prefix}{scope_desc}缺失要点 {name}（缺 {miss}）——{why}"
        err(msg, rel)


def _step_exists(rules, step):
    """文件/路径须存在（`files` 给出路径列表，`why` 说明缺失为什么会失效）。"""
    ctx = rules.ctx
    for rel in step["files"]:
        if ctx.read(rel) is None:
            ctx.err(step["message"].replace("{file}", rel), rel)


def _step_section_groups(rules, step):
    """取某二级节 → 逐组核锚点（取不到节即报错、不退化到全文）。"""
    ctx = rules.ctx
    rel = step["file"]
    text = ctx.read(rel)
    if text is None:
        ctx.err(_msg(step, "missing_file_message").replace("{file}", rel), rel)
        return
    section = ctx.section(text, step["section"])
    if not section:
        # 缺的是**哪一个**节须出现在报错正文里（`_msg` 不认 `{section}` 这类占位符，
        # 直接填节名）——否则读者只看到"某个句子缺了"、定位不到落点。
        ctx.err(_msg(step, "missing_section_message").replace("{file}", rel)
                .replace("{section}", step["section"]), rel)
        return
    groups = _groups_of(rules, step)
    if groups is None:
        return
    _check_groups(ctx.err, rel, f"「{step['section']}」节", section, groups,
                  prefix=step.get("prefix", ""), template=step.get("message"))


def _groups_of(rules, step):
    """取本步的锚点组：给 `token_list` 时从规则数据的**唯一一处**清单取，否则用 `step["groups"]`。

    **为什么要有它**：同一份锚点清单在 `section_groups` 里再抄一遍，就成了「同一数值的第二份
    写法」——两处各自漂移时没有任何判据会发声（本仓库实测：改 `collab.toml` 里抄的那一份、
    并把规范正文改成与它一致，`check_specs.py` 全绿；`anchor_count` 数的是 `_tokens.toml`
    那份，两处从此各说各话）。故清单**只写一处**（`_tokens.toml`）、本步按名引用。

    清单名取不到（未登记、写错）时**报错而非静默退化**：那会让整组锚点空转，而"核过且通过"
    与"没核"看起来一样。
    """
    # `token_list` 与 `groups_source` 同义：两者都指「锚点组来自 `_tokens.toml` 里的同名清单」。
    # 分两个名字是因为后者读起来是"另一份数据里的清单"、前者读起来是"一组词"——同义词只许
    # 有一处实现（本函数），别处不得各判一遍（见 `specs/general/coding.adoc`「同一件事只有一个来源」）。
    named = step.get("token_list") or step.get("groups_source")
    if not named:
        return step["groups"]
    data = rules.ctx.tokens(named)
    if not isinstance(data, (list, tuple)):
        rules.ctx.err(f"规则数据里没有 `{named}`——本节各锚点的唯一来源缺失，"
                      "该步整组空转（`section_groups` 引了 `token_list` 就必须取得到）",
                      step["file"])
        return None
    return data


def _step_subsection_groups(rules, step):
    """取某三级小节 → 逐组核锚点（与 `_step_section_groups` 互补，判据对象是三级节）。"""
    ctx = rules.ctx
    rel = step["file"]
    text = ctx.read(rel)
    if text is None:
        ctx.err(_msg(step, "missing_file_message").replace("{file}", rel), rel)
        return
    section = ctx.subsection(text, step["subsection"])
    if not section:
        # 同上：填入 `subsection`，缺的是哪个小节须出现在报错正文里。
        ctx.err(_msg(step, "missing_section_message").replace("{file}", rel)
                .replace("{section}", step["subsection"]), rel)
        return
    groups = _groups_of(rules, step)
    if groups is None:
        return
    _check_groups(ctx.err, rel, f"「{step['subsection']}」小节", section, groups,
                  prefix=step.get("prefix", ""), template=step.get("message"))


def _step_target(rules, step):
    """取本步的**核对对象**：给了 `section` 时取该二级节的正文，否则取整份文件。

    返回 `(文本, 落点描述)`；文件读不到、或 `section` 指定的节取不到时返回 `(None, 描述)`
    并由调用方报错——**"核不到"与"核过且通过"必须分得清**（同 `_step_section_groups`）。

    为什么要有这一个：按**整份文件**核"某小节里的要点还在不在"时，同一批字样在文件别处
    也会出现（本仓库实测：`specs/general/doc.adoc` 的「引用路径」节被抽空、只留标题，
    而别处仍有同样字样，检查全绿；`specs/stack/java-testing.adoc` 的节名与节内正文被改回
    强制面时，取节名之前那一段同样全绿）。判据是"**这一节**里的要点还在不在"，
    核对对象就必须是**这一节**。
    """
    ctx = rules.ctx
    rel = step["file"]
    text = ctx.read(rel)
    if text is None:
        ctx.err(_msg(step, "missing_file_message").replace("{file}", rel), rel)
        return None, ""
    section = step.get("section")
    subsection = step.get("subsection")
    if not section and not subsection:
        return text, step.get("scope", "文件")
    if subsection:
        found = ctx.subsection(text, subsection)
        title = subsection
    else:
        found = ctx.section(text, section)
        title = section
    if not found:
        ctx.err(_msg(step, "missing_section_message").replace("{file}", rel)
                .replace("{section}", title), rel)
        return None, ""
    return found, f"「{title}」节"


def _step_file_groups(rules, step):
    """整份文件（或 `section` 指定的二级节）逐组核锚点。

    判据对象默认是全文（如"该文件里必须出现这几组要点"）；给出 `section` 时收窄到该节
    （见 `_step_target`——按全文核"某节里的要点"会被别处的同形字样兜住）。
    """
    text, scope_desc = _step_target(rules, step)
    if text is None:
        return
    _check_groups(rules.ctx.err, step["file"], scope_desc, text, step["groups"],
                  prefix=step.get("prefix", ""), template=step.get("message"))


def _step_file_tokens(rules, step):
    """整份文件（或 `section` 指定的二级节）核一组平铺锚点（不分组，缺任一即报同一条说明）。"""
    text, _scope_desc = _step_target(rules, step)
    if text is None:
        return
    miss = [t for t in step["tokens"] if t not in text]
    if miss:
        rules.ctx.err(step["message"].replace("{file}", step["file"])
                      .replace("{missing}", str(miss)), step["file"])


def _step_line_tokens(rules, step):
    """找**包含 `anchor` 的那一行**，再核该行是否含全部 `tokens`（用于调度器登记这类"条目级"判据）。"""
    ctx = rules.ctx
    rel = step["file"]
    text = ctx.read(rel)
    if text is None:
        ctx.err(_msg(step, "missing_file_message").replace("{file}", rel), rel)
        return
    line = next((ln for ln in text.splitlines()
                 if all(a in ln for a in step["anchor"])), "")
    if not line:
        # `{file}` 与其余步骤同口径：报错须给出**缺的是哪份文件**，否则读者只看到一句
        # "没有对应条目"、连去哪找都无从知道（`_msg` 返回的默认文案含该占位符）
        ctx.err(_msg(step, "missing_line_message").replace("{file}", rel), rel)
        return
    miss = [t for t in step["tokens"] if t not in line]
    if miss:
        ctx.err(step["message"].replace("{missing}", str(miss)), rel)


def _step_forbid_section(rules, step):
    """某节内**不得出现**任一禁用锚点（与 `_step_section_groups` 方向相反）。"""
    ctx = rules.ctx
    rel = step["file"]
    text = ctx.read(rel)
    if text is None:
        ctx.err(_msg(step, "missing_file_message").replace("{file}", rel), rel)
        return
    section = ctx.section(text, step["section"])
    if not section:
        ctx.err(_msg(step, "missing_section_message").replace("{file}", rel)
                .replace("{section}", step["section"]), rel)
        return
    hit = [t for t in step["forbidden"] if t in section]
    if hit:
        ctx.err(step["message"].replace("{hit}", str(hit)), rel)



def _step_file_forbidden(rules, step):
    """整份文件内**不得出现**任一禁用锚点（与 `file_tokens` 方向相反）。

    用于"同一件事只在别处写一份、此处不得再抄"这类要求：正向锚点只能证明"该写的还在"，
    证明不了"不该抄的没抄"。
    """
    ctx = rules.ctx
    rel = step["file"]
    text = ctx.read(rel)
    if text is None:
        ctx.err(_msg(step, "missing_file_message").replace("{file}", rel), rel)
        return
    hit = [t for t in step["forbidden"] if t in text]
    if hit:
        ctx.err(step["message"].replace("{file}", rel).replace("{hit}", str(hit)), rel)


def _step_split_block(rules, step):
    """按定界串切出一段（`split_by` 取最后一段，`end_by` 截断）→ 逐组核锚点。

    用于提示词公共片段（`tag::x[]`）与"最高优先级铁律"这类**非标准节**的文本块。
    """
    ctx = rules.ctx
    rel = step["file"]
    text = ctx.read(rel)
    if text is None:
        ctx.err(_msg(step, "missing_file_message").replace("{file}", rel), rel)
        return
    if step["split_by"] not in text:
        ctx.err(_msg(step, "missing_block_message").replace("{file}", rel)
                .replace("{marker}", step["split_by"]), rel)
        return
    block = text.split(step["split_by"], 1)[-1]
    if step.get("end_by"):
        block = block.split(step["end_by"], 1)[0]
    _check_groups(ctx.err, rel, step.get("scope", "该段"), block, step["groups"],
                  prefix=step.get("prefix", ""), template=step.get("message"))


def _step_regex_section(rules, step):
    """按 `^== <节名>` 正则取节（到下一个 `== ` 或文末）→ 逐组核锚点。

    用于节名带可变后缀（如 `P6.`、`压缩提交`）的场合——节名的**前缀**由配置给出。
    """
    ctx = rules.ctx
    rel = step["file"]
    text = ctx.read(rel)
    if text is None:
        ctx.err(_msg(step, "missing_file_message").replace("{file}", rel), rel)
        return
    m = re.search(step["pattern"], text, re.M | re.S)
    if m is None:
        ctx.err(_msg(step, "missing_section_message").replace("{file}", rel)
                .replace("{section}", step["label"]), rel)
        return
    _check_groups(ctx.err, rel, f"「{step['label']}」", m.group(0), step["groups"],
                  prefix=step.get("prefix", ""), template=step.get("message"))


def _step_bullet_tokens(rules, step):
    """取某节里以 `* **<bullet>` 开头的那个 bullet → 核其 tokens（条目内核对）。

    按整节核对时，相邻条款的字样会兜住被抽空的条目；故条目级判据须落在 bullet 正文上。

    `until` 给出**截断串**（可选）：核对对象只取 bullet 正文里该串**之前**的那一段——
    用于"同一 bullet 的后半句会兜住前半句缺项"的场合（实测形态：条目正文的**清单句**缺一项，
    而同一 bullet 末尾的**依据行**同样罗列这些名字，于是在 bullet 级核仍全绿）。
    截断串按**最后一次**出现切（清单句与其后首次复现之间可能夹着别的说明）。
    `anchor` 给出**起始串**（可选）：核对对象从 bullet 正文里该串**之后**那一段起算——
    用于"要核的是 bullet 里某一句，而该句前后的话都不该参与核对"。两者可同用（先切 `anchor`、
    再截 `until`）；都不给则核对整条 bullet。
    """
    ctx = rules.ctx
    rel = step["file"]
    text = ctx.read(rel)
    if text is None:
        ctx.err(_msg(step, "missing_file_message").replace("{file}", rel), rel)
        return
    section = ctx.section(text, step["section"])
    if not section:
        ctx.err(_msg(step, "missing_section_message").replace("{file}", rel)
                .replace("{section}", step["section"]), rel)
        return
    bullet = ctx.bullet(section, step["bullet"])
    if not bullet:
        ctx.err(_msg(step, "missing_bullet_message").replace("{file}", rel)
                .replace("{bullet}", step["bullet"]), rel)
        return
    scope = bullet
    anchor = step.get("anchor")
    if anchor:
        if anchor not in scope:
            ctx.err(step["message"].replace("{missing}", str(anchor)), rel)
            return
        scope = scope.split(anchor, 1)[1]
    if step.get("until"):
        scope = scope.split(step["until"], 1)[0]
    miss = [t for t in step["tokens"] if t not in scope]
    if miss:
        ctx.err(step["message"].replace("{missing}", str(miss)), rel)
    # 本步的锚点清单**自己**被删项时现场一字不少、上一句一次也不报错（"防线零证据"的形态，
    # 与 `anchor_count` 同一条道理）：`min` 取当前条数，删锚点须与调 `min` 一并发生。
    floor = step.get("min")
    if isinstance(floor, int) and len(step["tokens"]) < floor:
        ctx.err(_msg(step, "anchor_count_message")
                .replace("{file}", rel).replace("{have}", str(len(step["tokens"])))
                .replace("{min}", str(floor)).replace("{bullet}", step["bullet"]), rel)


def _paired_bullet_token_count(rules, step):
    """取本步所指清单的锚点条数；**清单本身取不到时返回 `None`**（调用方须报红）。

    两种取法：① `token_list` 给出规则数据里的锚点清单名（`tokens` 段里的常量，形如
    `[[组名, [锚点...], 理由], ...]`）——**按组内的锚点项数逐项累加**，这样删掉一项锚点
    也会被本步接住（只取组数拦不住组内被削）；清单名拼错或被整段删掉时 `ctx.tokens()`
    给不出数据，此时条数是"取不到"、不是 0——返回 0 会被 `min` 判成"清单只剩 0 项"、
    把读者指向错误的原因（真因是清单名对不上）。② `file` + `bullet` 指向同防线同位置的
    那条 `bullet_tokens` 步骤，取其 `tokens` 条数（取不到成对那一步同样是"取不到"）。
    """
    guard = step.get("_guard")
    if guard is None:
        return 0
    named = step.get("token_list")
    if named:
        data = rules.ctx.tokens(named)
        if not isinstance(data, (list, tuple)):
            return None
        total = 0
        for group in data:
            if isinstance(group, (list, tuple)) and len(group) >= 2 \
                    and isinstance(group[1], (list, tuple)):
                total += len(group[1])
        return total
    for other in rules.steps(guard):
        if (other is not step and other.get("kind") == "bullet_tokens"
                and other.get("file") == step.get("file")
                and other.get("bullet") == step.get("bullet")):
            return len(other.get("tokens", []))
    return None


def _step_anchor_count(rules, step):
    """核「锚点清单自身的条数」——**规则数据里的锚点被删**是唯一一种"防线零证据"的形态。

    其余步骤核的都是"现场文档里有没有这些锚点"；而锚点清单**自己**被删掉几项时（规范正文
    一字未动），现场什么都不缺、防线一次也不报错——`miss` 是空集，"核过且通过"与"没核"
    看起来一模一样。本步把清单条数变成可核对的：低于 `min` 即报错并给出本条清单的现值。

    实测（本仓库）：把规则数据里某条锚点整行删掉、规范正文一字未动，`python3 script/check_specs.py`
    仍报"OK 规范检查全部通过"——**判据被静默摘走一项**，且与"核过且通过"无从区分。

    `min` 取**当前条数**（不是理想条数）：本判据只拦"无声变少"，拦不住"本来就少"。
    删清单须与改 `min` 一并发生，于是这个动作在 diff 里可见。
    """
    ctx = rules.ctx
    have = _paired_bullet_token_count(rules, step)
    if have is None:
        # 清单名拼错 / 成对的那一步被删：条数取不到时若当成 0，报错会写成"清单只剩 0 项"，
        # 读者按那句话去正文里找，而真因在规则数据这一侧——故单列一句、指向该清单。
        target = step.get("token_list") or f"{step.get('file')} 的 `{step.get('bullet')}` 条目"
        ctx.err(f"取不到锚点清单 `{target}`——`anchor_count` 核的是清单自己的条数，"
                "取不到成对的那一步/那一个清单名时该清单**没有任何机械抓手**"
                "（改错名字或删掉成对步骤都属这个形态）", step["file"])
        return
    floor = step["min"]
    if have < floor:
        ctx.err(_msg(step, "anchor_count_message")
                .replace("{file}", step["file"]).replace("{have}", str(have))
                .replace("{min}", str(floor))
                .replace("{bullet}", step.get("bullet") or step.get("token_list", "")),
                step["file"])


def _step_prompt_files_groups(rules, step):
    """对 `prompts/` 下每个任务提示词文件逐组核锚点。

    提示词的题面各有自己的措辞，"公共片段里有"不代表"题面里也有"——故题面侧须逐文件核。
    文件清单由 `ctx.prompt_files()` 给（跳过 `_` 前缀的公共片段）。

    **公共片段算入核对对象（`resolve_includes`，默认开）**：提示词的内容可以为"一处维护、
    两处生效"而由 `include::_common.txt[tag=…]` 引入——此时该条**在装配后的提示词里是有的**，
    题面侧要求的是"它须被引入"，不是"它须逐字抄在题面里"。故核对前把提示词正文里的
    `include::` 指令**就地展开**（按 `prompts/` 下的同名文件与 `// tag::<名>[]` 片段取）；
    贴片失败（文件缺失、tag 缺失）**即报错**——"引用了却展不开"等于该条在装配后的提示词里
    根本不存在，比"没引用"更坏（读者按片段名以为内容在、实际取不到）。
    """
    ctx = rules.ctx
    files = ctx.prompt_files()
    if not files:
        ctx.err(step.get("missing_files_message",
                         "prompts/ 下未找到任何任务提示词文档（除 `_` 前缀公共片段外）"),
                "prompts/")
        return
    resolve = step.get("resolve_includes", True)
    for rel in files:
        text = ctx.read(rel)
        if text is None:
            ctx.err(_msg(step, "missing_file_message").replace("{file}", rel), rel)
            continue
        if resolve:
            text = _expand_includes(ctx, rel, text)
        _check_groups(ctx.err, rel, step.get("scope", "文件"), text, step["groups"],
                      prefix=step.get("prefix", ""), template=step.get("message"))


def _expand_includes(ctx, rel, text):
    """把 `include::<文件>[tag=<名>]` 就地展开成被引片段（取不到即报错并原样留下指令）。"""
    def _sub(m):
        target, tag = m.group(1), m.group(2)
        folder = rel.rsplit("/", 1)[0] if "/" in rel else ""
        src = f"{folder}/{target}" if folder else target
        body = ctx.read(src)
        if body is None:
            ctx.err(f"{rel} 引用了 {src}，但该文件不存在——"
                    "装配后的提示词里这条会整段缺失（引用了却展不开，比没引用更坏）", rel)
            return m.group(0)
        begin = f"// tag::{tag}[]"
        if begin not in body:
            ctx.err(f"{rel} 引用了 {src} 的 `{tag}` 片段，但该 tag 不存在——"
                    "装配后的提示词里这条会整段缺失", rel)
            return m.group(0)
        rest = body.split(begin, 1)[1]
        end = f"// end::{tag}[]"
        return rest.split(end, 1)[0].strip("\n") if end in rest else rest.strip("\n")

    return re.sub(r"include::([A-Za-z0-9_.-]+)\[tag=([A-Za-z0-9_-]+)\]", _sub, text)


# `section_bullets` 的**截断标记**：分组里的锚点以它们收尾时，末段不是锚点而是**截断串**
# （`"**判定标准" + CUT_END`）——该组只核 bullet 里这一段之前（或之后）的正文。
#
# 为什么要有：`section_bullets` 按 bullet 核锚点，而**同一条 bullet 的相邻两句常共用
# 同一个词**（实测：『必须用双引号』与紧接着的『判定标准』里都出现『双引号』），于是
# 抽掉前一句的要点、后一句照样把它兜住——按整条 bullet 核时这一组形同虚设。
# 用后缀而不是另立 `kind`，是因为"该组只核 bullet 的前半句"与"核整条 bullet"共用同一套
# 加载期判据与报错文案，另立 kind 只会让规则数据里出现两套同形写法。
CUT_START = "~cut-start"   # 该串**之后**起算（等价 `bullet_tokens` 的 `anchor`）
CUT_END = "~cut-end"       # 该串**之前**截止（等价 `bullet_tokens` 的 `until`）


def _step_section_bullets(rules, step):
    """取节内**每个分组自身**的 bullet 文本，再核该组的其余锚点（条目内核对）。

    分组形态：`[标题, [标题, 锚点...], 说明]`——首项是 bullet 前缀、其余是须落在
    **该 bullet 正文**里的锚点。只核整节时，相邻条目的字样会兜住被抽空的条目。
    `ctx.bullet` 取不到该 bullet 时**跳过**（轴标题缺失由别的检查负责，避免重复发声）。

    `tokens` 里可再给两个**截断串**（`…, "<起始串>", "<结束串>"` 收尾）：与
    `bullet_tokens` 的 `anchor`/`until` 同口径，只为"一条 bullet 里前半句与后半句同锚点"
    的场合服务——同一 bullet 的后半句会把前半句缺项兜住时，把核对面收到前半句上
    （实测形态：『必须用双引号』与紧随其后的『判定标准』里都出现『双引号』）。
    """
    ctx = rules.ctx
    rel = step["file"]
    text = ctx.read(rel)
    if text is None:
        ctx.err(_msg(step, "missing_file_message").replace("{file}", rel), rel)
        return
    section = ctx.section(text, step["section"])
    if not section:
        ctx.err(_msg(step, "missing_section_message").replace("{file}", rel)
                .replace("{section}", step["section"]), rel)
        return
    for name, tokens, why in step["groups"]:
        prefix, marks = tokens[0], list(tokens[1:])
        anchor = until = None
        if len(marks) >= 1 and marks[-1].endswith(CUT_END):
            until = marks.pop()[:-len(CUT_END)]
        if len(marks) >= 1 and marks[-1].endswith(CUT_START):
            anchor = marks.pop()[:-len(CUT_START)]
        anchors = marks
        bullet = ctx.bullet(section, prefix)
        if bullet is None:
            # 首项是该组的 **bullet 前缀**，取不到它说明这条 bullet 没了（或被改名）——
            # 那是"核对面整个消失"，不能静默跳过：跳过等于该组判据在此处不生效，
            # 而规则数据里写着它该管这件事（本仓库实测：把 bullet 标题连同要点一起改掉，
            # 按 bullet 核的整组**一条都不报**）。
            ctx.err(f"{rel} 的「{section}」节里找不到以 `{prefix}` 起头的条目——"
                    f"『{name}』失去核对对象，该组判据无从生效", rel)
            continue
        scope = bullet
        if anchor:
            if anchor not in scope:
                ctx.err(f"{rel} 的『{name}』正文里找不到起始串 `{anchor}`——"
                        "核对面收不到该句上，本组判据无从生效", rel)
                continue
            scope = scope.split(anchor, 1)[1]
        if until and until in scope:
            scope = scope.split(until, 1)[0]
        miss = [t for t in anchors if t not in scope]
        if miss:
            msg = step.get("message", "{file} 的『{name}』正文缺失 {missing}——{desc}")
            ctx.err(msg.replace("{file}", rel).replace("{name}", name)
                    .replace("{missing}", str(miss)).replace("{desc}", why), rel)


def _step_text_block_groups(rules, step):
    """先按定界串切出一段，再核这组「须同时命中的锚点」（与 `_step_file_tokens` 互补）。

    用于"某段提示词/某个模块/某个以给定片段起头的区域必须同时包含这几句"这类判据——
    它们此前以 `for rel, keys, desc in (...)` 的形式硬编码在防线函数体里（同一段实现
    被复制 N 遍），故与锚点一并外置到规则数据。
    `anchor` 给出切分串（取它之后的全部文本）；缺省则判据对象是整份文件。
    """
    ctx = rules.ctx
    rel = step["file"]
    text = ctx.read(rel)
    if text is None:
        ctx.err(_msg(step, "missing_file_message").replace("{file}", rel), rel)
        return
    want = step.get("anchor")
    if want is not None:
        if want not in text:
            ctx.err(step["message"].replace("{file}", rel).replace("{missing}", str(want)),
                    rel)
            return
        text = text.split(want, 1)[1]
    if step.get("forbidden"):
        hit = [t for t in step["forbidden"] if t in text]
        if hit:
            ctx.err(step["message"].replace("{file}", rel).replace("{hit}", str(hit)), rel)
            return
    miss = [t for t in step["tokens"] if t not in text]
    if miss:
        ctx.err(step["message"].replace("{file}", rel).replace("{missing}", str(miss)), rel)




def _step_dispatcher_no_verbatim(rules, step):
    """调度器条目**不得抄条目本体**：对每条调度行，取其括号内的说明，与**被引规范文件**的
    正文做最长公共子串检测——超过阈值即报红（说明是把本体的取值/判据抄进了调度器）。

    为什么需要它：`AGENTS_COMMON.adoc`（加载调度器）的职责是"登记 + 触发特征"，
    **落点承担什么、有哪些条、依据是什么一律写在被引文件里**（`terminology.adoc`
    「数据字典」的反膨胀、`doc-design.adoc`「信息归属」）。但"只核存在、不核唯一"的
    既有一组锚点只能证明"该写的还在"，证明不了"不该抄的没抄"——于是本体的**取值与判据**
    会被一句句抄进调度器、两处各自漂移（本轮实证：Java/Maven/Spring/CNB/通用层都在抄）。

    规则参数：
      * `file`：调度器文件（如 `AGENTS_COMMON.adoc`）；
      * `min_overlap`：最长公共子串的字符阈值（低于它视为巧合、不报）；默认 16；
      * `ignore`：不计入检测的整行子串（如"必加载层"这类本就只给路径的行）。

    只做**可逐字判定**的事：检索"整段逐字重合"。语义判断（这句是不是在复述本体）仍交人复核。
    """
    ctx = rules.ctx
    rel = step["file"]
    text = ctx.read(rel)
    if text is None:
        ctx.err(_msg(step, "missing_file_message").replace("{file}", rel), rel)
        return
    threshold = int(step.get("min_overlap", 16))
    ignores = step.get("ignore", [])
    # 只在指定节内核对（默认全文）：调度器守卫**只应作用于加载调度器那一节**——
    # 入口的「最高优先级铁律」是刻意写成"可先读、不必先加载其他文件"的**摘要**，
    # 与本条要拦的"把条目本体抄进调度器"是两件事，不应被误伤。
    scope_after = step.get("scope_after", "")
    scope_until = step.get("scope_until", "")
    # 起始行偏移：切走前缀后行号会变，报错时须还原成**文件里的真实行号**。
    lineno_offset = 0
    if scope_after:
        if scope_after not in text:
            ctx.err(_msg(step, "missing_block_message").replace("{file}", rel)
                    .replace("{marker}", scope_after), rel)
            return
        prefix, text = text.split(scope_after, 1)
        lineno_offset = prefix.count("\n")
    if scope_until and scope_until in text:
        text = text.split(scope_until, 1)[0]

    def _norm(s):
        # 去行内代码、去空白——只比较实义文字，避免路径/命令造成假命中
        s = re.sub(r"`[^`]*`", "", s)
        return re.sub(r"\s+", "", s)

    # 被引文件的自动机按归一化正文缓存：同一份文件被多行引用时只建一次，各行的说明段
    # 去走表——这道防线原来的耗时几乎全长在"每行为整份文件重建一次表"上（`b` 侧是整份
    # 被引文件、最大十万字符级）。改自动机后取最大值的定义不变，故判据与输出都不变。
    sam_cache = {}

    def sam_of(normalized):
        sam = sam_cache.get(normalized)
        if sam is None:
            sam = sam_cache[normalized] = _build_sam(normalized)
        return sam

    # 缓存被引规范文件正文（同一文件被多行引用时只读一次）
    spec_cache = {}

    def _spec_norm(path):
        if path not in spec_cache:
            body = ctx.read(path)
            spec_cache[path] = _norm(body) if body else ""
        return spec_cache[path]

    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if not stripped.startswith("*"):
            continue
        if any(ig in line for ig in ignores):
            continue
        # 该行引用了哪些规范文件（`specs/... .adoc`，含 `specs-project-maintainer/`）
        refs = re.findall(r"[A-Za-z0-9_./-]*(?:specs|specs-project-maintainer)/[A-Za-z0-9_./-]+\.adoc", line)
        if not refs:
            continue
        # 只核该行的**说明段**（括号内），不含句首的加载项名——加载项名本就是主题名
        desc = "（".join(line.split("（")[1:]) if "（" in line else ""
        if not desc:
            continue
        ndesc = _norm(desc)
        if len(ndesc) < threshold:
            continue
        for ref in refs:
            # 只判"是否 ≥ 阈值"：够到即停，不必走完整份被引文件（最大十万字符级）
            overlap, frag = _lcs_against(sam_of(_spec_norm(ref)), ndesc,
                                         early_stop=threshold)
            if overlap >= threshold:
                ctx.err(step["message"].replace("{file}", rel)
                        .replace("{line}", str(lineno + lineno_offset))
                        .replace("{ref}", ref)
                        .replace("{overlap}", str(overlap))
                        .replace("{frag}", frag),
                        rel, lineno)


def _step_pointer_no_verbatim(rules, step):
    """**自称"回指"的行不得同时复述被指文件的取值**：对给定的行（默认：含回指标记的行），
    取出该行引用的规范文件的正文，做最长公共子串检测——超过阈值即报红。

    为什么需要它：`duplicate_scan` 的阈值（40）是**下界**，只报"长度极显著"的重合；而
    "回指句 + 顺手把取值也抄一遍"这种形态的公共子串常常只有二十几字（本轮实证：
    `library/mirrors.adoc` 自称"本文件只给实测记录/取舍本体见 adoption.adoc"，却仍把
    "每级先实测可用、不跳级、不覆盖既有配置" 21 字逐字写在同段里），`duplicate_scan`
    **核不出来**。这类行的自相矛盾是**可逐字判定**的：既然同一行里既说"见别处"、
    又把别处的话写了一遍，那它至少是多写的。

    判据见 `specs/general/review.adoc`「精炼性（同一描述只写一处）」——同一件事只在一处
    完整定义、其余位置只留「这是什么 + 在哪」的一行引用。

    规则参数：
      * `files`：参与核对的文件列表（每个文件单独扫）；
      * `markers`：**回指标记**——行里含任一即视为"自称回指的行"，参与核对；缺省用
        一组通用措辞（`唯一落点`/`不复述`/`不重复`/`本处不重述`/`只给…记录` 等）；
      * `min_overlap`：最长公共子串阈值，默认 20；
      * `ignore`：含该子串的行不参与（如依据行、标准名括注这类本就该逐字一致的行）；
      * `exclude_refs`：被引文件中不参与比对的（如自指、或纯清单文件）。
    """
    ctx = rules.ctx
    threshold = int(step.get("min_overlap", 20))
    markers = step.get("markers") or [
        "唯一落点", "不复述", "不重复", "不在此重述", "本处不重述", "不在此重复",
        "只给实测记录", "只给索引", "只留索引", "不再复述", "不列其条目",
    ]
    ignores = step.get("ignore", [])
    exclude_refs = step.get("exclude_refs", [])

    def _norm(t):
        t = re.sub(r"`[^`]*`", "", t)
        return re.sub(r"\s+", "", t)

    spec_cache = {}

    def _spec_norm(path):
        if path not in spec_cache:
            body = ctx.read(path)
            spec_cache[path] = _norm(body) if body else ""
        return spec_cache[path]

    # 被指文件的自动机按文件缓存：同一份文件会被多条回指行各比一次，建表只做一遍
    sam_cache = {}

    def _spec_sam(path):
        if path not in sam_cache:
            sam_cache[path] = _build_sam(_spec_norm(path))
        return sam_cache[path]

    for rel in step["files"]:
        text = ctx.read(rel)
        if text is None:
            ctx.err(_msg(step, "missing_file_message").replace("{file}", rel), rel)
            continue
        for lineno, line in enumerate(text.split("\n"), 1):
            if not any(m in line for m in markers):
                continue
            if any(ig in line for ig in ignores):
                continue
            # **被指文件不限于 `.adoc`**：回指的落点还可能是随规范分发的脚本/入口/规则数据
            # （`.py`/`.sh`/`.bat`/`.ps1`/`.toml`），或提示词片段（`.txt`）——"真源在脚本头部
            # 注释里"这类回指正属本条的核对面。原实现只认 `.adoc`，于是**指向脚本的回指整类漏检**：
            # 本轮实测 `AGENTS_COMMON.adoc` 一行自称"真源是 `script/fetch-specs.py` 的头部注释、
            # 本节不复述"，却把那脚本头部的开关/退出码/解释器次序逐字抄了一遍（35 字重合），
            # 而遍历到的引用为空、直接跳过。扩展名按**可被回指的落点类型**取全，
            # 但**不扩到任意扩展名**（图片/二进制一类既无正文、也不承载取值）。
            refs = re.findall(r"[A-Za-z0-9_./-]*\.(?:adoc|py|sh|bat|cmd|ps1|toml|txt)", line)
            refs = [r for r in refs if r != os.path.basename(rel) and r not in exclude_refs]
            if not refs:
                continue
            nline = _norm(line)
            if len(nline) < threshold:
                continue
            for ref in refs:
                if ctx.read(ref) is None:
                    continue
                # 只判"是否 ≥ 阈值"：够到即停，不必走完整份被引文件（最大十万字符级）
                overlap, frag = _lcs_against(_spec_sam(ref), nline, early_stop=threshold)
                if overlap >= threshold:
                    ctx.err(step["message"].replace("{file}", rel)
                            .replace("{line}", str(lineno))
                            .replace("{ref}", ref)
                            .replace("{overlap}", str(overlap))
                            .replace("{frag}", frag),
                            rel, lineno)


def _norm_dup(s):
    """逐字重复检测的归一化：去行内代码、去空白。

    去行内代码是刻意的：路径/命令/标识符（`` `specs/general/script.adoc` ``）本身就该
    在两处出现，拿它们算重合只会刷出假命中；**比的是实义文字**。
    """
    return re.sub(r"\s+", "", re.sub(r"`[^`]*`", "", s))


def _strip_punct(text):
    """去掉**断句标点**（逗号/顿号/分号/冒号）：判据是"同一段文字被判据复制后随手断句"，
    标点位置不同不构成"两条不同的规则"——把标点也算进去，逐字相同的判据只要一处被
    加了逗号就核不出来。

    只去句读、不去句号：句号是"句子边界"，跨句的重复由逐句那一遍按句核。
    """
    return re.sub(r"[，、；：,;:]", "", text)


def _dup_units(rel, text):
    """把一份文档切成"实体"：**bullet 一级项**（含其换行承接的续行）各一个，其余每行一个。

    bullet 一级项须**整条**作为实体：这条规范的事实常常跨越 bullet 自己那行与它的续行
    （`** **范围性**…`），只按行切会把同一件事切碎、核不出来。
    """
    units = []
    cur = None
    for lineno, line in enumerate(text.split("\n"), 1):
        if line.startswith("* "):
            if cur:
                units.append(cur)
            cur = [lineno, [line]]
        elif cur is not None and line.strip() and not line.startswith("=="):
            cur[1].append(line)
        else:
            if cur:
                units.append(cur)
                cur = None
            units.append([lineno, [line]])
    if cur:
        units.append(cur)
    return [(ln, "\n".join(ls), _norm_dup("\n".join(ls))) for ln, ls in units]


def _build_sam(text):
    """后缀自动机：`nxt[i]` 是状态 i 的转移表、`link[i]` 是后缀链接、
    `length[i]` 是该状态代表的最长子串长度（状态 0 为初始状态）。

    单独成函数是为了让**同一个实体只建一次表**：'逐字重复扫描'要拿它跟上百个实体各比
    一次，建表正是其中最贵的一半；两份缓存都按"自动机建在更长的一侧"来存，走表那趟
    才是长串。
    """
    nxt = [{}]
    link = [-1]
    length = [0]
    last = 0
    for ch in text:
        cur = len(nxt)
        nxt.append({})
        link.append(-1)
        length.append(length[last] + 1)
        p = last
        while p != -1 and ch not in nxt[p]:
            nxt[p][ch] = cur
            p = link[p]
        if p == -1:
            link[cur] = 0
        else:
            q = nxt[p][ch]
            if length[p] + 1 == length[q]:
                link[cur] = q
            else:
                # 克隆状态：把 q 的转移表整份复制过来（`dict()` 复制是 C 级操作）
                clone = len(nxt)
                nxt.append(dict(nxt[q]))
                length.append(length[p] + 1)
                link.append(link[q])
                while p != -1 and nxt[p].get(ch) == q:
                    nxt[p][ch] = clone
                    p = link[p]
                link[q] = clone
                link[cur] = clone
        last = cur
    return nxt, link, length


def _lcs_against(built, a, early_stop=None):
    """拿 `a` 在**已建好的**自动机上走一遍，返回 (最长公共子串长度, 片段)。

    能走多远就是当前起点的匹配长度，断链时沿后缀链接回退——O(len(a))。

    `early_stop` 只用于**判定"是否 ≥ 阈值"**：最长值一旦够到它就打住，此时"够没够到"
    与走完全程同值（`_sam_lcs` 要精确最大值，不传）。
    片段在提前退出时退化为"走到的那一段"——报错文案里它只作定位提示，判据是长度本身。
    """
    nxt, link, length = built
    v = 0
    ln = 0
    best = 0
    end = 0
    for i, ch in enumerate(a):
        while v and ch not in nxt[v]:
            v = link[v]
            ln = length[v]
        to = nxt[v].get(ch)
        if to is None:
            v = 0
            ln = 0
        else:
            v = to
            ln += 1
            if ln > best:
                best = ln
                end = i + 1
                if early_stop is not None and best >= early_stop:
                    break
    return best, a[end - best:end]


@functools.lru_cache(maxsize=8192)
def _sentences(raw, min_len):
    """把实体按句号切开，返回**归一化后**不短于 `min_len` 的句子（去重、保序）。

    用于"折叠 vs 展开"那一次补核：同一事实在一处换了行、在别处铺成多行时，整条公共子串
    会被换行打断，只有按句才核得出来。归一化与实体侧同源（`_norm_dup`），否则比的是
    两种不同形态的文本。
    """
    seen = set()
    result = []
    for part in raw.split("。"):
        norm = _norm_dup(part)
        if len(norm) < min_len or norm in seen:
            continue
        seen.add(norm)
        result.append(norm)
    return result


def _sam_lcs(a, b):
    """最长公共子串（返回 (长度, 片段)）：后缀自动机建在**较长的一侧**，另一侧上去走一遍。

    为什么不用 DP：本条的核对对象是**全对**实体（近两千条实体、两万多对候选、单次调用
    十余万次），DP 的 O(len(a)·len(b)) 是逐字符的 Python 级循环，单这一道防线就十几秒
    （实测 10 s 占整条校验链的一半以上）。后缀自动机是 O(len(a)+len(b))，结果与 DP
    **完全相同**——都是"最长公共子串"的确定定义，不是近似。

    返回 (长度, 片段)——**完全匹配时片段可能不唯一**，报错文案里的片段只作定位提示，
    判据是长度本身。
    """
    if not a or not b:
        return 0, ""
    # 自动机建在长的一侧：走表只有一趟、建表才是贵的，故让建表那侧承担更长的串
    if len(a) < len(b):
        a, b = b, a
    return _lcs_against(_build_sam(b), a)


def _pairs_of(buckets):
    """把"桶 → 成员下标"聚成**去重、有序**的候选对（`i < j`，按 `(i, j)` 升序）。

    单独成函数：整条层与逐句层各聚一次，去重与排序的口径须一致——桶是字典、成员是列表，
    直接迭代会让报错次序随哈希漂移（同一份文档两次跑出两种次序）。
    """
    pairs = set()
    for group in buckets.values():
        if len(group) < 2:
            continue
        for x in range(len(group)):
            for y in range(x + 1, len(group)):
                a, b = group[x], group[y]
                if a != b:
                    pairs.add((a, b) if a < b else (b, a))
    return sorted(pairs)


def _step_duplicate_scan(rules, step):
    """**同一件事不得两处逐字重复**：对 `sources`（文件或目录）下每份文档切成语义实体，
    超阈值的重合即报红。判定面分两层：**整条实体**（比阈值还长的那一类才可能整条命中）
    与**句子**（`。` 切分，短行与长短混对全靠这一层）；两层各自按 n-gram 桶聚候选对，
    真正"算不算重复"一律由最长公共子串判，桶只负责"这一对值不值得算"。

    为什么需要它：`specs/general/review.adoc`「精炼性」把"重复面"列为必查项，但此前
    **只有语义复核、没有机械抓手**——"同一件事只在一处给真源"于是靠自觉。实证形态：
    * 两处逐字相同的段落（本仓库实测：同一段验收判据在 `verify.adoc` 与维护方 `context.adoc`
      各存一份；两个提示词的公共步骤逐字重复、却不在公共片段里）；
    * 一处**折叠**重复、一处**展开**重复（同一事实换行处不同、整条公共子串被换行打断）。
    只做**可逐字判定**的事：语义判断（这两句是不是在讲同一件事）仍交人复核——阈值以下、
    表述不同的重复核不出来，这是**下界**、不是"没有重复"的证明。

    规则参数：
      * `sources`：参与检测的文件或**目录**（目录递归取 `.adoc`）；
      * `min_overlap`：最长公共子串阈值（低于它可能是惯用语巧合、不报；默认 24）；
      * `min_sentence`：按句核对时单句的最短长度（默认同 `min_overlap`）——短于它的句子
        不参与逐句那一遍；
      * `min_text`：实体短于该长度即不参与（默认同 `min_overlap`）；逐句那一遍的阈值取
        两者**更小**的那个——`min_text` 是"整条太短不值得核"，不该顺带把"短到只有一句"
        的那类实体连整体一起挡在门外（阈值 40 时它们正是要核的那一类）；
      * `exclude`：不参与检测的路径子串（如历史留痕的大文件）；
      * `ignore`：含该子串的实体不参与（如"依据（标准名/编号）"这类本就该逐字一致的引用行）；
      * `ignore_units`：**例外清单**——含该子串的实体不参与，**每条理由须写在规则数据里**
        （如图书馆的逐字引文、带出处的用户原话），不得为了让检查变绿而加。
    """
    ctx = rules.ctx
    sources = step.get("sources") or [step.get("file")]
    threshold = int(step.get("min_overlap", 24))
    min_text = int(step.get("min_text", threshold))
    min_sentence = int(step.get("min_sentence", threshold))
    excludes = step.get("exclude", [])
    ignores = step.get("ignore", []) + step.get("ignore_units", [])

    files = []
    for src in sources:
        if not isinstance(src, str) or not src:
            continue
        if src.endswith("/"):
            files.extend(ctx.list_files(src, ".adoc"))
        else:
            files.append(src)
    files = [f for f in sorted(set(files)) if not any(x in f for x in excludes)]
    if len(files) < 2:
        ctx.err(_msg(step, "dup_missing_files_message").replace("{file}", str(sources)),
                str(sources or ""))
        return

    # 实体表：每项 (文件, 行号, 原文, 归一化)。`ignore` 命中的实体**不参与核对**——
    # 判据是"这些实体本就该逐字一致/本就是带出处的记载"，不是"给它们开个后门"。
    # **`min_text` 只管整条那一层**：整条短于它时"跨换行整条命中"无从谈起，但其中一句
    # 仍可能够到阈值——故这类实体照样收进来（报错由逐句那一遍判）。
    units = []
    for rel in files:
        body = ctx.read(rel) or ""
        for lineno, raw, normalized in _dup_units(rel, body):
            if len(normalized) < min(min_sentence, min_text):
                continue
            if any(ig in raw for ig in ignores):
                continue
            units.append((rel, lineno, raw, normalized))
    if len(units) < 2:
        ctx.log("  ^ 逐字重复扫描：可核对实体不足，本次未形成有效扫描面")
        return

    # **桶只负责"这一对值不值得算"**：n-gram 按判定阈值的长度取——只有共享一个阈值长的
    # 片段，才可能够到阈值。取短了（早期按 8 字）长实体之间几乎必然共享某个片段，桶就白
    # 聚一遍（实测候选对 ≈ 全对数）；比阈值还短的实体整条不可能命中，直接不进桶。
    gram = max(2, threshold)
    hit = 0
    reported = set()
    # 自动机按实体缓存：同一实体要跟上百个实体各比一次，建表比走表贵得多，
    # 每次重建成这一道防线的主要开销
    built_units = {}

    def _whole(i, j):
        """整条实体比一遍（自动机建在更长的一侧：走表那趟才是长串）。"""
        na = units[i][3]
        nb = units[j][3]
        if len(na) >= len(nb):
            if i not in built_units:
                built_units[i] = _build_sam(na)
            return _lcs_against(built_units[i], nb, early_stop=threshold)
        if j not in built_units:
            built_units[j] = _build_sam(nb)
        return _lcs_against(built_units[j], na, early_stop=threshold)

    def _report(i, j, size, frag):
        rel_a, ln_a = units[i][0], units[i][1]
        rel_b, ln_b = units[j][0], units[j][1]
        ctx.err(_msg(step, "dup_message").replace("{a}", rel_a).replace("{b}", rel_b)
                .replace("{line_a}", str(ln_a)).replace("{line_b}", str(ln_b))
                .replace("{overlap}", str(size)).replace("{frag}", frag), rel_a, ln_a)

    whole_buckets = {}
    for idx, (_rel, _ln, _raw, normalized) in enumerate(units):
        if len(normalized) < gram:
            continue
        for g in {normalized[pos:pos + gram] for pos in range(len(normalized) - gram + 1)}:
            whole_buckets.setdefault(g, []).append(idx)
    whole_hits = []
    for i, j in _pairs_of(whole_buckets):
        # **同一实体不算重复**（一个实体内部的多个 n-gram 会聚成自配对）。
        if units[i][0] == units[j][0] and units[i][1] == units[j][1]:
            continue
        size, frag = _whole(i, j)
        if size >= threshold:
            whole_hits.append((i, j, size, frag))
            reported.add((i, j))
    for i, j, size, frag in whole_hits:
        hit += 1
        _report(i, j, size, frag)

    # 粗筛只聚"长到能整条命中"的那一层，**短行与长短混对**要靠下面这一遍补：
    # 判据与整条层**同一条**（最长公共子串 ≥ 阈值即报），只是核对面从"整条实体"换成
    # "句子"——整条命中的前提是两侧的公共子串跨得过换行，短行与被标点切开的句子都凑不出
    # 来。故不能要求"一句整句出现在另一句里"：那只是"两侧都够长、且没被标点切开"的特例
    # （实证：一条 34 字的判据在一处写全、另一处在字中间被逗号劈开，整条层最长只有 20、
    # 逐句层又要求整句命中，于是逐字重复被静默放行）。
    #
    # 桶的 n-gram 取阈值的一半：本层要接住的正是"阈值以下、但侧边被切开"的形态，
    # 取阈值长度时两侧凑不出共同的 n-gram（切点落在任何 n-gram 内部）；取一半，两侧至少
    # 各剩半个阈值长才可能被同一批候选对看见。
    sent_girs = max(2, threshold // 2)
    sent_buckets = {}
    sent_order = {}
    for idx, (_rel, _ln, raw, _normalized) in enumerate(units):
        for sa in _sentences(raw, min(min_sentence, min_text)):
            sent_order[(idx, sa)] = len(sent_order)
            for pos in range(len(sa) - sent_girs + 1):
                sent_buckets.setdefault(sa[pos:pos + sent_girs], set()).add((idx, sa))
    sent_pairs = set()
    for group in sent_buckets.values():
        if len(group) < 2:
            continue
        # 候选对按**首次出现次序**回收：桶是字典、集合是无序的，直接迭代会让报错次序
        # 随哈希漂移（同一份文档两次跑出两种次序）。
        members = sorted(group, key=lambda m: sent_order[m])
        for x in range(len(members)):
            for y in range(x + 1, len(members)):
                sent_pairs.add((members[x], members[y]))
    sent_hits = []
    built_sent = {}
    for (i, sa), (j, sb) in sorted(sent_pairs,
                                   key=lambda p: (sent_order[p[0]], sent_order[p[1]])):
        key = (i, j) if i < j else (j, i)
        if i == j:
            # 同一实体内部的两句也要比（折叠与展开常落在同一条 bullet 的相邻句里），
            # 但同**一句**不比。
            if sa == sb:
                continue
        elif key in reported:
            continue
        # 判据载体是**本句去断句标点后的样子**：同一段被判据复制后随手断句时，两侧的
        # 句子一对就错位（切口位置不同），而把断句标点去掉之后，一对句子仍要**同为那一句**——
        # 一刀切成两半的形态本层本就不该报（它由整条层按"跨过切口的那一整段"核），
        # 本层只管"同一句被标点切过"这一形态：切口在哪侧、切了几次，去标点后都对得上。
        ta = _strip_punct(sa)
        tb = _strip_punct(sb)
        if len(ta) >= len(tb):
            if (i, sa) not in built_sent:
                built_sent[(i, sa)] = _build_sam(ta)
            size, frag = _lcs_against(built_sent[(i, sa)], tb, early_stop=threshold)
        else:
            if (j, sb) not in built_sent:
                built_sent[(j, sb)] = _build_sam(tb)
            size, frag = _lcs_against(built_sent[(j, sb)], ta, early_stop=threshold)
        if size >= threshold and key not in reported:
            reported.add(key)
            sent_hits.append((key[0], key[1], size, frag))
    for i, j, size, frag in sent_hits:
        hit += 1
        _report(i, j, size, frag)

    if not hit:
        ctx.log(f"  ^ 逐字重复扫描：{len(units)} 个实体、"
                f"{len(whole_hits) + len(sent_hits)} 处重合")


def _step_table_row_pipe(rules, step):
    """**表格行不得以 `|` 收尾**：维护范围内的每份文档里，`|===` 之间的表格行（以 `|` 起头）
    若以 `|` 结尾即报红——AsciiDoc 把它读成**多出一个空单元格**的残缺行。

    为什么需要它：`check_asciidoctor_syntax` 是**确定项**校验，但它只在"本机能装出
    `asciidoctor`"时跑得出问题（本仓库实证：本机长期没有处理器，该段报错而不是报出问题，
    于是**行尾多出的一个 `|`** 安静地留在了 `guards.adoc` 的清单表里）。这类错字有两个
    恶果：① 编译告警（`dropping cells from incomplete row detected end of table`）；
    ② **整表错乱**——多一个空单元格会让后续单元格整体错位，报出的行号还落到**别的行**上。
    而它**不会**被任何按文本核锚点的检查发现（文本一字不少、锚点全在）。

    判据（可逐字判定，与处理器版本无关）：表格行**以 `|` 收尾**即报红；行内相邻单元格之间
    照旧以管道分隔。**行尾那个 `|` 之后的行内注释（`// ...`）与硬换行标记（`+`）先剥掉
    再看正文**——实测 `asciidoctor 2.0.26` 对"裸行尾管道""管道后跟注释""管道后跟硬换行"
    三种写法报的是同一句 `dropping cells from incomplete row detected end of table`，
    只核裸形态会把后两种**漏放**。只核这一种形态——"表格该有几列""某行的单元格是否
    漏写"属语义性判断，仍由 `check_asciidoctor_syntax` 编译验证承担。

    规则参数：
      * `files`（可选）：参与检测的**文件清单**；不给时取维护范围内的全部 `.adoc`
        （`ctx.adoc_files()`，与语法编译段**同一处收集实现**）——**不另列维护根清单**，
        否则"哪些文档算维护范围"就有两处真源、改一处必漏另一处。
    """
    ctx = rules.ctx
    files = step.get("files") or []
    if not files:
        # 维护范围**不外列清单**：`adoc_files()` 与语法编译段同源（同一处实现），
        # 规则数据再自列一份"哪些根算维护范围"就是第二真源——改一处必漏另一处
        # （本条立项的失效形态正是"两处各自漂移"）。未提供时按同源口径取全量。
        files = ctx.adoc_files() if hasattr(ctx, "adoc_files") else []
    files = sorted(set(files))
    if not files:
        ctx.err(_msg(step, "missing_files_message").replace("{file}", "维护范围内的 .adoc"),
                "")
        return
    for rel in files:
        text = ctx.read(rel)
        if text is None:
            ctx.err(_msg(step, "missing_file_message").replace("{file}", rel), rel)
            continue
        in_table = False
        for lineno, line in enumerate(text.splitlines(), 1):
            if line.strip().startswith("|==="):
                in_table = not in_table
                continue
            if not in_table or not line.startswith("|"):
                continue
            # 行尾那个 `|` 之后还可能有**行内注释**（`// ...`）或**硬换行**（`+`）——
            # AsciiDoc 同样把它们读成"多一个空单元格"（实测 `asciidoctor 2.0.26` 对
            # `| A | B | // x` 与 `| A | B | +` 都报同一句
            # `dropping cells from incomplete row detected end of table`）。故先把
            # 行内注释与硬换行标记剥掉，再看剩下的正文是否以 `|` 收尾——否则这两种
            # 真实残缺行会**漏放**（只核"裸行尾管道"一种形态时它们全绿）。
            body = line.rstrip()
            body = re.sub(r"\s*//.*$", "", body) if " // " in body or body.endswith("//") else body
            body = body.rstrip()
            while body.endswith(" +"):
                body = body[:-2].rstrip()
            if body.endswith("|"):
                ctx.err(step["message"].replace("{file}", rel)
                        .replace("{line}", str(lineno)),
                        rel, lineno)


# 平面列表结构（`list_structure`）的三个形态判据：AsciiDoc 的**节标题**（`== ...` 含更长层级）、
# **列表项**（`* ` / `. ` / `- `，与 `_bullet_text` 取条目时的口径同源）、**定界块边界**
# （`----`/`....`/`====`/`****` 一类，**只认至少 4 个同字符**——`===` 是三级节标题，不是块边界）。
_BLOCK_DELIM = re.compile(r"^(?:-{4,}|\.{4,}|={4,}|\*{4,}|_{4,}|\+{4,}|`{3,})$")
_HEADING = re.compile(r"^=+[ \t]")
_LIST_ITEM = re.compile(r"^\*{1,2}\s|^[.\-]\s")
# 块属性行（`[listing]`、`[cols="1,2"]`、`[NOTE]`）：紧跟其后的定界块仍属当前列表项
_BLOCK_ATTR = re.compile(r"^\[[^\]]+\]$")


def _step_prose_mentions(rules, step):
    """**同一取值在正文里被复述**：`sources` 下每份文档里，`values` 中任一取值**在正文中
    出现**即报红；只有**同一段落里同样出现 `cite_tokens` 之一**（那是对真源的一句回指）时
    才放行。

    为什么需要它（本仓库实证的失效形态）：`script/specs-config.toml` 立为"唯一真源"后，
    **代码侧**接上了（常量从配置算），**文档与规则数据侧**却照旧各抄一份——`specs-config.toml`
    自己的头部注释写着"配置文件自己叫什么"、"安装脚本名单"、"超时与并发"的取值，
    `pathconfig.py` 的 docstring 把落点写了一遍，维护方台账 `guards.adoc` 的那一行又把落点
    与其余取值复述了一遍。它们**都是正文**，而当时唯一的抓手只核"落点这一串在**代码文件**里
    出没出现"——于是改配置时这几处必然静默漂移，且检查全绿。

    判据是"**引用形态**"而不是"这些字不许出现"：谈这件事的地方天然要提它，规则要求的是
    **提真源的名字**、不复述取值。故 `cite_tokens` 是这条判据的开关——只提及、不引真源的
    那一处才是第二份来源。

    给 `section` 时只核该节（`_step_target` 同口径：整份文件里别处的同形字样会兜住缺项）。
    """
    text, scope_desc = _step_target(rules, step)
    if text is None:
        return
    del scope_desc
    values = step["values"]
    cites = step["cite_tokens"]
    hits = [v for v in values if v and v in text]
    if not hits:
        return
    paragraphs = _prose_paragraphs(text)
    for hit in hits:
        for para in paragraphs:
            if hit not in para:
                continue
            if any(c in para for c in cites):
                continue
            rules.ctx.err(
                step["message"].replace("{file}", step["file"])
                .replace("{hit}", hit).replace("{cite}", " / ".join(cites)),
                step["file"])
            break


def _prose_paragraphs(text):
    """把文本切成段落（空行、标题行、代码块定界处断开）——判据的粒度是"同一段落里有没有回指"。

    不按整份文件判：一处给了回指、另一处复述时，按整份核会把复述那一处兜住（本仓库实测：
    文档里既有"取值见配置"的回指、又有一行把落点写全，按整份判即全绿）。
    """
    out, buf, in_block = [], [], False
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped == "----":
            in_block = not in_block
            out.append("\n".join(buf))
            buf = []
            continue
        if in_block:
            continue
        if not stripped or re.match(r"^=+\s", stripped):
            out.append("\n".join(buf))
            buf = []
            continue
        buf.append(line)
    out.append("\n".join(buf))
    return [p for p in out if p.strip()]


def _step_list_structure(rules, step):
    """核**列表结构没被写坏**：平面列表范围内缩进了即报红。

    判据、范围与白名单的落点是 `script/specs-rules/list.toml`，本函数只实现它。
    规则参数：`files`（可选），不给时取维护范围内的全部 `.adoc`。
    """
    ctx = rules.ctx
    files = sorted(set(step.get("files") or (ctx.adoc_files() if hasattr(ctx, "adoc_files") else [])))
    if not files:
        ctx.err(_msg(step, "missing_files_message").replace("{file}", "维护范围内的 .adoc"), "")
        return
    for rel in files:
        text = ctx.read(rel)
        if text is None:
            ctx.err(_msg(step, "missing_file_message").replace("{file}", rel), rel)
            continue
        in_block = False       # 定界块内部：块内的缩进本来就用
        in_list = False        # 上一行之后，平面列表是否还在继续
        after_block = False    # 白名单：紧贴定界块收尾的**那一段**（遇空行即复原，防它悄悄扩散）
        for lineno, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                # 空行不算列表断开（列表中间可隔着空段）；白名单只管**紧贴块收尾的那一段**，
                # 隔了空行即失效（否则"插完块再续写缩进"能绕开整道防线）。
                after_block = False
                continue
            if _BLOCK_DELIM.match(line.strip()):
                if in_block:
                    in_block = False
                    after_block = in_list
                elif not (line[0] in " \t"):
                    in_block = True
                    after_block = False
                continue
            if in_block:
                continue
            if _HEADING.match(line):
                # 节标题**不结束**列表范围：列表到"顶格非列表正文"为止，小节标题不是正文
                # （判据原文如此）。此处只把白名单复原——块刚收尾就换节时，那一段白名单失效。
                after_block = False
                continue
            if not (line[0] in " \t"):
                # 顶格行三种：**列表项**与**块属性行**（`[listing]` 一类，仍属条目内的块）
                # 让列表继续；**顶格非列表正文**则是列表范围的终点。
                if _LIST_ITEM.match(line):
                    in_list = True
                elif not _BLOCK_ATTR.match(line):
                    in_list = False
                after_block = False
                continue
            if in_list and not after_block:
                ctx.err(step["message"].replace("{file}", rel)
                        .replace("{line}", str(lineno)), rel, lineno)


KINDS = {
    "exists": _step_exists,
    "section_groups": _step_section_groups,
    "subsection_groups": _step_subsection_groups,
    "file_groups": _step_file_groups,
    "file_tokens": _step_file_tokens,
    "line_tokens": _step_line_tokens,
    "forbid_section": _step_forbid_section,
    "file_forbidden": _step_file_forbidden,
    "split_block": _step_split_block,
    "regex_section": _step_regex_section,
    "bullet_tokens": _step_bullet_tokens,
    "anchor_count": _step_anchor_count,
    "prompt_files_groups": _step_prompt_files_groups,
    "section_bullets": _step_section_bullets,
    "text_block_groups": _step_text_block_groups,
    "dispatcher_no_verbatim": _step_dispatcher_no_verbatim,
    "duplicate_scan": _step_duplicate_scan,
    "pointer_no_verbatim": _step_pointer_no_verbatim,
    "table_row_pipe": _step_table_row_pipe,
    "list_structure": _step_list_structure,
    "prose_mentions_generated": _step_prose_mentions,
}


class Rules:
    """一份规则数据 + 通用的核对原语。

    参数
    ----
    data : dict
        `{"guards": {<防线名>: [<步骤>...]}}`，步骤的 `kind` 取值见 `KINDS`。
    ctx : object
        上下文对象，须提供 `err(msg, path="", line=0)`、`read(rel)`、`section(text, title)`、
        `subsection(text, keyword)`、`tokens(name)`（`anchor_count` 按清单名取条数时用）
        （由调用方提供；本模块不直接依赖它，便于单测注入夹具）。
    """

    def __init__(self, data, ctx):
        if not isinstance(data, dict) or not isinstance(data.get("guards"), dict):
            raise RulesError("规则配置结构不符：须为 {'guards': {<防线名>: [<步骤>...]}}")
        # 同一套加载期判据，走 `load_rules`（按文件加载）与直接构造（单测注入）两条路
        # 都要过——只挂在前者时，直接构造的规则数据仍能把 `{section}` 写进报错正文。
        for name, steps in data["guards"].items():
            _check_placeholders("<内存>", name, steps)
        self._guards = data["guards"]
        self.ctx = ctx

    # ---- 查询 ----

    def has(self, guard: str) -> bool:
        return guard in self._guards

    def guard_names(self):
        return sorted(self._guards)

    def steps(self, guard: str) -> list:
        if guard not in self._guards:
            raise RulesError(f"规则配置里没有防线 `{guard}`——防线名与配置须一一对应，"
                             "缺配置时该防线会静默变成空转")
        return self._guards[guard]

    # ---- 执行 ----

    def run(self, guard: str) -> None:
        """跑某道防线的全部规则步骤（步骤相互独立：任一失败即报错、其余照跑）。

        运行前给每步注入 `_guard`（**运行期视图，不回写规则数据**）：步骤之间可以互相
        取用对方的信息（如 `anchor_count` 取同防线同 bullet 的 `bullet_tokens` 步的锚点条数），
        故步骤须知道自己属于哪道防线。
        """
        for step in self.steps(guard):
            step["_guard"] = guard
            self._run_step(step)

    def _run_step(self, step):
        kind = step.get("kind")
        handler = KINDS.get(kind)
        if handler is None:
            raise RulesError(f"未知规则步骤类型 `{kind}`——配置文件里有引擎不认识的 kind，"
                             "若是拼写错误则该规则会静默不生效")
        handler(self, step)


def load_rules(path: str):
    """读并解析**一个**规则文件；文件缺失或 TOML 非法时抛 `RulesError`（不静默退回）。

    单文件读法保留给"只想知道某一份里写了什么"的场合；防线侧一律走 `load_rule_files`
    （自动扫描规则目录、把全部规则文件合并成一个数据集）。
    """
    if not os.path.isfile(path):
        raise RulesError(f"缺少规则文件 {path}——规则数据与脚本隔离后，"
                         "规则文件是规则措辞的唯一来源，缺失即整批防线空转")
    return _load_toml(path)


def _load_toml(path: str):
    """按 TOML 解析一份规则文件；语法/结构非法一律抛 `RulesError`（不静默退回）。

    解析器用标准库 `tomllib`（Python 3.11+）——**不引入第三方依赖**：引擎是校验链的
    确定项，装依赖才跑得起来等于"缺工具就静默跳过"（见 `specs/general/ci-cd.adoc`）。
    TOML 自身的语法就是一层确定项：重复表头（同名防线/同名名单）直接被解析器拒绝，
    不必等加载期才发现"两处各写一半"。

    读与解析都走缓存（键是文件字节的摘要、**不是路径**）：同一份规则从不同目录读出来
    （单测把规则原样落到各自的临时仓库根）只解析一次，改动任何一个字节即换键。
    """
    key = _digest(read_bytes(path))
    if key not in _TOML_CACHE:
        raw = read_bytes(path)
        try:
            _TOML_CACHE[key] = tomllib.loads(raw.decode("utf-8"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
            raise RulesError(f"规则文件 {path} 不是合法 TOML：{exc}")
    # 交出的是**浅拷贝**：`guards` / `tokens` 两张表各是新字典，表内的取值（锚点清单、
    # 报错文案）共用同一份、按只读使用。合并期只往这两张表里加键，不会改已有取值。
    return {k: dict(v) if isinstance(v, dict) else v for k, v in _TOML_CACHE[key].items()}


def read_bytes(path: str) -> bytes:
    """读一份规则文件的原始字节（缓存键的**唯一来源**：读与解析用同一份内容）。"""
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError as exc:
        raise RulesError(f"规则文件 {path} 读不出来：{exc}")


def _digest(raw: bytes) -> bytes:
    return hashlib.sha256(raw).digest()


def _check_placeholders(name: str, guard: str, steps) -> None:
    """校验防线各步骤里的报错文案**只用得到 `PLACEHOLDERS` 里的占位符**。

    文案里写了别的名字（本仓库实测：把 `{file}` 写成 `{rel_exec}`）`_fill` 填不进去，
    报错正文会原样带着 `{rel_exec}` 交给读者——那是"缺失说明给不出缺失对象"，
    属规则数据本身的错，故在加载期就报错、不等跑起来才发现。
    """
    for step in steps if isinstance(steps, list) else []:
        if not isinstance(step, dict):
            continue
        for key, value in step.items():
            if not key.endswith("message") or not isinstance(value, str):
                continue
            for ph in re.findall(r"\{([a-z_]+)\}", value):
                if ph not in PLACEHOLDERS:
                    raise RulesError(
                        f"规则文件 {name} 的防线 `{guard}` 在 `{key}` 里用了引擎不认识的"
                        f"占位符 `{{{ph}}}`——可用的是 {list(PLACEHOLDERS)}；"
                        "写错的占位符会原样留在报错正文里，读者看不到缺失的是哪个文件")


# `tokens` 里"不给规则引擎用、只给脚本读"的纯数据表名（提到顶层供脚本直取）。
#
# 为什么要这张名单：规则文件里的措辞必须"改措辞不动代码"，但**不是所有措辞都是锚点组**
# ——例如『NPC 禁合并·动作侧』的措辞表（提交说明里哪些话术算"合并动作的痕迹"、哪些算
# "记录禁令的放行标记"）是纯数据表，规则引擎不认它的结构。故允许它包在 `tokens` 里
# 过纯度判据，再由本名单显式提到顶层。
DATA_TABLE_KEYS = ("merge_state_guard", "change_number_scope_guard")


# 解析与合并结果都按**内容摘要**缓存（不按路径）：`tomllib` 是纯 Python，一批规则整体
# 解析 + 合并合计几十毫秒，而调用方每次都要"取同一批文件"——现场跑一次只要一次，
# **单测**却要跑上百次（每道防线的用例各自把规则原样落到临时目录、各自重建引擎实例；
# 路径每次都不同、内容一字不差）。键取字节摘要：任何一处改动都会换键，不存在"读到旧
# 规则"；路径不入键，才使"同一份规则从不同目录读"共用一次解析。
# 缓存里存**可变**结构，交出去的是浅拷贝（见 `_load_toml` / `load_rule_files`）——
# 引擎会就地把 `_guard` 写进步骤表，深拷一份冻结结构比省下的解析还贵。
_TOML_CACHE = {}
# 合并结果同样按内容缓存（见 `load_rule_files`）：键是这批文件摘要的排序元组。
_MERGED_CACHE = {}


def _merge_file(name: str, data, merged: dict) -> None:
    """把一份规则文件并进汇总数据集；**同键冲突即报错**（不静默覆盖）。

    `tokens` 段另允许承载**不给规则引擎用、只给脚本读的纯数据表**（如
    『NPC 禁合并·动作侧』的措辞表 `merge_state_guard`）：它们同样是"改措辞不动代码"
    的落点，包一层 `tokens` 只是为过"规则文件只承载 guards/tokens 两键"的纯度判据。
    """
    if not isinstance(data, dict):
        raise RulesError(f"规则文件 {name} 不是对象（顶层须为 `guards` / `tokens` 两张表）")
    for key, value in data.get("guards", {}).items():
        if key in merged["guards"]:
            raise RulesError(f"规则文件 {name} 与其它规则文件重复定义了防线 `{key}`——"
                             "同一防线的规则只能有一处落点（第二处会让你改了其中一份、"
                             "另一份照旧生效；这正是'规则与脚本隔离'要防的形态）")
        _check_placeholders(name, key, value)
        merged["guards"][key] = value
    for key, value in data.get("tokens", {}).items():
        if key in merged["tokens"]:
            raise RulesError(f"规则文件 {name} 与其它规则文件重复定义了名单/锚点 `{key}`——"
                             "同一份名单只能有一处落点（两处会各写一半、彼此漂移）")
        merged["tokens"][key] = value
    # tokens 里的纯数据表（非锚点组）**提到顶层**：脚本按表名直取，不必知道它包在 tokens 里。
    # 注意：**检测重复用的是 `is not None`**——合并容器在开头就把这些键预置成了 None，
    # 用 `in` 判会一律命中"重复定义"（实测踩过）。
    for key, value in data.get("tokens", {}).items():
        if key in DATA_TABLE_KEYS:
            if merged[key] is not None:
                raise RulesError(f"规则文件 {name} 与其它规则文件重复定义了数据表 `{key}`——"
                                 "同一份数据表只能有一处落点")
            merged[key] = value


def load_rule_specs(spec) -> dict:
    """按 `spec` 展开成**规则文件清单**，并自动扫描其中是目录的那些。

    `spec` 允许字符串或列表，元素可以是"某个文件"或"某个目录"：

    * **目录**：自动扫描其下全部 `*.toml`（按文件名排序，次序稳定），该目录即"一类规则
      的落点"——新增一个规则文件**不必改任何脚本**（脚本只登记目录，不登记文件名）；
    * **文件**：只有确需单点指定的场合才写具体文件名。

    据此 `spec` 可以只是**一个目录**，脚本侧不必逐个列出规则文件——"自动扫描规则文件
    加载"要买的正是这件事：加一个规则文件不需要动 `.py`。
    """
    items = [spec] if isinstance(spec, (str, os.PathLike)) else list(spec)
    files = []
    for item in items:
        item = str(item)
        if os.path.isdir(item):
            names = sorted(f for f in os.listdir(item)
                           if f.endswith(RULES_FILE_SUFFIX) and not f.startswith("."))
            if not names:
                raise RulesError(f"规则目录 {item} 里没有任何 *{RULES_FILE_SUFFIX}——目录是'一类规则的"
                                 "落点'，空目录意味着这一批规则整体消失（不得静默放过）")
            files.extend(os.path.join(item, f) for f in names)
        else:
            files.append(item)
    return files


def load_rule_files(spec) -> dict:
    """按 `spec` 加载并**合并**全部规则文件（自动扫描目录），返回 `{"guards":…, "tokens":…}`。

    合并不是"后一份覆盖前一份"：重复防线名/名单名一律抛 `RulesError`——两条规则同名时，
    读者会以为新的一条生效，而实际生效的可能是另一份文件里的那一条。
    """
    paths = load_rule_specs(spec)
    # 合并结果按**这批文件的内容**缓存：合并（逐个文件并进同一张表、逐条核占位符）比解析
    # 还贵一点，且它与内容一一对应。键取各文件摘要的排序结果——同一批内容只合一次。
    key = tuple(sorted(_digest(read_bytes(path)) for path in paths))
    if key not in _MERGED_CACHE:
        _MERGED_CACHE[key] = _merge_all(paths)
    # 浅拷贝（`guards` / `tokens` 两张新字典）：引擎运行期要给步骤注入 `_guard`（就地写），
    # 步骤表因此**每道防线各一份**——一份规则被多道防线取用时，改这份不会串到那份。
    merged = _MERGED_CACHE[key]
    out = {k: dict(v) if isinstance(v, dict) else v for k, v in merged.items()}
    out["guards"] = {name: [dict(step) if isinstance(step, dict) else step for step in steps]
                     for name, steps in merged["guards"].items()}
    return out


def _merge_all(paths) -> dict:
    """把一批规则文件并成 `{"guards":…, "tokens":…}`；冲突即抛 `RulesError`。"""
    merged = {"guards": {}, "tokens": {}, **{k: None for k in DATA_TABLE_KEYS}}
    for path in paths:
        if not os.path.isfile(path):
            raise RulesError(f"缺少规则文件 {path}——规则数据与脚本隔离后，"
                             "规则文件是规则措辞的唯一来源，缺失即整批规则静默失效")
        _merge_file(os.path.basename(path), _load_toml(path), merged)
    for key in DATA_TABLE_KEYS:
        if merged[key] is None:
            del merged[key]
    if not merged["guards"]:
        raise RulesError("规则文件里一道防线的规则都没有——规则数据整体缺失，"
                         "所有防线会静默空转（不得当成'没有规则就是通过'）")
    return merged
