from __future__ import annotations

from pathlib import Path

from core.evidence import EvidenceRecord, EvidenceValidator
from core.goals.goal_completion_authority import GoalCompletionAuthority
from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.engineering_portfolio_coordinator import EngineeringPortfolioCoordinator
from core.tasks.engineering_portfolio_cycle import EngineeringPortfolioCycle
from core.tasks.engineering_portfolio_repository import EngineeringPortfolioRepository


def _attestation(goal_id: str):
    evidence = EvidenceValidator().validate(EvidenceRecord("seed-e", goal_id, None, "test", "ok", "now"))
    return GoalCompletionAuthority().complete_goal(goal_id=goal_id, evidence_refs=[evidence], all_subgoals_completed=True)


class FakeGoalLoop:
    def __init__(self, outcomes: dict[str, str] | None = None) -> None:
        self.outcomes = outcomes or {}
        self.calls: list[str] = []

    def run_until_terminal(self, goal_id: str, max_cycles: int = 3) -> dict:
        self.calls.append(goal_id)
        stop_reason = self.outcomes.get(goal_id, "complete")
        evidence = EvidenceValidator().validate(EvidenceRecord("e1", goal_id, None, "test", "ok", "now"))
        attestation = GoalCompletionAuthority().complete_goal(
            goal_id=goal_id,
            evidence_refs=[evidence],
            all_subgoals_completed=True,
        )
        return {
            "ok": stop_reason == "complete",
            "goal_id": goal_id,
            "terminal": stop_reason in {"complete", "blocked"},
            "stop_reason": stop_reason,
            "max_cycles": max_cycles,
            "cycle_count": 1,
            "cycles": [
                {
                    "cycle_index": 0,
                    "goal_id": goal_id,
                    "runtime_state": stop_reason,
                    "adaptive_decision": stop_reason,
                    "adaptive_reason": f"{stop_reason}_reason",
                    "goal_completion_attestation": attestation if stop_reason == "complete" else None,
                }
            ],
        }


def _cycle(tmp_path: Path, statuses: dict[str, str], outcomes: dict[str, str] | None = None):
    portfolio_repository = EngineeringPortfolioRepository(tmp_path)
    goal_repository = EngineeringGoalRepository(tmp_path)
    goal_loop = FakeGoalLoop(outcomes)
    portfolio_repository.create_portfolio({"portfolio_id": "portfolio_1", "name": "Cycle portfolio"})
    for goal_id, status in statuses.items():
        goal_repository.save_goal(
            {"goal_id": goal_id, "summary": goal_id, "status": status},
            completion_attestation=_attestation(goal_id) if status in {"complete", "completed"} else None,
        )
        portfolio_repository.add_goal_to_portfolio("portfolio_1", goal_id)
    coordinator = EngineeringPortfolioCoordinator(
        repo_root=tmp_path,
        portfolio_repository=portfolio_repository,
        goal_repository=goal_repository,
        goal_loop=goal_loop,
    )
    return (
        EngineeringPortfolioCycle(
            repo_root=tmp_path,
            portfolio_repository=portfolio_repository,
            goal_repository=goal_repository,
            goal_loop=goal_loop,
            coordinator=coordinator,
        ),
        goal_repository,
        goal_loop,
    )


def test_portfolio_cycle_can_advance_multiple_goals(tmp_path) -> None:
    cycle, goal_repository, goal_loop = _cycle(tmp_path, {"goal_1": "pending", "goal_2": "pending"})

    result = cycle.run_cycle("portfolio_1")

    assert result["stop_reason"] == "portfolio_completed"
    assert result["cycle_count"] == 2
    assert result["executed_goal_count"] == 2
    assert result["completed_goal_count"] == 2
    assert result["blocked_goal_count"] == 0
    assert goal_loop.calls == ["goal_1", "goal_2"]
    assert goal_repository.load_goal("goal_1")["status"] == "complete"
    assert goal_repository.load_goal("goal_2")["status"] == "complete"
    assert result["portfolio_id"] == "portfolio_1"
    assert result["goal_id"] == "goal_2"
    assert result["selected_goal"]["selected_goal_id"] == "goal_2"
    assert result["execution_path"]["portfolio_owns_goal_selection"] is True


def test_blocked_and_completed_goals_are_skipped_and_not_rerun(tmp_path) -> None:
    cycle, goal_repository, goal_loop = _cycle(
        tmp_path,
        {"done": "complete", "blocked": "blocked", "ready": "pending"},
    )

    result = cycle.run_until_idle("portfolio_1")

    assert goal_loop.calls == ["ready"]
    assert goal_repository.load_goal("done")["status"] == "complete"
    assert goal_repository.load_goal("blocked")["status"] == "blocked"
    assert goal_repository.load_goal("ready")["status"] == "complete"
    assert result["executed_goal_count"] == 1
    assert result["completed_goal_count"] == 2
    assert result["blocked_goal_count"] == 1
    assert result["skipped_goal_count"] >= 2


def test_run_until_idle_stops_when_no_runnable_goal_remains(tmp_path) -> None:
    cycle, _goal_repository, goal_loop = _cycle(tmp_path, {"goal_1": "pending", "goal_2": "blocked"})

    result = cycle.run_until_idle("portfolio_1", max_goals=5)

    assert result["stop_reason"] == "no_runnable_goal"
    assert result["cycle_count"] == 1
    assert result["executed_goal_count"] == 1
    assert goal_loop.calls == ["goal_1"]


def test_run_until_idle_stops_at_max_goals(tmp_path) -> None:
    cycle, _goal_repository, goal_loop = _cycle(
        tmp_path,
        {"goal_1": "pending", "goal_2": "pending", "goal_3": "pending"},
    )

    result = cycle.run_until_idle("portfolio_1", max_goals=2)

    assert result["stop_reason"] == "max_goals_reached"
    assert result["cycle_count"] == 2
    assert result["executed_goal_count"] == 2
    assert goal_loop.calls == ["goal_1", "goal_2"]


def test_build_cycle_summary_counts_skipped_unique_goals(tmp_path) -> None:
    cycle, _goal_repository, _goal_loop = _cycle(tmp_path, {})

    summary = cycle.build_cycle_summary(
        portfolio_id="portfolio_1",
        runs=[{"selected_goal_id": "goal_1"}, {"selected_goal_id": "goal_2"}],
        selections=[
            {"skipped_goals": [{"goal_id": "done"}, {"goal_id": "blocked"}]},
            {"skipped_goals": [{"goal_id": "done"}]},
        ],
        stop_reason="no_runnable_goal",
        portfolio_state={"progress": {"completed_goal_count": 2, "blocked_goal_count": 1}, "state": "active"},
        max_goals=5,
    )

    assert summary["cycle_count"] == 2
    assert summary["executed_goal_count"] == 2
    assert summary["completed_goal_count"] == 2
    assert summary["blocked_goal_count"] == 1
    assert summary["skipped_goal_count"] == 2
    assert summary["portfolio_state"]["state"] == "active"
