#!/usr/bin/env bash
set -euo pipefail

BASE="/workspace/devops/env_prod/service/ai/hr_mcp"
URL="${HR_MCP_URL:-http://127.0.0.1:${HR_MCP_PORT:-8765}}"
TOKEN="${HR_MCP_TOKEN:-${HR_MCP_CHECK_TOKEN:-}}"

if [ -z "$TOKEN" ]; then
  echo "Set HR_MCP_TOKEN or HR_MCP_CHECK_TOKEN before running this script." >&2
  exit 1
fi

echo "Checking $URL/healthz"
curl -sS "$URL/healthz"
echo

echo "Checking $URL/readyz"
curl -sS "$URL/readyz"
echo

echo "Checking MCP tools/list"
curl -sS "$URL/mcp" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
echo

echo "Checking query_talent_pool_facts"
curl -sS "$URL/mcp" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"query_talent_pool_facts","arguments":{"metrics":["count"],"group_by":["position_name"]}}}'
echo

echo "Checking describe_hr_safe_schema"
curl -sS "$URL/mcp" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"describe_hr_safe_schema","arguments":{}}}'
echo

echo "Checking query_hr_safe_sql"
curl -sS "$URL/mcp" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"query_hr_safe_sql","arguments":{"purpose":"deployment smoke","sql":"SELECT candidate_id, name, status FROM v_candidate_agent_safe LIMIT 5"}}}'
echo

echo "Checking interview evaluation safe SQL"
curl -sS "$URL/mcp" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"query_hr_safe_sql","arguments":{"purpose":"deployment smoke interview evaluation","sql":"SELECT candidate_id, candidate_name, feedback, evaluation_result FROM v_candidate_interview_evaluate_safe LIMIT 5"}}}'
echo

echo "Checking interview question aggregate safe SQL"
curl -sS "$URL/mcp" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"query_hr_safe_sql","arguments":{"purpose":"deployment smoke interview score aggregate","sql":"SELECT interviewer_id, AVG(score) AS avg_score, COUNT(*) AS count FROM v_candidate_interview_question_safe GROUP BY interviewer_id LIMIT 5"}}}'
echo

echo "Checking screen evaluation safe SQL"
curl -sS "$URL/mcp" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"query_hr_safe_sql","arguments":{"purpose":"deployment smoke screen evaluation","sql":"SELECT candidate_id, candidate_name, feedback, screen_result FROM v_candidate_screen_evaluate_safe LIMIT 5"}}}'
echo
