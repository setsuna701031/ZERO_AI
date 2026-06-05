from __future__ import annotations

import os
import runpy
import sys
import json
from pathlib import Path
from typing import Any, Callable, List

from core.tasks.runtime_state_hygiene import make_json_safe


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def _legacy_app_path() -> Path:
    override = os.environ.get("ZERO_LEGACY_APP", "").strip()
    if override:
        return Path(override).resolve(strict=False)
    return _repo_root() / "app_legacy.py"


def _load_task_cli() -> Callable[..., bool]:
    from cli.task_cli import try_handle_fast_task_command

    return try_handle_fast_task_command


def _load_runtime_cli() -> Callable[..., bool]:
    from cli.runtime_cli import try_handle_fast_runtime_command

    return try_handle_fast_runtime_command


def _load_goal_cli() -> Callable[..., bool]:
    from cli.goal_cli import try_handle_goal_command

    return try_handle_goal_command


def _load_portfolio_cli() -> Callable[..., bool]:
    from cli.portfolio_cli import try_handle_portfolio_command

    return try_handle_portfolio_command


def _load_program_cli() -> Callable[..., bool]:
    from cli.program_cli import try_handle_program_command

    return try_handle_program_command


def _load_artifact_cli() -> Callable[..., bool]:
    from cli.artifact_cli import try_handle_artifact_command

    return try_handle_artifact_command


def _load_evidence_cli() -> Callable[..., bool]:
    from cli.evidence_cli import try_handle_evidence_command

    return try_handle_evidence_command


def _load_issue_cli() -> Callable[..., bool]:
    from cli.issue_cli import try_handle_issue_command

    return try_handle_issue_command


def _is_help_command(argv: List[str]) -> bool:
    normalized = [str(item).strip().lower() for item in argv if str(item).strip()]
    return len(normalized) == 1 and normalized[0] in {"--help", "-h", "help", "/help"}


def _print_thin_help() -> None:
    print("ZERO CLI")
    print("")
    print("Fast commands:")
    print("  python app.py --help")
    print("  python app.py task list")
    print("  python app.py task run [count]")
    print("  python app.py goal list")
    print("  python app.py goal add <summary>")
    print("  python app.py goal show <goal_id>")
    print("  python app.py goal run <goal_id>")
    print("  python app.py goal loop <goal_id>")
    print("  python app.py goal run-next")
    print("  python app.py program create <name>")
    print("  python app.py program list")
    print("  python app.py program show <program_id>")
    print("  python app.py program add-portfolio <program_id> <portfolio_id>")
    print("  python app.py program remove-portfolio <program_id> <portfolio_id>")
    print("  python app.py program run-next <program_id>")
    print("  python app.py program cycle <program_id>")
    print("  python app.py program run-until-idle <program_id>")
    print("  python app.py program state <program_id>")
    print("  python app.py program summary <program_id>")
    print("  python app.py program tree <program_id>")
    print("  python app.py program observability <program_id>")
    print("  python app.py artifact list-goal <goal_id>")
    print("  python app.py artifact list-portfolio <portfolio_id>")
    print("  python app.py artifact list-program <program_id>")
    print("  python app.py artifact show <artifact_id>")
    print("  python app.py artifact state")
    print("  python app.py artifact summary")
    print("  python app.py evidence create <name> [--artifact <artifact_id>] [--goal <goal_id>]")
    print("  python app.py evidence list")
    print("  python app.py evidence show <evidence_id>")
    print("  python app.py evidence summary")
    print("  python app.py evidence state")
    print("  python app.py evidence list-artifact <artifact_id>")
    print("  python app.py evidence list-goal <goal_id>")
    print("  python app.py evidence list-portfolio <portfolio_id>")
    print("  python app.py evidence list-program <program_id>")
    print("  python app.py issue list")
    print("  python app.py issue show <issue_id>")
    print("  python app.py portfolio create <name>")
    print("  python app.py portfolio list")
    print("  python app.py portfolio show <portfolio_id>")
    print("  python app.py portfolio state <portfolio_id>")
    print("  python app.py portfolio summary <portfolio_id>")
    print("  python app.py portfolio add-goal <portfolio_id> <goal_id>")
    print("  python app.py portfolio remove-goal <portfolio_id> <goal_id>")
    print("  python app.py portfolio run-next <portfolio_id>")
    print("  python app.py portfolio cycle <portfolio_id>")
    print("  python app.py portfolio run-until-idle <portfolio_id>")
    print("  python app.py runtime")
    print("  python app.py health")
    print("  python app.py replay")
    print("  python app.py ask <message>")
    print("  python app.py chat <message>")
    print("")
    print("Legacy/runtime commands:")
    print("  python app.py task show <task_id>")
    print("  python app.py task result <task_id>")
    print("  python app.py task open <task_id> [target]")
    print("  python app.py task delete <task_id>")
    print("  python app.py task retry <task_id>")
    print("  python app.py task rerun <task_id>")
    print("  python app.py task create <goal>")
    print("  python app.py task submit [task_id]")
    print("  python app.py l5-run [--json] [--tts] <task>")
    print("")
    print("Note:")
    print("  This is the thin launcher help path.")
    print("  It intentionally does not boot app_legacy.py or the heavy runtime graph.")


