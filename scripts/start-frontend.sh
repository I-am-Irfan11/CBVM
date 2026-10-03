#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../frontend"
[[ -x node_modules/.bin/vite ]] || { echo "Missing frontend dependencies; run scripts/setup.sh first." >&2; exit 1; }
npm run dev
