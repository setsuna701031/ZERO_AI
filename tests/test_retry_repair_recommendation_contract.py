from __future__ import annotations

import pytest

from core.engineering.retry_repair_recommendation import (

    build_retry_repair_recommendation,
    validate_retry_repair_recommendation_contract,
)
pytestmark = [pytest.mark.contract]



def test_retry_repair_recommendation_no_action_for_passed_verification() -> None:
    recommendation = build_retry_repair_recommendation(_bundle(status="passed", failure="none"))
    payload = recommendation.to_dict()

    assert payload["recommendation_id"].startswith("retry-repair-recommendation-")
    assert payload["decision"] == "no_action"
    assert payload["retry_allowed"] is False
    assert payload["repair_recommended"] is False
    assert payload["escalation_required"] is False
    assert payload["approval_required"] is False
    assert payload["metadata"]["control_plane_only"] is True
    assert payload["metadata"]["mutation_allowed"] is False
    assert payload["metadata"]["execution_allowed"] is False
    assert payload["metadata"]["runtime_authority_granted"] is False
    assert validate_retry_repair_recommendation_contract(payload) is True


def test_retry_repair_recommendation_retries_timeout_before_escalation() -> None:
    first = build_retry_repair_recommendation(
        _bundle(status="timeout", failure="timeout"),
        attempt_index=0,
        max_retries=2,
    ).to_dict()
    exhausted = build_retry_repair_recommendation(
        _bundle(status="timeout", failure="timeout"),
        attempt_index=2,
        max_retries=2,
    ).to_dict()

    assert first["decision"] == "retry_verification"
    assert first["retry_allowed"] is True
    assert first["repair_recommended"] is False
    assert first["approval_required"] is False

    assert exhausted["decision"] == "escalate_to_user"
    assert exhausted["retry_allowed"] is False
    assert exhausted["escalation_required"] is True
    assert exhausted["approval_required"] is True


def test_retry_repair_recommendation_recommends_repair_after_retry_budget() -> None:
    first = build_retry_repair_recommendation(
        _bundle(status="failed", failure="test_failure"),
        attempt_index=0,
        max_retries=1,
    ).to_dict()
    exhausted = build_retry_repair_recommendation(
        _bundle(status="failed", failure="test_failure"),
        attempt_index=1,
        max_retries=1,
    ).to_dict()

    assert first["decision"] == "retry_then_review"
    assert first["retry_allowed"] is True
    assert first["repair_recommended"] is True
    assert first["approval_required"] is True

    assert exhausted["decision"] == "recommend_repair"
    assert exhausted["retry_allowed"] is False
    assert exhausted["repair_recommended"] is True
    assert exhausted["approval_required"] is True


def test_retry_repair_recommendation_escalates_unknown_after_budget() -> None:
    payload = build_retry_repair_recommendation(
        _bundle(status="failed", failure="unknown_failure"),
        attempt_index=2,
        max_retries=2,
    ).to_dict()

    assert payload["decision"] == "escalate_to_user"
    assert payload["escalation_required"] is True
    assert payload["approval_required"] is True
    assert payload["repair_recommended"] is False


def test_retry_repair_recommendation_rejects_non_verification_evidence() -> None:
    bundle = _bundle(status="failed", failure="test_failure")
    bundle["metadata"]["verification_only"] = False

    with pytest.raises(ValueError, match="evidence_bundle_must_be_verification_only"):
        build_retry_repair_recommendation(bundle)


def test_retry_repair_recommendation_contract_rejects_runtime_success_shape() -> None:
    payload = build_retry_repair_recommendation(
        _bundle(status="failed", failure="compile_failure")
    ).to_dict()

    assert validate_retry_repair_recommendation_contract(payload) is True

    payload["runtime_evidence_id"] = "runtime-evidence-123"

    assert validate_retry_repair_recommendation_contract(payload) is False


def _bundle(*, status: str, failure: str) -> dict[str, object]:
    return {
        "bundle_id": "verification-evidence-123",
        "verification_route_id": "verification-route-123",
        "command": "python -m pytest tests/test_alpha.py",
        "status": status,
        "exit_code": 0 if status == "passed" else 1,
        "stdout_tail": "",
        "stderr_tail": "",
        "failure_classification": failure,
        "retry_recommended": failure != "none",
        "repair_eligible": failure in {
            "test_failure",
            "compile_failure",
            "lint_failure",
            "runtime_error",
        },
        "metadata": {
            "verification_only": True,
            "read_only": True,
            "mutation_allowed": False,
            "execution_authority_granted": False,
            "patch_apply_allowed": False,
            "canonical_runtime_success": False,
        },
    }
