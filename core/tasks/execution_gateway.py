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


_ACTION_ALIASES: Dict[str, str] = {
    "append": "append_file",
    "workspace_append": "append_file",
    "write": "write_file",
    "workspace_write": "write_file",
}

_STEP_TYPE_ALIASES: Dict[str, str] = {
    "verify_file": "verify",
}


def _clean_text(value: Any, fallback: str = "") -> str:
    text = str(value if value is not None else fallback).strip()
    return text if text else fallback


def _normalize_step_type(value: Any, fallback: str = "noop") -> str:
    text = _clean_text(value, fallback)
    if text.lower() == "unknown":
        text = fallback
    return _STEP_TYPE_ALIASES.get(text, text)


def _canonical_action(value: Any, fallback: str = "noop") -> str:
    text = _clean_text(value, fallback)
    if text.lower() == "unknown":
        text = fallback
    return _ACTION_ALIASES.get(text, text)


def _target_path_from_step(step: Dict[str, Any]) -> Optional[str]:
    for key in ("target_path", "path", "file_path", "target"):
        value = step.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _normalize_gateway_step(step: Dict[str, Any], *, ok: bool, invoked: bool, error: Optional[str], errors: List[str], warnings: List[str]) -> Dict[str, Any]:
    normalized = dict(step)

    raw_type = normalized.get("type") or normalized.get("action") or "noop"
    normalized_type = _normalize_step_type(raw_type)
    normalized["type"] = normalized_type

    target_path = _target_path_from_step(normalized)
    if target_path is not None:
        normalized["target_path"] = target_path

    normalized["execution_gateway_ok"] = bool(ok)
    normalized["execution_gateway_invoked"] = bool(invoked)
    normalized["execution_gateway_error"] = error
    normalized["execution_gateway_errors"] = list(errors)
    normalized["execution_gateway_warnings"] = list(warnings)

    return normalized


def _normalize_gateway_result(result: Dict[str, Any], step: Dict[str, Any], *, ok: bool, invoked: bool, error: Optional[str]) -> Dict[str, Any]:
    normalized = dict(result)

    raw_action = normalized.get("action") or step.get("type") or "noop"
    action = _canonical_action(raw_action)

    normalized.setdefault("ok", bool(ok))
    normalized["action"] = action

    # Keep explicit step_type from the executor when present, but normalize file-specific aliases.
    if "step_type" in normalized:
        normalized["step_type"] = _normalize_step_type(normalized.get("step_type"))
    else:
        normalized["step_type"] = _normalize_step_type(step.get("type") or action)

    target_path = normalized.get("target_path")
    if not isinstance(target_path, str) or not target_path.strip():
        target_path = _target_path_from_step(step)
    if target_path is not None:
        normalized["target_path"] = target_path

    normalized["execution_gateway_ok"] = bool(ok)
    normalized["execution_gateway_invoked"] = bool(invoked)
    normalized["execution_gateway_error"] = error

    return normalized


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

    raw_runtime_step = dict(runtime_result.step)
    raw_runtime_result = dict(runtime_result.result)

    step = _normalize_gateway_step(
        raw_runtime_step,
        ok=runtime_result.ok,
        invoked=runtime_result.invoked,
        error=runtime_result.invocation_error,
        errors=list(runtime_result.errors),
        warnings=list(runtime_result.warnings),
    )

    result = _normalize_gateway_result(
        raw_runtime_result,
        step,
        ok=runtime_result.ok,
        invoked=runtime_result.invoked,
        error=runtime_result.invocation_error,
    )

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
    normalized_step_type = _normalize_step_type(step_type or "noop")
    return {
        "ok": True,
        "action": "noop",
        "reason": str(reason or ""),
        "step": {
            "contract_version": "execution_contract.v1",
            "type": normalized_step_type,
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
