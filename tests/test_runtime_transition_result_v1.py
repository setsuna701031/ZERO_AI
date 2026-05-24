from __future__ import annotations

from core.runtime.runtime_transition_record import RuntimeTransitionRecord
from core.runtime.runtime_transition_result import build_runtime_transition_result


def test_runtime_transition_result_preserves_canonical_record_and_evidence() -> None:
    record = RuntimeTransitionRecord(
        transition_id="transition-1",
        source="runtime_lifecycle_coordinator",
        from_state="verified",
        to_state="sealed",
        normalized_from_state="SESSION_RESTORED",
        normalized_to_state="SESSION_SEALED",
        canonical_from_status="runtime_verified",
        canonical_to_status="runtime_sealed",
        allowed=True,
        reason="transition_allowed",
        status="transitioned",
        enforcement_mode="AUDIT_ONLY",
        enforcement_allowed=True,
        enforcement_classification="observe_only",
        blocked=False,
        would_block=False,
        guard_ok=True,
        guard_reason="transition_allowed",
        lifecycle_id="life-1",
        artifact_id="artifact-1",
        artifact_type="session",
        metadata={"operator": "test"},
        evidence={"contract": {"allowed": True}},
    )

    result = build_runtime_transition_result(record)

    payload = result.to_dict()

    assert result.ok is True
    assert payload["schema"] == "runtime_transition_result.v1"
    assert payload["record"]["schema"] == "runtime_transition_record.v1"
    assert payload["evidence"]["schema"] == "runtime_transition_evidence.v1"
    assert payload["record"]["transition_id"] == "transition-1"
    assert payload["evidence"]["transition_id"] == "transition-1"
    assert payload["record"]["normalized_from_state"] == "SESSION_RESTORED"
    assert payload["record"]["normalized_to_state"] == "SESSION_SEALED"
    assert payload["evidence"]["evidence"]["transition_record"]["transition_id"] == "transition-1"


def test_runtime_transition_result_marks_blocked_record_not_ok() -> None:
    record = RuntimeTransitionRecord(
        transition_id="transition-2",
        source="runtime_lifecycle_coordinator",
        from_state="active",
        to_state="sealed",
        allowed=False,
        reason="invalid_lifecycle_transition:active->sealed",
        status="blocked",
        blocked=True,
        guard_ok=None,
    )

    result = build_runtime_transition_result(record)

    assert result.allowed is False
    assert result.blocked is True
    assert result.ok is False
    assert result.to_dict()["status"] == "blocked"
