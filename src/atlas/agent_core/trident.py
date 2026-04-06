from __future__ import annotations

from atlas.config import TridentWeights


class TridentScorer:
    """TRIDENT composite scoring algorithm implementation."""

    def __init__(self, weights: TridentWeights) -> None:
        self.weights = weights

    def score(
        self,
        twin_sim_gain: float,
        rl_value: float,
        sla_improvement: float,
        risk: float,
        cost: float,
        trust: float,
    ) -> float:
        return (
            self.weights.alpha * twin_sim_gain
            + self.weights.beta * rl_value
            + self.weights.gamma * sla_improvement
            - self.weights.lambda_penalty * risk
            - self.weights.mu * cost
            + self.weights.nu * trust
        )
