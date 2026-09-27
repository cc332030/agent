#!/usr/bin/env python3
"""最小 YAML 子集解析器（纯 stdlib，无第三方依赖）。

用途与边界
----------
本仓库的机械校验按 `specs/general/ci-cd.adoc`「校验链完整」的要求，**不得依赖本机恰好
装了什么第三方库**——引入 PyYAML 会让「校验手段」多一个环境前提（缺它即静默跳过或直接
失败，两种都不是本集合要的）。故这里只实现**本项目流水线配置真正用到的那一小撮 YAML**：

* 块映射（`key:` 与 `key: 值`）、块序列（`- 值`、`- key: 值` 起的映射项）、嵌套缩进；
* 行内流式序列 `[a, b, c]`（元素只允许标量，不嵌套集合）；
* 标量：裸串、带引号串（单/双引号）、`~`/`null`/空值为 `None`、`true`/`false`、整数；
  **键名一律按字符串取**（不做 YAML 1.1 的隐式类型推断）——这是与 PyYAML 的**已知差异**：
  PyYAML 按 YAML 1.1 把键 `on:` 读成布尔 `True`（`yes`/`no`/`on`/`off` 同理），而流水线
  配置里 `on:`（触发条件）、`on: push` 是**键名不是布尔值**，按字符串取才与配置的语义一致；
* 注释（`#` 起，只在行首或空白之后起效）与空行；制表符缩进一律报错（YAML 本就不允许）。

**不支持**（遇到即取不到键，**不猜**）：锚点/别名、多文档（`---`）、块标量（`|`/`>`）、
流式映射、复杂键、`!` 标签。解析结果是一个普通 `dict`/`list`/标量树——取值走
`get_path(node, "jobs.build.steps.0.run")` 这类路径，取不到返回 `None`。

定位：这是**判据的读入件**，不是通用 YAML 库；解析失败一律抛 `YamlSubsetError`
（调用方按"配置读不出来即报红"处置，不得当成"文件没有该键"）。
"""

import re

__all__ = ["YamlSubsetError", "load", "load_all_as", "get_path", "iter_mapping_entries"]


class YamlSubsetError(ValueError):
    """本解析器不支持或不合法的写法——调用方须报红，不得静默放过。"""


_NUM_RE = re.compile(r"^[+-]?\d+$")
_KEY_RE = re.compile(r"^([^:\s][^:]*?)\s*:(?:\s+(.*))?$")


class _Line:
    __slots__ = ("indent", "text", "no")

    def __init__(self, indent, text, no):
        self.indent = indent
        self.text = text
        self.no = no


def _strip_comment(raw: str) -> str:
    """剥掉行内注释：`#` 只在**行首或空白之后**才算注释起点（`a#b` 是普通标量）。"""
    out = []
    for i, ch in enumerate(raw):
        if ch == "#" and (i == 0 or raw[i - 1] in " \t"):
            break
        out.append(ch)
    return "".join(out).rstrip()


_ALIAS_RE = re.compile(r"^[&*][^\s\[\]{},]+$")


def _split_scalar(text: str):
    """把标量文本转成 Python 值（只处理本子集里的那几种）。

    **不做**"标量里出现 `key:` 即报错"的判断：`run: echo a: b`（内联复合结构、
    `a:#b` 这类含冒号的裸串）都是合法 YAML，在那里报错会把整份配置判成"读不出来"，
    把真正该核的步骤一并拦掉。会**被**判成不合法的冒号写法由 `_split_key` 拦：
    `key: a: b` 里的外层键按**第一个** `: ` 切开，剩下的 `a: b` 落到本函数，
    作为字符串值读入（值不进判据，不影响"这一步有没有时限"）。
    """
    s = text.strip()
    # 锚点/别名（`&name` / `*name`）：本子集**不解析成引用**——原样当标量文本返回。
    # 这是刻意的：本仓库的 `.github/workflows/check-specs.yml` 用 `paths: &spec-paths`
    # 在两个触发点之间复用一段序列，把整份配置判成"读不出来"会**拦掉真正该核的步骤**。
    # 代价是"别名指到哪"不进判据（引用面本身不承载判据）；对"每一步有没有时限"没有影响。
    if _ALIAS_RE.match(s):
        return s
    if s[:1] in ("|", ">") and len(s) <= 2:
        return ""
    if s == "" or s in ("~", "null", "Null", "NULL"):
        return None
    if s in ("true", "True", "TRUE"):
        return True
    if s in ("false", "False", "FALSE"):
        return False
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        body = s[1:-1]
        return body.replace("''", "'") if s[0] == "'" else body.replace('\\"', '"')
    if _NUM_RE.match(s):
        return int(s)
    return s


