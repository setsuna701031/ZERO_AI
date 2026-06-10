from __future__ import annotations

"""Thin adapter that injects read-only memory context into an existing planner."""

import copy
from typing import Any, Mapping

from core.planning.memory_context import MemoryContext, MemoryContextBuilder


def inject_memory_context(
    context: Mapping[str, Any] | None,
    *,
    user_input: str = "",
    memory_context: MemoryContext | Mapping[str, Any] | None = None,
    memory_context_builder: MemoryContextBuilder | None = None,
) -> dict[str, Any]:
    planner_context = copy.deepcopy(dict(context)) if isinstance(context, Mapping) else {}
    if memory_context is None and memory_context_builder is not None:
        memory_context = memory_context_builder.build(
            task_id=str(planner_context.get("task_id") or planner_context.get("id") or "").strip(),
            goal=str(user_input or planner_context.get("goal") or planner_context.get("user_input") or "").strip(),
        )
    if isinstance(memory_context, MemoryContext):
        planner_context["memory_context"] = memory_context.to_dict()
    elif isinstance(memory_context, Mapping):
        planner_context["memory_context"] = copy.deepcopy(dict(memory_context))
    return planner_context


class MemoryAwarePlanner:
    """Delegates planning unchanged after preparing planner input context."""

    def __init__(self, planner: Any, memory_context_builder: MemoryContextBuilder | None = None) -> None:
        self.planner = planner
        self.memory_context_builder = memory_context_builder or MemoryContextBuilder()

    def plan(
        self,
        context: Mapping[str, Any] | None = None,
        user_input: str = "",
        route: Any = None,
        *,
        memory_context: MemoryContext | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        planner_context = inject_memory_context(
            context,
            user_input=user_input,
            memory_context=memory_context,
            memory_context_builder=self.memory_context_builder,
        )
        return self.planner.plan(context=planner_context, user_input=user_input, route=route, **kwargs)

    def run(self, *args: Any, **kwargs: Any) -> Any:
        return self.plan(*args, **kwargs)


__all__ = ["MemoryAwarePlanner", "inject_memory_context"]
