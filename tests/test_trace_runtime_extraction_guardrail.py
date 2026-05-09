from __future__ import annotations

from pathlib import Path

from core.runtime.trace_runtime import TraceRuntime


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_trace_runtime_module_exists_before_scheduler_extraction() -> None:
    assert (REPO_ROOT / "core/runtime/trace_runtime.py").exists()


def test_scheduler_still_owns_trace_methods_until_explicit_extraction() -> None:
    content = (REPO_ROOT / "core/tasks/scheduler.py").read_text(
        encoding="utf-8",
        errors="ignore",
    )

    required_methods = [
        "def _get_trace_file_for_task",
        "def _load_trace_for_task",
        "def _save_trace_for_task",
        "def _trace_summary",
        "def _trace_status",
        "def _trace_step",
        "def _trace_replan",
    ]

    for method in required_methods:
        assert method in content, method


def test_trace_runtime_can_be_constructed_without_scheduler() -> None:
    runtime = TraceRuntime(repo_root=REPO_ROOT)

    path = runtime.trace_file_for_task({"task_id": "guardrail_demo"})

    assert path.name == "guardrail_demo.json"
    assert "runtime_traces" in str(path)