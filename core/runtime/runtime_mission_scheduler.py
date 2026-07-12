from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import stat
import time
from typing import Any, Callable, Mapping

from core.runtime.runtime_autonomous_loop import RuntimeAutonomousLoop
from core.runtime.runtime_mission_model import load_mission
from core.runtime.runtime_operator_session import fingerprint, parse_time, time_text

CONTRACT = "zero.runtime.mission_scheduler.v1"
ENTRY_CONTRACT = "zero.runtime.mission_scheduler_entry.v1"

DEFAULT_LEASE_SECONDS = 120
MIN_POLL_INTERVAL = 0.1
MAX_POLL_INTERVAL = 60.0

ACTIVE_ENTRY_STATUSES = {
    "queued",
    "leased",
    "running",
    "waiting",
}
TERMINAL_ENTRY_STATUSES = {
    "completed",
    "partially_completed",
    "blocked",
    "failed",
    "cancelled",
    "expired",
}
MISSION_TERMINAL_STATUSES = {
    "completed",
    "partially_completed",
    "blocked",
    "failed",
    "cancelled",
    "expired",
}


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _unsigned(
    value: Mapping[str, Any],
    fingerprint_field: str,
) -> dict[str, Any]:
    result = _mapping(value)
    result.pop(fingerprint_field, None)
    return result


def _unsafe(path: Path) -> bool:
    try:
        attributes = getattr(
            path.lstat(),
            "st_file_attributes",
            0,
        )
        reparse = getattr(
            stat,
            "FILE_ATTRIBUTE_REPARSE_POINT",
            0x400,
        )
        return path.is_symlink() or bool(attributes & reparse)
    except OSError:
        return False


def _atomic_write_json(
    value: Mapping[str, Any],
    destination: Path,
) -> None:
    if destination.exists() and _unsafe(destination):
        raise ValueError("unsafe_mission_scheduler_state_path")

    destination.parent.mkdir(parents=True, exist_ok=True)
    if _unsafe(destination.parent):
        raise ValueError(
            "unsafe_mission_scheduler_state_directory"
        )

    temporary = destination.with_name(
        f".{destination.name}.tmp"
    )
    with temporary.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as handle:
        handle.write(
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())

    os.replace(temporary, destination)


def _normalized_path(path: Any) -> str:
    return str(Path(path).resolve(strict=False))


def _publish_scheduler_event(
    runtime_config: Mapping[str, Any] | None,
    *,
    topic: str,
    source: str,
    payload: Mapping[str, Any],
    idempotency_key: str,
    now: Any = None,
) -> dict[str, Any] | None:
    config = _mapping(runtime_config)
    state_path_text = str(
        config.get("event_bus_state_path") or ""
    ).strip()
    if not state_path_text:
        return None

    from core.runtime.runtime_event_bus import (
        load_event_bus_state,
        publish,
        save_event_bus_state,
    )

    state_path = Path(state_path_text)
    bus = load_event_bus_state(state_path)
    bus, event = publish(
        bus,
        event_type="scheduler",
        topic=topic,
        source=source,
        payload=payload,
        idempotency_key=idempotency_key,
        correlation_id=str(
            payload.get("mission_id")
            or payload.get("scheduler_id")
            or ""
        )
        or None,
        causation_id=str(
            payload.get("entry_id") or ""
        )
        or None,
        now=now,
    )
    save_event_bus_state(bus, state_path)
    return event


def _entry_identity(
    *,
    mission_id: str,
    mission_path: Any,
) -> str:
    identity = {
        "mission_id": mission_id,
        "mission_path": _normalized_path(
            mission_path
        ).replace("\\", "/").casefold(),
    }
    return (
        f"mission-scheduler-entry-"
        f"{fingerprint(identity)[:20]}"
    )


def _lease_identity(
    *,
    scheduler_id: str,
    entry_id: str,
    owner: str,
    acquired_at: str,
) -> str:
    identity = {
        "scheduler_id": scheduler_id,
        "entry_id": entry_id,
        "owner": owner,
        "acquired_at": acquired_at,
    }
    return (
        f"mission-scheduler-lease-"
        f"{fingerprint(identity)[:20]}"
    )


def seal_mission_scheduler_entry(
    entry: Mapping[str, Any],
) -> dict[str, Any]:
    value = _unsigned(
        entry,
        "entry_fingerprint",
    )
    value["entry_fingerprint"] = fingerprint(value)
    return value


