from __future__ import annotations

import copy
import time
import traceback
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

try:
    from core.runtime.runtime_legality import RuntimeLegalityEngine
except Exception:  # pragma: no cover - keeps older test surfaces importable
    RuntimeLegalityEngine = None  # type: ignore[assignment]


@dataclass(frozen=True)
class SchedulerExecutionGatewayResult:
    ok: bool
    step: Dict[str, Any]
    result: Dict[str, Any]
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    gateway_error: Optional[str] = None
    invoked: bool = False
    used_gateway: bool = True
    used_legacy_fallback: bool = False
    runtime_error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _normalize_step(step: Any) -> Dict[str, Any]:
    if isinstance(step, dict):
        return copy.deepcopy(step)
    if step is None:
        return {"type": "noop", "action": "noop"}
    return {"type": "noop", "action": "noop", "raw_step": copy.deepcopy(step)}


def _step_type(step: Any) -> str:
    if isinstance(step, dict):
        value = step.get("action") or step.get("type") or "noop"
        text = str(value).strip().lower()
        if text and text != "unknown":
            return text
    return "noop"


def _step_action(step: Any, fallback: str = "noop") -> str:
    if isinstance(step, dict):
        value = step.get("action") or step.get("type")
        if isinstance(value, str):
            text = value.strip()
            if text and text.lower() != "unknown":
                return text
    return fallback


