from atlas.governance_chain.ledger import PermissionedLedger
from atlas.types import ActionScoreBreakdown, AllowedAction, CandidateAction, Proposal, Vote


def test_ledger_consistency_audit_passes_for_valid_flow(tmp_path) -> None:
    db_path = tmp_path / "audit_pass.db"
    ledger = PermissionedLedger(str(db_path), members=["gov-1", "gov-2", "gov-3"])

    proposal = Proposal(
        proposal_id="proposal-ok",
        agent_id="agent-1",
        governance_id="gov-1",
        action=CandidateAction(action=AllowedAction.REBALANCE_RESOURCES),
        score_breakdown=ActionScoreBreakdown(
            twin_sim_gain=0.5,
            rl_value=0.2,
            sla_improvement=0.3,
            risk=0.1,
            cost=0.1,
            trust=0.5,
        ),
        composite_score=0.7,
        rationale="valid",
        created_at="2026-04-07T00:00:00+00:00",
    )
    ledger.submit_proposal(proposal)
    ledger.cast_vote(
        Vote(
            proposal_id=proposal.proposal_id,
            voter_id="gov-1",
            approve=True,
            confidence=0.9,
            reason="ok",
            created_at="2026-04-07T00:00:01+00:00",
        )
    )
    ledger.cast_vote(
        Vote(
            proposal_id=proposal.proposal_id,
            voter_id="gov-2",
            approve=True,
            confidence=0.8,
            reason="ok",
            created_at="2026-04-07T00:00:02+00:00",
        )
    )
    ledger.finalize(proposal.proposal_id, consensus_latency_ms=4.0)

    audit = ledger.audit_consistency()
    assert audit["ok"]


def test_ledger_consistency_detects_orphan_vote(tmp_path) -> None:
    db_path = tmp_path / "audit_fail.db"
    ledger = PermissionedLedger(str(db_path), members=["gov-1", "gov-2", "gov-3"])

    with ledger._connect() as conn:  # noqa: SLF001
        conn.execute(
            """
            INSERT INTO votes(proposal_id, voter_id, approve, confidence, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("missing-proposal", "gov-1", 1, 0.7, "manual", "2026-04-07T00:00:00+00:00"),
        )

    audit = ledger.audit_consistency()
    assert not audit["ok"]
    assert "orphan_votes" in audit["issues"]
