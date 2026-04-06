from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from atlas.config import PolicyConfig, SLAConfig
from atlas.types import AllowedAction, CandidateAction, TwinSnapshot


class GuardResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    reasons: list[str] = Field(default_factory=list)
    risk_score: float = 0.0
    cost_estimate: float = 0.0


class PolicyGuard:
    """Hard safety constraints and policy validation for candidate actions."""

    _base_risk: dict[AllowedAction, float] = {
        AllowedAction.SCALE_UP_SERVICE: 0.20,
        AllowedAction.SCALE_DOWN_SERVICE: 0.38,
        AllowedAction.MIGRATE_WORKLOAD: 0.30,
        AllowedAction.RESTART_SERVICE: 0.24,
        AllowedAction.ISOLATE_NODE: 0.75,
        AllowedAction.FAILOVER_TO_REPLICA: 0.40,
        AllowedAction.RATE_LIMIT_SERVICE: 0.30,
        AllowedAction.REBALANCE_RESOURCES: 0.20,
        AllowedAction.DEFER_LOW_PRIORITY_JOBS: 0.18,
    }

    _base_cost: dict[AllowedAction, float] = {
        AllowedAction.SCALE_UP_SERVICE: 0.45,
        AllowedAction.SCALE_DOWN_SERVICE: 0.12,
        AllowedAction.MIGRATE_WORKLOAD: 0.25,
        AllowedAction.RESTART_SERVICE: 0.20,
        AllowedAction.ISOLATE_NODE: 0.55,
        AllowedAction.FAILOVER_TO_REPLICA: 0.28,
        AllowedAction.RATE_LIMIT_SERVICE: 0.08,
        AllowedAction.REBALANCE_RESOURCES: 0.18,
        AllowedAction.DEFER_LOW_PRIORITY_JOBS: 0.06,
    }

    def __init__(self, policy: PolicyConfig, sla: SLAConfig) -> None:
        self.policy = policy
        self.sla = sla

    def evaluate(self, action: CandidateAction, snapshot: TwinSnapshot) -> GuardResult:
        reasons: list[str] = []
        risk = self._base_risk[action.action]
        cost = self._base_cost[action.action]

        services = snapshot.services
        nodes = snapshot.nodes
        metrics = snapshot.metrics

        healthy_nodes = sum(1 for node in nodes.values() if node.get("healthy", True) and not node.get("isolated", False))

        if action.action in {
            AllowedAction.SCALE_UP_SERVICE,
            AllowedAction.SCALE_DOWN_SERVICE,
            AllowedAction.RESTART_SERVICE,
            AllowedAction.FAILOVER_TO_REPLICA,
            AllowedAction.RATE_LIMIT_SERVICE,
            AllowedAction.MIGRATE_WORKLOAD,
        }:
            if action.target_service and action.target_service not in services:
                reasons.append("target_service_not_found")

        if action.action in {AllowedAction.ISOLATE_NODE, AllowedAction.MIGRATE_WORKLOAD}:
            if action.target_node and action.target_node not in nodes:
                reasons.append("target_node_not_found")

        if action.action == AllowedAction.SCALE_UP_SERVICE:
            service = services.get(action.target_service or "")
            if service and int(service.get("instances", 1)) >= self.policy.max_service_instances:
                reasons.append("max_instances_reached")
            if metrics.resource_utilization >= self.policy.max_node_cpu_utilization:
                risk += 0.20

        if action.action == AllowedAction.SCALE_DOWN_SERVICE:
            service = services.get(action.target_service or "")
            if service and int(service.get("instances", 1)) <= 1:
                reasons.append("service_at_min_instances")
            if metrics.sla_violations > 0:
                reasons.append("sla_degraded_scale_down_blocked")

        if action.action == AllowedAction.MIGRATE_WORKLOAD:
            service = services.get(action.target_service or "")
            if service:
                destination = action.target_node
                if not destination:
                    reasons.append("missing_target_node")
                elif destination == service.get("node_id"):
                    reasons.append("destination_same_as_source")
                else:
                    destination_node = nodes.get(destination, {})
                    if not destination_node.get("healthy", True) or destination_node.get("isolated", False):
                        reasons.append("destination_node_unhealthy")

        if action.action == AllowedAction.ISOLATE_NODE:
            if healthy_nodes <= self.policy.min_healthy_nodes:
                reasons.append("insufficient_healthy_nodes_for_isolation")

        if action.action == AllowedAction.FAILOVER_TO_REPLICA:
            service = services.get(action.target_service or "")
            if not service:
                reasons.append("service_not_found")
            else:
                replica_id = str(service.get("replica_node", ""))
                replica = nodes.get(replica_id, {})
                if not replica or not replica.get("healthy", True) or replica.get("isolated", False):
                    reasons.append("replica_not_available")

        if action.action == AllowedAction.RATE_LIMIT_SERVICE:
            factor = float(action.params.get("factor", 0.85))
            if factor < 0.4 or factor > 1.0:
                reasons.append("rate_limit_factor_out_of_bounds")
            if metrics.sla_violations == 0 and metrics.resource_utilization < 0.75:
                risk += 0.20

        if action.action == AllowedAction.REBALANCE_RESOURCES:
            cpu_values = [float(node.get("cpu_used", 0.0)) for node in nodes.values()]
            capacity_values = [max(float(node.get("cpu_capacity", 100.0)), 1.0) for node in nodes.values()]
            if cpu_values:
                utilizations = [cpu / cap for cpu, cap in zip(cpu_values, capacity_values, strict=False)]
                if max(utilizations) - min(utilizations) < 0.10:
                    risk += 0.15

        if action.action == AllowedAction.DEFER_LOW_PRIORITY_JOBS:
            has_low_priority = any(int(service.get("priority", 1)) >= 2 for service in services.values())
            if not has_low_priority:
                reasons.append("no_low_priority_jobs_available")

        if metrics.avg_latency_ms > self.sla.latency_target_ms * 1.2:
            risk += 0.15
        if metrics.availability < self.sla.availability_target:
            risk += 0.10

        return GuardResult(
            allowed=not reasons,
            reasons=reasons,
            risk_score=round(min(2.0, risk), 4),
            cost_estimate=round(cost, 4),
        )
