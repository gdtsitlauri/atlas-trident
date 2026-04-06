#!/usr/bin/env bash
set -euo pipefail

STEPS="${1:-20}"
SCENARIOS="${2:-overload,node_failure,latency_spike,conflicting_proposals,resource_scarcity}"
BASELINES="${3:-random_policy,rule_based_policy,trident_no_rl,trident_no_trust,full_trident}"
SEEDS="${4:-42}"
RESULTS_ROOT="${5:-results}"

source .venv/bin/activate
python experiments/run_benchmark.py --steps "${STEPS}" --scenarios "${SCENARIOS}" --baselines "${BASELINES}" --seeds "${SEEDS}" --deterministic --config config/default.toml --results-root "${RESULTS_ROOT}"
