from __future__ import annotations

from pathlib import Path


REPO_STATE_PATH = Path("core/tasks/scheduler_core/repo_state_helpers.py")
TEST_PATH = Path("tests/test_failure_observability_envelope_contract.py")


OLD_FAILED_BLOCK = '''    task["history"] = scheduler._append_history(task.get("history"), "failed")

    scheduler._persist_task_payload(task_id=task_id, task=task)
    scheduler.worker_pool.release_by_task(task_id)
'''


NEW_FAILED_BLOCK = '''    task["history"] = scheduler._append_history(task.get("history"), "failed")
    task["observability_event"] = build_failure_observability_event(
        event_type="repo_task_failed",
        task=task,
        task_id=task_id,
        error_text=final_error,
        status="failed",
    )

    scheduler._persist_task_payload(task_id=task_id, task=task)
    scheduler.worker_pool.release_by_task(task_id)
'''


OLD_QUEUED_BLOCK = '''    task["history"] = scheduler._append_history(task.get("history"), "queued")
    scheduler._persist_task_payload(task_id=task_id, task=task)
'''


NEW_QUEUED_BLOCK = '''    task["history"] = scheduler._append_history(task.get("history"), "queued")
    if final_error:
        task["observability_event"] = build_failure_observability_event(
            event_type="repo_task_requeued",
            task=task,
            task_id=task_id,
            error_text=final_error,
            status="queued",
        )
    scheduler._persist_task_payload(task_id=task_id, task=task)
'''


HELPER_BLOCK = r'''

# ============================================================
# ZERO Runtime Observability Layer v1B
# Failure / Retry Observability Envelope
# ============================================================

def build_failure_observability_event(
    *,
    event_type: str,
    task: Dict[str, Any],
    task_id: str = "",
    error_text: str = "",
    status: str = "",
) -> Dict[str, Any]:
    task_payload = task if isinstance(task, dict) else {}
    resolved_task_id = str(
        task_id
        or task_payload.get("task_id")
        or task_payload.get("id")
        or task_payload.get("task_name")
        or ""
    ).strip()

    resolved_status = str(status or task_payload.get("status") or "").strip().lower()
    resolved_error = str(
        error_text
        or task_payload.get("last_error")
        or task_payload.get("failure_message")
        or ""
    ).strip()

    failure_type = str(
        task_payload.get("failure_type")
        or ("repo_task_failed" if resolved_status == "failed" else "repo_task_requeued")
    ).strip()

    event = {
        "event_type": str(event_type or "repo_task_failure"),
        "ok": False if resolved_status in {"failed", "error"} else True,
        "task_id": resolved_task_id,
        "status": resolved_status,
        "failure_type": failure_type,
        "error_text": resolved_error,
        "runtime_mode": "repo_state",
        "retry_count": int(task_payload.get("retry_count", 0) or 0),
        "replan_count": int(task_payload.get("replan_count", 0) or 0),
        "repair_fingerprint": str(task_payload.get("repair_fingerprint") or ""),
    }
    return event
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


class FailureObservabilityEnvelopeContractTest(unittest.TestCase):
    def test_build_failure_observability_event_failed(self) -> None:
        from core.tasks.scheduler_core.repo_state_helpers import build_failure_observability_event

        task: Dict[str, Any] = {
            "task_id": "task-1",
            "status": "failed",
            "failure_type": "execution_failed",
            "last_error": "boom",
            "retry_count": 1,
            "replan_count": 2,
            "repair_fingerprint": "fp-1",
        }

        event = build_failure_observability_event(
            event_type="repo_task_failed",
            task=copy.deepcopy(task),
            task_id="task-1",
            error_text="boom",
            status="failed",
        )

        self.assertEqual(event.get("event_type"), "repo_task_failed")
        self.assertIs(event.get("ok"), False)
        self.assertEqual(event.get("task_id"), "task-1")
        self.assertEqual(event.get("status"), "failed")
        self.assertEqual(event.get("failure_type"), "execution_failed")
        self.assertEqual(event.get("error_text"), "boom")
        self.assertEqual(event.get("runtime_mode"), "repo_state")
        self.assertEqual(event.get("retry_count"), 1)
        self.assertEqual(event.get("replan_count"), 2)
        self.assertEqual(event.get("repair_fingerprint"), "fp-1")

    def test_build_failure_observability_event_requeued(self) -> None:
        from core.tasks.scheduler_core.repo_state_helpers import build_failure_observability_event

        task: Dict[str, Any] = {
            "task_id": "task-2",
            "status": "queued",
            "failure_message": "retry later",
        }

        event = build_failure_observability_event(
            event_type="repo_task_requeued",
            task=copy.deepcopy(task),
            task_id="task-2",
            error_text="retry later",
            status="queued",
        )

        self.assertEqual(event.get("event_type"), "repo_task_requeued")
        self.assertIs(event.get("ok"), True)
        self.assertEqual(event.get("task_id"), "task-2")
        self.assertEqual(event.get("status"), "queued")
        self.assertEqual(event.get("error_text"), "retry later")
        self.assertEqual(event.get("runtime_mode"), "repo_state")

    def test_failure_observability_event_defaults_task_id_from_task(self) -> None:
        from core.tasks.scheduler_core.repo_state_helpers import build_failure_observability_event

        task: Dict[str, Any] = {
            "id": "fallback-id",
            "status": "failed",
            "last_error": "fallback error",
        }

        event = build_failure_observability_event(
            event_type="repo_task_failed",
            task=copy.deepcopy(task),
        )

        self.assertEqual(event.get("task_id"), "fallback-id")
        self.assertEqual(event.get("error_text"), "fallback error")
        self.assertEqual(event.get("status"), "failed")


if __name__ == "__main__":
    unittest.main()
'''


def main() -> None:
    if not REPO_STATE_PATH.exists():
        raise FileNotFoundError(REPO_STATE_PATH)

    source = REPO_STATE_PATH.read_text(encoding="utf-8")

    if "def build_failure_observability_event(" not in source:
        marker = "\ndef extract_effective_status_and_answer(\n"
        if marker not in source:
            raise RuntimeError("repo_state_helpers insertion marker not found")
        source = source.replace(marker, HELPER_BLOCK + marker, 1)

    if OLD_FAILED_BLOCK in source:
        source = source.replace(OLD_FAILED_BLOCK, NEW_FAILED_BLOCK, 1)

    if OLD_QUEUED_BLOCK in source:
        source = source.replace(OLD_QUEUED_BLOCK, NEW_QUEUED_BLOCK, 1)

    REPO_STATE_PATH.write_text(source, encoding="utf-8")
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")

    print("[failure-observability-envelope-v1] updated core/tasks/scheduler_core/repo_state_helpers.py")
    print("[failure-observability-envelope-v1] created tests/test_failure_observability_envelope_contract.py")


if __name__ == "__main__":
    main()