from __future__ import annotations

import ast
from pathlib import Path

from core.evidence import EvidenceRecord, EvidenceValidator
from core.goals.goal_completion_authority import GoalCompletionAuthority
from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.engineering_portfolio_coordinator import (
    ENGINEERING_PORTFOLIO_COORDINATOR_SCHEMA,
    EngineeringPortfolioCoordinator,
)
from core.tasks.engineering_portfolio_repository import EngineeringPortfolioRepository


REPO_ROOT = Path(__file__).resolve().parents[1]
COORDINATOR_FILE = REPO_ROOT / "core/tasks/engineering_portfolio_coordinator.py"


def _attestation(goal_id: str, goal_lineage=None):
    evidence = EvidenceValidator().validate(
        EvidenceRecord(
            "seed-e",
            goal_id,
            None,
            "test",
            "ok",
            "now",
            metadata=goal_lineage or {},
        )
    )
    return GoalCompletionAuthority().complete_goal(
        goal_id=goal_id,
        evidence_refs=[evidence],
        all_subgoals_completed=True,
        goal_lineage=goal_lineage,
    )


class FakeGoalLoop:
    def __init__(self, *, stop_reason: str = "complete") -> None:
        self.stop_reason = stop_reason
        self.calls: list[tuple[str, int]] = []

    def run_until_terminal(self, goal_id: str, max_cycles: int = 3, *, goal_lineage=None) -> dict:
        self.calls.append((goal_id, max_cycles))
        evidence = EvidenceValidator().validate(
            EvidenceRecord("e1", goal_id, None, "test", "ok", "now", metadata=goal_lineage or {})
        )
        attestation = GoalCompletionAuthority().complete_goal(
            goal_id=goal_id,
            evidence_refs=[evidence],
            all_subgoals_completed=True,
            goal_lineage=goal_lineage,
        )
        return {
            "ok": self.stop_reason == "complete",
            "goal_id": goal_id,
            "terminal": self.stop_reason in {"complete", "blocked"},
            "stop_reason": self.stop_reason,
            "cycle_count": 1,
            "cycles": [
                {
                    "cycle_index": 0,
                    "goal_id": goal_id,
                    "runtime_state": self.stop_reason,
                    "adaptive_decision": self.stop_reason,
                    "adaptive_reason": f"{self.stop_reason}_reason",
                    "goal_completion_attestation": attestation if self.stop_reason == "complete" else None,
                }
            ],
        }


def _repos(tmp_path):
    return EngineeringPortfolioRepository(tmp_path), EngineeringGoalRepository(tmp_path)


def _portfolio_with_goals(tmp_path, statuses: dict[str, str]):
    portfolio_repository, goal_repository = _repos(tmp_path)
    portfolio = portfolio_repository.create_portfolio({"portfolio_id": "portfolio_1", "name": "Runtime portfolio"})
    for goal_id, status in statuses.items():
        goal = goal_repository.save_goal(
            {"goal_id": goal_id, "summary": goal_id, "status": "pending"}
        )
        if status in {"complete", "completed"}:
            goal["status"] = status
            goal_repository.update_goal(
                goal_id,
                {"status": status},
                completion_attestation=_attestation(goal_id, goal["goal_lineage"]),
            )
        elif status != "pending":
            goal_repository.update_goal(goal_id, {"status": status})
        portfolio_repository.add_goal_to_portfolio(portfolio["portfolio_id"], goal_id)
    return portfolio_repository, goal_repository


def test_select_next_goal_uses_first_runnable_goal_in_ref_order(tmp_path) -> None:
    portfolio_repository, goal_repository = _portfolio_with_goals(
        tmp_path,
        {"goal_done": "complete", "goal_blocked": "blocked", "goal_ready": "pending"},
    )

    selection = EngineeringPortfolioCoordinator(
        repo_root=tmp_path,
        portfolio_repository=portfolio_repository,
        goal_repository=goal_repository,
        goal_loop=FakeGoalLoop(),
    ).select_next_goal("portfolio_1")

    assert selection["schema"] == "zero.engineering_portfolio_coordinator.selection.v1"
    assert selection["ok"] is True
    assert selection["selected_goal_id"] == "goal_ready"
    assert [item["goal_id"] for item in selection["skipped_goals"]] == ["goal_done", "goal_blocked"]


