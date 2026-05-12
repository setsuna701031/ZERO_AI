from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RepoRuntimeStateAdapterContractTest(unittest.TestCase):
    def test_success_repo_runtime_state_gets_adapter_payload(self) -> None:
        from core.tasks.scheduler_core.repo_state_helpers import attach_repo_runtime_state_adapter_payload

        payload: Dict[str, Any] = {
            "status": "finished",
            "final_answer": "done",
            "runtime_mode": "repo_state",
            "execution_trace": [{"step": 1, "ok": True}],
        }

        adapted = attach_repo_runtime_state_adapter_payload(copy.deepcopy(payload))
        adapter = adapted.get("adapter_payload")

        self.assertIsInstance(adapter, dict)
        self.assertIs(adapter.get("ok"), True)
        self.assertEqual(adapter.get("message"), "done")
        self.assertEqual(adapter.get("final_answer"), "done")
        self.assertEqual(adapter.get("runtime_mode"), "repo_state")
        self.assertEqual(adapter.get("execution_trace"), [{"step": 1, "ok": True}])

    def test_failed_repo_runtime_state_gets_error_payload(self) -> None:
        from core.tasks.scheduler_core.repo_state_helpers import attach_repo_runtime_state_adapter_payload

        payload: Dict[str, Any] = {
            "status": "failed",
            "failure_type": "execution_failed",
            "failure_message": "boom",
            "last_error": "boom",
        }

        adapted = attach_repo_runtime_state_adapter_payload(copy.deepcopy(payload))
        adapter = adapted.get("adapter_payload")

        self.assertIsInstance(adapter, dict)
        self.assertIs(adapter.get("ok"), False)
        self.assertEqual(adapter.get("error_type"), "execution_failed")
        self.assertEqual(adapter.get("error_text"), "boom")
        self.assertEqual(adapter.get("runtime_mode"), "repo_state")

    def test_build_repo_runtime_state_adapter_uses_runner_result(self) -> None:
        from core.tasks.scheduler_core.repo_state_helpers import build_repo_runtime_state_adapter_payload

        merged: Dict[str, Any] = {
            "status": "running",
            "final_answer": "",
        }
        runner_result: Dict[str, Any] = {
            "ok": True,
            "message": "runner ok",
            "final_answer": "runner done",
            "runtime_mode": "execute",
            "execution_trace": [{"runner": True}],
            "last_result": {"ok": True},
        }

        adapted = build_repo_runtime_state_adapter_payload(
            merged=copy.deepcopy(merged),
            runner_result=copy.deepcopy(runner_result),
        )
        adapter = adapted.get("adapter_payload")

        self.assertIsInstance(adapter, dict)
        self.assertIs(adapter.get("ok"), True)
        self.assertEqual(adapter.get("message"), "runner ok")
        self.assertEqual(adapter.get("final_answer"), "runner done")
        self.assertEqual(adapter.get("runtime_mode"), "execute")
        self.assertEqual(adapter.get("execution_trace"), [{"runner": True}])
        self.assertEqual(adapter.get("last_result"), {"ok": True})

    def test_existing_adapter_payload_is_preserved_from_runner(self) -> None:
        from core.tasks.scheduler_core.repo_state_helpers import build_repo_runtime_state_adapter_payload

        merged: Dict[str, Any] = {
            "status": "running",
        }
        runner_result: Dict[str, Any] = {
            "ok": True,
            "adapter_payload": {
                "ok": True,
                "message": "already adapted",
            },
        }

        adapted = build_repo_runtime_state_adapter_payload(
            merged=copy.deepcopy(merged),
            runner_result=copy.deepcopy(runner_result),
        )

        self.assertEqual(adapted["adapter_payload"]["message"], "already adapted")


if __name__ == "__main__":
    unittest.main()
