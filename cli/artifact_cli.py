from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from core.tasks.engineering_artifact_repository import EngineeringArtifactRepository
from core.tasks.engineering_artifact_state import EngineeringArtifactState


ARTIFACT_CLI_SCHEMA = "zero.artifact_cli.v1"


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


def _artifact_store_path(repo_root: Path) -> Path:
    override = os.environ.get("ZERO_ARTIFACT_STORE", "").strip()
    if override:
        path = Path(override)
        return path if path.is_absolute() else repo_root / path
    if os.environ.get("ZERO_WORKSPACE"):
        return _workspace_root(repo_root) / "engineering_artifacts.json"
    return repo_root / "runtime" / "artifacts" / "artifacts.json"


def _repository(repo_root: Path) -> EngineeringArtifactRepository:
    return EngineeringArtifactRepository(repo_root, storage_path=_artifact_store_path(repo_root))


def _artifact_state(repo_root: Path) -> EngineeringArtifactState:
    return EngineeringArtifactState(repo_root, artifact_repository=_repository(repo_root))


def _handle_state(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 2 or argv[1] != "state":
        return False
    result = _artifact_state(repo_root).evaluate_artifact_state()
    _print_json({"schema": ARTIFACT_CLI_SCHEMA, "ok": bool(result.get("ok")), "artifact_state": result})
    return True


def _handle_summary(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 2 or argv[1] != "summary":
        return False
    result = _artifact_state(repo_root).summarize_artifacts()
    _print_json(
        {
            "schema": ARTIFACT_CLI_SCHEMA,
            "ok": bool(result.get("ok")),
            "artifact_summary": result,
            "policy_summary": result.get("policy_summary") or {},
        }
    )
    return True


def _handle_list_goal(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 3 or argv[1] != "list-goal":
        return False
    artifacts = _repository(repo_root).list_goal_artifacts(argv[2])
    _print_json({"schema": ARTIFACT_CLI_SCHEMA, "ok": True, "goal_id": argv[2], "artifacts": artifacts})
    return True


def _handle_list_portfolio(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 3 or argv[1] != "list-portfolio":
        return False
    artifacts = _repository(repo_root).list_portfolio_artifacts(argv[2])
    _print_json({"schema": ARTIFACT_CLI_SCHEMA, "ok": True, "portfolio_id": argv[2], "artifacts": artifacts})
    return True


def _handle_list_program(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 3 or argv[1] != "list-program":
        return False
    artifacts = _repository(repo_root).list_program_artifacts(argv[2])
    _print_json({"schema": ARTIFACT_CLI_SCHEMA, "ok": True, "program_id": argv[2], "artifacts": artifacts})
    return True


def _handle_show(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 3 or argv[1] != "show":
        return False
    artifact = _repository(repo_root).get_artifact(argv[2])
    _print_json({"schema": ARTIFACT_CLI_SCHEMA, "ok": artifact is not None, "artifact_id": argv[2], "artifact": artifact or {}})
    return True


def try_handle_artifact_command(argv: list[str], *, repo_root: Path) -> bool:
    clean_argv = [str(item).strip() for item in argv if str(item).strip()]
    if not clean_argv or clean_argv[0].lower() != "artifact":
        return False
    normalized = [clean_argv[0].lower(), *[item.lower() if index == 1 else item for index, item in enumerate(clean_argv[1:], start=1)]]

    for handler in (
        _handle_state,
        _handle_summary,
        _handle_list_goal,
        _handle_list_portfolio,
        _handle_list_program,
        _handle_show,
    ):
        if handler(normalized, repo_root):
            return True

    _print_json({"schema": ARTIFACT_CLI_SCHEMA, "ok": False, "error": "unknown_artifact_command"})
    return True


__all__ = ["ARTIFACT_CLI_SCHEMA", "try_handle_artifact_command"]
