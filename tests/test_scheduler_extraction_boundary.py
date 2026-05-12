from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class SchedulerExtractionBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        from core.tasks.scheduler import Scheduler

        self.scheduler = Scheduler.__new__(Scheduler)

    def test_pure_helper_wrappers_forward_behavior(self) -> None:
        self.assertEqual(self.scheduler._safe_int_for_runtime_gate("9"), 9)
        self.assertEqual(self.scheduler._safe_int_for_runtime_gate("bad", default=4), 4)

        self.assertEqual(self.scheduler._extract_task_id({"task_id": " task_x "}), "task_x")
        self.assertEqual(self.scheduler._extract_task_id({"task_name": " task_name_x "}), "task_name_x")
        self.assertEqual(self.scheduler._extract_task_id({"id": " id_x "}), "id_x")
        self.assertEqual(self.scheduler._extract_task_id({}), "")

        self.assertEqual(self.scheduler._strip_quotes('"abc"'), "abc")
        self.assertEqual(self.scheduler._strip_quotes("'abc'"), "abc")
        self.assertEqual(self.scheduler._strip_quotes("abc"), "abc")

        self.assertEqual(
            self.scheduler._extract_file_path("read workspace/shared/input.txt"),
            "workspace/shared/input.txt",
        )
        self.assertIsNone(self.scheduler._extract_file_path("no path"))

    def test_canonicalize_steps_wrapper_forwards_behavior(self) -> None:
        steps = [
            {"b": " two ", "a": 1},
            "run",
            {"type": "verify", "path": " out.txt "},
        ]

        self.assertEqual(
            self.scheduler._canonicalize_steps_for_compare(steps),
            [
                {"a": 1, "b": "two"},
                {"type": "run"},
                {"path": "out.txt", "type": "verify"},
            ],
        )
        self.assertEqual(self.scheduler._canonicalize_steps_for_compare(None), [])

    def test_path_parser_wrappers_forward_behavior(self) -> None:
        self.assertEqual(
            self.scheduler._extract_python_file_paths(
                r"fix core/tasks/scheduler.py and workspace\shared\demo.py"
            ),
            ["core/tasks/scheduler.py", "workspace/shared/demo.py"],
        )

        self.assertTrue(self.scheduler._is_shared_like_path("workspace/shared/demo.txt"))
        self.assertTrue(self.scheduler._is_shared_like_path(r"shared\demo.txt"))
        self.assertFalse(self.scheduler._is_shared_like_path("workspace/private/demo.txt"))

        self.assertEqual(
            self.scheduler._strip_markdown_code_fences("```python\nprint('ok')\n```"),
            "print('ok')\n",
        )
        self.assertEqual(self.scheduler._strip_markdown_code_fences("plain text"), "plain text")

        self.assertEqual(
            self.scheduler._extract_all_document_file_paths(
                "read workspace/shared/input.txt and write workspace/shared/summary.md"
            ),
            ["workspace/shared/input.txt", "workspace/shared/summary.md"],
        )

        self.assertEqual(
            self.scheduler._extract_document_arrow_paths(
                "workspace/shared/input.txt -> workspace/shared/summary.md"
            ),
            ("workspace/shared/input.txt", "workspace/shared/summary.md"),
        )
        self.assertIsNone(self.scheduler._extract_document_arrow_paths("workspace/shared/input.txt"))

    def test_extracted_helper_modules_are_importable(self) -> None:
        import core.tasks.scheduler_core.path_parser_helpers as path_parser_helpers
        import core.tasks.scheduler_core.pure_helpers as pure_helpers

        self.assertTrue(hasattr(pure_helpers, "_safe_int_for_runtime_gate"))
        self.assertTrue(hasattr(pure_helpers, "_canonicalize_steps_for_compare"))
        self.assertTrue(hasattr(path_parser_helpers, "_extract_python_file_paths"))
        self.assertTrue(hasattr(path_parser_helpers, "_extract_document_arrow_paths"))


if __name__ == "__main__":
    unittest.main()
