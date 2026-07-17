from __future__ import annotations

import inspect
import json
from pathlib import Path

from core.runtime.runtime_evidence_surface import list_evidence, register_evidence
from core.runtime.runtime_recovery_evidence import export_runtime_recovery_evidence
from core.runtime.runtime_recovery_state import RuntimeRecoveryExecutionResult
from core.runtime.runtime_transition_evidence import (

    build_runtime_transition_evidence,
    export_runtime_transition_evidence,
)
from core.runtime.runtime_transition_record import RuntimeTransitionRecord
import pytest

pytestmark = [pytest.mark.integration]



def test_recovery_report_evidence_exports_existing_payload(tmp_path: Path) -> None:
    report = RuntimeRecoveryExecutionResult(
        execution_id="runtime-recovery-exec-1",
        recovery_id="recovery-1",
        source_session_id="source-session-1",
        status="completed",
        continuation_decision="ready_for_continuation",
        action_results=[
            {
                "action_id": "recovery-1-exec-verify",
                "action_type": "verify_recovery",
                "status": "completed",
            }
        ],
        verification_snapshot={"ok": True},
        recovery_chain_status="verified",
        metadata={"schema": "runtime_recovery_execution_result.v1"},
    )
    expected_payload = report.to_dict()

    export = export_runtime_recovery_evidence(
        repo_root=tmp_path,
        task_id="task recovery",
        recovery_report=report,
    )

    evidence_path = Path(export["evidence_path"])
    exported_payload = json.loads(evidence_path.read_text(encoding="utf-8"))

    assert exported_payload == expected_payload
    assert export["payload"] == expected_payload
    assert evidence_path == (
        tmp_path
        / "workspace"
        / "evidence"
        / "recovery"
        / "task_recovery_recovery_report.json"
    )


def test_recovery_report_registers_into_evidence_index(tmp_path: Path) -> None:
    export = export_runtime_recovery_evidence(
        repo_root=tmp_path,
        task_id="task-recovery",
        recovery_report={
            "schema": "custom_recovery_report.v1",
            "recovery_id": "recovery-2",
            "status": "ready",
            "summary": "existing recovery output",
        },
    )

    indexed = list_evidence("task-recovery", repo_root=tmp_path)

    assert indexed == [
        {
            "task_id": "task-recovery",
            "evidence_type": "recovery_report",
            "path": export["evidence_path"],
            "metadata": {
                "artifact_path": export["artifact_path"],
                "evidence_path": export["evidence_path"],
                "schema": "custom_recovery_report.v1",
                "recovery_id": "recovery-2",
                "status": "ready",
            },
        }
    ]


def test_evidence_index_lists_mixed_evidence_in_registration_order(tmp_path: Path) -> None:
    code_chain_path = (
        tmp_path
        / "workspace"
        / "evidence"
        / "code_chain_repair"
        / "task_123_repair_result_report.json"
    )
    register_evidence(
        "task_123",
        "code_chain_repair_result_report",
        code_chain_path,
        {"schema": "code_chain_repair_result_report_v1"},
        repo_root=tmp_path,
    )

    export_runtime_transition_evidence(
        repo_root=tmp_path,
        task_id="task_123",
        transition_evidence=build_runtime_transition_evidence(
            _transition_record("transition-recovery-mixed", lifecycle_id="task_123")
        ),
    )

    export_runtime_recovery_evidence(
        repo_root=tmp_path,
        task_id="task_123",
        recovery_report={
            "schema": "runtime_recovery_report.v1",
            "recovery_id": "recovery-mixed",
            "status": "verified",
        },
    )

    indexed = list_evidence("task_123", repo_root=tmp_path)

    assert [item["evidence_type"] for item in indexed] == [
        "code_chain_repair_report",
        "runtime_transition",
        "recovery_report",
    ]


def test_runtime_recovery_evidence_integration_adds_no_execution_path() -> None:
    import core.runtime.runtime_recovery_evidence as recovery_evidence
    from core.agent import agent_loop
    from core.tasks import scheduler

    source = inspect.getsource(recovery_evidence)
    agent_loop_source = inspect.getsource(agent_loop)
    scheduler_source = inspect.getsource(scheduler)

    assert "StepExecutor" not in source
    assert "AgentLoop" not in source
    assert "execute_code_chain_attempt" not in source
    assert "autonomous_repair_loop" not in source
    assert "run_recovery(" not in source
    assert "execute_recovery(" not in source
    assert "runtime_recovery_evidence" not in agent_loop_source
    assert "runtime_recovery_evidence" not in scheduler_source


def _transition_record(transition_id: str, *, lifecycle_id: str = "") -> RuntimeTransitionRecord:
    return RuntimeTransitionRecord(
        transition_id=transition_id,
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
        lifecycle_id=lifecycle_id,
        artifact_id="artifact-1",
        artifact_type="session",
        metadata={"operator": "test"},
        evidence={"contract": {"allowed": True}},
    )
