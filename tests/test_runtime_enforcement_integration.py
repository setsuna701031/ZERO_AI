from __future__ import annotations

from pathlib import Path

import pytest


def _coordinator_with_verified_record(lifecycle_id: str = "life-enforce"):
    from core.runtime.runtime_lifecycle_coordinator import RuntimeLifecycleCoordinator

    coordinator = RuntimeLifecycleCoordinator()
    coordinator.create_record(
        lifecycle_id=lifecycle_id,
        artifact_id=f"artifact-{lifecycle_id}",
        artifact_type="execution",
    )
    coordinator.transition(lifecycle_id, "active")
    coordinator.transition(lifecycle_id, "verified")
    return coordinator


def test_lifecycle_transition_defaults_to_audit_only_without_blocking() -> None:
    coordinator = _coordinator_with_verified_record("life-audit-default")

    result = coordinator.transition("life-audit-default", "active")

    assert result.status == "blocked"
    assert result.metadata["enforcement_mode"] == "audit_only"
    assert result.metadata["block_recommended"] is True
    assert result.metadata["enforcement_allowed"] is True
    assert result.metadata["would_block"] is False


def test_lifecycle_transition_dry_run_reports_would_block_without_raising() -> None:
    from core.runtime.runtime_enforcement_readiness import RuntimeEnforcementMode

    coordinator = _coordinator_with_verified_record("life-dry-run")

    result = coordinator.transition(
        "life-dry-run",
        "active",
        enforcement_mode=RuntimeEnforcementMode.DRY_RUN,
    )

    assert result.status == "blocked"
    assert result.metadata["enforcement_mode"] == "dry_run"
    assert result.metadata["block_recommended"] is True
    assert result.metadata["enforcement_allowed"] is True
    assert result.metadata["would_block"] is True


def test_lifecycle_transition_enforce_blocks_only_hard_block_candidates() -> None:
    from core.runtime.runtime_enforcement_readiness import (
        RuntimeEnforcementMode,
        RuntimeTransitionBlockedError,
    )

    coordinator = _coordinator_with_verified_record("life-hard-block")

    with pytest.raises(RuntimeTransitionBlockedError) as context:
        coordinator.transition(
            "life-hard-block",
            "active",
            enforcement_mode=RuntimeEnforcementMode.ENFORCE,
        )

    assert context.value.decision.blocked is True
    assert context.value.decision.classification == "block_recommended"
    assert context.value.decision.safe_to_enforce is True


def test_lifecycle_transition_enforce_allows_canonical_allowed_transition() -> None:
    from core.runtime.runtime_enforcement_readiness import RuntimeEnforcementMode
    from core.runtime.runtime_lifecycle_coordinator import RuntimeLifecycleCoordinator

    coordinator = RuntimeLifecycleCoordinator()
    coordinator.create_record(
        lifecycle_id="life-allowed",
        artifact_id="artifact-allowed",
        artifact_type="execution",
    )

    result = coordinator.transition(
        "life-allowed",
        "active",
        enforcement_mode=RuntimeEnforcementMode.ENFORCE,
    )

    assert result.status == "transitioned"
    assert result.record.state == "active"
    assert result.metadata["blocked"] is False
    assert result.metadata["enforcement_allowed"] is True


def test_lifecycle_transition_enforce_allows_observe_only_shortcut() -> None:
    from core.runtime.runtime_enforcement_readiness import RuntimeEnforcementMode
    from core.runtime.runtime_lifecycle_coordinator import RuntimeLifecycleCoordinator

    coordinator = RuntimeLifecycleCoordinator()
    coordinator.create_record(
        lifecycle_id="life-observe",
        artifact_id="artifact-observe",
        artifact_type="execution",
    )
    coordinator.transition("life-observe", "active")

    result = coordinator.transition(
        "life-observe",
        "committed",
        enforcement_mode=RuntimeEnforcementMode.ENFORCE,
    )

    assert result.status == "transitioned"
    assert result.metadata["enforcement_classification"] == "observe_only"
    assert result.metadata["enforcement_allowed"] is True


def test_lifecycle_transition_enforce_allows_review_required_transition() -> None:
    from core.runtime.runtime_enforcement_readiness import RuntimeEnforcementMode
    from core.runtime.runtime_lifecycle_coordinator import RuntimeLifecycleCoordinator

    coordinator = RuntimeLifecycleCoordinator()
    coordinator.create_record(
        lifecycle_id="life-review",
        artifact_id="artifact-review",
        artifact_type="execution",
    )

    result = coordinator.transition(
        "life-review",
        "verified",
        enforcement_mode=RuntimeEnforcementMode.ENFORCE,
    )

    assert result.status == "blocked"
    assert result.metadata["review_required"] is True
    assert result.metadata["enforcement_allowed"] is True
    assert result.metadata["block_recommended"] is False


