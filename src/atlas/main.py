from __future__ import annotations

import argparse
import json

from atlas.baselines import BASELINE_MODES, FULL_TRIDENT
from atlas.orchestrator import AtlasOrchestrator


def run_default(
    steps: int = 10,
    config_path: str | None = None,
    baseline_mode: str = FULL_TRIDENT,
    seed: int | None = None,
    deterministic_mode: bool | None = None,
) -> list[dict]:
    orchestrator = AtlasOrchestrator(
        config_path=config_path,
        baseline_mode=baseline_mode,
        seed=seed,
        deterministic_mode=deterministic_mode,
    )
    reports = orchestrator.run(steps=steps)
    return [report.model_dump() for report in reports]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ATLAS orchestrator with default settings")
    parser.add_argument("--steps", type=int, default=10, help="Number of simulation cycles")
    parser.add_argument("--config", type=str, default=None, help="Path to TOML config file")
    parser.add_argument("--baseline-mode", type=str, default=FULL_TRIDENT, choices=sorted(BASELINE_MODES))
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--deterministic", dest="deterministic_mode", action=argparse.BooleanOptionalAction, default=None)
    args = parser.parse_args()

    output = run_default(
        steps=max(1, args.steps),
        config_path=args.config,
        baseline_mode=args.baseline_mode,
        seed=args.seed,
        deterministic_mode=args.deterministic_mode,
    )
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
