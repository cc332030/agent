#!/usr/bin/env bash
#
# 用 OpenAI 兼容 API 对规范集合做一致性语义审查。
#
# 用法：
#   AI_API_KEY=<key> [AI_API_BASE=...] [AI_MODEL=...] bash script/ai-review.sh \
#       <AGENTS.adoc> <specs 目录>
#
# 环境变量：
#   AI_API_KEY   必填，API 密钥（推荐通过 GitHub Secrets 注入）
#   AI_API_BASE  可选，OpenAI 兼容 API 基地址，默认 https://api.openai.com/v1
#   AI_MODEL     可选，模型名，默认 gpt-4o-mini
#
# 行为：
#   拼接所有规范文本作为 user 消息，调用 chat/completions，把模型输出写入
#   /tmp/ai-findings.txt（或 AI_OUTPUT 指定路径）。
#   约定模型输出：发现问题时最后一行 ISSUES_FOUND，未发现为 NO_ISSUES_FOUND。
#   退出码：AI 调用失败返回 1；调用成功返回 0（问题与否由输出标记判定，不由本脚本判定）。

set -euo pipefail

AGENTS="${1:?缺少 AGENTS.adoc 参数}"
SPECS_DIR="${2:?缺少 specs 目录参数}"
OUTPUT="${AI_OUTPUT:-/tmp/ai-findings.txt}"

AI_API_BASE="${AI_API_BASE:-https://api.openai.com/v1}"
AI_MODEL="${AI_MODEL:-gpt-4o-mini}"

# 1) 拼接规范内容
CONTEXT="${OUTPUT}.ctx"
{
  echo "===== FILE: ${AGENTS} ====="
  cat "${AGENTS}"
  while IFS= read -r f; do
    echo ""
    echo "===== FILE: ${f} ====="
    cat "${f}"
  done < <(find "${SPECS_DIR}" -name '*.adoc' -type f | sort)
} > "${CONTEXT}"

echo "已拼接规范上下文: ${CONTEXT} ($(wc -l < "${CONTEXT}") 行)"

# 2) 构造系统提示词与请求体
SYSTEM_PROMPT=$(cat <<'SYS'
你是一名严谨的技术规范审查专家。只审查 agent 执行规范集合的一致性。
输出要求：若发现问题，逐条列出"文件、问题描述、具体建议的修改"，并在最后一行
输出标记 ISSUES_FOUND；若未发现问题，只输出一行 NO_ISSUES_FOUND。
重点检查：1) 规范之间是否自相矛盾或重复；2) 是否存在歧义、不严谨、会误导
agent 的表述；3) 是否含私有项目专属约定（应中性化）。
SYS
)

CONTENT_JSON=$(jq -Rs . "${CONTEXT}")
SYSTEM_JSON=$(jq -n --arg s "${SYSTEM_PROMPT}" '$s')
# system / content 已是 JSON 字符串（含引号），需用 --argjson 传入避免二次转义
BODY=$(jq -n \
  --arg model "${AI_MODEL}" \
  --argjson system "${SYSTEM_JSON}" \
  --argjson content "${CONTENT_JSON}" \
  '{model:$model, messages:[{role:"system",content:$system},{role:"user",content:$content}]}')

# 3) 调用 API
echo "调用模型 ${AI_MODEL} (${AI_API_BASE}/chat/completions) ..."
RESP=$(curl -sS -f \
  -H "Authorization: Bearer ${AI_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "${BODY}" \
  "${AI_API_BASE}/chat/completions")

echo "${RESP}" | jq -r '.choices[0].message.content' > "${OUTPUT}"
echo "===== AI 审查结果 (${OUTPUT}) ====="
cat "${OUTPUT}"
