from __future__ import annotations

from typing import Any

from core.runtime.step_executor import StepExecutor
from core.runtime.task_runner import TaskRunner


class OwnedStepExecutor:
    """Test facade that exercises StepExecutor only through TaskRunner ownership."""

    def __init__(self, endpoint: StepExecutor) -> None:
        self.endpoint = endpoint
        self.runner = TaskRunner(step_executor=endpoint)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.endpoint, name)

    def execute_step(self, step: dict[str, Any], task: dict[str, Any] | None = None, **kwargs: Any):
        return self.runner.execute_owned_step(step, task=task, **kwargs)

    def execute_steps(self, steps: list[dict[str, Any]], task: dict[str, Any] | None = None, **kwargs: Any):
        return self.runner.execute_owned_steps(steps, task=task, context=kwargs.get("context"))


def owned_step_executor(*args: Any, **kwargs: Any) -> OwnedStepExecutor:
    return OwnedStepExecutor(StepExecutor(*args, **kwargs))
