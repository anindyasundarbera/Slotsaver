#!/usr/bin/env bash
# One-time local setup. Requires Python 3.12+ and Node 20+.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

command -v python3.12 >/dev/null || { echo "python3.12 required" >&2; exit 1; }
command -v node >/dev/null || { echo "node required" >&2; exit 1; }

if [[ ! -d .venv ]]; then
  python3.12 -m venv .venv
fi
.venv/bin/pip install --upgrade pip >/dev/null
.venv/bin/pip install -r backend/requirements.txt
.venv/bin/pip install -r backend/requirements-dev.txt

if [[ ! -d frontend/node_modules ]]; then
  ( cd frontend && npm ci )
fi

if [[ ! -f backend/.env ]]; then
  cp backend/.env.example backend/.env
  echo "created backend/.env from .env.example (edit it for sandbox mode)"
fi

echo "setup complete. Next: ./scripts/dev.sh"
