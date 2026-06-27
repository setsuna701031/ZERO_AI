from __future__ import annotations

from typing import Any, Callable

from core.runtime.operator_registry_service import get_operator_registry_service
from core.tasks.scheduler_core.scheduler_completion import (
    complete_operator,
    mark_completed_steps_fallback,
    mark_failed_if_ok_without_completion,
    mark_failed_step_if_needed,
    mark_operator_complete_if_ok,
    mark_operator_complete_or_failed,
    run_operator_completion_pipeline,
    task_from_args,
    task_id,
)


RegistryFactory = Callable[[], Any]


def _registry_factory(registry_factory: RegistryFactory | None) -> RegistryFactory:
    return registry_factory or get_operator_registry_service


def _zero_scheduler_task_from_args(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    return task_from_args(args, kwargs)


def _zero_scheduler_task_id(task: dict[str, Any]) -> str:
    return task_id(task)


def _zero_scheduler_mark_completed_steps_fallback(
    owner: Any,
    task: dict[str, Any],
    step_id: str,
) -> bool:
    return mark_completed_steps_fallback(owner, task, step_id)


def _zero_scheduler_complete_operator(
    owner: Any,
    task: dict[str, Any],
    result: dict[str, Any],
    *,
    outcome: str = "complete",
    registry_factory: RegistryFactory | None = None,
) -> bool:
    return complete_operator(
        owner,
        task,
        result,
        outcome=outcome,
        registry_factory=_registry_factory(registry_factory),
    )


def _zero_scheduler_mark_operator_complete_if_ok(
    task: dict[str, Any],
    result: dict[str, Any],
    *,
    registry_factory: RegistryFactory | None = None,
) -> None:
    return mark_operator_complete_if_ok(
        task,
        result,
        registry_factory=_registry_factory(registry_factory),
    )


def _zero_scheduler_mark_operator_complete_or_failed(
    task: dict[str, Any],
    result: dict[str, Any],
    *,
    registry_factory: RegistryFactory | None = None,
) -> None:
    return mark_operator_complete_or_failed(
        task,
        result,
        registry_factory=_registry_factory(registry_factory),
    )


def _zero_scheduler_mark_failed_step_if_needed(
    task: dict[str, Any],
    result: dict[str, Any],
    *,
    registry_factory: RegistryFactory | None = None,
) -> None:
    return mark_failed_step_if_needed(
        task,
        result,
        registry_factory=_registry_factory(registry_factory),
    )


def _zero_scheduler_mark_failed_if_ok_without_completion(
    task: dict[str, Any],
    result: dict[str, Any],
    *,
    registry_factory: RegistryFactory | None = None,
) -> None:
    return mark_failed_if_ok_without_completion(
        task,
        result,
        registry_factory=_registry_factory(registry_factory),
    )


def _zero_scheduler_run_operator_completion_pipeline(
    task: dict[str, Any],
    result: dict[str, Any],
    *,
    mode: str = "all",
    registry_factory: RegistryFactory | None = None,
) -> None:
    return run_operator_completion_pipeline(
        task,
        result,
        mode=mode,
        registry_factory=_registry_factory(registry_factory),
    )


def run_zero_scheduler_run_one_step_v16(
    owner: Any,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    *,
    base_run_one_step: Callable[..., Any],
    run_operator_completion_pipeline: Callable[..., Any] = _zero_scheduler_run_operator_completion_pipeline,
    task_from_args_func: Callable[[tuple[Any, ...], dict[str, Any]], Any] = _zero_scheduler_task_from_args,
) -> Any:
    result = base_run_one_step(owner, *args, **kwargs)
    run_operator_completion_pipeline(
        task_from_args_func(args, kwargs),
        result,
        mode="missing_completion",
    )
    return result
