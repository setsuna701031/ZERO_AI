from __future__ import annotations

from pathlib import Path

import pytest


def test_audit_only_never_blocks() -> None:
    from core.runtime.runtime_enforcement_readiness import (
        RuntimeEnforcementMode,
        apply_runtime_enforcement_decision,
    )

    payload = apply_runtime_enforcement_decision(
        {
            "from_status": "sealed",
            "to_status": "running",
            "transition_evidence": {"id": "ev"},
            "source": "test",
        },
        mode=RuntimeEnforcementMode.AUDIT_ONLY,
    )

    assert payload["enforcement_allowed"] is True
    assert payload["blocked"] is False
    assert payload["would_block"] is False
    assert payload["enforcement_decision"]["classification"] == "block_recommended"


def test_dry_run_reports_would_block_without_raising() -> None:
    from core.runtime.runtime_enforcement_readiness import (
        RuntimeEnforcementMode,
        apply_runtime_enforcement_decision,
    )

    payload = apply_runtime_enforcement_decision(
        {
            "from_status": "verified",
            "to_status": "running",
            "transition_evidence": {"id": "ev"},
            "source": "test",
        },
        mode=RuntimeEnforcementMode.DRY_RUN,
    )

    assert payload["enforcement_allowed"] is True
    assert payload["blocked"] is False
    assert payload["would_block"] is True


def test_enforce_raises_only_for_safe_block_recommended() -> None:
    from core.runtime.runtime_enforcement_readiness import (
        RuntimeEnforcementMode,
        RuntimeTransitionBlockedError,
        apply_runtime_enforcement_decision,
    )

    with pytest.raises(RuntimeTransitionBlockedError) as context:
        apply_runtime_enforcement_decision(
            {
                "from_status": "blocked",
                "to_status": "executed",
                "transition_evidence": {"id": "ev"},
                "source": "test",
            },
            mode=RuntimeEnforcementMode.ENFORCE,
        )

    assert context.value.decision.blocked is True
    assert context.value.decision.safe_to_enforce is True


def test_enforce_does_not_raise_for_observe_only_review_or_allowed() -> None:
    from core.runtime.runtime_enforcement_readiness import (
        RuntimeEnforcementMode,
        apply_runtime_enforcement_decision,
    )

    observe = apply_runtime_enforcement_decision(
        {
            "from_status": "running",
            "to_status": "committed",
            "transition_evidence": {"id": "ev"},
            "source": "test",
        },
        mode=RuntimeEnforcementMode.ENFORCE,
    )
    review = apply_runtime_enforcement_decision(
        {
            "from_status": "queued",
            "to_status": "running",
            "source": "test",
        },
        mode=RuntimeEnforcementMode.ENFORCE,
    )
    allowed = apply_runtime_enforcement_decision(
        {
            "from_status": "queued",
            "to_status": "running",
            "transition_evidence": {"id": "ev"},
            "source": "test",
        },
        mode=RuntimeEnforcementMode.ENFORCE,
    )

    assert observe["blocked"] is False
    assert observe["enforcement_classification"] == "observe_only"
    assert review["blocked"] is False
    assert review["review_required"] is True
    assert allowed["blocked"] is False
    assert allowed["allowed"] is True


def test_missing_evidence_and_replay_recovery_remain_review_required() -> None:
    from core.runtime.runtime_enforcement_readiness import (
        RuntimeEnforcementMode,
        apply_runtime_enforcement_decision,
    )

    missing = apply_runtime_enforcement_decision(
        {"from_status": "queued", "to_status": "running", "source": "test"},
        mode=RuntimeEnforcementMode.ENFORCE,
    )
    replay = apply_runtime_enforcement_decision(
        {"from_status": "unknown", "to_status": "replayed", "source": "test"},
        mode=RuntimeEnforcementMode.ENFORCE,
    )
    recovery = apply_runtime_enforcement_decision(
        {"from_status": "running", "to_status": "recovered", "source": "test"},
        mode=RuntimeEnforcementMode.ENFORCE,
    )

    assert missing["review_required"] is True
    assert missing["blocked"] is False
    assert replay["review_required"] is True
    assert replay["blocked"] is False
    assert recovery["review_required"] is True
    assert recovery["blocked"] is False


def test_runtime_transition_probe_defaults_to_audit_only_and_can_enforce() -> None:
    from core.runtime.runtime_enforcement_readiness import RuntimeTransitionBlockedError
    from core.runtime.runtime_status_transition import canonical_transition_summary

    audit = canonical_transition_summary("sealed", "running", source="probe")

    assert audit["enforcement_mode"] == "audit_only"
    assert audit["blocked"] is False
    assert audit["enforcement_allowed"] is True

    with pytest.raises(RuntimeTransitionBlockedError):
        canonical_transition_summary("sealed", "running", source="probe", mode="enforce")


def test_no_scheduler_agent_loop_or_step_executor_coupling() -> None:
    root = Path(__file__).resolve().parents[1]
    checked = [
        root / "core/runtime/runtime_enforcement_readiness.py",
        root / "core/runtime/runtime_status_transition.py",
    ]

    for path in checked:
        source = path.read_text(encoding="utf-8")
        assert "core.tasks.scheduler" not in source
        assert "core.agent.agent_loop" not in source
        assert "core.runtime.step_executor" not in source
