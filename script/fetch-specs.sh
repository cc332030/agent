#!/usr/bin/env bash
# fetch-specs - Linux/macOS 入口（薄壳：定位逻辑代码、原样转交参数、原样返回退出码）
#
# 解释器按次序探测：本入口不得假设调用方机器上已装 Python——
# 先 PATH 里的 python3（本仓库脚本的规范取值，见 specs/stack/python.adoc），
# 再回退到 python，逐个 command -v 判到为止。两者都没有时报一句错、退出非 0，
# 不静默继续（"变量未定义一律当错误"，见 specs/stack/batch.adoc）。
set -u

script_dir="$(cd -- "$(dirname -- "$0")" && pwd)"

if command -v python3 >/dev/null 2>&1; then
  runtime="python3"
elif command -v python >/dev/null 2>&1; then
  runtime="python"
else
  echo "错误: 未找到解释器 python3/python，无法运行 fetch-specs.py" >&2
  exit 127
fi

# 解释器是原生可执行文件（非脚本），exec 按 POSIX 语义把 PID 交给它；
# 位置参数为空时兼容 shell 继续往下走，故不在末尾依赖 exec 的返回。
exec "$runtime" "$script_dir/fetch-specs.py" "$@"
