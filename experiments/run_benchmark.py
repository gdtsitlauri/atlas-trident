from __future__ import annotations
# ruff: noqa: E402, I001

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from atlas.baselines import BASELINE_MODES
from atlas.benchmarking import DEFAULT_BASELINES, DEFAULT_SCENARIOS, run_benchmark_suite


def _parse_csv_list(value: str | None, fallback: list[str]) -> list[str]:
    if not value:
        return fallback
    return [chunk.strip() for chunk in value.split(",") if chunk.strip()]


def _parse_seed_list(value: str | None) -> list[int]:
    if not value:
        return [42]
    return [int(chunk.strip()) for chunk in value.split(",") if chunk.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ATLAS baseline benchmark suite")
    parser.add_argument("--config", type=str, default="config/default.toml")
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument(
        "--scenarios",
        type=str,
        default=",".join(DEFAULT_SCENARIOS),
        help="Comma-separated scenario names",
    )
    parser.add_argument(
        "--baselines",
        type=str,
        default=",".join(DEFAULT_BASELINES),
        help="Comma-separated baseline modes",
    )
    parser.add_argument(
        "--seeds",
        type=str,
        default="42",
        help="Comma-separated integer seeds",
    )
    parser.add_argument("--results-root", type=str, default="results")
    parser.add_argument("--deterministic", dest="deterministic_mode", action=argparse.BooleanOptionalAction, default=True)

    args = parser.parse_args()
    scenarios = _parse_csv_list(args.scenarios, DEFAULT_SCENARIOS)
    baselines = _parse_csv_list(args.baselines, DEFAULT_BASELINES)
    seeds = _parse_seed_list(args.seeds)

    for mode in baselines:
        if mode not in BASELINE_MODES:
            raise ValueError(f"Unsupported baseline mode: {mode}")

    results = run_benchmark_suite(
        config_path=args.config,
        steps=max(1, int(args.steps)),
        scenarios=scenarios,
        baseline_modes=baselines,
        seeds=seeds,
        results_root=args.results_root,
        deterministic_mode=args.deterministic_mode,
    )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
