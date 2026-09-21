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
    "missing_line_message": "缺少 {file} 的对应条目——没有登记行则该条实际失效",
    "missing_block_message": "缺少 {file} 的 `{marker}` 片段——该边界在提示词侧失去落点",
    "file_message": "缺少 {file}——该条的落点无从核对",
    "dup_message": "{a}:{line_a} 与 {b}:{line_b} 逐字重合 {overlap} 字：`{frag}`",
    "dup_missing_files_message": "逐字重复扫描的落点不足（{file}）——少于两个可核对文档时该防线空转",
}


# 报错文案里允许出现的占位符：`_check_groups` 按这几个名字填值。
# 文案里写了别的名字（如把 `{file}` 写成 `{rel_exec}`）`_fill` 填不进去，
# 报错正文就会原样带着 `{rel_exec}` 给读者看——加载期一律拒绝。
# 可用占位符（加载期校验 `message` 里不得出现白名单外的名字）。
# `ref`/`overlap`/`frag`/`line` 供 `dispatcher_no_verbatim` 报告"与哪个文件重合了多少字、
# 重合的片段是什么、在第几行"——写错的占位符会原样留在报错正文里，故同样在加载期拦住。
# `a`/`b`/`line_a`/`line_b` 供 `duplicate_scan` 报告"哪两处、各自在第几行"。
PLACEHOLDERS = ("file", "missing", "desc", "hit", "ref", "overlap", "frag", "line",
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
        ctx.err(_msg(step, "missing_section_message").replace("{file}", rel)
                .replace("{section}", step["section"]), rel)
        return
    _check_groups(ctx.err, rel, f"「{step['section']}」节", section, step["groups"],
                  prefix=step.get("prefix", ""), template=step.get("message"))


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
        ctx.err(_msg(step, "missing_section_message").replace("{file}", rel)
                .replace("{section}", step["subsection"]), rel)
        return
    _check_groups(ctx.err, rel, f"「{step['subsection']}」小节", section, step["groups"],
                  prefix=step.get("prefix", ""), template=step.get("message"))


def _step_file_groups(rules, step):
    """整份文件逐组核锚点（判据对象是全文，如"该文件里必须出现这几组要点"）。"""
    ctx = rules.ctx
    rel = step["file"]
    text = ctx.read(rel)
    if text is None:
        ctx.err(_msg(step, "missing_file_message").replace("{file}", rel), rel)
        return
    _check_groups(ctx.err, rel, step.get("scope", "文件"), text, step["groups"],
                  prefix=step.get("prefix", ""), template=step.get("message"))


def _step_file_tokens(rules, step):
    """整份文件核一组平铺锚点（不分组，缺任一即报同一条说明）。"""
    ctx = rules.ctx
    rel = step["file"]
    text = ctx.read(rel)
    if text is None:
        ctx.err(_msg(step, "missing_file_message").replace("{file}", rel), rel)
        return
    miss = [t for t in step["tokens"] if t not in text]
    if miss:
        ctx.err(step["message"].replace("{file}", rel).replace("{missing}", str(miss)), rel)


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
        ctx.err(_msg(step, "missing_line_message"), rel)
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


def _step_section_bullets(rules, step):
    """取节内**每个分组自身**的 bullet 文本，再核该组的其余锚点（条目内核对）。

    分组形态：`[标题, [标题, 锚点...], 说明]`——首项是 bullet 前缀、其余是须落在
    **该 bullet 正文**里的锚点。只核整节时，相邻条目的字样会兜住被抽空的条目。
    `ctx.bullet` 取不到该 bullet 时**跳过**（轴标题缺失由别的检查负责，避免重复发声）。
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
        prefix, anchors = tokens[0], tokens[1:]
        bullet = ctx.bullet(section, prefix)
        if bullet is None:
            continue
        miss = [t for t in anchors if t not in bullet]
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

    def _lcs(a, b):
        if not a or not b:
            return 0, ""
        prev = [0] * (len(b) + 1)
        best = 0
        end = 0
        for i in range(1, len(a) + 1):
            cur = [0] * (len(b) + 1)
            ai = a[i - 1]
            for j in range(1, len(b) + 1):
                if ai == b[j - 1]:
                    cur[j] = prev[j - 1] + 1
                    if cur[j] > best:
                        best = cur[j]
                        end = i
            prev = cur
        return best, a[end - best:end]

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
            overlap, frag = _lcs(ndesc, _spec_norm(ref))
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
            refs = re.findall(r"[A-Za-z0-9_./-]*\.adoc", line)
            refs = [r for r in refs if r != os.path.basename(rel) and r not in exclude_refs]
            if not refs:
                continue
            nline = _norm(line)
            if len(nline) < threshold:
                continue
            for ref in refs:
                if ctx.read(ref) is None:
                    continue
                overlap, frag = _sam_lcs(nline, _spec_norm(ref))
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


def _longest_common(a, b):
    """最长公共子串（返回 (长度, 片段)）。DP + 一维滚动数组，纯 stdlib。"""
    if not a or not b:
        return 0, ""
    prev = [0] * (len(b) + 1)
    best = end = 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            if ai == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
                    end = i
        prev = cur
    return best, a[end - best:end]


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


def _sam_lcs(a, b):
    """最长公共子串（后缀自动机版）：对 `b` 建 SAM、再拿 `a` 在上面走一遍。

    为什么不用 DP：本条的核对对象是**全对**实体（数千条实体两两比对），DP 的
    O(len(a)·len(b)) 在真实规模下是十亿级单元、分钟级耗时；SAM 是 O(len(a)+len(b))，
    且仓储级规模下实测亚秒级。返回 (长度, 片段)——**完全匹配时片段可能不唯一**，
    报错文案里的片段只作定位提示，判据是长度本身。
    """
    if not a or not b:
        return 0, ""
    nxt = [{}]
    link = [-1]
    length = [0]
    last = 0
    for ch in b:
        cur = len(nxt)
        nxt.append({})
        length.append(length[last] + 1)
        link.append(0)
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
    v = 0
    ln = 0
    best = 0
    end = 0
    for i, ch in enumerate(a):
        while v and ch not in nxt[v]:
            v = link[v]
            ln = length[v]
        if ch in nxt[v]:
            v = nxt[v][ch]
            ln += 1
            if ln > best:
                best = ln
                end = i + 1
        else:
            v = 0
            ln = 0
    return best, a[end - best:end]


def _step_duplicate_scan(rules, step):
    """**同一件事不得两处逐字重复**：对 `sources`（文件或目录）下每份文档切成语义实体，
    先按 n-gram 粗筛出候选对，再做全对最长公共子串检测——超过阈值即报红。

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
      * `min_sentence`：按句核对时单句的最短长度（默认同 `min_overlap`）；
      * `min_text`：实体短于该长度即不参与（默认同 `min_overlap`）；
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
    units = []
    for rel in files:
        body = ctx.read(rel) or ""
        for lineno, raw, normalized in _dup_units(rel, body):
            if len(normalized) < min_text:
                continue
            if any(ig in raw for ig in ignores):
                continue
            units.append((rel, lineno, raw, normalized))
    if len(units) < 2:
        ctx.log("  ^ 逐字重复扫描：可核对实体不足，本次未形成有效扫描面")
        return

    # 粗筛：按 n-gram 桶聚出候选对。全对 DP 在真实规模下是分钟级，粗筛把它压到亚秒级。
    # **取 n-gram 时必须逐位滑动、不能按固定步长跳跃**：公共子串在两串里的起点未必同余，
    # 按 `gram` 步长取样时整段公共子串可能一个样本都取不到（本轮实证：两个 bullet 有 55 字
    # 公共子串，取步长 8 时桶交集为空、防线**静默放行**）。逐位取样仍是 O(总长)，
    # 数量级不变，但**不漏**——公共子串长于 n-gram 时，其每个 n-gram 都落在同一对实体的桶里。
    gram = min(8, max(2, threshold // 3))
    buckets = {}
    for idx, (_rel, _ln, _raw, normalized) in enumerate(units):
        for j in range(0, max(1, len(normalized) - gram + 1)):
            buckets.setdefault(normalized[j:j + gram], []).append(idx)
    candidate = set()
    for group in buckets.values():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                candidate.add((group[i], group[j]))

    hit = 0
    seen = set()
    for i, j in sorted(candidate):
        rel_a, ln_a, raw_a, na = units[i]
        rel_b, ln_b, raw_b, nb = units[j]
        # **同一实体不算重复**（粗筛会把一个实体的多个 n-gram 桶聚成自配对）。
        if rel_a == rel_b and ln_a == ln_b:
            continue
        key = (min(i, j), max(i, j))
        if key in seen:
            continue
        seen.add(key)
        size, frag = _sam_lcs(na, nb)
        if size < threshold:
            # 折叠 vs 展开：同一事实在一处换了行、在别处铺成多行时，整条公共子串会被换行
            # 打断——改按**句子**（'。' 切分）逐句核，补上这一形态。
            done = False
            for sent_a in raw_a.split("。"):
                sa = _norm_dup(sent_a)
                if len(sa) < max(min_sentence, min_text):
                    continue
                for sent_b in raw_b.split("。"):
                    sb = _norm_dup(sent_b)
                    if len(sb) < min_sentence:
                        continue
                    ssize, sfrag = _sam_lcs(sa, sb)
                    if ssize >= threshold:
                        size, frag = ssize, sfrag
                        done = True
                        break
                if done:
                    break
        if size >= threshold:
            hit += 1
            ctx.err(_msg(step, "dup_message").replace("{a}", rel_a).replace("{b}", rel_b)
                    .replace("{line_a}", str(ln_a)).replace("{line_b}", str(ln_b))
                    .replace("{overlap}", str(size)).replace("{frag}", frag), rel_a, ln_a)
    if not hit:
        ctx.log(f"  ^ 逐字重复扫描：{len(units)} 个实体、{len(candidate)} 对候选，"
                "无超阈值重合")



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
    "prompt_files_groups": _step_prompt_files_groups,
    "section_bullets": _step_section_bullets,
    "text_block_groups": _step_text_block_groups,
    "dispatcher_no_verbatim": _step_dispatcher_no_verbatim,
    "duplicate_scan": _step_duplicate_scan,
    "pointer_no_verbatim": _step_pointer_no_verbatim,
}


class Rules:
    """一份规则数据 + 通用的核对原语。

    参数
    ----
    data : dict
        `{"guards": {<防线名>: [<步骤>...]}}`，步骤的 `kind` 取值见 `KINDS`。
    ctx : object
        上下文对象，须提供 `err(msg, path="", line=0)`、`read(rel)`、`section(text, title)`、
        `subsection(text, keyword)`（由调用方提供；本模块不直接依赖它，
        便于单测注入夹具）。
    """

    def __init__(self, data, ctx):
        if not isinstance(data, dict) or not isinstance(data.get("guards"), dict):
            raise RulesError("规则配置结构不符：须为 {'guards': {<防线名>: [<步骤>...]}}")
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
        """跑某道防线的全部规则步骤（步骤相互独立：任一失败即报错、其余照跑）。"""
        for step in self.steps(guard):
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
    """
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise RulesError(f"规则文件 {path} 不是合法 TOML：{exc}")


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


def _merge_file(name: str, data, merged: dict) -> None:
    """把一份规则文件并进汇总数据集；**同键冲突即报错**（不静默覆盖）。"""
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
    merged = {"guards": {}, "tokens": {}}
    for path in load_rule_specs(spec):
        if not os.path.isfile(path):
            raise RulesError(f"缺少规则文件 {path}——规则数据与脚本隔离后，"
                             "规则文件是规则措辞的唯一来源，缺失即整批规则静默失效")
        _merge_file(os.path.basename(path), _load_toml(path), merged)
    if not merged["guards"]:
        raise RulesError("规则文件里一道防线的规则都没有——规则数据整体缺失，"
                         "所有防线会静默空转（不得当成'没有规则就是通过'）")
    return merged
