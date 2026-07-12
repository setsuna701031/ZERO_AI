from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from core.runtime.runtime_event_bus import (
    load_event_bus_state,
    publish,
    save_event_bus_state,
)
from core.runtime.runtime_operator_session import (
    fingerprint,
    parse_time,
    time_text,
)
from core.runtime.runtime_worker_service import (
    load_worker_state,
)

CONTRACT = "zero.runtime.dispatch_coordinator.v1"
WORKER_RECORD_CONTRACT = (
    "zero.runtime.dispatch_coordinator.worker_record.v1"
)
LEASE_CONTRACT = (
    "zero.runtime.dispatch_coordinator.worker_lease.v1"
)

DEFAULT_LEASE_SECONDS = 120
HEARTBEAT_FRESH_SECONDS = 90

VALID_COORDINATOR_STATUSES = {
    "created",
    "running",
    "idle",
    "paused",
    "stopped",
    "blocked",
    "failed",
}

VALID_WORKER_STATUSES = {
    "registered",
    "available",
    "busy",
    "paused",
    "stale",
    "failed",
    "stopped",
}

VALID_LEASE_STATUSES = {
    "active",
    "completed",
    "released",
    "expired",
    "failed",
}


def _mapping(value: Any) -> dict[str, Any]:
    return (
        deepcopy(dict(value))
        if isinstance(value, Mapping)
        else {}
    )


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
        return path.is_symlink() or bool(
            attributes & reparse
        )
    except OSError:
        return False


