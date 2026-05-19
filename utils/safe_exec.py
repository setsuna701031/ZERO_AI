from __future__ import annotations

import sys
from pathlib import Path

from config import ALLOWED_RUN_DIRS, ALLOWED_WRITE_DIRS, SAFE_MODE
from core.runtime.execution_gateway import safe_subprocess_run


def _is_under_allowed(path: Path, allowed_dirs: list[str]) -> bool:
    resolved = path.resolve()
    for allowed in allowed_dirs:
        allowed_path = Path(allowed).resolve()
        if resolved == allowed_path or allowed_path in resolved.parents:
            return True
    return False


def ensure_write_allowed(path: Path) -> None:
    if not SAFE_MODE:
        return
    if not _is_under_allowed(path, ALLOWED_WRITE_DIRS):
        raise PermissionError(f"write path is outside allowed directories: {path}")


def ensure_run_allowed(path: Path) -> None:
    if not SAFE_MODE:
        return
    if not _is_under_allowed(path, ALLOWED_RUN_DIRS):
        raise PermissionError(f"run path is outside allowed directories: {path}")


def run_python_file(path: Path, timeout: int = 20) -> str:
    result = safe_subprocess_run(
        [sys.executable, str(path)],
        timeout=timeout,
        cwd=str(path.parent),
    )

    stdout = str(result.get("stdout") or "").strip() or "<empty stdout>"
    stderr = str(result.get("stderr") or "").strip() or "<empty stderr>"
    return (
        f"returncode: {result.get('returncode')}\n"
        f"--- stdout ---\n{stdout}\n"
        f"--- stderr ---\n{stderr}"
    )
