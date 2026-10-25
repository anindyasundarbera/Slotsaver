#!/usr/bin/env bash
# Start the API and the Angular dev server together.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/python ]]; then
  echo "error: .venv missing. Run ./scripts/setup.sh first." >&2
  exit 1
fi
if [[ ! -d frontend/node_modules ]]; then
  echo "error: frontend/node_modules missing. Run ./scripts/setup.sh first." >&2
  exit 1
fi

mkdir -p backend/data
cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

( cd backend && ../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 ) &
API_PID=$!
( cd frontend && npm start --silent ) &
UI_PID=$!

echo "API  http://127.0.0.1:8000/api/health  (pid $API_PID)"
echo "UI   http://localhost:4200            (pid $UI_PID)"
wait
