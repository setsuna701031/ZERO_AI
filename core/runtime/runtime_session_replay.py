from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def load_session_replay(session_dir: Path) -> Dict[str, Any]:
    path = session_dir / "session_replay.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def replay_event_summary(session_dir: Path) -> Dict[str, Any]:
    replay = load_session_replay(session_dir)
    events = replay.get("events") if isinstance(replay.get("events"), list) else []
    return {
        "ok": bool(replay),
        "session_id": replay.get("session_id"),
        "event_count": len(events),
        "events": [
            {
                "event": event.get("event"),
                "plan_index": event.get("plan_index"),
                "plan_status": event.get("plan_status"),
                "plan_ok": event.get("plan_ok"),
            }
            for event in events
            if isinstance(event, dict)
        ],
    }
