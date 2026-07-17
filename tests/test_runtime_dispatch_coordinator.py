from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

import core.runtime.runtime_dispatch_coordinator as coordinator_module
from core.runtime.runtime_dispatch_coordinator import (
    CONTRACT,
    LEASE_CONTRACT,
    WORKER_RECORD_CONTRACT,
    acquire_worker_lease,
    complete_worker_lease,
    create_dispatch_coordinator_state,
    load_dispatch_coordinator_state,
    refresh_workers,
    register_worker,
    save_dispatch_coordinator_state,
    select_available_worker,
    validate_dispatch_coordinator_state,
    validate_dispatch_lease,
    validate_worker_record,
)
from core.runtime.runtime_session_queue import (
    create_scheduler_state,
    save_scheduler_state,
)
from core.runtime.runtime_worker_service import (
    create_worker_state,
    save_worker_state,
)


NOW = datetime(2026, 7, 12, 7, 0, 0, tzinfo=timezone.utc)


def _create_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    name: str,
    status: str = "idle",
    heartbeat_at: datetime = NOW,
    successful_dispatches: int = 0,
    failed_dispatches: int = 0,
    current_lease: dict[str, Any] | None = None,
) -> tuple[Path, dict[str, Any]]:
    del monkeypatch

    scheduler_path = tmp_path / f"{name}.scheduler.json"
    worker_path = tmp_path / f"{name}.worker.json"

    scheduler = create_scheduler_state(
        state_path=scheduler_path,
        now=NOW,
    )
    save_scheduler_state(
        scheduler,
        scheduler_path,
    )

    worker = create_worker_state(
        scheduler_state_path=scheduler_path,
        worker_state_path=worker_path,
        worker_name=name,
        now=NOW,
    )
    worker["worker_status"] = status
    worker["last_heartbeat_at"] = heartbeat_at.isoformat()
    worker["updated_at"] = heartbeat_at.isoformat()
    worker["successful_dispatches"] = successful_dispatches
    worker["failed_dispatches"] = failed_dispatches
    worker["current_lease"] = deepcopy(current_lease)
    worker["current_session_id"] = (
        current_lease.get("session_id")
        if current_lease
        else None
    )
    worker = save_worker_state(worker, worker_path)
    return worker_path, worker


def _create_state(
    tmp_path: Path,
) -> tuple[Path, dict[str, Any]]:
    state_path = tmp_path / "dispatch-coordinator.json"
    state = create_dispatch_coordinator_state(
        state_path=state_path,
        coordinator_name="primary",
        now=NOW,
    )
    return state_path, state


def test_create_save_and_load_coordinator_state(
    tmp_path: Path,
) -> None:
    state_path, state = _create_state(tmp_path)

    assert state["contract"] == CONTRACT
    assert state["coordinator_name"] == "primary"
    assert state["coordinator_status"] == "created"
    assert state["workers"] == {}
    assert state["worker_order"] == []
    assert state["leases"] == {}
    assert state["lease_order"] == []
    assert validate_dispatch_coordinator_state(state) == []

    saved = save_dispatch_coordinator_state(
        state,
        state_path,
    )
    loaded = load_dispatch_coordinator_state(
        state_path
    )

    assert state_path.exists()
    assert loaded == saved
    assert loaded["coordinator_fingerprint"] == (
        saved["coordinator_fingerprint"]
    )


def test_register_worker_creates_valid_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, state = _create_state(tmp_path)
    worker_path, worker = _create_worker(
        tmp_path,
        monkeypatch,
        name="worker-1",
    )

    result = register_worker(
        state,
        worker_state_path=worker_path,
        weight=150,
        tags=["python", "windows", "python"],
        now=NOW,
    )

    assert result["registered_worker_count"] == 1
    assert result["available_worker_count"] == 1
    worker_id = result["worker_order"][0]
    record = result["workers"][worker_id]

    assert worker_id == worker["worker_id"]
    assert record["contract"] == WORKER_RECORD_CONTRACT
    assert record["worker_name"] == "worker-1"
    assert record["worker_status"] == "available"
    assert record["weight"] == 150
    assert record["tags"] == ["python", "windows"]
    assert validate_worker_record(record) == []


def test_register_worker_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, state = _create_state(tmp_path)
    worker_path, _ = _create_worker(
        tmp_path,
        monkeypatch,
        name="worker-1",
    )

    first = register_worker(
        state,
        worker_state_path=worker_path,
        weight=100,
        now=NOW,
    )
    second = register_worker(
        first,
        worker_state_path=worker_path,
        weight=999,
        now=NOW + timedelta(seconds=1),
    )

    assert second == first
    assert len(second["worker_order"]) == 1
    record = second["workers"][
        second["worker_order"][0]
    ]
    assert record["weight"] == 100


