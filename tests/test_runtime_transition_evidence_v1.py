from __future__ import annotations

from core.runtime.runtime_transition_evidence import (
    build_runtime_transition_evidence,
    transition_evidence_from_legacy_metadata,
)
from core.runtime.runtime_transition_record import RuntimeTransitionRecord


def test_runtime_transition_evidence_wraps_transition_record() -> None:
    record = RuntimeTransitionRecord(
        transition_id="transition-evidence-1",
        source="runtime_transition_guard",
        from_state="SESSION_RESTORED",
        to_state="SESSION_SEALED",
        allowed=True,
        reason="transition_allowed",
        status="guarded",
        guard_ok=True,
        guard_reason="allowed",
        metadata={"phase": "seal"},
        evidence={"guard": {"ok": True}},
    )

    evidence = build_runtime_transition_evidence(
        record,
        metadata={"replay_safe": True},
    )

    payload = evidence.to_dict()

    assert payload["schema"] == "runtime_transition_evidence.v1"
    assert payload["record_schema"] == "runtime_transition_record.v1"
    assert payload["transition_id"] == "transition-evidence-1"
    assert payload["guard_ok"] is True
    assert payload["metadata"]["phase"] == "seal"
    assert payload["metadata"]["replay_safe"] is True
    assert payload["evidence"]["transition_record"]["schema"] == "runtime_transition_record.v1"


def test_transition_evidence_from_legacy_metadata_preserves_guard_and_enforcement() -> None:
    legacy = {
        "transition_allowed": True,
        "transition_reason": "canonical_transition_allowed",
        "canonical_status": "runtime_sealed",
        "canonical_from_status": "runtime_verified",
        "canonical_to_status": "runtime_sealed",
        "enforcement_mode": "AUDIT_ONLY",
        "enforcement_classification": "observe_only",
        "runtime_transition_guard": {
            "ok": False,
            "reason": "runtime_transition_denied",
        },
        "blocked": False,
    }

    evidence = transition_evidence_from_legacy_metadata(
        legacy,
        evidence_id="legacy-evidence-1",
        transition_id="legacy-transition-1",
        source="runtime_lifecycle_coordinator",
    )

    payload = evidence.to_dict()

    assert payload["evidence_id"] == "legacy-evidence-1"
    assert payload["transition_id"] == "legacy-transition-1"
    assert payload["allowed"] is True
    assert payload["guard_ok"] is False
    assert payload["blocked"] is False
    assert payload["canonical_to_status"] == "runtime_sealed"
    assert payload["enforcement_mode"] == "AUDIT_ONLY"
