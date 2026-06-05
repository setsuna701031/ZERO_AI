from __future__ import annotations

"""Coordinate engineering programs over existing portfolio cycles.

EngineeringProgramCoordinator owns only program-to-portfolio orchestration. It
does not inspect goals directly, call runtime owners, schedule globally, run in
parallel, persist memory, or apply priority rules.
"""

import copy
import time
from pathlib import Path
from typing import Any, Mapping

from core.tasks.engineering_portfolio_cycle import EngineeringPortfolioCycle
from core.tasks.engineering_portfolio_repository import EngineeringPortfolioRepository
from core.tasks.engineering_program_policy import EngineeringProgramPolicy
from core.tasks.engineering_program_repository import EngineeringProgramRepository
from core.tasks.engineering_program_state import EngineeringProgramState


ENGINEERING_PROGRAM_COORDINATOR_SCHEMA = "zero.engineering_program_coordinator.v1"
ENGINEERING_PROGRAM_SELECTION_SCHEMA = "zero.engineering_program_coordinator.selection.v1"


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _as_portfolio_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    refs: list[str] = []
    seen: set[str] = set()
    for item in value:
        portfolio_id = _clean_text(item)
        if portfolio_id and portfolio_id not in seen:
            refs.append(portfolio_id)
            seen.add(portfolio_id)
    return refs


