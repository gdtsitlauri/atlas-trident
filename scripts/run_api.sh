#!/usr/bin/env bash
set -euo pipefail

HOST="${1:-0.0.0.0}"
PORT="${2:-8000}"
BASELINE_MODE="${3:-full_trident}"
SEED="${4:-42}"
DETERMINISTIC="${5:-true}"

source .venv/bin/activate
ATLAS_CONFIG=config/default.toml ATLAS_LOGS_DIR=logs/latest ATLAS_BASELINE_MODE="${BASELINE_MODE}" ATLAS_SEED="${SEED}" ATLAS_DETERMINISTIC="${DETERMINISTIC}" uvicorn atlas.api.main:app --host "${HOST}" --port "${PORT}"
