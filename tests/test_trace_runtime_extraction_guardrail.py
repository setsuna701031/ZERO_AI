from __future__ import annotations

from pathlib import Path

from core.runtime.trace_runtime import TraceRuntime


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_trace_runtime_module_exists_before_scheduler_extraction() -> None:
    assert (REPO_ROOT / "core/runtime/trace_runtime.py").exists()


def test_scheduler_trace_ownership_is_extracted_to_helper_layer() -> None:
    content = (REPO_ROOT / "core/tasks/scheduler.py").read_text(
        encoding="utf-8",
        errors="ignore",
    )

    forbidden_methods = [
        "def _get_trace_file_for_task",
        "def _trace_summary",
        "def _trace_step",
        "def _trace_replan",
    ]

    for method in forbidden_methods:
        assert method not in content, method

    required_methods = [
        "def _load_trace_for_task",
        "def _save_trace_for_task",
        "def _trace_status",
    ]

    for method in required_methods:
        assert method in content, method


def test_trace_runtime_can_be_constructed_without_scheduler() -> None:
    runtime = TraceRuntime(repo_root=REPO_ROOT)

    path = runtime.trace_file_for_task({"task_id": "guardrail_demo"})

    assert path.name == "guardrail_demo.json"
    assert "runtime_traces" in str(path)