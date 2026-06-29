from __future__ import annotations

from pathlib import Path
from typing import Any
import pytest

pytestmark = [pytest.mark.contract]




def test_scheduler_authority_context_is_orchestration_only(tmp_path: Path) -> None:
    scheduler = _make_scheduler(tmp_path)
    execution_authority = _execution_authority(action_type="mutation")

    context = scheduler._build_scheduler_authority_context(
        {
            "task_id": "task-scheduler-authority",
            "authority_propagation_required": True,
            "execution_authority": execution_authority,
        }
    )

    assert context["authority_phase"] == "scheduler_dispatch"
    assert context["authority_layer"] == "scheduler"
    assert context["authority_role"] == "orchestration"
    assert context["execution_authority_granted"] is False
    assert context["can_execute_privileged_step"] is False
    assert context["escalated"] is False
    assert context["execution_authority"] == execution_authority
    assert context["execution_authority"]["authority_source"] == "human_review"
    assert context["authority_chain"][-1]["layer"] == "scheduler"
    assert context["authority_chain"][-1]["execution_authority_granted"] is False


def test_scheduler_task_intake_preserves_explicit_execution_authority(tmp_path: Path) -> None:
    scheduler = _make_scheduler(tmp_path)
    authority = _execution_authority(action_type="mutation")

    result = scheduler._create_task_record(
        "authority intake :: step=write_file:shared/intake.txt|authorized",
        initial_status="queued",
        execution_authority=authority,
        authority_propagation_required=True,
        operator_session_id="operator-authority-intake",
    )

    task = scheduler._get_task_from_repo(result["task"]["task_id"])
    assert task["execution_authority"] == authority
    assert task["authority_propagation_required"] is True
    assert task["operator_session_id"] == "operator-authority-intake"


def test_approved_non_repair_scheduler_task_completes_without_new_review(tmp_path: Path) -> None:
    scheduler = _make_scheduler(tmp_path)
    authority = _execution_authority(action_type="mutation")
    result = scheduler._create_task_record(
        "authorized completion :: step=write_file:shared/completion.txt|authorized :: step=verify:contains=authorized",
        initial_status="queued",
        execution_authority=authority,
        authority_propagation_required=True,
    )
    task_id = result["task"]["task_id"]

    for _ in range(4):
        scheduler.tick()
        task = scheduler._get_task_from_repo(task_id)
        if task["status"] == "finished":
            break

    assert task["status"] == "finished"
    assert task["current_step_index"] == 2
    assert task["requires_review"] is False
    assert task["replan_count"] == 0


def test_taskrunner_propagates_authority_without_escalation(tmp_path: Path) -> None:
    from core.runtime.runtime_dispatcher import RuntimeDispatcher
    from core.runtime.task_runner import TaskRunner

    scheduler_context = _make_scheduler(tmp_path)._build_scheduler_authority_context(
        {
            "task_id": "task-taskrunner-authority",
            "authority_propagation_required": True,
            "execution_authority": _execution_authority(action_type="mutation"),
        }
    )
    runner = TaskRunner(step_executor=_RecordingStepExecutor(), debug=False)

    context = runner._build_taskrunner_authority_context(
        task={
            "task_id": "task-taskrunner-authority",
            "authority_context": scheduler_context,
            "runtime_execution_capability": RuntimeDispatcher._execution_capability(
                {
                    "task_id": "task-taskrunner-authority",
                    "package_id": "",
                    "session_id": "",
                }
            ),
        },
        state={"current_step_index": 0},
        step={"type": "write_file"},
        upstream_context={},
    )

    assert context["authority_phase"] == "taskrunner_delegation"
    assert context["authority_layer"] == "task_runner"
    assert context["authority_role"] == "canonical_delegation"
    assert context["execution_authority_granted"] is False
    assert context["can_execute_privileged_step"] is True
    assert context["escalated"] is False
    assert context["execution_authority"]["descriptive_only"] is True
    assert [item["layer"] for item in context["authority_chain"]] == [
        "scheduler",
        "task_runner",
    ]
    assert all(
        item["execution_authority_granted"] is False
        for item in context["authority_chain"]
    )


