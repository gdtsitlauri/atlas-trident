#!/usr/bin/env bash
set -euo pipefail

SCENARIO="${1:-overload}"
STEPS="${2:-20}"
BASELINE_MODE="${3:-full_trident}"
SEED="${4:-42}"
LOGS_DIR="${5:-logs/latest}"

source .venv/bin/activate
python experiments/run_scenario.py --scenario "${SCENARIO}" --steps "${STEPS}" --baseline-mode "${BASELINE_MODE}" --seed "${SEED}" --deterministic --config config/default.toml --logs-dir "${LOGS_DIR}"
