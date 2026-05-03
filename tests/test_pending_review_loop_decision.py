from __future__ import annotations

from core.agent.loop_decision import observe_and_decide


def test_pending_review_returns_wait_without_terminal_or_replan() -> None:
    decision = observe_and_decide(
        {
            "ok": True,
            "status": "pending_review",
            "requires_review": True,
            "review_status": "pending_review",
            "review_id": "review-test-001",
            "agent_action": "await_review_decision",
        },
        task={"task_id": "task-review"},
        max_replans=1,
        replan_count=0,
    )

    assert decision["decision"] == "wait"
    assert decision["next_action"] == "wait_for_external_event"
    assert decision["terminal"] is False
    assert decision["should_continue"] is False
    assert decision["should_replan"] is False
    assert decision["should_fail"] is False
    assert "review-test-001" in decision["reason"]


def test_review_gate_beats_blocked_status() -> None:
    decision = observe_and_decide(
        {
            "ok": True,
            "status": "blocked",
            "requires_review": True,
            "review_status": "pending_review",
            "review_id": "review-blocked-but-waiting",
        },
        task={"task_id": "task-review"},
    )

    assert decision["decision"] == "wait"
    assert decision["next_action"] == "wait_for_external_event"
    assert decision["terminal"] is False


def test_normal_blocked_still_blocks_when_no_review_gate() -> None:
    decision = observe_and_decide(
        {"ok": False, "status": "blocked", "error": "guard blocked"},
        task={"task_id": "task-blocked"},
    )

    assert decision["decision"] == "blocked"
    assert decision["next_action"] == "finish"
    assert decision["terminal"] is True