def test_scheduler_side_effect_dispatch_delegates_to_step_executor(
    tmp_path: Path,
) -> None:
    recorder = _RecordingStepExecutor()
    scheduler = _make_scheduler(tmp_path, step_executor=recorder)
    task_dir = tmp_path / "tasks" / "task-side-effect"
    task_dir.mkdir(parents=True)
    target = tmp_path / "shared" / "scheduler-must-not-write.txt"

    result = scheduler._execute_simple_step(
        task={
            "task_id": "task-side-effect",
            "task_dir": str(task_dir),
            "authority_propagation_required": True,
            "execution_authority": _execution_authority(action_type="mutation"),
        },
        step={
            "type": "write_file",
            "path": "workspace/shared/scheduler-must-not-write.txt",
            "content": "scheduler should not write directly",
        },
    )

    assert result["source"] == "step_executor"
    assert recorder.calls
    assert recorder.calls[0]["step"]["type"] == "write_file"
    assert recorder.calls[0]["context"]["authority_context"]["authority_layer"] == "task_runner"
    assert recorder.calls[0]["context"]["authority_context"][
        "execution_authority_granted"
    ] is False
    assert not target.exists()


def test_step_executor_is_execution_authority_endpoint_with_valid_authority(
    tmp_path: Path,
) -> None:
    from tests.authority_test_support import owned_step_executor

    executor = owned_step_executor(workspace_root=str(tmp_path))
    result = executor.execute_step(
        step={
            "type": "write_file",
            "path": "workspace/shared/endpoint.txt",
            "content": "endpoint authority",
        },
        context={"execution_authority": _execution_authority(action_type="mutation")},
    )

    assert result["ok"] is True
    assert result["authority_decision"]["authority_phase"] == "pre_execution"
    assert result["authority_decision"]["decision"] == "allowed"
    assert result["authority_decision"]["authority_source"] == "task_runner"
    assert result["authority_decision"]["sealed"] is True
    endpoint_path = Path(result["result"]["result"]["full_path"])
    assert endpoint_path.read_text(encoding="utf-8") == (
        "endpoint authority"
    )


def test_missing_or_invalid_authority_blocks_before_execution(
    tmp_path: Path,
) -> None:
    from core.runtime.step_executor import StepExecutor

    executor = StepExecutor(workspace_root=str(tmp_path))

    missing = executor.execute_step(
        step={
            "type": "write_file",
            "path": "workspace/shared/missing.txt",
            "content": "must not write",
        },
        context={"authority_propagation_required": True},
    )
    invalid = executor.execute_step(
        step={
            "type": "write_file",
            "path": "workspace/shared/invalid.txt",
            "content": "must not write",
        },
        context={
            "authority_propagation_required": True,
            "authority_context": {
                "authority_layer": "scheduler",
                "execution_authority": {
                    **_execution_authority(action_type="mutation"),
                    "authority_source": "scheduler",
                },
            },
        },
    )

    for result in (missing, invalid):
        assert result["ok"] is False
        assert result["executed"] is False
        assert result["blocked"] is True
        assert result["error"]["type"] == "execution_authority_denied"
        assert result["authority_decision"]["authority_phase"] == "pre_execution"
        assert result["authority_decision"]["decision"] == "denied"

    assert not (tmp_path / "shared" / "missing.txt").exists()
    assert not (tmp_path / "shared" / "invalid.txt").exists()


def _make_scheduler(tmp_path: Path, step_executor: Any | None = None) -> Any:
    from core.tasks.scheduler import Scheduler

    return Scheduler(
        workspace_dir=str(tmp_path),
        step_executor=step_executor,
        allow_commands=True,
        debug=False,
    )


def _execution_authority(*, action_type: str) -> dict[str, Any]:
    return {
        "authority_source": "human_review",
        "authority_status": "allowed",
        "execution_authority_endpoint": "step_executor",
        "action_type": action_type,
        "ownership_source": "human_review",
        "authority_scope": "step_executor_side_effect",
        "task_id": "task-authority",
        "step_id": "step-authority",
        "runtime_session": "session-authority",
        "approval_state": "approved",
        "policy_result": {"allowed": True, "decision": "allow"},
        "trace_id": "trace-authority",
    }


class _RecordingStepExecutor:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def execute_step(
        self,
        *,
        step: dict[str, Any],
        task: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "step": step,
                "task": task,
                "context": context,
                "kwargs": kwargs,
            }
        )
        return {
            "ok": True,
            "source": "step_executor",
            "step_type": str(step.get("type") or ""),
            "authority_decision": {
                "authority_phase": "pre_execution",
                "authority_required": True,
                "action_type": "mutation",
                "step_type": str(step.get("type") or ""),
                "decision": "allowed",
                "authority_source": "human_review",
                "sealed": False,
                "reason": "explicit_step_executor_authority",
            },
        }
