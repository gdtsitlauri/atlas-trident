from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atlas.baselines import BASELINE_MODES, FULL_TRIDENT, normalize_baseline_mode
from atlas.experiment_runner import available_scenarios, run_scenario_experiment

DEFAULT_SCENARIOS = [
    "overload",
    "node_failure",
    "latency_spike",
    "conflicting_proposals",
    "resource_scarcity",
]

DEFAULT_BASELINES = [
    "random_policy",
    "rule_based_policy",
    "trident_no_rl",
    "trident_no_trust",
    FULL_TRIDENT,
]


def _ensure_valid_modes(modes: list[str]) -> list[str]:
    normalized = [normalize_baseline_mode(mode) for mode in modes]
    if len(set(normalized)) != len(normalized):
        deduped: list[str] = []
        seen: set[str] = set()
        for mode in normalized:
            if mode in seen:
                continue
            seen.add(mode)
            deduped.append(mode)
        return deduped
    return normalized


def run_benchmark_suite(
    config_path: str = "config/default.toml",
    steps: int = 20,
    scenarios: list[str] | None = None,
    baseline_modes: list[str] | None = None,
    seeds: list[int] | None = None,
    results_root: str = "results",
    deterministic_mode: bool | None = True,
) -> dict[str, Any]:
    scenario_names = scenarios or DEFAULT_SCENARIOS
    scenario_set = set(available_scenarios())
    for scenario_name in scenario_names:
        if scenario_name not in scenario_set:
            raise ValueError(f"unknown_scenario: {scenario_name}")

    chosen_baselines = _ensure_valid_modes(baseline_modes or DEFAULT_BASELINES)
    seed_values = seeds or [42]

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = f"benchmark_{timestamp}"

    root = Path(results_root)
    benchmark_root = root / "benchmark_runs" / run_id
    summaries_root = root / "summaries"
    sample_root = root / "sample_reports"
    benchmark_root.mkdir(parents=True, exist_ok=True)
    summaries_root.mkdir(parents=True, exist_ok=True)
    sample_root.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []

    for baseline_mode in chosen_baselines:
        for scenario_name in scenario_names:
            for seed in seed_values:
                run_dir = benchmark_root / baseline_mode / scenario_name / f"seed_{seed}"
                summary = run_scenario_experiment(
                    scenario_name=scenario_name,
                    steps=steps,
                    config_path=config_path,
                    logs_dir=str(run_dir),
                    baseline_mode=baseline_mode,
                    seed=seed,
                    deterministic_mode=deterministic_mode,
                )
                records.append(
                    {
                        "run_id": run_id,
                        "scenario": scenario_name,
                        "baseline_mode": baseline_mode,
                        "seed": seed,
                        "steps": steps,
                        "decision_latency_ms_avg": summary["decision_latency_ms_avg"],
                        "consensus_latency_ms_avg": summary["consensus_latency_ms_avg"],
                        "sla_violations_total": summary["sla_violations_total"],
                        "recovery_time_ms_max": summary["recovery_time_ms_max"],
                        "resource_utilization_avg": summary["resource_utilization_avg"],
                        "cost_proxy_avg": summary["cost_proxy_avg"],
                        "action_success_rate": summary["action_success_rate"],
                        "governance_overhead_total": summary["governance_overhead_total"],
                        "total_proposals": summary["total_proposals"],
                        "total_approved": summary["total_approved"],
                        "latest_utility": summary["latest_metrics"]["utility"],
                        "latest_sla_violations": summary["latest_metrics"]["sla_violations"],
                        "run_dir": str(run_dir).replace("\\", "/"),
                    }
                )

    csv_path = summaries_root / f"{run_id}.csv"
    json_path = summaries_root / f"{run_id}.json"
    metadata_path = summaries_root / f"{run_id}_metadata.json"

    fieldnames = list(records[0].keys()) if records else ["run_id"]
    with csv_path.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        for row in records:
            writer.writerow(row)

    json_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    metadata_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "config_path": config_path,
                "steps": steps,
                "deterministic_mode": deterministic_mode,
                "baseline_modes": chosen_baselines,
                "scenarios": scenario_names,
                "seeds": seed_values,
                "records": len(records),
                "results_root": str(root).replace("\\", "/"),
                "allowed_baseline_modes": sorted(BASELINE_MODES),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    sample_path = sample_root / f"{run_id}_sample.json"
    sample_payload = records[: min(5, len(records))]
    sample_path.write_text(json.dumps(sample_payload, indent=2), encoding="utf-8")

    return {
        "run_id": run_id,
        "records": len(records),
        "benchmark_root": str(benchmark_root).replace("\\", "/"),
        "summary_csv": str(csv_path).replace("\\", "/"),
        "summary_json": str(json_path).replace("\\", "/"),
        "metadata_json": str(metadata_path).replace("\\", "/"),
        "sample_report": str(sample_path).replace("\\", "/"),
    }
