from __future__ import annotations

from collections import deque
from random import Random

from atlas.config import RLConfig
from atlas.types import AllowedAction, TwinSnapshot


class QLearningEngine:
    """Tabular Q-learning for discrete action optimization in constrained environments."""

    def __init__(self, config: RLConfig, seed: int = 42) -> None:
        self.config = config
        self.q_table: dict[str, dict[str, float]] = {}
        self.replay_buffer: deque[tuple[str, str, float, str, bool]] = deque(maxlen=config.replay_size)
        self.random = Random(seed)
        self.reward_history: deque[float] = deque(maxlen=256)

    def _state_key(self, snapshot: TwinSnapshot) -> str:
        metrics = snapshot.metrics
        latency_bucket = int(min(9, metrics.avg_latency_ms // 40))
        violation_bucket = int(min(5, metrics.sla_violations))
        utilization_bucket = int(min(9, metrics.resource_utilization * 10))
        availability_bucket = int(min(9, (1.0 - metrics.availability) * 10))
        return f"{latency_bucket}:{violation_bucket}:{utilization_bucket}:{availability_bucket}"

    def _get_q_values(self, state_key: str) -> dict[str, float]:
        if state_key not in self.q_table:
            self.q_table[state_key] = {action.value: 0.0 for action in AllowedAction}
        return self.q_table[state_key]

    def value(self, snapshot: TwinSnapshot, action: AllowedAction) -> float:
        state = self._state_key(snapshot)
        return self._get_q_values(state).get(action.value, 0.0)

    def best_action_value(self, snapshot: TwinSnapshot) -> float:
        state = self._state_key(snapshot)
        return max(self._get_q_values(state).values())

    def observe(
        self,
        snapshot: TwinSnapshot,
        action: AllowedAction,
        reward: float,
        next_snapshot: TwinSnapshot,
        done: bool = False,
    ) -> None:
        state_key = self._state_key(snapshot)
        next_key = self._state_key(next_snapshot)
        self.replay_buffer.append((state_key, action.value, reward, next_key, done))
        self.reward_history.append(reward)
        self._update_transition(state_key, action.value, reward, next_key, done)

    def _update_transition(
        self,
        state_key: str,
        action: str,
        reward: float,
        next_key: str,
        done: bool,
    ) -> None:
        q_values = self._get_q_values(state_key)
        next_q_values = self._get_q_values(next_key)
        max_next = 0.0 if done else max(next_q_values.values())
        td_target = reward + self.config.discount_factor * max_next
        td_error = td_target - q_values[action]
        q_values[action] += self.config.learning_rate * td_error

    def train_from_replay(self, batch_size: int = 16, epochs: int = 1) -> None:
        if not self.replay_buffer:
            return
        batch_size = max(1, min(batch_size, len(self.replay_buffer)))
        for _ in range(max(1, epochs)):
            sampled = self.random.sample(list(self.replay_buffer), batch_size)
            for state_key, action, reward, next_key, done in sampled:
                self._update_transition(state_key, action, reward, next_key, done)

    def average_reward(self) -> float:
        if not self.reward_history:
            return 0.0
        return sum(self.reward_history) / len(self.reward_history)
