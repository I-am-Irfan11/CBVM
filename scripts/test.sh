#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -x .venv/bin/python ]] || { echo "Missing virtual environment; run scripts/setup.sh first." >&2; exit 1; }
mkdir -p test-results
GATELOG_TEST_TEMP="$(mktemp -d "$PWD/test-results/pytest.XXXXXX")"
(cd backend && ../.venv/bin/python -B -m pytest -q -p no:cacheprovider --basetemp="$GATELOG_TEST_TEMP")
(cd frontend && npm run build -- --configLoader native)
