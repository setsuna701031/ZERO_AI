from __future__ import annotations

from pathlib import Path


def governed_put_text(path: Path, content: str) -> None:
    """Filesystem write primitive owned by the governed mutation boundary."""
    path.write_text(content, encoding="utf-8")


__all__ = ["governed_put_text"]
