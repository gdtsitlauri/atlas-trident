from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atlas.baselines import FULL_TRIDENT, normalize_baseline_mode
from atlas.orchestrator import AtlasOrchestrator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCENARIOS_DIR = PROJECT_ROOT / "experiments" / "scenarios"


def available_scenarios() -> list[str]:
    return sorted(path.stem for path in SCENARIOS_DIR.glob("*.json"))


def load_scenario_payload(scenario_name: str, scenario_file: str | None = None) -> dict[str, Any]:
    scenario_path = Path(scenario_file) if scenario_file else SCENARIOS_DIR / f"{scenario_name}.json"
    if not scenario_path.exists():
        raise FileNotFoundError(f"Scenario file not found: {scenario_path}")
    return json.loads(scenario_path.read_text(encoding="utf-8"))


def summarize_reports(
    orchestrator: AtlasOrchestrator,
    reports: list[Any],
    scenario_name: str,
    baseline_mode: str,
    seed: int,
) -> dict[str, Any]:
    if not reports:
        return {
            "scenario": scenario_name,
            "baseline_mode": baseline_mode,
            "seed": seed,
            "cycles": 0,
        }

    total_approved = sum(report.approved for report in reports)
    total_proposals = sum(report.proposals for report in reports)
    weighted_success = sum(report.action_success_rate * report.approved for report in reports)
    overall_success_rate = 0.0 if total_approved == 0 else weighted_success / total_approved

    return {
        "scenario": scenario_name,
        "baseline_mode": baseline_mode,
        "seed": seed,
        "cycles": len(reports),
        "decision_latency_ms_avg": sum(report.decision_latency_ms for report in reports) / len(reports),
        "consensus_latency_ms_avg": sum(report.consensus_latency_ms for report in reports) / len(reports),
        "sla_violations_total": sum(report.metrics.sla_violations for report in reports),
        "recovery_time_ms_max": max(report.metrics.recovery_time_ms for report in reports),
        "resource_utilization_avg": sum(report.metrics.resource_utilization for report in reports) / len(reports),
        "cost_proxy_avg": sum(report.metrics.cost_proxy for report in reports) / len(reports),
        "action_success_rate": overall_success_rate,
        "governance_overhead_total": sum(report.governance_overhead for report in reports),
        "total_proposals": total_proposals,
        "total_approved": total_approved,
        "trust_scores_final": orchestrator.ledger.get_all_trust(),
        "rl_reward_trends": {
            agent.agent_id: agent.rl_engine.average_reward() for agent in orchestrator.agents
        },
        "latest_metrics": reports[-1].metrics.model_dump(),
    }


def run_scenario_experiment(
    scenario_name: str,
    scenario_file: str | None = None,
    steps: int | None = None,
    config_path: str = "config/default.toml",
    logs_dir: str | None = None,
    baseline_mode: str = FULL_TRIDENT,
    seed: int | None = None,
    deterministic_mode: bool | None = None,
) -> dict[str, Any]:
    baseline_mode = normalize_baseline_mode(baseline_mode)
    scenario = load_scenario_payload(scenario_name, scenario_file=scenario_file)
    events = scenario.get("events", [])
    event_schedule = AtlasOrchestrator.build_event_schedule(events)

    effective_seed = int(seed if seed is not None else scenario.get("seed", 42))
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    default_logs_dir = (
        PROJECT_ROOT
        / "logs"
        / f"{scenario_name}_{baseline_mode}_seed{effective_seed}_{timestamp}"
    )

    orchestrator = AtlasOrchestrator(
        config_path=config_path,
        logs_dir=logs_dir or str(default_logs_dir),
        baseline_mode=baseline_mode,
        seed=effective_seed,
        deterministic_mode=deterministic_mode,
    )
    scenario_steps = max(1, int(steps or scenario.get("default_steps", orchestrator.config.episode_steps)))

    reports = orchestrator.run(steps=scenario_steps, event_schedule=event_schedule)
    summary = summarize_reports(
        orchestrator,
        reports,
        scenario_name=scenario_name,
        baseline_mode=baseline_mode,
        seed=effective_seed,
    )

    output_dir = Path(orchestrator.config.paths.logs_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "cycle_reports.json").write_text(
        json.dumps([report.model_dump() for report in reports], indent=2),
        encoding="utf-8",
    )
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