def _split_inline_list(text: str):
    """行内流式序列 `[a, b]` → list；非本子集形态返回 None。"""
    s = text.strip()
    if not (s.startswith("[") and s.endswith("]")):
        return None
    inner = s[1:-1].strip()
    if inner == "":
        return []
    items, buf, quote = [], [], None
    for ch in inner:
        if quote:
            if ch == quote:
                quote = None
            buf.append(ch)
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
        elif ch == ",":
            items.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    items.append("".join(buf))
    out = []
    for it in items:
        it = it.strip()
        if it.startswith("[") or it.startswith("{"):
            raise YamlSubsetError("行内序列不支持嵌套集合：%r" % it)
        out.append(_split_scalar(it))
    return out


def _split_key(text: str):
    """`key: value` → (key, value_text)；不像映射项时返回 None。"""
    m = _KEY_RE.match(text)
    if not m:
        return None
    key = m.group(1).strip()
    if key.startswith(("'", '"')) and key.endswith(key[0]) and len(key) >= 2:
        key = key[1:-1]
    if key.startswith("[") or key.startswith("{") or key.startswith("?"):
        raise YamlSubsetError("不支持复杂键：%r" % key)
    return key, (m.group(2) or "")


def _parse_block(lines, pos, indent):
    """解析缩进为 `indent` 的一段块，返回 (值, 下一个未消费的行号)。"""
    if pos >= len(lines):
        return None, pos
    first = lines[pos]
    if first.text == "-" or first.text.startswith("- "):
        return _parse_seq(lines, pos, indent)
    # 该块里出现"比当前更深且不是流式写法"的行时，**缩进更深的那些行跟着最近的那个
    # 键走**——`paths:` 后直接跟序列（`  push:` / `    paths: &x` / `      - 'a'`）
    # 就是这种形态（键的缩进取了映射自身的缩进，序列项再深一级）。
    # 这里不按"再深一层"要求序列，故把序列并入本映射、逐键取值。
    return _parse_map(lines, pos, indent)


