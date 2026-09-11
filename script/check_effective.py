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
规范（`link:specs/general/git.adoc[]`）自行检查，本仓库只能把规范文本写清楚）。
"""

import argparse
import sys
from os import path

HERE = path.dirname(path.abspath(__file__))

# 输出列宽（中文按 2 字符宽对齐，避免手写空格导致清单错位）
NAME_WIDTH = 46

# 强制条款 → 可执行抓手映射。
# (条款名, 来源规范文件, 抓手相对路径[None=暂无机械抓手], 备注)
MECHANISMS = [
    ("规范调整后须真正验证（要点防线）",       "AGENTS.adoc",                 "script/check_specs.py",      "check_specs 的 check_principle_guard 校验该条仍存在"),
    ("内部链接须用相对路径、禁根绝对",           "specs/general/doc.adoc",           "script/check_specs.py",      "check_link_refs"),
    ("规范引用文件必须真实存在",                 "AGENTS.adoc",                 "script/check_specs.py",      "check_refs_exist"),
    ("技术栈登记与文件一致",                     "AGENTS_COMMON.adoc",        "script/check_specs.py",      "check_stack_consistency"),
    ("私有工程约定不入全局规范",                 "specs/general/*.adoc",            "script/check_specs.py",      "check_forbidden_patterns"),
    ("不保留无用的历史来源声明",                 "AGENTS.adoc",                 "script/check_specs.py",      "check_historical_notes"),
    ("禁止无意义/划水/凑字数的文档",            "specs/general/doc.adoc",           "script/check_specs.py",      "check_filler_docs（占位段/完全重复段）"),
    ("文档须高质量（准确/完整/可执行/有价值/简洁/可验证）", "specs/general/doc.adoc",   "script/check_specs.py",      "可验证性由 check_refs_exist/check_link_refs/check_section_refs 兜底，其余交人 review"),
    ("INSTALL 模板代码块逐字保留（换行/空行不丢失）", "INSTALL.adoc",            "script/check_specs.py",      "check_install_codeblock"),
    ("临时产物清理脚本可用",                     "specs/core/execution.adoc",       "script/clean_tmp.py",        "存在清理脚本"),
    ("完整性校验配套测试",                       "AGENTS.adoc",                 "script/check_specs_test.py", "20+ 用例"),
    ("定义未执行核验配套测试",                   "AGENTS.adoc",                 "script/check_effective_test.py", "本工具的自测"),
    ("变更日志只记影响、不记过程（重点优先、拒细枝末节）", "specs/general/changelog.adoc", "script/check_specs.py", "check_section_refs 钉住「应当记录/不应当记录/条目书写」三节引用不悬空；条目内容的详略判断交人 review"),
    ("文件移动/重命名必须 git mv（防历史断裂）", "specs/core/execution.adoc",       None,                         "无机械抓手：铁律作用于**引用方项目**的工作区，本仓库（校验入口）看不到其操作；靠遵守 + 各项目自行检查"),
    ("测试文件后缀式命名（禁 test_ 前戳）",       "specs/general/testing.adoc",      None,                         "无机械抓手：靠遵守"),
    ("校验范围只限公共内容与本仓库工具（不检查引用方项目工作区）", "AGENTS.adoc", "script/check_specs_test.py", "TestScopeStaysOnCommonContent 钉住 check_specs.py 不得读 git 工作区状态/HEAD"),
    ("最高关注项（L1/不可降级）不得被删或降级", "specs/core/priority.adoc", "script/check_specs.py", "check_priority_guard 钉住 P1/P2/P3 与 L1/L2/L3 分级仍在"),
    ("去重不得误删最高关注项的引用", "AGENTS.adoc", "script/check_specs.py", "check_priority_guard：最高关注项的存在性机械钉住（引用是否被删由该防线兜底发现）"),
    ("提示词主侧重（方向前提）与优先级不得被删/降级", "PROMPTS.adoc", "script/check_specs.py", "check_prompts_primary 钉住 PROMPTS.adoc 主侧重登记、各提示词 primary 声明与 priority-rules 的 L1/L2/L3"),
]


def display_width(text: str) -> int:
    """按终端显示宽度计算字符串宽度（CJK 字符按 2 列计）。"""
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in text)


def _pad(text: str, width: int = NAME_WIDTH) -> str:
    """条款名右侧补空格到统一列宽，保证多行清单左对齐。"""
    return text + " " * max(0, width - display_width(text))


def evaluate(root: str = HERE) -> list:
    """逐条判定抓手状态。root 可注入以便测试（不依赖真实仓库）。"""
    rows = []
    for name, source, grip, note in MECHANISMS:
        if grip is None:
            status = "no-grip"
        elif path.isfile(path.join(root, grip)):
            status = "has-grip"
        else:
            status = "grip-missing"
        rows.append({
            "name": name, "source": source, "grip": grip,
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
