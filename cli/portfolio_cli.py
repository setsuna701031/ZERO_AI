from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Mapping

from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.engineering_portfolio_repository import EngineeringPortfolioRepository


PORTFOLIO_CLI_SCHEMA = "zero.portfolio_cli.v1"


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=str))


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


def _portfolio_repository(repo_root: Path) -> EngineeringPortfolioRepository:
    return EngineeringPortfolioRepository(repo_root, storage_path=_portfolio_store_path(repo_root))


def _goal_repository(repo_root: Path) -> EngineeringGoalRepository:
    return EngineeringGoalRepository(repo_root, storage_path=_goal_store_path(repo_root))


def _portfolio_summary(portfolio: Mapping[str, Any]) -> dict[str, Any]:
    goal_ids = portfolio.get("goal_ids") if isinstance(portfolio.get("goal_ids"), list) else []
    return {
        "portfolio_id": _clean_text(portfolio.get("portfolio_id")),
        "name": _clean_text(portfolio.get("name")),
        "goal_count": len(goal_ids),
        "goal_ids": copy.deepcopy(goal_ids),
    }


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
    ):
        if handler(normalized, repo_root):
            return True

    _print_json({"schema": PORTFOLIO_CLI_SCHEMA, "ok": False, "error": "unknown_portfolio_command"})
    return True


__all__ = ["PORTFOLIO_CLI_SCHEMA", "try_handle_portfolio_command"]