def test_run_next_goal_delegates_to_goal_loop_and_records_complete_status(tmp_path) -> None:
    portfolio_repository, goal_repository = _portfolio_with_goals(tmp_path, {"goal_1": "pending"})
    loop = FakeGoalLoop(stop_reason="complete")

    result = EngineeringPortfolioCoordinator(
        repo_root=tmp_path,
        portfolio_repository=portfolio_repository,
        goal_repository=goal_repository,
        goal_loop=loop,
    ).run_next_goal("portfolio_1")

    assert result["schema"] == ENGINEERING_PORTFOLIO_COORDINATOR_SCHEMA
    assert result["ok"] is True
    assert result["selected_goal_id"] == "goal_1"
    assert loop.calls == [("goal_1", 3)]
    assert goal_repository.load_goal("goal_1")["status"] == "complete"


def test_blocked_goal_is_not_rerun_after_status_recorded(tmp_path) -> None:
    portfolio_repository, goal_repository = _portfolio_with_goals(tmp_path, {"goal_1": "pending"})
    loop = FakeGoalLoop(stop_reason="blocked")
    coordinator = EngineeringPortfolioCoordinator(
        repo_root=tmp_path,
        portfolio_repository=portfolio_repository,
        goal_repository=goal_repository,
        goal_loop=loop,
    )

    first = coordinator.run_next_goal("portfolio_1")
    second = coordinator.run_next_goal("portfolio_1")

    assert first["ok"] is False
    assert first["reason"] == "blocked"
    assert goal_repository.load_goal("goal_1")["status"] == "blocked"
    assert second["ok"] is False
    assert second["reason"] == "no_runnable_goal"
    assert loop.calls == [("goal_1", 3)]


def test_run_portfolio_cycle_stops_with_no_runnable_goal(tmp_path) -> None:
    portfolio_repository, goal_repository = _portfolio_with_goals(tmp_path, {"goal_1": "complete"})

    result = EngineeringPortfolioCoordinator(
        repo_root=tmp_path,
        portfolio_repository=portfolio_repository,
        goal_repository=goal_repository,
        goal_loop=FakeGoalLoop(),
    ).run_portfolio_cycle("portfolio_1")

    assert result["ok"] is False
    assert result["stop_reason"] == "no_runnable_goal"
    assert result["run_count"] == 0
    assert result["no_runnable_result"]["reason"] == "no_runnable_goal"


def test_summarize_portfolio_state_lists_runnable_terminal_and_missing_refs(tmp_path) -> None:
    portfolio_repository, goal_repository = _portfolio_with_goals(tmp_path, {"goal_1": "pending", "goal_2": "blocked"})
    portfolio_repository.add_goal_to_portfolio("portfolio_1", "missing_goal")

    summary = EngineeringPortfolioCoordinator(
        repo_root=tmp_path,
        portfolio_repository=portfolio_repository,
        goal_repository=goal_repository,
        goal_loop=FakeGoalLoop(),
    ).summarize_portfolio_state("portfolio_1")

    assert summary["ok"] is True
    assert summary["runnable_goal_ids"] == ["goal_1"]
    assert summary["terminal_goal_ids"] == ["goal_2"]
    assert summary["missing_goal_ids"] == ["missing_goal"]


def test_portfolio_coordinator_boundary_imports_only_allowed_owners() -> None:
    tree = ast.parse(COORDINATOR_FILE.read_text(encoding="utf-8"))
    imports: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
            for alias in node.names:
                imports.add(alias.name)

    forbidden = {
        "EngineeringRuntimeOrchestrator",
        "EngineeringGoalScheduler",
        "EngineeringAdaptivePlanner",
        "run_engineering_task",
        "core.tasks.scheduler",
        "core.tasks.engineering_runtime_orchestrator",
        "core.tasks.engineering_goal_scheduler",
    }
    required = {
        "EngineeringPortfolioRepository",
        "EngineeringGoalRepository",
        "EngineeringGoalLoop",
    }
    assert imports.isdisjoint(forbidden)
    assert required.issubset(imports)
