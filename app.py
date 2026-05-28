from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path
from typing import Callable, List


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