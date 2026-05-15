from __future__ import annotations

import json

from core.runtime.audit_log import AuditLogger
from core.runtime.runtime_recovery_audit_log_bridge import (
    RuntimeRecoveryAuditLogBridge,
    log_runtime_recovery_audit_artifact,
)


def test_runtime_recovery_audit_log_bridge(tmp_path) -> None:
    logger = AuditLogger(workspace_root=str(tmp_path))

    artifact = log_runtime_recovery_audit_artifact(
        payload={
            "task_id": "task-1",
        },
        source={
            "operator_summary": {
                "ok": True,
                "status": "ready",
                "readiness": "ready",
                "summary": "Recovery gate passed.",
                "blockers": [],
            }
        },
        audit_id="audit-1",
        recovery_id="recovery-1",
        audit_logger=logger,
    )

    assert artifact["audit_id"] == "audit-1"

    audit_file = tmp_path / "tasks" / "task-1" / "audit_log.jsonl"

    assert audit_file.exists()

    lines = audit_file.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 1

    payload = json.loads(lines[0])

    assert payload["event"] == RuntimeRecoveryAuditLogBridge.EVENT
    assert payload["source"] == RuntimeRecoveryAuditLogBridge.SOURCE

    data = payload["data"]

    assert data["artifact"]["readiness"] == "ready"
    assert data["artifact"]["status"] == "ready"


def test_runtime_recovery_audit_log_bridge_blocked(tmp_path) -> None:
    logger = AuditLogger(workspace_root=str(tmp_path))

    artifact = log_runtime_recovery_audit_artifact(
        payload={
            "task_id": "task-2",
        },
        source={
            "operator_summary": {
                "ok": False,
                "status": "blocked",
                "readiness": "blocked",
                "summary": "Blocked.",
                "blockers": ["missing confirmation"],
            }
        },
        audit_logger=logger,
    )

    assert artifact["readiness"] == "blocked"

    audit_file = tmp_path / "tasks" / "task-2" / "audit_log.jsonl"

    lines = audit_file.read_text(encoding="utf-8").splitlines()

    payload = json.loads(lines[0])

    artifact_payload = payload["data"]["artifact"]

    assert artifact_payload["blockers"] == ["missing confirmation"]
