from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional


@dataclass(frozen=True)
class NormalizedRuntimePayload:
    ok: Optional[bool]
    text: str
    message: str
    final_answer: str
    error_text: str
    error_type: str
    raw: Any

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "text": self.text,
            "message": self.message,
            "final_answer": self.final_answer,
            "error_text": self.error_text,
            "error_type": self.error_type,
            "raw": self.raw,
        }


def _as_mapping(value: Any) -> Optional[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return value
    return None


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _first_text(payload: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        text = _as_text(payload.get(key))
        if text:
            return text
    return ""


def _extract_nested_payload(payload: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    for key in ("payload", "result", "runner_result", "previous_result"):
        nested = _as_mapping(payload.get(key))
        if nested is not None:
            return nested
    return None


def extract_runtime_text(value: Any) -> str:
    payload = _as_mapping(value)
    if payload is None:
        return _as_text(value)

    direct = _first_text(
        payload,
        (
            "text",
            "content",
            "message",
            "final_answer",
            "summary",
            "stdout",
            "stderr",
        ),
    )
    if direct:
        return direct

    nested = _extract_nested_payload(payload)
    if nested is not None:
        return extract_runtime_text(nested)

    return ""


def extract_runtime_error_text(value: Any) -> str:
    payload = _as_mapping(value)
    if payload is None:
        if isinstance(value, str):
            return value.strip()
        return ""

    error = _as_mapping(payload.get("error"))
    if error is not None:
        error_message = _first_text(error, ("message", "text", "detail", "type"))
        if error_message:
            return error_message

    direct = _first_text(
        payload,
        (
            "error_text",
            "last_error",
            "stderr",
            "message",
            "final_answer",
            "text",
            "content",
        ),
    )
    if direct:
        return direct

    nested = _extract_nested_payload(payload)
    if nested is not None:
        return extract_runtime_error_text(nested)

    return ""


def extract_runtime_error_type(value: Any) -> str:
    payload = _as_mapping(value)
    if payload is None:
        return ""

    error = _as_mapping(payload.get("error"))
    if error is not None:
        error_type = _as_text(error.get("type"))
        if error_type:
            return error_type

    direct = _as_text(payload.get("error_type"))
    if direct:
        return direct

    nested = _extract_nested_payload(payload)
    if nested is not None:
        return extract_runtime_error_type(nested)

    return ""


def normalize_runtime_payload(value: Any) -> NormalizedRuntimePayload:
    payload = _as_mapping(value)

    ok: Optional[bool] = None
    if payload is not None and isinstance(payload.get("ok"), bool):
        ok = bool(payload.get("ok"))

    text = extract_runtime_text(value)
    error_text = extract_runtime_error_text(value)
    error_type = extract_runtime_error_type(value)

    message = ""
    final_answer = ""

    if payload is not None:
        message = _as_text(payload.get("message"))
        final_answer = _as_text(payload.get("final_answer"))

    if not message:
        message = text

    if not final_answer:
        final_answer = text

    return NormalizedRuntimePayload(
        ok=ok,
        text=text,
        message=message,
        final_answer=final_answer,
        error_text=error_text,
        error_type=error_type,
        raw=value,
    )

def extract_runtime_failure_text(task: Any, runner_result: Any = None) -> str:
    candidates: list[Any] = []

    runner_payload = _as_mapping(runner_result)
    if runner_payload is not None:
        candidates.extend(
            [
                runner_payload.get("last_error"),
                runner_payload.get("failure_message"),
                runner_payload.get("error"),
                runner_payload.get("message"),
                runner_payload.get("final_answer"),
                runner_payload.get("last_step_result"),
                runner_payload.get("result"),
                runner_payload.get("task"),
            ]
        )

    task_payload = _as_mapping(task)
    if task_payload is not None:
        candidates.extend(
            [
                task_payload.get("last_error"),
                task_payload.get("failure_message"),
                task_payload.get("error"),
                task_payload.get("message"),
                task_payload.get("final_answer"),
                task_payload.get("last_step_result"),
            ]
        )

        for key in ("step_results", "results", "execution_log"):
            items = task_payload.get(key)
            if isinstance(items, list):
                candidates.extend(reversed(items[-5:]))

    for candidate in candidates:
        text = extract_runtime_error_text(candidate)
        if text:
            return text

    return ""

def normalize_runtime_adapter_payload(value: Any) -> Dict[str, Any]:
    payload = _as_mapping(value)
    normalized = normalize_runtime_payload(value)

    result: Dict[str, Any] = {
        "ok": normalized.ok,
        "message": normalized.message,
        "final_answer": normalized.final_answer,
        "text": normalized.text,
        "error_text": normalized.error_text,
        "error_type": normalized.error_type,
        "runtime_mode": "",
        "last_result": None,
        "execution_trace": [],
        "raw": value,
    }

    if payload is None:
        return result

    runtime_mode = _as_text(payload.get("runtime_mode"))
    if runtime_mode:
        result["runtime_mode"] = runtime_mode

    last_result = payload.get("last_result")
    if isinstance(last_result, dict):
        result["last_result"] = last_result

    trace = payload.get("execution_trace")
    if isinstance(trace, list):
        result["execution_trace"] = [item for item in trace if isinstance(item, dict)]

    return result

