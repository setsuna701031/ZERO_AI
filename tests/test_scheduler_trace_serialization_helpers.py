from __future__ import annotations

from pathlib import Path

from core.tasks.scheduler_core.trace_serialization_helpers import (
    extract_execution_trace_from_payload,
    load_trace_for_task,
    promote_execution_trace_in_executed_results,
    save_trace_for_task,
)
from core.tools.execution_trace import ExecutionTrace


class FakeScheduler:
    def __init__(self, root: Path) -> None:
        self.tasks_root = str(root)
        self.trace_runtime = None

    def _extract_task_id(self, task):
        return str(task.get("task_id") or "")


def test_extract_execution_trace_from_payload_handles_empty_trace() -> None:
    assert extract_execution_trace_from_payload({}) == []
    assert extract_execution_trace_from_payload({"execution_trace": []}) == []
    assert extract_execution_trace_from_payload({"result": {"execution_trace": []}}) == []


def test_promote_execution_trace_in_executed_results_promotes_normal_trace_list() -> None:
    results = [
        {
            "ok": True,
            "result": {
                "execution_trace": [
                    {"event_type": "step", "ok": True},
                    "ignored",
                ]
            },
        }
    ]

    promoted = promote_execution_trace_in_executed_results(results)

    assert promoted[0]["execution_trace"] == [{"event_type": "step", "ok": True}]
    assert promoted[0]["result"]["execution_trace"] == [
        {"event_type": "step", "ok": True},
        "ignored",
    ]
    assert "execution_trace" not in results[0]


def test_load_trace_for_task_missing_file_returns_empty_trace(tmp_path: Path) -> None:
    scheduler = FakeScheduler(tmp_path)
    task = {"task_id": "missing_trace"}

    trace = load_trace_for_task(scheduler, task)

    assert isinstance(trace, ExecutionTrace)
    assert trace.to_dict()["events"] == []
    assert task["trace_file"].endswith("trace.json")


def test_load_trace_for_task_malformed_json_returns_empty_trace(tmp_path: Path) -> None:
    scheduler = FakeScheduler(tmp_path)
    task_dir = tmp_path / "bad_trace"
    task_dir.mkdir()
    trace_file = task_dir / "trace.json"
    trace_file.write_text("{bad json", encoding="utf-8")
    task = {"task_id": "bad_trace", "task_dir": str(task_dir), "trace_file": str(trace_file)}

    trace = load_trace_for_task(scheduler, task)

    assert isinstance(trace, ExecutionTrace)
    assert trace.to_dict()["events"] == []
    assert task["trace_file"] == str(trace_file)


def test_save_trace_for_task_preserves_trace_format(tmp_path: Path) -> None:
    scheduler = FakeScheduler(tmp_path)
    task = {"task_id": "save_trace"}
    trace = ExecutionTrace()
    trace.add_status_event(task_id="save_trace", status="queued")

    saved = save_trace_for_task(scheduler, task, trace)

    assert saved is not None
    payload = Path(saved).read_text(encoding="utf-8")
    assert '"trace_version": 1' in payload
    assert '"event_count": 1' in payload
