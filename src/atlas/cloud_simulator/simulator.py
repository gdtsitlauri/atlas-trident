from __future__ import annotations

import random
from copy import deepcopy
from dataclasses import asdict, dataclass
from statistics import mean
from typing import Any

from atlas.config import AtlasConfig
from atlas.types import AllowedAction, CandidateAction, SLAMetrics, TwinSnapshot


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(slots=True)
class NodeState:
    node_id: str
    cpu_capacity: float = 100.0
    memory_capacity: float = 100.0
    cpu_used: float = 0.0
    memory_used: float = 0.0
    healthy: bool = True
    isolated: bool = False
    latency_penalty_ms: float = 0.0
    recovery_timer: int = 0


@dataclass(slots=True)
class ServiceState:
    service_id: str
    node_id: str
    replica_node: str
    priority: int = 1
    instances: int = 1
    request_rate: float = 60.0
    base_latency_ms: float = 30.0
    latency_ms: float = 30.0
    error_rate: float = 0.01


class CloudSimulator:
    """Lightweight cloud simulator for services, nodes, workloads, and faults."""

    def __init__(self, config: AtlasConfig) -> None:
        self.config = config
        self.random = random.Random(config.seed)
        self.step_count = 0
        self.pending_action_cost = 0.0
        self.event_history: list[dict[str, Any]] = []
        self.nodes: dict[str, NodeState] = {}
        self.services: dict[str, ServiceState] = {}
        self.last_metrics = SLAMetrics(
            step=0,
            avg_latency_ms=0.0,
            sla_violations=0,
            availability=1.0,
            resource_utilization=0.0,
            cost_proxy=0.0,
            utility=0.0,
            recovery_time_ms=0.0,
        )
        self.reset()

    def reset(self) -> None:
        self.step_count = 0
        self.pending_action_cost = 0.0
        self.event_history.clear()

        self.nodes = {
            f"node-{i+1}": NodeState(node_id=f"node-{i+1}")
            for i in range(self.config.twin_nodes)
        }

        self.services = {}
        for i in range(self.config.twin_nodes):
            node_id = f"node-{i+1}"
            replica_index = (i + 1) % self.config.twin_nodes
            replica_node = f"node-{replica_index+1}"
            self.services[f"svc-{i+1}"] = ServiceState(
                service_id=f"svc-{i+1}",
                node_id=node_id,
                replica_node=replica_node,
                priority=1 if i == 0 else 2,
                instances=1,
                request_rate=65 + i * 15,
                base_latency_ms=28 + i * 4,
                latency_ms=30 + i * 5,
            )

        self.last_metrics = self._compute_metrics()

    def clone(self) -> "CloudSimulator":
        cloned = CloudSimulator(self.config)
        cloned.random.setstate(self.random.getstate())
        cloned.step_count = self.step_count
        cloned.pending_action_cost = self.pending_action_cost
        cloned.event_history = deepcopy(self.event_history)
        cloned.nodes = deepcopy(self.nodes)
        cloned.services = deepcopy(self.services)
        cloned.last_metrics = self.last_metrics.model_copy(deep=True)
        return cloned

    def _compute_metrics(self) -> SLAMetrics:
        if not self.services:
            return SLAMetrics(
                step=self.step_count,
                avg_latency_ms=0.0,
                sla_violations=0,
                availability=1.0,
                resource_utilization=0.0,
                cost_proxy=0.0,
                utility=0.0,
                recovery_time_ms=0.0,
            )

        avg_latency = mean(service.latency_ms for service in self.services.values())
        availability = mean(1.0 - service.error_rate for service in self.services.values())
        sla_violations = sum(
            1
            for service in self.services.values()
            if service.latency_ms > self.config.sla.latency_target_ms
            or (1.0 - service.error_rate) < self.config.sla.availability_target
        )
        resource_utilization = mean(
            _clamp(node.cpu_used / max(node.cpu_capacity, 1.0), 0.0, 1.5)
            for node in self.nodes.values()
        )
        isolated_nodes = sum(1 for node in self.nodes.values() if node.isolated)
        cost_proxy = (
            0.50 * sum(service.instances for service in self.services.values())
            + self.pending_action_cost
            + 0.25 * isolated_nodes
        )
        unhealthy_nodes = sum(1 for node in self.nodes.values() if not node.healthy)
        recovery_time_ms = float(unhealthy_nodes * 120)

        utility = (
            2.8 * availability
            - 0.013 * avg_latency
            - 1.30 * sla_violations
            - 0.65 * cost_proxy
        )

        return SLAMetrics(
            step=self.step_count,
            avg_latency_ms=round(avg_latency, 3),
            sla_violations=sla_violations,
            availability=round(_clamp(availability, 0.0, 1.0), 5),
            resource_utilization=round(_clamp(resource_utilization, 0.0, 1.5), 5),
            cost_proxy=round(cost_proxy, 5),
            utility=round(utility, 5),
            recovery_time_ms=recovery_time_ms,
        )

    def _pick_least_loaded_node(self, exclude: str | None = None) -> str | None:
        load_pairs: list[tuple[float, str]] = []
        for node_id, node in self.nodes.items():
            if node_id == exclude or not node.healthy or node.isolated:
                continue
            load = node.cpu_used / max(node.cpu_capacity, 1.0)
            load_pairs.append((load, node_id))
        if not load_pairs:
            return None
        load_pairs.sort(key=lambda item: item[0])
        return load_pairs[0][1]

    def _pick_hottest_service(self) -> ServiceState:
        return max(self.services.values(), key=lambda svc: svc.latency_ms + svc.request_rate / 10)

    def apply_action(self, action: CandidateAction) -> tuple[bool, str]:
        if action.action == AllowedAction.SCALE_UP_SERVICE:
            service = self.services.get(action.target_service or "") or self._pick_hottest_service()
            if service.instances >= self.config.policy.max_service_instances:
                return False, "service_already_at_max_instances"
            service.instances += 1
            self.pending_action_cost += 0.35
            return True, f"scaled_up_{service.service_id}"

        if action.action == AllowedAction.SCALE_DOWN_SERVICE:
            service = self.services.get(action.target_service or "") or self._pick_hottest_service()
            if service.instances <= 1:
                return False, "service_already_at_min_instances"
            service.instances -= 1
            self.pending_action_cost += 0.10
            return True, f"scaled_down_{service.service_id}"

        if action.action == AllowedAction.MIGRATE_WORKLOAD:
            service = self.services.get(action.target_service or "")
            if not service:
                return False, "unknown_service"
            destination = action.target_node or self._pick_least_loaded_node(exclude=service.node_id)
            if not destination:
                return False, "no_healthy_destination_node"
            service.node_id = destination
            self.pending_action_cost += 0.25
            return True, f"migrated_{service.service_id}_to_{destination}"

        if action.action == AllowedAction.RESTART_SERVICE:
            service = self.services.get(action.target_service or "")
            if not service:
                return False, "unknown_service"
            service.error_rate = _clamp(service.error_rate - 0.25, 0.0, 1.0)
            service.request_rate *= 0.96
            self.pending_action_cost += 0.15
            return True, f"restarted_{service.service_id}"

        if action.action == AllowedAction.ISOLATE_NODE:
            node = self.nodes.get(action.target_node or "")
            if not node:
                return False, "unknown_node"
            node.isolated = True
            node.healthy = False
            node.recovery_timer = 3
            self.pending_action_cost += 0.30
            return True, f"isolated_{node.node_id}"

        if action.action == AllowedAction.FAILOVER_TO_REPLICA:
            service = self.services.get(action.target_service or "")
            if not service:
                return False, "unknown_service"
            replica = self.nodes.get(service.replica_node)
            if not replica or not replica.healthy or replica.isolated:
                return False, "replica_unavailable"
            service.node_id = service.replica_node
            self.pending_action_cost += 0.22
            return True, f"failed_over_{service.service_id}_to_{service.replica_node}"

        if action.action == AllowedAction.RATE_LIMIT_SERVICE:
            service = self.services.get(action.target_service or "")
            if not service:
                return False, "unknown_service"
            factor = float(action.params.get("factor", 0.85))
            factor = _clamp(factor, 0.40, 1.0)
            service.request_rate *= factor
            self.pending_action_cost += 0.05
            return True, f"rate_limited_{service.service_id}"

        if action.action == AllowedAction.REBALANCE_RESOURCES:
            hottest_service = self._pick_hottest_service()
            destination = self._pick_least_loaded_node(exclude=hottest_service.node_id)
            if not destination:
                return False, "rebalance_failed_no_destination"
            hottest_service.node_id = destination
            self.pending_action_cost += 0.20
            return True, f"rebalanced_{hottest_service.service_id}_to_{destination}"

        if action.action == AllowedAction.DEFER_LOW_PRIORITY_JOBS:
            factor = float(action.params.get("factor", 0.78))
            for service in self.services.values():
                if service.priority >= 2:
                    service.request_rate *= factor
            self.pending_action_cost += 0.03
            return True, "deferred_low_priority_jobs"

        return False, "unknown_action"

    def inject_event(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("type", "")).lower()
        if event_type == "overload":
            service_id = str(event.get("service_id", "svc-1"))
            factor = float(event.get("factor", 1.6))
            service = self.services.get(service_id)
            if service:
                service.request_rate *= max(1.0, factor)

        elif event_type == "node_failure":
            node_id = str(event.get("node_id", "node-1"))
            duration = int(event.get("duration", 3))
            node = self.nodes.get(node_id)
            if node:
                node.healthy = False
                node.recovery_timer = max(duration, 1)

        elif event_type == "latency_spike":
            node_id = str(event.get("node_id", "node-1"))
            extra_ms = float(event.get("extra_ms", 120))
            node = self.nodes.get(node_id)
            if node:
                node.latency_penalty_ms += max(extra_ms, 10.0)

        elif event_type == "resource_scarcity":
            node_id = str(event.get("node_id", "node-1"))
            ratio = float(event.get("ratio", 0.85))
            ratio = _clamp(ratio, 0.4, 1.0)
            node = self.nodes.get(node_id)
            if node:
                node.cpu_capacity *= ratio
                node.memory_capacity *= ratio

        elif event_type == "recover_node":
            node_id = str(event.get("node_id", "node-1"))
            node = self.nodes.get(node_id)
            if node:
                node.healthy = True
                node.isolated = False
                node.recovery_timer = 0

        self.event_history.append({"step": self.step_count, "event": event})

    def step(self, external_events: list[dict[str, Any]] | None = None) -> SLAMetrics:
        self.step_count += 1
        for node in self.nodes.values():
            node.cpu_used = 0.0
            node.memory_used = 0.0

            if node.recovery_timer > 0:
                node.recovery_timer -= 1
                if node.recovery_timer == 0 and not node.isolated:
                    node.healthy = True

            node.latency_penalty_ms *= 0.90

        for event in external_events or []:
            self.inject_event(event)

        for service in self.services.values():
            node = self.nodes[service.node_id]

            demand_cpu = (service.request_rate * 0.90) / max(service.instances, 1)
            demand_mem = (service.request_rate * 0.50) / max(service.instances, 1)
            node.cpu_used += demand_cpu
            node.memory_used += demand_mem

            utilization = node.cpu_used / max(node.cpu_capacity, 1.0)
            base_latency = service.base_latency_ms + node.latency_penalty_ms
            jitter = self.random.uniform(-4.0, 4.0)
            service.latency_ms = max(5.0, base_latency + 175 * utilization + jitter)

            error_rate = 0.01 + max(0.0, utilization - 0.80) * 0.60
            if not node.healthy:
                error_rate += 0.45
            if node.isolated:
                error_rate += 0.50
            service.error_rate = _clamp(error_rate, 0.0, 1.0)

            service.request_rate = _clamp(
                service.request_rate * self.random.uniform(0.96, 1.04),
                20.0,
                260.0,
            )

        self.last_metrics = self._compute_metrics()
        self.pending_action_cost = 0.0
        return self.last_metrics

    def rollout_utility(self, horizon: int, action: CandidateAction | None = None) -> float:
        horizon = max(1, horizon)
        shadow = self.clone()
        if action:
            shadow.apply_action(action)
        utility_values: list[float] = []
        for _ in range(horizon):
            metrics = shadow.step()
            utility_values.append(metrics.utility)
        return mean(utility_values)

    def estimate_sla_improvement(self, action: CandidateAction, horizon: int = 2) -> float:
        horizon = max(1, horizon)
        baseline = self.clone()
        candidate = self.clone()
        candidate.apply_action(action)

        baseline_violations = 0
        candidate_violations = 0
        for _ in range(horizon):
            baseline_violations += baseline.step().sla_violations
            candidate_violations += candidate.step().sla_violations

        return float(baseline_violations - candidate_violations)

    def export_state(self) -> dict[str, Any]:
        return {
            "step": self.step_count,
            "metrics": self.last_metrics.model_dump(),
            "nodes": {node_id: asdict(node) for node_id, node in self.nodes.items()},
            "services": {svc_id: asdict(service) for svc_id, service in self.services.items()},
        }

    def get_twin_snapshot(self, twin_id: str) -> TwinSnapshot:
        exported = self.export_state()
        return TwinSnapshot(
            twin_id=twin_id,
            step=exported["step"],
            nodes=exported["nodes"],
            services=exported["services"],
            metrics=self.last_metrics,
        )
