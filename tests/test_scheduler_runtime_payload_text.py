from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class SchedulerRuntimePayloadTextTest(unittest.TestCase):
    def setUp(self) -> None:
        from core.tasks.scheduler import Scheduler

        self.scheduler = Scheduler.__new__(Scheduler)

    def test_extract_text_preserves_current_legacy_first_behavior(self) -> None:
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

    def test_extract_text_message_used_when_legacy_text_missing(self) -> None:
        payload: Dict[str, Any] = {
            "message": "canonical message",
            "final_answer": "canonical final",
        }

        self.assertEqual(
            self.scheduler._extract_text_from_result_payload(payload),
            "canonical message",
        )

    def test_extract_text_legacy_fallback_still_works(self) -> None:
        payload: Dict[str, Any] = {
            "result": {
                "payload": {
                    "content": "legacy nested content",
                }
            }
        }

        self.assertEqual(
            self.scheduler._extract_text_from_result_payload(payload),
            "legacy nested content",
        )

    def test_extract_text_recursive_previous_result_still_works(self) -> None:
        payload: Dict[str, Any] = {
            "previous_result": {
                "result": {
                    "final_answer": "previous final",
                }
            }
        }

        self.assertEqual(
            self.scheduler._extract_text_from_result_payload(payload),
            "previous final",
        )

    def test_build_simple_final_answer_uses_last_result_text(self) -> None:
        results = [
            {
                "message": "first message",
                "final_answer": "first final",
            },
            {
                "result": {
                    "final_answer": "last final",
                }
            },
        ]

        self.assertEqual(self.scheduler._build_simple_final_answer(results), "last final")

    def test_extract_error_text_prefers_error_message(self) -> None:
        payload: Dict[str, Any] = {
            "message": "generic message",
            "final_answer": "generic final",
            "error": {
                "type": "runtime_error",
                "message": "canonical error message",
            },
        }

        self.assertEqual(
            self.scheduler._extract_error_text_deep(payload),
            "canonical error message",
        )

    def test_extract_error_text_legacy_fallback_still_works(self) -> None:
        payload: Dict[str, Any] = {
            "runner_result": {
                "result": {
                    "stderr": "legacy stderr",
                }
            }
        }

        self.assertEqual(
            self.scheduler._extract_error_text_deep(payload),
            "legacy stderr",
        )

    def test_extract_failure_text_prefers_runner_result_before_task(self) -> None:
        runner_result: Dict[str, Any] = {
            "error": {
                "message": "runner canonical error",
            }
        }
        task: Dict[str, Any] = {
            "last_error": "task last error",
            "results": [
                {
                    "message": "task result message",
                }
            ],
        }

        self.assertEqual(
            self.scheduler._extract_failure_text_for_retry_collapse(
                task=task,
                runner_result=runner_result,
            ),
            "runner canonical error",
        )

    def test_extract_failure_text_reads_recent_task_results(self) -> None:
        task: Dict[str, Any] = {
            "results": [
                {"message": "old result"},
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
