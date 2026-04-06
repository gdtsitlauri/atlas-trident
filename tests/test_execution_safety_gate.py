from atlas.orchestrator import AtlasOrchestrator
from atlas.types import ActionScoreBreakdown, AllowedAction, CandidateAction, Proposal, Vote


def test_pre_execution_policy_gate_blocks_unsafe_action(tmp_path) -> None:
    logs_dir = tmp_path / "safety_gate"
    orchestrator = AtlasOrchestrator(
        config_path="config/default.toml",
        logs_dir=str(logs_dir),
        baseline_mode="full_trident",
        seed=42,
    )

    unsafe_proposal = Proposal(
        proposal_id="forced-unsafe-proposal",
        agent_id="agent-1",
        governance_id="gov-1",
        action=CandidateAction(action=AllowedAction.MIGRATE_WORKLOAD, target_service="svc-1"),
        score_breakdown=ActionScoreBreakdown(
            twin_sim_gain=1.0,
            rl_value=0.5,
            sla_improvement=0.2,
            risk=0.1,
            cost=0.1,
            trust=0.5,
        ),
        composite_score=9.0,
        rationale="forced proposal for safety gate test",
        created_at="2026-04-07T00:00:00+00:00",
    )

    def forced_propose(*_args, **_kwargs):
        return unsafe_proposal, []

    def make_forced_approve(voter_id: str):
        def forced_approve(proposal: Proposal):
            return Vote(
                proposal_id=proposal.proposal_id,
                voter_id=voter_id,
                approve=True,
                confidence=0.99,
                reason="forced-approve",
                created_at="2026-04-07T00:00:01+00:00",
            )

        return forced_approve

    orchestrator.agents[0].propose = forced_propose
    for agent in orchestrator.agents:
        agent.validate_proposal = make_forced_approve(agent.governance_id)

    orchestrator.run(steps=1)
    executions = orchestrator.ledger.list_recent("executions", limit=5)
    assert executions
    assert any(str(item.get("details", "")).startswith("blocked_pre_execution") for item in executions)
