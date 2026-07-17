from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from core.tasks.engineering_issue_reporter import EngineeringIssueReporter


ISSUE_CLI_SCHEMA = "zero.issue_cli.v1"


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=str))


def _workspace_dir() -> str:
    return os.environ.get("ZERO_WORKSPACE", "workspace")


def _workspace_root(repo_root: Path) -> Path:
    workspace = Path(_workspace_dir())
    if workspace.is_absolute():
        return workspace
    return repo_root / workspace


def _issue_store_path(repo_root: Path) -> Path:
    override = os.environ.get("ZERO_ISSUE_STORE", "").strip()
    if override:
        path = Path(override)
        return path if path.is_absolute() else repo_root / path
    if os.environ.get("ZERO_WORKSPACE"):
        return _workspace_root(repo_root) / "engineering_issues.json"
    return repo_root / "runtime" / "issues" / "issues.json"


def _reporter(repo_root: Path) -> EngineeringIssueReporter:
    return EngineeringIssueReporter(repo_root, storage_path=_issue_store_path(repo_root))


def _handle_list(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 2 or argv[1] != "list":
        return False
    reporter = _reporter(repo_root)
    _print_json({"schema": ISSUE_CLI_SCHEMA, "ok": True, "issues": reporter.list_issues(), "summary": reporter.build_summary()})
    return True


def _handle_show(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 3 or argv[1] != "show":
        return False
    issue = _reporter(repo_root).get_issue(argv[2])
    _print_json({"schema": ISSUE_CLI_SCHEMA, "ok": issue is not None, "issue_id": argv[2], "issue": issue or {}})
    return True


def _handle_summary(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 2 or argv[1] != "summary":
        return False
    summary = _reporter(repo_root).build_summary()
    _print_json({"schema": ISSUE_CLI_SCHEMA, "ok": bool(summary.get("ok")), "issue_summary": summary})
    return True


def try_handle_issue_command(argv: list[str], *, repo_root: Path) -> bool:
    clean_argv = [str(item).strip() for item in argv if str(item).strip()]
    if not clean_argv or clean_argv[0].lower() != "issue":
        return False
    normalized = [clean_argv[0].lower(), *[item.lower() if index == 1 else item for index, item in enumerate(clean_argv[1:], start=1)]]

    for handler in (_handle_list, _handle_show, _handle_summary):
        if handler(normalized, repo_root):
            return True

    _print_json({"schema": ISSUE_CLI_SCHEMA, "ok": False, "error": "unknown_issue_command"})
    return True


__all__ = ["ISSUE_CLI_SCHEMA", "try_handle_issue_command"]
