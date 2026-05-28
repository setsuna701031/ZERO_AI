from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def build_runtime_health_state(repo_root: Path, watchdog_scan: Dict[str, Any]) -> Dict[str, Any]:
    recovery_count = int(watchdog_scan.get("recovery_required_count") or 0)
    stalled_count = int(watchdog_scan.get("stalled_count") or 0)
    orphaned_count = int(watchdog_scan.get("orphaned_count") or 0)
    completed_count = int(watchdog_scan.get("completed_count") or 0)

    if stalled_count or orphaned_count:
        status = "degraded"
    elif recovery_count:
        status = "recovery_required"
    else:
        status = "healthy"

    return {
        "ok": status in {"healthy", "recovery_required", "degraded"},
        "schema": "zero.aer.runtime_health_state.v1",
        "created_at": time.time(),
        "status": status,
        "session_count": int(watchdog_scan.get("session_count") or 0),
        "completed_count": completed_count,
        "recovery_required_count": recovery_count,
        "stalled_count": stalled_count,
        "orphaned_count": orphaned_count,
        "replayable_count": int(watchdog_scan.get("replayable_count") or 0),
        "boundary": {
            "health_registry_is_observability_only": True,
            "no_execution_authority": True,
            "no_hidden_mutation_shortcut": True,
        },
    }


def persist_runtime_health(repo_root: Path, health_state: Dict[str, Any], watchdog_scan: Dict[str, Any]) -> Dict[str, Any]:
    root = repo_root / "workspace" / "runtime_health"
    registry_path = root / "runtime_health_registry.json"
    snapshot_path = root / "runtime_health_snapshot.json"

    registry = {
        "schema": "zero.aer.runtime_health_registry.v1",
        "updated_at": time.time(),
        "health_state": health_state,
        "last_watchdog_scan": watchdog_scan,
    }
    _write_json(registry_path, registry)
    _write_json(snapshot_path, health_state)

    return {
        "ok": True,
        "schema": "zero.aer.runtime_health_persistence.v1",
        "registry_path": str(registry_path),
        "snapshot_path": str(snapshot_path),
        "health_state": health_state,
    }