def validate_mission_scheduler_entry(
    entry: Mapping[str, Any],
) -> list[str]:
    value = _mapping(entry)
    reasons: list[str] = []

    if value.get("contract") != ENTRY_CONTRACT:
        reasons.append("invalid_mission_scheduler_entry_contract")

    expected = fingerprint(
        _unsigned(
            value,
            "entry_fingerprint",
        )
    )
    if value.get("entry_fingerprint") != expected:
        reasons.append(
            "mission_scheduler_entry_fingerprint_mismatch"
        )

    if not str(value.get("entry_id") or "").strip():
        reasons.append("mission_scheduler_entry_id_required")
    if not str(value.get("mission_id") or "").strip():
        reasons.append("mission_id_required")
    if not str(value.get("mission_path") or "").strip():
        reasons.append("mission_path_required")

    status = value.get("entry_status")
    if status not in (
        ACTIVE_ENTRY_STATUSES
        | TERMINAL_ENTRY_STATUSES
    ):
        reasons.append(
            "invalid_mission_scheduler_entry_status"
        )

    priority = value.get("priority")
    if (
        isinstance(priority, bool)
        or not isinstance(priority, int)
        or not -100 <= priority <= 100
    ):
        reasons.append("invalid_mission_scheduler_priority")

    lease = _mapping(value.get("lease"))
    if status in {"leased", "running"}:
        if not lease:
            reasons.append(
                "mission_scheduler_active_lease_required"
            )
        elif not str(lease.get("lease_id") or "").strip():
            reasons.append("mission_scheduler_lease_id_required")
        elif not str(lease.get("owner") or "").strip():
            reasons.append("mission_scheduler_lease_owner_required")
        elif not lease.get("expires_at"):
            reasons.append(
                "mission_scheduler_lease_expiry_required"
            )

    return reasons


def seal_mission_scheduler_state(
    state: Mapping[str, Any],
) -> dict[str, Any]:
    value = _unsigned(
        state,
        "scheduler_fingerprint",
    )
    value["scheduler_fingerprint"] = fingerprint(value)
    return value


def validate_mission_scheduler_state(
    state: Mapping[str, Any],
) -> list[str]:
    value = _mapping(state)
    reasons: list[str] = []

    if value.get("contract") != CONTRACT:
        reasons.append("invalid_mission_scheduler_contract")

    expected = fingerprint(
        _unsigned(
            value,
            "scheduler_fingerprint",
        )
    )
    if value.get("scheduler_fingerprint") != expected:
        reasons.append(
            "mission_scheduler_fingerprint_mismatch"
        )

    if not str(value.get("scheduler_id") or "").strip():
        reasons.append("mission_scheduler_id_required")

    if value.get("scheduler_status") not in {
        "created",
        "running",
        "idle",
        "paused",
        "stopping",
        "stopped",
        "blocked",
        "failed",
    }:
        reasons.append("invalid_mission_scheduler_status")

    entries = value.get("entries")
    order = value.get("entry_order")
    if not isinstance(entries, Mapping):
        reasons.append("mission_scheduler_entries_required")
        entries = {}
    if not isinstance(order, list):
        reasons.append(
            "mission_scheduler_entry_order_required"
        )
        order = []

    if set(order) != set(entries):
        reasons.append(
            "mission_scheduler_entry_order_mismatch"
        )

    for entry_id in order:
        entry = _mapping(entries.get(entry_id))
        if entry.get("entry_id") != entry_id:
            reasons.append(
                f"mission_scheduler_entry_identity_mismatch:{entry_id}"
            )
            continue
        for reason in validate_mission_scheduler_entry(
            entry
        ):
            reasons.append(f"{entry_id}:{reason}")

    return reasons


