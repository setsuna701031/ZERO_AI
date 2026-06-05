from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Mapping

from core.tasks.engineering_program_repository import EngineeringProgramRepository


PROGRAM_CLI_SCHEMA = "zero.program_cli.v1"


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


def _program_store_path(repo_root: Path) -> Path:
    override = os.environ.get("ZERO_PROGRAM_STORE", "").strip()
    if override:
        path = Path(override)
        return path if path.is_absolute() else repo_root / path
    if os.environ.get("ZERO_WORKSPACE"):
        return _workspace_root(repo_root) / "engineering_programs.json"
    return repo_root / "runtime" / "programs" / "programs.json"


def _program_repository(repo_root: Path) -> EngineeringProgramRepository:
    return EngineeringProgramRepository(repo_root, storage_path=_program_store_path(repo_root))


def _program_summary(program: Mapping[str, Any]) -> dict[str, Any]:
    portfolio_ids = program.get("portfolio_ids") if isinstance(program.get("portfolio_ids"), list) else []
    return {
        "program_id": _clean_text(program.get("program_id")),
        "name": _clean_text(program.get("name")),
        "portfolio_count": len(portfolio_ids),
        "portfolio_ids": copy.deepcopy(portfolio_ids),
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
    ):
        if handler(normalized, repo_root):
            return True

    _print_json({"schema": PROGRAM_CLI_SCHEMA, "ok": False, "error": "unknown_program_command"})
    return True


__all__ = ["PROGRAM_CLI_SCHEMA", "try_handle_program_command"]
