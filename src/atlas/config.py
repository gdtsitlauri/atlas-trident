from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from atlas.baselines import FULL_TRIDENT, normalize_baseline_mode

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "default.toml"


@dataclass(slots=True)
class TridentWeights:
    alpha: float = 0.34
    beta: float = 0.23
    gamma: float = 0.22
    lambda_penalty: float = 0.12
    mu: float = 0.05
    nu: float = 0.18


@dataclass(slots=True)
class RLConfig:
    learning_rate: float = 0.15
    discount_factor: float = 0.92
    epsilon: float = 0.10
    replay_size: int = 512


@dataclass(slots=True)
class PolicyConfig:
    max_service_instances: int = 5
    max_node_cpu_utilization: float = 0.95
    max_node_memory_utilization: float = 0.95
    min_healthy_nodes: int = 2


@dataclass(slots=True)
class SLAConfig:
    latency_target_ms: float = 180.0
    availability_target: float = 0.99


@dataclass(slots=True)
class LLMConfig:
    mode: str = "mock"
    ollama_url: str = "http://localhost:11434/api/generate"
    ollama_model: str = "llama3.1:8b-instruct-q4_0"
    openai_url: str = "http://localhost:8001/v1/chat/completions"
    openai_model: str = "gpt-4o-mini"
    request_timeout_sec: float = 15.0


@dataclass(slots=True)
class PathConfig:
    logs_dir: str = "logs/latest"
    ledger_db: str = "logs/latest/atlas_ledger.db"


@dataclass(slots=True)
class AtlasConfig:
    seed: int = 42
    deterministic_mode: bool = True
    twin_nodes: int = 3
    governance_nodes: int = 3
    episode_steps: int = 20
    what_if_horizon: int = 3
    max_candidates: int = 6
    planner_mode: str = "mock"
    baseline_mode: str = FULL_TRIDENT
    trident: TridentWeights = field(default_factory=TridentWeights)
    rl: RLConfig = field(default_factory=RLConfig)
    policy: PolicyConfig = field(default_factory=PolicyConfig)
    sla: SLAConfig = field(default_factory=SLAConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    paths: PathConfig = field(default_factory=PathConfig)

    @staticmethod
    def from_toml(path: str | Path | None = None) -> "AtlasConfig":
        config_path = Path(path) if path else DEFAULT_CONFIG_PATH
        if not config_path.exists():
            return AtlasConfig()

        raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
        system = raw.get("system", {})
        return AtlasConfig(
            seed=system.get("seed", 42),
            deterministic_mode=bool(system.get("deterministic_mode", True)),
            twin_nodes=system.get("twin_nodes", 3),
            governance_nodes=system.get("governance_nodes", 3),
            episode_steps=system.get("episode_steps", 20),
            what_if_horizon=system.get("what_if_horizon", 3),
            max_candidates=system.get("max_candidates", 6),
            planner_mode=system.get("planner_mode", "mock"),
            baseline_mode=normalize_baseline_mode(system.get("baseline_mode", FULL_TRIDENT)),
            trident=TridentWeights(**raw.get("trident", {})),
            rl=RLConfig(**raw.get("rl", {})),
            policy=PolicyConfig(**raw.get("policy", {})),
            sla=SLAConfig(**raw.get("sla", {})),
            llm=LLMConfig(**raw.get("llm", {})),
            paths=PathConfig(**raw.get("paths", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
