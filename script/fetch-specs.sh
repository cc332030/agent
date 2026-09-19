#!/usr/bin/env bash
# fetch-specs - Linux/macOS 入口（薄壳：定位逻辑代码、原样转交参数、原样返回退出码）
set -u
exec python3 "$(dirname "$0")/fetch-specs.py" "$@"
