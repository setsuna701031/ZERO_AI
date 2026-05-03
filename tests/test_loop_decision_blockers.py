from __future__ import annotations

from core.agent.loop_decision import observe_and_decide


def test_active_blocker_returns_wait_even_when_status_is_blocked() -> None:
    decision = observe_and_decide(
        {
            "ok": True,
            "status": "blocked",
            "blockers": [
                {
                    "type": "review",
                    "id": "review-loop-001",
                    "status": "pending",
                    "reason": "human review required",
                }
            ],
        },
        task={"task_id": "task-blocker"},
    )

    assert decision["decision"] == "wait"
    assert decision["next_action"] == "wait_for_external_event"
    assert decision["terminal"] is False
    assert decision["should_continue"] is False
    assert decision["should_replan"] is False
    assert decision["should_fail"] is False
    assert "review-loop-001" in decision["reason"]


def test_resolved_blocker_does_not_wait() -> None:
    decision = observe_and_decide(
        {
            "ok": True,
            "status": "running",
            "current_step_index": 0,
            "steps_total": 2,
            "blockers": [
                {
                    "type": "review",
                    "id": "review-done",
                    "status": "applied",
                }
            ],
        },
        task={"task_id": "task-no-active-blocker"},
    )

    assert decision["decision"] == "continue"
    assert decision["next_action"] == "run_next_tick"


def test_legacy_review_fields_are_converted_to_blocker_wait() -> None:
    decision = observe_and_decide(
        {
            "ok": True,
            "status": "pending_review",
            "requires_review": True,
            "review_status": "pending_review",
            "review_id": "review-legacy-001",
        },
        task={"task_id": "task-legacy-review"},
    )

    assert decision["decision"] == "wait"
    assert decision["next_action"] == "wait_for_external_event"
    assert "review-legacy-001" in decision["reason"]


def test_normal_blocked_still_blocks_without_active_blocker() -> None:
    decision = observe_and_decide(
        {"ok": False, "status": "blocked", "error": "guard blocked"},
        task={"task_id": "task-blocked"},
    )

    assert decision["decision"] == "blocked"
    assert decision["next_action"] == "finish"
    assert decision["terminal"] is True