def _canonical_action_from_payload(payload: Any, fallback: str = "noop") -> str:
    if isinstance(payload, dict):
        step = payload.get("step")
        if isinstance(step, dict):
            action = _step_action(step, fallback="")
            if action:
                return action

        for key in ("step_type", "action", "type"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip() and value.strip().lower() != "unknown":
                return value.strip()

    return fallback


def _validate_step(step: Dict[str, Any]) -> List[str]:
    step_type = _step_type(step)
    errors: List[str] = []

    if step_type in {"write_file", "append_file", "workspace_write", "workspace_append"}:
        path = step.get("path") or step.get("file_path") or step.get("target") or step.get("target_path")
        if not isinstance(path, str) or not path.strip():
            errors.append(f"{step_type}:missing_path")

    return errors


def _risk_level_for_step(step: Dict[str, Any]) -> str:
    explicit = step.get("risk_level") or step.get("risk") or step.get("execution_risk")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip().lower()

    step_type = _step_type(step)
    if step_type in {"read_file", "workspace_read", "list_directory", "runtime_status", "noop"}:
        return "low"
    if step_type in {"write_file", "append_file", "workspace_write", "apply_patch", "apply_unified_diff"}:
        return "medium"
    if step_type in {"command", "run_python", "execute_python", "subprocess", "shell"}:
        return "high"
    if step_type in {"delete_repo", "force_push", "system_wipe"}:
        return "critical"
    return "unknown"


def _evaluate_legality(
    *,
    step: Dict[str, Any],
    governance_snapshot: Any = None,
    constitution: Any = None,
) -> Any:
    if constitution is None or RuntimeLegalityEngine is None:
        return None

    engine = RuntimeLegalityEngine()
    return engine.evaluate_action(
        action_type=_step_type(step),
        risk_level=_risk_level_for_step(step),
        governance_snapshot=governance_snapshot,
        constitution=constitution,
    )


def _decision_to_dict(decision: Any) -> Dict[str, Any]:
    if decision is None:
        return {}

    to_dict = getattr(decision, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, dict):
            return copy.deepcopy(payload)

    payload: Dict[str, Any] = {}
    for key in (
        "allowed",
        "requires_review",
        "blocked",
        "decision",
        "reason",
        "violated_rules",
        "action_type",
        "risk_level",
        "governance_id",
        "constitution_version",
    ):
        if hasattr(decision, key):
            payload[key] = copy.deepcopy(getattr(decision, key))

    if "decision" not in payload:
        if bool(payload.get("blocked")):
            payload["decision"] = "BLOCK"
        elif bool(payload.get("requires_review")):
            payload["decision"] = "REVIEW"
        elif bool(payload.get("allowed")):
            payload["decision"] = "ALLOW"
        else:
            payload["decision"] = "UNKNOWN"

    return payload


def build_noop_execution_result(
    step: Any = None,
    *,
    ok: bool = True,
    action: Optional[str] = None,
    message: Optional[str] = None,
    source: str = "scheduler_execution_gateway",
    metadata: Optional[Dict[str, Any]] = None,
    **extra: Any,
) -> Dict[str, Any]:
    normalized_step = _normalize_step(step)
    final_action = action or _step_action(normalized_step, fallback="noop")
    step_type = _step_type(normalized_step)
    final_message = message or f"{final_action}: {step_type}"

    result: Dict[str, Any] = {
        "ok": bool(ok),
        "action": final_action,
        "type": final_action,
        "step_type": step_type,
        "step": copy.deepcopy(normalized_step),
        "message": final_message,
        "final_answer": final_message,
        "error": None if ok else final_action,
        "scheduler_execution_gateway_returned": True,
        "scheduler_execution_gateway_used": False,
        "scheduler_execution_legacy_fallback_used": False,
        "scheduler_execution_gateway_source": source,
        "scheduler_execution_runtime_ok": bool(ok),
        "scheduler_execution_runtime_error": None,
        "execution_trace": [
            {
                "source": source,
                "event": final_action,
                "step_type": step_type,
                "ok": bool(ok),
                "message": final_message,
                "timestamp_ms": _now_ms(),
            }
        ],
        "metadata": {
            "source": source,
            "noop": True,
            "step_type": step_type,
        },
    }

    if metadata:
        result["metadata"].update(copy.deepcopy(metadata))

    if extra:
        result.update(copy.deepcopy(extra))

    return result


def normalize_execution_result(
    value: Any,
    *,
    step: Any = None,
    source: str = "scheduler_execution_gateway",
) -> Dict[str, Any]:
    normalized_step = _normalize_step(step)
    fallback_action = _step_action(normalized_step, fallback="execution_result")

    if isinstance(value, dict):
        result = copy.deepcopy(value)
    else:
        result = {
            "ok": bool(value),
            "action": fallback_action,
            "raw_result": copy.deepcopy(value),
        }

    action = _canonical_action_from_payload(
        {
            **result,
            "step": normalized_step,
        },
        fallback=fallback_action,
    )

    result.setdefault("ok", bool(result.get("success", result.get("executed", False))))
    result["action"] = action
    result["type"] = action
    result["step_type"] = action
    result.setdefault("step", copy.deepcopy(normalized_step))
    result.setdefault("message", str(result.get("final_answer") or result.get("summary") or action))
    result.setdefault("final_answer", str(result.get("message") or action))
    result.setdefault("error", None if bool(result.get("ok")) else result.get("error") or "execution_failed")

    result["scheduler_execution_gateway_returned"] = True
    result.setdefault("scheduler_execution_gateway_source", source)

    if not isinstance(result.get("execution_trace"), list):
        result["execution_trace"] = []

    result["execution_trace"].append(
        {
            "source": source,
            "event": "normalized_execution_result",
            "step_type": result.get("step_type"),
            "ok": bool(result.get("ok")),
            "timestamp_ms": _now_ms(),
        }
    )

    return result


def build_gateway_result(
    *,
    result: Any,
    step: Any = None,
    used_gateway: bool = True,
    used_legacy_fallback: bool = False,
    runtime_error: Optional[str] = None,
    gateway_error: Optional[str] = None,
    errors: Optional[List[str]] = None,
    warnings: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    source: str = "scheduler_execution_gateway",
) -> SchedulerExecutionGatewayResult:
    normalized_step = _normalize_step(step)
    normalized_result = normalize_execution_result(result, step=normalized_step, source=source)

    final_gateway_error = gateway_error or runtime_error
    error_list = list(errors or [])
    warning_list = list(warnings or [])

    normalized_result["scheduler_execution_gateway_used"] = bool(used_gateway)
    normalized_result["scheduler_execution_legacy_fallback_used"] = bool(used_legacy_fallback)
    normalized_result["scheduler_execution_runtime_ok"] = bool(normalized_result.get("ok")) and final_gateway_error is None
    normalized_result["scheduler_execution_runtime_error"] = final_gateway_error

    if error_list:
        normalized_result["scheduler_execution_gateway_errors"] = copy.deepcopy(error_list)
    if warning_list:
        normalized_result["scheduler_execution_gateway_warnings"] = copy.deepcopy(warning_list)
    if metadata:
        normalized_result.setdefault("metadata", {})
        if isinstance(normalized_result["metadata"], dict):
            normalized_result["metadata"].update(copy.deepcopy(metadata))

    return SchedulerExecutionGatewayResult(
        ok=bool(normalized_result.get("ok")) and final_gateway_error is None,
        step=normalized_step,
        result=normalized_result,
        errors=error_list,
        warnings=warning_list,
        gateway_error=final_gateway_error,
        invoked=bool(used_gateway),
        used_gateway=bool(used_gateway),
        used_legacy_fallback=bool(used_legacy_fallback),
        runtime_error=runtime_error,
        metadata=copy.deepcopy(metadata or {}),
    )


def _invoke_executor(executor: Any, step: Dict[str, Any], kwargs: Dict[str, Any]) -> Any:
    if callable(executor):
        try:
            return executor(step, **kwargs)
        except TypeError:
            return executor(step)

    execute_step = getattr(executor, "execute_step", None)
    if callable(execute_step):
        try:
            return execute_step(step=step, **kwargs)
        except TypeError:
            return execute_step(step)

    execute = getattr(executor, "execute", None)
    if callable(execute):
        try:
            return execute(step=step, **kwargs)
        except TypeError:
            return execute(step)

    raise TypeError("executor_not_callable")


def _build_legality_rejection_result(
    *,
    step: Dict[str, Any],
    decision: Any,
    source: str,
) -> SchedulerExecutionGatewayResult:
    decision_payload = _decision_to_dict(decision)
    decision_name = str(decision_payload.get("decision") or "UNKNOWN").upper()
    action = "execution_step_blocked" if decision_name == "BLOCK" else "execution_step_requires_review"
    reason = str(decision_payload.get("reason") or action)

    result = build_noop_execution_result(
        step,
        ok=False,
        action=action,
        message=reason,
        source=source,
        metadata={
            "runtime_legality_decision": decision_payload,
            "execution_intercepted": True,
        },
        runtime_legality_decision=decision_payload,
        execution_intercepted=True,
    )

    return build_gateway_result(
        result=result,
        step=step,
        used_gateway=False,
        used_legacy_fallback=False,
        runtime_error=action,
        gateway_error=action,
        errors=[action],
        warnings=[] if decision_name == "BLOCK" else ["runtime_legality_requires_review"],
        metadata={
            "trace": True,
            "gateway_call": "runtime_legality",
            "runtime_legality_decision": decision_payload,
            "execution_intercepted": True,
        },
        source=source,
    )


def run_scheduler_execution_gateway(
    executor: Callable[..., Any],
    step: Any,
    *,
    legacy_result: Any = None,
    allow_legacy_fallback: bool = True,
    trace: bool = True,
    source: str = "scheduler_execution_gateway",
    governance_snapshot: Any = None,
    constitution: Any = None,
    enforce_legality: bool = True,
    **kwargs: Any,
) -> SchedulerExecutionGatewayResult:
    normalized_step = _normalize_step(step)
    validation_errors = _validate_step(normalized_step)

    if validation_errors:
        fallback = legacy_result
        if fallback is None:
            fallback = build_noop_execution_result(
                normalized_step,
                ok=False,
                action=_step_action(normalized_step, fallback="invalid_step"),
                message=validation_errors[0],
                source=source,
            )

        return build_gateway_result(
            result=fallback,
            step=normalized_step,
            used_gateway=False,
            used_legacy_fallback=bool(allow_legacy_fallback),
            errors=validation_errors,
            source=source,
        )

    if enforce_legality and constitution is not None:
        legality_decision = _evaluate_legality(
            step=normalized_step,
            governance_snapshot=governance_snapshot,
            constitution=constitution,
        )
        if legality_decision is not None:
            if bool(getattr(legality_decision, "blocked", False)) or bool(getattr(legality_decision, "requires_review", False)):
                return _build_legality_rejection_result(
                    step=normalized_step,
                    decision=legality_decision,
                    source=source,
                )

    try:
        raw_result = _invoke_executor(executor, normalized_step, kwargs)
        return build_gateway_result(
            result=raw_result,
            step=normalized_step,
            used_gateway=True,
            used_legacy_fallback=False,
            source=source,
            metadata={
                "trace": bool(trace),
                "gateway_call": "executor",
            },
        )

    except Exception as exc:
        error_text = f"execution_invocation_failed:{type(exc).__name__}:{exc}"

        if allow_legacy_fallback:
            fallback = legacy_result
            if fallback is None:
                fallback = build_noop_execution_result(
                    normalized_step,
                    ok=False,
                    action=_step_action(normalized_step, fallback="gateway_exception_fallback"),
                    message=error_text,
                    source=source,
                )

            return build_gateway_result(
                result=fallback,
                step=normalized_step,
                used_gateway=False,
                used_legacy_fallback=True,
                runtime_error=error_text,
                gateway_error=error_text,
                errors=[error_text],
                warnings=["legacy_fallback_used_after_gateway_exception"],
                metadata={
                    "trace": bool(trace),
                    "traceback": traceback.format_exc(),
                },
                source=source,
            )

        return build_gateway_result(
            result=build_noop_execution_result(
                normalized_step,
                ok=False,
                action=_step_action(normalized_step, fallback="gateway_exception"),
                message=error_text,
                source=source,
            ),
            step=normalized_step,
            used_gateway=False,
            used_legacy_fallback=False,
            runtime_error=error_text,
            gateway_error=error_text,
            errors=[error_text],
            metadata={
                "trace": bool(trace),
                "traceback": traceback.format_exc(),
            },
            source=source,
        )


def call_execution_gateway(
    executor: Callable[..., Any],
    step: Any,
    *,
    legacy_result: Any = None,
    allow_legacy_fallback: bool = True,
    trace: bool = True,
    source: str = "scheduler_execution_gateway",
    governance_snapshot: Any = None,
    constitution: Any = None,
    enforce_legality: bool = True,
    **kwargs: Any,
) -> SchedulerExecutionGatewayResult:
    return run_scheduler_execution_gateway(
        executor,
        step,
        legacy_result=legacy_result,
        allow_legacy_fallback=allow_legacy_fallback,
        trace=trace,
        source=source,
        governance_snapshot=governance_snapshot,
        constitution=constitution,
        enforce_legality=enforce_legality,
        **kwargs,
    )


def export_execution_gateway_result(
    executor: Any,
    raw_step: Any,
    *,
    method_name: str = "execute",
    trace: bool = True,
    governance_snapshot: Any = None,
    constitution: Any = None,
    enforce_legality: bool = True,
) -> Dict[str, Any]:
    return call_execution_gateway(
        executor,
        raw_step,
        method_name=method_name,
        trace=trace,
        governance_snapshot=governance_snapshot,
        constitution=constitution,
        enforce_legality=enforce_legality,
    ).result


def _event_name_for_runtime_result(runtime_result: Any) -> str:
    if not bool(getattr(runtime_result, "ok", False)):
        action = ""
        try:
            action = str(runtime_result.result.get("action") or "")
        except Exception:
            action = ""

        if action == "execution_step_rejected":
            return "execution_step_rejected"
        if action == "execution_step_blocked":
            return "execution_step_blocked"
        if action == "execution_step_requires_review":
            return "execution_step_requires_review"
        if action == "execution_invocation_failed":
            return "execution_invocation_failed"
        return "execution_gateway_failed"

    return "execution_gateway_completed"
