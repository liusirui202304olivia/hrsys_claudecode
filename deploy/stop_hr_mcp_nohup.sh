#!/usr/bin/env bash
set -euo pipefail

BASE="/workspace/devops/env_prod/service/ai/hr_mcp"
LOGS="$BASE/logs"
PID_FILE="$LOGS/hr_mcp.pid"

if [ ! -f "$PID_FILE" ]; then
  echo "No pid file found: $PID_FILE"
  exit 0
fi

PID="$(cat "$PID_FILE")"
if [ -z "$PID" ]; then
  echo "Empty pid file: $PID_FILE"
  rm -f "$PID_FILE"
  exit 0
fi

if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "Stopped HR MCP pid $PID"
else
  echo "Process $PID is not running"
fi

rm -f "$PID_FILE"
