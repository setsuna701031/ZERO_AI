from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.tasks.execution_runtime_entry import run_execution_runtime_entry
from core.tasks.execution_contract_trace import trace_execution_contract_payload


@dataclass(frozen=True)
class ExecutionGatewayResult:
    ok: bool
    step: Dict[str, Any]
    result: Dict[str, Any]
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    gateway_error: Optional[str] = None
    invoked: bool = False


def call_execution_gateway(
    executor: Any,
    raw_step: Any,
    *,
    method_name: str = "execute",
    trace: bool = True,
) -> ExecutionGatewayResult:
    runtime_result = run_execution_runtime_entry(
        executor,
        raw_step,
        method_name=method_name,
    )

    step = dict(runtime_result.step)
    result = dict(runtime_result.result)

    step["execution_gateway_ok"] = runtime_result.ok
    step["execution_gateway_invoked"] = runtime_result.invoked
    step["execution_gateway_error"] = runtime_result.invocation_error
    step["execution_gateway_errors"] = list(runtime_result.errors)
    step["execution_gateway_warnings"] = list(runtime_result.warnings)

    result.setdefault("ok", runtime_result.ok)
    result.setdefault("action", str(step.get("type") or "noop"))
    result["execution_gateway_ok"] = runtime_result.ok
    result["execution_gateway_invoked"] = runtime_result.invoked
    result["execution_gateway_error"] = runtime_result.invocation_error

    if trace:
        try:
            trace_execution_contract_payload(
                event=_event_name_for_runtime_result(runtime_result),
                source="execution_gateway",
                step=step,
                result=result,
                ok=runtime_result.ok,
                errors=list(runtime_result.errors),
                warnings=list(runtime_result.warnings),
            )
        except Exception:
            pass

    return ExecutionGatewayResult(
        ok=runtime_result.ok,
        step=step,
        result=result,
        errors=list(runtime_result.errors),
        warnings=list(runtime_result.warnings),
        gateway_error=runtime_result.invocation_error,
        invoked=runtime_result.invoked,
    )


def export_execution_gateway_result(
    executor: Any,
    raw_step: Any,
    *,
    method_name: str = "execute",
    trace: bool = True,
) -> Dict[str, Any]:
    return call_execution_gateway(
        executor,
        raw_step,
        method_name=method_name,
        trace=trace,
    ).result


def build_noop_execution_result(
    *,
    reason: str,
    step_type: str = "noop",
) -> Dict[str, Any]:
    return {
        "ok": True,
        "action": "noop",
        "reason": str(reason or ""),
        "step": {
            "contract_version": "execution_contract.v1",
            "type": str(step_type or "noop"),
            "path": None,
            "target_path": None,
            "content": "",
            "command": "",
            "reason": str(reason or ""),
            "description": "",
            "metadata": {},
            "is_valid": True,
            "contract_errors": [],
            "contract_warnings": [],
            "execution_adapter_ok": True,
            "execution_adapter_errors": [],
            "execution_adapter_warnings": [],
            "execution_runtime_entry_step_ok": True,
            "execution_runtime_entry_invoked": False,
            "execution_runtime_entry_ok": True,
            "execution_runtime_entry_error": None,
            "execution_gateway_ok": True,
            "execution_gateway_invoked": False,
            "execution_gateway_error": None,
            "execution_gateway_errors": [],
            "execution_gateway_warnings": [],
        },
        "execution_gateway_ok": True,
        "execution_gateway_invoked": False,
        "execution_gateway_error": None,
    }


def _event_name_for_runtime_result(runtime_result: Any) -> str:
    if not bool(getattr(runtime_result, "ok", False)):
        action = ""
        try:
            action = str(runtime_result.result.get("action") or "")
        except Exception:
            action = ""

        if action == "execution_step_rejected":
            return "execution_step_rejected"
        if action == "execution_invocation_failed":
            return "execution_invocation_failed"
        return "execution_gateway_failed"

    return "execution_gateway_completed"