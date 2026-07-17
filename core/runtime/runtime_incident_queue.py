from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _incident_id(seed: str) -> str:
    return "runtime_incident_" + hashlib.sha1(f"{seed}:{time.time()}".encode("utf-8")).hexdigest()[:16]


def build_incident_queue(repo_root: Path, watchdog_scan: Dict[str, Any], health_state: Dict[str, Any]) -> Dict[str, Any]:
    root = repo_root / "workspace" / "runtime_incidents"
    queue_path = root / "incident_queue.json"

    incidents: List[Dict[str, Any]] = []
    for record in watchdog_scan.get("stalled_sessions", []) if isinstance(watchdog_scan.get("stalled_sessions"), list) else []:
        incidents.append(
            {
                "incident_id": _incident_id(str(record.get("session_id"))),
                "type": "stalled_session",
                "session_id": record.get("session_id"),
                "session_dir": record.get("session_dir"),
                "severity": "warning",
                "created_at": time.time(),
                "requires_recovery_schedule": True,
            }
        )

    for record in watchdog_scan.get("recovery_required_sessions", []) if isinstance(watchdog_scan.get("recovery_required_sessions"), list) else []:
        incidents.append(
            {
                "incident_id": _incident_id(str(record.get("session_id"))),
                "type": "recovery_required_session",
                "session_id": record.get("session_id"),
                "session_dir": record.get("session_dir"),
                "severity": "recoverable",
                "created_at": time.time(),
                "requires_recovery_schedule": True,
            }
        )

    for record in watchdog_scan.get("orphaned_sessions", []) if isinstance(watchdog_scan.get("orphaned_sessions"), list) else []:
        incidents.append(
            {
                "incident_id": _incident_id(str(record.get("session_id"))),
                "type": "orphaned_session",
                "session_id": record.get("session_id"),
                "session_dir": record.get("session_dir"),
                "severity": "manual_review",
                "created_at": time.time(),
                "requires_recovery_schedule": False,
            }
        )

    existing = _read_json(queue_path)
    previous = existing.get("incidents") if isinstance(existing.get("incidents"), list) else []
    combined = previous + incidents

    queue = {
        "ok": True,
        "schema": "zero.aer.runtime_incident_queue.v1",
        "updated_at": time.time(),
        "health_status": health_state.get("status"),
        "incident_count": len(combined),
        "new_incident_count": len(incidents),
        "incidents": combined,
        "queue_path": str(queue_path),
    }
    _write_json(queue_path, queue)

    for incident in incidents:
        _write_json(root / f"{incident['incident_id']}.json", incident)

    return queue
