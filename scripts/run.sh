#!/bin/bash
# MemBridge native runner — sources .env then starts uvicorn.
# Invoked by launchd (com.daihi.membridge.plist).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV="$PROJECT_DIR/.venv"
ENV_FILE="$PROJECT_DIR/.env"

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

HOST="${MEMBRIDGE_HOST:-127.0.0.1}"

exec "$VENV/bin/uvicorn" membridge.server:app \
  --host "$HOST" \
  --port 7842 \
  --app-dir "$PROJECT_DIR"
