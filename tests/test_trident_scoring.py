from atlas.agent_core.trident import TridentScorer
from atlas.config import TridentWeights


def test_trident_scoring_formula_matches_expected_values() -> None:
    scorer = TridentScorer(
        TridentWeights(alpha=0.4, beta=0.2, gamma=0.2, lambda_penalty=0.1, mu=0.05, nu=0.1)
    )
    score = scorer.score(
        twin_sim_gain=2.0,
        rl_value=1.5,
        sla_improvement=1.0,
        risk=0.8,
        cost=0.3,
        trust=0.7,
    )

    expected = 0.4 * 2.0 + 0.2 * 1.5 + 0.2 * 1.0 - 0.1 * 0.8 - 0.05 * 0.3 + 0.1 * 0.7
    assert round(score, 8) == round(expected, 8)
