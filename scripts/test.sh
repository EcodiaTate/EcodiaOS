#!/usr/bin/env bash
set -euo pipefail
export DEV=1 SIMULA_ARTIFACTS_ROOT="${SIMULA_ARTIFACTS_ROOT:-.simula}"
ruff check systems tests
mypy systems -q || true
pytest -q -n auto --maxfail=1 --durations=10
