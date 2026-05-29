from __future__ import annotations

from core.runtime.runtime_session_resume import (
    RESUMABLE_TASK_STATUSES,
    RuntimeSessionResume,
    is_resumable_task_status,
    is_terminal_task_status,
    stable_resume_fingerprint,
)


def test_runtime_session_resume_contract_seal(tmp_path):
    runtime = RuntimeSessionResume(workspace_root=tmp_path, storage_path=tmp_path / "resume.json")
    plan = runtime.build_resume_plan(tasks=[{"task_id": "task-a", "status": "running"}], session_id="seal-session")

    assert plan["ok"] is True
    assert plan["action"] == "resume_tasks"
    assert plan["resume_policy"]["scheduler_should_requeue_runnable"] is True
    assert plan["resume_policy"]["scheduler_should_keep_blocked_waiting"] is True


def test_runtime_session_resume_status_boundary_seal():
    assert is_resumable_task_status("running") is True
    assert is_resumable_task_status("review_required") is True
    assert is_terminal_task_status("finished") is True
    assert is_terminal_task_status("failed") is True
    assert "running" in RESUMABLE_TASK_STATUSES
    assert "review_required" in RESUMABLE_TASK_STATUSES


def test_runtime_session_resume_fingerprint_is_stable():
    left = stable_resume_fingerprint({"b": 2, "a": 1})
    right = stable_resume_fingerprint({"a": 1, "b": 2})
    assert left == right
    assert len(left) == 64
