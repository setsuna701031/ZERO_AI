from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from core.tasks.execution_gateway_runtime import run_scheduler_execution_gateway


@dataclass(frozen=True)
class SchedulerExecutionGatewayResult:
    ok: bool
    step: Dict[str, Any]
    result: Dict[str, Any]
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    used_gateway: bool = False
    used_legacy_fallback: bool = False
    runtime_error: Optional[str] = None


def run_scheduler_step_execution_gateway(
    executor: Any,
    step: Any,
    *,
    method_name: str = "execute",
    legacy_result: Optional[Mapping[str, Any]] = None,
    allow_legacy_fallback: bool = True,
    trace: bool = True,
) -> SchedulerExecutionGatewayResult:
    runtime_result = run_scheduler_execution_gateway(
        executor,
        step,
        method_name=method_name,
        legacy_result=legacy_result,
        allow_legacy_fallback=allow_legacy_fallback,
        trace=trace,
    )

    result = dict(runtime_result.result)
    step_payload = dict(runtime_result.step)

    result["scheduler_execution_gateway_layer"] = "scheduler_execution_gateway.v1"
    step_payload["scheduler_execution_gateway_layer"] = "scheduler_execution_gateway.v1"

    return SchedulerExecutionGatewayResult(
        ok=runtime_result.ok,
        step=step_payload,
        result=result,
        errors=list(runtime_result.errors),
        warnings=list(runtime_result.warnings),
        used_gateway=runtime_result.used_gateway,
        used_legacy_fallback=runtime_result.used_legacy_fallback,
        runtime_error=runtime_result.runtime_error,
    )


def export_scheduler_step_execution_result(
    executor: Any,
    step: Any,
    *,
    method_name: str = "execute",
    legacy_result: Optional[Mapping[str, Any]] = None,
    allow_legacy_fallback: bool = True,
    trace: bool = True,
) -> Dict[str, Any]:
    return run_scheduler_step_execution_gateway(
        executor,
        step,
        method_name=method_name,
        legacy_result=legacy_result,
        allow_legacy_fallback=allow_legacy_fallback,
        trace=trace,
    ).result