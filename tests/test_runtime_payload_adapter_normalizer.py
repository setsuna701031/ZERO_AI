from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimePayloadAdapterNormalizerTest(unittest.TestCase):
    def test_adapter_normalizes_basic_success_payload(self) -> None:
        from core.runtime.payload_normalizer import normalize_runtime_adapter_payload

        payload: Dict[str, Any] = {
            "ok": True,
            "message": "done",
            "final_answer": "final done",
            "runtime_mode": "execute",
        }

        normalized = normalize_runtime_adapter_payload(payload)

        self.assertIs(normalized["ok"], True)
        self.assertEqual(normalized["message"], "done")
        self.assertEqual(normalized["final_answer"], "final done")
        self.assertEqual(normalized["text"], "done")
        self.assertEqual(normalized["runtime_mode"], "execute")
        self.assertEqual(normalized["execution_trace"], [])
        self.assertIsNone(normalized["last_result"])

    def test_adapter_normalizes_error_payload(self) -> None:
        from core.runtime.payload_normalizer import normalize_runtime_adapter_payload

        payload: Dict[str, Any] = {
            "ok": False,
            "message": "failed",
            "error": {
                "type": "runtime_error",
                "message": "boom",
            },
            "runtime_mode": "execute",
        }

        normalized = normalize_runtime_adapter_payload(payload)

        self.assertIs(normalized["ok"], False)
        self.assertEqual(normalized["message"], "failed")
        self.assertEqual(normalized["final_answer"], "failed")
        self.assertEqual(normalized["error_text"], "boom")
        self.assertEqual(normalized["error_type"], "runtime_error")
        self.assertEqual(normalized["runtime_mode"], "execute")

    def test_adapter_preserves_last_result_dict(self) -> None:
        from core.runtime.payload_normalizer import normalize_runtime_adapter_payload

        payload: Dict[str, Any] = {
            "ok": False,
            "message": "failed",
            "last_result": {
                "ok": False,
                "message": "inner failure",
            },
        }

        normalized = normalize_runtime_adapter_payload(payload)

        self.assertIsInstance(normalized["last_result"], dict)
        self.assertEqual(normalized["last_result"]["message"], "inner failure")

    def test_adapter_filters_execution_trace_to_dict_items(self) -> None:
        from core.runtime.payload_normalizer import normalize_runtime_adapter_payload

        payload: Dict[str, Any] = {
            "ok": True,
            "message": "done",
            "execution_trace": [
                {"step_index": 0, "ok": True},
                "bad trace item",
                {"step_index": 1, "ok": True},
            ],
        }

        normalized = normalize_runtime_adapter_payload(payload)

        self.assertEqual(
            normalized["execution_trace"],
            [
                {"step_index": 0, "ok": True},
                {"step_index": 1, "ok": True},
            ],
        )

    def test_adapter_handles_malformed_payload(self) -> None:
        from core.runtime.payload_normalizer import normalize_runtime_adapter_payload

        normalized = normalize_runtime_adapter_payload(None)

        self.assertIsNone(normalized["ok"])
        self.assertEqual(normalized["message"], "")
        self.assertEqual(normalized["final_answer"], "")
        self.assertEqual(normalized["text"], "")
        self.assertEqual(normalized["error_text"], "")
        self.assertEqual(normalized["error_type"], "")
        self.assertEqual(normalized["runtime_mode"], "")
        self.assertIsNone(normalized["last_result"])
        self.assertEqual(normalized["execution_trace"], [])


if __name__ == "__main__":
    unittest.main()
