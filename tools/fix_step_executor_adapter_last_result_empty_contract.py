from pathlib import Path

TARGET = Path("core/runtime/step_executor.py")
MARKER = "# ZERO v7.3.12 - Adapter empty last_result contract seal"

PATCH = r'''
# ZERO v7.3.12 - Adapter empty last_result contract seal
# Empty execute_steps([]) keeps adapter_payload.last_result as None.
# Non-empty aggregate keeps adapter_payload.last_result as dict.


_ZERO_V7312_PREVIOUS_ATTACH_ADAPTER_PAYLOAD = StepExecutor._attach_adapter_payload


def _zero_v7312_attach_adapter_payload(self, result):
    normalized = _ZERO_V7312_PREVIOUS_ATTACH_ADAPTER_PAYLOAD(self, result)

    if not isinstance(normalized, dict):
        return normalized

    adapter_payload = normalized.get("adapter_payload")
    if not isinstance(adapter_payload, dict):
        adapter_payload = {}
        normalized["adapter_payload"] = adapter_payload

    results = normalized.get("results")
    if isinstance(results, list) and len(results) == 0:
        adapter_payload["last_result"] = None

    return normalized


StepExecutor._attach_adapter_payload = _zero_v7312_attach_adapter_payload
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