def create_mission_scheduler_state(
    *,
    state_path: Any,
    scheduler_name: str = "default",
    now: Any = None,
) -> dict[str, Any]:
    name = str(scheduler_name or "").strip()
    if not name:
        raise ValueError("mission_scheduler_name_required")

    destination = Path(state_path)
    at = time_text(now)
    identity = {
        "scheduler_name": name,
        "state_path": _normalized_path(
            destination
        ).replace("\\", "/").casefold(),
    }
    scheduler_id = (
        f"mission-scheduler-"
        f"{fingerprint(identity)[:20]}"
    )

    return seal_mission_scheduler_state(
        {
            "contract": CONTRACT,
            "scheduler_id": scheduler_id,
            "scheduler_name": name,
            "scheduler_status": "created",
            "state_path": _normalized_path(destination),
            "entries": {},
            "entry_order": [],
            "created_at": at,
            "updated_at": at,
            "started_at": None,
            "stopped_at": None,
            "loop_iteration": 0,
            "completed_missions": 0,
            "waiting_missions": 0,
            "blocked_missions": 0,
            "failed_missions": 0,
            "recovered_leases": 0,
            "idle_iterations": 0,
            "stop_requested": False,
            "pause_requested": False,
            "current_entry_id": None,
            "current_mission_id": None,
            "last_result": None,
            "last_event_id": None,
            "failure": None,
            "audit_record": {
                "event_type": (
                    "runtime_mission_scheduler_created"
                ),
                "created_at": at,
            },
        }
    )


def save_mission_scheduler_state(
    state: Mapping[str, Any],
    path: Any,
) -> dict[str, Any]:
    destination = Path(path)
    value = seal_mission_scheduler_state(state)
    reasons = validate_mission_scheduler_state(value)
    if reasons:
        raise ValueError(";".join(reasons))
    _atomic_write_json(value, destination)
    return value


def load_mission_scheduler_state(
    path: Any,
) -> dict[str, Any]:
    source = Path(path)
    if _unsafe(source):
        raise ValueError(
            "unsafe_mission_scheduler_state_path"
        )

    try:
        value = json.loads(
            source.read_text(
                encoding="utf-8-sig"
            )
        )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError(
            "invalid_mission_scheduler_json"
        ) from exc

    reasons = validate_mission_scheduler_state(
        value
    )
    if reasons:
        raise ValueError(";".join(reasons))
    return value


def enqueue_mission(
    state: Mapping[str, Any],
    mission_path: Any,
    *,
    priority: int = 0,
    now: Any = None,
) -> dict[str, Any]:
    if (
        isinstance(priority, bool)
        or not isinstance(priority, int)
        or not -100 <= priority <= 100
    ):
        raise ValueError(
            "invalid_mission_scheduler_priority"
        )

    value = _mapping(state)
    reasons = validate_mission_scheduler_state(
        value
    )
    if reasons:
        raise ValueError(";".join(reasons))

    mission = load_mission(
        mission_path,
        check_expiry=False,
    )
    mission_id = str(
        mission.get("mission_id") or ""
    ).strip()
    if not mission_id:
        raise ValueError("mission_id_required")

    entry_id = _entry_identity(
        mission_id=mission_id,
        mission_path=mission_path,
    )
    entries = _mapping(value.get("entries"))

    existing = _mapping(entries.get(entry_id))
    if existing:
        if existing.get("mission_id") != mission_id:
            raise ValueError(
                "mission_scheduler_entry_collision"
            )
        return value

    status = str(
        mission.get("mission_status") or ""
    ).strip()
    entry_status = (
        status
        if status in TERMINAL_ENTRY_STATUSES
        else "queued"
    )
    at = time_text(now)

    entry = seal_mission_scheduler_entry(
        {
            "contract": ENTRY_CONTRACT,
            "entry_id": entry_id,
            "mission_id": mission_id,
            "mission_path": _normalized_path(
                mission_path
            ),
            "mission_status": status,
            "entry_status": entry_status,
            "priority": priority,
            "enqueued_at": at,
            "updated_at": at,
            "started_at": None,
            "completed_at": (
                at
                if entry_status
                in TERMINAL_ENTRY_STATUSES
                else None
            ),
            "lease": None,
            "attempt_count": 0,
            "last_driver_result": None,
            "last_error": None,
        }
    )

    entries[entry_id] = entry
    value["entries"] = entries
    value.setdefault("entry_order", []).append(
        entry_id
    )
    value["updated_at"] = at
    return seal_mission_scheduler_state(value)


