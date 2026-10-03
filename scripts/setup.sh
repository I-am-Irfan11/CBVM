#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v python3 >/dev/null || { echo "Python 3.10+ is required." >&2; exit 1; }
command -v node >/dev/null || { echo "Node.js 22+ is required." >&2; exit 1; }
command -v npm >/dev/null || { echo "npm is required." >&2; exit 1; }
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
[[ -f .env ]] || cp .env.example .env
.venv/bin/python scripts/bootstrap_env.py
(cd frontend && npm ci)
echo "Setup complete. Run scripts/start-backend.sh and scripts/start-frontend.sh in separate terminals."
