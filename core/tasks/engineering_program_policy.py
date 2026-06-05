from __future__ import annotations

"""Selection policy for engineering program portfolios.

EngineeringProgramPolicy classifies portfolio summaries and selects the first
runnable portfolio in the order supplied by the program. It does not load data,
execute portfolios, inspect goals, schedule work, or call runtime owners.
"""

import copy
import time
from typing import Any, Mapping


ENGINEERING_PROGRAM_POLICY_SCHEMA = "zero.engineering_program_policy.v1"
ENGINEERING_PROGRAM_POLICY_SELECTION_SCHEMA = "zero.engineering_program_policy.selection.v1"

RUNNABLE_PORTFOLIO_STATES = {"active"}
SKIPPED_PORTFOLIO_STATES = {"completed", "blocked", "paused", "archived", "missing"}


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_summary(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


class EngineeringProgramPolicy:
    """Classify portfolio summaries and select the next runnable portfolio."""

    def classify_portfolio_state(self, portfolio_summary: Mapping[str, Any]) -> str:
        state = _clean_text(_as_summary(portfolio_summary).get("state"), "active").lower()
        if state in RUNNABLE_PORTFOLIO_STATES | SKIPPED_PORTFOLIO_STATES:
            return state
        return "active"

    def is_runnable_portfolio(self, portfolio_summary: Mapping[str, Any]) -> bool:
        return self.classify_portfolio_state(portfolio_summary) == "active"

    def explain_skip_reason(self, portfolio_summary: Mapping[str, Any]) -> str:
        state = self.classify_portfolio_state(portfolio_summary)
        if state == "active":
            return ""
        if state == "missing":
            return "portfolio_not_found"
        return f"portfolio_{state}"

    def select_next_portfolio(self, portfolio_summaries: list[Mapping[str, Any]]) -> dict[str, Any]:
        normalized = [_as_summary(item) for item in portfolio_summaries if isinstance(item, Mapping)]
        skipped_portfolios: list[dict[str, Any]] = []
        for summary in normalized:
            portfolio_id = _clean_text(summary.get("portfolio_id"))
            state = self.classify_portfolio_state(summary)
            if self.is_runnable_portfolio(summary):
                return {
                    "schema": ENGINEERING_PROGRAM_POLICY_SELECTION_SCHEMA,
                    "ok": True,
                    "decision": "selected",
                    "reason": "selected_runnable_portfolio",
                    "selected_portfolio_id": portfolio_id,
                    "selected_portfolio": copy.deepcopy(summary),
                    "skipped_portfolios": skipped_portfolios,
                    "selection_summary": self.build_selection_summary(normalized),
                    "execution_path": {
                        "deterministic_ref_order": True,
                        "priority_algorithm": False,
                        "parallel_execution": False,
                        "portfolio_execution": False,
                        "scheduler_used": False,
                        "goal_repository_used_here": False,
                        "runtime_orchestrator_used_here": False,
                    },
                    "updated_at": time.time(),
                }
            skipped_portfolios.append(
                {
                    "portfolio_id": portfolio_id,
                    "state": state,
                    "reason": self.explain_skip_reason(summary),
                }
            )

        return {
            "schema": ENGINEERING_PROGRAM_POLICY_SELECTION_SCHEMA,
            "ok": False,
            "decision": "no_runnable_portfolio",
            "reason": "no_runnable_portfolio",
            "selected_portfolio_id": "",
            "selected_portfolio": {},
            "skipped_portfolios": skipped_portfolios,
            "selection_summary": self.build_selection_summary(normalized),
            "execution_path": {
                "deterministic_ref_order": True,
                "priority_algorithm": False,
                "parallel_execution": False,
                "portfolio_execution": False,
                "scheduler_used": False,
                "goal_repository_used_here": False,
                "runtime_orchestrator_used_here": False,
            },
            "updated_at": time.time(),
        }

    def build_selection_summary(self, portfolio_summaries: list[Mapping[str, Any]]) -> dict[str, Any]:
        normalized = [_as_summary(item) for item in portfolio_summaries if isinstance(item, Mapping)]
        runnable_portfolio_ids: list[str] = []
        skipped_portfolios: list[dict[str, Any]] = []
        state_counts: dict[str, int] = {}
        for summary in normalized:
            portfolio_id = _clean_text(summary.get("portfolio_id"))
            state = self.classify_portfolio_state(summary)
            state_counts[state] = state_counts.get(state, 0) + 1
            if state == "active":
                runnable_portfolio_ids.append(portfolio_id)
            else:
                skipped_portfolios.append(
                    {
                        "portfolio_id": portfolio_id,
                        "state": state,
                        "reason": self.explain_skip_reason(summary),
                    }
                )

        return {
            "schema": ENGINEERING_PROGRAM_POLICY_SCHEMA,
            "portfolio_count": len(normalized),
            "runnable_portfolio_ids": runnable_portfolio_ids,
            "runnable_portfolio_count": len(runnable_portfolio_ids),
            "skipped_portfolios": skipped_portfolios,
            "skipped_portfolio_count": len(skipped_portfolios),
            "state_counts": state_counts,
            "deterministic_ref_order": True,
            "priority_algorithm": False,
            "updated_at": time.time(),
        }


__all__ = [
    "ENGINEERING_PROGRAM_POLICY_SCHEMA",
    "ENGINEERING_PROGRAM_POLICY_SELECTION_SCHEMA",
    "EngineeringProgramPolicy",
]
