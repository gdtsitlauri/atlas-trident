from __future__ import annotations

import argparse
import json

from atlas.baselines import BASELINE_MODES, FULL_TRIDENT
from atlas.orchestrator import AtlasOrchestrator


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ATLAS command-line interface")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_cmd = subparsers.add_parser("run", help="Run the baseline simulation")
    run_cmd.add_argument("--steps", type=int, default=20)
    run_cmd.add_argument("--config", type=str, default="config/default.toml")
    run_cmd.add_argument("--logs-dir", type=str, default=None)
    run_cmd.add_argument("--baseline-mode", type=str, default=FULL_TRIDENT, choices=sorted(BASELINE_MODES))
    run_cmd.add_argument("--seed", type=int, default=None)
    run_cmd.add_argument("--deterministic", dest="deterministic_mode", action=argparse.BooleanOptionalAction, default=None)

    scenario_cmd = subparsers.add_parser("scenario", help="Run a scenario file")
    scenario_cmd.add_argument("--scenario-file", type=str, required=True)
    scenario_cmd.add_argument("--steps", type=int, default=20)
    scenario_cmd.add_argument("--config", type=str, default="config/default.toml")
    scenario_cmd.add_argument("--logs-dir", type=str, default=None)
    scenario_cmd.add_argument("--baseline-mode", type=str, default=FULL_TRIDENT, choices=sorted(BASELINE_MODES))
    scenario_cmd.add_argument("--seed", type=int, default=None)
    scenario_cmd.add_argument("--deterministic", dest="deterministic_mode", action=argparse.BooleanOptionalAction, default=None)

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    orchestrator = AtlasOrchestrator(
        config_path=args.config,
        logs_dir=args.logs_dir,
        baseline_mode=args.baseline_mode,
        seed=args.seed,
        deterministic_mode=args.deterministic_mode,
    )

    if args.command == "run":
        reports = orchestrator.run(steps=max(1, args.steps))
        print(json.dumps([report.model_dump() for report in reports], indent=2))
        return

    if args.command == "scenario":
        schedule = AtlasOrchestrator.load_event_schedule(args.scenario_file)
        reports = orchestrator.run(steps=max(1, args.steps), event_schedule=schedule)
        print(json.dumps([report.model_dump() for report in reports], indent=2))
        return

    raise ValueError("unsupported_cli_command")


if __name__ == "__main__":
    main()
