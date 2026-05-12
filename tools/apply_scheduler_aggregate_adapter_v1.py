from __future__ import annotations

from pathlib import Path


SCHEDULER_PATH = Path("core/tasks/scheduler.py")
TEST_PATH = Path("tests/test_scheduler_aggregate_adapter_contract.py")


HELPER_BLOCK = r'''

# ============================================================
# ZERO Runtime Aggregate Convergence v1.1
# Scheduler Aggregate Adapter Payload
# ============================================================

def _zero_v11_scheduler_bool(value):
    return bool(value)


def _zero_v11_scheduler_str(value, default=""):
    if value is None:
        return default
    text = str(value)
    return text if text else default


def _zero_v11_scheduler_copy_dict(value):
    if isinstance(value, dict):
        try:
            return copy.deepcopy(value)
        except Exception:
            return dict(value)
    return {}


def _zero_v11_extract_scheduler_error_type(payload):
    if not isinstance(payload, dict):
        return ""

    error = payload.get("error")
    if isinstance(error, dict):
        for key in ("type", "error_type", "code"):
            value = error.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        message = error.get("message")
        if message is not None and str(message).strip():
            return "scheduler_error"

    if isinstance(error, str) and error.strip():
        return "scheduler_error"

    for key in ("error_type", "failure_type"):
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()

    return ""


def _zero_v11_extract_scheduler_error_text(payload):
    if not isinstance(payload, dict):
        return ""

    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message") or error.get("error") or error.get("text")
        if message is not None and str(message).strip():
            return str(message).strip()
        if error:
            return str(error)

    if isinstance(error, str) and error.strip():
        return error.strip()

    for key in ("error_text", "message", "final_answer"):
        value = payload.get(key)
        if value is not None and str(value).strip():
            if key == "message" and bool(payload.get("ok", False)):
                continue
            return str(value).strip()

    return ""


def _zero_v11_extract_scheduler_runtime_mode(payload):
    if not isinstance(payload, dict):
        return ""

    for key in ("runtime_mode", "mode", "execution_mode"):
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()

    runtime_context = payload.get("runtime_context")
    if isinstance(runtime_context, dict):
        for key in ("runtime_mode", "mode", "execution_mode"):
            value = runtime_context.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()

    return ""


def _zero_v11_extract_scheduler_trace(payload):
    if not isinstance(payload, dict):
        return []

    trace = payload.get("execution_trace")
    if isinstance(trace, list):
        try:
            return copy.deepcopy(trace)
        except Exception:
            return list(trace)

    result = payload.get("result")
    if isinstance(result, dict):
        nested = result.get("execution_trace")
        if isinstance(nested, list):
            try:
                return copy.deepcopy(nested)
            except Exception:
                return list(nested)

    return []


def _zero_v11_attach_scheduler_adapter_payload(result):
    if not isinstance(result, dict):
        return result

    if isinstance(result.get("adapter_payload"), dict):
        return result

    payload = copy.deepcopy(result)

    ok = bool(payload.get("ok", False))
    message = _zero_v11_scheduler_str(payload.get("message"), "執行完成" if ok else "執行失敗")
    final_answer = _zero_v11_scheduler_str(payload.get("final_answer"), message)

    adapter_payload = {
        "ok": ok,
        "message": message,
        "final_answer": final_answer,
        "text": final_answer or message,
        "error_text": "" if ok else _zero_v11_extract_scheduler_error_text(payload),
        "error_type": "" if ok else _zero_v11_extract_scheduler_error_type(payload),
        "runtime_mode": _zero_v11_extract_scheduler_runtime_mode(payload),
        "last_result": _zero_v11_scheduler_copy_dict(payload.get("last_result")),
        "execution_trace": _zero_v11_extract_scheduler_trace(payload),
        "raw": payload,
    }

    result["adapter_payload"] = adapter_payload
    return result
'''


OLD_WRAPPER = '''def _zero_v352_scheduler_run_one_step(
    self,
    task: Dict[str, Any],
    current_tick: Optional[int] = None,
) -> Dict[str, Any]:
    result = _ZERO_V352_ORIGINAL_SCHEDULER_RUN_ONE_STEP(
        self,
        task=task,
        current_tick=current_tick,
    )

    if not isinstance(result, dict):
        return result

    try:
        enriched = self._attach_orchestration_summary_to_runner_result(
            task=task if isinstance(task, dict) else {},
            runner_result=result,
        )
        return enriched if isinstance(enriched, dict) else result
    except Exception:
        return result
'''


