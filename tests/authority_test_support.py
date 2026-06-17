from __future__ import annotations

from typing import Any

from core.runtime.step_executor import StepExecutor
from core.runtime.task_runner import TaskRunner
from core.runtime.runtime_authority_seal import (
    _RUNTIME_DISPATCHER_ISSUER_TOKEN,
    _TASK_RUNNER_ISSUER_TOKEN,
    delegate_taskrunner_execution_capability,
    issue_dispatch_execution_capability,
    issue_terminal_execution_evidence,
)


class OwnedStepExecutor:
    """Test facade that exercises StepExecutor only through TaskRunner ownership."""

    def __init__(self, endpoint: StepExecutor) -> None:
        self.endpoint = endpoint
        self.runner = TaskRunner(step_executor=endpoint)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.endpoint, name)

    def execute_step(self, step: dict[str, Any], task: dict[str, Any] | None = None, **kwargs: Any):
        owned_task = self._dispatcher_task(task)
        return self.runner.execute_owned_step(step, task=owned_task, **kwargs)

    def execute_steps(self, steps: list[dict[str, Any]], task: dict[str, Any] | None = None, **kwargs: Any):
        owned_task = self._dispatcher_task(task)
        return self.runner.execute_owned_steps(steps, task=owned_task, context=kwargs.get("context"))

    @staticmethod
    def _dispatcher_task(task: dict[str, Any] | None) -> dict[str, Any]:
        owned = dict(task or {})
        task_id = str(owned.get("task_id") or owned.get("id") or "test-dispatch-task")
        package_id = str(owned.get("package_id") or owned.get("work_package_id") or "test-dispatch-package")
        session_id = str(owned.get("session_id") or owned.get("runtime_session") or "test-dispatch-session")
        owned.update({"task_id": task_id, "package_id": package_id, "session_id": session_id})
        owned["runtime_execution_capability"] = issue_dispatch_execution_capability(
            _RUNTIME_DISPATCHER_ISSUER_TOKEN,
            task_id=task_id,
            package_id=package_id,
            session_id=session_id,
        )
        return owned


def owned_step_executor(*args: Any, **kwargs: Any) -> OwnedStepExecutor:
    return OwnedStepExecutor(StepExecutor(*args, **kwargs))


def live_terminal_evidence_for_test(
    task: dict[str, Any],
    *,
    step_id: str = "test-terminal",
) -> Any:
    """Issue live terminal evidence for tests that need a legal finish event."""
    task_id = str(task.get("task_id") or task.get("id") or "test-dispatch-task")
    package_id = str(task.get("package_id") or task.get("work_package_id") or "test-dispatch-package")
    session_id = str(task.get("session_id") or task.get("runtime_session") or "test-dispatch-session")
    task.update({"task_id": task_id, "package_id": package_id, "session_id": session_id})
    dispatch = task.get("runtime_execution_capability")
    if dispatch is None:
        dispatch = issue_dispatch_execution_capability(
            _RUNTIME_DISPATCHER_ISSUER_TOKEN,
            task_id=task_id,
            package_id=package_id,
            session_id=session_id,
        )
        task["runtime_execution_capability"] = dispatch
    delegated = delegate_taskrunner_execution_capability(
        _TASK_RUNNER_ISSUER_TOKEN,
        dispatch,
        task_id=task_id,
        step_id=step_id,
    )
    return issue_terminal_execution_evidence(
        _TASK_RUNNER_ISSUER_TOKEN,
        delegated,
        task_id=task_id,
        package_id=package_id,
        session_id=session_id,
        step_id=step_id,
    )
