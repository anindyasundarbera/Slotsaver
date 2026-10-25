#!/usr/bin/env bash
# Reset ONLY the synthetic demo database, then reseed.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DB_PATH="${1:-backend/data/slotsaver.db}"
case "$DB_PATH" in
  *production*|*prod*)
    echo "refusing to delete $DB_PATH: looks like a production path" >&2
    exit 1 ;;
esac

rm -f "$DB_PATH" "$DB_PATH-wal" "$DB_PATH-shm"
mkdir -p "$(dirname "$DB_PATH")"
echo "removed $DB_PATH (seeded automatically on next start)"
