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
