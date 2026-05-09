from __future__ import annotations

import ast
from pathlib import Path


SCHEDULER_PATH = Path("core/tasks/scheduler.py")
SCHEDULER_CORE_DIR = Path("core/tasks/scheduler_core")


KERNEL_FUNCTIONS = {
    "_persist_task_payload",
    "_hydrate_task_from_workspace",
    "_plan_goal",
    "_is_repairable_failure",
}

EXTRACTED_HELPER_FILES = {
    "trace_helpers.py",
    "step_path_helpers.py",
    "simple_runner_helpers.py",
    "simple_step_executor_helpers.py",
    "command_step_helpers.py",
    "llm_step_helpers.py",
    "dispatch_helpers.py",
    "queue_sync_helpers.py",
    "repo_state_helpers.py",
    "public_task_record_helpers.py",
}

FORBIDDEN_SCHEDULER_WRAPPERS = {
    "_get_trace_file_for_task",
    "_trace_summary",
    "_trace_step",
    "_trace_replan",
    "_resolve_step_path",
    "_resolve_read_path_with_fallback",
    "_needs_scheduler_path_resolution",
    "_resolve_guard_target_path",
    "_handle_simple_terminal_task",
    "_handle_simple_blocked_task",
    "_handle_simple_finished_task",
    "_handle_simple_invalid_step",
    "_handle_simple_step_exception",
    "_handle_simple_step_success",
    "_execute_dispatch_round",
    "_handle_dispatch_result",
    "_handle_missing_repo_task",
    "_handle_run_one_step_exception",
    "_finalize_dispatched_task",
    "_scheduler_dispatch_idle",
}


def _scheduler_tree() -> ast.Module:
    return ast.parse(SCHEDULER_PATH.read_text(encoding="utf-8", errors="ignore"))


def _top_level_class_function_names() -> set[str]:
    tree = _scheduler_tree()
    names: set[str] = set()

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Scheduler":
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.add(item.name)

    return names


def test_scheduler_keeps_intentional_runtime_kernel_functions() -> None:
    names = _top_level_class_function_names()

    missing = sorted(KERNEL_FUNCTIONS - names)

    assert missing == []


def test_scheduler_does_not_reintroduce_extracted_wrapper_ownership() -> None:
    names = _top_level_class_function_names()

    reintroduced = sorted(FORBIDDEN_SCHEDULER_WRAPPERS & names)

    assert reintroduced == []


def test_scheduler_core_extracted_helper_files_exist() -> None:
    missing = sorted(
        file_name
        for file_name in EXTRACTED_HELPER_FILES
        if not (SCHEDULER_CORE_DIR / file_name).exists()
    )

    assert missing == []


def test_scheduler_kernel_boundary_docs_exist() -> None:
    expected_docs = [
        Path("docs/runtime_kernel_boundary_map.md"),
        Path("docs/runtime_kernel_zones.md"),
    ]

    missing = [str(path) for path in expected_docs if not path.exists()]

    assert missing == []
