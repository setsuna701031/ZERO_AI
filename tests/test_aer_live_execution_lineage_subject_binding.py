from __future__ import annotations

from pathlib import Path

import pytest

from core.runtime.runtime_dispatcher import RuntimeDispatcher
from core.runtime.runtime_authority_seal import (
    is_taskrunner_execution_capability,
)
from core.runtime.step_executor import StepExecutor
from core.runtime.task_runner import TaskRunner
from tests.authority_test_support import sealed_dispatch_task


def _dispatcher_task(task_id: str = "task-a") -> dict:
    package_id = "package-a"
    session_id = "session-a"
    return sealed_dispatch_task({
        "task_id": task_id,
        "package_id": package_id,
        "session_id": session_id,
        "runtime_execution_capability": RuntimeDispatcher._execution_capability(
            {
                "task_id": task_id,
                "package_id": package_id,
                "session_id": session_id,
            }
        ),
    })


def test_taskrunner_rejects_execution_without_live_dispatcher_capability(tmp_path: Path) -> None:
    result = TaskRunner(step_executor=StepExecutor(workspace_root=str(tmp_path))).execute_owned_step(
        {"id": "command-a", "type": "command", "command": "echo must-not-run"},
        task={"task_id": "task-a"},
    )

    assert result["ok"] is False
    assert result["executed"] is False
    assert result["blocked"] is True
    assert result["authority_decision"]["decision"] == "denied"


def test_step_executor_rejects_cross_task_live_capability(tmp_path: Path) -> None:
    runner = TaskRunner(step_executor=StepExecutor(workspace_root=str(tmp_path)))
    task_a = _dispatcher_task("task-a")
    authority_context = runner._build_taskrunner_authority_context(
        task=task_a,
        state={},
        step={"id": "command-a", "type": "command"},
    )

    result = StepExecutor(workspace_root=str(tmp_path)).execute_step(
        {"id": "command-a", "type": "command", "command": "echo must-not-run"},
        task={"task_id": "task-b", "package_id": "package-a", "session_id": "session-a"},
        context={
            "runtime_execution_capability": authority_context["runtime_execution_capability"],
            "authority_propagation_required": True,
        },
    )

    assert result["ok"] is False
    assert result["executed"] is False
    assert result["blocked"] is True
    assert result["authority_decision"]["decision"] == "denied"


@pytest.mark.parametrize(
    ("field", "wrong_value"),
    [("package_id", "package-b"), ("session_id", "session-b")],
)
def test_step_executor_rejects_cross_package_or_session_live_capability(
    tmp_path: Path,
    field: str,
    wrong_value: str,
) -> None:
    runner = TaskRunner(step_executor=StepExecutor(workspace_root=str(tmp_path)))
    task = _dispatcher_task()
    authority_context = runner._build_taskrunner_authority_context(
        task=task,
        state={},
        step={"id": "command-a", "type": "command"},
    )
    mismatched_task = {"task_id": "task-a", "package_id": "package-a", "session_id": "session-a"}
    mismatched_task[field] = wrong_value

    result = StepExecutor(workspace_root=str(tmp_path)).execute_step(
        {"id": "command-a", "type": "command", "command": "echo must-not-run"},
        task=mismatched_task,
        context={
            "runtime_execution_capability": authority_context["runtime_execution_capability"],
            "authority_propagation_required": True,
        },
    )

    assert result["ok"] is False
    assert result["executed"] is False
    assert result["authority_decision"]["decision"] == "denied"


def test_valid_dispatcher_capability_with_matching_subjects_executes(tmp_path: Path) -> None:
    task = _dispatcher_task()
    runner = TaskRunner(step_executor=StepExecutor(workspace_root=str(tmp_path)))
    authority_context = runner._build_taskrunner_authority_context(
        task=task,
        state={},
        step={"id": "command-a", "type": "command"},
    )

    assert is_taskrunner_execution_capability(
        authority_context["runtime_execution_capability"],
        task_id="task-a",
        step_id="command-a",
        package_id="package-a",
        session_id="session-a",
    )

    result = runner.execute_owned_step(
        {"id": "command-a", "type": "command", "command": "echo sealed"},
        task=task,
    )

    assert result["ok"] is True
    assert result["executed"] is True
    assert result["authority_decision"]["decision"] == "allowed"
