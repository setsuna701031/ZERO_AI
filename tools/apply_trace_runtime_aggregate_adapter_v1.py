from __future__ import annotations

from pathlib import Path


TRACE_RUNTIME_PATH = Path("core/runtime/trace_runtime.py")
TEST_PATH = Path("tests/test_trace_runtime_aggregate_adapter_contract.py")


HELPER_BLOCK = r'''

    # ============================================================
    # ZERO Runtime Aggregate Convergence v1.2
    # Trace Runtime Aggregate Adapter Payload
    # ============================================================

    def attach_adapter_payload(self, payload: Any) -> Any:
        if not isinstance(payload, dict):
            return payload

        if isinstance(payload.get("adapter_payload"), dict):
            return payload

        ok = bool(payload.get("ok", True))
        message = self._adapter_str(
            payload.get("message"),
            "trace runtime ok" if ok else "trace runtime failed",
        )
        final_answer = self._adapter_str(payload.get("final_answer"), message)

        adapter_payload = {
            "ok": ok,
            "message": message,
            "final_answer": final_answer,
            "text": final_answer or message,
            "error_text": "" if ok else self._adapter_error_text(payload),
            "error_type": "" if ok else self._adapter_error_type(payload),
            "runtime_mode": self._adapter_runtime_mode(payload),
            "last_result": self._adapter_copy_dict(payload.get("last_result")),
            "execution_trace": self._adapter_execution_trace(payload),
            "raw": copy.deepcopy(payload),
        }

        payload["adapter_payload"] = adapter_payload
        return payload

    def trace_adapter_payload(
        self,
        *,
        ok: bool = True,
        message: str = "",
        final_answer: str = "",
        runtime_mode: str = "trace",
        execution_trace: Optional[list[dict[str, Any]]] = None,
        last_result: Optional[Dict[str, Any]] = None,
        error: Optional[Any] = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "ok": bool(ok),
            "message": str(message or ("trace runtime ok" if ok else "trace runtime failed")),
            "final_answer": str(final_answer or message or ("trace runtime ok" if ok else "trace runtime failed")),
            "runtime_mode": str(runtime_mode or "trace"),
            "execution_trace": copy.deepcopy(execution_trace) if isinstance(execution_trace, list) else [],
            "last_result": copy.deepcopy(last_result) if isinstance(last_result, dict) else {},
            "error": copy.deepcopy(error) if error is not None else None,
        }

        for key, value in extra.items():
            if key not in payload:
                payload[key] = copy.deepcopy(value)

        return self.attach_adapter_payload(payload)

    def trace_to_adapter_payload(self, trace: Any, *, message: str = "trace runtime ok") -> Dict[str, Any]:
        if hasattr(trace, "to_dict") and callable(getattr(trace, "to_dict")):
            trace_payload = trace.to_dict()
        elif isinstance(trace, dict):
            trace_payload = copy.deepcopy(trace)
        elif isinstance(trace, list):
            trace_payload = {"events": copy.deepcopy(trace)}
        else:
            trace_payload = {"events": []}

        events = trace_payload.get("events")
        if not isinstance(events, list):
            events = []

        payload = {
            "ok": True,
            "message": message,
            "final_answer": message,
            "runtime_mode": "trace",
            "execution_trace": copy.deepcopy(events),
            "last_result": copy.deepcopy(events[-1]) if events else {},
            "trace": trace_payload,
            "event_count": len(events),
            "error": None,
        }
        return self.attach_adapter_payload(payload)

    def _adapter_str(self, value: Any, default: str = "") -> str:
        if value is None:
            return default
        text = str(value)
        return text if text else default

    def _adapter_copy_dict(self, value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return copy.deepcopy(value)
        return {}

    def _adapter_runtime_mode(self, payload: Dict[str, Any]) -> str:
        for key in ("runtime_mode", "mode", "execution_mode"):
            value = payload.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return "trace"

    def _adapter_execution_trace(self, payload: Dict[str, Any]) -> list[dict[str, Any]]:
        trace = payload.get("execution_trace")
        if isinstance(trace, list):
            return copy.deepcopy(trace)

        trace_payload = payload.get("trace")
        if isinstance(trace_payload, dict):
            events = trace_payload.get("events")
            if isinstance(events, list):
                return copy.deepcopy(events)

        return []

    def _adapter_error_type(self, payload: Dict[str, Any]) -> str:
        error = payload.get("error")
        if isinstance(error, dict):
            for key in ("type", "error_type", "code"):
                value = error.get(key)
                if value is not None and str(value).strip():
                    return str(value).strip()
            return "trace_runtime_error" if error else ""

        if isinstance(error, str) and error.strip():
            return "trace_runtime_error"

        value = payload.get("error_type")
        if value is not None and str(value).strip():
            return str(value).strip()

        return ""

    def _adapter_error_text(self, payload: Dict[str, Any]) -> str:
        error = payload.get("error")
        if isinstance(error, dict):
            for key in ("message", "error", "text"):
                value = error.get(key)
                if value is not None and str(value).strip():
                    return str(value).strip()
            return str(error) if error else ""

        if isinstance(error, str) and error.strip():
            return error.strip()

        for key in ("error_text", "message", "final_answer"):
            value = payload.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()

        return ""
'''