def test_missing_evidence_remains_review_required_without_hard_blocking() -> None:
    from core.runtime.runtime_enforcement_readiness import (
        RuntimeEnforcementMode,
        apply_runtime_enforcement_decision,
    )

    payload = apply_runtime_enforcement_decision(
        {"from_status": "queued", "to_status": "running", "source": "integration"},
        mode=RuntimeEnforcementMode.ENFORCE,
    )

    assert payload["review_required"] is True
    assert payload["blocked"] is False
    assert payload["enforcement_allowed"] is True


def test_lifecycle_report_preserves_explicit_enforcement_metadata() -> None:
    from core.runtime.runtime_enforcement_readiness import RuntimeEnforcementMode

    coordinator = _coordinator_with_verified_record("life-report")
    result = coordinator.transition(
        "life-report",
        "active",
        enforcement_mode=RuntimeEnforcementMode.DRY_RUN,
    )
    report = result.to_metadata()

    assert report["enforcement_mode"] == "dry_run"
    assert report["would_block"] is True
    assert report["metadata"]["enforcement_decision"]["mode"] == "dry_run"



def test_lifecycle_transition_history_persists_enforcement_decision_snapshot() -> None:
    from core.runtime.runtime_enforcement_readiness import RuntimeEnforcementMode
    from core.runtime.runtime_lifecycle_coordinator import RuntimeLifecycleCoordinator

    coordinator = RuntimeLifecycleCoordinator()
    coordinator.create_record(
        lifecycle_id="life-persist",
        artifact_id="artifact-persist",
        artifact_type="execution",
    )

    result = coordinator.transition(
        "life-persist",
        "active",
        enforcement_mode=RuntimeEnforcementMode.DRY_RUN,
        metadata={"operator": "test"},
    )

    history_event = result.record.transition_history[-1]
    decision = history_event["enforcement_decision"]

    assert decision["schema"] == "runtime_enforcement_decision.v1"
    assert decision["mode"] == "dry_run"
    assert decision["blocked"] is False
    assert decision["would_block"] is False
    assert decision["source_status"] == "pending"
    assert decision["target_status"] == "running"
    assert history_event["metadata"]["enforcement_decision"]["schema"] == "runtime_enforcement_decision.v1"
    assert result.record.metadata["last_enforcement_decision"]["schema"] == "runtime_enforcement_decision.v1"


def test_blocked_lifecycle_result_exports_persistence_safe_enforcement_snapshot() -> None:
    from core.runtime.runtime_enforcement_readiness import RuntimeEnforcementMode

    coordinator = _coordinator_with_verified_record("life-blocked-persist")
    result = coordinator.transition(
        "life-blocked-persist",
        "active",
        enforcement_mode=RuntimeEnforcementMode.DRY_RUN,
    )
    report = result.to_metadata()
    decision = report["metadata"]["enforcement_decision"]

    assert report["status"] == "blocked"
    assert decision["schema"] == "runtime_enforcement_decision.v1"
    assert decision["mode"] == "dry_run"
    assert decision["classification"] == "block_recommended"
    assert decision["safe_to_enforce"] is True
    assert decision["would_block"] is True
    assert report["enforcement_decision_schema"] == "runtime_enforcement_decision.v1"


def test_enforcement_decision_snapshot_is_deep_copied_for_persistence() -> None:
    from core.runtime.runtime_enforcement_readiness import RuntimeEnforcementMode
    from core.runtime.runtime_lifecycle_coordinator import RuntimeLifecycleCoordinator

    coordinator = RuntimeLifecycleCoordinator()
    coordinator.create_record(
        lifecycle_id="life-copy",
        artifact_id="artifact-copy",
        artifact_type="execution",
    )

    result = coordinator.transition(
        "life-copy",
        "active",
        enforcement_mode=RuntimeEnforcementMode.AUDIT_ONLY,
        metadata={"nested": {"value": "original"}},
    )

    event = result.record.transition_history[-1]
    event["metadata"]["enforcement_decision"]["metadata"]["nested"]["value"] = "mutated"

    assert result.record.metadata["last_enforcement_decision"]["metadata"]["nested"]["value"] == "original"


def test_forbidden_layers_do_not_reference_runtime_enforcement_integration() -> None:
    root = Path(__file__).resolve().parents[1]
    forbidden = [
        root / "core/tasks/scheduler.py",
        root / "core/agent/agent_loop.py",
        root / "core/runtime/step_executor.py",
        root / "core/runtime/repair_transaction_execution_bridge.py",
        root / "app.py",
        root / "services/system_boot.py",
    ]
    markers = (
        "RuntimeEnforcementMode",
        "RuntimeTransitionBlockedError",
        "enforcement_mode",
        "apply_runtime_enforcement_decision",
    )

    for path in forbidden:
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for marker in markers:
            assert marker not in source
