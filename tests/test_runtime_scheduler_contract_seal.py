from __future__ import annotations

import copy
from pathlib import Path

import pytest

from core.runtime.runtime_dispatcher import RuntimeDispatcher
from core.runtime.runtime_authority_seal import is_dispatch_execution_capability
from core.runtime.work_package_queue import RuntimePackageQueue, RuntimePackageQueueError
from core.tasks.scheduler_runtime_contract import (
    SchedulerRuntimeContractError,
    seal_scheduler_runtime_contract,
    validate_scheduler_lifecycle_transition,
    validate_scheduler_runtime_contract,
)


def _authority() -> dict:
    return {
        "authority_source": "human_review",
        "authority_status": "allowed",
        "execution_authority_endpoint": "step_executor",
    }


def _payload() -> dict:
    return {
        "package_id": "package-seal",
        "session_id": "session-seal",
        "task_id": "task-seal",
        "execution_authority": _authority(),
    }


def test_scheduler_identity_contract_seal() -> None:
    contract = seal_scheduler_runtime_contract(
        _payload(),
        lifecycle_state="executing",
        dispatch_path="Scheduler -> RuntimeDispatcher -> TaskRunner -> StepExecutor",
        require_package_identity=True,
        require_session_identity=True,
    )
    assert contract["package_id"] == "package-seal"
    assert contract["session_id"] == "session-seal"
    assert contract["task_id"] == "task-seal"
    assert validate_scheduler_runtime_contract(contract)["ok"] is True


def test_scheduler_lifecycle_rejects_completion_before_executing() -> None:
    for state in ("planned", "queued", "claimed"):
        assert validate_scheduler_lifecycle_transition(state, "completed") is False
    assert validate_scheduler_lifecycle_transition("claimed", "executing") is True
    assert validate_scheduler_lifecycle_transition("executing", "completed") is True


def test_scheduler_authority_contract_rejects_missing_metadata() -> None:
    payload = _payload()
    payload.pop("execution_authority")
    with pytest.raises(SchedulerRuntimeContractError, match="authority_metadata_missing"):
        seal_scheduler_runtime_contract(
            payload,
            lifecycle_state="executing",
            dispatch_path="Scheduler -> RuntimeDispatcher -> TaskRunner -> StepExecutor",
            require_authority_metadata=True,
        )


def test_runtime_dispatcher_contract_preserves_identity_authority_and_path(tmp_path: Path) -> None:
    queue = RuntimePackageQueue(repo_root=tmp_path)
    dispatcher = RuntimeDispatcher(queue=queue, task_runner=object(), workspace_root=tmp_path)
    record = {
        **_payload(),
        "runtime_queue_item": {"steps": [{"type": "inspect"}]},
    }
    task = dispatcher._execution_task(record)
    contract = task["scheduler_runtime_contract"]
    assert contract["package_id"] == task["package_id"]
    assert contract["session_id"] == task["session_id"]
    assert contract["task_id"] == task["task_id"]
    assert contract["authority"] == task["execution_authority"]
    assert contract["dispatch_path"] == "RuntimeDispatcher -> TaskRunner -> StepExecutor"


def test_scheduler_boundary_preserves_previous_evidence_and_parent_identity(tmp_path: Path) -> None:
    from core.tasks.scheduler import Scheduler

    calls = []

    class Runner:
        def run_task(self, task, current_tick=0):
            calls.append(copy.deepcopy(task))
            return {"ok": True, "runtime_state": {"final_result": {"ok": True}}}

    scheduler = Scheduler(workspace_dir=str(tmp_path), task_runner=Runner(), debug=False)
    task = {
        **_payload(),
        "status": "running",
        "current_step_index": 1,
        "last_step_result": {"result": {"content": "evidence-kept"}},
        "results": [{"ok": True}],
        "steps": [{"type": "write_file"}, {"type": "verify", "contains": "evidence-kept"}],
    }
    scheduler._run_step_via_task_runner(task=task, step=task["steps"][1])
    boundary = calls[0]
    assert boundary["scheduler_task_id"] == "task-seal"
    assert boundary["package_id"] == "package-seal"
    assert boundary["session_id"] == "session-seal"
    assert boundary["last_step_result"] == task["last_step_result"]
    assert boundary["scheduler_runtime_contract"]["lifecycle_state"] == "executing"
    assert boundary["scheduler_runtime_contract"]["dispatch_path"] == (
        "Scheduler -> RuntimeDispatcher -> TaskRunner -> StepExecutor"
    )
    assert boundary["runtime_dispatcher_handoff"]["capability_issuer"] == "RuntimeDispatcher"
    assert is_dispatch_execution_capability(
        boundary["runtime_execution_capability"],
        task_id="task-seal",
    )


def test_queue_direct_completion_is_illegal_before_executing(tmp_path: Path) -> None:
    queue = RuntimePackageQueue(repo_root=tmp_path)
    queue._write(
        {
            "package_id": "illegal-complete",
            "status": "queued",
            "runtime_lifecycle_state": "planned",
        }
    )
    record = queue.status("illegal-complete")
    with pytest.raises(RuntimePackageQueueError, match="invalid_runtime_lifecycle_transition"):
        queue._runtime_transition(record, "completed", reason="illegal_direct_completion")


def test_duplicate_replan_request_and_append_are_idempotent(tmp_path: Path) -> None:
    queue = RuntimePackageQueue(repo_root=tmp_path)
    queue._write(
        {
            "package_id": "duplicate-replan",
            "task_id": "task-duplicate-replan",
            "status": "running",
            "runtime_lifecycle_state": "executing",
            "runtime_queue_item": {"steps": [{"id": "original", "type": "inspect"}]},
            "replan_requests": [],
            "replan_history": [],
        }
    )
    request = {"request_id": "replan-request-1", "root_cause": "recoverable"}

    queue.record_replan_request("duplicate-replan", request)
    duplicate_request = queue.record_replan_request("duplicate-replan", request)
    first_append = queue.append_replan_steps(
        "duplicate-replan",
        request=request,
        steps=[{"id": "repair", "type": "inspect"}],
        replan_snapshot={"schema": "test", "planning_status": "ready"},
    )
    duplicate_append = queue.append_replan_steps(
        "duplicate-replan",
        request=request,
        steps=[{"id": "repair", "type": "inspect"}],
        replan_snapshot={"schema": "test", "planning_status": "ready"},
    )

    assert len(duplicate_request["replan_requests"]) == 1
    assert duplicate_request["duplicate_replan_request_rejected"] == "replan-request-1"
    assert len(first_append["runtime_queue_item"]["steps"]) == 2
    assert len(duplicate_append["runtime_queue_item"]["steps"]) == 2
    assert len(duplicate_append["replan_history"]) == 1
    assert duplicate_append["duplicate_replan_append_rejected"] == "replan-request-1"
