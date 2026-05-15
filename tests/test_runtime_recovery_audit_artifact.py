from __future__ import annotations

from core.runtime.runtime_recovery_audit_artifact import (
    RuntimeRecoveryAuditArtifactBuilder,
    build_runtime_recovery_audit_artifact,
)


def test_build_runtime_recovery_audit_artifact_ready() -> None:
    artifact = build_runtime_recovery_audit_artifact(
        {
            "operator_summary": {
                "ok": True,
                "status": "ready",
                "readiness": "ready",
                "summary": "Recovery gate passed.",
                "blockers": [],
            }
        },
        audit_id="audit-1",
        task_id="task-1",
        recovery_id="recovery-1",
    )

    assert artifact["ok"] is True
    assert artifact["schema"] == RuntimeRecoveryAuditArtifactBuilder.SCHEMA
    assert artifact["artifact_type"] == RuntimeRecoveryAuditArtifactBuilder.ARTIFACT_TYPE
    assert artifact["audit_id"] == "audit-1"
    assert artifact["task_id"] == "task-1"
    assert artifact["recovery_id"] == "recovery-1"
    assert artifact["read_only"] is True
    assert artifact["executes_recovery"] is False
    assert artifact["executes_rollback"] is False
    assert artifact["executes_repair"] is False
    assert artifact["invokes_scheduler"] is False
    assert artifact["readiness"] == "ready"
    assert artifact["status"] == "ready"
    assert artifact["summary"] == "Recovery gate passed."
    assert artifact["blockers"] == []


def test_build_runtime_recovery_audit_artifact_blocked() -> None:
    artifact = build_runtime_recovery_audit_artifact(
        {
            "operator_summary": {
                "ok": False,
                "status": "blocked",
                "readiness": "blocked",
                "summary": "Blocked.",
                "blockers": ["missing confirmation"],
            }
        }
    )

    assert artifact["ok"] is False
    assert artifact["readiness"] == "blocked"
    assert artifact["blockers"] == ["missing confirmation"]
    assert artifact["source_event"]["readiness"] == "blocked"
