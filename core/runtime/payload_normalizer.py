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