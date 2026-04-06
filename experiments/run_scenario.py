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

from atlas.baselines import BASELINE_MODES, FULL_TRIDENT
from atlas.experiment_runner import run_scenario_experiment


def main(default_scenario: str | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run ATLAS experiment scenarios")
    parser.add_argument("--scenario", type=str, default=default_scenario or "overload")
    parser.add_argument("--scenario-file", type=str, default=None)
    parser.add_argument("--steps", type=int, default=None)
    parser.add_argument("--config", type=str, default="config/default.toml")
    parser.add_argument("--logs-dir", type=str, default=None)
    parser.add_argument("--baseline-mode", type=str, default=FULL_TRIDENT, choices=sorted(BASELINE_MODES))
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--deterministic", dest="deterministic_mode", action=argparse.BooleanOptionalAction, default=None)
    args = parser.parse_args()

    summary = run_scenario_experiment(
        scenario_name=args.scenario,
        scenario_file=args.scenario_file,
        steps=args.steps,
        config_path=args.config,
        logs_dir=args.logs_dir,
        baseline_mode=args.baseline_mode,
        seed=args.seed,
        deterministic_mode=args.deterministic_mode,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
