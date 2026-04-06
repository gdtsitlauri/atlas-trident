from atlas.config import AtlasConfig
from atlas.llm_planner.planner import build_planner


def test_mock_planner_outputs_only_allowed_schema() -> None:
    config = AtlasConfig()
    planner = build_planner("mock", config)
    snapshot = __import__("atlas.cloud_simulator.simulator", fromlist=["CloudSimulator"]).CloudSimulator(config).get_twin_snapshot("twin-1")

    candidates = planner.plan(snapshot, max_candidates=6)
    assert candidates
    for candidate in candidates:
        assert isinstance(candidate.action.value, str)
