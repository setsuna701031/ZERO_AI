from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class SchedulerPayloadConvergenceGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        from core.tasks.scheduler import Scheduler

        self.scheduler = Scheduler.__new__(Scheduler)

    def test_text_extraction_uses_runtime_normalizer_semantics(self) -> None:
        payload: Dict[str, Any] = {
            "text": "legacy text",
            "content": "legacy content",
            "message": "canonical message",
            "final_answer": "canonical final",
        }

        self.assertEqual(
            self.scheduler._extract_text_from_result_payload(payload),
            "legacy text",
        )

    def test_text_extraction_preserves_nested_runtime_payload_semantics(self) -> None:
        payload: Dict[str, Any] = {
            "result": {
                "payload": {
                    "message": "nested message",
                    "final_answer": "nested final",
                }
            }
        }

        self.assertEqual(
            self.scheduler._extract_text_from_result_payload(payload),
            "nested message",
        )

    def test_error_extraction_uses_runtime_normalizer_semantics(self) -> None:
        payload: Dict[str, Any] = {
            "message": "generic message",
            "error": {
                "type": "runtime_error",
                "message": "canonical error message",
            },
        }

        self.assertEqual(
            self.scheduler._extract_error_text_deep(payload),
            "canonical error message",
        )

    def test_error_extraction_preserves_plain_string_semantics(self) -> None:
        self.assertEqual(
            self.scheduler._extract_error_text_deep("plain runtime error"),
            "plain runtime error",
        )

    def test_failure_retry_collapse_uses_runner_result_first(self) -> None:
        runner_result: Dict[str, Any] = {
            "error": {
                "type": "runtime_error",
                "message": "runner error message",
            }
        }
        task: Dict[str, Any] = {
            "last_error": "task last error",
            "results": [
                {"error": {"message": "task result error"}},
            ],
        }

        self.assertEqual(
            self.scheduler._extract_failure_text_for_retry_collapse(
                task=task,
                runner_result=runner_result,
            ),
            "runner error message",
        )

    def test_failure_retry_collapse_preserves_task_last_error_priority(self) -> None:
        task: Dict[str, Any] = {
            "last_error": "task last error",
            "results": [
                {"error": {"message": "new result error"}},
            ],
        }

        self.assertEqual(
            self.scheduler._extract_failure_text_for_retry_collapse(
                task=task,
                runner_result=None,
            ),
            "task last error",
        )

    def test_failure_retry_collapse_uses_recent_results_as_fallback(self) -> None:
        task: Dict[str, Any] = {
            "results": [
                {"error": {"message": "old result error"}},
                {"error": {"message": "new result error"}},
            ],
        }

        self.assertEqual(
            self.scheduler._extract_failure_text_for_retry_collapse(
                task=task,
                runner_result=None,
            ),
            "new result error",
        )


if __name__ == "__main__":
    unittest.main()