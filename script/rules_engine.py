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
}


# 报错文案里允许出现的占位符：`_check_groups` 按这几个名字填值。
# 文案里写了别的名字（如把 `{file}` 写成 `{rel_exec}`）`_fill` 填不进去，
# 报错正文就会原样带着 `{rel_exec}` 给读者看——加载期一律拒绝。
PLACEHOLDERS = ("file", "missing", "desc")


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
    miss = [t for t in step["tokens"] if t not in bullet]
    if miss:
        ctx.err(step["message"].replace("{missing}", str(miss)), rel)


def _step_prompt_files_groups(rules, step):
    """对 `prompts/` 下每个任务提示词文件逐组核锚点。

    提示词的题面各有自己的措辞，"公共片段里有"不代表"题面里也有"——故题面侧须逐文件核。
    文件清单由 `ctx.prompt_files()` 给（跳过 `_` 前缀的公共片段）。
    """
    ctx = rules.ctx
    files = ctx.prompt_files()
    if not files:
        ctx.err(step.get("missing_files_message",
                         "prompts/ 下未找到任何任务提示词文档（除 `_` 前缀公共片段外）"),
                "prompts/")
        return
    for rel in files:
        text = ctx.read(rel)
        if text is None:
            ctx.err(_msg(step, "missing_file_message").replace("{file}", rel), rel)
            continue
        _check_groups(ctx.err, rel, step.get("scope", "文件"), text, step["groups"],
                      prefix=step.get("prefix", ""), template=step.get("message"))


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



KINDS = {
    "exists": _step_exists,
    "section_groups": _step_section_groups,
    "subsection_groups": _step_subsection_groups,
    "file_groups": _step_file_groups,
    "file_tokens": _step_file_tokens,
    "line_tokens": _step_line_tokens,
    "forbid_section": _step_forbid_section,
    "split_block": _step_split_block,
    "regex_section": _step_regex_section,
    "bullet_tokens": _step_bullet_tokens,
    "prompt_files_groups": _step_prompt_files_groups,
    "section_bullets": _step_section_bullets,
    "text_block_groups": _step_text_block_groups,
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