TEST_CONTENT = r'''from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TraceRuntimeAggregateAdapterContractTest(unittest.TestCase):
    def test_trace_runtime_payload_gets_adapter_payload(self) -> None:
        from core.runtime.trace_runtime import TraceRuntime

        runtime = TraceRuntime()
        payload: Dict[str, Any] = {
            "ok": True,
            "message": "trace ok",
            "final_answer": "trace ok",
            "runtime_mode": "trace",
            "execution_trace": [{"event": "step", "ok": True}],
        }

        adapted = runtime.attach_adapter_payload(copy.deepcopy(payload))
        adapter = adapted.get("adapter_payload")

        self.assertIsInstance(adapter, dict)
        self.assertIs(adapter.get("ok"), True)
        self.assertEqual(adapter.get("message"), "trace ok")
        self.assertEqual(adapter.get("final_answer"), "trace ok")
        self.assertEqual(adapter.get("runtime_mode"), "trace")
        self.assertEqual(adapter.get("execution_trace"), [{"event": "step", "ok": True}])
        self.assertIsInstance(adapter.get("raw"), dict)

    def test_trace_runtime_failure_payload_gets_error_fields(self) -> None:
        from core.runtime.trace_runtime import TraceRuntime

        runtime = TraceRuntime()
        payload: Dict[str, Any] = {
            "ok": False,
            "message": "trace failed",
            "final_answer": "trace failed",
            "runtime_mode": "trace",
            "error": {
                "type": "trace_save_failed",
                "message": "disk error",
            },
        }

        adapted = runtime.attach_adapter_payload(copy.deepcopy(payload))
        adapter = adapted.get("adapter_payload")

        self.assertIsInstance(adapter, dict)
        self.assertIs(adapter.get("ok"), False)
        self.assertEqual(adapter.get("error_type"), "trace_save_failed")
        self.assertEqual(adapter.get("error_text"), "disk error")
        self.assertEqual(adapter.get("runtime_mode"), "trace")

    def test_trace_to_adapter_payload_uses_execution_trace_events(self) -> None:
        from core.runtime.trace_runtime import TraceRuntime
        from core.tools.execution_trace import ExecutionTrace

        runtime = TraceRuntime()
        trace = ExecutionTrace()
        trace.add_step_event(
            task_id="task-1",
            step_index=1,
            step={"type": "respond"},
            ok=True,
            result={"ok": True, "message": "done"},
            error="",
            tick=1,
        )

        adapted = runtime.trace_to_adapter_payload(trace)
        adapter = adapted.get("adapter_payload")

        self.assertIsInstance(adapter, dict)
        self.assertIs(adapter.get("ok"), True)
        self.assertEqual(adapter.get("runtime_mode"), "trace")
        self.assertEqual(adapted.get("event_count"), 1)
        self.assertEqual(len(adapter.get("execution_trace")), 1)
        self.assertIsInstance(adapter.get("last_result"), dict)

    def test_existing_adapter_payload_is_preserved(self) -> None:
        from core.runtime.trace_runtime import TraceRuntime

        runtime = TraceRuntime()
        payload: Dict[str, Any] = {
            "ok": True,
            "adapter_payload": {
                "ok": True,
                "message": "already adapted",
            },
        }

        adapted = runtime.attach_adapter_payload(payload)

        self.assertIs(adapted, payload)
        self.assertEqual(adapted["adapter_payload"]["message"], "already adapted")


if __name__ == "__main__":
    unittest.main()
'''


def main() -> None:
    if not TRACE_RUNTIME_PATH.exists():
        raise FileNotFoundError(TRACE_RUNTIME_PATH)

    source = TRACE_RUNTIME_PATH.read_text(encoding="utf-8")

    if "def attach_adapter_payload(self, payload: Any) -> Any:" not in source:
        marker = "\n    def _task_id(self, task: Dict[str, Any]) -> str:\n"
        if marker not in source:
            raise RuntimeError("TraceRuntime _task_id marker not found")
        source = source.replace(marker, HELPER_BLOCK + marker, 1)

    TRACE_RUNTIME_PATH.write_text(source, encoding="utf-8")
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")

    print("[trace-runtime-aggregate-adapter-v1] updated core/runtime/trace_runtime.py")
    print("[trace-runtime-aggregate-adapter-v1] created tests/test_trace_runtime_aggregate_adapter_contract.py")


if __name__ == "__main__":
    main()