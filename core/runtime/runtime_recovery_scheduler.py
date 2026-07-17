from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def build_recovery_schedule(repo_root: Path, incident_queue: Dict[str, Any], *, max_retry_depth: int = 2) -> Dict[str, Any]:
    schedule_items: List[Dict[str, Any]] = []

    incidents = incident_queue.get("incidents") if isinstance(incident_queue.get("incidents"), list) else []
    seen_sessions: set[str] = set()

    for incident in incidents:
        if not isinstance(incident, dict):
            continue
        session_id = str(incident.get("session_id") or "")
        if not session_id or session_id in seen_sessions:
            continue
        seen_sessions.add(session_id)

        if not bool(incident.get("requires_recovery_schedule")):
            continue

        schedule_items.append(
            {
                "action": "runtime_session_resume",
                "session_id": session_id,
                "reason": incident.get("type"),
                "max_retry_depth": max_retry_depth,
                "scheduled_at": time.time(),
                "status": "scheduled",
                "command_hint": f"python app.py task runtime-session-resume {session_id}",
            }
        )

    root = repo_root / "workspace" / "runtime_supervisor"
    schedule_path = root / "recovery_schedule.json"
    schedule = {
        "ok": True,
        "schema": "zero.aer.runtime_recovery_schedule.v1",
        "created_at": time.time(),
        "scheduled_count": len(schedule_items),
        "max_retry_depth": max_retry_depth,
        "items": schedule_items,
        "schedule_path": str(schedule_path),
        "boundary": {
            "scheduler_records_recovery_actions_only": True,
            "does_not_execute_hidden_resume": True,
            "bounded_recovery": True,
            "no_hidden_mutation_shortcut": True,
        },
    }
    _write_json(schedule_path, schedule)
    return schedule
