from __future__ import annotations

from pathlib import Path

from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.engineering_portfolio_coordinator import EngineeringPortfolioCoordinator
from core.tasks.engineering_portfolio_cycle import EngineeringPortfolioCycle
from core.tasks.engineering_portfolio_repository import EngineeringPortfolioRepository


class AdaptiveGoalLoop:
    def __init__(self, decision: dict) -> None:
        self.decision = decision

    def run_until_terminal(self, goal_id: str, max_cycles: int = 3, *, goal_lineage=None) -> dict:
        return {
            "ok": self.decision["decision"] == "complete",
            "goal_id": goal_id,
            "terminal": self.decision["decision"] in {"complete", "blocked", "replan"},
            "stop_reason": self.decision["decision"],
            "adaptive_decision": self.decision,
            "adaptive_reason": self.decision["reason"],
            "adaptive_confidence": self.decision["confidence"],
            "cycle_count": 1,
            "cycles": [],
        }


def _cycle(tmp_path: Path, decision: dict) -> EngineeringPortfolioCycle:
    portfolio_repository = EngineeringPortfolioRepository(tmp_path)
    goal_repository = EngineeringGoalRepository(tmp_path)
    goal_loop = AdaptiveGoalLoop(decision)
    portfolio_repository.create_portfolio({"portfolio_id": "portfolio_1", "name": "Adaptive portfolio"})
    goal_repository.save_goal({"goal_id": "goal_1", "summary": "Adaptive goal", "status": "pending"})
    portfolio_repository.add_goal_to_portfolio("portfolio_1", "goal_1")
    coordinator = EngineeringPortfolioCoordinator(
        repo_root=tmp_path,
        portfolio_repository=portfolio_repository,
        goal_repository=goal_repository,
        goal_loop=goal_loop,
    )
    return EngineeringPortfolioCycle(
        repo_root=tmp_path,
        portfolio_repository=portfolio_repository,
        goal_repository=goal_repository,
        goal_loop=goal_loop,
        coordinator=coordinator,
    )


def test_portfolio_summary_preserves_goal_adaptive_state(tmp_path) -> None:
    decision = {
        "decision": "blocked",
        "reason": "critical_failure",
        "confidence": 0.9,
        "continuation_plan": {},
        "replan_request": {},
        "blocking_issues": [{"issue_id": "blocker-1"}],
    }

    result = _cycle(tmp_path, decision).run_until_idle("portfolio_1", max_goals=1)

    run = result["runs"][0]
    assert result["adaptive_decision"] == decision
    assert result["adaptive_reason"] == "critical_failure"
    assert result["adaptive_confidence"] == 0.9
    assert result["stop_reason"] == "portfolio_blocked"
    assert run["adaptive_decision"] == decision
    assert run["adaptive_reason"] == "critical_failure"
    assert run["stop_reason"] == "blocked"
