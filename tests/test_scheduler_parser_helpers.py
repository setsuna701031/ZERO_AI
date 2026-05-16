from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class SchedulerParserHelpersTest(unittest.TestCase):
    def test_path_parser_helpers_extract_python_file_paths(self) -> None:
        from core.tasks.scheduler_core.path_parser_helpers import _extract_python_file_paths

        text = r"fix core/tasks/scheduler.py and workspace\shared\demo.py then core/tasks/scheduler.py"
        self.assertEqual(
            _extract_python_file_paths(text),
            ["core/tasks/scheduler.py", "workspace/shared/demo.py"],
        )

    def test_path_parser_helpers_shared_like_path(self) -> None:
        from core.tasks.scheduler_core.path_parser_helpers import _is_shared_like_path

        self.assertTrue(_is_shared_like_path("workspace/shared/demo.txt"))
        self.assertTrue(_is_shared_like_path(r"shared\demo.txt"))
        self.assertFalse(_is_shared_like_path("workspace/private/demo.txt"))

    def test_path_parser_helpers_strip_markdown_code_fences(self) -> None:
        from core.tasks.scheduler_core.path_parser_helpers import _strip_markdown_code_fences

        self.assertEqual(
            _strip_markdown_code_fences("```python\nprint('ok')\n```"),
            "print('ok')\n",
        )
        self.assertEqual(_strip_markdown_code_fences("plain text"), "plain text")

    def test_path_parser_helpers_extract_document_file_paths(self) -> None:
        from core.tasks.scheduler_core.path_parser_helpers import _extract_all_document_file_paths

        text = "read workspace/shared/input.txt and write workspace/shared/summary.md and input.txt"
        self.assertEqual(
            _extract_all_document_file_paths(text),
            ["workspace/shared/input.txt", "workspace/shared/summary.md", "input.txt"],
        )

    def test_path_parser_helpers_extract_document_arrow_paths(self) -> None:
        from core.tasks.scheduler_core.path_parser_helpers import _extract_document_arrow_paths

        self.assertEqual(
            _extract_document_arrow_paths("workspace/shared/input.txt -> workspace/shared/summary.md"),
            ("workspace/shared/input.txt", "workspace/shared/summary.md"),
        )
        self.assertIsNone(_extract_document_arrow_paths("workspace/shared/input.txt"))

    def test_path_parser_helpers_extract_document_source_path(self) -> None:
        from core.tasks.scheduler_core.path_parser_helpers import _extract_document_source_path

        paths = ["workspace/shared/input.txt", "workspace/shared/summary.md"]
        self.assertEqual(
            _extract_document_source_path("summarize workspace/shared/input.txt", paths),
            "workspace/shared/input.txt",
        )
        self.assertEqual(
            _extract_document_source_path("workspace/shared/input.txt -> workspace/shared/summary.md", paths),
            "workspace/shared/input.txt",
        )
        self.assertEqual(_extract_document_source_path("make summary", paths), "workspace/shared/input.txt")
        self.assertEqual(_extract_document_source_path("make summary", []), "")

    def test_path_parser_helpers_extract_document_output_path(self) -> None:
        from core.tasks.scheduler_core.path_parser_helpers import _extract_document_output_path

        paths = ["workspace/shared/input.txt", "workspace/shared/summary.md"]
        self.assertEqual(
            _extract_document_output_path("write summary to workspace/shared/summary.md", paths),
            "workspace/shared/summary.md",
        )
        self.assertEqual(
            _extract_document_output_path("workspace/shared/input.txt -> workspace/shared/summary.md", paths),
            "workspace/shared/summary.md",
        )
        self.assertEqual(_extract_document_output_path("make summary", paths), "workspace/shared/summary.md")
        self.assertEqual(_extract_document_output_path("make summary", ["workspace/shared/input.txt"]), "")

    def test_scheduler_document_path_wrappers_use_path_parser_helpers(self) -> None:
        from core.tasks.scheduler import Scheduler

        scheduler = Scheduler.__new__(Scheduler)
        paths = ["workspace/shared/input.txt", "workspace/shared/summary.md"]

        self.assertEqual(
            scheduler._extract_document_source_path("read workspace/shared/input.txt", paths),
            "workspace/shared/input.txt",
        )
        self.assertEqual(
            scheduler._extract_document_output_path("output to workspace/shared/summary.md", paths),
            "workspace/shared/summary.md",
        )

    def test_pure_helpers_safe_int_for_runtime_gate(self) -> None:
        from core.tasks.scheduler_core.pure_helpers import _safe_int_for_runtime_gate

        self.assertEqual(_safe_int_for_runtime_gate("7"), 7)
        self.assertEqual(_safe_int_for_runtime_gate(None, default=3), 3)
        self.assertEqual(_safe_int_for_runtime_gate("bad", default=5), 5)

    def test_pure_helpers_extract_task_id(self) -> None:
        from core.tasks.scheduler_core.pure_helpers import _extract_task_id

        self.assertEqual(_extract_task_id({"task_id": " task_1 "}), "task_1")
        self.assertEqual(_extract_task_id({"task_name": " task_name_1 "}), "task_name_1")
        self.assertEqual(_extract_task_id({"id": " id_1 "}), "id_1")
        self.assertEqual(_extract_task_id({}), "")

    def test_pure_helpers_strip_quotes(self) -> None:
        from core.tasks.scheduler_core.pure_helpers import _strip_quotes

        self.assertEqual(_strip_quotes('"hello"'), "hello")
        self.assertEqual(_strip_quotes("'hello'"), "hello")
        self.assertEqual(_strip_quotes("plain"), "plain")
        self.assertEqual(_strip_quotes(""), "")

    def test_pure_helpers_extract_file_path(self) -> None:
        from core.tasks.scheduler_core.path_parser_helpers import _extract_file_path

        self.assertEqual(
            _extract_file_path("please read workspace/shared/input.txt now"),
            "workspace/shared/input.txt",
        )
        self.assertEqual(
            _extract_file_path(r"check core\tasks\scheduler.py"),
            r"core\tasks\scheduler.py",
        )
        self.assertIsNone(_extract_file_path("no file path here"))

    def test_pure_helpers_extract_file_path_keeps_compatibility_wrapper(self) -> None:
        from core.tasks.scheduler_core.pure_helpers import _extract_file_path

        self.assertEqual(
            _extract_file_path("please read workspace/shared/input.txt now"),
            "workspace/shared/input.txt",
        )

    def test_scheduler_extract_file_path_wrapper_uses_path_parser_helper(self) -> None:
        from core.tasks.scheduler import Scheduler

        scheduler = Scheduler.__new__(Scheduler)

        self.assertEqual(
            scheduler._extract_file_path(r"check core\tasks\scheduler.py"),
            r"core\tasks\scheduler.py",
        )
        self.assertIsNone(scheduler._extract_file_path("no file path here"))

    def test_pure_helpers_canonicalize_steps_for_compare(self) -> None:
        from core.tasks.scheduler_core.pure_helpers import _canonicalize_steps_for_compare

        steps = [
            {"b": " two ", "a": 1},
            "run",
            {"type": "verify", "path": " out.txt "},
        ]

        self.assertEqual(
            _canonicalize_steps_for_compare(steps),
            [
                {"a": 1, "b": "two"},
                {"type": "run"},
                {"path": "out.txt", "type": "verify"},
            ],
        )
        self.assertEqual(_canonicalize_steps_for_compare("not-list"), [])

    def test_scheduler_normalize_verify_step_preserves_existing_behavior(self) -> None:
        from core.tasks.scheduler import Scheduler

        scheduler = Scheduler.__new__(Scheduler)

        result = scheduler._normalize_verify_step(
            {
                "type": "verify",
                "path": "workspace/shared/out.txt, contains=OK, exists=true",
            }
        )

        self.assertEqual(result["path"], "workspace/shared/out.txt")
        self.assertEqual(result["contains"], "OK")
        self.assertIs(result["exists"], True)
        self.assertIn("scope", result)

    def test_scheduler_extract_function_name_for_fix_preserves_existing_behavior(self) -> None:
        from core.tasks.scheduler import Scheduler

        scheduler = Scheduler.__new__(Scheduler)

        self.assertEqual(
            scheduler._extract_function_name_for_fix("Fix the add function so it returns correct result"),
            "add",
        )
        self.assertEqual(
            scheduler._extract_function_name_for_fix("repair multiply function"),
            "multiply",
        )
        self.assertEqual(
            scheduler._extract_function_name_for_fix("def divide(a, b): pass"),
            "divide",
        )

    def test_scheduler_try_plan_read_file_preserves_existing_behavior(self) -> None:
        from core.tasks.scheduler import Scheduler

        scheduler = Scheduler.__new__(Scheduler)

        self.assertEqual(
            scheduler._try_plan_read_file("read workspace/shared/input.txt"),
            {"type": "read_file", "path": "workspace/shared/input.txt"},
        )
        self.assertEqual(
            scheduler._try_plan_read_file("查看 workspace/shared/input.md"),
            {"type": "read_file", "path": "workspace/shared/input.md"},
        )
        self.assertIsNone(scheduler._try_plan_read_file("write workspace/shared/input.txt"))


if __name__ == "__main__":
    unittest.main()
