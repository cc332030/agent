#!/usr/bin/env python3
"""gen_derived - 本仓库**派生件**（生成物）的生成器：一处真源，整段现算。

为什么要有这个脚本
------------------
本仓库每次改动都在往一串「行集合」里加一项：一张表的行、一份清单的条目、一份台账的一条。
同一批内容被**逐行抄成第二份**时，每一轮改动都要往中间插一行、其后各行整体位移——两个
并行改动必然撞在同一片区域，那是本仓库剩下最硬的独占落点。判据本体见
`specs/general/coding.adoc`「分发产物的体积与按需加载」的「派生件与本体同处一个构建步骤、
同属一个构建产物」条：**派生件不由人工手作**，与本体同一次产出。

当前产出（登记表在 `script/specs-rules/ledger.toml` 的 `[tokens.not_collision_catalog]`，
本文件不另列一份清单——清单只有一处）：

* `specs-project-maintainer/guards.adoc`「检查项编号」**整节**：按 `script/check_specs.py`
  头部的检查项清单现算。头部那份清单是唯一真源，本表是它的**派生件**——原先是一份手抄的
  编号索引表，每轮新增检查项都往中间插一行。
* `specs-project-maintainer/guards.adoc`「生成物一览」：按登记表本身现算（加一个生成物
  只往登记表加一条，那一行自己长出来）。

用法与副作用
------------
    python3 script/gen_derived.py          # 只核：现场与重算结果不一致时打印、退出码 1
    python3 script/gen_derived.py --write  # 就地把生成段改写成重算结果

`--write` 只改登记表里那几段（有起止标记的按标记定位、没有的按整节重出，节头那段人写
的说明逐字保留）。不联网、无第三方依赖（`tomllib` 属标准库）。

关键约定与设计决策
------------------
* **整段现算、局部改写**：改写按段定位，段外内容逐字保留——生成器顺手"格式化"整份文件时，
  diff 会把不相关的变化一起带出来（评审读不出改了什么）。
* **不一致即报红，不自动覆盖**：`check_specs.py` 调 `stale_files()` 核"现场＝重算结果"；
  生成器不会在执行校验时偷偷写盘——"核过且通过"与"核的时候顺手改了"必须分得清。
* **生成物不得成为第二份真源**：这里只**读**真源。反过来被读去驱动别处，就是第三份来源。
"""

import argparse
import os
import re
import sys
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.dirname(HERE)
RULES_REL = "script/specs-rules/ledger.toml"
TABLE_HEADER = [
    '[cols="1,2", options="header"]',
    "|===",
    "| 编号 | 检查项或所属防线",
]
DOC_DELIM = '"' * 3


def _die(msg: str) -> "NoReturn":  # noqa: F821
    """生成器的失败路径只有一条：打印原因、非 0 退出（不吞、不猜）。"""
    print(f"gen_derived: {msg}", file=sys.stderr)
    raise SystemExit(1)


def _read(root: str, rel: str) -> str:
    path = os.path.join(root, *rel.split("/"))
    if not os.path.isfile(path):
        _die(f"缺文件 {rel}")
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def _write(root: str, rel: str, text: str) -> None:
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def sections(root: str = DEFAULT_ROOT) -> list:
    """读登记表：返回要产出的段（只取登记过的那几段，不猜、不遍历目录）。"""
    path = os.path.join(root, *RULES_REL.split("/"))
    if not os.path.isfile(path):
        _die(f"缺生成器登记表 {RULES_REL}")
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    rows = data.get("tokens", {}).get("not_collision_catalog", {}).get("sections", [])
    if not isinstance(rows, list):
        _die(f"{RULES_REL} 的 tokens.not_collision_catalog.sections 形态不对")
    return [r for r in rows if isinstance(r, list) and len(r) >= 6]


def _numbered_items(src: str) -> list:
    """取 `script/check_specs.py` 头部的检查项清单：连续编号那一片（唯一真源）。

    清单嵌在模块 docstring 里；按**成对**的分隔符取第一段（切成两半会落在文件里别处
    那些孤立的三条引号上，实测一条都取不到）。清单在「清单一到此为止」那一句收尾：
    其后的 ` NN. ` 是逐项说明里的展开，不是索引条目。
    """
    parts = src.split(DOC_DELIM)
    head = parts[1] if len(parts) > 1 else src
    stop = head.find("**清单一到此为止**")
    if stop > 0:
        head = head[:stop]
    return [(int(m.group(1)), m.group(2).strip())
            for m in re.finditer(r"(?m)^ (\d+)\. (\S.*)$", head)]


