from __future__ import annotations

from random import Random
from time import perf_counter
from uuid import uuid4

from atlas.agent_core.trident import TridentScorer
from atlas.baselines import FULL_TRIDENT, behavior_for, normalize_baseline_mode
from atlas.governance_chain.ledger import PermissionedLedger
from atlas.llm_planner.planner import BasePlanner
from atlas.policy_guard.guard import PolicyGuard
from atlas.rl_engine.q_learning import QLearningEngine
from atlas.twin_runtime.twin import DigitalTwin
from atlas.types import ActionScoreBreakdown, CandidateAction, DecisionTrace, Proposal, Vote
from atlas.utils.time_utils import utc_now_iso


class TwinAgent:
    """Autonomous decision-making agent attached to a digital twin."""

    def __init__(
        self,
        agent_id: str,
        governance_id: str,
        twin: DigitalTwin,
        planner: BasePlanner,
        rl_engine: QLearningEngine,
        policy_guard: PolicyGuard,
        ledger: PermissionedLedger,
        trident: TridentScorer,
        baseline_mode: str = FULL_TRIDENT,
        seed: int = 42,
    ) -> None:
        self.agent_id = agent_id
        self.governance_id = governance_id
        self.twin = twin
        self.planner = planner
        self.rl_engine = rl_engine
        self.policy_guard = policy_guard
        self.ledger = ledger
        self.trident = trident
        self.previous_snapshot = twin.get_snapshot()
        self.baseline_mode = normalize_baseline_mode(baseline_mode)
        self.behavior = behavior_for(self.baseline_mode)
        self.random = Random(seed)

    def propose(self, max_candidates: int = 6) -> tuple[Proposal | None, list[DecisionTrace]]:
        snapshot = self.twin.sync()
        proposal_start = perf_counter()
        candidates = self.planner.plan(snapshot, max_candidates=max_candidates)
        trust = self.ledger.get_trust(self.agent_id) if self.behavior.use_trust else 0.0

        scored_proposals: list[Proposal] = []
        traces: list[DecisionTrace] = []

        for candidate in candidates:
            guard = self.policy_guard.evaluate(candidate, snapshot)
            if not guard.allowed:
                traces.append(
                    DecisionTrace(
                        step=snapshot.step,
                        agent_id=self.agent_id,
                        proposal_id=f"{self.agent_id}-{uuid4().hex[:10]}",
                        action=candidate.action.value,
                        composite_score=-999.0,
                        breakdown=ActionScoreBreakdown(
                            twin_sim_gain=0.0,
                            rl_value=0.0,
                            sla_improvement=0.0,
                            risk=guard.risk_score,
                            cost=guard.cost_estimate,
                            trust=round(trust, 5),
                        ),
                        accepted=False,
                        reason="rejected_by_policy_guard:" + ",".join(guard.reasons),
                    )
                )
                continue

            twin_sim_gain, simulation_details = self.twin.evaluate_action(candidate)
            rl_value = self.rl_engine.value(snapshot, candidate.action) if self.behavior.use_rl else 0.0
            sla_improvement = simulation_details["sla_improvement"]

            if self.behavior.selection_strategy == "trident":
                composite_score = self.trident.score(
                    twin_sim_gain=twin_sim_gain,
                    rl_value=rl_value,
                    sla_improvement=sla_improvement,
                    risk=guard.risk_score,
                    cost=guard.cost_estimate,
                    trust=trust,
                )
                trace_reason = "candidate_scored_by_trident"
            elif self.behavior.selection_strategy == "rule_based":
                composite_score = (
                    1.50 * sla_improvement
                    + 1.00 * twin_sim_gain
                    - 0.80 * guard.risk_score
                    - 0.40 * guard.cost_estimate
                )
                trace_reason = "candidate_scored_by_rule_based"
            else:
                composite_score = self.random.uniform(-1.0, 1.0)
                trace_reason = "candidate_sampled_by_random_policy"

            breakdown = ActionScoreBreakdown(
                twin_sim_gain=round(twin_sim_gain, 5),
                rl_value=round(rl_value, 5),
                sla_improvement=round(sla_improvement, 5),
                risk=guard.risk_score,
                cost=guard.cost_estimate,
                trust=round(trust, 5),
            )

            proposal_id = f"{self.agent_id}-{uuid4().hex[:10]}"
            rationale = (
                f"sim_gain={twin_sim_gain:.3f}, rl={rl_value:.3f}, "
                f"sla={sla_improvement:.3f}, risk={guard.risk_score:.3f}, trust={trust:.3f}"
            )
            proposal = Proposal(
                proposal_id=proposal_id,
                agent_id=self.agent_id,
                governance_id=self.governance_id,
                action=candidate,
                score_breakdown=breakdown,
                composite_score=round(composite_score, 6),
                rationale=rationale,
                created_at=utc_now_iso(),
            )

            accepted = composite_score > 0.0 if self.behavior.selection_strategy != "random" else True
            traces.append(
                DecisionTrace(
                    step=snapshot.step,
                    agent_id=self.agent_id,
                    proposal_id=proposal_id,
                    action=candidate.action.value,
                    composite_score=round(composite_score, 6),
                    breakdown=breakdown,
                    accepted=accepted,
                    reason=trace_reason,
                )
            )

            scored_proposals.append(proposal)

        if not scored_proposals:
            return None, traces

        if self.behavior.selection_strategy == "random":
            best_proposal = self.random.choice(scored_proposals)
        else:
            best_proposal = max(scored_proposals, key=lambda proposal: proposal.composite_score)

        latency_ms = (perf_counter() - proposal_start) * 1000
        traces.append(
            DecisionTrace(
                step=snapshot.step,
                agent_id=self.agent_id,
                proposal_id=best_proposal.proposal_id,
                action=best_proposal.action.action.value,
                composite_score=best_proposal.composite_score,
                breakdown=best_proposal.score_breakdown,
                accepted=True,
                reason=(
                    "selected_candidate "
                    f"strategy={self.behavior.selection_strategy} latency_ms={latency_ms:.3f}"
                ),
            )
        )
        return best_proposal, traces

    def validate_proposal(self, proposal: Proposal) -> Vote:
        snapshot = self.twin.sync()
        guard = self.policy_guard.evaluate(proposal.action, snapshot)

        if not guard.allowed:
            return Vote(
                proposal_id=proposal.proposal_id,
                voter_id=self.governance_id,
                approve=False,
                confidence=0.95,
                reason="policy_guard_reject:" + ",".join(guard.reasons),
                created_at=utc_now_iso(),
            )

        local_gain, details = self.twin.evaluate_action(proposal.action)
        local_score = local_gain + details["sla_improvement"] - guard.risk_score
        approve = local_score >= 0.0 and proposal.composite_score >= -0.2
        confidence = max(0.05, min(0.99, 0.50 + local_score / 5))

        return Vote(
            proposal_id=proposal.proposal_id,
            voter_id=self.governance_id,
            approve=approve,
            confidence=round(confidence, 4),
            reason=f"local_score={local_score:.4f}",
            created_at=utc_now_iso(),
        )

    def learn(self, action: CandidateAction, reward: float) -> None:
        if not self.behavior.use_rl:
            return
        next_snapshot = self.twin.sync()
        self.rl_engine.observe(self.previous_snapshot, action.action, reward, next_snapshot, done=False)
        self.rl_engine.train_from_replay(batch_size=16, epochs=1)
        self.previous_snapshot = next_snapshot
