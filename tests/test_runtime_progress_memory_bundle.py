from __future__ import annotations

from pathlib import Path

from core.runtime.runtime_progress_memory import (
    build_runtime_progress_memory_audit_projection,
    build_runtime_progress_snapshot,
)
from core.runtime.runtime_resume_cursor import build_runtime_resume_cursor


ROOT = Path(__file__).resolve().parents[1]


def _commit(
    commit_id: str,
    *,
    status: str = "committed",
    kind: str = "read_result",
    step_index: int = 0,
    next_step_index: int | None = None,
    recovery_required: bool = False,
    failure_reason: str = "none",
):
    if next_step_index is None:
        next_step_index = step_index + 1
    return {
        "schema": "zero.runtime.step_result_commit.v1",
        "step_result_commit_id": commit_id,
        "runtime_session_id": "limited-runtime-session::birth-1209",
        "step_bridge_id": f"runtime-step-bridge::{commit_id}",
        "step_request_id": f"runtime-step-request::{commit_id}",
        "work_cycle_id": "runtime-work-cycle::cycle-1361",
        "execution_tick_id": "runtime-execution-tick::tick-1345",
        "result_status": status,
        "result_kind": kind,
        "result_summary": f"caller supplied {kind} evidence",
        "failure_reason": failure_reason,
        "progress_delta": {
            "step_id": f"step::{step_index}",
            "step_index": step_index,
            "next_step_index": next_step_index,
        },
        "recovery_required": recovery_required,
        "task_completion_candidate": False,
        "record_only": True,
        "result_evidence_only": True,
        "step_executed": False,
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "filesystem_mutation_performed": False,
        "task_completed": False,
        "task_marked_complete": False,
        "autonomy_loop_started": False,
        "background_worker_started": False,
    }


def test_1385_completed_commits_advance_progress():
    snapshot = build_runtime_progress_snapshot(
        [_commit("commit-1", step_index=0), _commit("commit-2", step_index=1)]
    )

    assert snapshot["runtime_id"] == "limited-runtime-session::birth-1209"
    assert len(snapshot["completed_steps"]) == 2
    assert snapshot["last_committed_step"]["step_result_commit_id"] == "commit-2"
    assert snapshot["resume_cursor"]["next_step_index"] == 2
    assert snapshot["resume_cursor"]["state"] == "CONTINUE"


def test_1386_failed_commits_mark_recovery_required():
    snapshot = build_runtime_progress_snapshot(
        [
            _commit("commit-1", step_index=0),
            _commit(
                "commit-2",
                status="failed",
                kind="failure_result",
                step_index=1,
                failure_reason="caller_reported_failure",
            ),
        ]
    )

    assert snapshot["recovery_required"] is True
    assert len(snapshot["failed_steps"]) == 1
    assert snapshot["failed_steps"][0]["failure_reason"] == "caller_reported_failure"
    assert snapshot["resume_cursor"]["state"] == "RECOVERY_REQUIRED"


def test_1387_replay_same_commits_same_snapshot():
    commits = [_commit("commit-1", step_index=0), _commit("commit-2", step_index=1)]

    first = build_runtime_progress_snapshot(commits)
    second = build_runtime_progress_snapshot(commits)

    assert first == second


def test_1388_cursor_deterministic():
    snapshot = build_runtime_progress_snapshot([_commit("commit-1", step_index=0)])

    first = build_runtime_resume_cursor(snapshot)
    second = build_runtime_resume_cursor(snapshot)

    assert first == second
    assert first["state"] == "CONTINUE"
    assert first["cursor_id"].startswith("runtime-resume-cursor::")


def test_1389_cursor_survives_noop_commits():
    snapshot = build_runtime_progress_snapshot(
        [
            _commit("commit-1", step_index=0, next_step_index=1),
            _commit(
                "commit-noop",
                kind="noop",
                step_index=1,
                next_step_index=1,
            ),
        ]
    )

    assert len(snapshot["completed_steps"]) == 1
    assert len(snapshot["skipped_steps"]) == 1
    assert snapshot["last_committed_step"]["step_result_commit_id"] == "commit-noop"
    assert snapshot["resume_cursor"]["next_step_index"] == 1
    assert snapshot["resume_cursor"]["state"] == "CONTINUE"


def test_1390_executor_import_forbidden():
    progress_source = (ROOT / "core/runtime/runtime_progress_memory.py").read_text()
    cursor_source = (ROOT / "core/runtime/runtime_resume_cursor.py").read_text()

    assert "import executor" not in progress_source
    assert "from core.runtime.executor" not in progress_source
    assert "import executor" not in cursor_source
    assert "from core.runtime.executor" not in cursor_source


def test_1391_scheduler_mutation_forbidden():
    progress_source = (ROOT / "core/runtime/runtime_progress_memory.py").read_text()
    cursor_source = (ROOT / "core/runtime/runtime_resume_cursor.py").read_text()
    snapshot = build_runtime_progress_snapshot([_commit("commit-1")])

    assert "import scheduler" not in progress_source
    assert "from core.runtime.runtime_scheduler" not in progress_source
    assert "import scheduler" not in cursor_source
    assert "from core.runtime.runtime_scheduler" not in cursor_source
    assert snapshot["scheduler_mutation_performed"] is False
    assert snapshot["resume_cursor"]["scheduler_mutation_performed"] is False


def test_1392_audit_projection_deterministic_and_complete_state():
    snapshot = build_runtime_progress_snapshot(
        [_commit("commit-1", step_index=0), _commit("commit-noop", kind="noop", step_index=1)],
        total_steps=2,
    )
    first = build_runtime_progress_memory_audit_projection(snapshot)
    second = build_runtime_progress_memory_audit_projection(snapshot)

    assert first == second
    assert first["projection_only"] is True
    assert first["resume_cursor"]["state"] == "COMPLETE"
    assert first["task_execution_performed"] is False
    assert first["executor_run_performed"] is False