def test_refresh_workers_marks_stale_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, state = _create_state(tmp_path)
    worker_path, _ = _create_worker(
        tmp_path,
        monkeypatch,
        name="worker-1",
        heartbeat_at=NOW - timedelta(seconds=91),
    )
    state = register_worker(
        state,
        worker_state_path=worker_path,
        now=NOW - timedelta(seconds=91),
    )

    refreshed = refresh_workers(
        state,
        now=NOW,
    )

    worker_id = refreshed["worker_order"][0]
    record = refreshed["workers"][worker_id]

    assert record["worker_status"] == "stale"
    assert refreshed["stale_worker_count"] == 1
    assert refreshed["available_worker_count"] == 0


def test_refresh_workers_projects_failed_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, state = _create_state(tmp_path)
    worker_path, _ = _create_worker(
        tmp_path,
        monkeypatch,
        name="worker-1",
        status="failed",
    )
    state = register_worker(
        state,
        worker_state_path=worker_path,
        now=NOW,
    )

    refreshed = refresh_workers(
        state,
        now=NOW,
    )

    worker_id = refreshed["worker_order"][0]
    assert refreshed["workers"][worker_id][
        "worker_status"
    ] == "failed"
    assert refreshed["failed_worker_count"] == 1


def test_select_available_worker_honors_required_tags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, state = _create_state(tmp_path)
    first_path, first_worker = _create_worker(
        tmp_path,
        monkeypatch,
        name="worker-1",
    )
    second_path, second_worker = _create_worker(
        tmp_path,
        monkeypatch,
        name="worker-2",
    )

    state = register_worker(
        state,
        worker_state_path=first_path,
        tags=["python"],
        now=NOW,
    )
    state = register_worker(
        state,
        worker_state_path=second_path,
        tags=["python", "gpu"],
        now=NOW,
    )

    refreshed, selected = select_available_worker(
        state,
        required_tags=["gpu"],
        now=NOW,
    )

    assert refreshed["available_worker_count"] == 2
    assert selected is not None
    assert selected["worker_id"] == second_worker["worker_id"]
    assert selected["worker_id"] != first_worker["worker_id"]


def test_select_available_worker_uses_weight_and_reliability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, state = _create_state(tmp_path)
    first_path, _ = _create_worker(
        tmp_path,
        monkeypatch,
        name="worker-1",
        successful_dispatches=10,
        failed_dispatches=0,
    )
    second_path, second_worker = _create_worker(
        tmp_path,
        monkeypatch,
        name="worker-2",
        successful_dispatches=0,
        failed_dispatches=0,
    )

    state = register_worker(
        state,
        worker_state_path=first_path,
        weight=50,
        now=NOW,
    )
    state = register_worker(
        state,
        worker_state_path=second_path,
        weight=100,
        now=NOW,
    )

    _, selected = select_available_worker(
        state,
        now=NOW,
    )

    assert selected is not None
    assert selected["worker_id"] == second_worker["worker_id"]


def test_acquire_worker_lease_marks_worker_busy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, state = _create_state(tmp_path)
    worker_path, worker = _create_worker(
        tmp_path,
        monkeypatch,
        name="worker-1",
    )
    state = register_worker(
        state,
        worker_state_path=worker_path,
        now=NOW,
    )

    leased_state, lease = acquire_worker_lease(
        state,
        mission_id="mission-1",
        entry_id="entry-1",
        lease_seconds=60,
        now=NOW,
    )

    assert lease is not None
    assert lease["contract"] == LEASE_CONTRACT
    assert lease["lease_status"] == "active"
    assert lease["worker_id"] == worker["worker_id"]
    assert lease["mission_id"] == "mission-1"
    assert lease["entry_id"] == "entry-1"
    assert validate_dispatch_lease(lease) == []

    record = leased_state["workers"][worker["worker_id"]]
    assert record["worker_status"] == "busy"
    assert record["active_lease_id"] == lease["lease_id"]
    assert leased_state["busy_worker_count"] == 1
    assert leased_state["available_worker_count"] == 0
    assert leased_state["dispatch_count"] == 1


def test_acquire_worker_lease_returns_none_when_no_worker_available(
    tmp_path: Path,
) -> None:
    _, state = _create_state(tmp_path)

    result, lease = acquire_worker_lease(
        state,
        mission_id="mission-1",
        entry_id="entry-1",
        now=NOW,
    )

    assert lease is None
    assert result["coordinator_status"] == "idle"
    assert result["dispatch_count"] == 0


def test_complete_worker_lease_returns_worker_to_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, state = _create_state(tmp_path)
    worker_path, worker = _create_worker(
        tmp_path,
        monkeypatch,
        name="worker-1",
    )
    state = register_worker(
        state,
        worker_state_path=worker_path,
        now=NOW,
    )
    state, lease = acquire_worker_lease(
        state,
        mission_id="mission-1",
        entry_id="entry-1",
        now=NOW,
    )
    assert lease is not None

    completed = complete_worker_lease(
        state,
        lease_id=lease["lease_id"],
        result={"ok": True},
        now=NOW + timedelta(seconds=5),
    )

    saved_lease = completed["leases"][lease["lease_id"]]
    record = completed["workers"][worker["worker_id"]]

    assert saved_lease["lease_status"] == "completed"
    assert saved_lease["result"] == {"ok": True}
    assert record["worker_status"] == "available"
    assert record["active_lease_id"] is None
    assert completed["completed_dispatch_count"] == 1
    assert completed["failed_dispatch_count"] == 0