def _recover_expired_leases(
    state: Mapping[str, Any],
    *,
    now: Any = None,
) -> tuple[dict[str, Any], int]:
    value = _mapping(state)
    current = parse_time(
        now or datetime.now(timezone.utc)
    )
    entries = _mapping(value.get("entries"))
    recovered = 0

    for entry_id in value.get("entry_order", []):
        entry = _mapping(entries.get(entry_id))
        if entry.get("entry_status") not in {
            "leased",
            "running",
        }:
            continue

        lease = _mapping(entry.get("lease"))
        try:
            expired = (
                parse_time(lease.get("expires_at"))
                <= current
            )
        except (TypeError, ValueError):
            expired = True

        if not expired:
            continue

        entry["entry_status"] = "queued"
        entry["lease"] = None
        entry["updated_at"] = time_text(now)
        entry["last_error"] = {
            "reason": "mission_scheduler_lease_expired"
        }
        entries[entry_id] = (
            seal_mission_scheduler_entry(entry)
        )
        recovered += 1

    value["entries"] = entries
    value["recovered_leases"] = int(
        value.get("recovered_leases") or 0
    ) + recovered
    return (
        seal_mission_scheduler_state(value),
        recovered,
    )


def _ordered_candidate_entries(
    state: Mapping[str, Any],
) -> list[dict[str, Any]]:
    value = _mapping(state)
    entries = _mapping(value.get("entries"))
    indexed = {
        entry_id: index
        for index, entry_id
        in enumerate(value.get("entry_order", []))
    }

    candidates = [
        _mapping(entry)
        for entry in entries.values()
        if entry.get("entry_status")
        in {"queued", "waiting"}
    ]
    candidates.sort(
        key=lambda entry: (
            -int(entry.get("priority") or 0),
            indexed.get(entry.get("entry_id"), 10**9),
            str(entry.get("enqueued_at") or ""),
        )
    )
    return candidates


