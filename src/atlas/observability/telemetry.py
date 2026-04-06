from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from atlas.types import CycleReport, DecisionTrace
from atlas.utils.time_utils import utc_now_iso


class ObservabilityHub:
    """Metrics, events, traces, and trust evolution storage for experiments."""

    def __init__(self, logs_dir: str) -> None:
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        self.metrics_csv = self.logs_dir / "metrics.csv"
        self.events_jsonl = self.logs_dir / "events.jsonl"
        self.decision_traces_jsonl = self.logs_dir / "decision_traces.jsonl"
        self.trust_jsonl = self.logs_dir / "trust_scores.jsonl"
        self.rl_stats_jsonl = self.logs_dir / "rl_stats.jsonl"
        self.state_json = self.logs_dir / "state_latest.json"
        self.run_metadata_json = self.logs_dir / "run_metadata.json"
        self.config_snapshot_json = self.logs_dir / "config_snapshot.json"

        if not self.metrics_csv.exists():
            with self.metrics_csv.open("w", encoding="utf-8", newline="") as file_obj:
                writer = csv.writer(file_obj)
                writer.writerow(
                    [
                        "timestamp",
                        "step",
                        "proposals",
                        "approved",
                        "action_success_rate",
                        "decision_latency_ms",
                        "consensus_latency_ms",
                        "governance_overhead",
                        "avg_latency_ms",
                        "sla_violations",
                        "availability",
                        "resource_utilization",
                        "cost_proxy",
                        "utility",
                        "recovery_time_ms",
                    ]
                )

    def record_cycle(self, report: CycleReport) -> None:
        metrics = report.metrics
        with self.metrics_csv.open("a", encoding="utf-8", newline="") as file_obj:
            writer = csv.writer(file_obj)
            writer.writerow(
                [
                    utc_now_iso(),
                    report.step,
                    report.proposals,
                    report.approved,
                    round(report.action_success_rate, 5),
                    round(report.decision_latency_ms, 5),
                    round(report.consensus_latency_ms, 5),
                    report.governance_overhead,
                    metrics.avg_latency_ms,
                    metrics.sla_violations,
                    metrics.availability,
                    metrics.resource_utilization,
                    metrics.cost_proxy,
                    metrics.utility,
                    metrics.recovery_time_ms,
                ]
            )

    def record_event(self, event_kind: str, payload: dict[str, Any]) -> None:
        with self.events_jsonl.open("a", encoding="utf-8") as file_obj:
            file_obj.write(json.dumps({"ts": utc_now_iso(), "kind": event_kind, "payload": payload}) + "\n")

    def record_decision_trace(self, trace: DecisionTrace) -> None:
        with self.decision_traces_jsonl.open("a", encoding="utf-8") as file_obj:
            file_obj.write(json.dumps(trace.model_dump()) + "\n")

    def record_trust(self, step: int, trust_scores: dict[str, float]) -> None:
        with self.trust_jsonl.open("a", encoding="utf-8") as file_obj:
            file_obj.write(
                json.dumps({"ts": utc_now_iso(), "step": step, "trust_scores": trust_scores}) + "\n"
            )

    def record_rl_stats(
        self,
        step: int,
        agent_id: str,
        reward: float,
        average_reward: float,
        replay_size: int,
        q_states: int,
        rl_enabled: bool,
    ) -> None:
        payload = {
            "ts": utc_now_iso(),
            "step": step,
            "agent_id": agent_id,
            "reward": reward,
            "average_reward": average_reward,
            "replay_size": replay_size,
            "q_states": q_states,
            "rl_enabled": rl_enabled,
        }
        with self.rl_stats_jsonl.open("a", encoding="utf-8") as file_obj:
            file_obj.write(json.dumps(payload) + "\n")

    def write_run_metadata(self, metadata: dict[str, Any]) -> None:
        self.run_metadata_json.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    def write_config_snapshot(self, config_snapshot: dict[str, Any]) -> None:
        self.config_snapshot_json.write_text(json.dumps(config_snapshot, indent=2), encoding="utf-8")

    def write_state(self, state: dict[str, Any]) -> None:
        self.state_json.write_text(json.dumps(state, indent=2), encoding="utf-8")
