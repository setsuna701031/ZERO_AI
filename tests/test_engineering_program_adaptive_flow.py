from __future__ import annotations

from core.tasks.engineering_program_cycle import EngineeringProgramCycle


class ProgramCoordinator:
    def __init__(self) -> None:
        self.states = [
            {
                "ok": True,
                "program_id": "program_1",
                "state": "active",
                "completed_portfolio_count": 0,
                "blocked_portfolio_count": 0,
            },
            {
                "ok": True,
                "program_id": "program_1",
                "state": "active",
                "completed_portfolio_count": 0,
                "blocked_portfolio_count": 0,
            },
        ]

    def summarize_program_state(self, program_id: str) -> dict:
        if len(self.states) > 1:
            return self.states.pop(0)
        return self.states[0]

    def select_next_portfolio(self, program_id: str) -> dict:
        return {
            "ok": True,
            "program_id": program_id,
            "selected_portfolio_id": "portfolio_1",
            "skipped_portfolios": [],
        }


class PortfolioCycle:
    def __init__(self, decision: dict) -> None:
        self.decision = decision

    def run_until_idle(self, portfolio_id: str) -> dict:
        return {
            "ok": self.decision["decision"] == "complete",
            "portfolio_id": portfolio_id,
            "stop_reason": "portfolio_replan",
            "adaptive_decision": self.decision,
            "adaptive_reason": self.decision["reason"],
            "adaptive_confidence": self.decision["confidence"],
            "cycle_count": 1,
        }


def test_program_summary_preserves_portfolio_adaptive_state(tmp_path) -> None:
    decision = {
        "decision": "replan",
        "reason": "missing_output",
        "confidence": 0.8,
        "continuation_plan": {},
        "replan_request": {"reason": "missing_output"},
        "blocking_issues": [],
    }

    result = EngineeringProgramCycle(
        repo_root=tmp_path,
        coordinator=ProgramCoordinator(),
        portfolio_cycle=PortfolioCycle(decision),
    ).run_until_idle("program_1", max_portfolios=1)

    run = result["runs"][0]
    assert result["adaptive_decision"] == decision
    assert result["adaptive_reason"] == "missing_output"
    assert result["adaptive_confidence"] == 0.8
    assert result["stop_reason"] == "max_portfolios_reached"
    assert run["adaptive_decision"] == decision
    assert run["adaptive_reason"] == "missing_output"
    assert run["stop_reason"] == "portfolio_replan"
