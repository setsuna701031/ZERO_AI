from __future__ import annotations

"""Derived lifecycle state for engineering programs.

EngineeringProgramState reads program records and portfolio records, then uses
EngineeringPortfolioState to derive portfolio summaries. It does not inspect
goals directly, execute cycles, schedule work, persist memory, or call runtime
owners.
"""

import copy
import time
from pathlib import Path
from typing import Any, Mapping

from core.tasks.engineering_portfolio_repository import EngineeringPortfolioRepository
from core.tasks.engineering_portfolio_state import EngineeringPortfolioState
from core.tasks.engineering_program_repository import EngineeringProgramRepository


ENGINEERING_PROGRAM_STATE_SCHEMA = "zero.engineering_program_state.v1"
ENGINEERING_PROGRAM_SUMMARY_SCHEMA = "zero.engineering_program_summary.v1"

PROGRAM_STATES = {"active", "paused", "blocked", "completed", "archived"}
NON_RUNNABLE_PROGRAM_PORTFOLIO_STATES = {"completed", "blocked", "paused", "archived"}


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


def _record_state(record: Mapping[str, Any]) -> str:
    metadata = _as_mapping(record.get("metadata"))
    candidates = (
        record.get("program_state"),
        record.get("portfolio_state"),
        record.get("lifecycle_state"),
        record.get("state"),
        record.get("status"),
        metadata.get("program_state"),
        metadata.get("portfolio_state"),
        metadata.get("lifecycle_state"),
        metadata.get("state"),
        metadata.get("status"),
    )
    for candidate in candidates:
        state = _clean_text(candidate).lower()
        if state in PROGRAM_STATES:
            return state
    return ""


