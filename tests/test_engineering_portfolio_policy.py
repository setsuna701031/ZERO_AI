from __future__ import annotations

from core.tasks.engineering_portfolio_policy import EngineeringPortfolioPolicy


def _goal(goal_id: str, status: str) -> dict:
    return {"goal_id": goal_id, "summary": goal_id, "status": status}


def test_policy_skips_completed_blocked_cancelled_and_paused_goals() -> None:
    policy = EngineeringPortfolioPolicy()

    for status, state, reason in (
        ("complete", "completed", "completed_goal"),
        ("completed", "completed", "completed_goal"),
        ("blocked", "blocked", "blocked_goal"),
        ("cancelled", "cancelled", "cancelled_goal"),
        ("paused", "paused", "paused_goal"),
    ):
        goal = _goal(status, status)
        assert policy.classify_goal_state(goal) == state
        assert policy.is_runnable_goal(goal) is False
        assert policy.explain_skip_reason(goal) == reason


def test_policy_allows_active_pending_and_in_progress_goals() -> None:
    policy = EngineeringPortfolioPolicy()

    for status in ("active", "pending", "in_progress"):
        goal = _goal(status, status)
        assert policy.classify_goal_state(goal) == "runnable"
        assert policy.is_runnable_goal(goal) is True
        assert policy.explain_skip_reason(goal) == ""


def test_policy_selects_first_runnable_goal_in_input_order() -> None:
    selection = EngineeringPortfolioPolicy().select_next_goal(
        [
            _goal("done", "completed"),
            _goal("paused", "paused"),
            _goal("ready_1", "pending"),
            _goal("ready_2", "active"),
        ]
    )

    assert selection["ok"] is True
    assert selection["decision"] == "selected"
    assert selection["selected_goal_id"] == "ready_1"
    assert [item["goal_id"] for item in selection["skipped_goals"]] == ["done", "paused"]
    assert selection["selection_summary"]["runnable_goal_ids"] == ["ready_1", "ready_2"]


def test_policy_returns_no_runnable_goal_summary() -> None:
    selection = EngineeringPortfolioPolicy().select_next_goal(
        [
            _goal("done", "complete"),
            _goal("blocked", "blocked"),
            _goal("cancelled", "cancelled"),
            _goal("paused", "paused"),
        ]
    )

    assert selection["ok"] is False
    assert selection["decision"] == "no_runnable_goal"
    assert selection["selected_goal_id"] == ""
    assert selection["selection_summary"]["runnable_goal_count"] == 0
    assert selection["selection_summary"]["skipped_goal_count"] == 4


def test_policy_build_selection_summary_counts_missing_and_skipped_goals() -> None:
    summary = EngineeringPortfolioPolicy().build_selection_summary(
        [
            {"goal_id": "missing_ref", "status": "missing"},
            _goal("ready", "in_progress"),
            _goal("blocked", "blocked"),
        ]
    )

    assert summary["selected_goal_id"] == "ready"
    assert summary["goal_count"] == 3
    assert summary["runnable_goal_count"] == 1
    assert summary["skipped_goal_count"] == 2
    assert [item["reason"] for item in summary["skipped_goals"]] == ["goal_not_found", "blocked_goal"]
    assert summary["deterministic_ref_order"] is True
    assert summary["priority_algorithm"] is False
