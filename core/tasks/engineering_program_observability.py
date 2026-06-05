from __future__ import annotations

"""Read-only engineering program observability summaries.

EngineeringProgramObservability builds program, portfolio, and goal summaries
from repository snapshots. It does not execute goals, run portfolio/program
cycles, coordinate selection, change lifecycle state, or import execution
owners.
"""

import copy
import time
from pathlib import Path
from typing import Any, Mapping

from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.engineering_portfolio_repository import EngineeringPortfolioRepository
from core.tasks.engineering_portfolio_state import EngineeringPortfolioState
from core.tasks.engineering_program_repository import EngineeringProgramRepository
from core.tasks.engineering_program_state import EngineeringProgramState


ENGINEERING_PROGRAM_OBSERVABILITY_SCHEMA = "zero.engineering_program_observability.v1"
ENGINEERING_PROGRAM_TREE_SUMMARY_SCHEMA = "zero.engineering_program_observability.tree.v1"

COMPLETED_GOAL_STATUSES = {"complete", "completed"}
BLOCKED_GOAL_STATUSES = {"blocked"}
TERMINAL_GOAL_STATUSES = COMPLETED_GOAL_STATUSES | BLOCKED_GOAL_STATUSES | {"cancelled", "canceled"}


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _as_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    ids: list[str] = []
    seen: set[str] = set()
    for item in value:
        item_id = _clean_text(item)
        if item_id and item_id not in seen:
            ids.append(item_id)
            seen.add(item_id)
    return ids


def _goal_status(goal: Mapping[str, Any]) -> str:
    return _clean_text(goal.get("status"), "pending").lower()


def _goal_summary(goal_id: str, goal: Mapping[str, Any] | None) -> dict[str, Any]:
    if goal is None:
        return {
            "goal_id": _clean_text(goal_id),
            "summary": "",
            "status": "missing",
            "state": "missing",
            "active": False,
            "blocked": False,
            "completed": False,
            "missing": True,
        }
    status = _goal_status(goal)
    return {
        "goal_id": _clean_text(goal.get("goal_id"), goal_id),
        "summary": _clean_text(goal.get("summary")),
        "status": status,
        "state": status,
        "active": status not in TERMINAL_GOAL_STATUSES,
        "blocked": status in BLOCKED_GOAL_STATUSES,
        "completed": status in COMPLETED_GOAL_STATUSES,
        "missing": False,
    }


