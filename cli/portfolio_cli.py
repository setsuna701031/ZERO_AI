from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Mapping

from core.tasks.engineering_goal_loop import EngineeringGoalLoop
from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.engineering_issue_reporter import EngineeringIssueReporter
from core.tasks.engineering_issue_summary import apply_engineering_issue_summary
from core.tasks.engineering_portfolio_coordinator import EngineeringPortfolioCoordinator
from core.tasks.engineering_portfolio_cycle import EngineeringPortfolioCycle
from core.tasks.engineering_portfolio_repository import EngineeringPortfolioRepository
from core.runtime.runtime_route_keys import RuntimeRouteKeys
from core.runtime.runtime_route_registry import default_runtime_route_registry


PORTFOLIO_CLI_SCHEMA = "zero.portfolio_cli.v1"


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=str))


def _run_via_mainline(repo_root: Path, *, entrypoint: str, runner: Any, goal: str, request: dict[str, Any] | None = None) -> Any:
    route_key = (
        RuntimeRouteKeys.CLI_PORTFOLIO_CYCLE
        if entrypoint.endswith(".cycle") or entrypoint.endswith(".run_until_idle")
        else RuntimeRouteKeys.CLI_PORTFOLIO_RUN
    )
    registry = default_runtime_route_registry()
    registry.register(
        route_key,
        lambda _request, _workspace_root, _goal: runner,
        {"entrypoint": entrypoint, "component": "portfolio_cli"},
    )
    return registry.run(
        route_key=route_key,
        request=request,
        workspace_root=_workspace_root(repo_root),
        goal=goal,
    )


def _workspace_dir() -> str:
    return os.environ.get("ZERO_WORKSPACE", "workspace")


def _workspace_root(repo_root: Path) -> Path:
    workspace = Path(_workspace_dir())
    if workspace.is_absolute():
        return workspace
    return repo_root / workspace


def _portfolio_store_path(repo_root: Path) -> Path:
    override = os.environ.get("ZERO_PORTFOLIO_STORE", "").strip()
    if override:
        path = Path(override)
        return path if path.is_absolute() else repo_root / path
    if os.environ.get("ZERO_WORKSPACE"):
        return _workspace_root(repo_root) / "engineering_portfolios.json"
    return repo_root / "runtime" / "portfolios" / "portfolios.json"


def _goal_store_path(repo_root: Path) -> Path:
    override = os.environ.get("ZERO_GOAL_STORE", "").strip()
    if override:
        path = Path(override)
        return path if path.is_absolute() else repo_root / path
    if os.environ.get("ZERO_WORKSPACE"):
        return _workspace_root(repo_root) / "engineering_goals.json"
    return repo_root / "runtime" / "goals" / "goals.json"


def _issue_store_path(repo_root: Path) -> Path:
    override = os.environ.get("ZERO_ISSUE_STORE", "").strip()
    if override:
        path = Path(override)
        return path if path.is_absolute() else repo_root / path
    if os.environ.get("ZERO_WORKSPACE"):
        return _workspace_root(repo_root) / "engineering_issues.json"
    return repo_root / "runtime" / "issues" / "issues.json"


def _issue_reporter(repo_root: Path) -> EngineeringIssueReporter:
    return EngineeringIssueReporter(repo_root, storage_path=_issue_store_path(repo_root))


def _portfolio_repository(repo_root: Path) -> EngineeringPortfolioRepository:
    return EngineeringPortfolioRepository(repo_root, storage_path=_portfolio_store_path(repo_root))


def _goal_repository(repo_root: Path) -> EngineeringGoalRepository:
    return EngineeringGoalRepository(repo_root, storage_path=_goal_store_path(repo_root))


def _coordinator(repo_root: Path) -> EngineeringPortfolioCoordinator:
    portfolio_repository = _portfolio_repository(repo_root)
    goal_repository = _goal_repository(repo_root)
    reporter = _issue_reporter(repo_root)
    return EngineeringPortfolioCoordinator(
        repo_root=repo_root,
        portfolio_repository=portfolio_repository,
        goal_repository=goal_repository,
        goal_loop=EngineeringGoalLoop(repo_root=repo_root, repository=goal_repository, issue_reporter=reporter),
    )