class EngineeringProgramState:
    """Evaluate lifecycle state and progress for one program snapshot."""

    def __init__(
        self,
        repo_root: str | Path,
        *,
        program_repository: EngineeringProgramRepository | Any | None = None,
        portfolio_repository: EngineeringPortfolioRepository | Any | None = None,
        portfolio_state: EngineeringPortfolioState | Any | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.program_repository = program_repository or EngineeringProgramRepository(self.repo_root)
        self.portfolio_repository = portfolio_repository or EngineeringPortfolioRepository(self.repo_root)
        self.portfolio_state = portfolio_state or EngineeringPortfolioState()

    def evaluate_program_state(self, program_id: str) -> dict[str, Any]:
        summary = self.summarize_program(program_id)
        if not bool(summary.get("ok")):
            return summary
        return {
            "schema": ENGINEERING_PROGRAM_STATE_SCHEMA,
            "ok": True,
            "program_id": _clean_text(program_id),
            "state": _clean_text(summary.get("state"), "active"),
            **_as_mapping(summary.get("progress")),
            "updated_at": time.time(),
        }

    def calculate_program_progress(self, program_id: str) -> dict[str, Any]:
        program = self.program_repository.load_program(program_id)
        if program is None:
            return {
                "schema": ENGINEERING_PROGRAM_STATE_SCHEMA,
                "ok": False,
                "program_id": _clean_text(program_id),
                "reason": "program_not_found",
                "portfolio_count": 0,
                "completed_portfolio_count": 0,
                "blocked_portfolio_count": 0,
                "active_portfolio_count": 0,
                "completion_ratio": 0.0,
            }

        portfolio_summaries = self._portfolio_summaries(program)
        progress = self._calculate_progress_from_summaries(_as_portfolio_ids(program.get("portfolio_ids")), portfolio_summaries)
        return {
            "schema": ENGINEERING_PROGRAM_STATE_SCHEMA,
            "ok": True,
            "program_id": _clean_text(program_id),
            **progress,
            "updated_at": time.time(),
        }

    def summarize_program(self, program_id: str) -> dict[str, Any]:
        target_program_id = _clean_text(program_id)
        program = self.program_repository.load_program(target_program_id)
        if program is None:
            return {
                "schema": ENGINEERING_PROGRAM_SUMMARY_SCHEMA,
                "ok": False,
                "program_id": target_program_id,
                "reason": "program_not_found",
                "state": "",
                "progress": {
                    "portfolio_count": 0,
                    "completed_portfolio_count": 0,
                    "blocked_portfolio_count": 0,
                    "active_portfolio_count": 0,
                    "completion_ratio": 0.0,
                },
                "portfolios": [],
                "runnable_portfolio_ids": [],
                "skipped_portfolios": [],
                "missing_portfolio_ids": [],
                "updated_at": time.time(),
            }

        portfolio_ids = _as_portfolio_ids(program.get("portfolio_ids"))
        portfolio_summaries = self._portfolio_summaries(program)
        progress = self._calculate_progress_from_summaries(portfolio_ids, portfolio_summaries)
        state = self._evaluate_state_from_summaries(portfolio_ids, portfolio_summaries)
        runnable_portfolio_ids: list[str] = []
        skipped_portfolios: list[dict[str, Any]] = []
        missing_portfolio_ids: list[str] = []

        for summary in portfolio_summaries:
            portfolio_id = _clean_text(summary.get("portfolio_id"))
            state_value = _clean_text(summary.get("state"), "active").lower()
            if state_value == "missing":
                missing_portfolio_ids.append(portfolio_id)
                skipped_portfolios.append({"portfolio_id": portfolio_id, "state": "missing", "reason": "portfolio_not_found"})
            elif state_value in NON_RUNNABLE_PROGRAM_PORTFOLIO_STATES:
                skipped_portfolios.append({"portfolio_id": portfolio_id, "state": state_value, "reason": f"portfolio_{state_value}"})
            else:
                runnable_portfolio_ids.append(portfolio_id)

        return {
            "schema": ENGINEERING_PROGRAM_SUMMARY_SCHEMA,
            "ok": True,
            "program_id": target_program_id,
            "state": state,
            "progress": progress,
            **progress,
            "program": copy.deepcopy(dict(program)),
            "portfolios": portfolio_summaries,
            "runnable_portfolio_ids": runnable_portfolio_ids,
            "skipped_portfolios": skipped_portfolios,
            "missing_portfolio_ids": missing_portfolio_ids,
            "reason": "ok" if runnable_portfolio_ids else "no_runnable_portfolio",
            "updated_at": time.time(),
        }

    def _portfolio_summaries(self, program: Mapping[str, Any]) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for portfolio_id in _as_portfolio_ids(program.get("portfolio_ids")):
            portfolio = self.portfolio_repository.load_portfolio(portfolio_id)
            if portfolio is None:
                summaries.append({"portfolio_id": portfolio_id, "state": "missing", "runnable": False, "portfolio": {}})
                continue
            summary = self.portfolio_state.summarize_portfolio(portfolio, [])
            state = _record_state(portfolio) or _clean_text(summary.get("state"), "active").lower()
            runnable = state not in NON_RUNNABLE_PROGRAM_PORTFOLIO_STATES
            summaries.append(
                {
                    "portfolio_id": portfolio_id,
                    "name": _clean_text(portfolio.get("name")),
                    "state": state,
                    "runnable": runnable,
                    "portfolio": copy.deepcopy(dict(portfolio)),
                    "portfolio_summary": copy.deepcopy(dict(summary)),
                }
            )
        return summaries

    def _calculate_progress_from_summaries(
        self,
        portfolio_ids: list[str],
        portfolio_summaries: list[Mapping[str, Any]],
    ) -> dict[str, Any]:
        completed_portfolio_count = 0
        blocked_portfolio_count = 0
        active_portfolio_count = 0
        for summary in portfolio_summaries:
            state = _clean_text(summary.get("state"), "active").lower()
            if state == "completed":
                completed_portfolio_count += 1
            elif state == "blocked":
                blocked_portfolio_count += 1
            elif state == "active":
                active_portfolio_count += 1
        portfolio_count = len(portfolio_ids)
        completion_ratio = completed_portfolio_count / portfolio_count if portfolio_count else 0.0
        return {
            "portfolio_count": portfolio_count,
            "completed_portfolio_count": completed_portfolio_count,
            "blocked_portfolio_count": blocked_portfolio_count,
            "active_portfolio_count": active_portfolio_count,
            "completion_ratio": completion_ratio,
        }

    def _evaluate_state_from_summaries(self, portfolio_ids: list[str], portfolio_summaries: list[Mapping[str, Any]]) -> str:
        if not portfolio_ids:
            return "active"
        states = [_clean_text(summary.get("state"), "active").lower() for summary in portfolio_summaries]
        known_states = [state for state in states if state in PROGRAM_STATES]
        if known_states and len(known_states) == len(portfolio_ids) and all(state == "completed" for state in known_states):
            return "completed"
        if known_states and len(known_states) == len(portfolio_ids) and all(state == "archived" for state in known_states):
            return "archived"
        if any(state == "active" for state in states):
            return "active"
        if any(state == "blocked" for state in states):
            return "blocked"
        if states and all(state == "paused" for state in states):
            return "paused"
        return "active"


__all__ = [
    "ENGINEERING_PROGRAM_STATE_SCHEMA",
    "ENGINEERING_PROGRAM_SUMMARY_SCHEMA",
    "PROGRAM_STATES",
    "EngineeringProgramState",
]
