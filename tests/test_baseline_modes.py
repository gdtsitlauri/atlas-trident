from pathlib import Path

from atlas.orchestrator import AtlasOrchestrator


def test_rule_based_baseline_runs_and_sets_state(tmp_path) -> None:
    logs_dir = tmp_path / "rule_based"
    orchestrator = AtlasOrchestrator(
        config_path="config/default.toml",
        logs_dir=str(logs_dir),
        baseline_mode="rule_based_policy",
        seed=12,
    )

    reports = orchestrator.run(steps=2)
    assert len(reports) == 2
    assert orchestrator.get_state()["baseline_mode"] == "rule_based_policy"
    assert (Path(logs_dir) / "decision_traces.jsonl").exists()


def test_trident_no_trust_keeps_agent_trust_static(tmp_path) -> None:
    logs_dir = tmp_path / "no_trust"
    orchestrator = AtlasOrchestrator(
        config_path="config/default.toml",
        logs_dir=str(logs_dir),
        baseline_mode="trident_no_trust",
        seed=21,
    )

    orchestrator.run(steps=3)
    trust = orchestrator.ledger.get_all_trust()
    assert trust["agent-1"] == 0.5
    assert trust["agent-2"] == 0.5
    assert trust["agent-3"] == 0.5


def test_trident_no_rl_disables_learning_updates(tmp_path) -> None:
    logs_dir = tmp_path / "no_rl"
    orchestrator = AtlasOrchestrator(
        config_path="config/default.toml",
        logs_dir=str(logs_dir),
        baseline_mode="trident_no_rl",
        seed=7,
    )

    orchestrator.run(steps=2)
    for agent in orchestrator.agents:
        assert len(agent.rl_engine.reward_history) == 0
        assert agent.rl_engine.average_reward() == 0.0


def test_full_trident_updates_trust_scores(tmp_path) -> None:
    logs_dir = tmp_path / "full_trident"
    orchestrator = AtlasOrchestrator(
        config_path="config/default.toml",
        logs_dir=str(logs_dir),
        baseline_mode="full_trident",
        seed=42,
    )

    orchestrator.run(steps=2)
    trust = orchestrator.ledger.get_all_trust()
    assert any(trust.get(agent_id) != 0.5 for agent_id in ["agent-1", "agent-2", "agent-3"])