NEW_WRAPPER = '''def _zero_v352_scheduler_run_one_step(
    self,
    task: Dict[str, Any],
    current_tick: Optional[int] = None,
) -> Dict[str, Any]:
    result = _ZERO_V352_ORIGINAL_SCHEDULER_RUN_ONE_STEP(
        self,
        task=task,
        current_tick=current_tick,
    )

    if not isinstance(result, dict):
        return result

    try:
        enriched = self._attach_orchestration_summary_to_runner_result(
            task=task if isinstance(task, dict) else {},
            runner_result=result,
        )
        result = enriched if isinstance(enriched, dict) else result
    except Exception:
        pass

    return _zero_v11_attach_scheduler_adapter_payload(result)
'''


TEST_CONTENT = r'''from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class SchedulerAggregateAdapterContractTest(unittest.TestCase):
    def test_scheduler_success_result_gets_adapter_payload(self) -> None:
        from core.tasks.scheduler import _zero_v11_attach_scheduler_adapter_payload

        result: Dict[str, Any] = {
            "ok": True,
            "message": "done",
            "final_answer": "done",
            "runtime_mode": "execute",
            "execution_trace": [{"step": 1, "ok": True}],
        }

        adapted = _zero_v11_attach_scheduler_adapter_payload(copy.deepcopy(result))
        adapter = adapted.get("adapter_payload")

        self.assertIsInstance(adapter, dict)
        self.assertIs(adapter.get("ok"), True)
        self.assertEqual(adapter.get("message"), "done")
        self.assertEqual(adapter.get("final_answer"), "done")
        self.assertEqual(adapter.get("text"), "done")
        self.assertEqual(adapter.get("error_text"), "")
        self.assertEqual(adapter.get("error_type"), "")
        self.assertEqual(adapter.get("runtime_mode"), "execute")
        self.assertEqual(adapter.get("execution_trace"), [{"step": 1, "ok": True}])
        self.assertIsInstance(adapter.get("raw"), dict)

    def test_scheduler_failed_result_gets_error_payload(self) -> None:
        from core.tasks.scheduler import _zero_v11_attach_scheduler_adapter_payload

        result: Dict[str, Any] = {
            "ok": False,
            "message": "failed",
            "final_answer": "failed",
            "error": {
                "type": "scheduler_failed",
                "message": "boom",
            },
            "execution_trace": [{"step": 1, "ok": False}],
        }

        adapted = _zero_v11_attach_scheduler_adapter_payload(copy.deepcopy(result))
        adapter = adapted.get("adapter_payload")

        self.assertIsInstance(adapter, dict)
        self.assertIs(adapter.get("ok"), False)
        self.assertEqual(adapter.get("message"), "failed")
        self.assertEqual(adapter.get("final_answer"), "failed")
        self.assertEqual(adapter.get("error_text"), "boom")
        self.assertEqual(adapter.get("error_type"), "scheduler_failed")
        self.assertEqual(adapter.get("execution_trace"), [{"step": 1, "ok": False}])

    def test_scheduler_existing_adapter_payload_is_preserved(self) -> None:
        from core.tasks.scheduler import _zero_v11_attach_scheduler_adapter_payload

        result: Dict[str, Any] = {
            "ok": True,
            "adapter_payload": {
                "ok": True,
                "message": "already adapted",
            },
        }

        adapted = _zero_v11_attach_scheduler_adapter_payload(result)

        self.assertIs(adapted, result)
        self.assertEqual(adapted["adapter_payload"]["message"], "already adapted")


if __name__ == "__main__":
    unittest.main()
'''


def main() -> None:
    if not SCHEDULER_PATH.exists():
        raise FileNotFoundError(SCHEDULER_PATH)

    source = SCHEDULER_PATH.read_text(encoding="utf-8")

    if "_zero_v11_attach_scheduler_adapter_payload" not in source:
        marker = "_ZERO_V352_ORIGINAL_SCHEDULER_RUN_ONE_STEP = Scheduler.run_one_step\n"
        if marker not in source:
            raise RuntimeError("final run_one_step wrapper marker not found")
        source = source.replace(marker, HELPER_BLOCK + "\n\n" + marker, 1)

    if OLD_WRAPPER in source:
        source = source.replace(OLD_WRAPPER, NEW_WRAPPER, 1)
    elif NEW_WRAPPER not in source:
        raise RuntimeError("target final wrapper not found or already changed unexpectedly")

    SCHEDULER_PATH.write_text(source, encoding="utf-8")
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")

    print("[scheduler-aggregate-adapter-v1] updated core/tasks/scheduler.py")
    print("[scheduler-aggregate-adapter-v1] created tests/test_scheduler_aggregate_adapter_contract.py")


if __name__ == "__main__":
    main()