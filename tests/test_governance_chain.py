from atlas.governance_chain.ledger import PermissionedLedger
from atlas.types import ActionScoreBreakdown, AllowedAction, CandidateAction, Proposal, Vote


def test_permissioned_ledger_finalize_with_quorum(tmp_path) -> None:
    db_path = tmp_path / "ledger.db"
    ledger = PermissionedLedger(str(db_path), members=["gov-1", "gov-2", "gov-3"])

    proposal = Proposal(
        proposal_id="prop-1",
        agent_id="agent-1",
        governance_id="gov-1",
        action=CandidateAction(action=AllowedAction.REBALANCE_RESOURCES),
        score_breakdown=ActionScoreBreakdown(
            twin_sim_gain=1.2,
            rl_value=0.8,
            sla_improvement=0.5,
            risk=0.2,
            cost=0.1,
            trust=0.6,
        ),
        composite_score=0.95,
        rationale="test",
        created_at="2026-04-07T00:00:00+00:00",
    )

    ledger.submit_proposal(proposal)
    ledger.cast_vote(
        Vote(
            proposal_id="prop-1",
            voter_id="gov-1",
            approve=True,
            confidence=0.9,
            reason="approve",
            created_at="2026-04-07T00:00:01+00:00",
        )
    )
    ledger.cast_vote(
        Vote(
            proposal_id="prop-1",
            voter_id="gov-2",
            approve=True,
            confidence=0.8,
            reason="approve",
            created_at="2026-04-07T00:00:02+00:00",
        )
    )
    ledger.cast_vote(
        Vote(
            proposal_id="prop-1",
            voter_id="gov-3",
            approve=False,
            confidence=0.7,
            reason="reject",
            created_at="2026-04-07T00:00:03+00:00",
        )
    )

    decision = ledger.finalize("prop-1", consensus_latency_ms=7.4)
    assert decision.approved
    assert decision.yes_votes == 2
    assert decision.quorum_required == 2

    blocks = ledger.list_recent("blocks", limit=20)
    assert len(blocks) >= 5
