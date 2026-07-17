from pathlib import Path

TARGET = Path("core/runtime/step_executor.py")
MARKER = "# ZERO v7.3.11 - Adapter last_result contract seal"

PATCH = r'''
# ZERO v7.3.11 - Adapter last_result contract seal
# Ensures adapter_payload.last_result is always a dict.


_ZERO_V7311_PREVIOUS_ATTACH_ADAPTER_PAYLOAD = StepExecutor._attach_adapter_payload


def _zero_v7311_safe_last_result_from_result(result):
    if not isinstance(result, dict):
        return {}

    last_result = result.get("last_result")
    if isinstance(last_result, dict):
        return {
            "ok": bool(last_result.get("ok", False)),
            "step_type": str(last_result.get("step_type") or ""),
            "step_index": last_result.get("step_index"),
            "step_count": last_result.get("step_count"),
            "runtime_mode": str(last_result.get("runtime_mode") or ""),
            "message": str(last_result.get("message") or ""),
            "final_answer": str(last_result.get("final_answer") or ""),
            "error": copy.deepcopy(last_result.get("error")),
        }

    results = result.get("results")
    if isinstance(results, list) and results:
        candidate = results[-1]
        if isinstance(candidate, dict):
            return {
                "ok": bool(candidate.get("ok", False)),
                "step_type": str(candidate.get("step_type") or ""),
                "step_index": candidate.get("step_index"),
                "step_count": candidate.get("step_count"),
                "runtime_mode": str(candidate.get("runtime_mode") or ""),
                "message": str(candidate.get("message") or ""),
                "final_answer": str(candidate.get("final_answer") or ""),
                "error": copy.deepcopy(candidate.get("error")),
            }

    return {}


def _zero_v7311_attach_adapter_payload(self, result):
    normalized = _ZERO_V7311_PREVIOUS_ATTACH_ADAPTER_PAYLOAD(self, result)

    if not isinstance(normalized, dict):
        return normalized

    adapter_payload = normalized.get("adapter_payload")
    if not isinstance(adapter_payload, dict):
        adapter_payload = {}
        normalized["adapter_payload"] = adapter_payload

    adapter_payload["last_result"] = _zero_v7311_safe_last_result_from_result(normalized)

    return normalized


StepExecutor._attach_adapter_payload = _zero_v7311_attach_adapter_payload
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