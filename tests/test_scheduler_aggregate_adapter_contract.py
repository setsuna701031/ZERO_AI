from __future__ import annotations

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