def lease_next_mission(
    state: Mapping[str, Any],
    *,
    owner: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    now: Any = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    owner_text = str(owner or "").strip()
    if not owner_text:
        raise ValueError(
            "mission_scheduler_lease_owner_required"
        )
    if (
        isinstance(lease_seconds, bool)
        or not isinstance(lease_seconds, int)
        or lease_seconds < 1
    ):
        raise ValueError(
            "invalid_mission_scheduler_lease_seconds"
        )

    value, _ = _recover_expired_leases(
        state,
        now=now,
    )
    candidates = _ordered_candidate_entries(value)
    if not candidates:
        return value, None

    entry = candidates[0]
    at = parse_time(
        now or datetime.now(timezone.utc)
    )
    acquired_at = time_text(at)
    expires_at = time_text(
        at + timedelta(seconds=lease_seconds)
    )
    lease_id = _lease_identity(
        scheduler_id=value["scheduler_id"],
        entry_id=entry["entry_id"],
        owner=owner_text,
        acquired_at=acquired_at,
    )

    entry["entry_status"] = "leased"
    entry["lease"] = {
        "lease_id": lease_id,
        "owner": owner_text,
        "acquired_at": acquired_at,
        "expires_at": expires_at,
    }
    entry["updated_at"] = acquired_at

    entries = _mapping(value.get("entries"))
    entries[entry["entry_id"]] = (
        seal_mission_scheduler_entry(entry)
    )
    value["entries"] = entries
    value["current_entry_id"] = entry["entry_id"]
    value["current_mission_id"] = entry["mission_id"]
    value["updated_at"] = acquired_at
    return (
        seal_mission_scheduler_state(value),
        deepcopy(entry["lease"]),
    )


def release_mission_lease(
    state: Mapping[str, Any],
    *,
    entry_id: str,
    lease_id: str,
    owner: str,
    next_status: str = "queued",
    now: Any = None,
) -> dict[str, Any]:
    if next_status not in (
        ACTIVE_ENTRY_STATUSES
        | TERMINAL_ENTRY_STATUSES
    ):
        raise ValueError(
            "invalid_mission_scheduler_entry_status"
        )

    value = _mapping(state)
    entries = _mapping(value.get("entries"))
    entry = _mapping(entries.get(entry_id))
    if not entry:
        raise ValueError(
            "mission_scheduler_entry_not_found"
        )

    lease = _mapping(entry.get("lease"))
    if lease.get("lease_id") != lease_id:
        raise ValueError(
            "mission_scheduler_lease_identity_mismatch"
        )
    if lease.get("owner") != owner:
        raise ValueError(
            "mission_scheduler_lease_owner_mismatch"
        )

    at = time_text(now)
    entry["entry_status"] = next_status
    entry["lease"] = None
    entry["updated_at"] = at
    if next_status in TERMINAL_ENTRY_STATUSES:
        entry["completed_at"] = at

    entries[entry_id] = seal_mission_scheduler_entry(
        entry
    )
    value["entries"] = entries
    value["current_entry_id"] = None
    value["current_mission_id"] = None
    value["updated_at"] = at
    return seal_mission_scheduler_state(value)


def run_mission_scheduler_iteration(
    *,
    scheduler_state_path: Any,
    worker_state_path: Any,
    worker_name: str,
    target_root: Any,
    workspace_root: Any,
    runtime_config: Mapping[str, Any] | None = None,
    mission_driver: RuntimeAutonomousLoop | None = None,
    owner: str = "mission-runtime",
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    mission_max_iterations: int = 10,
    now: Any = None,
) -> dict[str, Any]:
    state = load_mission_scheduler_state(
        scheduler_state_path
    )
    state, recovered = _recover_expired_leases(
        state,
        now=now,
    )
    state["loop_iteration"] = int(
        state.get("loop_iteration") or 0
    ) + 1
    state["recovered_leases"] = int(
        state.get("recovered_leases") or 0
    ) + recovered

    if state.get("stop_requested"):
        state["scheduler_status"] = "stopped"
        state["stopped_at"] = time_text(now)
        state["updated_at"] = time_text(now)
        state = save_mission_scheduler_state(
            state,
            scheduler_state_path,
        )
        event = _publish_scheduler_event(
            runtime_config,
            topic="scheduler.stopped",
            source=state["scheduler_id"],
            payload={
                "scheduler_id": state["scheduler_id"],
                "scheduler_status": state[
                    "scheduler_status"
                ],
                "loop_iteration": state[
                    "loop_iteration"
                ],
            },
            idempotency_key=(
                f"{state['scheduler_id']}:"
                f"scheduler.stopped:"
                f"{state['loop_iteration']}"
            ),
            now=now,
        )
        if event:
            state["last_event_id"] = event.get(
                "event_id"
            )
        return save_mission_scheduler_state(
            state,
            scheduler_state_path,
        )

    if state.get("pause_requested"):
        state["scheduler_status"] = "paused"
        state["idle_iterations"] = int(
            state.get("idle_iterations") or 0
        ) + 1
        state["updated_at"] = time_text(now)
        state = save_mission_scheduler_state(
            state,
            scheduler_state_path,
        )
        event = _publish_scheduler_event(
            runtime_config,
            topic="scheduler.paused",
            source=state["scheduler_id"],
            payload={
                "scheduler_id": state["scheduler_id"],
                "scheduler_status": state[
                    "scheduler_status"
                ],
                "loop_iteration": state[
                    "loop_iteration"
                ],
            },
            idempotency_key=(
                f"{state['scheduler_id']}:"
                f"scheduler.paused:"
                f"{state['loop_iteration']}"
            ),
            now=now,
        )
        if event:
            state["last_event_id"] = event.get(
                "event_id"
            )
        return save_mission_scheduler_state(
            state,
            scheduler_state_path,
        )

    state, lease = lease_next_mission(
        state,
        owner=owner,
        lease_seconds=lease_seconds,
        now=now,
    )
    if lease is None:
        state["scheduler_status"] = "idle"
        state["idle_iterations"] = int(
            state.get("idle_iterations") or 0
        ) + 1
        state["last_result"] = {
            "dispatched": False,
            "reason": "no_dispatchable_mission",
        }
        state["updated_at"] = time_text(now)
        state = save_mission_scheduler_state(
            state,
            scheduler_state_path,
        )
        event = _publish_scheduler_event(
            runtime_config,
            topic="scheduler.idle",
            source=state["scheduler_id"],
            payload={
                "scheduler_id": state["scheduler_id"],
                "scheduler_status": state[
                    "scheduler_status"
                ],
                "loop_iteration": state[
                    "loop_iteration"
                ],
                "reason": "no_dispatchable_mission",
            },
            idempotency_key=(
                f"{state['scheduler_id']}:"
                f"scheduler.idle:"
                f"{state['loop_iteration']}"
            ),
            now=now,
        )
        if event:
            state["last_event_id"] = event.get(
                "event_id"
            )
        return save_mission_scheduler_state(
            state,
            scheduler_state_path,
        )

    entry_id = state["current_entry_id"]
    entries = _mapping(state.get("entries"))
    entry = _mapping(entries.get(entry_id))
    entry["entry_status"] = "running"
    entry["started_at"] = (
        entry.get("started_at")
        or time_text(now)
    )
    entry["updated_at"] = time_text(now)
    entry["attempt_count"] = int(
        entry.get("attempt_count") or 0
    ) + 1
    entries[entry_id] = seal_mission_scheduler_entry(
        entry
    )
    state["entries"] = entries
    state["scheduler_status"] = "running"
    state["idle_iterations"] = 0
    state["started_at"] = (
        state.get("started_at")
        or time_text(now)
    )
    state = save_mission_scheduler_state(
        state,
        scheduler_state_path,
    )
    dispatched_event = _publish_scheduler_event(
        runtime_config,
        topic="scheduler.dispatched",
        source=state["scheduler_id"],
        payload={
            "scheduler_id": state["scheduler_id"],
            "scheduler_status": state[
                "scheduler_status"
            ],
            "entry_id": entry_id,
            "mission_id": entry["mission_id"],
            "mission_path": entry["mission_path"],
            "lease_id": lease["lease_id"],
            "lease_owner": lease["owner"],
            "attempt_count": entry[
                "attempt_count"
            ],
        },
        idempotency_key=(
            f"{state['scheduler_id']}:"
            f"scheduler.dispatched:"
            f"{entry_id}:{lease['lease_id']}"
        ),
        now=now,
    )
    if dispatched_event:
        state["last_event_id"] = (
            dispatched_event.get("event_id")
        )
        state = save_mission_scheduler_state(
            state,
            scheduler_state_path,
        )

    driver = mission_driver or RuntimeAutonomousLoop(
        task_runner=lambda _: {
            "ok": False,
            "denial_reason": (
                "mission_scheduler_task_runner_unused"
            ),
        },
        max_iterations=mission_max_iterations,
    )

    try:
        result = driver.run_mission(
            entry["mission_path"],
            scheduler_state_path=(
                load_mission(
                    entry["mission_path"],
                    check_expiry=False,
                ).get("scheduler_state_path")
            ),
            worker_state_path=worker_state_path,
            worker_name=worker_name,
            target_root=target_root,
            workspace_root=workspace_root,
            runtime_config=runtime_config,
            max_iterations=mission_max_iterations,
            lease_seconds=lease_seconds,
            now_provider=(
                (lambda: now)
                if now is not None
                else None
            ),
        )
        final_status = str(
            result.get("mission_status") or ""
        ).strip()
        if final_status in MISSION_TERMINAL_STATUSES:
            next_status = final_status
        elif result.get("mission_waiting") is True:
            next_status = "waiting"
        else:
            next_status = "queued"

        state = load_mission_scheduler_state(
            scheduler_state_path
        )
        entries = _mapping(state.get("entries"))
        current_entry = _mapping(
            entries.get(entry_id)
        )
        current_entry["mission_status"] = final_status
        current_entry["last_driver_result"] = deepcopy(
            result
        )
        current_entry["last_error"] = None
        entries[entry_id] = (
            seal_mission_scheduler_entry(
                current_entry
            )
        )
        state["entries"] = entries
        state = release_mission_lease(
            state,
            entry_id=entry_id,
            lease_id=lease["lease_id"],
            owner=owner,
            next_status=next_status,
            now=now,
        )
        state["last_result"] = {
            "dispatched": True,
            "entry_id": entry_id,
            "mission_id": entry["mission_id"],
            "mission_status": final_status,
            "driver_status": result.get(
                "driver_status"
            ),
            "stopped_reason": result.get(
                "stopped_reason"
            ),
        }
        if next_status == "completed":
            state["completed_missions"] = int(
                state.get("completed_missions") or 0
            ) + 1
        elif next_status == "waiting":
            state["waiting_missions"] = int(
                state.get("waiting_missions") or 0
            ) + 1
        elif next_status == "blocked":
            state["blocked_missions"] = int(
                state.get("blocked_missions") or 0
            ) + 1
        elif next_status == "failed":
            state["failed_missions"] = int(
                state.get("failed_missions") or 0
            ) + 1

        state["scheduler_status"] = "running"
        state["updated_at"] = time_text(now)
        state = save_mission_scheduler_state(
            state,
            scheduler_state_path,
        )

        if next_status == "completed":
            topic = "scheduler.completed"
        elif next_status == "waiting":
            topic = "scheduler.waiting"
        elif next_status in {
            "blocked",
            "failed",
            "cancelled",
            "expired",
            "partially_completed",
        }:
            topic = "scheduler.blocked"
        else:
            topic = "scheduler.requeued"

        event = _publish_scheduler_event(
            runtime_config,
            topic=topic,
            source=state["scheduler_id"],
            payload={
                "scheduler_id": state["scheduler_id"],
                "scheduler_status": state[
                    "scheduler_status"
                ],
                "entry_id": entry_id,
                "mission_id": entry["mission_id"],
                "mission_status": final_status,
                "entry_status": next_status,
                "driver_status": result.get(
                    "driver_status"
                ),
                "stopped_reason": result.get(
                    "stopped_reason"
                ),
            },
            idempotency_key=(
                f"{state['scheduler_id']}:{topic}:"
                f"{entry_id}:{final_status}:"
                f"{current_entry.get('attempt_count')}"
            ),
            now=now,
        )
        if event:
            state["last_event_id"] = event.get(
                "event_id"
            )
        return save_mission_scheduler_state(
            state,
            scheduler_state_path,
        )
    except Exception as exc:
        state = load_mission_scheduler_state(
            scheduler_state_path
        )
        entries = _mapping(state.get("entries"))
        current_entry = _mapping(
            entries.get(entry_id)
        )
        current_entry["last_error"] = {
            "reason": f"{type(exc).__name__}:{exc}"
        }
        current_entry["mission_status"] = (
            current_entry.get("mission_status")
            or "unknown"
        )
        entries[entry_id] = (
            seal_mission_scheduler_entry(
                current_entry
            )
        )
        state["entries"] = entries
        try:
            state = release_mission_lease(
                state,
                entry_id=entry_id,
                lease_id=lease["lease_id"],
                owner=owner,
                next_status="queued",
                now=now,
            )
        except ValueError:
            pass

        state["failed_missions"] = int(
            state.get("failed_missions") or 0
        ) + 1
        state["scheduler_status"] = "blocked"
        state["failure"] = {
            "critical": False,
            "reasons": [
                f"{type(exc).__name__}:{exc}"
            ],
        }
        state["last_result"] = {
            "dispatched": False,
            "entry_id": entry_id,
            "mission_id": entry.get("mission_id"),
            "reason": f"{type(exc).__name__}:{exc}",
        }
        state["updated_at"] = time_text(now)
        state = save_mission_scheduler_state(
            state,
            scheduler_state_path,
        )
        event = _publish_scheduler_event(
            runtime_config,
            topic="scheduler.failed",
            source=state["scheduler_id"],
            payload={
                "scheduler_id": state["scheduler_id"],
                "scheduler_status": state[
                    "scheduler_status"
                ],
                "entry_id": entry_id,
                "mission_id": entry.get(
                    "mission_id"
                ),
                "reason": (
                    f"{type(exc).__name__}:{exc}"
                ),
            },
            idempotency_key=(
                f"{state['scheduler_id']}:"
                f"scheduler.failed:{entry_id}:"
                f"{fingerprint({'reason': str(exc)})[:20]}"
            ),
            now=now,
        )
        if event:
            state["last_event_id"] = event.get(
                "event_id"
            )
        return save_mission_scheduler_state(
            state,
            scheduler_state_path,
        )


def run_mission_scheduler(
    *,
    scheduler_state_path: Any,
    worker_state_path: Any,
    worker_name: str,
    target_root: Any,
    workspace_root: Any,
    runtime_config: Mapping[str, Any] | None = None,
    owner: str = "mission-runtime",
    poll_interval_seconds: float = 1.0,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    mission_max_iterations: int = 10,
    max_iterations: int | None = None,
    idle_exit_after: int | None = None,
    now_provider: Callable[[], Any] | None = None,
    sleep_provider: Callable[[float], None] | None = None,
    stop_signal: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    interval = float(poll_interval_seconds)
    if not MIN_POLL_INTERVAL <= interval <= MAX_POLL_INTERVAL:
        raise ValueError(
            "invalid_mission_scheduler_poll_interval"
        )
    if (
        max_iterations is not None
        and (
            isinstance(max_iterations, bool)
            or max_iterations < 1
        )
    ):
        raise ValueError(
            "invalid_mission_scheduler_max_iterations"
        )
    if (
        idle_exit_after is not None
        and (
            isinstance(idle_exit_after, bool)
            or idle_exit_after < 1
        )
    ):
        raise ValueError(
            "invalid_mission_scheduler_idle_exit_after"
        )

    clock = now_provider or (
        lambda: datetime.now(timezone.utc)
    )
    sleeper = sleep_provider or time.sleep
    iterations = 0

    state = load_mission_scheduler_state(
        scheduler_state_path
    )
    state["scheduler_status"] = "running"
    state["started_at"] = (
        state.get("started_at")
        or time_text(clock())
    )
    state["stopped_at"] = None
    state = save_mission_scheduler_state(
        state,
        scheduler_state_path,
    )

    while True:
        if stop_signal and stop_signal():
            state = load_mission_scheduler_state(
                scheduler_state_path
            )
            state["stop_requested"] = True
            save_mission_scheduler_state(
                state,
                scheduler_state_path,
            )

        state = run_mission_scheduler_iteration(
            scheduler_state_path=scheduler_state_path,
            worker_state_path=worker_state_path,
            worker_name=worker_name,
            target_root=target_root,
            workspace_root=workspace_root,
            runtime_config=runtime_config,
            owner=owner,
            lease_seconds=lease_seconds,
            mission_max_iterations=(
                mission_max_iterations
            ),
            now=clock(),
        )
        iterations += 1

        if state["scheduler_status"] in {
            "stopped",
            "failed",
        }:
            break

        if (
            max_iterations is not None
            and iterations >= max_iterations
        ):
            state["stop_requested"] = True
            state = save_mission_scheduler_state(
                state,
                scheduler_state_path,
            )

        if (
            idle_exit_after is not None
            and int(state.get("idle_iterations") or 0)
            >= idle_exit_after
        ):
            state["stop_requested"] = True
            state = save_mission_scheduler_state(
                state,
                scheduler_state_path,
            )

        if state.get("stop_requested"):
            state = run_mission_scheduler_iteration(
                scheduler_state_path=scheduler_state_path,
                worker_state_path=worker_state_path,
                worker_name=worker_name,
                target_root=target_root,
                workspace_root=workspace_root,
                runtime_config=runtime_config,
                owner=owner,
                lease_seconds=lease_seconds,
                mission_max_iterations=(
                    mission_max_iterations
                ),
                now=clock(),
            )
            break

        sleeper(interval)

    return state


def request_mission_scheduler_action(
    state: Mapping[str, Any],
    action: str,
    *,
    now: Any = None,
) -> dict[str, Any]:
    value = _mapping(state)
    at = time_text(now)

    if action == "pause":
        value["pause_requested"] = True
        status = "paused"
    elif action == "resume":
        value["pause_requested"] = False
        value["stop_requested"] = False
        status = "idle"
    elif action == "stop":
        value["stop_requested"] = True
        status = "stopping"
    else:
        raise ValueError(
            "invalid_mission_scheduler_action"
        )

    value["scheduler_status"] = status
    value["updated_at"] = at
    return seal_mission_scheduler_state(value)


__all__ = [
    "ACTIVE_ENTRY_STATUSES",
    "CONTRACT",
    "DEFAULT_LEASE_SECONDS",
    "ENTRY_CONTRACT",
    "MAX_POLL_INTERVAL",
    "MIN_POLL_INTERVAL",
    "MISSION_TERMINAL_STATUSES",
    "TERMINAL_ENTRY_STATUSES",
    "create_mission_scheduler_state",
    "enqueue_mission",
    "lease_next_mission",
    "load_mission_scheduler_state",
    "release_mission_lease",
    "request_mission_scheduler_action",
    "run_mission_scheduler",
    "run_mission_scheduler_iteration",
    "save_mission_scheduler_state",
    "seal_mission_scheduler_entry",
    "seal_mission_scheduler_state",
    "validate_mission_scheduler_entry",
    "validate_mission_scheduler_state",
]