class EngineeringProgramObservability:
    """Build read-only rollups for program, portfolio, and goal state."""

    def __init__(
        self,
        repo_root: str | Path,
        *,
        program_repository: EngineeringProgramRepository | Any | None = None,
        program_state: EngineeringProgramState | Any | None = None,
        portfolio_repository: EngineeringPortfolioRepository | Any | None = None,
        portfolio_state: EngineeringPortfolioState | Any | None = None,
        goal_repository: EngineeringGoalRepository | Any | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.program_repository = program_repository or EngineeringProgramRepository(self.repo_root)
        self.portfolio_repository = portfolio_repository or EngineeringPortfolioRepository(self.repo_root)
        self.goal_repository = goal_repository or EngineeringGoalRepository(self.repo_root)
        self.portfolio_state = portfolio_state or EngineeringPortfolioState()
        self.program_state = program_state or EngineeringProgramState(
            self.repo_root,
            program_repository=self.program_repository,
            portfolio_repository=self.portfolio_repository,
            portfolio_state=self.portfolio_state,
        )

    def build_program_tree_summary(self, program_id: str) -> dict[str, Any]:
        target_program_id = _clean_text(program_id)
        program = self.program_repository.load_program(target_program_id)
        if program is None:
            return self._not_found_summary(target_program_id, schema=ENGINEERING_PROGRAM_TREE_SUMMARY_SCHEMA)

        portfolios = self.summarize_portfolios(target_program_id).get("portfolios", [])
        metrics = self.calculate_rollup_metrics(target_program_id)
        return {
            "schema": ENGINEERING_PROGRAM_TREE_SUMMARY_SCHEMA,
            "ok": True,
            "program_id": target_program_id,
            "program": copy.deepcopy(dict(program)),
            "program_state": _clean_text(metrics.get("program_state"), "active"),
            "tree": {
                "program_id": target_program_id,
                "name": _clean_text(program.get("name")),
                "state": _clean_text(metrics.get("program_state"), "active"),
                "portfolios": copy.deepcopy(portfolios),
            },
            **metrics,
            "updated_at": time.time(),
        }

    def summarize_portfolios(self, program_id: str) -> dict[str, Any]:
        target_program_id = _clean_text(program_id)
        program = self.program_repository.load_program(target_program_id)
        if program is None:
            return self._not_found_summary(target_program_id)

        portfolios: list[dict[str, Any]] = []
        for portfolio_id in _as_ids(program.get("portfolio_ids")):
            portfolio = self.portfolio_repository.load_portfolio(portfolio_id)
            if portfolio is None:
                portfolios.append(
                    {
                        "portfolio_id": portfolio_id,
                        "name": "",
                        "state": "missing",
                        "goal_count": 0,
                        "completed_goal_count": 0,
                        "blocked_goal_count": 0,
                        "active_goal_count": 0,
                        "completion_ratio": 0.0,
                        "goals": [],
                        "missing": True,
                    }
                )
                continue
            goals = self._load_portfolio_goals(portfolio)
            portfolio_summary = self.portfolio_state.summarize_portfolio(portfolio, goals)
            portfolios.append(
                {
                    "portfolio_id": portfolio_id,
                    "name": _clean_text(portfolio.get("name")),
                    "state": _clean_text(portfolio_summary.get("state"), "active"),
                    "goal_count": int(portfolio_summary.get("goal_count") or 0),
                    "completed_goal_count": int(portfolio_summary.get("completed_goal_count") or 0),
                    "blocked_goal_count": int(portfolio_summary.get("blocked_goal_count") or 0),
                    "active_goal_count": int(portfolio_summary.get("active_goal_count") or 0),
                    "completion_ratio": float(portfolio_summary.get("completion_ratio") or 0.0),
                    "goals": [_goal_summary(_clean_text(goal.get("goal_id")), goal) for goal in goals],
                    "missing_goal_ids": copy.deepcopy(portfolio_summary.get("missing_goal_ids"))
                    if isinstance(portfolio_summary.get("missing_goal_ids"), list)
                    else [],
                    "missing": False,
                }
            )
        return {
            "schema": ENGINEERING_PROGRAM_OBSERVABILITY_SCHEMA,
            "ok": True,
            "program_id": target_program_id,
            "portfolios": portfolios,
            "updated_at": time.time(),
        }

    def summarize_goals(self, program_id: str) -> dict[str, Any]:
        target_program_id = _clean_text(program_id)
        portfolio_result = self.summarize_portfolios(target_program_id)
        if not bool(portfolio_result.get("ok")):
            return portfolio_result
        goals: list[dict[str, Any]] = []
        for portfolio in portfolio_result.get("portfolios", []):
            if not isinstance(portfolio, Mapping):
                continue
            portfolio_id = _clean_text(portfolio.get("portfolio_id"))
            for goal in portfolio.get("goals", []) if isinstance(portfolio.get("goals"), list) else []:
                if isinstance(goal, Mapping):
                    item = _as_mapping(goal)
                    item["portfolio_id"] = portfolio_id
                    goals.append(item)
        return {
            "schema": ENGINEERING_PROGRAM_OBSERVABILITY_SCHEMA,
            "ok": True,
            "program_id": target_program_id,
            "goals": goals,
            "updated_at": time.time(),
        }

    def calculate_rollup_metrics(self, program_id: str) -> dict[str, Any]:
        target_program_id = _clean_text(program_id)
        program_summary = self.program_state.summarize_program(target_program_id)
        if not bool(program_summary.get("ok")):
            return self._not_found_summary(target_program_id)
        portfolio_result = self.summarize_portfolios(target_program_id)
        portfolios = portfolio_result.get("portfolios") if isinstance(portfolio_result.get("portfolios"), list) else []

        completed_portfolio_count = 0
        blocked_portfolio_count = 0
        active_portfolio_count = 0
        goal_count = 0
        completed_goal_count = 0
        blocked_goal_count = 0
        active_goal_count = 0
        active_portfolios: list[dict[str, Any]] = []
        blocked_portfolios: list[dict[str, Any]] = []
        active_goals: list[dict[str, Any]] = []
        blocked_goals: list[dict[str, Any]] = []

        for portfolio in portfolios:
            if not isinstance(portfolio, Mapping):
                continue
            state = _clean_text(portfolio.get("state"), "active").lower()
            portfolio_item = {
                "portfolio_id": _clean_text(portfolio.get("portfolio_id")),
                "name": _clean_text(portfolio.get("name")),
                "state": state,
            }
            if state == "completed":
                completed_portfolio_count += 1
            elif state == "blocked":
                blocked_portfolio_count += 1
                blocked_portfolios.append(portfolio_item)
            elif state == "active":
                active_portfolio_count += 1
                active_portfolios.append(portfolio_item)

            goal_count += int(portfolio.get("goal_count") or 0)
            completed_goal_count += int(portfolio.get("completed_goal_count") or 0)
            blocked_goal_count += int(portfolio.get("blocked_goal_count") or 0)
            active_goal_count += int(portfolio.get("active_goal_count") or 0)
            for goal in portfolio.get("goals", []) if isinstance(portfolio.get("goals"), list) else []:
                if not isinstance(goal, Mapping):
                    continue
                goal_item = {
                    "program_id": target_program_id,
                    "portfolio_id": _clean_text(portfolio.get("portfolio_id")),
                    "goal_id": _clean_text(goal.get("goal_id")),
                    "summary": _clean_text(goal.get("summary")),
                    "status": _clean_text(goal.get("status"), "pending"),
                }
                if bool(goal.get("blocked")):
                    blocked_goals.append(goal_item)
                elif bool(goal.get("active")):
                    active_goals.append(goal_item)

        portfolio_count = len(_as_ids(_as_mapping(program_summary.get("program")).get("portfolio_ids")))
        completion_ratio = completed_goal_count / goal_count if goal_count else 0.0
        return {
            "schema": ENGINEERING_PROGRAM_OBSERVABILITY_SCHEMA,
            "ok": True,
            "program_id": target_program_id,
            "program_state": self._rollup_program_state(portfolios, fallback=_clean_text(program_summary.get("state"), "active")),
            "portfolio_count": portfolio_count,
            "completed_portfolio_count": completed_portfolio_count,
            "blocked_portfolio_count": blocked_portfolio_count,
            "active_portfolio_count": active_portfolio_count,
            "goal_count": goal_count,
            "completed_goal_count": completed_goal_count,
            "blocked_goal_count": blocked_goal_count,
            "active_goal_count": active_goal_count,
            "completion_ratio": completion_ratio,
            "active_portfolios": active_portfolios,
            "blocked_portfolios": blocked_portfolios,
            "active_goals": active_goals,
            "blocked_goals": blocked_goals,
            "updated_at": time.time(),
        }

    def list_blocked_items(self, program_id: str) -> dict[str, Any]:
        metrics = self.calculate_rollup_metrics(program_id)
        if not bool(metrics.get("ok")):
            return metrics
        return {
            "schema": ENGINEERING_PROGRAM_OBSERVABILITY_SCHEMA,
            "ok": True,
            "program_id": _clean_text(program_id),
            "blocked_portfolios": copy.deepcopy(metrics.get("blocked_portfolios")),
            "blocked_goals": copy.deepcopy(metrics.get("blocked_goals")),
            "blocked_portfolio_count": int(metrics.get("blocked_portfolio_count") or 0),
            "blocked_goal_count": int(metrics.get("blocked_goal_count") or 0),
            "updated_at": time.time(),
        }

    def list_active_items(self, program_id: str) -> dict[str, Any]:
        metrics = self.calculate_rollup_metrics(program_id)
        if not bool(metrics.get("ok")):
            return metrics
        return {
            "schema": ENGINEERING_PROGRAM_OBSERVABILITY_SCHEMA,
            "ok": True,
            "program_id": _clean_text(program_id),
            "active_portfolios": copy.deepcopy(metrics.get("active_portfolios")),
            "active_goals": copy.deepcopy(metrics.get("active_goals")),
            "active_portfolio_count": int(metrics.get("active_portfolio_count") or 0),
            "active_goal_count": int(metrics.get("active_goal_count") or 0),
            "updated_at": time.time(),
        }

    def _load_portfolio_goals(self, portfolio: Mapping[str, Any]) -> list[dict[str, Any]]:
        goals: list[dict[str, Any]] = []
        for goal_id in _as_ids(portfolio.get("goal_ids")):
            goal = self.goal_repository.load_goal(goal_id)
            if goal is None:
                goals.append({"goal_id": goal_id, "summary": "", "status": "missing"})
            else:
                goals.append(copy.deepcopy(dict(goal)))
        return goals

    def _rollup_program_state(self, portfolios: list[Any], *, fallback: str) -> str:
        states = [_clean_text(portfolio.get("state"), "active").lower() for portfolio in portfolios if isinstance(portfolio, Mapping)]
        if not states:
            return _clean_text(fallback, "active")
        if all(state == "completed" for state in states):
            return "completed"
        if all(state == "archived" for state in states):
            return "archived"
        if any(state == "active" for state in states):
            return "active"
        if any(state == "blocked" for state in states):
            return "blocked"
        if all(state == "paused" for state in states):
            return "paused"
        return _clean_text(fallback, "active")

    def _not_found_summary(self, program_id: str, *, schema: str = ENGINEERING_PROGRAM_OBSERVABILITY_SCHEMA) -> dict[str, Any]:
        return {
            "schema": schema,
            "ok": False,
            "program_id": _clean_text(program_id),
            "reason": "program_not_found",
            "program_state": "",
            "portfolio_count": 0,
            "completed_portfolio_count": 0,
            "blocked_portfolio_count": 0,
            "active_portfolio_count": 0,
            "goal_count": 0,
            "completed_goal_count": 0,
            "blocked_goal_count": 0,
            "active_goal_count": 0,
            "completion_ratio": 0.0,
            "active_portfolios": [],
            "blocked_portfolios": [],
            "active_goals": [],
            "blocked_goals": [],
            "updated_at": time.time(),
        }


__all__ = [
    "ENGINEERING_PROGRAM_OBSERVABILITY_SCHEMA",
    "ENGINEERING_PROGRAM_TREE_SUMMARY_SCHEMA",
    "EngineeringProgramObservability",
]
