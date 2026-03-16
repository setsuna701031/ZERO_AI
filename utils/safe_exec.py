from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from config import ALLOWED_RUN_DIRS, ALLOWED_WRITE_DIRS, SAFE_MODE



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
        raise PermissionError(f"禁止寫入此路徑: {path}")



def ensure_run_allowed(path: Path) -> None:
    if not SAFE_MODE:
        return
    if not _is_under_allowed(path, ALLOWED_RUN_DIRS):
        raise PermissionError(f"禁止執行此路徑: {path}")



def run_python_file(path: Path, timeout: int = 20) -> str:
    process = subprocess.run(
        [sys.executable, str(path)],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(path.parent),
    )

    stdout = process.stdout.strip() or "<無 stdout>"
    stderr = process.stderr.strip() or "<無 stderr>"
    return (
        f"returncode: {process.returncode}\n"
        f"--- stdout ---\n{stdout}\n"
        f"--- stderr ---\n{stderr}"
    )