def _portfolio_cycle(repo_root: Path) -> EngineeringPortfolioCycle:
    portfolio_repository = _portfolio_repository(repo_root)
    goal_repository = _goal_repository(repo_root)
    reporter = _issue_reporter(repo_root)
    goal_loop = EngineeringGoalLoop(repo_root=repo_root, repository=goal_repository, issue_reporter=reporter)
    coordinator = EngineeringPortfolioCoordinator(
        repo_root=repo_root,
        portfolio_repository=portfolio_repository,
        goal_repository=goal_repository,
        goal_loop=goal_loop,
    )
    return EngineeringPortfolioCycle(
        repo_root=repo_root,
        portfolio_repository=portfolio_repository,
        goal_repository=goal_repository,
        goal_loop=goal_loop,
        coordinator=coordinator,
        issue_reporter=reporter,
    )


def _portfolio_summary(portfolio: Mapping[str, Any]) -> dict[str, Any]:
    goal_ids = portfolio.get("goal_ids") if isinstance(portfolio.get("goal_ids"), list) else []
    return {
        "portfolio_id": _clean_text(portfolio.get("portfolio_id")),
        "name": _clean_text(portfolio.get("name")),
        "goal_count": len(goal_ids),
        "goal_ids": copy.deepcopy(goal_ids),
    }


def _coordinator_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    loop_result = result.get("loop_result") if isinstance(result.get("loop_result"), Mapping) else {}
    cycles = loop_result.get("cycles") if isinstance(loop_result.get("cycles"), list) else []
    return {
        "schema": _clean_text(result.get("schema")),
        "ok": bool(result.get("ok")),
        "mode": _clean_text(result.get("mode")),
        "action": _clean_text(result.get("action")),
        "portfolio_id": _clean_text(result.get("portfolio_id")),
        "selected_goal_id": _clean_text(result.get("selected_goal_id")),
        "reason": _clean_text(result.get("reason")),
        "selection": copy.deepcopy(result.get("selection")) if isinstance(result.get("selection"), Mapping) else {},
        "loop_result": {
            "ok": bool(loop_result.get("ok")),
            "goal_id": _clean_text(loop_result.get("goal_id")),
            "terminal": bool(loop_result.get("terminal")),
            "stop_reason": _clean_text(loop_result.get("stop_reason")),
            "cycle_count": int(loop_result.get("cycle_count") or 0),
            "cycles": [
                {
                    "cycle_index": int(cycle.get("cycle_index") or 0),
                    "goal_id": _clean_text(cycle.get("goal_id")),
                    "runtime_state": _clean_text(cycle.get("runtime_state")),
                    "adaptive_decision": _clean_text(cycle.get("adaptive_decision")),
                    "adaptive_reason": _clean_text(cycle.get("adaptive_reason")),
                }
                for cycle in cycles
                if isinstance(cycle, Mapping)
            ],
        },
        "updated_goal": copy.deepcopy(result.get("updated_goal")) if isinstance(result.get("updated_goal"), Mapping) else {},
        "issues_found": copy.deepcopy(result.get("issues_found")) if isinstance(result.get("issues_found"), list) else [],
        "blocking_issues": copy.deepcopy(result.get("blocking_issues")) if isinstance(result.get("blocking_issues"), list) else [],
        "deferred_issues": copy.deepcopy(result.get("deferred_issues")) if isinstance(result.get("deferred_issues"), list) else [],
        "success_allowed": bool(result.get("success_allowed", True)),
    }


def _cycle_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    runs = result.get("runs") if isinstance(result.get("runs"), list) else []
    return {
        "schema": _clean_text(result.get("schema")),
        "ok": bool(result.get("ok")),
        "portfolio_id": _clean_text(result.get("portfolio_id")),
        "stop_reason": _clean_text(result.get("stop_reason")),
        "max_goals": result.get("max_goals"),
        "cycle_count": int(result.get("cycle_count") or len(runs)),
        "run_count": int(result.get("cycle_count") or len(runs)),
        "executed_goal_count": int(result.get("executed_goal_count") or 0),
        "completed_goal_count": int(result.get("completed_goal_count") or 0),
        "blocked_goal_count": int(result.get("blocked_goal_count") or 0),
        "skipped_goal_count": int(result.get("skipped_goal_count") or 0),
        "runs": [copy.deepcopy(dict(run)) for run in runs if isinstance(run, Mapping)],
        "portfolio_state": copy.deepcopy(result.get("portfolio_state")) if isinstance(result.get("portfolio_state"), Mapping) else {},
        "issues_found": copy.deepcopy(result.get("issues_found")) if isinstance(result.get("issues_found"), list) else [],
        "blocking_issues": copy.deepcopy(result.get("blocking_issues")) if isinstance(result.get("blocking_issues"), list) else [],
        "deferred_issues": copy.deepcopy(result.get("deferred_issues")) if isinstance(result.get("deferred_issues"), list) else [],
        "success_allowed": bool(result.get("success_allowed", True)),
    }


