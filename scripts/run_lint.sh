#!/usr/bin/env bash
set -euo pipefail

source .venv/bin/activate
python -m ruff check src tests experiments dashboard