def _parse_seq(lines, pos, indent):
    items = []
    while pos < len(lines):
        line = lines[pos]
        if line.indent < indent or not line.text.startswith("-"):
            break
        if line.indent > indent:
            # 序列项自身的缩进即序列缩进；更深只可能是嵌套结构，由各自的解析分支处理
            raise YamlSubsetError("第 %d 行缩进比序列项更深且不是序列项" % line.no)
        body = line.text[1:].strip()
        pos += 1
        if body == "":
            # `-` 单独成行：值在其后的更深一层块里
            if pos < len(lines) and lines[pos].indent > indent:
                value, pos = _parse_block(lines, pos, lines[pos].indent)
            else:
                value = None
            items.append(value)
            continue
        kv = _split_key(body)
        if kv is None:
            if body.startswith("{"):
                raise YamlSubsetError("第 %d 行用了流式映射（`{...}`）——本子集不支持"
                                      % line.no)
            inline = _split_inline_list(body)
            items.append(inline if inline is not None else _split_scalar(body))
            continue
        # `- key: value`：本项是一张映射表，且后续同缩进的 `key:` 也要并进来
        key, rest = kv
        entry_indent = line.indent + 2
        mapping = {}
        if rest.strip() == "":
            if pos < len(lines) and lines[pos].indent > line.indent:
                nxt = lines[pos]
                if nxt.text == "-" or nxt.text.startswith("- "):
                    # `- run: |` 之后不会到这；这里是 `- key:` 后**直接跟序列项**的形态
                    value, pos = _parse_seq(lines, pos, nxt.indent)
                else:
                    value, pos = _parse_block(lines, pos, nxt.indent)
            else:
                value = None
        else:
            inline = _split_inline_list(rest)
            value = inline if inline is not None else _split_scalar(rest)
        mapping[key] = value
        while pos < len(lines) and lines[pos].indent == entry_indent and not lines[pos].text.startswith("-"):
            sub = lines[pos]
            kv2 = _split_key(sub.text)
            if kv2 is None:
                break
            k2, r2 = kv2
            pos += 1
            if r2.strip() == "":
                if pos < len(lines) and lines[pos].indent > sub.indent:
                    nxt2 = lines[pos]
                    if nxt2.text == "-" or nxt2.text.startswith("- "):
                        v2, pos = _parse_seq(lines, pos, nxt2.indent)
                    else:
                        v2, pos = _parse_block(lines, pos, nxt2.indent)
                else:
                    v2 = None
            elif r2.strip() in ("|", ">", "|-", ">-", "|+", ">+"):
                # `- name: x` / `- run: |` 形态里的块标量：正文是其后更深的行
                literal = r2.strip().startswith("|")
                buf = []
                while pos < len(lines) and lines[pos].indent > sub.indent:
                    buf.append(lines[pos].text)
                    pos += 1
                v2 = ("\n".join(buf) + "\n") if literal else " ".join(buf)
            elif r2.strip().startswith("- "):
                raise YamlSubsetError("第 %d 行的 `key: - x` 同行序列不在本子集内"
                                      % sub.no)
            else:
                inline2 = _split_inline_list(r2)
                v2 = inline2 if inline2 is not None else _split_scalar(r2)
            mapping[k2] = v2
        items.append(mapping)
    return items, pos


def _parse_map(lines, pos, indent):
    mapping = {}
    pending_seq_key = None  # 刚收下一个"值为空的键"，其下同缩进的序列项仍归它
    while pos < len(lines):
        line = lines[pos]
        if line.indent < indent:
            break
        if line.text.startswith("-") and line.indent == indent:
            # YAML 允许**序列项与其父键同缩进**（`steps:` 下一行直接写顶格的 `- run: x`），
            # 这是手写配置里最常见的写法之一。序列项归"最近的、值仍为空的键"，
            # 不当成同级键、也不报错——报错会把整份配置判成"读不出来"，
            # 而本工具的靶心是逐执行单位核时限（判成读不出来即拦掉真正该核的步骤）。
            if pending_seq_key is None:
                break  # 前面没有待接序列的键：交给调用方按"本层就是序列"处置
            value, pos = _parse_seq(lines, pos, line.indent)
            mapping[pending_seq_key] = value
            pending_seq_key = None
            continue
        if line.indent > indent:
            raise YamlSubsetError("第 %d 行缩进比同级键更深且不是键——"
                                  "多行标量/续行不在本子集内" % line.no)
        kv = _split_key(line.text)
        if kv is None:
            raise YamlSubsetError("第 %d 行不是合法的 `key: value`：%r" % (line.no, line.text))
        key, rest = kv
        pos += 1
        if rest.strip() == "":
            if pos < len(lines) and lines[pos].indent > indent:
                # `paths:` 后**直接跟序列**（`    paths: &x` / `      - 'a'`）是合法写法：
                # 序列项以 `-` 起头、比本键缩进更深即可，**不要求再深一层**。故先看下一行
                # 是不是序列项——是就在"序列项自身的缩进"上起序列（不按更深一层解析）。
                nxt = lines[pos]
                if nxt.text == "-" or nxt.text.startswith("- "):
                    # 序列项自身的缩进即序列的缩进（不再要求"比键多缩两格"）
                    value, pos = _parse_seq(lines, pos, nxt.indent)
                    mapping[key] = value
                    continue
                value, pos = _parse_block(lines, pos, nxt.indent)
            else:
                value = None
                pending_seq_key = key  # 值留空：其下同缩进的序列项若出现，归本键
        elif rest.strip().startswith("- "):
            # `paths: - x` 这类"键后同行起序列"的写法不在本子集内
            raise YamlSubsetError("第 %d 行的 `key: - x` 同行序列不在本子集内——"
                                  "请把序列项换行书写" % line.no)
        else:
            if rest.strip() in ("|", ">", "|-", ">-", "|+", ">+"):
                # 块标量（`|`/`>`）：**读得懂，只是值不进判据**——把其下更深的行当一段文本
                # 收起来（流水线配置里最常见的块标量就是 `run: |` 的多行命令）。
                # 判成"读不出来"会拦掉整份配置里**真正该核的步骤**，与本工具的靶心相悖。
                literal = rest.strip().startswith("|")
                buf = []
                # 块标量的正文是**其下更深的行**——缩进基准取"本键自身"（键缩进），
                # 故只收严格更深的行；收到第一个不更深的行即结束
                while pos < len(lines) and lines[pos].indent > indent:
                    buf.append(lines[pos].text)
                    pos += 1
                value = ("\n".join(buf) + "\n") if literal else " ".join(buf)
                mapping[key] = value
                continue
            if rest.strip().startswith("{"):
                raise YamlSubsetError("第 %d 行用了流式映射（`{...}`）——本子集不支持"
                                      % line.no)
            inline = _split_inline_list(rest)
            value = inline if inline is not None else _split_scalar(rest)
            # 标量/行内序列之后**紧跟更深或同缩进的序列项**时（`paths: &spec-paths` 后再写
            # `  - 'x'`，或 `steps:` 后直接写顶格的 `- run: x`），把那些序列项一并收在
            # 本键下——此时 YAML 里"键的值"就是那段序列。
            if (value is None or isinstance(value, str)) and pos < len(lines) \
                    and lines[pos].indent >= indent \
                    and (lines[pos].text == "-" or lines[pos].text.startswith("- ")):
                value, pos = _parse_seq(lines, pos, lines[pos].indent)
                pending_seq_key = None
        mapping[key] = value
    return mapping, pos


