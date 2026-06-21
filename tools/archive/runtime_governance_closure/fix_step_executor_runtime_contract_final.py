from pathlib import Path

TARGET = Path("core/runtime/step_executor.py")

START_MARKERS = [
    "# ZERO v7.3.6 - Runtime aggregate adapter/event stream seal",
    "# ZERO v7.3.7 - Runtime event phase contract seal",
    "# ZERO v7.3.8 - Runtime event schema contract seal",
    "# ZERO v7.3.9 - Runtime aggregate/event contract final seal",
]

FINAL_PATCH = r'''
# ZERO v7.3.9 - Runtime aggregate/event contract final seal
# Final StepExecutor aggregate contract seal:
#   - adapter_payload is always dict
#   - runtime_event_stream is always list
#   - each event has source/event_type/sequence/timestamp/runtime_phase/payload
#   - runtime_event_stream cardinality follows execution_trace exactly

def _zero_v739_now_iso():
    try:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
    except Exception:
        return ""


def _zero_v739_error_type_from_payload(payload):
    if not isinstance(payload, dict):
        return ""

    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("type") or error.get("error_type") or "")

    if error is not None:
        return str(error)

    return str(payload.get("error_type") or "")


def _zero_v739_error_text_from_payload(payload):
    if not isinstance(payload, dict):
        return ""

    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("text") or "")

    if error is not None:
        return str(error)

    return ""


def _zero_v739_safe_adapter_payload(result):
    payload = result if isinstance(result, dict) else {}

    message = str(payload.get("message") or "")
    final_answer = str(payload.get("final_answer") or "")
    error_type = _zero_v739_error_type_from_payload(payload)
    error_text = _zero_v739_error_text_from_payload(payload)
    text = message or final_answer or error_text

    return {
        "ok": bool(payload.get("ok", False)),
        "message": message,
        "final_answer": final_answer,
        "text": text,
        "error_text": error_text,
        "error_type": error_type,
        "summary": str(payload.get("summary") or ""),
        "step_type": str(payload.get("step_type") or ""),
        "step_index": payload.get("step_index"),
        "step_count": payload.get("step_count"),
        "completed_steps": payload.get("completed_steps"),
        "failed_step": payload.get("failed_step"),
    }


def _zero_v739_attach_adapter_payload(self, result):
    normalized = copy.deepcopy(result) if isinstance(result, dict) else {}
    adapter_input = _zero_v739_safe_adapter_payload(normalized)

    adapter_payload = None
    try:
        from core.runtime.payload_normalizer import normalize_runtime_adapter_payload
        adapter_payload = normalize_runtime_adapter_payload(adapter_input)
    except Exception:
        adapter_payload = None

    if not isinstance(adapter_payload, dict):
        adapter_payload = dict(adapter_input)

    if not isinstance(adapter_payload.get("ok"), bool):
        adapter_payload["ok"] = bool(adapter_input.get("ok", False))

    for key in (
        "message",
        "final_answer",
        "text",
        "error_text",
        "error_type",
        "summary",
        "step_type",
    ):
        if adapter_payload.get(key) is None:
            adapter_payload[key] = str(adapter_input.get(key) or "")

    for key in ("step_index", "step_count", "completed_steps", "failed_step"):
        if key not in adapter_payload:
            adapter_payload[key] = adapter_input.get(key)

    normalized["adapter_payload"] = adapter_payload
    return normalized


def _zero_v739_runtime_phase_from_trace_event(event):
    if not isinstance(event, dict):
        return "execute"

    for key in ("runtime_phase", "phase", "runtime_mode"):
        value = event.get(key)
        if value is None or not str(value).strip():
            continue

        text = str(value).strip().lower()

        if text in {"execution", "run", "running"}:
            return "execute"

        if text in {"verification"}:
            return "verify"

        return text

    return "execute"


def _zero_v739_event_payload_from_trace_event(event):
    item = event if isinstance(event, dict) else {}

    return {
        "step_index": item.get("step_index"),
        "step_type": str(item.get("step_type") or ""),
        "runtime_mode": str(item.get("runtime_mode") or "execute"),
        "ok": bool(item.get("ok", False)),
        "message": str(item.get("message") or ""),
        "final_answer": str(item.get("final_answer") or ""),
        "error_type": item.get("error_type"),
        "classification": item.get("classification"),
        "attempts": item.get("attempts"),
        "max_attempts": item.get("max_attempts"),
        "retry_used": bool(item.get("retry_used", False)),
    }


def _zero_v739_event_from_trace_event(event, sequence, source):
    item = event if isinstance(event, dict) else {}
    runtime_phase = _zero_v739_runtime_phase_from_trace_event(item)

    return {
        "source": str(source or "step_executor"),
        "event_type": str(item.get("event_type") or "step_execution_result"),
        "sequence": int(sequence),
        "timestamp": str(item.get("timestamp") or _zero_v739_now_iso()),
        "runtime_phase": runtime_phase,
        "payload": _zero_v739_event_payload_from_trace_event(item),
    }


def _zero_v739_build_runtime_event_stream(payload, source):
    if not isinstance(payload, dict):
        return []

    trace = payload.get("execution_trace")
    if not isinstance(trace, list):
        return []

    stream = []
    for index, item in enumerate(trace, start=1):
        if isinstance(item, dict):
            stream.append(
                _zero_v739_event_from_trace_event(
                    event=item,
                    sequence=index,
                    source=source,
                )
            )

    return stream


def _zero_v739_attach_runtime_event_stream(payload, source="step_executor"):
    if not isinstance(payload, dict):
        return payload

    stream = _zero_v739_build_runtime_event_stream(
        payload=payload,
        source=source,
    )

    payload["runtime_event_stream"] = stream
    payload["event_stream"] = copy.deepcopy(stream)
    return payload


StepExecutor._attach_adapter_payload = _zero_v739_attach_adapter_payload
attach_runtime_event_stream = _zero_v739_attach_runtime_event_stream
'''


def strip_old_zero_runtime_patches(text: str) -> str:
    cut_positions = [
        text.find(marker)
        for marker in START_MARKERS
        if text.find(marker) >= 0
    ]

    if not cut_positions:
        return text

    cut_at = min(cut_positions)
    return text[:cut_at].rstrip() + "\n"


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    text = strip_old_zero_runtime_patches(text)

    if not text.endswith("\n"):
        text += "\n"

    TARGET.write_text(text + "\n" + FINAL_PATCH.lstrip("\n"), encoding="utf-8")
    print("patched:", TARGET)


if __name__ == "__main__":
    main()