class EngineeringProgramCoordinator:
    """Select runnable portfolios from a program and delegate to PortfolioCycle."""

    def __init__(
        self,
        *,
        repo_root: str | Path,
        program_repository: EngineeringProgramRepository | Any | None = None,
        portfolio_repository: EngineeringPortfolioRepository | Any | None = None,
        program_state: EngineeringProgramState | Any | None = None,
        program_policy: EngineeringProgramPolicy | Any | None = None,
        portfolio_cycle: EngineeringPortfolioCycle | Any | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.program_repository = program_repository or EngineeringProgramRepository(self.repo_root)
        self.portfolio_repository = portfolio_repository or EngineeringPortfolioRepository(self.repo_root)
        self.portfolio_cycle = portfolio_cycle or EngineeringPortfolioCycle(
            repo_root=self.repo_root,
            portfolio_repository=self.portfolio_repository,
        )
        self.program_state = program_state or EngineeringProgramState(
            self.repo_root,
            program_repository=self.program_repository,
            portfolio_repository=self.portfolio_repository,
        )
        self.program_policy = program_policy or EngineeringProgramPolicy()

    def select_next_portfolio(self, program_id: str) -> dict[str, Any]:
        target_program_id = _clean_text(program_id)
        program = self.program_repository.load_program(target_program_id)
        if program is None:
            return self._selection_result(
                program_id=target_program_id,
                program={},
                selected_portfolio={},
                policy_selection={
                    "ok": False,
                    "decision": "program_not_found",
                    "reason": "program_not_found",
                    "selected_portfolio_id": "",
                    "selected_portfolio": {},
                    "skipped_portfolios": [],
                    "selection_summary": {},
                },
                reason="program_not_found",
            )

        program_summary = self.program_state.summarize_program(target_program_id)
        portfolio_summaries = program_summary.get("portfolios") if isinstance(program_summary.get("portfolios"), list) else []
        policy_selection = self.program_policy.select_next_portfolio(portfolio_summaries)
        selected_portfolio_id = _clean_text(policy_selection.get("selected_portfolio_id"))
        selected_portfolio = self.portfolio_repository.load_portfolio(selected_portfolio_id) if selected_portfolio_id else None

        return self._selection_result(
            program_id=target_program_id,
            program=program,
            selected_portfolio=selected_portfolio or {},
            policy_selection=policy_selection,
        )

    def run_next_portfolio(self, program_id: str) -> dict[str, Any]:
        selection = self.select_next_portfolio(program_id)
        selected_portfolio_id = _clean_text(selection.get("selected_portfolio_id"))
        if not bool(selection.get("ok")) or not selected_portfolio_id:
            return {
                "schema": ENGINEERING_PROGRAM_COORDINATOR_SCHEMA,
                "ok": False,
                "mode": "engineering_program_coordinator",
                "action": "run_next_portfolio",
                "program_id": _clean_text(program_id),
                "selected_portfolio_id": "",
                "reason": _clean_text(selection.get("reason"), "no_runnable_portfolio"),
                "selection": selection,
                "cycle_result": {},
                "updated_at": time.time(),
            }

        cycle_result = self.portfolio_cycle.run_until_idle(selected_portfolio_id, max_goals=1)
        return {
            "schema": ENGINEERING_PROGRAM_COORDINATOR_SCHEMA,
            "ok": bool(cycle_result.get("ok")),
            "mode": "engineering_program_coordinator",
            "action": "run_next_portfolio",
            "program_id": _clean_text(program_id),
            "selected_portfolio_id": selected_portfolio_id,
            "reason": _clean_text(cycle_result.get("stop_reason"), "portfolio_cycle_finished"),
            "selection": selection,
            "cycle_result": copy.deepcopy(dict(cycle_result)),
            "updated_at": time.time(),
        }

    def run_program_cycle(self, program_id: str, max_portfolios: int = 1) -> dict[str, Any]:
        portfolio_limit = max(1, int(max_portfolios or 1))
        runs: list[dict[str, Any]] = []
        stop_reason = "max_portfolios_reached"

        for _ in range(portfolio_limit):
            run = self.run_next_portfolio(program_id)
            if not bool(run.get("selection", {}).get("ok")):
                stop_reason = _clean_text(run.get("reason"), "no_runnable_portfolio")
                return self._cycle_result(program_id, runs, stop_reason, max_portfolios=portfolio_limit, no_runnable=run)
            runs.append(run)

        return self._cycle_result(program_id, runs, stop_reason, max_portfolios=portfolio_limit, no_runnable={})

    def summarize_program_state(self, program_id: str) -> dict[str, Any]:
        target_program_id = _clean_text(program_id)
        summary = self.program_state.summarize_program(target_program_id)
        if not bool(summary.get("ok")):
            return {
                "schema": ENGINEERING_PROGRAM_COORDINATOR_SCHEMA,
                "ok": False,
                "program_id": target_program_id,
                "reason": "program_not_found",
                "portfolio_count": 0,
                "runnable_portfolio_ids": [],
                "skipped_portfolios": [],
                "portfolios": [],
                "updated_at": time.time(),
            }
        return {
            "schema": ENGINEERING_PROGRAM_COORDINATOR_SCHEMA,
            "ok": True,
            "program_id": target_program_id,
            "state": _clean_text(summary.get("state"), "active"),
            "program": copy.deepcopy(_as_mapping(summary.get("program"))),
            "portfolio_count": int(summary.get("portfolio_count") or 0),
            "completed_portfolio_count": int(summary.get("completed_portfolio_count") or 0),
            "blocked_portfolio_count": int(summary.get("blocked_portfolio_count") or 0),
            "active_portfolio_count": int(summary.get("active_portfolio_count") or 0),
            "completion_ratio": float(summary.get("completion_ratio") or 0.0),
            "progress": copy.deepcopy(_as_mapping(summary.get("progress"))),
            "runnable_portfolio_ids": copy.deepcopy(summary.get("runnable_portfolio_ids")) if isinstance(summary.get("runnable_portfolio_ids"), list) else [],
            "skipped_portfolios": copy.deepcopy(summary.get("skipped_portfolios")) if isinstance(summary.get("skipped_portfolios"), list) else [],
            "missing_portfolio_ids": copy.deepcopy(summary.get("missing_portfolio_ids")) if isinstance(summary.get("missing_portfolio_ids"), list) else [],
            "portfolios": copy.deepcopy(summary.get("portfolios")) if isinstance(summary.get("portfolios"), list) else [],
            "program_summary": copy.deepcopy(dict(summary)),
            "reason": _clean_text(summary.get("reason"), "ok"),
            "updated_at": time.time(),
        }

    def _selection_result(
        self,
        *,
        program_id: str,
        program: Mapping[str, Any],
        selected_portfolio: Mapping[str, Any],
        policy_selection: Mapping[str, Any] | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        policy_selection = policy_selection if isinstance(policy_selection, Mapping) else {}
        selected_portfolio_id = _clean_text(selected_portfolio.get("portfolio_id"))
        selected_policy_summary = policy_selection.get("selected_portfolio") if isinstance(policy_selection.get("selected_portfolio"), Mapping) else {}
        return {
            "schema": ENGINEERING_PROGRAM_SELECTION_SCHEMA,
            "ok": bool(selected_portfolio_id),
            "program_id": program_id,
            "decision": _clean_text(policy_selection.get("decision"), "selected" if selected_portfolio_id else _clean_text(reason, "no_runnable_portfolio")),
            "reason": _clean_text(policy_selection.get("reason"), reason or "no_runnable_portfolio"),
            "selected_portfolio_id": selected_portfolio_id,
            "selected_portfolio": copy.deepcopy(dict(selected_portfolio)) if isinstance(selected_portfolio, Mapping) else {},
            "selected_portfolio_state": copy.deepcopy(dict(selected_policy_summary)),
            "program": copy.deepcopy(dict(program)) if isinstance(program, Mapping) else {},
            "skipped_portfolios": copy.deepcopy(policy_selection.get("skipped_portfolios")) if isinstance(policy_selection.get("skipped_portfolios"), list) else [],
            "selection_summary": copy.deepcopy(policy_selection.get("selection_summary")) if isinstance(policy_selection.get("selection_summary"), Mapping) else {},
            "policy_selection": copy.deepcopy(dict(policy_selection)) if isinstance(policy_selection, Mapping) else {},
            "execution_path": {
                "deterministic_ref_order": True,
                "priority_algorithm": False,
                "parallel_execution": False,
                "scheduler_used": False,
                "program_policy_used": True,
                "program_repository_data_only": True,
                "goal_repository_used_here": False,
                "runtime_orchestrator_used_here": False,
                "portfolio_cycle_delegated": False,
            },
            "updated_at": time.time(),
        }

    def _cycle_result(
        self,
        program_id: str,
        runs: list[dict[str, Any]],
        stop_reason: str,
        *,
        max_portfolios: int,
        no_runnable: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "schema": ENGINEERING_PROGRAM_COORDINATOR_SCHEMA,
            "ok": bool(runs) and stop_reason != "no_runnable_portfolio",
            "mode": "engineering_program_coordinator",
            "action": "run_program_cycle",
            "program_id": _clean_text(program_id),
            "stop_reason": stop_reason,
            "max_portfolios": int(max_portfolios),
            "run_count": len(runs),
            "runs": copy.deepcopy(runs),
            "no_runnable_result": copy.deepcopy(dict(no_runnable)) if isinstance(no_runnable, Mapping) else {},
            "program_state": self.summarize_program_state(program_id),
            "updated_at": time.time(),
        }


__all__ = [
    "ENGINEERING_PROGRAM_COORDINATOR_SCHEMA",
    "ENGINEERING_PROGRAM_SELECTION_SCHEMA",
    "EngineeringProgramCoordinator",
]
