#!/usr/bin/env bash
# Full verification: backend tests, frontend typecheck + production build.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== backend tests =="
( cd backend && ../.venv/bin/python -m pytest -q )

echo "== frontend typecheck =="
( cd frontend && npx tsc -p tsconfig.app.json --noEmit )

echo "== frontend production build =="
( cd frontend && npm run build )

echo "== all checks passed =="
