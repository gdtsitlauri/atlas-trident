#!/usr/bin/env bash
set -euo pipefail

STEPS="${1:-20}"
BASELINE_MODE="${2:-full_trident}"
SEED="${3:-42}"
LOGS_DIR="${4:-logs/latest}"

source .venv/bin/activate
python -m atlas.cli run --steps "${STEPS}" --baseline-mode "${BASELINE_MODE}" --seed "${SEED}" --deterministic --config config/default.toml --logs-dir "${LOGS_DIR}"
