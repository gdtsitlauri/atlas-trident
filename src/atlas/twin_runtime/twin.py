from __future__ import annotations

from typing import Any

from atlas.cloud_simulator.simulator import CloudSimulator
from atlas.types import CandidateAction, TwinSnapshot
from atlas.utils.time_utils import utc_now_iso


class DigitalTwin:
    """Digital twin for one logical node/service participant."""

    def __init__(self, twin_id: str, simulator: CloudSimulator, what_if_horizon: int = 3) -> None:
        self.twin_id = twin_id
        self.simulator = simulator
        self.what_if_horizon = max(1, what_if_horizon)
        self.snapshot = simulator.get_twin_snapshot(twin_id)
        self.history: list[dict[str, Any]] = []

    def sync(self) -> TwinSnapshot:
        self.snapshot = self.simulator.get_twin_snapshot(self.twin_id)
        self.history.append(
            {
                "ts": utc_now_iso(),
                "kind": "snapshot",
                "step": self.snapshot.step,
                "metrics": self.snapshot.metrics.model_dump(),
            }
        )
        if len(self.history) > 512:
            self.history = self.history[-512:]
        return self.snapshot

    def get_snapshot(self) -> TwinSnapshot:
        return self.snapshot

    def evaluate_action(self, action: CandidateAction) -> tuple[float, dict[str, float]]:
        baseline_utility = self.simulator.rollout_utility(self.what_if_horizon)
        action_utility = self.simulator.rollout_utility(self.what_if_horizon, action=action)
        sla_improvement = self.simulator.estimate_sla_improvement(action, horizon=max(1, self.what_if_horizon // 2))
        gain = action_utility - baseline_utility
        return gain, {
            "baseline_utility": baseline_utility,
            "action_utility": action_utility,
            "sla_improvement": sla_improvement,
        }

    def estimate_sla_improvement(self, action: CandidateAction) -> float:
        return self.simulator.estimate_sla_improvement(action, horizon=max(1, self.what_if_horizon // 2))

    def record_outcome(self, outcome: dict[str, Any]) -> None:
        self.history.append({"ts": utc_now_iso(), "kind": "outcome", **outcome})
        if len(self.history) > 512:
            self.history = self.history[-512:]
