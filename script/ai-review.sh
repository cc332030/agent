#!/usr/bin/env bash
#
# 用 OpenAI 兼容 API 对规范集合做语义审查，支持"整体解析"与"单个解析"两种粒度。
#
# 用法：
#   AI_API_KEY=<key> AI_MODEL=<model> [AI_API_BASE=...] bash script/ai-review.sh \
#       <AGENTS_COMMON.adoc> <specs 目录>
#   # 逐个解析：对每一个 adoc 文档分别单独审查，最后再整体审查（推荐）
#   AI_API_KEY=<key> AI_MODEL=<model> bash script/ai-review.sh --per-file <AGENTS_COMMON.adoc> <specs 目录>
#
# 参数：
#   --per-file   启用"单个解析"：依次对每个 .adoc 文档单独调用 AI 审查，
#                每个文件一份独立结果；随后再做一次整体拼接审查。整体结果写入
#                $AI_OUTPUT（默认 /tmp/ai-findings.txt），每个文件的单份结果写入
#                $AI_PER_FILE_DIR/<序号>-<文件名>.md（默认 /tmp/ai-per-file）。
#   <AGENTS_COMMON.adoc>  规范入口文件（必填）
#   <specs 目录>   规范分类目录（必填）
#
# 环境变量：
#   AI_API_KEY      必填，API 密钥（推荐通过 GitHub Secrets 注入）
#   AI_API_BASE     可选，OpenAI 兼容 API 基地址，默认 https://api.openai.com/v1
#   AI_MODEL        必填，模型名，通过环境变量自由接入任意 OpenAI 兼容模型
#                   （如 gpt-4o-mini、deepseek-chat、qwen-max 或本地 vLLM 模型等）
#   AI_OUTPUT       可选，整体审查结果输出路径，默认 /tmp/ai-findings.txt
#   AI_PER_FILE_DIR 可选，单个解析结果输出目录，默认 /tmp/ai-per-file
#
# 行为：
#   * 整体解析（始终执行）：拼接所有规范文本作为 user 消息，调用 chat/completions，
#     把模型输出写入整体结果文件。约定模型输出：发现问题时最后一行 ISSUES_FOUND，
#     未发现为 NO_ISSUES_FOUND。
#   * 单个解析（--per-file 时启用）：对每个 .adoc 文件单独构造 user 消息并调用一次
#     API，每个文件独立判定 ISSUES_FOUND / NO_ISSUES_FOUND，逐文件汇总。
#   * 退出码：任一 AI 调用失败返回 1；调用全部成功返回 0
#     （问题与否由输出标记判定，不由本脚本判定）。

set -euo pipefail

# ---- 参数解析 ---------------------------------------------------------------
PER_FILE=false
POSITIONAL=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --per-file)
      PER_FILE=true
      shift
      ;;
    --help|-h)
      cat <<'USAGE'
用法: bash script/ai-review.sh [--per-file] <AGENTS_COMMON.adoc> <specs 目录>

参数:
  --per-file   启用"单个解析"：对每个 .adoc 文档单独调用 AI 审查（推荐）
  -h, --help   显示本帮助
  <AGENTS_COMMON.adoc>  规范入口文件（必填）
  <specs 目录>   规范分类目录（必填）

环境变量:
  AI_API_KEY      必填，API 密钥
  AI_API_BASE     可选，API 基地址，默认 https://api.openai.com/v1
  AI_MODEL        必填，模型名，通过环境变量自由接入任意 OpenAI 兼容模型
                  （如 gpt-4o-mini、deepseek-chat、qwen-max 或本地 vLLM 模型等）
  AI_OUTPUT       可选，整体审查结果输出路径，默认 /tmp/ai-findings.txt
  AI_PER_FILE_DIR 可选，单个解析结果输出目录，默认 /tmp/ai-per-file
USAGE
      exit 0
      ;;
    -*)
      echo "未知参数: $1" >&2
      echo "用法: bash script/ai-review.sh [--per-file] <AGENTS_COMMON.adoc> <specs 目录>" >&2
      exit 2
      ;;
    *)
      POSITIONAL+=("$1")
      shift
      ;;
  esac
done

AGENTS="${POSITIONAL[0]:-}"
SPECS_DIR="${POSITIONAL[1]:-}"
if [[ -z "$AGENTS" || -z "$SPECS_DIR" ]]; then
  echo "缺少 AGENTS_COMMON.adoc 或 specs 目录参数" >&2
  echo "用法: bash script/ai-review.sh [--per-file] <AGENTS_COMMON.adoc> <specs 目录>" >&2
  exit 2
fi

OUTPUT="${AI_OUTPUT:-/tmp/ai-findings.txt}"
PER_FILE_DIR="${AI_PER_FILE_DIR:-/tmp/ai-per-file}"

AI_API_BASE="${AI_API_BASE:-https://api.openai.com/v1}"

# 模型名不写死默认值：必须通过 AI_MODEL 环境变量指定，以便自由接入任意
# OpenAI 兼容模型（OpenAI、DeepSeek、通义、本地 vLLM 等）。
if [[ -z "${AI_MODEL:-}" ]]; then
  echo "缺少环境变量 AI_MODEL：请指定要接入的模型名，例如" >&2
  echo '  AI_MODEL=gpt-4o-mini bash script/ai-review.sh AGENTS_COMMON.adoc specs' >&2
  echo '（AI_MODEL 支持任意 OpenAI 兼容模型，具体以你的 AI_API_BASE 服务为准）' >&2
  exit 2
fi

# 收集全部 spec 文件（入口 + specs/**/*.adoc，排序固定保证可复现）
# 入口位于仓库根目录（如 AGENTS_COMMON.adoc），与 specs/ 下 find 结果不重叠；
# 仍用 awk 按首次出现去重（保持入口在前、其余按序），兼容入口落入 specs/ 的情况。
collect_files() {
  {
    echo "${AGENTS}"
    find "${SPECS_DIR}" -name '*.adoc' -type f | sort
  } | sed '/^$/d' | awk '!seen[$0]++'
}

# 调用一次 chat/completions，把模型输出写入指定文件。
# 约定模型输出：发现问题时最后一行 ISSUES_FOUND，未发现为 NO_ISSUES_FOUND。
# 参数：<user-content> <输出文件>
call_ai() {
  local content_file="$1" out_file="$2"
  local SYSTEM_PROMPT CONTENT_JSON SYSTEM_JSON BODY RESP
  SYSTEM_PROMPT=$(cat <<'SYS'
你是一名严谨的技术规范审查专家。只审查 agent 执行规范集合的一致性。
输出要求：若发现问题，逐条列出"文件、问题描述、具体建议的修改"，并在最后一行
输出标记 ISSUES_FOUND；若未发现问题，只输出一行 NO_ISSUES_FOUND。
重点检查：1) 规范之间是否自相矛盾或重复；2) 是否存在歧义、不严谨、会误导
agent 的表述；3) 是否含私有项目专属约定（应中性化）。
SYS
  )
  CONTENT_JSON=$(jq -Rs . "${content_file}")
  SYSTEM_JSON=$(jq -n --arg s "${SYSTEM_PROMPT}" '$s')
  # system / content 已是 JSON 字符串（含引号），需用 --argjson 传入避免二次转义
  BODY=$(jq -n \
    --arg model "${AI_MODEL}" \
    --argjson system "${SYSTEM_JSON}" \
    --argjson content "${CONTENT_JSON}" \
    '{model:$model, messages:[{role:"system",content:$system},{role:"user",content:$content}]}')

  RESP=$(curl -sS -f \
    -H "Authorization: Bearer ${AI_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "${BODY}" \
    "${AI_API_BASE}/chat/completions")

  echo "${RESP}" | jq -r '.choices[0].message.content' > "${out_file}"
}

# ---- 单个解析（--per-file）：逐个文件单独审查 ---------------------------------
if [[ "$PER_FILE" == true ]]; then
  echo "===== 单个解析（逐文件审查） ====="
  mkdir -p "${PER_FILE_DIR}"
  per_found=0
  # 行号前缀保证目录内顺序与整体审查的拼接顺序一致
  lineno=0
  while IFS= read -r f; do
    lineno=$((lineno + 1))
    rel="${f#./}"
    n=$(basename "${f}" .adoc)
    idx=$(printf "%02d" "${lineno}")
    single_out="${PER_FILE_DIR}/${idx}-${n}.md"
    {
      echo "===== FILE: ${f} ====="
      cat "${f}"
    } > "${single_out}.ctx"
    echo "  [逐个] 审查 ${rel} -> ${single_out}"
    if ! call_ai "${single_out}.ctx" "${single_out}"; then
      echo "  [逐个] ${rel} 调用失败" >&2
      per_found=$((per_found + 1))
      continue
    fi
    # 统计本文件是否发现问题
    if grep -q "ISSUES_FOUND" "${single_out}"; then
      echo "  [逐个] ${rel}: ISSUES_FOUND"
      per_found=$((per_found + 1))
    else
      echo "  [逐个] ${rel}: NO_ISSUES_FOUND"
    fi
    rm -f "${single_out}.ctx"
  done < <(collect_files)
  echo "单个解析完成：${PER_FILE_DIR}（发现问题文件数 ${per_found}）"
  echo ""
fi

# ---- 整体解析（始终执行）：拼接全部规范后一次性审查 ---------------------------
echo "===== 整体解析（拼接全量审查） ====="
CONTEXT="${OUTPUT}.ctx"
{
  while IFS= read -r f; do
    echo ""
    echo "===== FILE: ${f} ====="
    cat "${f}"
  done < <(collect_files)
} > "${CONTEXT}"

echo "已拼接规范上下文: ${CONTEXT} ($(wc -l < "${CONTEXT}") 行)"

if ! call_ai "${CONTEXT}" "${OUTPUT}"; then
  echo "整体解析调用失败" >&2
  exit 1
fi
rm -f "${CONTEXT}"

echo "===== AI 审查结果（整体，${OUTPUT}） ====="
cat "${OUTPUT}"

# 任一文件发现问题时，给出汇总提示（不改变退出码）
if [[ "$PER_FILE" == true ]] && grep -q "ISSUES_FOUND" "${OUTPUT}"; then
  echo ""
  echo "提示：整体解析发现问题，逐文件结果见 ${PER_FILE_DIR}。"
fi
