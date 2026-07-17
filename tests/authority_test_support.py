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
from core.runtime.runtime_dispatcher import RuntimeDispatcher
from core.runtime.runtime_execution_authority import propagate_runtime_capability
from core.goals.goal_lineage_contract import (
    attach_goal_lineage,
    attach_runtime_identity_graph,
    bind_runtime_identity_graph,
    create_root_goal_lineage,
    extract_goal_lineage,
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
        return sealed_dispatch_task(task)


def sealed_dispatch_task(task: dict[str, Any] | None) -> dict[str, Any]:
    owned = dict(task or {})
    task_id = str(owned.get("task_id") or owned.get("id") or "test-dispatch-task")
    package_id = str(owned.get("package_id") or owned.get("work_package_id") or "test-dispatch-package")
    try:
        lineage = extract_goal_lineage(owned, require_complete=True, reject_conflicts=True)
    except ValueError:
        lineage = create_root_goal_lineage(
            goal_id=str(owned.get("goal_id") or task_id),
            session_id=str(owned.get("session_id") or owned.get("runtime_session") or "") or None,
            runtime_session_id=str(owned.get("runtime_session_id") or "") or None,
        )
    owned.update({"task_id": task_id, "package_id": package_id, "session_id": lineage["session_id"]})
    owned = attach_goal_lineage(owned, lineage)
    owned = RuntimeDispatcher._attach_execution_identity(owned)
    provenance = RuntimeDispatcher._capability_provenance(owned)
    owned.update(propagate_runtime_capability({}, provenance, stage="dispatcher"))
    owned = attach_runtime_identity_graph(
        owned,
        bind_runtime_identity_graph(
            owned["runtime_identity_graph"], capability_id=provenance.capability_id
        ),
    )
    owned["runtime_execution_capability"] = RuntimeDispatcher._execution_capability(owned)
    owned["runtime_system_capability"] = RuntimeDispatcher._system_execution_capability(owned)
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
