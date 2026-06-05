from __future__ import annotations

"""Bounded auto-cycle orchestration for engineering portfolios.

EngineeringPortfolioCycle advances portfolio goals sequentially through the
existing coordinator and goal loop. It does not schedule globally, run goals in
parallel, choose by priority, persist memory, render UI, or call runtime owners
directly.
"""

import copy
import time
from pathlib import Path
from typing import Any, Mapping

from core.tasks.engineering_goal_loop import EngineeringGoalLoop
from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.engineering_issue_summary import apply_engineering_issue_summary
from core.tasks.engineering_portfolio_coordinator import EngineeringPortfolioCoordinator
from core.tasks.engineering_portfolio_repository import EngineeringPortfolioRepository


ENGINEERING_PORTFOLIO_CYCLE_SCHEMA = "zero.engineering_portfolio_cycle.v1"
ENGINEERING_PORTFOLIO_CYCLE_SUMMARY_SCHEMA = "zero.engineering_portfolio_cycle.summary.v1"

STOP_STATES = {"completed", "blocked", "paused", "archived"}


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


class EngineeringPortfolioCycle:
    """Advance portfolio goals one at a time until a bounded stop condition."""

    def __init__(
        self,
        *,
        repo_root: str | Path,
        coordinator: EngineeringPortfolioCoordinator | Any | None = None,
        portfolio_repository: EngineeringPortfolioRepository | Any | None = None,
        goal_repository: EngineeringGoalRepository | Any | None = None,
        goal_loop: EngineeringGoalLoop | Any | None = None,
        issue_reporter: Any | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.portfolio_repository = portfolio_repository or EngineeringPortfolioRepository(self.repo_root)
        self.goal_repository = goal_repository or EngineeringGoalRepository(self.repo_root)
        self.issue_reporter = issue_reporter
        self.goal_loop = goal_loop or EngineeringGoalLoop(
            repo_root=self.repo_root,
            repository=self.goal_repository,
            issue_reporter=self.issue_reporter,
        )
        self.coordinator = coordinator or EngineeringPortfolioCoordinator(
            repo_root=self.repo_root,
            portfolio_repository=self.portfolio_repository,
            goal_repository=self.goal_repository,
            goal_loop=self.goal_loop,
        )

    def run_cycle(self, portfolio_id: str) -> dict[str, Any]:
        return self.run_until_idle(portfolio_id, max_goals=5)

    def run_until_idle(self, portfolio_id: str, max_goals: int = 5) -> dict[str, Any]:
        target_portfolio_id = _clean_text(portfolio_id)
        goal_limit = max(1, int(max_goals or 1))
        runs: list[dict[str, Any]] = []
        selections: list[dict[str, Any]] = []
        stop_reason = "max_goals_reached"

        initial_state = self.coordinator.summarize_portfolio_state(target_portfolio_id)
        if not bool(initial_state.get("ok")):
            return self.build_cycle_summary(
                portfolio_id=target_portfolio_id,
                runs=runs,
                selections=selections,
                stop_reason=_clean_text(initial_state.get("reason"), "portfolio_not_found"),
                portfolio_state=initial_state,
                max_goals=goal_limit,
            )
        if _clean_text(initial_state.get("state")).lower() in STOP_STATES:
            return self.build_cycle_summary(
                portfolio_id=target_portfolio_id,
                runs=runs,
                selections=selections,
                stop_reason=f"portfolio_{_clean_text(initial_state.get('state')).lower()}",
                portfolio_state=initial_state,
                max_goals=goal_limit,
            )

        current_state = initial_state
        for _ in range(goal_limit):
            selection = self.coordinator.select_next_goal(target_portfolio_id)
            selections.append(selection)
            selected_goal_id = _clean_text(selection.get("selected_goal_id"))
            if not bool(selection.get("ok")) or not selected_goal_id:
                stop_reason = _clean_text(selection.get("reason"), "no_runnable_goal")
                current_state = self.coordinator.summarize_portfolio_state(target_portfolio_id)
                break

            loop_result = self.goal_loop.run_until_terminal(selected_goal_id, max_cycles=3)
            updated_goal = self._record_terminal_status(selected_goal_id, loop_result)
            current_state = self.coordinator.summarize_portfolio_state(target_portfolio_id)
            runs.append(
                {
                    "schema": ENGINEERING_PORTFOLIO_CYCLE_SCHEMA,
                    "ok": bool(loop_result.get("terminal")),
                    "portfolio_id": target_portfolio_id,
                    "selected_goal_id": selected_goal_id,
                    "selection": copy.deepcopy(selection),
                    "loop_result": copy.deepcopy(dict(loop_result)),
                    "updated_goal": updated_goal,
                    "portfolio_state": copy.deepcopy(current_state),
                    "updated_at": time.time(),
                }
            )

            state = _clean_text(current_state.get("state")).lower()
            if state == "completed":
                stop_reason = "portfolio_completed"
                break
            if state == "blocked":
                stop_reason = "portfolio_blocked"
                break

        return self.build_cycle_summary(
            portfolio_id=target_portfolio_id,
            runs=runs,
            selections=selections,
            stop_reason=stop_reason,
            portfolio_state=current_state,
            max_goals=goal_limit,
        )

    def build_cycle_summary(
        self,
        *,
        portfolio_id: str,
        runs: list[Mapping[str, Any]],
        selections: list[Mapping[str, Any]],
        stop_reason: str,
        portfolio_state: Mapping[str, Any],
        max_goals: int | None = None,
    ) -> dict[str, Any]:
        progress = _as_mapping(portfolio_state.get("progress"))
        skipped_goal_ids: set[str] = set()
        for selection in selections:
            skipped = selection.get("skipped_goals") if isinstance(selection.get("skipped_goals"), list) else []
            for item in skipped:
                if isinstance(item, Mapping):
                    goal_id = _clean_text(item.get("goal_id"))
                    if goal_id:
                        skipped_goal_ids.add(goal_id)

        return apply_engineering_issue_summary(
            {
            "schema": ENGINEERING_PORTFOLIO_CYCLE_SUMMARY_SCHEMA,
            "ok": _clean_text(stop_reason) not in {"portfolio_not_found"},
            "portfolio_id": _clean_text(portfolio_id),
            "stop_reason": _clean_text(stop_reason),
            "max_goals": max_goals,
            "cycle_count": len(runs),
            "executed_goal_count": len({_clean_text(run.get("selected_goal_id")) for run in runs if _clean_text(run.get("selected_goal_id"))}),
            "completed_goal_count": int(progress.get("completed_goal_count") or 0),
            "blocked_goal_count": int(progress.get("blocked_goal_count") or 0),
            "skipped_goal_count": len(skipped_goal_ids),
            "portfolio_state": copy.deepcopy(dict(portfolio_state)) if isinstance(portfolio_state, Mapping) else {},
            "runs": [copy.deepcopy(dict(run)) for run in runs],
            "selections": [copy.deepcopy(dict(selection)) for selection in selections],
            "updated_at": time.time(),
            },
            repo_root=self.repo_root,
            issue_reporter=self.issue_reporter,
        )

    def _record_terminal_status(self, goal_id: str, loop_result: Mapping[str, Any]) -> dict[str, Any]:
        stop_reason = _clean_text(loop_result.get("stop_reason")).lower()
        if stop_reason == "complete":
            return self.goal_repository.update_goal(goal_id, {"status": "complete"})
        if stop_reason == "blocked":
            return self.goal_repository.update_goal(goal_id, {"status": "blocked"})
        return {}


__all__ = [
    "ENGINEERING_PORTFOLIO_CYCLE_SCHEMA",
    "ENGINEERING_PORTFOLIO_CYCLE_SUMMARY_SCHEMA",
    "EngineeringPortfolioCycle",
]
