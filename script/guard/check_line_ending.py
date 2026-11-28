#!/usr/bin/env python3
"""『提交错误的换行符』的机械门禁：逐文件实扫索引侧与工作区侧的行尾（纯 stdlib）。

要治的失效
----------
公共规范定义了换行符标准（LF 基准、`.bat`/`.cmd`/`.ps1` 用 CRLF）并配好了
`.gitattributes`/`.editorconfig`，但"文件真的按这个标准落盘了没有"此前无人核对——
标准写在文档里、错了靠人肉发现，正是"有定义、没校验"。本件把标准接成两道防线：

* **提交前**：本地跑一次，错误换行不进提交；
* **CI**：合并前再跑一次，绕过本地者仍被拦。

两道都核 `git ls-files --eol` 的两列，缺一不可：

* `i/`（索引侧）＝**真正提交进仓库的字节**。git 对 text 文件（含 `eol=crlf`）都按 LF
  归一化存索引，故这里只许 `lf`/`none`；出现 `crlf`/`mixed` 即"把错误换行提交了"。
* `w/`（工作区侧）＝检出/编辑后的字节。须与 `attr/` 声明一致（`eol=crlf` → `crlf`、
  其余 → `lf`）；`mixed` 一定是混用违规。`none`（空文件）不算违规。

本件**只在维护规范集合的本仓库侧运行、不在默认引用面内**（规范入口不会加载
本件，引用方也不该依赖它）；它核的是本仓库这一半的事实，引用方工作区的门禁由引用方按规范自查。

用法
----
    python3 script/guard/check_line_ending.py                 # 查当前目录
    python3 script/guard/check_line_ending.py --repo .        # 查指定仓库

退出码：0 全绿；1 有违规；2 前置条件错误（不是 git 工作区 / git 不可用 / 命令失败）。
**一份文件都没核到**按 2 退出——"核不到"与"核过且通过"必须分得开。
"""

import argparse
import os
import re
import subprocess
import sys

BINARY_ATTR_RE = re.compile(r"\bbinary\b|-text")


def expected_eol(attr: str):
    """从 `git ls-files --eol` 的 `attr/` 列读出该文件应有的行尾。

    返回 `'crlf'` / `'lf'` / None；None 表示不参与核对（二进制或被显式关掉 text）。
    `text` 但没写 `eol=` 归到仓库基准 LF（与仓库根 `* text eol=lf` 一致）。
    """
    if BINARY_ATTR_RE.search(attr):
        return None
    if "eol=crlf" in attr:
        return "crlf"
    if "eol=lf" in attr or "text" in attr:
        return "lf"
    return None


def eol_violations(lines):
    """核 `git ls-files --eol` 的输出行，返回违规描述列表（纯函数，便于单测）。

    每行的形如 `i/lf    w/crlf  attr/text eol=lf\\tpath`，按 tab 切成元数据与路径。
    解析不出的行（如 git 的提示行）跳过，不因此放过违规文件。
    """
    out = []
    for raw in lines:
        line = raw.rstrip("\n")
        if "\t" not in line:
            continue
        meta, path = line.split("\t", 1)
        mi = re.search(r"\bi/(\w+)", meta)
        mw = re.search(r"\bw/(\w+)", meta)
        ma = re.search(r"\battr/(.*)$", meta)
        if not (mi and mw and ma):
            continue
        idx, wt, attr = mi.group(1), mw.group(1), ma.group(1).strip()
        want = expected_eol(attr)
        if want is None:
            continue
        if idx in ("crlf", "mixed"):
            out.append(f"{path}：索引行尾为 {idx}（提交进仓库的字节不是 LF；"
                       "CRLF 例外只在检出侧，索引一律归一化成 LF）")
        if wt == "mixed" or (wt != "none" and wt != want):
            out.append(f"{path}：工作区行尾为 {wt}，与 {attr} 声明的 {want} 不一致（含混用）")
    return out


def scan(repo: str):
    """在 `repo` 上跑实扫，返回 `(核到的文件数, 违规列表)`；前置错误抛 `RuntimeError`。"""
    git_path = os.path.join(repo, ".git")
    if not (os.path.isdir(git_path) or os.path.isfile(git_path)):
        raise RuntimeError(f"{repo} 不是 git 工作区（缺 .git）——无从读行尾状态")
    try:
        out = subprocess.run(
            ["git", "ls-files", "--eol"], cwd=repo,
            capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"git ls-files --eol 执行失败：{exc}") from exc
    if out.returncode != 0:
        raise RuntimeError(f"git ls-files --eol 返回 {out.returncode}：{out.stderr.strip()}")
    lines = [ln for ln in out.stdout.splitlines() if "\t" in ln]
    return len(lines), eol_violations(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="实扫 git 仓库行尾：索引禁 CRLF、工作区须与声明一致")
    ap.add_argument("--repo", default=".", help="要核对的仓库根（默认当前目录）")
    args = ap.parse_args(argv)
    try:
        count, violations = scan(args.repo)
    except RuntimeError as exc:
        print(f"换行符门禁前置条件失败：{exc}")
        return 2
    if count == 0:
        print("换行符门禁：一份文件都没核到（git ls-files --eol 无输出）——"
              "核不到不等于核过")
        return 2
    if violations:
        print(f"换行符门禁：核到 {count} 份文件，发现 {len(violations)} 处违规：")
        for v in violations:
            print(f"  - {v}")
        print("按 LF 基准 / `.bat`/`.cmd`/`.ps1` 用 CRLF 的分流修正后重跑；"
              "违规即阻断提交/合并。")
        return 1
    print(f"换行符门禁：核到 {count} 份文件，索引与工作区行尾均合规（零违规、零混用）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
