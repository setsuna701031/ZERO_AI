from __future__ import annotations

import copy

import pytest

import core.runtime.persistent_runtime_orchestrator as persistent_orchestrator_module
from core.adaptive.continuation_runtime import ContinuationRuntime
from core.adaptive.replan_runtime import ReplanRuntime
from core.goals.goal_lineage_contract import extract_goal_lineage, extract_runtime_identity
from core.runtime.persistent_queue_contract import queue_session_id
from core.runtime.persistent_runtime_orchestrator import PersistentRuntimeOrchestrator
from core.runtime.runtime_recovery_continuation import RuntimeRecoveryContinuationLayer
from core.runtime.runtime_recovery_state import RECOVERY_CONTINUATION_READY, RECOVERY_EXECUTION_STATUS_COMPLETED
from core.runtime.runtime_execution_fabric import RuntimeExecutionFabric
from core.runtime.runtime_session_resume import RuntimeSessionResumeRecord
from core.runtime.runtime_transaction_fabric import RuntimeTransactionFabric
pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]




def _lineage() -> dict[str, str]:
    return extract_goal_lineage(
        {
            "root_goal_id": "goal-a",
            "source_goal_id": "goal-a",
            "goal_id": "goal-a",
            "branch_type": "root",
            "branch_id": "goal-a",
            "session_id": "session-a",
            "runtime_session_id": "runtime-a",
        },
        require_complete=True,
    )


def test_canonical_runtime_identity_preserves_source_session_as_distinct() -> None:
    identity = extract_runtime_identity(
        {
            "session_id": "session-a",
            "runtime_session_id": "runtime-a",
            "source_session_id": "source-a",
        },
        require_complete=True,
    )

    assert identity == {
        "schema": "zero.runtime_identity.v1",
        "session_id": "session-a",
        "runtime_session_id": "runtime-a",
        "source_session_id": "source-a",
    }


def test_queue_session_lookup_never_aliases_runtime_or_source_session() -> None:
    assert queue_session_id({"runtime_session_id": "runtime-a"}) == ""
    assert queue_session_id({"source_session_id": "source-a"}) == ""
    assert queue_session_id({"session_id": "session-a", "runtime_session_id": "runtime-a"}) == "session-a"
    with pytest.raises(ValueError, match="session_identity_conflicting_fields:session_id"):
        queue_session_id({"session_id": "session-a", "metadata": {"session_id": "session-drift"}})


def test_adaptive_runtime_defaults_keep_session_and_runtime_session_distinct() -> None:
    continuation = ContinuationRuntime.start("goal-a")
    replan = ReplanRuntime.start()

    assert continuation.session_id != continuation.runtime_session_id
    assert replan.session_id != replan.runtime_session_id


def test_persistent_resume_cursor_uses_canonical_runtime_session(monkeypatch, tmp_path) -> None:
    captured = {}

    class EngineeringSession:
        def __init__(self, **kwargs):
            captured["init"] = copy.deepcopy(kwargs)

        def initialize(self):
            return None

        def create_resume_point(self, **kwargs):
            captured["cursor"] = copy.deepcopy(kwargs["cursor"])
            return {"resume_id": "resume-a"}

        def record_continuation(self, **kwargs):
            return copy.deepcopy(kwargs)

        def summary(self):
            return {}

    monkeypatch.setattr(persistent_orchestrator_module, "PersistentEngineeringSession", EngineeringSession)
    orchestrator = PersistentRuntimeOrchestrator(repo_root=tmp_path, workspace_dir=tmp_path / "workspace")
    record = RuntimeSessionResumeRecord(session_id="session-a", status="resumable", workspace_root=str(tmp_path))

    orchestrator._record_persistent_engineering_resume(
        agent_loop=None,
        record=record,
        resume_plan={"lineage_by_task_id": {"task-a": _lineage()}},
        continuation_plan={},
        repository_updates=[],
        scheduler_updates=[],
    )

    assert captured["cursor"]["runtime_session_id"] == "runtime-a"
    assert captured["cursor"]["runtime_session_id"] != record.session_id


def test_persistent_resume_rejects_multiple_runtime_session_identities(monkeypatch, tmp_path) -> None:
    class EngineeringSession:
        def __init__(self, **_kwargs):
            raise AssertionError("conflicting identity must be rejected before session creation")

    monkeypatch.setattr(persistent_orchestrator_module, "PersistentEngineeringSession", EngineeringSession)
    orchestrator = PersistentRuntimeOrchestrator(repo_root=tmp_path, workspace_dir=tmp_path / "workspace")
    record = RuntimeSessionResumeRecord(session_id="session-a", status="resumable", workspace_root=str(tmp_path))
    second = {**_lineage(), "runtime_session_id": "runtime-b"}

    result = orchestrator._record_persistent_engineering_resume(
        agent_loop=None,
        record=record,
        resume_plan={"lineage_by_task_id": {"task-a": _lineage(), "task-b": second}},
        continuation_plan={},
        repository_updates=[],
        scheduler_updates=[],
    )

    assert result["ok"] is False
    assert result["reason"] == "persistent_engineering_session_record_failed"
    assert "resume_plan_conflicting_runtime_session_identity" in result["error"]


def test_recovery_continuation_rejects_conflicting_source_session_before_handler() -> None:
    handler_calls = []

    def handler(plan, context):
        handler_calls.append(copy.deepcopy(context))
        return {"ok": True, "source_state": context["source_state"]}

    state = {**_lineage(), "status": "failed", "source_session_id": "source-a"}
    state["metadata"] = {"source_session_id": "source-drift"}
    execution = {
        "execution_id": "execution-a",
        "recovery_id": "recovery-a",
        "source_session_id": "source-a",
        "status": RECOVERY_EXECUTION_STATUS_COMPLETED,
        "continuation_decision": RECOVERY_CONTINUATION_READY,
        "verification_snapshot": {"verified": True},
        "recovery_chain_status": "verified",
    }
    layer = RuntimeRecoveryContinuationLayer(handler=handler)

    plan = layer.plan_continuation(execution, source_state=state, approval={"approved": True})
    result = layer.apply_continuation(plan, approval={"approved": True})

    assert result.applied is False
    assert handler_calls == []


def test_execution_recovery_incident_does_not_alias_source_as_runtime_session() -> None:
    fabric = RuntimeExecutionFabric()
    record = fabric.start_execution(
        source_session_id="source-a",
        task_id="task-a",
        metadata={"session_id": "session-a", "runtime_session_id": "runtime-a"},
    )

    incident = fabric.create_recovery_incident(record.execution_id)

    assert incident["source_session_id"] == "source-a"
    assert incident["session_id"] == "session-a"
    assert incident["runtime_session_id"] == "runtime-a"


def test_transaction_recovery_incident_does_not_alias_source_as_runtime_session() -> None:
    fabric = RuntimeTransactionFabric()
    record = fabric.begin_transaction(
        source_session_id="source-a",
        task_id="task-a",
        metadata={"session_id": "session-a", "runtime_session_id": "runtime-a"},
    )

    incident = fabric.create_recovery_incident(record.transaction_id)

    assert incident["source_session_id"] == "source-a"
    assert incident["session_id"] == "session-a"
    assert incident["runtime_session_id"] == "runtime-a"
