#!/usr/bin/env bash
set -euo pipefail

BASE="/workspace/devops/env_prod/service/ai/hr_mcp"
APP="$BASE/app"
VENV="$BASE/venv_py36"
LOGS="$BASE/logs"
ENV_FILE="$BASE/.env"
PID_FILE="$LOGS/hr_mcp.pid"
OUT_FILE="$LOGS/hr_mcp.out"
ERR_FILE="$LOGS/hr_mcp.err"

mkdir -p "$LOGS"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing env file: $ENV_FILE" >&2
  exit 1
fi

if [ ! -x "$VENV/bin/python" ]; then
  echo "Missing Python executable: $VENV/bin/python" >&2
  exit 1
fi

if [ -f "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE")"
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "HR MCP already running with pid $OLD_PID"
    exit 0
  fi
fi

cd "$APP"
export HR_MCP_ENV_PATH="$ENV_FILE"
nohup "$VENV/bin/python" -m hr_mcp > "$OUT_FILE" 2> "$ERR_FILE" &
PID="$!"
echo "$PID" > "$PID_FILE"
echo "HR MCP started with pid $PID"
echo "stdout: $OUT_FILE"
echo "stderr: $ERR_FILE"
