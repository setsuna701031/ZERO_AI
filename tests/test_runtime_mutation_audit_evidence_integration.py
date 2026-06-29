from __future__ import annotations

import inspect
import json
from pathlib import Path

from core.runtime.mutation_audit import (

    build_mutation_audit_record,
    create_audit_event,
)
from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationRiskLevel,
    MutationScope,
    MutationVerificationRequirement,
    create_mutation_session,
)
from core.runtime.runtime_evidence_surface import list_evidence, register_evidence
from core.runtime.runtime_mutation_audit_evidence import (
    export_runtime_mutation_audit_evidence,
)
from core.runtime.runtime_recovery_evidence import export_runtime_recovery_evidence
from core.runtime.runtime_transition_evidence import (
    build_runtime_transition_evidence,
    export_runtime_transition_evidence,
)
from core.runtime.runtime_transition_record import RuntimeTransitionRecord
import pytest

pytestmark = [pytest.mark.integration]



def test_mutation_audit_evidence_exports_existing_payload(tmp_path: Path) -> None:
    audit = _audit_record(session_id="mutation-session-1")
    expected_payload = json.loads(json.dumps(audit.to_dict(), sort_keys=True, default=str))

    export = export_runtime_mutation_audit_evidence(
        repo_root=tmp_path,
        task_id="task mutation",
        mutation_audit=audit,
    )

    evidence_path = Path(export["evidence_path"])
    exported_payload = json.loads(evidence_path.read_text(encoding="utf-8"))

    assert exported_payload == expected_payload
    assert export["payload"] == expected_payload
    assert evidence_path == (
        tmp_path
        / "workspace"
        / "evidence"
        / "mutation_audit"
        / "task_mutation_mutation_audit.json"
    )


def test_mutation_audit_registers_into_evidence_index(tmp_path: Path) -> None:
    export = export_runtime_mutation_audit_evidence(
        repo_root=tmp_path,
        task_id="task-mutation",
        mutation_audit={
            "schema": "custom_mutation_audit.v1",
            "audit_id": "audit-1",
            "session_id": "mutation-session-2",
            "status": "approved",
            "events": [],
        },
    )

    indexed = list_evidence("task-mutation", repo_root=tmp_path)

    assert indexed == [
        {
            "task_id": "task-mutation",
            "evidence_type": "mutation_audit",
            "path": export["evidence_path"],
            "metadata": {
                "artifact_path": export["artifact_path"],
                "evidence_path": export["evidence_path"],
                "schema": "custom_mutation_audit.v1",
                "session_id": "mutation-session-2",
                "audit_id": "audit-1",
                "status": "approved",
            },
        }
    ]


def test_evidence_index_lists_mixed_evidence_with_mutation_audit(tmp_path: Path) -> None:
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
            _transition_record("transition-mutation-mixed", lifecycle_id="task_123")
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

    export_runtime_mutation_audit_evidence(
        repo_root=tmp_path,
        task_id="task_123",
        mutation_audit={
            "schema": "runtime_mutation_audit.v1",
            "audit_id": "audit-mixed",
            "session_id": "mutation-session-mixed",
            "status": "approved",
            "events": [],
        },
    )

    indexed = list_evidence("task_123", repo_root=tmp_path)

    assert [item["evidence_type"] for item in indexed] == [
        "code_chain_repair_report",
        "runtime_transition",
        "recovery_report",
        "mutation_audit",
    ]


def test_runtime_mutation_audit_evidence_integration_adds_no_execution_path() -> None:
    import core.runtime.runtime_mutation_audit_evidence as mutation_audit_evidence
    from core.agent import agent_loop
    from core.tasks import scheduler

    source = inspect.getsource(mutation_audit_evidence)
    agent_loop_source = inspect.getsource(agent_loop)
    scheduler_source = inspect.getsource(scheduler)

    assert "StepExecutor" not in source
    assert "AgentLoop" not in source
    assert "execute_code_chain_attempt" not in source
    assert "autonomous_repair_loop" not in source
    assert "run_mutation_runtime_pipeline(" not in source
    assert "run_governed_mutation_runtime(" not in source
    assert "MutationGateway" not in source
    assert "runtime_mutation_audit_evidence" not in agent_loop_source
    assert "runtime_mutation_audit_evidence" not in scheduler_source


def _audit_record(session_id: str):
    session = create_mutation_session(
        intent="Export mutation audit evidence",
        initiator="test",
        reason="Verify mutation audit evidence export",
        scope=MutationScope(allowed_paths=("core/runtime",)),
        risk_level=MutationRiskLevel.MEDIUM,
        approval_mode=MutationApprovalMode.AUTO,
        verification=MutationVerificationRequirement.TARGETED_TESTS,
        sandbox_run_id="sandbox-run-1",
        metadata={"session_id_override": session_id},
    )
    extra = create_audit_event(
        event_type="mutation.custom.note",
        session_id=session.session_id,
        payload={"note": "existing audit output"},
    )
    return build_mutation_audit_record(
        session=session,
        extra_events=[extra],
        metadata={"track": "controlled-mutation-sandbox"},
    )


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
