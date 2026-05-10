from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from core.tasks.execution_gateway import (
    build_noop_execution_result,
    call_execution_gateway,
)


@dataclass(frozen=True)
class ExecutionGatewayRuntimeResult:
    ok: bool
    step: Dict[str, Any]
    result: Dict[str, Any]
    legacy_result: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    used_gateway: bool = False
    used_legacy_fallback: bool = False
    runtime_error: Optional[str] = None


def run_scheduler_execution_gateway(
    executor: Any,
    raw_step: Any,
    *,
    method_name: str = "execute",
    legacy_result: Optional[Mapping[str, Any]] = None,
    allow_legacy_fallback: bool = True,
    trace: bool = True,
) -> ExecutionGatewayRuntimeResult:
    gateway_result = call_execution_gateway(
        executor,
        raw_step,
        method_name=method_name,
        trace=trace,
    )

    if gateway_result.ok:
        step = _scheduler_safe_step(gateway_result.step)
        result = _scheduler_safe_result(gateway_result.result)
        step["scheduler_execution_gateway_used"] = True
        step["scheduler_execution_legacy_fallback_used"] = False
        step["scheduler_execution_runtime_ok"] = True
        step["scheduler_execution_runtime_error"] = None

        result["scheduler_execution_gateway_used"] = True
        result["scheduler_execution_legacy_fallback_used"] = False
        result["scheduler_execution_runtime_ok"] = True
        result["scheduler_execution_runtime_error"] = None

        return ExecutionGatewayRuntimeResult(
            ok=True,
            step=step,
            result=result,
            legacy_result=dict(legacy_result or {}),
            errors=[],
            warnings=list(gateway_result.warnings),
            used_gateway=True,
            used_legacy_fallback=False,
            runtime_error=None,
        )

    if allow_legacy_fallback and isinstance(legacy_result, Mapping):
        step = _scheduler_safe_step(gateway_result.step)
        result = _scheduler_safe_result(dict(legacy_result))
        step["scheduler_execution_gateway_used"] = False
        step["scheduler_execution_legacy_fallback_used"] = True
        step["scheduler_execution_runtime_ok"] = True
        step["scheduler_execution_runtime_error"] = None
        step["execution_gateway_errors"] = list(gateway_result.errors)
        step["execution_gateway_warnings"] = list(gateway_result.warnings)

        result["scheduler_execution_gateway_used"] = False
        result["scheduler_execution_legacy_fallback_used"] = True
        result["scheduler_execution_runtime_ok"] = True
        result["scheduler_execution_runtime_error"] = None
        result["execution_gateway_errors"] = list(gateway_result.errors)
        result["execution_gateway_warnings"] = list(gateway_result.warnings)

        return ExecutionGatewayRuntimeResult(
            ok=True,
            step=step,
            result=result,
            legacy_result=dict(legacy_result),
            errors=list(gateway_result.errors),
            warnings=list(gateway_result.warnings),
            used_gateway=False,
            used_legacy_fallback=True,
            runtime_error=None,
        )

    reason = gateway_result.gateway_error or ";".join(gateway_result.errors) or "execution_gateway_failed"
    result = build_noop_execution_result(
        reason=reason,
        step_type=_extract_step_type(raw_step),
    )
    step = _scheduler_safe_step(result.get("step", {}))
    step["scheduler_execution_gateway_used"] = False
    step["scheduler_execution_legacy_fallback_used"] = False
    step["scheduler_execution_runtime_ok"] = False
    step["scheduler_execution_runtime_error"] = reason
    step["execution_gateway_errors"] = list(gateway_result.errors)
    step["execution_gateway_warnings"] = list(gateway_result.warnings)

    result = _scheduler_safe_result(result)
    result["scheduler_execution_gateway_used"] = False
    result["scheduler_execution_legacy_fallback_used"] = False
    result["scheduler_execution_runtime_ok"] = False
    result["scheduler_execution_runtime_error"] = reason
    result["execution_gateway_errors"] = list(gateway_result.errors)
    result["execution_gateway_warnings"] = list(gateway_result.warnings)

    return ExecutionGatewayRuntimeResult(
        ok=False,
        step=step,
        result=result,
        legacy_result=dict(legacy_result or {}),
        errors=list(gateway_result.errors),
        warnings=list(gateway_result.warnings),
        used_gateway=False,
        used_legacy_fallback=False,
        runtime_error=reason,
    )


def export_scheduler_execution_result(
    executor: Any,
    raw_step: Any,
    *,
    method_name: str = "execute",
    legacy_result: Optional[Mapping[str, Any]] = None,
    allow_legacy_fallback: bool = True,
    trace: bool = True,
) -> Dict[str, Any]:
    return run_scheduler_execution_gateway(
        executor,
        raw_step,
        method_name=method_name,
        legacy_result=legacy_result,
        allow_legacy_fallback=allow_legacy_fallback,
        trace=trace,
    ).result


def _scheduler_safe_step(step: Any) -> Dict[str, Any]:
    safe = dict(step) if isinstance(step, Mapping) else {}

    safe.setdefault("contract_version", "execution_contract.v1")
    safe.setdefault("type", "noop")
    safe.setdefault("path", None)
    safe.setdefault("target_path", None)
    safe.setdefault("content", "")
    safe.setdefault("command", "")
    safe.setdefault("reason", "")
    safe.setdefault("description", "")
    safe.setdefault("metadata", {})
    safe.setdefault("is_valid", True)
    safe.setdefault("contract_errors", [])
    safe.setdefault("contract_warnings", [])
    safe.setdefault("execution_adapter_ok", True)
    safe.setdefault("execution_adapter_errors", [])
    safe.setdefault("execution_adapter_warnings", [])
    safe.setdefault("execution_runtime_entry_step_ok", True)
    safe.setdefault("execution_runtime_entry_invoked", False)
    safe.setdefault("execution_runtime_entry_ok", True)
    safe.setdefault("execution_runtime_entry_error", None)
    safe.setdefault("execution_gateway_ok", True)
    safe.setdefault("execution_gateway_invoked", False)
    safe.setdefault("execution_gateway_error", None)
    safe.setdefault("execution_gateway_errors", [])
    safe.setdefault("execution_gateway_warnings", [])

    return safe


def _scheduler_safe_result(result: Any) -> Dict[str, Any]:
    safe = dict(result) if isinstance(result, Mapping) else {}

    safe.setdefault("ok", True)
    safe.setdefault("action", "noop")
    safe.setdefault("reason", "")
    safe.setdefault("error", "")
    safe.setdefault("execution_gateway_ok", True)
    safe.setdefault("execution_gateway_invoked", False)
    safe.setdefault("execution_gateway_error", None)
    safe.setdefault("execution_gateway_errors", [])
    safe.setdefault("execution_gateway_warnings", [])

    return safe


def _extract_step_type(raw_step: Any) -> str:
    if not isinstance(raw_step, Mapping):
        return "noop"

    value = raw_step.get("type") or raw_step.get("action") or raw_step.get("kind")
    if value is None:
        return "noop"

    text = str(value).strip()
    return text or "noop"