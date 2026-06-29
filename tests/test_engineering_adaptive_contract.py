from __future__ import annotations

from core.tasks.engineering_adaptive_planner import ALLOWED_ADAPTIVE_DECISIONS, normalize_adaptive_decision
import pytest

pytestmark = [pytest.mark.contract]




REQUIRED_KEYS = {
    "decision",
    "reason",
    "confidence",
    "next_action",
    "continuation_plan",
    "replan_request",
    "blocking_issues",
}


def test_adaptive_decision_contract_accepts_only_four_states() -> None:
    for decision in sorted(ALLOWED_ADAPTIVE_DECISIONS):
        normalized = normalize_adaptive_decision({"decision": decision, "reason": f"{decision}_reason"})

        assert REQUIRED_KEYS.issubset(normalized)
        assert normalized["decision"] == decision
        assert normalized["reason"]
        assert 0.0 <= normalized["confidence"] <= 1.0
        assert isinstance(normalized["continuation_plan"], dict)
        assert isinstance(normalized["replan_request"], dict)
        assert isinstance(normalized["blocking_issues"], list)


def test_adaptive_decision_contract_normalizes_legacy_continue_aliases() -> None:
    for decision in ["retry", "again", "next", "resume", "loop"]:
        normalized = normalize_adaptive_decision({"decision": decision, "reason": "legacy_continue"})

        assert normalized["decision"] == "continue"
        assert normalized["reason"] == "legacy_continue"


def test_adaptive_decision_contract_rejects_unknown_as_blocked_contract_state() -> None:
    normalized = normalize_adaptive_decision({"decision": "unknown", "confidence": 4.2})

    assert normalized["decision"] == "blocked"
    assert normalized["reason"] == "invalid_adaptive_decision"
    assert normalized["confidence"] == 1.0
