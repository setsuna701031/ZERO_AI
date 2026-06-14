from __future__ import annotations

"""Coordinate portfolio goal refs with the existing goal loop.

EngineeringPortfolioCoordinator coordinates portfolio goal refs, delegates
selection rules to EngineeringPortfolioPolicy, and delegates selected goal
execution to EngineeringGoalLoop. It does not schedule globally, execute work
directly, persist memory, or call runtime owners.
"""

import copy
import time
from pathlib import Path
from typing import Any, Mapping

from core.tasks.engineering_goal_loop import EngineeringGoalLoop
from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.engineering_portfolio_policy import EngineeringPortfolioPolicy
from core.tasks.engineering_portfolio_repository import EngineeringPortfolioRepository
from core.tasks.engineering_portfolio_state import EngineeringPortfolioState


ENGINEERING_PORTFOLIO_COORDINATOR_SCHEMA = "zero.engineering_portfolio_coordinator.v1"
ENGINEERING_PORTFOLIO_SELECTION_SCHEMA = "zero.engineering_portfolio_coordinator.selection.v1"


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _as_goal_ids(value: Any) -> list[str]:
    return [_clean_text(item) for item in value if _clean_text(item)] if isinstance(value, list) else []


class EngineeringPortfolioCoordinator:
    """Select runnable portfolio goals and delegate them to EngineeringGoalLoop."""

    def __init__(
        self,
        *,
        repo_root: str | Path,
        portfolio_repository: EngineeringPortfolioRepository | Any | None = None,
        goal_repository: EngineeringGoalRepository | Any | None = None,
        goal_loop: EngineeringGoalLoop | Any | None = None,
        portfolio_state: EngineeringPortfolioState | Any | None = None,
        portfolio_policy: EngineeringPortfolioPolicy | Any | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.portfolio_repository = portfolio_repository or EngineeringPortfolioRepository(self.repo_root)
        self.goal_repository = goal_repository or EngineeringGoalRepository(self.repo_root)
        self.goal_loop = goal_loop or EngineeringGoalLoop(repo_root=self.repo_root, repository=self.goal_repository)
        self.portfolio_state = portfolio_state or EngineeringPortfolioState()
        self.portfolio_policy = portfolio_policy or EngineeringPortfolioPolicy()

    def select_next_goal(self, portfolio_id: str) -> dict[str, Any]:
        target_portfolio_id = _clean_text(portfolio_id)
        portfolio = self.portfolio_repository.load_portfolio(target_portfolio_id)
        if portfolio is None:
            return self._selection_result(
                portfolio_id=target_portfolio_id,
                policy_selection={
                    "ok": False,
                    "decision": "portfolio_not_found",
                    "reason": "portfolio_not_found",
                    "selected_goal": {},
                    "skipped_goals": [],
                    "selection_summary": {},
                },
            )

        goals: list[dict[str, Any]] = []
        for goal_id in _as_goal_ids(portfolio.get("goal_ids")):
            goal = self.goal_repository.load_goal(goal_id)
            if goal is None:
                goals.append({"goal_id": goal_id, "status": "missing"})
                continue
            goals.append(copy.deepcopy(dict(goal)))

        policy_selection = self.portfolio_policy.select_next_goal(goals)
        return self._selection_result(portfolio_id=target_portfolio_id, policy_selection=policy_selection)

    def run_next_goal(self, portfolio_id: str) -> dict[str, Any]:
        selection = self.select_next_goal(portfolio_id)
        selected_goal_id = _clean_text(selection.get("selected_goal_id"))
        if not bool(selection.get("ok")) or not selected_goal_id:
            return {
                "schema": ENGINEERING_PORTFOLIO_COORDINATOR_SCHEMA,
                "ok": False,
                "mode": "engineering_portfolio_coordinator",
                "action": "run_next_goal",
                "portfolio_id": _clean_text(portfolio_id),
                "selected_goal_id": "",
                "reason": _clean_text(selection.get("reason"), "no_runnable_goal"),
                "selection": selection,
                "loop_result": {},
                "updated_goal": {},
                "updated_at": time.time(),
            }

        loop_result = self.goal_loop.run_until_terminal(selected_goal_id, max_cycles=3)
        updated_goal = self._record_loop_terminal_status(selected_goal_id, loop_result)
        return {
            "schema": ENGINEERING_PORTFOLIO_COORDINATOR_SCHEMA,
            "ok": bool(loop_result.get("ok")),
            "mode": "engineering_portfolio_coordinator",
            "action": "run_next_goal",
            "portfolio_id": _clean_text(portfolio_id),
            "selected_goal_id": selected_goal_id,
            "reason": _clean_text(loop_result.get("stop_reason"), "goal_loop_finished"),
            "selection": selection,
            "loop_result": copy.deepcopy(dict(loop_result)),
            "updated_goal": updated_goal,
            "updated_at": time.time(),
        }

    def run_portfolio_cycle(self, portfolio_id: str, max_goals: int = 1) -> dict[str, Any]:
        goal_limit = max(1, int(max_goals or 1))
        runs: list[dict[str, Any]] = []
        stop_reason = "max_goals_reached"

        for _ in range(goal_limit):
            run = self.run_next_goal(portfolio_id)
            if not bool(run.get("selection", {}).get("ok")):
                stop_reason = _clean_text(run.get("reason"), "no_runnable_goal")
                return self._cycle_result(portfolio_id, runs, stop_reason, max_goals=goal_limit, no_runnable=run)
            runs.append(run)

        return self._cycle_result(portfolio_id, runs, stop_reason, max_goals=goal_limit, no_runnable={})

    def summarize_portfolio_state(self, portfolio_id: str) -> dict[str, Any]:
        target_portfolio_id = _clean_text(portfolio_id)
        portfolio = self.portfolio_repository.load_portfolio(target_portfolio_id)
        if portfolio is None:
            return {
                "schema": ENGINEERING_PORTFOLIO_COORDINATOR_SCHEMA,
                "ok": False,
                "portfolio_id": target_portfolio_id,
                "reason": "portfolio_not_found",
                "goals": [],
                "runnable_goal_ids": [],
                "terminal_goal_ids": [],
                "missing_goal_ids": [],
            }

        goals: list[dict[str, Any]] = []
        loaded_goal_records: list[dict[str, Any]] = []
        runnable_goal_ids: list[str] = []
        terminal_goal_ids: list[str] = []
        missing_goal_ids: list[str] = []
        for goal_id in _as_goal_ids(portfolio.get("goal_ids")):
            goal = self.goal_repository.load_goal(goal_id)
            if goal is None:
                missing_goal_ids.append(goal_id)
                goals.append({"goal_id": goal_id, "status": "missing", "runnable": False})
                continue
            loaded_goal_records.append(copy.deepcopy(dict(goal)))
            status = _clean_text(goal.get("status"), "pending").lower()
            runnable = bool(self.portfolio_policy.is_runnable_goal(goal))
            if runnable:
                runnable_goal_ids.append(goal_id)
            else:
                terminal_goal_ids.append(goal_id)
            goals.append(
                {
                    "goal_id": goal_id,
                    "status": status,
                    "summary": _clean_text(goal.get("summary")),
                    "runnable": runnable,
                }
            )
        portfolio_summary = self.portfolio_state.summarize_portfolio(portfolio, loaded_goal_records)
        return {
            "schema": ENGINEERING_PORTFOLIO_COORDINATOR_SCHEMA,
            "ok": True,
            "portfolio_id": target_portfolio_id,
            "state": _clean_text(portfolio_summary.get("state"), "active"),
            "progress": {
                "goal_count": int(portfolio_summary.get("goal_count") or 0),
                "completed_goal_count": int(portfolio_summary.get("completed_goal_count") or 0),
                "blocked_goal_count": int(portfolio_summary.get("blocked_goal_count") or 0),
                "active_goal_count": int(portfolio_summary.get("active_goal_count") or 0),
                "completion_ratio": float(portfolio_summary.get("completion_ratio") or 0.0),
            },
            "portfolio_summary": portfolio_summary,
            "portfolio": copy.deepcopy(dict(portfolio)),
            "goals": goals,
            "runnable_goal_ids": runnable_goal_ids,
            "terminal_goal_ids": terminal_goal_ids,
            "missing_goal_ids": missing_goal_ids,
            "updated_at": time.time(),
        }

    def read_portfolio_state(self, portfolio_id: str) -> dict[str, Any]:
        target_portfolio_id = _clean_text(portfolio_id)
        summary = self.summarize_portfolio_state(target_portfolio_id)
        if not bool(summary.get("ok")):
            return summary
        progress = _as_mapping(summary.get("progress"))
        return {
            "schema": ENGINEERING_PORTFOLIO_COORDINATOR_SCHEMA,
            "ok": True,
            "portfolio_id": target_portfolio_id,
            "state": _clean_text(summary.get("state"), "active"),
            **progress,
            "updated_at": time.time(),
        }

    def _selection_result(
        self,
        *,
        portfolio_id: str,
        policy_selection: Mapping[str, Any],
    ) -> dict[str, Any]:
        selected = _as_mapping(policy_selection.get("selected_goal"))
        return {
            "schema": ENGINEERING_PORTFOLIO_SELECTION_SCHEMA,
            "ok": bool(policy_selection.get("ok")),
            "portfolio_id": portfolio_id,
            "decision": _clean_text(policy_selection.get("decision"), "no_runnable_goal"),
            "reason": _clean_text(policy_selection.get("reason"), "no_runnable_goal"),
            "selected_goal_id": _clean_text(selected.get("goal_id")),
            "selected_goal": selected,
            "skipped_goals": copy.deepcopy(policy_selection.get("skipped_goals")) if isinstance(policy_selection.get("skipped_goals"), list) else [],
            "selection_summary": copy.deepcopy(policy_selection.get("selection_summary")) if isinstance(policy_selection.get("selection_summary"), Mapping) else {},
            "execution_path": {
                "deterministic_ref_order": True,
                "priority_algorithm": False,
                "portfolio_policy_used": True,
                "scheduler_used": False,
                "runtime_orchestrator_used_here": False,
            },
            "updated_at": time.time(),
        }

    def _record_loop_terminal_status(self, goal_id: str, loop_result: Mapping[str, Any]) -> dict[str, Any]:
        stop_reason = _clean_text(loop_result.get("stop_reason")).lower()
        if stop_reason == "complete":
            cycles = loop_result.get("cycles") if isinstance(loop_result.get("cycles"), list) else []
            latest_cycle = cycles[-1] if cycles and isinstance(cycles[-1], Mapping) else {}
            return self.goal_repository.update_goal(
                goal_id,
                {"status": "complete"},
                completion_attestation=latest_cycle.get("goal_completion_attestation"),
            )
        if stop_reason == "blocked":
            return self.goal_repository.update_goal(goal_id, {"status": "blocked"})
        return {}

    def _cycle_result(
        self,
        portfolio_id: str,
        runs: list[dict[str, Any]],
        stop_reason: str,
        *,
        max_goals: int,
        no_runnable: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "schema": ENGINEERING_PORTFOLIO_COORDINATOR_SCHEMA,
            "ok": bool(runs) and stop_reason != "no_runnable_goal",
            "mode": "engineering_portfolio_coordinator",
            "action": "run_portfolio_cycle",
            "portfolio_id": _clean_text(portfolio_id),
            "stop_reason": stop_reason,
            "max_goals": int(max_goals),
            "run_count": len(runs),
            "runs": copy.deepcopy(runs),
            "no_runnable_result": copy.deepcopy(dict(no_runnable)) if isinstance(no_runnable, Mapping) else {},
            "portfolio_state": self.summarize_portfolio_state(portfolio_id),
            "updated_at": time.time(),
        }


__all__ = [
    "ENGINEERING_PORTFOLIO_COORDINATOR_SCHEMA",
    "ENGINEERING_PORTFOLIO_SELECTION_SCHEMA",
    "EngineeringPortfolioCoordinator",
]