def test_complete_failed_worker_lease_marks_worker_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, state = _create_state(tmp_path)
    worker_path, worker = _create_worker(
        tmp_path,
        monkeypatch,
        name="worker-1",
    )
    state = register_worker(
        state,
        worker_state_path=worker_path,
        now=NOW,
    )
    state, lease = acquire_worker_lease(
        state,
        mission_id="mission-1",
        entry_id="entry-1",
        now=NOW,
    )
    assert lease is not None

    failed = complete_worker_lease(
        state,
        lease_id=lease["lease_id"],
        result={
            "failure": {
                "reasons": ["execution_failed"]
            }
        },
        failed=True,
        now=NOW + timedelta(seconds=5),
    )

    saved_lease = failed["leases"][lease["lease_id"]]
    record = failed["workers"][worker["worker_id"]]

    assert saved_lease["lease_status"] == "failed"
    assert record["worker_status"] == "failed"
    assert failed["failed_dispatch_count"] == 1
    assert failed["failed_worker_count"] == 1


def test_expired_worker_lease_is_recovered(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, state = _create_state(tmp_path)
    worker_path, worker = _create_worker(
        tmp_path,
        monkeypatch,
        name="worker-1",
    )
    state = register_worker(
        state,
        worker_state_path=worker_path,
        now=NOW,
    )
    state, first_lease = acquire_worker_lease(
        state,
        mission_id="mission-1",
        entry_id="entry-1",
        lease_seconds=1,
        now=NOW,
    )
    assert first_lease is not None

    recovered, second_lease = acquire_worker_lease(
        state,
        mission_id="mission-2",
        entry_id="entry-2",
        lease_seconds=60,
        now=NOW + timedelta(seconds=2),
    )

    assert second_lease is not None
    assert second_lease["lease_id"] != first_lease["lease_id"]
    first_saved = recovered["leases"][
        first_lease["lease_id"]
    ]
    assert first_saved["lease_status"] == "expired"
    assert recovered["recovered_lease_count"] == 1
    assert recovered["workers"][worker["worker_id"]][
        "active_lease_id"
    ] == second_lease["lease_id"]


def test_event_bus_integration_publishes_dispatch_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.runtime.runtime_event_bus import (
        create_event_bus_state,
        replay,
        save_event_bus_state,
    )

    event_bus_path = tmp_path / "event-bus.json"
    bus = create_event_bus_state(
        state_path=event_bus_path,
        now=NOW,
    )
    save_event_bus_state(bus, event_bus_path)

    state_path = tmp_path / "dispatch-coordinator.json"
    state = create_dispatch_coordinator_state(
        state_path=state_path,
        coordinator_name="primary",
        event_bus_state_path=event_bus_path,
        now=NOW,
    )

    worker_path, _ = _create_worker(
        tmp_path,
        monkeypatch,
        name="worker-1",
    )
    state = register_worker(
        state,
        worker_state_path=worker_path,
        now=NOW,
    )
    state, lease = acquire_worker_lease(
        state,
        mission_id="mission-1",
        entry_id="entry-1",
        now=NOW,
    )
    assert lease is not None
    state = complete_worker_lease(
        state,
        lease_id=lease["lease_id"],
        result={"ok": True},
        now=NOW + timedelta(seconds=1),
    )

    from core.runtime.runtime_event_bus import load_event_bus_state

    loaded_bus = load_event_bus_state(event_bus_path)
    topics = [
        event["topic"]
        for event in replay(loaded_bus)
    ]

    assert "dispatch.worker_registered" in topics
    assert "dispatch.assigned" in topics
    assert "dispatch.completed" in topics
    assert state["last_event_id"] is not None


def test_tampered_worker_record_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, state = _create_state(tmp_path)
    worker_path, _ = _create_worker(
        tmp_path,
        monkeypatch,
        name="worker-1",
    )
    state = register_worker(
        state,
        worker_state_path=worker_path,
        now=NOW,
    )

    worker_id = state["worker_order"][0]
    record = deepcopy(state["workers"][worker_id])
    record["worker_status"] = "failed"

    reasons = validate_worker_record(record)

    assert (
        "dispatch_worker_record_fingerprint_mismatch"
        in reasons
    )


def test_tampered_coordinator_state_is_rejected(
    tmp_path: Path,
) -> None:
    _, state = _create_state(tmp_path)
    state["dispatch_count"] = 999

    reasons = validate_dispatch_coordinator_state(
        state
    )

    assert (
        "dispatch_coordinator_fingerprint_mismatch"
        in reasons
    )
