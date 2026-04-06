from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AllowedAction(str, Enum):
    SCALE_UP_SERVICE = "scale_up_service"
    SCALE_DOWN_SERVICE = "scale_down_service"
    MIGRATE_WORKLOAD = "migrate_workload"
    RESTART_SERVICE = "restart_service"
    ISOLATE_NODE = "isolate_node"
    FAILOVER_TO_REPLICA = "failover_to_replica"
    RATE_LIMIT_SERVICE = "rate_limit_service"
    REBALANCE_RESOURCES = "rebalance_resources"
    DEFER_LOW_PRIORITY_JOBS = "defer_low_priority_jobs"


class CandidateAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: AllowedAction
    target_service: str | None = None
    target_node: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class CandidatePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[CandidateAction] = Field(min_length=1, max_length=10)


class SLAMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: int
    avg_latency_ms: float
    sla_violations: int
    availability: float
    resource_utilization: float
    cost_proxy: float
    utility: float
    recovery_time_ms: float


class TwinSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    twin_id: str
    step: int
    nodes: dict[str, dict[str, Any]]
    services: dict[str, dict[str, Any]]
    metrics: SLAMetrics


class ActionScoreBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    twin_sim_gain: float
    rl_value: float
    sla_improvement: float
    risk: float
    cost: float
    trust: float


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    agent_id: str
    governance_id: str
    action: CandidateAction
    score_breakdown: ActionScoreBreakdown
    composite_score: float
    rationale: str
    created_at: str


class Vote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    voter_id: str
    approve: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    created_at: str


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    approved: bool
    quorum_required: int
    yes_votes: int
    total_votes: int
    consensus_latency_ms: float
    decided_at: str


class ExecutionOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    success: bool
    details: str
    reward: float
    decision_latency_ms: float
    executed_at: str


class DecisionTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: int
    agent_id: str
    proposal_id: str
    action: str
    composite_score: float
    breakdown: ActionScoreBreakdown
    accepted: bool
    reason: str


class CycleReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: int
    proposals: int
    approved: int
    action_success_rate: float
    decision_latency_ms: float
    consensus_latency_ms: float
    governance_overhead: int
    metrics: SLAMetrics
