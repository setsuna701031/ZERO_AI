from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from core.runtime.runtime_loop_resume_policy import build_runtime_resume_decision
from core.runtime.runtime_progress_memory import build_runtime_progress_snapshot


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
        "record_only": True,
        "step_executed": False,
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "filesystem_mutation_performed": False,
        "task_completed": False,
        "autonomy_loop_started": False,
        "background_worker_started": False,
    }


def test_1393_completed_cursor_marks_complete():
    snapshot = build_runtime_progress_snapshot(
        [_commit("commit-1", step_index=0), _commit("commit-2", kind="noop", step_index=1)],
        total_steps=2,
    )
    decision = build_runtime_resume_decision(snapshot, snapshot["resume_cursor"])

    assert snapshot["resume_cursor"]["state"] == "COMPLETE"
    assert decision["action"] == "MARK_COMPLETE"
    assert decision["recovery_required"] is False
    assert decision["reason"] == "resume_cursor_complete"


def test_1394_normal_cursor_continues_execution():
    snapshot = build_runtime_progress_snapshot([_commit("commit-1", step_index=0)])
    decision = build_runtime_resume_decision(snapshot, snapshot["resume_cursor"])

    assert snapshot["resume_cursor"]["state"] == "CONTINUE"
    assert decision["action"] == "CONTINUE_EXECUTION"
    assert decision["next_step"]["next_step_index"] == 1


def test_1395_failure_with_recovery_enters_recovery():
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
    decision = build_runtime_resume_decision(snapshot, snapshot["resume_cursor"])

    assert snapshot["resume_cursor"]["state"] == "RECOVERY_REQUIRED"
    assert decision["action"] == "ENTER_RECOVERY"
    assert decision["recovery_required"] is True


def test_1396_blocked_cursor_blocks_resume():
    snapshot = build_runtime_progress_snapshot([_commit("commit-1", step_index=0)])
    cursor = deepcopy(snapshot["resume_cursor"])
    cursor["state"] = "BLOCKED"
    decision = build_runtime_resume_decision(snapshot, cursor)

    assert decision["action"] == "BLOCKED"
    assert decision["reason"] == "resume_cursor_blocked"


def test_1397_same_snapshot_always_gives_same_decision():
    snapshot = build_runtime_progress_snapshot([_commit("commit-1", step_index=0)])

    first = build_runtime_resume_decision(snapshot, snapshot["resume_cursor"])
    second = build_runtime_resume_decision(snapshot, snapshot["resume_cursor"])

    assert first == second
    assert first["decision_id"].startswith("runtime-loop-resume-decision::")


def test_1398_policy_does_not_mutate_progress():
    snapshot = build_runtime_progress_snapshot([_commit("commit-1", step_index=0)])
    before = deepcopy(snapshot)

    decision = build_runtime_resume_decision(snapshot, snapshot["resume_cursor"])

    assert snapshot == before
    assert decision["progress_memory_mutated"] is False
    assert decision["task_execution_performed"] is False
    assert decision["executor_run_performed"] is False
    assert decision["scheduler_mutation_performed"] is False


def test_1399_no_executor_import():
    policy_source = (ROOT / "core/runtime/runtime_loop_resume_policy.py").read_text()

    assert "import executor" not in policy_source
    assert "from core.runtime.executor" not in policy_source
    assert "executor_run_performed" in policy_source


def test_1400_no_scheduler_import():
    policy_source = (ROOT / "core/runtime/runtime_loop_resume_policy.py").read_text()

    assert "import scheduler" not in policy_source
    assert "from core.runtime.runtime_scheduler" not in policy_source
    assert "scheduler_mutation_performed" in policy_source
