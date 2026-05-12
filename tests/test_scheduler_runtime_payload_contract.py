from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class SchedulerRuntimePayloadContractTest(unittest.TestCase):
    def setUp(self) -> None:
        from core.tasks.scheduler import Scheduler

        self.scheduler = Scheduler.__new__(Scheduler)

    def test_payload_text_contract_legacy_text_has_priority(self) -> None:
        payload: Dict[str, Any] = {
            "text": "legacy text",
            "content": "legacy content",
            "message": "canonical message",
            "final_answer": "canonical final answer",
        }

        self.assertEqual(
            self.scheduler._extract_text_from_result_payload(payload),
            "legacy text",
        )

    def test_payload_text_contract_legacy_content_fallback(self) -> None:
        payload: Dict[str, Any] = {
            "content": "legacy content",
            "message": "canonical message",
            "final_answer": "canonical final answer",
        }

        self.assertEqual(
            self.scheduler._extract_text_from_result_payload(payload),
            "legacy content",
        )

    def test_payload_text_contract_canonical_message_fallback(self) -> None:
        payload: Dict[str, Any] = {
            "message": "canonical message",
            "final_answer": "canonical final answer",
        }

        self.assertEqual(
            self.scheduler._extract_text_from_result_payload(payload),
            "canonical message",
        )

    def test_payload_text_contract_canonical_final_answer_fallback(self) -> None:
        payload: Dict[str, Any] = {
            "final_answer": "canonical final answer",
        }

        self.assertEqual(
            self.scheduler._extract_text_from_result_payload(payload),
            "canonical final answer",
        )

    def test_payload_text_contract_nested_result_payload(self) -> None:
        payload: Dict[str, Any] = {
            "result": {
                "payload": {
                    "message": "nested canonical message",
                    "final_answer": "nested final answer",
                }
            }
        }

        self.assertEqual(
            self.scheduler._extract_text_from_result_payload(payload),
            "nested canonical message",
        )

    def test_payload_text_contract_previous_result_payload(self) -> None:
        payload: Dict[str, Any] = {
            "previous_result": {
                "result": {
                    "payload": {
                        "final_answer": "previous nested final answer",
                    }
                }
            }
        }

        self.assertEqual(
            self.scheduler._extract_text_from_result_payload(payload),
            "previous nested final answer",
        )

    def test_payload_text_contract_malformed_payload_returns_string(self) -> None:
        malformed_values: List[Any] = [
            None,
            "",
            [],
            {},
            {"result": None},
            {"payload": []},
            {"message": None},
            {"final_answer": None},
        ]

        for value in malformed_values:
            with self.subTest(value=value):
                extracted = self.scheduler._extract_text_from_result_payload(value)
                self.assertIsInstance(extracted, str)

    def test_error_payload_contract_canonical_error_message_has_priority(self) -> None:
        payload: Dict[str, Any] = {
            "message": "generic message",
            "final_answer": "generic final",
            "stderr": "legacy stderr",
            "error": {
                "type": "runtime_error",
                "message": "canonical error message",
            },
        }

        self.assertEqual(
            self.scheduler._extract_error_text_deep(payload),
            "canonical error message",
        )

    def test_error_payload_contract_legacy_stderr_fallback(self) -> None:
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

    def test_failure_payload_contract_runner_result_before_task_state(self) -> None:
        runner_result: Dict[str, Any] = {
            "error": {
                "message": "runner error message",
            }
        }
        task: Dict[str, Any] = {
            "last_error": "task last error",
            "results": [
                {"message": "task result message"},
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

    def test_failure_payload_contract_last_error_before_recent_task_result(self) -> None:
        task: Dict[str, Any] = {
            "last_error": "task last error",
            "results": [
                {"message": "old result message"},
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

    def test_final_answer_contract_uses_last_extractable_result(self) -> None:
        results: List[Dict[str, Any]] = [
            {"message": "first message"},
            {"result": {"payload": {"message": "middle message"}}},
            {"previous_result": {"result": {"final_answer": "last final answer"}}},
        ]

        self.assertEqual(
            self.scheduler._build_simple_final_answer(results),
            "last final answer",
        )


if __name__ == "__main__":
    unittest.main()