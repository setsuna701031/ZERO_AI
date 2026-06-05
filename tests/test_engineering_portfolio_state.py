from __future__ import annotations

from core.tasks.engineering_portfolio_state import EngineeringPortfolioState


def _portfolio(*goal_ids: str, lifecycle_state: str = "") -> dict:
    portfolio = {"portfolio_id": "portfolio_1", "name": "State portfolio", "goal_ids": list(goal_ids)}
    if lifecycle_state:
        portfolio["lifecycle_state"] = lifecycle_state
    return portfolio


def test_active_portfolio_with_runnable_goal_is_active() -> None:
    state = EngineeringPortfolioState().evaluate_portfolio_state(
        _portfolio("goal_1"),
        [{"goal_id": "goal_1", "summary": "Runnable", "status": "pending"}],
    )

    assert state == "active"


def test_all_completed_goals_complete_portfolio() -> None:
    state = EngineeringPortfolioState().evaluate_portfolio_state(
        _portfolio("goal_1", "goal_2"),
        [
            {"goal_id": "goal_1", "summary": "Done", "status": "complete"},
            {"goal_id": "goal_2", "summary": "Done too", "status": "completed"},
        ],
    )

    assert state == "completed"


def test_all_blocked_goals_block_portfolio() -> None:
    state = EngineeringPortfolioState().evaluate_portfolio_state(
        _portfolio("goal_1", "goal_2"),
        [
            {"goal_id": "goal_1", "summary": "Blocked", "status": "blocked"},
            {"goal_id": "goal_2", "summary": "Blocked too", "status": "blocked"},
        ],
    )

    assert state == "blocked"


def test_manual_paused_and_archived_override_goal_state() -> None:
    portfolio_state = EngineeringPortfolioState()
    goals = [{"goal_id": "goal_1", "summary": "Runnable", "status": "pending"}]

    assert portfolio_state.evaluate_portfolio_state(_portfolio("goal_1", lifecycle_state="paused"), goals) == "paused"
    assert portfolio_state.evaluate_portfolio_state(_portfolio("goal_1", lifecycle_state="archived"), goals) == "archived"


def test_progress_counts_and_completion_ratio() -> None:
    progress = EngineeringPortfolioState().calculate_progress(
        _portfolio("done", "blocked", "active", "missing"),
        [
            {"goal_id": "done", "summary": "Done", "status": "complete"},
            {"goal_id": "blocked", "summary": "Blocked", "status": "blocked"},
            {"goal_id": "active", "summary": "Active", "status": "pending"},
        ],
    )

    assert progress == {
        "goal_count": 4,
        "completed_goal_count": 1,
        "blocked_goal_count": 1,
        "active_goal_count": 1,
        "completion_ratio": 0.25,
    }
