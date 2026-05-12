from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimePayloadFailureNormalizerTest(unittest.TestCase):
    def test_failure_text_runner_result_has_priority(self) -> None:
        from core.runtime.payload_normalizer import extract_runtime_failure_text

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
            extract_runtime_failure_text(task=task, runner_result=runner_result),
            "runner error message",
        )

    def test_failure_text_task_last_error_before_results(self) -> None:
        from core.runtime.payload_normalizer import extract_runtime_failure_text

        task: Dict[str, Any] = {
            "last_error": "task last error",
            "results": [
                {"error": {"message": "new result error"}},
            ],
        }

        self.assertEqual(
            extract_runtime_failure_text(task=task, runner_result=None),
            "task last error",
        )

    def test_failure_text_task_failure_message_before_results(self) -> None:
        from core.runtime.payload_normalizer import extract_runtime_failure_text

        task: Dict[str, Any] = {
            "failure_message": "task failure message",
            "results": [
                {"error": {"message": "new result error"}},
            ],
        }

        self.assertEqual(
            extract_runtime_failure_text(task=task, runner_result=None),
            "task failure message",
        )

    def test_failure_text_uses_recent_results_as_fallback(self) -> None:
        from core.runtime.payload_normalizer import extract_runtime_failure_text

        task: Dict[str, Any] = {
            "results": [
                {"error": {"message": "old result error"}},
                {"error": {"message": "new result error"}},
            ],
        }

        self.assertEqual(
            extract_runtime_failure_text(task=task, runner_result=None),
            "new result error",
        )

    def test_failure_text_uses_step_results_as_fallback(self) -> None:
        from core.runtime.payload_normalizer import extract_runtime_failure_text

        task: Dict[str, Any] = {
            "step_results": [
                {"message": "old step message"},
                {"error": {"message": "new step error"}},
            ],
        }

        self.assertEqual(
            extract_runtime_failure_text(task=task, runner_result=None),
            "new step error",
        )

    def test_failure_text_uses_execution_log_as_fallback(self) -> None:
        from core.runtime.payload_normalizer import extract_runtime_failure_text

        task: Dict[str, Any] = {
            "execution_log": [
                {"message": "old log message"},
                {"stderr": "new log stderr"},
            ],
        }

        self.assertEqual(
            extract_runtime_failure_text(task=task, runner_result=None),
            "new log stderr",
        )

    def test_failure_text_handles_malformed_payloads(self) -> None:
        from core.runtime.payload_normalizer import extract_runtime_failure_text

        self.assertEqual(extract_runtime_failure_text(task=None, runner_result=None), "")
        self.assertEqual(extract_runtime_failure_text(task=[], runner_result={}), "")
        self.assertEqual(extract_runtime_failure_text(task={}, runner_result=[]), "")


if __name__ == "__main__":
    unittest.main()
