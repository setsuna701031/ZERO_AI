from __future__ import annotations

import copy
import time
import traceback
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.tasks import execution_gateway_runtime as execution_gateway_runtime


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


GATEWAY_LAYER = "scheduler_execution_gateway.v1"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _export_action_alias(action: Any) -> str:
    text = str(action or "noop").strip()
    if not text or text.lower() == "unknown":
        return "noop"

    aliases = {
        "append": "append_file",
        "write": "write_file",
        "workspace_append": "append_file",
        "workspace_write": "write_file",
    }
    return aliases.get(text, text)


def _extract_target_path(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict):
        return None

    for key in ("target_path", "path", "file_path", "target"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    step = payload.get("step")
    if isinstance(step, dict):
        for key in ("target_path", "path", "file_path", "target"):
            value = step.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return None


def _normalize_step(step: Any) -> Dict[str, Any]:
    if isinstance(step, dict):
        normalized = copy.deepcopy(step)
    elif step is None:
        normalized = {"type": "noop", "action": "noop"}
    else:
        normalized = {"type": "noop", "action": "noop", "raw_step": copy.deepcopy(step)}

    normalized["scheduler_execution_gateway_layer"] = GATEWAY_LAYER
    return normalized


def _step_type(step: Any) -> str:
    if isinstance(step, dict):
        value = step.get("type") or step.get("action") or "noop"
        text = str(value).strip().lower()
        if text and text != "unknown":
            return text
    return "noop"


def _step_action(step: Any, fallback: str = "noop") -> str:
    if isinstance(step, dict):
        value = step.get("type") or step.get("action")
        if isinstance(value, str):
            text = value.strip()
            if text and text.lower() != "unknown":
                return text
    return fallback


def _canonical_action_from_payload(payload: Any, fallback: str = "noop") -> str:
    if isinstance(payload, dict):
        for key in ("action", "type", "step_type"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip() and value.strip().lower() != "unknown":
                return value.strip()

        step = payload.get("step")
        if isinstance(step, dict):
            action = _step_action(step, fallback="")
            if action:
                return action

    return fallback


def _validate_step(step: Dict[str, Any]) -> List[str]:
    step_type = _step_type(step)
    errors: List[str] = []

    if step_type in {"write_file", "append_file", "workspace_write", "workspace_append"}:
        path = step.get("path") or step.get("file_path") or step.get("target") or step.get("target_path")
        if not isinstance(path, str) or not path.strip():
            errors.append(f"{step_type}:missing_path")

    return errors


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
        "scheduler_execution_gateway_layer": GATEWAY_LAYER,
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

    target_path = _extract_target_path(normalized_step)
    if target_path is not None:
        result["target_path"] = target_path

    if metadata:
        result["metadata"].update(copy.deepcopy(metadata))

    if extra:
        result.update(copy.deepcopy(extra))

    return result


def _nested_mapping_values(payload: Any) -> List[Dict[str, Any]]:
    """Return nested dict payloads that commonly carry executor truth.

    SchedulerExecutionGateway is a transport/compatibility layer. It must not
    reinterpret a successful StepExecutor payload as failed just because the
    outer compatibility wrapper did not include an explicit top-level ``ok``.
    """
    if not isinstance(payload, dict):
        return []

    values: List[Dict[str, Any]] = []
    for key in ("result", "output", "data", "payload", "raw", "adapter_payload"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            values.append(nested)
            values.extend(_nested_mapping_values(nested))
    return values


def _payload_chain(payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    return [payload, *_nested_mapping_values(payload)]


def _payload_step_type(payload: Any, fallback: str = "") -> str:
    for source_payload in _payload_chain(payload):
        for key in ("step_type", "type", "action"):
            value = source_payload.get(key)
            if isinstance(value, str) and value.strip() and value.strip().lower() != "unknown":
                return value.strip().lower()
        step = source_payload.get("step")
        if isinstance(step, dict):
            value = step.get("type") or step.get("action")
            if isinstance(value, str) and value.strip() and value.strip().lower() != "unknown":
                return value.strip().lower()
    return str(fallback or "").strip().lower()


def _has_nonempty_text(payload: Any, *keys: str) -> bool:
    for source_payload in _payload_chain(payload):
        for key in keys:
            value = source_payload.get(key)
            if isinstance(value, str) and value.strip():
                return True
    return False


def _has_path_signal(payload: Any) -> bool:
    for source_payload in _payload_chain(payload):
        for key in ("full_path", "path", "target_path", "file_path"):
            value = source_payload.get(key)
            if isinstance(value, str) and value.strip():
                return True
    return False


def _has_hard_failure_signal(payload: Any) -> bool:
    """Return True only for errors that should beat a successful payload shape."""
    soft_errors = {"execution_failed"}
    for source_payload in _payload_chain(payload):
        for key in ("blocked", "failed"):
            if bool(source_payload.get(key)):
                return True

        error_type = source_payload.get("error_type")
        if isinstance(error_type, str) and error_type.strip():
            return True

        error = source_payload.get("error")
        if isinstance(error, dict):
            error_name = str(error.get("type") or "").strip().lower()
            if error_name and error_name not in soft_errors:
                return True
            message = str(error.get("message") or "").strip()
            if message and error_name not in soft_errors:
                return True
        elif isinstance(error, str):
            error_name = error.strip().lower()
            if error_name and error_name not in soft_errors:
                return True
        elif error not in (None, "", False, {}, []):
            return True
    return False


def _looks_like_successful_payload(payload: Any, *, fallback_step_type: str = "") -> bool:
    """Recognize legacy/basic executor success shapes without inventing success.

    Some older scheduler-basic paths return useful read/write payloads but mark
    ``ok`` false because they treat missing outer executor transport metadata as
    a failure.  The gateway is the contract boundary, so it may correct those
    known shapes only when a concrete success signal exists and no hard error is
    present.
    """
    if not isinstance(payload, dict):
        return bool(payload)

    if _has_hard_failure_signal(payload):
        return False

    step_type = _payload_step_type(payload, fallback=fallback_step_type)

    if step_type in {"read_file", "workspace_read"}:
        return _has_path_signal(payload) and _has_nonempty_text(payload, "content", "text", "message", "final_answer")

    if step_type in {"write_file", "workspace_write", "append_file", "workspace_append", "ensure_file"}:
        return _has_path_signal(payload) and (
            _has_nonempty_text(payload, "content", "message", "final_answer")
            or any("bytes" in source_payload or "bytes_appended" in source_payload for source_payload in _payload_chain(payload))
            or any(source_payload.get("created") is not None for source_payload in _payload_chain(payload))
        )

    if step_type in {"llm", "llm_generate", "respond", "final_answer"}:
        return _has_nonempty_text(payload, "text", "content", "message", "final_answer", "response")

    if step_type in {"command", "shell", "run_python"}:
        for source_payload in _payload_chain(payload):
            if "returncode" in source_payload:
                try:
                    return int(source_payload.get("returncode", 1)) == 0
                except Exception:
                    return False

    return False


def _infer_execution_ok(payload: Dict[str, Any], *, fallback_step_type: str = "") -> bool:
    """Infer execution truth without letting legacy wrappers invert success.

    Precedence:
    1. Explicit hard failure signals.
    2. Known successful executor payload shapes such as read_file with content.
    3. Explicit top-level ok/success/executed.
    4. Explicit nested ok/success/executed.
    5. False by default.
    """
    if not isinstance(payload, dict):
        return bool(payload)

    if _has_hard_failure_signal(payload):
        return False

    if _looks_like_successful_payload(payload, fallback_step_type=fallback_step_type):
        return True

    for key in ("ok", "success", "executed"):
        if key in payload:
            return bool(payload.get(key))

    for nested in _nested_mapping_values(payload):
        for key in ("ok", "success", "executed"):
            if key in nested:
                return bool(nested.get(key))

    return False


def _extract_execution_text(payload: Dict[str, Any]) -> str:
    """Extract the best human-facing text from a gateway/executor payload."""
    keys = (
        "final_answer",
        "message",
        "summary",
        "summary_text",
        "content",
        "text",
        "response",
        "answer",
        "output_text",
        "stdout",
    )

    for source_payload in [payload, *_nested_mapping_values(payload)]:
        for key in keys:
            value = source_payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return ""


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
        result,
        fallback=fallback_action,
    )

    inferred_ok = _infer_execution_ok(result, fallback_step_type=_step_type(normalized_step))
    # Do not let a legacy/basic wrapper keep ok=False when the payload has a
    # concrete successful executor shape (for example read_file with content).
    result["ok"] = inferred_ok
    result["action"] = action
    result.setdefault("type", action)
    result.setdefault("step_type", _step_type(normalized_step))
    result.setdefault("step", copy.deepcopy(normalized_step))

    extracted_text = _extract_execution_text(result)
    result.setdefault("message", extracted_text or str(result.get("final_answer") or result.get("summary") or action))
    result.setdefault("final_answer", extracted_text or str(result.get("message") or action))

    if bool(result.get("ok")):
        result["error"] = None
    else:
        result.setdefault("error", result.get("error") or "execution_failed")

    target_path = _extract_target_path(result) or _extract_target_path(normalized_step)
    if target_path is not None:
        result["target_path"] = target_path

    result["scheduler_execution_gateway_returned"] = True
    result.setdefault("scheduler_execution_gateway_source", source)
    result["scheduler_execution_gateway_layer"] = GATEWAY_LAYER

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

    error_list = list(errors or [])
    warning_list = list(warnings or [])
    final_gateway_error = gateway_error or runtime_error
    if final_gateway_error is None and error_list and not used_legacy_fallback:
        final_gateway_error = error_list[0]
        runtime_error = error_list[0]

    payload_ok = bool(normalized_result.get("ok"))
    transport_ok = final_gateway_error is None

    normalized_result["scheduler_execution_gateway_used"] = bool(used_gateway)
    normalized_result["scheduler_execution_legacy_fallback_used"] = bool(used_legacy_fallback)
    # Transport truth and payload truth are intentionally separate.
    # ``scheduler_execution_runtime_ok`` means the gateway wrapper did not fail;
    # ``ok`` remains the executor/legacy payload result.
    normalized_result["scheduler_execution_runtime_ok"] = transport_ok
    normalized_result["scheduler_execution_runtime_error"] = final_gateway_error
    normalized_result["scheduler_execution_payload_ok"] = payload_ok
    normalized_result["scheduler_execution_gateway_layer"] = GATEWAY_LAYER

    if error_list:
        normalized_result["scheduler_execution_gateway_errors"] = copy.deepcopy(error_list)
    if warning_list:
        normalized_result["scheduler_execution_gateway_warnings"] = copy.deepcopy(warning_list)

    return SchedulerExecutionGatewayResult(
        ok=bool(normalized_result.get("ok")),
        step=normalized_step,
        result=normalized_result,
        errors=error_list,
        warnings=warning_list,
        gateway_error=final_gateway_error,
        invoked=bool(used_gateway),
        used_gateway=bool(used_gateway),
        used_legacy_fallback=bool(used_legacy_fallback),
        runtime_error=runtime_error or final_gateway_error,
        metadata=copy.deepcopy(metadata or {}),
    )


def _invoke_executor(executor: Any, step: Dict[str, Any], kwargs: Dict[str, Any]) -> Any:
    """Invoke a scheduler execution target with one canonical contract.

    This function deliberately avoids broad TypeError fallback chains. Those
    chains used to catch TypeError raised *inside* a handler and retry with
    ``handler(step)``, hiding the real error and breaking bound handlers.

    Supported contracts:
    - StepExecutor-like object: execute_step(step=..., task=..., context=..., previous_result=...)
    - StepExecutor-like object: execute(step=..., task=..., context=..., previous_result=...)
    - Bound StepHandler callable: handler(step, task, context, previous_result)
    - Legacy explicit opt-in callable: handler(step) only when no task/context/previous_result exists.
    """
    task = kwargs.get("task")
    context = kwargs.get("context")
    previous_result = kwargs.get("previous_result")

    execute_step = getattr(executor, "execute_step", None)
    if callable(execute_step):
        return execute_step(step=step, **kwargs)

    execute = getattr(executor, "execute", None)
    if callable(execute):
        return execute(step=step, **kwargs)

    if callable(executor):
        if task is not None or context is not None or previous_result is not None:
            return executor(step, task, context, previous_result)
        try:
            return executor(step, task, context, previous_result)
        except TypeError as exc:
            message = str(exc)
            contract_error_markers = (
                "required positional argument",
                "positional arguments",
                "unexpected keyword argument",
                "takes",
            )
            if any(marker in message for marker in contract_error_markers):
                return executor(step)
            raise

    raise TypeError("executor_not_callable")


def run_scheduler_execution_gateway(
    executor: Callable[..., Any],
    step: Any,
    *,
    legacy_result: Any = None,
    allow_legacy_fallback: bool = True,
    trace: bool = True,
    source: str = "scheduler_execution_gateway",
    **kwargs: Any,
) -> SchedulerExecutionGatewayResult:
    normalized_step = _normalize_step(step)
    validation_errors = _validate_step(normalized_step)

    if validation_errors:
        if not allow_legacy_fallback and legacy_result is None:
            fallback = build_noop_execution_result(
                normalized_step,
                ok=False,
                action="noop",
                message=validation_errors[0],
                source=source,
            )
            return build_gateway_result(
                result=fallback,
                step=normalized_step,
                used_gateway=False,
                used_legacy_fallback=False,
                runtime_error=validation_errors[0],
                gateway_error=validation_errors[0],
                errors=validation_errors,
                source=source,
            )

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
                    ok=True,
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
    **kwargs: Any,
) -> SchedulerExecutionGatewayResult:
    return run_scheduler_execution_gateway(
        executor,
        step,
        legacy_result=legacy_result,
        allow_legacy_fallback=allow_legacy_fallback,
        trace=trace,
        source=source,
        **kwargs,
    )


def run_scheduler_step_execution_gateway(
    executor: Callable[..., Any],
    step: Any,
    *,
    legacy_result: Any = None,
    allow_legacy_fallback: bool = True,
    trace: bool = True,
    source: str = "scheduler_step_execution_gateway",
    **kwargs: Any,
) -> SchedulerExecutionGatewayResult:
    return run_scheduler_execution_gateway(
        executor,
        step,
        legacy_result=legacy_result,
        allow_legacy_fallback=allow_legacy_fallback,
        trace=trace,
        source=source,
        **kwargs,
    )


def _export_scheduler_result_only(value: Any) -> Dict[str, Any]:
    if isinstance(value, SchedulerExecutionGatewayResult):
        exported = copy.deepcopy(value.result)
    elif isinstance(value, dict):
        exported = copy.deepcopy(value)
    else:
        return {"ok": bool(value), "result": copy.deepcopy(value)}

    raw_action = exported.get("action") or exported.get("type") or exported.get("step_type") or "noop"
    canonical_action = _export_action_alias(raw_action)

    exported["action"] = canonical_action
    exported["type"] = canonical_action
    exported["step_type"] = canonical_action
    exported["scheduler_execution_gateway_layer"] = GATEWAY_LAYER

    target_path = _extract_target_path(exported)
    if target_path is not None:
        exported["target_path"] = target_path

    return exported


def export_scheduler_step_execution_result(
    executor_or_value: Any,
    step: Any = None,
    *,
    legacy_result: Any = None,
    allow_legacy_fallback: bool = True,
    trace: bool = True,
    source: str = "scheduler_execution_gateway",
    **kwargs: Any,
) -> Dict[str, Any]:
    if step is None:
        return _export_scheduler_result_only(executor_or_value)

    gateway_result = run_scheduler_step_execution_gateway(
        executor_or_value,
        step,
        legacy_result=legacy_result,
        allow_legacy_fallback=allow_legacy_fallback,
        trace=trace,
        source=source,
        **kwargs,
    )
    return _export_scheduler_result_only(gateway_result)


__all__ = [
    "SchedulerExecutionGatewayResult",
    "build_noop_execution_result",
    "normalize_execution_result",
    "build_gateway_result",
    "run_scheduler_execution_gateway",
    "call_execution_gateway",
    "run_scheduler_step_execution_gateway",
    "export_scheduler_step_execution_result",
]