def print_json(data: Any) -> None:
    print(json.dumps(make_json_safe(data), ensure_ascii=False, indent=2, sort_keys=True))


def _is_runtime_command(argv: List[str]) -> bool:
    normalized = [str(item).strip().lower() for item in argv if str(item).strip()]
    if not normalized:
        return False
    return normalized[0] in {"runtime", "health", "replay", "audit", "ask", "chat"}


def _try_fast_cli(argv: List[str]) -> bool:
    if _is_help_command(argv):
        _print_thin_help()
        return True

    try:
        goal_cli = _load_goal_cli()
        if bool(goal_cli(argv, repo_root=_repo_root())):
            return True
    except Exception:
        pass

    try:
        program_cli = _load_program_cli()
        if bool(program_cli(argv, repo_root=_repo_root())):
            return True
    except Exception:
        pass

    try:
        portfolio_cli = _load_portfolio_cli()
        if bool(portfolio_cli(argv, repo_root=_repo_root())):
            return True
    except Exception:
        pass

    try:
        artifact_cli = _load_artifact_cli()
        if bool(artifact_cli(argv, repo_root=_repo_root())):
            return True
    except Exception:
        pass

    try:
        evidence_cli = _load_evidence_cli()
        if bool(evidence_cli(argv, repo_root=_repo_root())):
            return True
    except Exception:
        pass

    try:
        issue_cli = _load_issue_cli()
        if bool(issue_cli(argv, repo_root=_repo_root())):
            return True
    except Exception:
        pass

    try:
        task_cli = _load_task_cli()
        if bool(task_cli(argv, repo_root=_repo_root())):
            return True
    except Exception:
        pass

    if _is_runtime_command(argv):
        try:
            runtime_cli = _load_runtime_cli()
            if bool(runtime_cli(argv, repo_root=_repo_root())):
                return True
        except Exception:
            pass

    return False


def _run_legacy(argv: List[str]) -> int:
    legacy = _legacy_app_path()

    if not legacy.is_file():
        print(
            "ZERO launcher error: app_legacy.py not found. "
            "Before installing this thin app.py, rename the previous full app.py to app_legacy.py.",
            file=sys.stderr,
        )
        return 1

    old_argv = sys.argv[:]

    try:
        sys.argv = [str(legacy), *argv]
        runpy.run_path(str(legacy), run_name="__main__")
        return 0
    except SystemExit as exc:
        if exc.code is None:
            return 0
        if isinstance(exc.code, int):
            return exc.code
        return 1
    finally:
        sys.argv = old_argv


def main() -> int:
    argv = sys.argv[1:]

    if _try_fast_cli(argv):
        return 0

    return _run_legacy(argv)


if __name__ == "__main__":
    raise SystemExit(main())
