from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimePayloadNormalizerTest(unittest.TestCase):
    def test_normalizer_preserves_legacy_text_priority(self) -> None:
        from core.runtime.payload_normalizer import normalize_runtime_payload

        payload: Dict[str, Any] = {
            "text": "legacy text",
            "content": "legacy content",
            "message": "canonical message",
            "final_answer": "canonical final",
        }

        normalized = normalize_runtime_payload(payload)

        self.assertEqual(normalized.text, "legacy text")
        self.assertEqual(normalized.message, "canonical message")
        self.assertEqual(normalized.final_answer, "canonical final")

    def test_normalizer_uses_content_before_canonical_message_for_text(self) -> None:
        from core.runtime.payload_normalizer import normalize_runtime_payload

        payload: Dict[str, Any] = {
            "content": "legacy content",
            "message": "canonical message",
            "final_answer": "canonical final",
        }

        normalized = normalize_runtime_payload(payload)

        self.assertEqual(normalized.text, "legacy content")
        self.assertEqual(normalized.message, "canonical message")
        self.assertEqual(normalized.final_answer, "canonical final")

    def test_normalizer_uses_message_when_legacy_text_missing(self) -> None:
        from core.runtime.payload_normalizer import normalize_runtime_payload

        payload: Dict[str, Any] = {
            "message": "canonical message",
            "final_answer": "canonical final",
        }

        normalized = normalize_runtime_payload(payload)

        self.assertEqual(normalized.text, "canonical message")
        self.assertEqual(normalized.message, "canonical message")
        self.assertEqual(normalized.final_answer, "canonical final")

    def test_normalizer_uses_final_answer_when_only_final_answer_exists(self) -> None:
        from core.runtime.payload_normalizer import normalize_runtime_payload

        payload: Dict[str, Any] = {
            "final_answer": "canonical final",
        }

        normalized = normalize_runtime_payload(payload)

        self.assertEqual(normalized.text, "canonical final")
        self.assertEqual(normalized.message, "canonical final")
        self.assertEqual(normalized.final_answer, "canonical final")

    def test_normalizer_reads_nested_result_payload(self) -> None:
        from core.runtime.payload_normalizer import normalize_runtime_payload

        payload: Dict[str, Any] = {
            "result": {
                "payload": {
                    "message": "nested message",
                    "final_answer": "nested final",
                }
            }
        }

        normalized = normalize_runtime_payload(payload)

        self.assertEqual(normalized.text, "nested message")
        self.assertEqual(normalized.message, "nested message")
        self.assertEqual(normalized.final_answer, "nested message")

    def test_normalizer_reads_previous_result_payload(self) -> None:
        from core.runtime.payload_normalizer import normalize_runtime_payload

        payload: Dict[str, Any] = {
            "previous_result": {
                "result": {
                    "payload": {
                        "final_answer": "previous final",
                    }
                }
            }
        }

        normalized = normalize_runtime_payload(payload)

        self.assertEqual(normalized.text, "previous final")

    def test_normalizer_extracts_canonical_error_message(self) -> None:
        from core.runtime.payload_normalizer import normalize_runtime_payload

        payload: Dict[str, Any] = {
            "message": "generic message",
            "error": {
                "type": "runtime_error",
                "message": "canonical error message",
            },
        }

        normalized = normalize_runtime_payload(payload)

        self.assertEqual(normalized.error_text, "canonical error message")
        self.assertEqual(normalized.error_type, "runtime_error")

    def test_normalizer_extracts_legacy_stderr_error(self) -> None:
        from core.runtime.payload_normalizer import normalize_runtime_payload

        payload: Dict[str, Any] = {
            "runner_result": {
                "result": {
                    "stderr": "legacy stderr",
                }
            }
        }

        normalized = normalize_runtime_payload(payload)

        self.assertEqual(normalized.error_text, "legacy stderr")

    def test_normalizer_preserves_ok_boolean(self) -> None:
        from core.runtime.payload_normalizer import normalize_runtime_payload

        success = normalize_runtime_payload({"ok": True, "message": "done"})
        failure = normalize_runtime_payload({"ok": False, "message": "failed"})
        unknown = normalize_runtime_payload({"message": "unknown"})

        self.assertIs(success.ok, True)
        self.assertIs(failure.ok, False)
        self.assertIsNone(unknown.ok)

    def test_normalizer_handles_malformed_payloads(self) -> None:
        from core.runtime.payload_normalizer import normalize_runtime_payload

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
                normalized = normalize_runtime_payload(value)
                self.assertIsInstance(normalized.text, str)
                self.assertIsInstance(normalized.message, str)
                self.assertIsInstance(normalized.final_answer, str)
                self.assertIsInstance(normalized.error_text, str)
                self.assertIsInstance(normalized.error_type, str)

    def test_normalizer_to_dict_contract(self) -> None:
        from core.runtime.payload_normalizer import normalize_runtime_payload

        normalized = normalize_runtime_payload(
            {
                "ok": False,
                "message": "failed",
                "error": {
                    "type": "runtime_error",
                    "message": "boom",
                },
            }
        )

        data = normalized.to_dict()

        self.assertEqual(data["ok"], False)
        self.assertEqual(data["text"], "failed")
        self.assertEqual(data["message"], "failed")
        self.assertEqual(data["final_answer"], "failed")
        self.assertEqual(data["error_text"], "boom")
        self.assertEqual(data["error_type"], "runtime_error")
        self.assertIn("raw", data)


if __name__ == "__main__":
    unittest.main()