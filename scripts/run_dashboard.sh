#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-8501}"

source .venv/bin/activate
ATLAS_LOGS_DIR=logs/latest streamlit run dashboard/app.py --server.port "${PORT}" --server.address 0.0.0.0
