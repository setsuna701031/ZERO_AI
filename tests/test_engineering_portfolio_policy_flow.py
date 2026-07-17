from __future__ import annotations

import ast
from pathlib import Path

from core.evidence import EvidenceRecord, EvidenceValidator
from core.goals.goal_completion_authority import GoalCompletionAuthority
from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.engineering_portfolio_coordinator import EngineeringPortfolioCoordinator
from core.tasks.engineering_portfolio_cycle import EngineeringPortfolioCycle
from core.tasks.engineering_portfolio_repository import EngineeringPortfolioRepository


REPO_ROOT = Path(__file__).resolve().parents[1]
COORDINATOR_FILE = REPO_ROOT / "core/tasks/engineering_portfolio_coordinator.py"
CYCLE_FILE = REPO_ROOT / "core/tasks/engineering_portfolio_cycle.py"


def _attestation(goal_id: str, goal_lineage=None):
    evidence = EvidenceValidator().validate(
        EvidenceRecord("seed-e", goal_id, None, "test", "ok", "now", metadata=goal_lineage or {})
    )
    return GoalCompletionAuthority().complete_goal(
        goal_id=goal_id,
        evidence_refs=[evidence],
        all_subgoals_completed=True,
        goal_lineage=goal_lineage,
    )


class FakePolicy:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def select_next_goal(self, goals: list[dict]) -> dict:
        self.calls.append([goal["goal_id"] for goal in goals])
        selected = goals[-1]
        return {
            "ok": True,
            "decision": "selected",
            "reason": "fake_policy_selected",
            "selected_goal_id": selected["goal_id"],
            "selected_goal": selected,
            "skipped_goals": [{"goal_id": goals[0]["goal_id"], "reason": "fake_skip"}],
            "selection_summary": {"selected_goal_id": selected["goal_id"], "policy": "fake"},
        }

    def is_runnable_goal(self, goal: dict) -> bool:
        return goal.get("status") in {"active", "pending", "in_progress"}


class FakeGoalLoop:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def run_until_terminal(self, goal_id: str, max_cycles: int = 3, *, goal_lineage=None) -> dict:
        self.calls.append(goal_id)
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
            "ok": True,
            "goal_id": goal_id,
            "terminal": True,
            "stop_reason": "complete",
            "cycle_count": 1,
            "cycles": [{"adaptive_decision": "complete", "goal_completion_attestation": attestation}],
        }


def _repos(tmp_path: Path, statuses: dict[str, str]):
    portfolio_repository = EngineeringPortfolioRepository(tmp_path)
    goal_repository = EngineeringGoalRepository(tmp_path)
    portfolio_repository.create_portfolio({"portfolio_id": "portfolio_1", "name": "Policy portfolio"})
    for goal_id, status in statuses.items():
        if status in {"complete", "completed"}:
            goal = goal_repository.save_goal({"goal_id": goal_id, "summary": goal_id, "status": "pending"})
            goal_repository.update_goal(
                goal_id,
                {"status": status},
                completion_attestation=_attestation(goal_id, goal["goal_lineage"]),
            )
        else:
            goal_repository.save_goal({"goal_id": goal_id, "summary": goal_id, "status": status})
        portfolio_repository.add_goal_to_portfolio("portfolio_1", goal_id)
    return portfolio_repository, goal_repository


def test_coordinator_delegates_selection_to_policy(tmp_path) -> None:
    portfolio_repository, goal_repository = _repos(tmp_path, {"goal_1": "pending", "goal_2": "pending"})
    policy = FakePolicy()

    selection = EngineeringPortfolioCoordinator(
        repo_root=tmp_path,
        portfolio_repository=portfolio_repository,
        goal_repository=goal_repository,
        goal_loop=FakeGoalLoop(),
        portfolio_policy=policy,
    ).select_next_goal("portfolio_1")

    assert policy.calls == [["goal_1", "goal_2"]]
    assert selection["selected_goal_id"] == "goal_2"
    assert selection["reason"] == "fake_policy_selected"
    assert selection["selection_summary"] == {"selected_goal_id": "goal_2", "policy": "fake"}
    assert selection["execution_path"]["portfolio_policy_used"] is True


def test_policy_flow_skips_terminal_and_paused_goals_in_ref_order(tmp_path) -> None:
    portfolio_repository, goal_repository = _repos(
        tmp_path,
        {
            "done": "completed",
            "blocked": "blocked",
            "cancelled": "cancelled",
            "paused": "paused",
            "ready": "in_progress",
            "later": "active",
        },
    )

    selection = EngineeringPortfolioCoordinator(
        repo_root=tmp_path,
        portfolio_repository=portfolio_repository,
        goal_repository=goal_repository,
        goal_loop=FakeGoalLoop(),
    ).select_next_goal("portfolio_1")

    assert selection["selected_goal_id"] == "ready"
    assert [item["goal_id"] for item in selection["skipped_goals"]] == ["done", "blocked", "cancelled", "paused"]
    assert [item["reason"] for item in selection["skipped_goals"]] == [
        "completed_goal",
        "blocked_goal",
        "cancelled_goal",
        "paused_goal",
    ]
    assert selection["selection_summary"]["runnable_goal_ids"] == ["ready", "later"]


def test_cycle_uses_coordinator_selection_without_goal_policy_checks(tmp_path) -> None:
    portfolio_repository, goal_repository = _repos(tmp_path, {"goal_1": "pending"})
    goal_loop = FakeGoalLoop()
    coordinator = EngineeringPortfolioCoordinator(
        repo_root=tmp_path,
        portfolio_repository=portfolio_repository,
        goal_repository=goal_repository,
        goal_loop=goal_loop,
    )

    result = EngineeringPortfolioCycle(
        repo_root=tmp_path,
        portfolio_repository=portfolio_repository,
        goal_repository=goal_repository,
        goal_loop=goal_loop,
        coordinator=coordinator,
    ).run_until_idle("portfolio_1", max_goals=1)

    assert result["cycle_count"] == 1
    assert result["selections"][0]["selection_summary"]["selected_goal_id"] == "goal_1"
    assert goal_loop.calls == ["goal_1"]


def test_coordinator_imports_policy_and_has_no_embedded_terminal_status_table() -> None:
    source = COORDINATOR_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
            for alias in node.names:
                imports.add(alias.name)

    assert "EngineeringPortfolioPolicy" in imports
    assert "core.tasks.engineering_portfolio_policy" in imports
    assert "TERMINAL_GOAL_STATUSES" not in source
    assert "terminal_goal_status" not in source
    assert "status in" not in source


def test_cycle_does_not_directly_classify_goal_runnability() -> None:
    source = CYCLE_FILE.read_text(encoding="utf-8")

    assert "is_runnable_goal" not in source
    assert "classify_goal_state" not in source
    assert "explain_skip_reason" not in source
    assert "TERMINAL_GOAL_STATUSES" not in source
