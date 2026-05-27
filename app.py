from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path
from typing import List


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def _legacy_app_path() -> Path:
    override = os.environ.get("ZERO_LEGACY_APP", "").strip()
    if override:
        return Path(override).resolve(strict=False)
    return _repo_root() / "app_legacy.py"


def _try_fast_cli(argv: List[str]) -> bool:
    try:
        from cli.task_cli import try_handle_fast_task_command
        if bool(try_handle_fast_task_command(argv, repo_root=_repo_root())):
            return True
    except Exception:
        pass

    try:
        from cli.runtime_cli import try_handle_fast_runtime_command
        if bool(try_handle_fast_runtime_command(argv, repo_root=_repo_root())):
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
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
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
