import pytest

from atlas.llm_planner.planner import PlannerValidationError, validate_candidate_payload


def test_invalid_llm_action_payload_is_rejected() -> None:
    payload = {
        "candidates": [
            {
                "action": "drop_database",
                "target_service": "svc-1",
            }
        ]
    }

    with pytest.raises(PlannerValidationError):
        validate_candidate_payload(payload, max_candidates=5)


def test_non_dict_or_list_payload_is_rejected() -> None:
    with pytest.raises(PlannerValidationError):
        validate_candidate_payload("bad-payload", max_candidates=5)