def _atomic_write_json(
    value: Mapping[str, Any],
    destination: Path,
) -> None:
    if destination.exists() and _unsafe(destination):
        raise ValueError(
            "unsafe_dispatch_coordinator_state_path"
        )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    if _unsafe(destination.parent):
        raise ValueError(
            "unsafe_dispatch_coordinator_state_directory"
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


def _unsigned(
    value: Mapping[str, Any],
    fingerprint_field: str,
) -> dict[str, Any]:
    result = _mapping(value)
    result.pop(fingerprint_field, None)
    return result


def seal_worker_record(
    record: Mapping[str, Any],
) -> dict[str, Any]:
    value = _unsigned(
        record,
        "worker_record_fingerprint",
    )
    value["worker_record_fingerprint"] = fingerprint(
        value
    )
    return value


def validate_worker_record(
    record: Mapping[str, Any],
) -> list[str]:
    value = _mapping(record)
    reasons: list[str] = []

    if value.get("contract") != WORKER_RECORD_CONTRACT:
        reasons.append(
            "invalid_dispatch_worker_record_contract"
        )

    if value.get(
        "worker_record_fingerprint"
    ) != fingerprint(
        _unsigned(
            value,
            "worker_record_fingerprint",
        )
    ):
        reasons.append(
            "dispatch_worker_record_fingerprint_mismatch"
        )

    for field in (
        "worker_id",
        "worker_name",
        "worker_state_path",
    ):
        if not str(value.get(field) or "").strip():
            reasons.append(f"{field}_required")

    if value.get("worker_status") not in (
        VALID_WORKER_STATUSES
    ):
        reasons.append(
            "invalid_dispatch_worker_status"
        )

    active_lease_id = value.get("active_lease_id")
    if (
        value.get("worker_status") == "busy"
        and not str(active_lease_id or "").strip()
    ):
        reasons.append(
            "busy_worker_active_lease_required"
        )

    return reasons


def seal_dispatch_lease(
    lease: Mapping[str, Any],
) -> dict[str, Any]:
    value = _unsigned(
        lease,
        "lease_fingerprint",
    )
    value["lease_fingerprint"] = fingerprint(value)
    return value


def validate_dispatch_lease(
    lease: Mapping[str, Any],
) -> list[str]:
    value = _mapping(lease)
    reasons: list[str] = []

    if value.get("contract") != LEASE_CONTRACT:
        reasons.append(
            "invalid_dispatch_worker_lease_contract"
        )

    if value.get("lease_fingerprint") != fingerprint(
        _unsigned(
            value,
            "lease_fingerprint",
        )
    ):
        reasons.append(
            "dispatch_worker_lease_fingerprint_mismatch"
        )

    for field in (
        "lease_id",
        "worker_id",
        "mission_id",
        "entry_id",
        "acquired_at",
        "expires_at",
    ):
        if not str(value.get(field) or "").strip():
            reasons.append(f"{field}_required")

    if value.get("lease_status") not in (
        VALID_LEASE_STATUSES
    ):
        reasons.append(
            "invalid_dispatch_worker_lease_status"
        )

    return reasons


def seal_dispatch_coordinator_state(
    state: Mapping[str, Any],
) -> dict[str, Any]:
    value = _unsigned(
        state,
        "coordinator_fingerprint",
    )
    value["coordinator_fingerprint"] = fingerprint(
        value
    )
    return value


def validate_dispatch_coordinator_state(
    state: Mapping[str, Any],
) -> list[str]:
    value = _mapping(state)
    reasons: list[str] = []

    if value.get("contract") != CONTRACT:
        reasons.append(
            "invalid_dispatch_coordinator_contract"
        )

    if value.get(
        "coordinator_fingerprint"
    ) != fingerprint(
        _unsigned(
            value,
            "coordinator_fingerprint",
        )
    ):
        reasons.append(
            "dispatch_coordinator_fingerprint_mismatch"
        )

    if not str(
        value.get("coordinator_id") or ""
    ).strip():
        reasons.append(
            "dispatch_coordinator_id_required"
        )

    if not str(
        value.get("coordinator_name") or ""
    ).strip():
        reasons.append(
            "dispatch_coordinator_name_required"
        )

    if value.get("coordinator_status") not in (
        VALID_COORDINATOR_STATUSES
    ):
        reasons.append(
            "invalid_dispatch_coordinator_status"
        )

    workers = value.get("workers")
    worker_order = value.get("worker_order")
    leases = value.get("leases")
    lease_order = value.get("lease_order")

    if not isinstance(workers, Mapping):
        reasons.append(
            "dispatch_coordinator_workers_required"
        )
        workers = {}
    if not isinstance(worker_order, list):
        reasons.append(
            "dispatch_coordinator_worker_order_required"
        )
        worker_order = []
    if not isinstance(leases, Mapping):
        reasons.append(
            "dispatch_coordinator_leases_required"
        )
        leases = {}
    if not isinstance(lease_order, list):
        reasons.append(
            "dispatch_coordinator_lease_order_required"
        )
        lease_order = []

    if set(worker_order) != set(workers):
        reasons.append(
            "dispatch_coordinator_worker_order_mismatch"
        )
    if set(lease_order) != set(leases):
        reasons.append(
            "dispatch_coordinator_lease_order_mismatch"
        )

    for worker_id in worker_order:
        record = _mapping(workers.get(worker_id))
        if record.get("worker_id") != worker_id:
            reasons.append(
                f"dispatch_worker_identity_mismatch:{worker_id}"
            )
            continue
        for reason in validate_worker_record(record):
            reasons.append(f"{worker_id}:{reason}")

    for lease_id in lease_order:
        lease = _mapping(leases.get(lease_id))
        if lease.get("lease_id") != lease_id:
            reasons.append(
                f"dispatch_lease_identity_mismatch:{lease_id}"
            )
            continue
        for reason in validate_dispatch_lease(lease):
            reasons.append(f"{lease_id}:{reason}")

    return reasons


def create_dispatch_coordinator_state(
    *,
    state_path: Any,
    coordinator_name: str = "default",
    event_bus_state_path: Any = None,
    now: Any = None,
) -> dict[str, Any]:
    name = str(coordinator_name or "").strip()
    if not name:
        raise ValueError(
            "dispatch_coordinator_name_required"
        )

    destination = Path(state_path)
    at = time_text(now)
    identity = {
        "coordinator_name": name,
        "state_path": str(
            destination.resolve(strict=False)
        ).replace("\\", "/").casefold(),
    }

    return seal_dispatch_coordinator_state(
        {
            "contract": CONTRACT,
            "coordinator_id": (
                "dispatch-coordinator-"
                f"{fingerprint(identity)[:20]}"
            ),
            "coordinator_name": name,
            "coordinator_status": "created",
            "state_path": str(
                destination.resolve(strict=False)
            ),
            "event_bus_state_path": (
                str(
                    Path(
                        event_bus_state_path
                    ).resolve(strict=False)
                )
                if event_bus_state_path is not None
                else None
            ),
            "workers": {},
            "worker_order": [],
            "leases": {},
            "lease_order": [],
            "created_at": at,
            "updated_at": at,
            "last_event_id": None,
            "registered_worker_count": 0,
            "available_worker_count": 0,
            "busy_worker_count": 0,
            "stale_worker_count": 0,
            "failed_worker_count": 0,
            "dispatch_count": 0,
            "completed_dispatch_count": 0,
            "failed_dispatch_count": 0,
            "recovered_lease_count": 0,
            "failure": None,
        }
    )


def save_dispatch_coordinator_state(
    state: Mapping[str, Any],
    path: Any,
) -> dict[str, Any]:
    destination = Path(path)
    value = seal_dispatch_coordinator_state(state)
    reasons = validate_dispatch_coordinator_state(
        value
    )
    if reasons:
        raise ValueError(";".join(reasons))
    _atomic_write_json(value, destination)
    return value


def load_dispatch_coordinator_state(
    path: Any,
) -> dict[str, Any]:
    source = Path(path)
    if _unsafe(source):
        raise ValueError(
            "unsafe_dispatch_coordinator_state_path"
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
            "invalid_dispatch_coordinator_json"
        ) from exc

    reasons = validate_dispatch_coordinator_state(
        value
    )
    if reasons:
        raise ValueError(";".join(reasons))
    return value


def _publish_event(
    state: Mapping[str, Any],
    *,
    topic: str,
    payload: Mapping[str, Any],
    idempotency_key: str,
    now: Any = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    value = _mapping(state)
    state_path_text = str(
        value.get("event_bus_state_path") or ""
    ).strip()
    if not state_path_text:
        return value, None

    event_bus_path = Path(state_path_text)
    bus = load_event_bus_state(event_bus_path)
    bus, event = publish(
        bus,
        event_type="scheduler",
        topic=topic,
        source=value["coordinator_id"],
        payload=payload,
        idempotency_key=idempotency_key,
        correlation_id=str(
            payload.get("mission_id")
            or payload.get("worker_id")
            or value.get("coordinator_id")
        ),
        causation_id=str(
            payload.get("lease_id") or ""
        )
        or None,
        now=now,
    )
    save_event_bus_state(bus, event_bus_path)
    value["last_event_id"] = event.get(
        "event_id"
    )
    return (
        seal_dispatch_coordinator_state(value),
        event,
    )


def _recount_workers(
    state: Mapping[str, Any],
) -> dict[str, Any]:
    value = _mapping(state)
    workers = _mapping(value.get("workers"))
    statuses = [
        str(record.get("worker_status") or "")
        for record in workers.values()
    ]

    value["registered_worker_count"] = len(workers)
    value["available_worker_count"] = statuses.count(
        "available"
    )
    value["busy_worker_count"] = statuses.count(
        "busy"
    )
    value["stale_worker_count"] = statuses.count(
        "stale"
    )
    value["failed_worker_count"] = statuses.count(
        "failed"
    )
    return seal_dispatch_coordinator_state(value)


def register_worker(
    state: Mapping[str, Any],
    *,
    worker_state_path: Any,
    weight: int = 100,
    tags: list[str] | None = None,
    now: Any = None,
) -> dict[str, Any]:
    if (
        isinstance(weight, bool)
        or not isinstance(weight, int)
        or not 1 <= weight <= 1000
    ):
        raise ValueError("invalid_worker_weight")

    value = _mapping(state)
    worker = load_worker_state(worker_state_path)
    worker_id = str(
        worker.get("worker_id") or ""
    ).strip()
    if not worker_id:
        raise ValueError("worker_id_required")

    workers = _mapping(value.get("workers"))
    existing = _mapping(workers.get(worker_id))
    if existing:
        if existing.get("worker_state_path") != str(
            Path(worker_state_path).resolve(
                strict=False
            )
        ):
            raise ValueError(
                "worker_state_path_mismatch"
            )
        return value

    at = time_text(now)
    health_status = str(
        worker.get("worker_status") or ""
    )
    if health_status in {"failed"}:
        projected_status = "failed"
    elif health_status in {"stopped", "stopping"}:
        projected_status = "stopped"
    elif health_status == "paused":
        projected_status = "paused"
    elif worker.get("current_lease"):
        projected_status = "busy"
    else:
        projected_status = "available"

    record = seal_worker_record(
        {
            "contract": WORKER_RECORD_CONTRACT,
            "worker_id": worker_id,
            "worker_name": worker.get(
                "worker_name"
            ),
            "worker_state_path": str(
                Path(worker_state_path).resolve(
                    strict=False
                )
            ),
            "worker_status": projected_status,
            "weight": weight,
            "tags": sorted(
                {
                    str(item).strip()
                    for item in (tags or [])
                    if str(item).strip()
                }
            ),
            "registered_at": at,
            "updated_at": at,
            "last_heartbeat_at": worker.get(
                "last_heartbeat_at"
            ),
            "last_seen_loop_iteration": int(
                worker.get("loop_iteration") or 0
            ),
            "successful_dispatches": int(
                worker.get(
                    "successful_dispatches"
                )
                or 0
            ),
            "failed_dispatches": int(
                worker.get("failed_dispatches") or 0
            ),
            "active_lease_id": None,
            "last_assigned_at": None,
            "last_completed_at": None,
            "last_failure": deepcopy(
                worker.get("failure")
            ),
        }
    )

    workers[worker_id] = record
    value["workers"] = workers
    value.setdefault("worker_order", []).append(
        worker_id
    )
    value["updated_at"] = at
    value = _recount_workers(value)
    value, _ = _publish_event(
        value,
        topic="dispatch.worker_registered",
        payload={
            "coordinator_id": value[
                "coordinator_id"
            ],
            "worker_id": worker_id,
            "worker_name": record["worker_name"],
            "worker_status": projected_status,
        },
        idempotency_key=(
            f"{value['coordinator_id']}:"
            f"worker_registered:{worker_id}"
        ),
        now=now,
    )
    return value


def refresh_workers(
    state: Mapping[str, Any],
    *,
    now: Any = None,
) -> dict[str, Any]:
    value = _mapping(state)
    current = parse_time(
        now or datetime.now(timezone.utc)
    )
    workers = _mapping(value.get("workers"))

    for worker_id in value.get("worker_order", []):
        record = _mapping(workers.get(worker_id))
        try:
            worker = load_worker_state(
                record["worker_state_path"]
            )
        except ValueError as exc:
            record["worker_status"] = "failed"
            record["last_failure"] = {
                "reasons": [
                    f"{type(exc).__name__}:{exc}"
                ]
            }
            record["updated_at"] = time_text(now)
            workers[worker_id] = seal_worker_record(
                record
            )
            continue

        heartbeat_text = worker.get(
            "last_heartbeat_at"
        )
        try:
            fresh = (
                current - parse_time(heartbeat_text)
            ).total_seconds() <= HEARTBEAT_FRESH_SECONDS
        except (TypeError, ValueError):
            fresh = False

        status = str(
            worker.get("worker_status") or ""
        )
        if not fresh:
            projected = "stale"
        elif status == "failed":
            projected = "failed"
        elif status in {"stopped", "stopping"}:
            projected = "stopped"
        elif status == "paused":
            projected = "paused"
        elif record.get("active_lease_id"):
            projected = "busy"
        else:
            projected = "available"

        record["worker_status"] = projected
        record["last_heartbeat_at"] = (
            heartbeat_text
        )
        record["last_seen_loop_iteration"] = int(
            worker.get("loop_iteration") or 0
        )
        record["successful_dispatches"] = int(
            worker.get(
                "successful_dispatches"
            )
            or 0
        )
        record["failed_dispatches"] = int(
            worker.get("failed_dispatches") or 0
        )
        record["last_failure"] = deepcopy(
            worker.get("failure")
        )
        record["updated_at"] = time_text(now)
        workers[worker_id] = seal_worker_record(
            record
        )

    value["workers"] = workers
    value["updated_at"] = time_text(now)
    return _recount_workers(value)


def _recover_expired_leases(
    state: Mapping[str, Any],
    *,
    now: Any = None,
) -> dict[str, Any]:
    value = _mapping(state)
    current = parse_time(
        now or datetime.now(timezone.utc)
    )
    workers = _mapping(value.get("workers"))
    leases = _mapping(value.get("leases"))
    recovered = 0

    for lease_id in value.get("lease_order", []):
        lease = _mapping(leases.get(lease_id))
        if lease.get("lease_status") != "active":
            continue

        try:
            expired = (
                parse_time(lease.get("expires_at"))
                <= current
            )
        except (TypeError, ValueError):
            expired = True

        if not expired:
            continue

        lease["lease_status"] = "expired"
        lease["completed_at"] = time_text(now)
        lease["failure"] = {
            "reason": "dispatch_worker_lease_expired"
        }
        leases[lease_id] = seal_dispatch_lease(
            lease
        )

        worker_id = lease.get("worker_id")
        record = _mapping(workers.get(worker_id))
        if record:
            record["active_lease_id"] = None
            record["worker_status"] = "available"
            record["updated_at"] = time_text(now)
            workers[worker_id] = seal_worker_record(
                record
            )
        recovered += 1

    value["workers"] = workers
    value["leases"] = leases
    value["recovered_lease_count"] = int(
        value.get("recovered_lease_count") or 0
    ) + recovered
    value["updated_at"] = time_text(now)
    return _recount_workers(value)


def _worker_score(
    record: Mapping[str, Any],
) -> tuple[int, int, str]:
    value = _mapping(record)
    successful = int(
        value.get("successful_dispatches") or 0
    )
    failed = int(
        value.get("failed_dispatches") or 0
    )
    load_penalty = 1 if value.get(
        "active_lease_id"
    ) else 0
    effective_weight = int(
        value.get("weight") or 100
    )
    reliability = successful - failed
    return (
        load_penalty,
        -(effective_weight + reliability),
        str(value.get("worker_id") or ""),
    )


def select_available_worker(
    state: Mapping[str, Any],
    *,
    required_tags: list[str] | None = None,
    now: Any = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    value = refresh_workers(
        _recover_expired_leases(
            state,
            now=now,
        ),
        now=now,
    )

    required = {
        str(item).strip()
        for item in (required_tags or [])
        if str(item).strip()
    }
    candidates: list[dict[str, Any]] = []

    for worker_id in value.get("worker_order", []):
        record = _mapping(
            _mapping(value.get("workers")).get(
                worker_id
            )
        )
        if record.get("worker_status") != "available":
            continue
        tags = set(record.get("tags") or [])
        if not required.issubset(tags):
            continue
        candidates.append(record)

    candidates.sort(key=_worker_score)
    return value, (
        deepcopy(candidates[0])
        if candidates
        else None
    )


def acquire_worker_lease(
    state: Mapping[str, Any],
    *,
    mission_id: str,
    entry_id: str,
    required_tags: list[str] | None = None,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    now: Any = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    mission_text = str(mission_id or "").strip()
    entry_text = str(entry_id or "").strip()
    if not mission_text:
        raise ValueError("mission_id_required")
    if not entry_text:
        raise ValueError("entry_id_required")
    if (
        isinstance(lease_seconds, bool)
        or not isinstance(lease_seconds, int)
        or lease_seconds < 1
    ):
        raise ValueError(
            "invalid_dispatch_worker_lease_seconds"
        )

    value, worker = select_available_worker(
        state,
        required_tags=required_tags,
        now=now,
    )
    if worker is None:
        value["coordinator_status"] = "idle"
        value["updated_at"] = time_text(now)
        value, _ = _publish_event(
            value,
            topic="dispatch.no_worker_available",
            payload={
                "coordinator_id": value[
                    "coordinator_id"
                ],
                "mission_id": mission_text,
                "entry_id": entry_text,
                "required_tags": sorted(
                    {
                        str(item).strip()
                        for item in (
                            required_tags or []
                        )
                        if str(item).strip()
                    }
                ),
            },
            idempotency_key=(
                f"{value['coordinator_id']}:"
                f"no_worker:{mission_text}:"
                f"{entry_text}"
            ),
            now=now,
        )
        return (
            seal_dispatch_coordinator_state(value),
            None,
        )

    at = parse_time(
        now or datetime.now(timezone.utc)
    )
    acquired_at = time_text(at)
    expires_at = time_text(
        at + timedelta(seconds=lease_seconds)
    )
    identity = {
        "coordinator_id": value[
            "coordinator_id"
        ],
        "worker_id": worker["worker_id"],
        "mission_id": mission_text,
        "entry_id": entry_text,
        "acquired_at": acquired_at,
    }
    lease_id = (
        "dispatch-worker-lease-"
        f"{fingerprint(identity)[:20]}"
    )

    lease = seal_dispatch_lease(
        {
            "contract": LEASE_CONTRACT,
            "lease_id": lease_id,
            "lease_status": "active",
            "worker_id": worker["worker_id"],
            "worker_name": worker["worker_name"],
            "mission_id": mission_text,
            "entry_id": entry_text,
            "required_tags": sorted(
                {
                    str(item).strip()
                    for item in (
                        required_tags or []
                    )
                    if str(item).strip()
                }
            ),
            "acquired_at": acquired_at,
            "expires_at": expires_at,
            "completed_at": None,
            "result": None,
            "failure": None,
        }
    )

    leases = _mapping(value.get("leases"))
    leases[lease_id] = lease
    value["leases"] = leases
    value.setdefault("lease_order", []).append(
        lease_id
    )

    workers = _mapping(value.get("workers"))
    record = _mapping(
        workers.get(worker["worker_id"])
    )
    record["worker_status"] = "busy"
    record["active_lease_id"] = lease_id
    record["last_assigned_at"] = acquired_at
    record["updated_at"] = acquired_at
    workers[worker["worker_id"]] = (
        seal_worker_record(record)
    )
    value["workers"] = workers
    value["dispatch_count"] = int(
        value.get("dispatch_count") or 0
    ) + 1
    value["coordinator_status"] = "running"
    value["updated_at"] = acquired_at
    value = _recount_workers(value)
    value, _ = _publish_event(
        value,
        topic="dispatch.assigned",
        payload={
            "coordinator_id": value[
                "coordinator_id"
            ],
            "lease_id": lease_id,
            "worker_id": worker["worker_id"],
            "worker_name": worker["worker_name"],
            "mission_id": mission_text,
            "entry_id": entry_text,
            "expires_at": expires_at,
        },
        idempotency_key=(
            f"{value['coordinator_id']}:"
            f"dispatch_assigned:{lease_id}"
        ),
        now=now,
    )
    return value, lease


def complete_worker_lease(
    state: Mapping[str, Any],
    *,
    lease_id: str,
    result: Mapping[str, Any] | None = None,
    failed: bool = False,
    now: Any = None,
) -> dict[str, Any]:
    value = _mapping(state)
    leases = _mapping(value.get("leases"))
    lease = _mapping(leases.get(lease_id))
    if not lease:
        raise ValueError(
            "dispatch_worker_lease_not_found"
        )
    if lease.get("lease_status") != "active":
        return value

    at = time_text(now)
    lease["lease_status"] = (
        "failed" if failed else "completed"
    )
    lease["completed_at"] = at
    lease["result"] = _mapping(result)
    lease["failure"] = (
        deepcopy(_mapping(result).get("failure"))
        if failed
        else None
    )
    leases[lease_id] = seal_dispatch_lease(lease)
    value["leases"] = leases

    workers = _mapping(value.get("workers"))
    worker_id = lease["worker_id"]
    record = _mapping(workers.get(worker_id))
    if record:
        record["active_lease_id"] = None
        record["worker_status"] = (
            "failed" if failed else "available"
        )
        record["last_completed_at"] = at
        record["last_failure"] = (
            deepcopy(lease.get("failure"))
            if failed
            else None
        )
        record["updated_at"] = at
        workers[worker_id] = seal_worker_record(
            record
        )
    value["workers"] = workers

    if failed:
        value["failed_dispatch_count"] = int(
            value.get("failed_dispatch_count") or 0
        ) + 1
    else:
        value["completed_dispatch_count"] = int(
            value.get(
                "completed_dispatch_count"
            )
            or 0
        ) + 1

    value["updated_at"] = at
    value = _recount_workers(value)
    topic = (
        "dispatch.failed"
        if failed
        else "dispatch.completed"
    )
    value, _ = _publish_event(
        value,
        topic=topic,
        payload={
            "coordinator_id": value[
                "coordinator_id"
            ],
            "lease_id": lease_id,
            "worker_id": worker_id,
            "mission_id": lease["mission_id"],
            "entry_id": lease["entry_id"],
            "lease_status": lease[
                "lease_status"
            ],
            "result": _mapping(result),
        },
        idempotency_key=(
            f"{value['coordinator_id']}:"
            f"{topic}:{lease_id}"
        ),
        now=now,
    )
    return value


__all__ = [
    "CONTRACT",
    "DEFAULT_LEASE_SECONDS",
    "HEARTBEAT_FRESH_SECONDS",
    "LEASE_CONTRACT",
    "VALID_COORDINATOR_STATUSES",
    "VALID_LEASE_STATUSES",
    "VALID_WORKER_STATUSES",
    "WORKER_RECORD_CONTRACT",
    "acquire_worker_lease",
    "complete_worker_lease",
    "create_dispatch_coordinator_state",
    "load_dispatch_coordinator_state",
    "refresh_workers",
    "register_worker",
    "save_dispatch_coordinator_state",
    "seal_dispatch_coordinator_state",
    "seal_dispatch_lease",
    "seal_worker_record",
    "select_available_worker",
    "validate_dispatch_coordinator_state",
    "validate_dispatch_lease",
    "validate_worker_record",
]
