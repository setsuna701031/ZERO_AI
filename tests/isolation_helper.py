from __future__ import annotations

import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def isolated_workspace(prefix: str) -> Iterator[Path]:
    repo_root = Path(__file__).resolve().parent.parent
    temp_root = repo_root / ".test_tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    root = (temp_root / f"zero_{prefix}_{uuid.uuid4().hex}").resolve()
    try:
        root.mkdir(parents=True, exist_ok=False)
        (root / "shared").mkdir(parents=True, exist_ok=True)
        (root / "tasks").mkdir(parents=True, exist_ok=True)
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)
        try:
            temp_root.rmdir()
        except OSError:
            pass
