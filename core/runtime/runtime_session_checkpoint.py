from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def list_session_checkpoints(session_dir: Path) -> List[Dict[str, Any]]:
    checkpoints_dir = session_dir / "checkpoints"
    if not checkpoints_dir.exists():
        return []
    records: List[Dict[str, Any]] = []
    for path in sorted(checkpoints_dir.glob("checkpoint_*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data["checkpoint_path"] = str(path)
                records.append(data)
        except Exception:
            continue
    return records


def load_latest_checkpoint(session_dir: Path) -> Dict[str, Any]:
    checkpoints = list_session_checkpoints(session_dir)
    return checkpoints[-1] if checkpoints else {}
