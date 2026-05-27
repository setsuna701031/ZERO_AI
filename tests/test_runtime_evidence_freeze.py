from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from core.runtime.execution_authority import ensure_authority_metadata, validate_authority_metadata
from core.runtime.runtime_evidence_freeze import (
    RuntimeEvidenceKind,
    assert_evidence_does_not_grant_authority,
    attach_authority_evidence,
    attach_recovery_evidence,
    attach_replay_evidence,
    attach_surface_evidence,
    attach_transaction_evidence,
    create_evidence_snapshot,
    normalize_evidence_record,
)
from core.runtime.runtime_recovery_freeze import (
    create_recovery_attempt,
    record_recovery_terminal_failure,
)
from core.runtime.runtime_replay_freeze import create_replay_run
from core.runtime.runtime_surface_registry import classify_runtime_surface
from core.runtime.runtime_transaction_registry import (
    create_transaction,
    record_approval,
    record_audit,
    record_preflight,
)


def test_authority_denied_creates_evidence() -> None:
    validation = validate_authority_metadata({}, surface="apply_patch")
    evidence = attach_authority_evidence({"surface": "apply_patch", "authority_validation": validation})

    assert validation["ok"] is False
    assert evidence.kind is RuntimeEvidenceKind.AUTHORITY
    assert evidence.decision == "denied"
    assert evidence.state == "blocked"


def test_authority_allowed_creates_evidence() -> None:
    metadata, validation = ensure_authority_metadata(
        {},
        task={"id": "task-evidence", "runtime_identity": {"identity_id": "runtime"}},
        step={"type": "write_file", "id": "step-evidence"},
        context={"runtime_session_id": "session-evidence"},
        lineage={"request_id": "trace-evidence"},
        surface="write_file",
        action_type="mutation",
    )
    evidence = attach_authority_evidence({**metadata, "surface": "write_file", "authority_validation": validation})

    assert validation["ok"] is True
    assert evidence.decision == "allowed"
    assert evidence.task_id == "task-evidence"


def test_surface_classification_creates_evidence_payload() -> None:
    surface = classify_runtime_surface("apply_patch")
    evidence = attach_surface_evidence(asdict(surface))

    assert evidence.kind is RuntimeEvidenceKind.SURFACE
    assert evidence.surface == "apply_patch"
    assert evidence.state == "side_effect"


def test_mutation_transaction_links_evidence_refs() -> None:
    tx = create_transaction(
        task_id="task-tx-evidence",
        step_id="step-tx-evidence",
        trace_id="trace-tx-evidence",
        authority_source="execution_gateway",
        surface="write_file",
        affected_files=["workspace/shared/evidence.txt"],
        audit_refs=["audit:tx-evidence"],
    )
    tx = record_preflight(tx, {"ok": True})
    tx = record_approval(tx, {"ok": False, "reason": "blocked"})
    tx = record_audit(tx, ["audit:tx-evidence"])
    evidence = attach_transaction_evidence(tx)

    assert evidence.transaction_id == tx.transaction_id
    assert "audit:tx-evidence" in evidence.refs


def test_replay_read_creates_read_only_evidence() -> None:
    replay = create_replay_run(
        event_log=[{"event_id": "r", "sequence": 1, "surface": "replay_read", "audit_refs": ["audit:replay"]}]
    )
    evidence = attach_replay_evidence(replay)

    assert replay.authority_required is False
    assert evidence.replay_run_id == replay.replay_run_id
    assert evidence.state == "verified"


def test_replay_evidence_does_not_grant_authority() -> None:
    replay = create_replay_run(event_log=[{"event_id": "r", "sequence": 1, "surface": "replay_read"}])
    evidence = attach_replay_evidence(replay)

    assert assert_evidence_does_not_grant_authority(evidence) is True


def test_recovery_terminal_state_creates_evidence() -> None:
    attempt = create_recovery_attempt(original_transaction_id="runtime_tx:evidence-source")
    attempt = record_recovery_terminal_failure(attempt, "recovery_failed_for_evidence")
    evidence = attach_recovery_evidence(attempt)

    assert attempt.evidence_id
    assert evidence.recovery_attempt_id == attempt.recovery_attempt_id
    assert evidence.state == "failed_terminal"


def test_blocked_mutation_leaves_evidence(tmp_path: Path) -> None:
    from core.runtime.step_executor import StepExecutor

    result = StepExecutor(workspace_root=str(tmp_path)).execute_step(
        {"type": "write_file", "path": "workspace/shared/blocked.txt", "content": "x"}
    )

    assert result["blocked"] is True
    assert result["canonical_evidence"]["evidence_refs"]
    assert result["runtime_execution_result"]["metadata"]["canonical_evidence"]["evidence_refs"]


def test_evidence_record_has_stable_normalized_digest() -> None:
    first = attach_authority_evidence({"surface": "write_file", "authority_validation": {"ok": False, "reason": "missing"}})
    second = attach_authority_evidence({"surface": "write_file", "authority_validation": {"ok": False, "reason": "missing"}})

    assert first.normalized_digest == second.normalized_digest
    assert normalize_evidence_record(first)["normalized_digest"] == normalize_evidence_record(second)["normalized_digest"]


def test_evidence_snapshot_includes_authority_surface_transaction_replay_recovery_refs() -> None:
    authority = attach_authority_evidence({"surface": "write_file", "authority_validation": {"ok": True, "reason": "authority_metadata_valid"}})
    surface = attach_surface_evidence(asdict(classify_runtime_surface("write_file")))
    tx = attach_transaction_evidence(
        create_transaction(
            task_id="task-snapshot",
            step_id="step-snapshot",
            trace_id="trace-snapshot",
            authority_source="execution_gateway",
            surface="write_file",
            affected_files=["workspace/shared/snapshot.txt"],
        )
    )
    replay = attach_replay_evidence(create_replay_run(event_log=[{"event_id": "r", "sequence": 1, "surface": "replay_read"}]))
    recovery = attach_recovery_evidence(create_recovery_attempt(original_transaction_id="runtime_tx:snapshot"))

    snapshot = create_evidence_snapshot([authority, surface, tx, replay, recovery])

    assert snapshot.authority_refs == (authority.evidence_id,)
    assert snapshot.surface_refs == (surface.evidence_id,)
    assert snapshot.transaction_refs == (tx.evidence_id,)
    assert snapshot.replay_refs == (replay.evidence_id,)
    assert snapshot.recovery_refs == (recovery.evidence_id,)
