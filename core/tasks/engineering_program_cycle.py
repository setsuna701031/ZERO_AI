from __future__ import annotations

"""Bounded auto-cycle orchestration for engineering programs.

EngineeringProgramCycle advances program portfolios sequentially through the
program coordinator and portfolio cycle. It does not inspect goals, run task
runtimes, schedule globally, plan adaptively, persist memory, or call lower
execution owners directly.
"""

import copy
import time
from pathlib import Path
from typing import Any, Mapping

from core.tasks.engineering_issue_summary import apply_engineering_issue_summary
from core.tasks.engineering_portfolio_cycle import EngineeringPortfolioCycle
from core.tasks.engineering_portfolio_repository import EngineeringPortfolioRepository
from core.tasks.engineering_program_coordinator import EngineeringProgramCoordinator
from core.tasks.engineering_program_repository import EngineeringProgramRepository
from core.tasks.engineering_program_state import EngineeringProgramState


ENGINEERING_PROGRAM_CYCLE_SCHEMA = "zero.engineering_program_cycle.v1"
ENGINEERING_PROGRAM_CYCLE_SUMMARY_SCHEMA = "zero.engineering_program_cycle.summary.v1"

STOP_STATES = {"completed", "blocked", "paused", "archived"}


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


class EngineeringProgramCycle:
    """Advance program portfolios one at a time until a bounded stop condition."""

    def __init__(
        self,
        *,
        repo_root: str | Path,
        coordinator: EngineeringProgramCoordinator | Any | None = None,
        program_repository: EngineeringProgramRepository | Any | None = None,
        portfolio_repository: EngineeringPortfolioRepository | Any | None = None,
        portfolio_cycle: EngineeringPortfolioCycle | Any | None = None,
        program_state: EngineeringProgramState | Any | None = None,
        issue_reporter: Any | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.program_repository = program_repository or EngineeringProgramRepository(self.repo_root)
        self.portfolio_repository = portfolio_repository or EngineeringPortfolioRepository(self.repo_root)
        self.issue_reporter = issue_reporter
        self.portfolio_cycle = portfolio_cycle or EngineeringPortfolioCycle(
            repo_root=self.repo_root,
            portfolio_repository=self.portfolio_repository,
            issue_reporter=self.issue_reporter,
        )
        self.program_state = program_state or EngineeringProgramState(
            self.repo_root,
            program_repository=self.program_repository,
            portfolio_repository=self.portfolio_repository,
        )
        self.coordinator = coordinator or EngineeringProgramCoordinator(
            repo_root=self.repo_root,
            program_repository=self.program_repository,
            portfolio_repository=self.portfolio_repository,
            program_state=self.program_state,
            portfolio_cycle=self.portfolio_cycle,
        )

    def run_cycle(self, program_id: str) -> dict[str, Any]:
        return self.run_until_idle(program_id, max_portfolios=1)

    def run_until_idle(self, program_id: str, max_portfolios: int = 5) -> dict[str, Any]:
        target_program_id = _clean_text(program_id)
        portfolio_limit = max(1, int(max_portfolios or 1))
        runs: list[dict[str, Any]] = []
        selections: list[dict[str, Any]] = []
        stop_reason = "max_portfolios_reached"

        current_state = self.coordinator.summarize_program_state(target_program_id)
        if not bool(current_state.get("ok")):
            return self.build_cycle_summary(
                program_id=target_program_id,
                runs=runs,
                selections=selections,
                stop_reason=_clean_text(current_state.get("reason"), "program_not_found"),
                program_state=current_state,
                max_portfolios=portfolio_limit,
            )

        initial_state = _clean_text(current_state.get("state")).lower()
        if initial_state in STOP_STATES:
            return self.build_cycle_summary(
                program_id=target_program_id,
                runs=runs,
                selections=selections,
                stop_reason=f"program_{initial_state}",
                program_state=current_state,
                max_portfolios=portfolio_limit,
            )

        for _ in range(portfolio_limit):
            selection = self.coordinator.select_next_portfolio(target_program_id)
            selections.append(selection)
            selected_portfolio_id = _clean_text(selection.get("selected_portfolio_id"))
            if not bool(selection.get("ok")) or not selected_portfolio_id:
                stop_reason = _clean_text(selection.get("reason"), "no_runnable_portfolio")
                current_state = self.coordinator.summarize_program_state(target_program_id)
                break

            portfolio_result = self.portfolio_cycle.run_until_idle(selected_portfolio_id)
            current_state = self.coordinator.summarize_program_state(target_program_id)
            adaptive_decision = _as_mapping(portfolio_result.get("adaptive_decision"))
            runs.append(
                {
                    "schema": ENGINEERING_PROGRAM_CYCLE_SCHEMA,
                    "ok": bool(portfolio_result.get("ok")),
                    "program_id": target_program_id,
                    "selected_portfolio_id": selected_portfolio_id,
                    "selection": copy.deepcopy(selection),
                    "portfolio_cycle_result": copy.deepcopy(dict(portfolio_result)),
                    "adaptive_decision": copy.deepcopy(adaptive_decision),
                    "adaptive_reason": _clean_text(adaptive_decision.get("reason") or portfolio_result.get("adaptive_reason")),
                    "adaptive_confidence": adaptive_decision.get("confidence", portfolio_result.get("adaptive_confidence", 0.0)),
                    "stop_reason": _clean_text(portfolio_result.get("stop_reason")),
                    "program_state": copy.deepcopy(current_state),
                    "updated_at": time.time(),
                }
            )

            state = _clean_text(current_state.get("state")).lower()
            if state == "completed":
                stop_reason = "program_completed"
                break
            if state == "blocked":
                stop_reason = "program_blocked"
                break

        return self.build_cycle_summary(
            program_id=target_program_id,
            runs=runs,
            selections=selections,
            stop_reason=stop_reason,
            program_state=current_state,
            max_portfolios=portfolio_limit,
        )

    def build_cycle_summary(
        self,
        *,
        program_id: str,
        runs: list[Mapping[str, Any]],
        selections: list[Mapping[str, Any]],
        stop_reason: str,
        program_state: Mapping[str, Any],
        max_portfolios: int | None = None,
    ) -> dict[str, Any]:
        skipped_portfolio_ids: set[str] = set()
        for selection in selections:
            skipped = selection.get("skipped_portfolios") if isinstance(selection.get("skipped_portfolios"), list) else []
            for item in skipped:
                if isinstance(item, Mapping):
                    portfolio_id = _clean_text(item.get("portfolio_id"))
                    if portfolio_id:
                        skipped_portfolio_ids.add(portfolio_id)
        latest_run = _as_mapping(runs[-1]) if runs else {}
        latest_adaptive_decision = _as_mapping(latest_run.get("adaptive_decision"))

        return apply_engineering_issue_summary(
            {
            "schema": ENGINEERING_PROGRAM_CYCLE_SUMMARY_SCHEMA,
            "ok": _clean_text(stop_reason) not in {"program_not_found"},
            "program_id": _clean_text(program_id),
            "stop_reason": _clean_text(stop_reason),
            "adaptive_decision": copy.deepcopy(latest_adaptive_decision),
            "adaptive_reason": _clean_text(latest_run.get("adaptive_reason") or latest_adaptive_decision.get("reason")),
            "adaptive_confidence": latest_adaptive_decision.get("confidence", latest_run.get("adaptive_confidence", 0.0)),
            "max_portfolios": max_portfolios,
            "cycle_count": len(runs),
            "executed_portfolio_count": len(
                {
                    _clean_text(run.get("selected_portfolio_id"))
                    for run in runs
                    if _clean_text(run.get("selected_portfolio_id"))
                }
            ),
            "completed_portfolio_count": int(program_state.get("completed_portfolio_count") or 0),
            "blocked_portfolio_count": int(program_state.get("blocked_portfolio_count") or 0),
            "skipped_portfolio_count": len(skipped_portfolio_ids),
            "program_state": copy.deepcopy(dict(program_state)) if isinstance(program_state, Mapping) else {},
            "runs": [copy.deepcopy(dict(run)) for run in runs],
            "selections": [copy.deepcopy(dict(selection)) for selection in selections],
            "updated_at": time.time(),
            },
            repo_root=self.repo_root,
            issue_reporter=self.issue_reporter,
        )


__all__ = [
    "ENGINEERING_PROGRAM_CYCLE_SCHEMA",
    "ENGINEERING_PROGRAM_CYCLE_SUMMARY_SCHEMA",
    "EngineeringProgramCycle",
]