def render_catalog_rows(root: str = DEFAULT_ROOT, rows=None) -> str:
    """产出「检查项编号」表的表体（`| <编号> | <检查项或所属防线>` 逐行）。

    真源取**登记项自己写的那一格**（`row[2]`），不在这里再写一遍 `script/check_specs.py`：
    同一份"表体从哪来"的取值写在两处，改一处必漏另一处。
    """
    rows = sections(root) if rows is None else rows
    src = rows[0][2] if rows else ""
    if not src:
        _die(f"{RULES_REL} 的登记表里没有取「检查项编号」真源的那一条")
    seq = _numbered_items(_read(root, src))
    if not seq:
        _die("script/check_specs.py 头部取不到检查项清单（表体的唯一真源）")
    return "".join(f"| {n} | {name}\n" for n, name in seq)


def render_index(rows) -> str:
    """产出「生成物一览」：登记表里每一段一条（段名与产出形态、真源、重算命令）。

    这一段自己也由登记表现算：加一个生成物只往登记表加一条，这一行自己长出来——
    原先新增一个生成物要往这几行里再插一句，那是同一个成因的另一处。
    """
    return "".join(
        f"* `{r[0]}`「{r[1]}」：{r[3]}（真源 `{r[2]}`；重算 `python3 script/gen_derived.py --write`）\n"
        for r in rows)


def _replace(text: str, row, rows) -> str:
    """按登记项定位并替换这一段：有起止标记的按标记、没有的按整节（节头人写的说明保留）。"""
    src, section, renders, begin, end = row[0], row[1], row[3], row[4], row[5]
    body = render_index(rows) if renders == "生成物逐条一览" else render_catalog_rows(rows=rows)
    if begin:
        m = re.search(re.escape(begin) + r"(.*?)" + re.escape(end), text, re.S)
        if m is None:
            _die(f"{src} 里找不到生成段的起止标记（{begin} / {end}）")
        return text[:m.start(1)] + "\n" + body + text[m.end(1):]
    m = re.search(r"(?ms)^== " + re.escape(section) + r".*?(?=^== |\Z)", text)
    if m is None:
        return text
    piece = m.group(0)
    head = piece.split(TABLE_HEADER[0], 1)[0].rstrip("\n")
    return text[:m.start()] + head + "\n\n" + "\n".join(TABLE_HEADER) + "\n\n" + body \
        + "|===\n\n" + text[m.end():]


def rendered(root: str = DEFAULT_ROOT) -> dict:
    """算出全部登记段"应该长什么样"：`{相对路径: 全文}`。"""
    rows = sections(root)
    out = {}
    for row in rows:
        rel = row[0]
        text = out.get(rel) or _read(root, rel)
        out[rel] = _replace(text, row, rows)
    return out


def stale_files(root: str = DEFAULT_ROOT) -> list:
    """现场与重算结果不一致的段（＝"手改过"或"改了真源忘了重算"）。"""
    return sorted(rel for rel, want in rendered(root).items()
                  if want != _read(root, rel))


def write(root: str = DEFAULT_ROOT) -> list:
    """就地把不一致的段改写成重算结果；返回真正被改写的文件。"""
    changed = []
    for rel, want in rendered(root).items():
        if want != _read(root, rel):
            _write(root, rel, want)
            changed.append(rel)
    return sorted(changed)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="产出本仓库的派生件（生成物）")
    parser.add_argument("--write", action="store_true", help="就地把生成段改写成重算结果")
    parser.add_argument("--root", default=DEFAULT_ROOT, help="仓库根（默认本脚本的上一级）")
    args = parser.parse_args(argv)
    if args.write:
        changed = write(args.root)
        print("已重算：" + ("、".join(changed) if changed else "无变化"))
        return 0
    stale = stale_files(args.root)
    if stale:
        print("与重算结果不一致：" + "、".join(stale), file=sys.stderr)
        print("改真源后重跑 `python3 script/gen_derived.py --write`", file=sys.stderr)
        return 1
    print("生成物与真源一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
