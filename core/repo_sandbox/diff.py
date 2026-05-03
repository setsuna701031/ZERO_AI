"""Unified diff helpers for sandboxed repo edits."""

from __future__ import annotations

from pathlib import Path
import difflib


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def build_unified_diff(
    before_path: str | Path,
    after_path: str | Path,
    relative_path: str | Path,
    *,
    context_lines: int = 3,
) -> str:
    """Return a unified diff for one file.

    Diff labels are stable review labels rather than absolute local paths.
    """

    before = Path(before_path)
    after = Path(after_path)
    rel = Path(relative_path).as_posix()

    before_lines = _read_text(before).splitlines(keepends=True) if before.exists() else []
    after_lines = _read_text(after).splitlines(keepends=True) if after.exists() else []

    return "".join(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
            n=context_lines,
        )
    )
