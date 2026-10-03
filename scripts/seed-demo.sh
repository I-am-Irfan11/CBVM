#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -x .venv/bin/python ]] || { echo "Missing virtual environment; run scripts/setup.sh first." >&2; exit 1; }
if grep -q '^DATABASE_MODE=memory$' .env; then
  echo "Memory mode seeds fictional demo data at backend startup; data is ephemeral."
  exit 0
fi
(cd backend && ../.venv/bin/python -m app.database.seed)
