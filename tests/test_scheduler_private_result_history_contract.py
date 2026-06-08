from __future__ import annotations

import json
from pathlib import Path

from core.tasks.scheduler import Scheduler
from core.tasks.task_repository import TaskRepository


def test_public_snapshot_compaction_does_not_truncate_private_result_history(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    scheduler = Scheduler(
        task_repo=TaskRepository(db_path=str(workspace / "tasks.json")),
        workspace_dir=str(workspace),
    )
    long_text = "project_summary.txt implementation_plan.txt acceptance_checklist.txt " + ("x" * 1200)
    task = {
        "task_id": "private-result-history",
        "task_name": "private-result-history",
        "status": "queued",
        "steps": [{"type": "llm"}, {"type": "write_file", "use_previous_text": True}],
        "current_step_index": 1,
        "results": [
            {
                "step_index": 0,
                "step": {"type": "llm"},
                "result": {"ok": True, "type": "llm", "text": long_text, "message": long_text},
            }
        ],
    }

    scheduler._persist_task_payload(task["task_id"], task)

    runtime_state = json.loads(
        (workspace / "tasks" / task["task_id"] / "runtime_state.json").read_text(encoding="utf-8")
    )
    public_result = json.loads(
        (workspace / "tasks" / task["task_id"] / "result.json").read_text(encoding="utf-8")
    )
    private_text = scheduler._extract_text_from_result_payload(runtime_state["last_step_result"])
    public_message = public_result["results"][-1]["message"]

    assert private_text == long_text
    assert len(private_text) > 500
    assert len(public_message) == 500
