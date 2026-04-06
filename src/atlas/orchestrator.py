from __future__ import annotations

import json
import logging
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

from atlas.agent_core.agent import TwinAgent
from atlas.agent_core.trident import TridentScorer
from atlas.baselines import behavior_for, normalize_baseline_mode
from atlas.cloud_simulator.simulator import CloudSimulator
from atlas.config import AtlasConfig
from atlas.governance_chain.ledger import PermissionedLedger
from atlas.llm_planner.planner import build_planner
from atlas.observability.telemetry import ObservabilityHub
from atlas.policy_guard.guard import PolicyGuard
from atlas.rl_engine.q_learning import QLearningEngine
from atlas.twin_runtime.twin import DigitalTwin
from atlas.types import CycleReport, ExecutionOutcome
from atlas.utils.reproducibility import configure_global_seed
from atlas.utils.time_utils import utc_now_iso

LOGGER = logging.getLogger(__name__)


class AtlasOrchestrator:
    """Coordinates decentralized twin agents, TRIDENT scoring, and permissioned governance."""

    def __init__(
        self,
        config: AtlasConfig | None = None,
        config_path: str | None = None,
        logs_dir: str | None = None,
        baseline_mode: str | None = None,
        seed: int | None = None,
        deterministic_mode: bool | None = None,
    ) -> None:
        self.config = config or AtlasConfig.from_toml(config_path)

        if seed is not None:
            self.config.seed = int(seed)
        if deterministic_mode is not None:
            self.config.deterministic_mode = bool(deterministic_mode)
        self.config.baseline_mode = normalize_baseline_mode(baseline_mode or self.config.baseline_mode)

        if logs_dir:
            self.config.paths.logs_dir = logs_dir
            self.config.paths.ledger_db = str(Path(logs_dir) / "atlas_ledger.db")

        Path(self.config.paths.logs_dir).mkdir(parents=True, exist_ok=True)
        self.reproducibility_status = configure_global_seed(
            self.config.seed,
            deterministic_mode=self.config.deterministic_mode,
        )

        self.simulator = CloudSimulator(self.config)
        self.governance_ids = [f"gov-{i+1}" for i in range(self.config.governance_nodes)]
        self.ledger = PermissionedLedger(self.config.paths.ledger_db, self.governance_ids)
        self.observability = ObservabilityHub(self.config.paths.logs_dir)
        self.execution_policy_guard = PolicyGuard(self.config.policy, self.config.sla)
        self.baseline_behavior = behavior_for(self.config.baseline_mode)

        self.observability.write_config_snapshot(self.config.to_dict())
        self.observability.write_run_metadata(
            {
                "created_at": utc_now_iso(),
                "seed": self.config.seed,
                "deterministic_mode": self.config.deterministic_mode,
                "baseline_mode": self.config.baseline_mode,
                "planner_mode": self.config.llm.mode or self.config.planner_mode,
                "reproducibility": self.reproducibility_status,
            }
        )

        self.agents: list[TwinAgent] = []
        planner_mode = self.config.llm.mode or self.config.planner_mode
        for idx in range(self.config.twin_nodes):
            twin = DigitalTwin(
                twin_id=f"twin-{idx+1}",
                simulator=self.simulator,
                what_if_horizon=self.config.what_if_horizon,
            )

            agent = TwinAgent(
                agent_id=f"agent-{idx+1}",
                governance_id=self.governance_ids[idx % len(self.governance_ids)],
                twin=twin,
                planner=build_planner(planner_mode, self.config),
                rl_engine=QLearningEngine(self.config.rl, seed=self.config.seed + idx),
                policy_guard=PolicyGuard(self.config.policy, self.config.sla),
                ledger=self.ledger,
                trident=TridentScorer(self.config.trident),
                baseline_mode=self.config.baseline_mode,
                seed=self.config.seed + idx,
            )
            self.agents.append(agent)
            self.ledger.get_trust(agent.agent_id)

        LOGGER.info(
            "ATLAS orchestrator initialized baseline=%s seed=%s deterministic=%s",
            self.config.baseline_mode,
            self.config.seed,
            self.config.deterministic_mode,
        )

    @staticmethod
    def build_event_schedule(events: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
        schedule: dict[int, list[dict[str, Any]]] = {}
        for event in events:
            step = int(event.get("step", 1))
            schedule.setdefault(step, []).append({k: v for k, v in event.items() if k != "step"})
        return schedule

    @staticmethod
    def load_event_schedule(path: str | Path) -> dict[int, list[dict[str, Any]]]:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        events = payload.get("events", []) if isinstance(payload, dict) else payload
        return AtlasOrchestrator.build_event_schedule(events)

    def get_state(self) -> dict[str, Any]:
        state = self.simulator.export_state()
        state["trust_scores"] = self.ledger.get_all_trust()
        state["planner_mode"] = self.config.llm.mode or self.config.planner_mode
        state["baseline_mode"] = self.config.baseline_mode
        state["seed"] = self.config.seed
        state["deterministic_mode"] = self.config.deterministic_mode
        state["agents"] = [agent.agent_id for agent in self.agents]
        state["governance_nodes"] = self.governance_ids
        return state

    def run_cycle(self, external_events: list[dict[str, Any]] | None = None) -> CycleReport:
        if external_events:
            self.observability.record_event("external_events", {"events": external_events})

        proposals = []
        for agent in self.agents:
            proposal, traces = agent.propose(max_candidates=self.config.max_candidates)
            for trace in traces:
                self.observability.record_decision_trace(trace)
            if proposal:
                proposals.append(proposal)
                self.ledger.submit_proposal(proposal)

        proposals.sort(key=lambda item: item.composite_score, reverse=True)

        governance_overhead = 0
        approved_count = 0
        success_count = 0
        consensus_latencies: list[float] = []
        decision_latencies: list[float] = []
        events_left = external_events

        latest_metrics = self.simulator.last_metrics

        for proposal in proposals:
            consensus_start = perf_counter()
            for validator in self.agents:
                vote = validator.validate_proposal(proposal)
                self.ledger.cast_vote(vote)
                governance_overhead += 1

            consensus_latency_ms = (perf_counter() - consensus_start) * 1000
            consensus_latencies.append(consensus_latency_ms)
            decision = self.ledger.finalize(
                proposal.proposal_id,
                consensus_latency_ms=consensus_latency_ms,
            )
            governance_overhead += 2

            if decision.approved:
                approved_count += 1

                decision_start = perf_counter()
                guard_snapshot = self.simulator.get_twin_snapshot("execution-guard")
                execution_guard = self.execution_policy_guard.evaluate(proposal.action, guard_snapshot)

                if not execution_guard.allowed:
                    decision_latency_ms = (perf_counter() - decision_start) * 1000
                    detail = "blocked_pre_execution:" + ",".join(execution_guard.reasons)
                    reward = -0.25
                    decision_latencies.append(decision_latency_ms)

                    outcome = ExecutionOutcome(
                        proposal_id=proposal.proposal_id,
                        success=False,
                        details=detail,
                        reward=round(reward, 6),
                        decision_latency_ms=round(decision_latency_ms, 6),
                        executed_at=utc_now_iso(),
                    )
                    self.ledger.record_execution(outcome)
                    if self.baseline_behavior.use_trust:
                        self.ledger.update_trust(proposal.agent_id, -0.03)

                    self.observability.record_event(
                        "execution_blocked",
                        {
                            "proposal_id": proposal.proposal_id,
                            "reason": detail,
                            "baseline_mode": self.config.baseline_mode,
                        },
                    )
                    continue

                success, detail = self.simulator.apply_action(proposal.action)
                latest_metrics = self.simulator.step(events_left)
                events_left = None
                reward = latest_metrics.utility if success else latest_metrics.utility - 0.20
                decision_latency_ms = (perf_counter() - decision_start) * 1000
                decision_latencies.append(decision_latency_ms)

                outcome = ExecutionOutcome(
                    proposal_id=proposal.proposal_id,
                    success=success,
                    details=detail,
                    reward=round(reward, 6),
                    decision_latency_ms=round(decision_latency_ms, 6),
                    executed_at=utc_now_iso(),
                )
                self.ledger.record_execution(outcome)
                if self.baseline_behavior.use_trust:
                    self.ledger.update_trust(proposal.agent_id, 0.03 if success else -0.05)
                self.observability.record_event(
                    "execution",
                    {
                        "proposal_id": proposal.proposal_id,
                        "approved": True,
                        "success": success,
                        "reward": reward,
                        "details": detail,
                    },
                )

                if success:
                    success_count += 1

                for agent in self.agents:
                    agent.learn(proposal.action, reward)
                    self.observability.record_rl_stats(
                        step=latest_metrics.step,
                        agent_id=agent.agent_id,
                        reward=reward,
                        average_reward=agent.rl_engine.average_reward(),
                        replay_size=len(agent.rl_engine.replay_buffer),
                        q_states=len(agent.rl_engine.q_table),
                        rl_enabled=agent.behavior.use_rl,
                    )

            else:
                decision_latencies.append(consensus_latency_ms)
                self.ledger.record_execution(
                    ExecutionOutcome(
                        proposal_id=proposal.proposal_id,
                        success=False,
                        details="quorum_not_reached",
                        reward=-0.1,
                        decision_latency_ms=round(consensus_latency_ms, 6),
                        executed_at=utc_now_iso(),
                    )
                )
                if self.baseline_behavior.use_trust:
                    self.ledger.update_trust(proposal.agent_id, -0.02)
                self.observability.record_event(
                    "execution",
                    {
                        "proposal_id": proposal.proposal_id,
                        "approved": False,
                        "success": False,
                        "reward": -0.1,
                        "details": "quorum_not_reached",
                    },
                )

        if not proposals or approved_count == 0:
            latest_metrics = self.simulator.step(events_left)

        report = CycleReport(
            step=latest_metrics.step,
            proposals=len(proposals),
            approved=approved_count,
            action_success_rate=0.0 if approved_count == 0 else success_count / approved_count,
            decision_latency_ms=0.0 if not decision_latencies else mean(decision_latencies),
            consensus_latency_ms=0.0 if not consensus_latencies else mean(consensus_latencies),
            governance_overhead=governance_overhead,
            metrics=latest_metrics,
        )

        self.observability.record_cycle(report)
        self.observability.record_trust(step=report.step, trust_scores=self.ledger.get_all_trust())
        governance_audit = self.ledger.audit_consistency()
        if not governance_audit["ok"]:
            self.observability.record_event("governance_audit_failure", governance_audit)
        self.observability.write_state(self.get_state())
        return report

    def run(
        self,
        steps: int,
        event_schedule: dict[int, list[dict[str, Any]]] | None = None,
    ) -> list[CycleReport]:
        reports: list[CycleReport] = []
        schedule = event_schedule or {}
        for step_idx in range(1, steps + 1):
            reports.append(self.run_cycle(external_events=schedule.get(step_idx, [])))
        self._write_run_artifacts(reports, run_label="local_run")
        return reports

    def _build_run_summary(self, reports: list[CycleReport], run_label: str) -> dict[str, Any]:
        if not reports:
            return {
                "run_label": run_label,
                "baseline_mode": self.config.baseline_mode,
                "seed": self.config.seed,
                "cycles": 0,
            }

        total_approved = sum(report.approved for report in reports)
        total_proposals = sum(report.proposals for report in reports)
        weighted_success = sum(report.action_success_rate * report.approved for report in reports)
        overall_success_rate = 0.0 if total_approved == 0 else weighted_success / total_approved

        return {
            "run_label": run_label,
            "baseline_mode": self.config.baseline_mode,
            "seed": self.config.seed,
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
            "trust_scores_final": self.ledger.get_all_trust(),
            "rl_reward_trends": {
                agent.agent_id: agent.rl_engine.average_reward() for agent in self.agents
            },
            "latest_metrics": reports[-1].metrics.model_dump(),
        }

    def _write_run_artifacts(self, reports: list[CycleReport], run_label: str) -> None:
        output_dir = Path(self.config.paths.logs_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        cycle_reports = [report.model_dump() for report in reports]
        (output_dir / "cycle_reports.json").write_text(
            json.dumps(cycle_reports, indent=2),
            encoding="utf-8",
        )
        summary = self._build_run_summary(reports, run_label=run_label)
        (output_dir / "summary.json").write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )
