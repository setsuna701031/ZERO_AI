from __future__ import annotations

from core.runtime.runtime_session_resume import RuntimeSessionResume
from core.runtime.runtime_task_continuation import build_persistent_task_resume_and_continuation, build_task_continuation_plan


def test_runtime_session_resume_persists_and_loads_resumable_tasks(tmp_path):
    storage_path = tmp_path / "resume.json"
    tasks = [
        {"task_id": "task_running", "status": "running", "current_step_index": 2},
        {"task_id": "task_blocked", "status": "blocked", "current_step_index": 1},
        {"task_id": "task_done", "status": "finished", "current_step_index": 9},
    ]

    runtime = RuntimeSessionResume(workspace_root=tmp_path, storage_path=storage_path)
    record = runtime.create_session_record(session_id="session-a", tasks=tasks)

    assert record.status == "resumable"
    assert [item.task_id for item in record.snapshots] == ["task_running", "task_blocked"]
    assert record.resume_plan["runnable_task_ids"] == ["task_running"]
    assert record.resume_plan["blocked_task_ids"] == ["task_blocked"]

    reloaded = RuntimeSessionResume(workspace_root=tmp_path, storage_path=storage_path)
    loaded = reloaded.get_record("session-a")

    assert loaded is not None
    assert loaded.resume_plan["task_ids"] == ["task_running", "task_blocked"]
    assert loaded.resume_plan["status_counts"] == {"blocked": 1, "running": 1}


def test_runtime_session_resume_mark_resumed_and_finalize(tmp_path):
    runtime = RuntimeSessionResume(workspace_root=tmp_path, storage_path=tmp_path / "resume.json")
    runtime.create_session_record(session_id="session-b", tasks=[{"task_id": "task_retry", "status": "retry"}])

    resumed = runtime.mark_resumed("session-b", metadata={"source": "test"})
    assert resumed.status == "resumed"
    assert resumed.metadata["source"] == "test"

    finalized = runtime.finalize_session("session-b", final_result={"ok": True})
    assert finalized.status == "finalized"
    assert finalized.metadata["final_result"] == {"ok": True}


def test_runtime_task_continuation_classifies_requeue_wait_skip():
    plan = build_task_continuation_plan([
        {"task_id": "task_queued", "status": "queued"},
        {"task_id": "task_review", "status": "review_required"},
        {"task_id": "task_finished", "status": "finished"},
    ])

    assert plan["ok"] is True
    assert plan["requeue_task_ids"] == ["task_queued"]
    assert plan["waiting_task_ids"] == ["task_review"]
    assert plan["skipped_task_ids"] == ["task_finished"]


def test_persistent_task_resume_and_continuation_combines_plans(tmp_path):
    result = build_persistent_task_resume_and_continuation(
        [
            {"task_id": "task_running", "status": "running"},
            {"task_id": "task_failed", "status": "failed"},
        ],
        workspace_root=str(tmp_path),
        storage_path=str(tmp_path / "resume.json"),
        session_id="session-c",
    )

    assert result["ok"] is True
    assert result["resume_plan"]["task_ids"] == ["task_running"]
    assert result["continuation_plan"]["requeue_task_ids"] == ["task_running"]
    assert result["continuation_plan"]["skipped_task_ids"] == ["task_failed"]