def load(text: str):
    """解析本子集内的 YAML 文本；支持多文档时只取第一份（其余报错）。"""
    lines = []
    for no, raw in enumerate(text.splitlines(), 1):
        if raw.strip().startswith("---") and raw.strip() != "---":
            raise YamlSubsetError("第 %d 行不是合法文档分隔符" % no)
        if raw.strip() == "---" and lines:
            raise YamlSubsetError("不支持多文档 YAML（第 %d 行）" % no)
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise YamlSubsetError("第 %d 行用制表符缩进——YAML 不允许" % no)
        text_line = _strip_comment(raw)
        if text_line.strip() == "":
            continue
        indent = len(text_line) - len(text_line.lstrip(" "))
        lines.append(_Line(indent, text_line.strip(), no))
    if not lines:
        return None
    base = lines[0].indent
    value, pos = _parse_block(lines, 0, base)
    if pos != len(lines):
        raise YamlSubsetError("第 %d 行未能归入任何块（缩进或写法超出本子集）" % lines[pos].no)
    return value


def load_all_as(path: str, encoding: str = "utf-8"):
    """读文件并解析；文件不存在返回 `None`（"没有该文件"与"解析失败"由调用方区分）。"""
    import os

    if not os.path.isfile(path):
        return None
    with open(path, encoding=encoding) as fh:
        return load(fh.read())


def get_path(node, path: str):
    """按点分路径取值（序列下标写成数字）；取不到一律返回 `None`。"""
    cur = node
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, list):
            if not part.isdigit() or int(part) >= len(cur):
                return None
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            if part not in cur:
                return None
            cur = cur[part]
        else:
            return None
    return cur


def iter_mapping_entries(node, path: str):
    """把点分路径处的映射表逐项产出 (键, 值)；该处不是映射表则产出空表。"""
    target = get_path(node, path)
    if not isinstance(target, dict):
        return []
    return list(target.items())
