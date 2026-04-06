from atlas.cloud_simulator.simulator import CloudSimulator
from atlas.config import AtlasConfig
from atlas.policy_guard.guard import PolicyGuard
from atlas.types import AllowedAction, CandidateAction


def test_policy_guard_rejects_isolation_when_healthy_nodes_too_low() -> None:
    config = AtlasConfig()
    simulator = CloudSimulator(config)
    snapshot = simulator.get_twin_snapshot("twin-1")
    snapshot.nodes["node-3"]["healthy"] = False

    guard = PolicyGuard(config.policy, config.sla)
    result = guard.evaluate(
        CandidateAction(action=AllowedAction.ISOLATE_NODE, target_node="node-1"),
        snapshot,
    )

    assert not result.allowed
    assert "insufficient_healthy_nodes_for_isolation" in result.reasons


def test_policy_guard_allows_scale_up_for_valid_service() -> None:
    config = AtlasConfig()
    simulator = CloudSimulator(config)
    snapshot = simulator.get_twin_snapshot("twin-1")

    guard = PolicyGuard(config.policy, config.sla)
    result = guard.evaluate(
        CandidateAction(action=AllowedAction.SCALE_UP_SERVICE, target_service="svc-1"),
        snapshot,
    )
    assert result.allowed


def test_policy_guard_rejects_unsafe_rate_limit_factor() -> None:
    config = AtlasConfig()
    simulator = CloudSimulator(config)
    snapshot = simulator.get_twin_snapshot("twin-1")

    guard = PolicyGuard(config.policy, config.sla)
    result = guard.evaluate(
        CandidateAction(
            action=AllowedAction.RATE_LIMIT_SERVICE,
            target_service="svc-1",
            params={"factor": 1.4},
        ),
        snapshot,
    )
    assert not result.allowed
    assert "rate_limit_factor_out_of_bounds" in result.reasons
