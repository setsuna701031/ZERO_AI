from __future__ import annotations

import shutil
from pathlib import Path

from core.runtime.runtime_transition_policy import RuntimeTransitionPolicy, RuntimeTransitionPolicyError
from core.runtime.task_runtime import TaskRuntime


REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_ROOT = REPO_ROOT / ".test_tmp" / "runtime_transition_policy_phase2"


def setup_function() -> None:
    if TEST_ROOT.exists():
        shutil.rmtree(TEST_ROOT)


def teardown_function() -> None:
    if TEST_ROOT.exists():
        shutil.rmtree(TEST_ROOT)


def _task(task_id: str = "transition_policy_phase2_probe") -> dict:
    task_dir = TEST_ROOT / "tasks" / task_id
    return {
        "task_id": task_id,
        "task_name": task_id,
        "goal": "runtime transition policy phase2 probe",
        "status": "queued",
        "task_dir": str(task_dir),
        "runtime_state_file": str(task_dir / "runtime_state.json"),
        "steps": [{"type": "final_answer", "content": "done"}],
        "current_step_index": 0,
    }


def test_review_required_to_running_requires_review_resolution_marker() -> None:
    decision = RuntimeTransitionPolicy().check_transition(
        current_state={"status": "review_required", "requires_review": True, "review_status": "pending_review"},
        updates={"status": "running"},
        owner="task_runtime",
        action="review_unblock",
    )

    assert decision.ok is False
    assert "requires resolved/approved review" in decision.reason
    assert decision.details["rule"] == "review_reopen_requires_resolution"


def test_review_required_to_running_allows_approved_review_resolution() -> None:
    decision = RuntimeTransitionPolicy().check_transition(
        current_state={"status": "review_required", "requires_review": True, "review_status": "pending_review"},
        updates={
            "status": "running",
            "review_resolved": True,
            "review_status": "approved",
        },
        owner="task_runtime",
        action="review_unblock_approved",
    )

    assert decision.ok is True


def test_waiting_review_to_running_allows_review_payload_resolution() -> None:
    decision = RuntimeTransitionPolicy().check_transition(
        current_state={
            "status": "waiting_review",
            "review_payload": {
                "resolution": {
                    "status": "approved",
                }
            },
        },
        updates={"status": "running"},
        owner="task_runtime",
        action="review_resume",
    )

    assert decision.ok is True


def test_blocked_to_running_requires_resolution_marker() -> None:
    decision = RuntimeTransitionPolicy().check_transition(
        current_state={"status": "blocked", "active_blocker_count": 1},
        updates={"status": "running"},
        owner="task_runtime",
        action="retry",
    )

    assert decision.ok is False
    assert "requires blocker resolution" in decision.reason
    assert decision.details["rule"] == "blocked_reopen_requires_resolution"


def test_blocked_to_running_allows_remove_blocker_action() -> None:
    decision = RuntimeTransitionPolicy().check_transition(
        current_state={"status": "blocked", "active_blocker_count": 1},
        updates={"status": "running"},
        owner="task_runtime",
        action="remove_blocker",
    )

    assert decision.ok is True


def test_retrying_requires_available_retry_budget() -> None:
    decision = RuntimeTransitionPolicy().check_transition(
        current_state={"status": "running", "retry_budget_remaining": 0},
        updates={"status": "retrying"},
        owner="task_runtime",
        action="retry_step",
    )

    assert decision.ok is False
    assert "retry transition requires available retry budget" in decision.reason
    assert decision.details["rule"] == "retry_requires_budget"


def test_retrying_allows_positive_retry_budget() -> None:
    decision = RuntimeTransitionPolicy().check_transition(
        current_state={"status": "running", "retry_budget_remaining": 1},
        updates={"status": "retrying"},
        owner="task_runtime",
        action="retry_step",
    )

    assert decision.ok is True


def test_task_runtime_apply_transition_enforces_review_resolution_policy() -> None:
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    task = _task("review_resolution_policy")
    state = runtime.ensure_runtime_state(task)
    state["status"] = "review_required"
    state["requires_review"] = True
    state["review_status"] = "pending_review"

    try:
        runtime.apply_runtime_transition(
            task,
            state,
            owner="task_runtime",
            action="review_unblock",
            updates={"status": "running"},
        )
    except RuntimeTransitionPolicyError as exc:
        assert "requires resolved/approved review" in str(exc)
    else:
        raise AssertionError("review reopen should require resolution marker")


def test_task_runtime_apply_transition_allows_approved_review_resolution() -> None:
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    task = _task("review_resolution_policy_allowed")
    state = runtime.ensure_runtime_state(task)
    state["status"] = "review_required"
    state["requires_review"] = True
    state["review_status"] = "pending_review"

    updated = runtime.apply_runtime_transition(
        task,
        state,
        owner="task_runtime",
        action="review_unblock_approved",
        updates={
            "status": "running",
            "review_resolved": True,
            "review_status": "approved",
        },
    )

    assert updated["status"] == "running"
    decision = updated["runtime_transition_policy"]["last_decision"]
    assert decision["ok"] is True
    assert decision["current_status"] == "review_required"
    assert decision["next_status"] == "running"