def _portfolio_state_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": _clean_text(result.get("schema")),
        "ok": bool(result.get("ok")),
        "portfolio_id": _clean_text(result.get("portfolio_id")),
        "state": _clean_text(result.get("state")),
        "goal_count": int(result.get("goal_count") or 0),
        "completed_goal_count": int(result.get("completed_goal_count") or 0),
        "blocked_goal_count": int(result.get("blocked_goal_count") or 0),
        "active_goal_count": int(result.get("active_goal_count") or 0),
        "completion_ratio": float(result.get("completion_ratio") or 0.0),
    }


def _portfolio_full_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    state_summary = result.get("portfolio_summary") if isinstance(result.get("portfolio_summary"), Mapping) else {}
    issue_fields = {
        "issues_found": copy.deepcopy(result.get("issues_found")) if isinstance(result.get("issues_found"), list) else [],
        "blocking_issues": copy.deepcopy(result.get("blocking_issues")) if isinstance(result.get("blocking_issues"), list) else [],
        "deferred_issues": copy.deepcopy(result.get("deferred_issues")) if isinstance(result.get("deferred_issues"), list) else [],
        "success_allowed": bool(result.get("success_allowed", True)),
    }
    if state_summary:
        summary = copy.deepcopy(dict(state_summary))
        summary.update(issue_fields)
        return summary
    summary = {
        "schema": _clean_text(result.get("schema")),
        "ok": bool(result.get("ok")),
        "portfolio_id": _clean_text(result.get("portfolio_id")),
        "state": _clean_text(result.get("state")),
        "progress": copy.deepcopy(result.get("progress")) if isinstance(result.get("progress"), Mapping) else {},
        "goals": copy.deepcopy(result.get("goals")) if isinstance(result.get("goals"), list) else [],
        "missing_goal_ids": copy.deepcopy(result.get("missing_goal_ids")) if isinstance(result.get("missing_goal_ids"), list) else [],
    }
    summary.update(issue_fields)
    return summary


def _handle_create(argv: list[str], repo_root: Path) -> bool:
    if len(argv) < 3 or argv[1] != "create":
        return False
    name = " ".join(argv[2:]).strip()
    portfolio = _portfolio_repository(repo_root).create_portfolio(
        {
            "name": name or "Untitled engineering portfolio",
            "metadata": {"source": "portfolio_cli"},
        }
    )
    _print_json({"schema": PORTFOLIO_CLI_SCHEMA, "ok": True, "created": True, "portfolio": portfolio})
    return True


