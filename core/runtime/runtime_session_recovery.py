from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def load_recovery_marker(session_dir: Path) -> Dict[str, Any]:
    path = session_dir / "recovery_marker.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def recovery_required(session_dir: Path) -> bool:
    return bool(load_recovery_marker(session_dir))
