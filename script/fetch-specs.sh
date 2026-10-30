#!/usr/bin/env bash
# fetch-specs - Linux/macOS 入口（薄壳：定位逻辑代码、原样转交参数、原样返回退出码）
#
# 解释器按次序探测：本入口不得假设调用方机器上已装 Python——
# 先 PATH 里的 python3（本仓库脚本的规范取值，见 specs/stack/python.adoc），
# 再回退到 python，**认第一个真的跑得起来的**；两者都没有时报一句错、退出非 0，
# 不静默继续（"变量未定义一律当错误"，见 specs/stack/batch.adoc）。
set -u

script_dir="$(cd -- "$(dirname -- "$0")" && pwd)"

# 探测分两步，次序就是**行序**：先把"在 PATH 上"逐行问一遍（每一行只认一个候选名，故位置
# 即次序），再拿问到的那个候选**试跑一次**（`--probe`：走到 `main` 早处即收工——不联网取清单、
# 不打印清单、不写盘、不取文件，也不换自身）。
runtime=""
command -v python3 >/dev/null 2>&1 && runtime="python3"
if [ -z "$runtime" ]; then
  command -v python >/dev/null 2>&1 && runtime="python"
fi

if [ -z "$runtime" ]; then
  echo "错误: 未找到可用的解释器 python3/python，无法运行 fetch-specs.py" >&2
  exit 127
fi

# 判据只有一条：**试跑退出码为 0**——探到不等于跑得起来，同名但不是 Python 的东西、
# 只装了壳没装解释器的发行版都会让 `command -v` 命中、真跑起来才失败，那时报错的是
# **解释器**（读者看到"找不到某个命令"，没有一句说"这台机器没有可用的 python"）。
# 试不过时**不换候选**（这里只有这一个候选）：如实说明，再把用法/取回的问题留给它原样报
# ——不替它把"解释器跑不起来"与"是取文件的问题"混成同一句话。
"$runtime" "$script_dir/fetch-specs.py" --probe >/dev/null 2>&1 \
  || printf '说明: 解释器 %s 试跑 fetch-specs.py 未通过——原样交给它，用法/取回的问题由它报\n' \
    "$runtime" >&2

# 跑**同一个**解释器进程：这里刻意不用 `exec`——exec 会把本壳换掉，后面那两件事
# （取退出码、按需停住）就再没有机会执行（本仓库实测：`exec` 之后 `status=$?` 那段
# 一行都不跑，窗口照旧秒关）。
"$runtime" "$script_dir/fetch-specs.py" "$@"
status=$?

# 跑完**停住**（用户口径：「下载完成不要关闭窗口」）：双击启动时终端窗口是入口自己开的，
# 逻辑代码一退出窗口就跟着关，进度与失败清单连看都来不及看。判据只认「自己开着一个终端」
# ——标准输入挂在终端上；管道、重定向、CI 里没有终端，照旧立刻退出（不给自动化挂上
# 一个"永久不返回"的命令，见 specs/general/verify.adoc「没有进度输出的操作尤其适用」）。
if [ -t 0 ]; then
  printf '\n按回车键关闭窗口…'
  read -r _ || true
fi

exit "$status"
