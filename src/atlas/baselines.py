from __future__ import annotations

from dataclasses import dataclass

RANDOM_POLICY = "random_policy"
RULE_BASED_POLICY = "rule_based_policy"
TRIDENT_NO_RL = "trident_no_rl"
TRIDENT_NO_TRUST = "trident_no_trust"
FULL_TRIDENT = "full_trident"

BASELINE_MODES = {
    RANDOM_POLICY,
    RULE_BASED_POLICY,
    TRIDENT_NO_RL,
    TRIDENT_NO_TRUST,
    FULL_TRIDENT,
}


@dataclass(frozen=True, slots=True)
class BaselineBehavior:
    selection_strategy: str
    use_rl: bool
    use_trust: bool


def normalize_baseline_mode(mode: str | None) -> str:
    normalized = (mode or FULL_TRIDENT).strip().lower()
    if normalized not in BASELINE_MODES:
        raise ValueError(
            "unsupported_baseline_mode: "
            f"{normalized}; expected one of {sorted(BASELINE_MODES)}"
        )
    return normalized


def behavior_for(mode: str) -> BaselineBehavior:
    normalized = normalize_baseline_mode(mode)
    if normalized == RANDOM_POLICY:
        return BaselineBehavior(selection_strategy="random", use_rl=False, use_trust=False)
    if normalized == RULE_BASED_POLICY:
        return BaselineBehavior(selection_strategy="rule_based", use_rl=False, use_trust=False)
    if normalized == TRIDENT_NO_RL:
        return BaselineBehavior(selection_strategy="trident", use_rl=False, use_trust=True)
    if normalized == TRIDENT_NO_TRUST:
        return BaselineBehavior(selection_strategy="trident", use_rl=True, use_trust=False)
    return BaselineBehavior(selection_strategy="trident", use_rl=True, use_trust=True)
