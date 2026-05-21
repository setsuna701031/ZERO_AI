from pathlib import Path

TARGET = Path("core/runtime/step_executor.py")
MARKER = "# ZERO v7.3.10 - Adapter execution trace contract seal"

PATCH = r'''
# ZERO v7.3.10 - Adapter execution trace contract seal
# Keeps adapter_payload.execution_trace aligned with aggregate execution_trace.


_ZERO_V7310_PREVIOUS_ATTACH_ADAPTER_PAYLOAD = StepExecutor._attach_adapter_payload


def _zero_v7310_adapter_trace_event_from_execution_trace(item, sequence):
    event = item if isinstance(item, dict) else {}

    return {
        "sequence": int(sequence),
        "step_index": event.get("step_index"),
        "step_type": str(event.get("step_type") or ""),
        "runtime_mode": str(event.get("runtime_mode") or "execute"),
        "ok": bool(event.get("ok", False)),
        "message": str(event.get("message") or ""),
        "final_answer": str(event.get("final_answer") or ""),
        "error_type": event.get("error_type"),
        "classification": event.get("classification"),
        "attempts": event.get("attempts"),
        "max_attempts": event.get("max_attempts"),
        "retry_used": bool(event.get("retry_used", False)),
    }


def _zero_v7310_adapter_execution_trace_from_result(result):
    if not isinstance(result, dict):
        return []

    trace = result.get("execution_trace")
    if not isinstance(trace, list):
        return []

    output = []
    for index, item in enumerate(trace, start=1):
        if isinstance(item, dict):
            output.append(
                _zero_v7310_adapter_trace_event_from_execution_trace(
                    item,
                    index,
                )
            )

    return output


def _zero_v7310_attach_adapter_payload(self, result):
    normalized = _ZERO_V7310_PREVIOUS_ATTACH_ADAPTER_PAYLOAD(self, result)

    if not isinstance(normalized, dict):
        return normalized

    adapter_payload = normalized.get("adapter_payload")
    if not isinstance(adapter_payload, dict):
        adapter_payload = {}
        normalized["adapter_payload"] = adapter_payload

    adapter_payload["execution_trace"] = _zero_v7310_adapter_execution_trace_from_result(normalized)

    if "stream" not in adapter_payload or not isinstance(adapter_payload.get("stream"), list):
        adapter_payload["stream"] = copy.deepcopy(adapter_payload["execution_trace"])

    return normalized


StepExecutor._attach_adapter_payload = _zero_v7310_attach_adapter_payload
'''

def main() -> None:
    text = TARGET.read_text(encoding="utf-8")

    if MARKER in text:
        print("already patched:", TARGET)
        return

    if not text.endswith("\n"):
        text += "\n"

    TARGET.write_text(text + "\n" + PATCH.lstrip("\n"), encoding="utf-8")
    print("patched:", TARGET)


if __name__ == "__main__":
    main()