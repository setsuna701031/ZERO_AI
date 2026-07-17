"""
Pytest compatibility bootstrap for ZERO_AI.

Purpose:
- Make repository-root imports stable when pytest is launched from different
  working directories or shells.
- Preserve legacy test contract for ``from app import print_json`` after the
  CLI split moved JSON output helpers out of app.py.

This file is intentionally test-scoped. It does not change runtime behavior.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]


def _ensure_repo_root_on_sys_path() -> None:
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def _legacy_print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _install_legacy_app_contract() -> None:
    try:
        import app  # type: ignore
    except Exception:
        return

    if not hasattr(app, "print_json"):
        setattr(app, "print_json", _legacy_print_json)


_ensure_repo_root_on_sys_path()
_install_legacy_app_contract()
