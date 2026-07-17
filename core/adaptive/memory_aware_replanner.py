from __future__ import annotations

"""Thin adapter that injects read-only memory context into one replanner."""

import inspect
from typing import Any, Mapping

from core.adaptive.adaptive_contract import AdaptiveDecision, DeviationReport
from core.adaptive.adaptive_memory_context import AdaptiveMemoryContext, AdaptiveMemoryContextBuilder


class MemoryAwareReplanner:
    def __init__(
        self,
        replanner: Any,
        memory_context_builder: AdaptiveMemoryContextBuilder | None = None,
    ) -> None:
        self.replanner = replanner
        self.memory_context_builder = memory_context_builder or AdaptiveMemoryContextBuilder()
        self.last_memory_context: AdaptiveMemoryContext | None = None

    def decide(
        self,
        report: DeviationReport,
        *,
        step: Mapping[str, Any],
        retry_count: int = 0,
        replan_count: int = 0,
        adaptive_memory_context: AdaptiveMemoryContext | Mapping[str, Any] | None = None,
    ) -> AdaptiveDecision:
        context = adaptive_memory_context or self.memory_context_builder.build(report)
        self.last_memory_context = context if isinstance(context, AdaptiveMemoryContext) else None
        kwargs = {
            "step": step,
            "retry_count": retry_count,
            "replan_count": replan_count,
        }
        if self._accepts_memory_context():
            kwargs["adaptive_memory_context"] = context
        return self.replanner.decide(report, **kwargs)

    def revise(self, **kwargs: Any) -> Any:
        return self.replanner.revise(**kwargs)

    def _accepts_memory_context(self) -> bool:
        try:
            parameters = inspect.signature(self.replanner.decide).parameters
        except (TypeError, ValueError):
            return False
        return "adaptive_memory_context" in parameters or any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        )


__all__ = ["MemoryAwareReplanner"]
