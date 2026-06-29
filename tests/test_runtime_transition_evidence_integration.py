from __future__ import annotations

import inspect
import json
from pathlib import Path

from core.runtime.runtime_evidence_surface import list_evidence, register_evidence
from core.runtime.runtime_transition_evidence import (

    RUNTIME_TRANSITION_EVIDENCE_SCHEMA,
    build_runtime_transition_evidence,
    export_runtime_transition_evidence,
)
from core.runtime.runtime_transition_record import RuntimeTransitionRecord
from core.runtime.runtime_transition_result import build_runtime_transition_result
import pytest

pytestmark = [pytest.mark.integration]



def test_runtime_transition_evidence_exports_and_registers_surface_index(tmp_path: Path) -> None:
    record = _transition_record("transition-surface-1", lifecycle_id="task_123")
    evidence = build_runtime_transition_evidence(record)
    expected_payload = evidence.to_dict()

    export = export_runtime_transition_evidence(
        repo_root=tmp_path,
        task_id="task_123",
        transition_evidence=evidence,
    )

    evidence_path = Path(export["evidence_path"])
    exported_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    indexed = list_evidence("task_123", repo_root=tmp_path)

    assert exported_payload == expected_payload
    assert evidence_path.parent == tmp_path / "workspace" / "evidence" / "runtime_transition"
    assert indexed == [
        {
            "task_id": "task_123",
            "evidence_type": "runtime_transition",
            "path": str(evidence_path),
            "metadata": {
                "artifact_path": str(evidence_path),
                "evidence_path": str(evidence_path),
                "schema": RUNTIME_TRANSITION_EVIDENCE_SCHEMA,
                "transition_id": "transition-surface-1",
                "evidence_id": "transition-surface-1:evidence",
            },
        }
    ]


def test_runtime_transition_result_can_opt_into_evidence_surface_export(tmp_path: Path) -> None:
    record = _transition_record("transition-result-1", lifecycle_id="task_result")

    result = build_runtime_transition_result(
        record,
        metadata={
            "runtime_evidence_surface": {
                "repo_root": tmp_path,
                "task_id": "task_result",
            }
        },
    )

    payload = result.to_dict()
    export = payload["metadata"]["runtime_transition_evidence_export"]
    indexed = list_evidence("task_result", repo_root=tmp_path)

    assert payload["evidence"]["schema"] == RUNTIME_TRANSITION_EVIDENCE_SCHEMA
    assert payload["evidence"]["transition_id"] == "transition-result-1"
    assert export["evidence_type"] == "runtime_transition"
    assert Path(export["evidence_path"]).exists()
    assert len(indexed) == 1
    assert indexed[0]["evidence_type"] == "runtime_transition"
    assert indexed[0]["metadata"]["result_schema"] == "runtime_transition_result.v1"


def test_evidence_index_lists_code_chain_and_runtime_transition(tmp_path: Path) -> None:
    code_chain_path = tmp_path / "workspace" / "evidence" / "code_chain_repair" / "task_123_repair_result_report.json"
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
            _transition_record("transition-surface-2", lifecycle_id="task_123")
        ),
    )

    indexed = list_evidence("task_123", repo_root=tmp_path)

    assert [item["evidence_type"] for item in indexed] == [
        "code_chain_repair_report",
        "runtime_transition",
    ]


def test_runtime_transition_evidence_integration_adds_no_execution_path() -> None:
    import core.runtime.runtime_transition_evidence as transition_evidence
    import core.runtime.runtime_transition_result as transition_result
    from core.agent import agent_loop
    from core.tasks import scheduler

    evidence_source = inspect.getsource(transition_evidence)
    result_source = inspect.getsource(transition_result)
    agent_loop_source = inspect.getsource(agent_loop)
    scheduler_source = inspect.getsource(scheduler)

    assert "StepExecutor" not in evidence_source
    assert "StepExecutor" not in result_source
    assert "execute_code_chain_attempt" not in evidence_source
    assert "execute_code_chain_attempt" not in result_source
    assert "runtime_transition_evidence" not in agent_loop_source
    assert "runtime_transition_evidence" not in scheduler_source


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
