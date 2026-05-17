#!/usr/bin/env bash
set -euo pipefail

OUTPUT_DIR="${1:-release}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$REPO_ROOT"

STATUS="$(git status --porcelain)"
if [ -n "$STATUS" ]; then
  echo "Working tree is not clean. Commit or stash changes before packaging." >&2
  exit 1
fi

COMMIT="$(git rev-parse --short HEAD)"
mkdir -p "$OUTPUT_DIR"
ARCHIVE_PATH="$OUTPUT_DIR/hr_mcp_release_${COMMIT}.zip"
rm -f "$ARCHIVE_PATH"

git archive --format=zip --output="$ARCHIVE_PATH" HEAD

echo "Created release archive: $REPO_ROOT/$ARCHIVE_PATH"
echo "Transfer this zip to nx2 with NoMachine, then unpack it on the intranet deployment machine."
echo "Intranet deployment target: /workspace/devops/env_prod/service/ai/hr_mcp"