def _handle_list(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 2 or argv[1] != "list":
        return False
    portfolios = _portfolio_repository(repo_root).list_portfolios()
    _print_json(
        {
            "schema": PORTFOLIO_CLI_SCHEMA,
            "ok": True,
            "portfolios": [_portfolio_summary(portfolio) for portfolio in portfolios],
        }
    )
    return True


def _handle_show(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 3 or argv[1] != "show":
        return False
    portfolio = _portfolio_repository(repo_root).load_portfolio(argv[2])
    _print_json({"schema": PORTFOLIO_CLI_SCHEMA, "ok": portfolio is not None, "portfolio_id": argv[2], "portfolio": portfolio or {}})
    return True


def _handle_add_goal(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 4 or argv[1] != "add-goal":
        return False
    portfolio_id = argv[2]
    goal_id = argv[3]
    if _goal_repository(repo_root).load_goal(goal_id) is None:
        _print_json({"schema": PORTFOLIO_CLI_SCHEMA, "ok": False, "error": "goal_not_found", "goal_id": goal_id, "portfolio_id": portfolio_id})
        return True
    try:
        portfolio = _portfolio_repository(repo_root).add_goal_to_portfolio(portfolio_id, goal_id)
    except KeyError:
        _print_json({"schema": PORTFOLIO_CLI_SCHEMA, "ok": False, "error": "portfolio_not_found", "portfolio_id": portfolio_id})
        return True
    _print_json({"schema": PORTFOLIO_CLI_SCHEMA, "ok": True, "portfolio": portfolio})
    return True


def _handle_remove_goal(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 4 or argv[1] != "remove-goal":
        return False
    portfolio_id = argv[2]
    goal_id = argv[3]
    try:
        portfolio = _portfolio_repository(repo_root).remove_goal_from_portfolio(portfolio_id, goal_id)
    except KeyError:
        _print_json({"schema": PORTFOLIO_CLI_SCHEMA, "ok": False, "error": "portfolio_not_found", "portfolio_id": portfolio_id})
        return True
    _print_json({"schema": PORTFOLIO_CLI_SCHEMA, "ok": True, "portfolio": portfolio})
    return True


def _handle_run_next(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 3 or argv[1] != "run-next":
        return False
    result = _run_via_mainline(
        repo_root,
        entrypoint="cli.portfolio_cli.run_next",
        runner=lambda: _coordinator(repo_root).run_next_goal(argv[2]),
        goal=argv[2],
        request={"command": "run-next", "portfolio_id": argv[2]},
    )
    result = apply_engineering_issue_summary(result, repo_root=repo_root, issue_reporter=_issue_reporter(repo_root))
    _print_json({"schema": PORTFOLIO_CLI_SCHEMA, "ok": bool(result.get("ok")), "coordinator_result": _coordinator_summary(result)})
    return True


def _handle_cycle(argv: list[str], repo_root: Path) -> bool:
    if len(argv) not in {3, 4} or argv[1] != "cycle":
        return False
    max_goals = 1
    if len(argv) == 4:
        try:
            max_goals = int(argv[3])
        except ValueError:
            _print_json({"schema": PORTFOLIO_CLI_SCHEMA, "ok": False, "error": "invalid_max_goals", "portfolio_id": argv[2]})
            return True
    cycle = _portfolio_cycle(repo_root)
    result = _run_via_mainline(
        repo_root,
        entrypoint="cli.portfolio_cli.cycle",
        runner=lambda: cycle.run_cycle(argv[2]) if len(argv) == 3 else cycle.run_until_idle(argv[2], max_goals=max_goals),
        goal=argv[2],
        request={"command": "cycle", "portfolio_id": argv[2], "max_goals": max_goals},
    )
    _print_json({"schema": PORTFOLIO_CLI_SCHEMA, "ok": bool(result.get("ok")), "cycle_summary": _cycle_summary(result)})
    return True


def _handle_run_until_idle(argv: list[str], repo_root: Path) -> bool:
    if len(argv) not in {3, 4} or argv[1] != "run-until-idle":
        return False
    max_goals = 5
    if len(argv) == 4:
        try:
            max_goals = int(argv[3])
        except ValueError:
            _print_json({"schema": PORTFOLIO_CLI_SCHEMA, "ok": False, "error": "invalid_max_goals", "portfolio_id": argv[2]})
            return True
    result = _run_via_mainline(
        repo_root,
        entrypoint="cli.portfolio_cli.run_until_idle",
        runner=lambda: _portfolio_cycle(repo_root).run_until_idle(argv[2], max_goals=max_goals),
        goal=argv[2],
        request={"command": "run-until-idle", "portfolio_id": argv[2], "max_goals": max_goals},
    )
    _print_json({"schema": PORTFOLIO_CLI_SCHEMA, "ok": bool(result.get("ok")), "cycle_summary": _cycle_summary(result)})
    return True


def _handle_state(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 3 or argv[1] != "state":
        return False
    result = _coordinator(repo_root).read_portfolio_state(argv[2])
    _print_json({"schema": PORTFOLIO_CLI_SCHEMA, "ok": bool(result.get("ok")), "portfolio_state": _portfolio_state_summary(result)})
    return True


def _handle_summary(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 3 or argv[1] != "summary":
        return False
    result = _coordinator(repo_root).summarize_portfolio_state(argv[2])
    result = apply_engineering_issue_summary(result, repo_root=repo_root, issue_reporter=_issue_reporter(repo_root))
    _print_json({"schema": PORTFOLIO_CLI_SCHEMA, "ok": bool(result.get("ok")), "portfolio_summary": _portfolio_full_summary(result)})
    return True


def try_handle_portfolio_command(argv: list[str], *, repo_root: Path) -> bool:
    clean_argv = [str(item).strip() for item in argv if str(item).strip()]
    if not clean_argv or clean_argv[0].lower() != "portfolio":
        return False
    normalized = [clean_argv[0].lower(), *[item.lower() if index == 1 else item for index, item in enumerate(clean_argv[1:], start=1)]]

    for handler in (
        _handle_create,
        _handle_list,
        _handle_show,
        _handle_add_goal,
        _handle_remove_goal,
        _handle_state,
        _handle_summary,
        _handle_run_next,
        _handle_cycle,
        _handle_run_until_idle,
    ):
        if handler(normalized, repo_root):
            return True

    _print_json({"schema": PORTFOLIO_CLI_SCHEMA, "ok": False, "error": "unknown_portfolio_command"})
    return True


__all__ = ["PORTFOLIO_CLI_SCHEMA", "try_handle_portfolio_command"]
