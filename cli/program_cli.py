from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Mapping

from core.tasks.engineering_portfolio_cycle import EngineeringPortfolioCycle
from core.tasks.engineering_portfolio_repository import EngineeringPortfolioRepository
from core.tasks.engineering_program_coordinator import EngineeringProgramCoordinator
from core.tasks.engineering_program_cycle import EngineeringProgramCycle
from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.engineering_issue_reporter import EngineeringIssueReporter
from core.tasks.engineering_issue_summary import apply_engineering_issue_summary
from core.tasks.engineering_program_observability import EngineeringProgramObservability
from core.tasks.engineering_program_repository import EngineeringProgramRepository
from core.tasks.engineering_program_state import EngineeringProgramState
from core.runtime.runtime_route_keys import RuntimeRouteKeys
from core.runtime.runtime_route_registry import default_runtime_route_registry


PROGRAM_CLI_SCHEMA = "zero.program_cli.v1"


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=str))


def _run_via_mainline(repo_root: Path, *, entrypoint: str, runner: Any, goal: str, request: dict[str, Any] | None = None) -> Any:
    route_key = (
        RuntimeRouteKeys.CLI_PROGRAM_CYCLE
        if entrypoint.endswith(".cycle") or entrypoint.endswith(".run_until_idle")
        else RuntimeRouteKeys.CLI_PROGRAM_RUN
    )
    registry = default_runtime_route_registry()
    registry.register(
        route_key,
        lambda _request, _workspace_root, _goal: runner,
        {"entrypoint": entrypoint, "component": "program_cli"},
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


def _program_store_path(repo_root: Path) -> Path:
    override = os.environ.get("ZERO_PROGRAM_STORE", "").strip()
    if override:
        path = Path(override)
        return path if path.is_absolute() else repo_root / path
    if os.environ.get("ZERO_WORKSPACE"):
        return _workspace_root(repo_root) / "engineering_programs.json"
    return repo_root / "runtime" / "programs" / "programs.json"


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


def _program_repository(repo_root: Path) -> EngineeringProgramRepository:
    return EngineeringProgramRepository(repo_root, storage_path=_program_store_path(repo_root))


def _portfolio_repository(repo_root: Path) -> EngineeringPortfolioRepository:
    return EngineeringPortfolioRepository(repo_root, storage_path=_portfolio_store_path(repo_root))


def _goal_repository(repo_root: Path) -> EngineeringGoalRepository:
    return EngineeringGoalRepository(repo_root, storage_path=_goal_store_path(repo_root))


def _program_coordinator(repo_root: Path) -> EngineeringProgramCoordinator:
    portfolio_repository = _portfolio_repository(repo_root)
    reporter = _issue_reporter(repo_root)
    return EngineeringProgramCoordinator(
        repo_root=repo_root,
        program_repository=_program_repository(repo_root),
        portfolio_repository=portfolio_repository,
        portfolio_cycle=EngineeringPortfolioCycle(
            repo_root=repo_root,
            portfolio_repository=portfolio_repository,
            issue_reporter=reporter,
        ),
    )


def _program_cycle(repo_root: Path) -> EngineeringProgramCycle:
    portfolio_repository = _portfolio_repository(repo_root)
    program_repository = _program_repository(repo_root)
    reporter = _issue_reporter(repo_root)
    portfolio_cycle = EngineeringPortfolioCycle(
        repo_root=repo_root,
        portfolio_repository=portfolio_repository,
        issue_reporter=reporter,
    )
    program_state = EngineeringProgramState(
        repo_root,
        program_repository=program_repository,
        portfolio_repository=portfolio_repository,
    )
    coordinator = EngineeringProgramCoordinator(
        repo_root=repo_root,
        program_repository=program_repository,
        portfolio_repository=portfolio_repository,
        program_state=program_state,
        portfolio_cycle=portfolio_cycle,
    )
    return EngineeringProgramCycle(
        repo_root=repo_root,
        program_repository=program_repository,
        portfolio_repository=portfolio_repository,
        portfolio_cycle=portfolio_cycle,
        program_state=program_state,
        coordinator=coordinator,
        issue_reporter=reporter,
    )


def _program_state(repo_root: Path) -> EngineeringProgramState:
    return EngineeringProgramState(
        repo_root,
        program_repository=_program_repository(repo_root),
        portfolio_repository=_portfolio_repository(repo_root),
    )


def _program_observability(repo_root: Path) -> EngineeringProgramObservability:
    program_repository = _program_repository(repo_root)
    portfolio_repository = _portfolio_repository(repo_root)
    return EngineeringProgramObservability(
        repo_root,
        program_repository=program_repository,
        portfolio_repository=portfolio_repository,
        goal_repository=_goal_repository(repo_root),
        program_state=EngineeringProgramState(
            repo_root,
            program_repository=program_repository,
            portfolio_repository=portfolio_repository,
        ),
    )


def _program_summary(program: Mapping[str, Any]) -> dict[str, Any]:
    portfolio_ids = program.get("portfolio_ids") if isinstance(program.get("portfolio_ids"), list) else []
    return {
        "program_id": _clean_text(program.get("program_id")),
        "name": _clean_text(program.get("name")),
        "portfolio_count": len(portfolio_ids),
        "portfolio_ids": copy.deepcopy(portfolio_ids),
    }


def _cycle_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    runs = result.get("runs") if isinstance(result.get("runs"), list) else []
    return {
        "schema": _clean_text(result.get("schema")),
        "ok": bool(result.get("ok")),
        "program_id": _clean_text(result.get("program_id")),
        "stop_reason": _clean_text(result.get("stop_reason")),
        "max_portfolios": result.get("max_portfolios"),
        "cycle_count": int(result.get("cycle_count") or len(runs)),
        "run_count": int(result.get("cycle_count") or len(runs)),
        "executed_portfolio_count": int(result.get("executed_portfolio_count") or 0),
        "completed_portfolio_count": int(result.get("completed_portfolio_count") or 0),
        "blocked_portfolio_count": int(result.get("blocked_portfolio_count") or 0),
        "skipped_portfolio_count": int(result.get("skipped_portfolio_count") or 0),
        "runs": [copy.deepcopy(dict(run)) for run in runs if isinstance(run, Mapping)],
        "program_state": copy.deepcopy(result.get("program_state")) if isinstance(result.get("program_state"), Mapping) else {},
        "issues_found": copy.deepcopy(result.get("issues_found")) if isinstance(result.get("issues_found"), list) else [],
        "blocking_issues": copy.deepcopy(result.get("blocking_issues")) if isinstance(result.get("blocking_issues"), list) else [],
        "deferred_issues": copy.deepcopy(result.get("deferred_issues")) if isinstance(result.get("deferred_issues"), list) else [],
        "success_allowed": bool(result.get("success_allowed", True)),
    }


def _handle_create(argv: list[str], repo_root: Path) -> bool:
    if len(argv) < 3 or argv[1] != "create":
        return False
    name = " ".join(argv[2:]).strip()
    program = _program_repository(repo_root).create_program({"name": name or "Untitled engineering program"})
    _print_json({"schema": PROGRAM_CLI_SCHEMA, "ok": True, "created": True, "program": program})
    return True


def _handle_list(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 2 or argv[1] != "list":
        return False
    programs = _program_repository(repo_root).list_programs()
    _print_json({"schema": PROGRAM_CLI_SCHEMA, "ok": True, "programs": [_program_summary(program) for program in programs]})
    return True


def _handle_show(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 3 or argv[1] != "show":
        return False
    program = _program_repository(repo_root).load_program(argv[2])
    _print_json({"schema": PROGRAM_CLI_SCHEMA, "ok": program is not None, "program_id": argv[2], "program": program or {}})
    return True


def _handle_add_portfolio(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 4 or argv[1] != "add-portfolio":
        return False
    program_id = argv[2]
    portfolio_id = argv[3]
    try:
        program = _program_repository(repo_root).add_portfolio(program_id, portfolio_id)
    except KeyError:
        _print_json({"schema": PROGRAM_CLI_SCHEMA, "ok": False, "error": "program_not_found", "program_id": program_id})
        return True
    _print_json({"schema": PROGRAM_CLI_SCHEMA, "ok": True, "program": program})
    return True


def _handle_remove_portfolio(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 4 or argv[1] != "remove-portfolio":
        return False
    program_id = argv[2]
    portfolio_id = argv[3]
    try:
        program = _program_repository(repo_root).remove_portfolio(program_id, portfolio_id)
    except KeyError:
        _print_json({"schema": PROGRAM_CLI_SCHEMA, "ok": False, "error": "program_not_found", "program_id": program_id})
        return True
    _print_json({"schema": PROGRAM_CLI_SCHEMA, "ok": True, "program": program})
    return True


def _handle_run_next(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 3 or argv[1] != "run-next":
        return False
    result = _run_via_mainline(
        repo_root,
        entrypoint="cli.program_cli.run_next",
        runner=lambda: _program_coordinator(repo_root).run_next_portfolio(argv[2]),
        goal=argv[2],
        request={"command": "run-next", "program_id": argv[2]},
    )
    result = apply_engineering_issue_summary(result, repo_root=repo_root, issue_reporter=_issue_reporter(repo_root))
    _print_json({"schema": PROGRAM_CLI_SCHEMA, "ok": bool(result.get("ok")), "program_run": result})
    return True


def _handle_cycle(argv: list[str], repo_root: Path) -> bool:
    if len(argv) not in {3, 4} or argv[1] != "cycle":
        return False
    max_portfolios = 1
    if len(argv) == 4:
        try:
            max_portfolios = int(argv[3])
        except ValueError:
            _print_json({"schema": PROGRAM_CLI_SCHEMA, "ok": False, "error": "invalid_max_portfolios", "program_id": argv[2]})
            return True
    result = _run_via_mainline(
        repo_root,
        entrypoint="cli.program_cli.cycle",
        runner=lambda: _program_coordinator(repo_root).run_program_cycle(argv[2], max_portfolios=max_portfolios),
        goal=argv[2],
        request={"command": "cycle", "program_id": argv[2], "max_portfolios": max_portfolios},
    )
    result = apply_engineering_issue_summary(result, repo_root=repo_root, issue_reporter=_issue_reporter(repo_root))
    _print_json({"schema": PROGRAM_CLI_SCHEMA, "ok": bool(result.get("ok")), "program_cycle": result})
    return True


def _handle_run_until_idle(argv: list[str], repo_root: Path) -> bool:
    if len(argv) not in {3, 4} or argv[1] != "run-until-idle":
        return False
    max_portfolios = 5
    if len(argv) == 4:
        try:
            max_portfolios = int(argv[3])
        except ValueError:
            _print_json({"schema": PROGRAM_CLI_SCHEMA, "ok": False, "error": "invalid_max_portfolios", "program_id": argv[2]})
            return True
    result = _run_via_mainline(
        repo_root,
        entrypoint="cli.program_cli.run_until_idle",
        runner=lambda: _program_cycle(repo_root).run_until_idle(argv[2], max_portfolios=max_portfolios),
        goal=argv[2],
        request={"command": "run-until-idle", "program_id": argv[2], "max_portfolios": max_portfolios},
    )
    _print_json({"schema": PROGRAM_CLI_SCHEMA, "ok": bool(result.get("ok")), "program_cycle": _cycle_summary(result)})
    return True


def _handle_state(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 3 or argv[1] != "state":
        return False
    result = _program_state(repo_root).evaluate_program_state(argv[2])
    _print_json({"schema": PROGRAM_CLI_SCHEMA, "ok": bool(result.get("ok")), "program_state": result})
    return True


def _handle_summary(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 3 or argv[1] != "summary":
        return False
    result = _program_state(repo_root).summarize_program(argv[2])
    result = apply_engineering_issue_summary(result, repo_root=repo_root, issue_reporter=_issue_reporter(repo_root))
    _print_json({"schema": PROGRAM_CLI_SCHEMA, "ok": bool(result.get("ok")), "program_summary": result})
    return True


def _handle_tree(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 3 or argv[1] != "tree":
        return False
    result = _program_observability(repo_root).build_program_tree_summary(argv[2])
    _print_json({"schema": PROGRAM_CLI_SCHEMA, "ok": bool(result.get("ok")), "program_tree": result})
    return True


def _handle_observability(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 3 or argv[1] != "observability":
        return False
    result = _program_observability(repo_root).calculate_rollup_metrics(argv[2])
    _print_json({"schema": PROGRAM_CLI_SCHEMA, "ok": bool(result.get("ok")), "program_observability": result})
    return True


def try_handle_program_command(argv: list[str], *, repo_root: Path) -> bool:
    clean_argv = [str(item).strip() for item in argv if str(item).strip()]
    if not clean_argv or clean_argv[0].lower() != "program":
        return False
    normalized = [clean_argv[0].lower(), *[item.lower() if index == 1 else item for index, item in enumerate(clean_argv[1:], start=1)]]

    for handler in (
        _handle_create,
        _handle_list,
        _handle_show,
        _handle_add_portfolio,
        _handle_remove_portfolio,
        _handle_run_next,
        _handle_cycle,
        _handle_run_until_idle,
        _handle_state,
        _handle_summary,
        _handle_tree,
        _handle_observability,
    ):
        if handler(normalized, repo_root):
            return True

    _print_json({"schema": PROGRAM_CLI_SCHEMA, "ok": False, "error": "unknown_program_command"})
    return True


__all__ = ["PROGRAM_CLI_SCHEMA", "try_handle_program_command"]
