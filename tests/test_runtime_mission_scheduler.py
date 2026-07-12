from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

import core.runtime.runtime_mission_scheduler as scheduler_module
from core.runtime.runtime_mission_scheduler import (
    CONTRACT,
    ENTRY_CONTRACT,
    create_mission_scheduler_state,
    enqueue_mission,
    lease_next_mission,
    load_mission_scheduler_state,
    release_mission_lease,
    request_mission_scheduler_action,
    run_mission_scheduler_iteration,
    save_mission_scheduler_state,
    validate_mission_scheduler_entry,
    validate_mission_scheduler_state,
)


NOW = datetime(2026, 7, 12, 4, 0, 0, tzinfo=timezone.utc)


def _mission(
    *,
    mission_id: str = "mission-1",
    mission_status: str = "running",
    scheduler_state_path: str = "runtime-session-scheduler.json",
) -> dict[str, Any]:
    return {
        "mission_id": mission_id,
        "mission_status": mission_status,
        "scheduler_state_path": scheduler_state_path,
    }


def _patch_missions(
    monkeypatch: pytest.MonkeyPatch,
    missions: dict[str, dict[str, Any]],
) -> None:
    normalized = {
        str(Path(path).resolve(strict=False)): deepcopy(value)
        for path, value in missions.items()
    }

    def fake_load_mission(
        path: Any,
        *,
        check_expiry: bool = False,
    ) -> dict[str, Any]:
        del check_expiry
        key = str(Path(path).resolve(strict=False))
        if key not in normalized:
            raise ValueError("unknown_test_mission")
        return deepcopy(normalized[key])

    monkeypatch.setattr(
        scheduler_module,
        "load_mission",
        fake_load_mission,
    )


class FakeMissionDriver:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = deepcopy(result)
        self.calls: list[dict[str, Any]] = []

    def run_mission(
        self,
        mission: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "mission": str(mission),
                "kwargs": deepcopy(kwargs),
            }
        )
        return deepcopy(self.result)


def test_create_save_and_load_scheduler_state(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "mission-scheduler.json"

    state = create_mission_scheduler_state(
        state_path=state_path,
        scheduler_name="primary",
        now=NOW,
    )

    assert state["contract"] == CONTRACT
    assert state["scheduler_status"] == "created"
    assert state["entries"] == {}
    assert state["entry_order"] == []
    assert validate_mission_scheduler_state(state) == []

    saved = save_mission_scheduler_state(
        state,
        state_path,
    )
    loaded = load_mission_scheduler_state(
        state_path
    )

    assert state_path.exists()
    assert loaded == saved
    assert loaded["scheduler_fingerprint"] == (
        saved["scheduler_fingerprint"]
    )


def test_enqueue_mission_creates_valid_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "mission-scheduler.json"
    mission_path = tmp_path / "mission-1.json"
    _patch_missions(
        monkeypatch,
        {
            str(mission_path): _mission(),
        },
    )

    state = create_mission_scheduler_state(
        state_path=state_path,
        now=NOW,
    )
    result = enqueue_mission(
        state,
        mission_path,
        priority=25,
        now=NOW,
    )

    assert len(result["entry_order"]) == 1
    entry_id = result["entry_order"][0]
    entry = result["entries"][entry_id]

    assert entry["contract"] == ENTRY_CONTRACT
    assert entry["mission_id"] == "mission-1"
    assert entry["mission_path"] == str(
        mission_path.resolve(strict=False)
    )
    assert entry["entry_status"] == "queued"
    assert entry["priority"] == 25
    assert entry["attempt_count"] == 0
    assert validate_mission_scheduler_entry(entry) == []
    assert validate_mission_scheduler_state(result) == []


def test_enqueue_mission_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "mission-scheduler.json"
    mission_path = tmp_path / "mission-1.json"
    _patch_missions(
        monkeypatch,
        {
            str(mission_path): _mission(),
        },
    )

    state = create_mission_scheduler_state(
        state_path=state_path,
        now=NOW,
    )
    first = enqueue_mission(
        state,
        mission_path,
        priority=10,
        now=NOW,
    )
    second = enqueue_mission(
        first,
        mission_path,
        priority=99,
        now=NOW + timedelta(seconds=1),
    )

    assert second == first
    assert len(second["entry_order"]) == 1
    entry = second["entries"][
        second["entry_order"][0]
    ]
    assert entry["priority"] == 10


def test_terminal_mission_is_enqueued_as_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "mission-scheduler.json"
    mission_path = tmp_path / "mission-complete.json"
    _patch_missions(
        monkeypatch,
        {
            str(mission_path): _mission(
                mission_id="mission-complete",
                mission_status="completed",
            ),
        },
    )

    state = create_mission_scheduler_state(
        state_path=state_path,
        now=NOW,
    )
    result = enqueue_mission(
        state,
        mission_path,
        now=NOW,
    )
    entry = result["entries"][
        result["entry_order"][0]
    ]

    assert entry["entry_status"] == "completed"
    assert entry["completed_at"] is not None


def test_lease_next_mission_uses_priority_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "mission-scheduler.json"
    low_path = tmp_path / "low.json"
    high_path = tmp_path / "high.json"
    _patch_missions(
        monkeypatch,
        {
            str(low_path): _mission(
                mission_id="mission-low"
            ),
            str(high_path): _mission(
                mission_id="mission-high"
            ),
        },
    )

    state = create_mission_scheduler_state(
        state_path=state_path,
        now=NOW,
    )
    state = enqueue_mission(
        state,
        low_path,
        priority=1,
        now=NOW,
    )
    state = enqueue_mission(
        state,
        high_path,
        priority=50,
        now=NOW,
    )

    leased, lease = lease_next_mission(
        state,
        owner="scheduler-worker-1",
        lease_seconds=60,
        now=NOW,
    )

    assert lease is not None
    entry = leased["entries"][
        leased["current_entry_id"]
    ]
    assert entry["mission_id"] == "mission-high"
    assert entry["entry_status"] == "leased"
    assert entry["lease"]["owner"] == (
        "scheduler-worker-1"
    )


def test_release_mission_lease_updates_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "mission-scheduler.json"
    mission_path = tmp_path / "mission-1.json"
    _patch_missions(
        monkeypatch,
        {
            str(mission_path): _mission(),
        },
    )

    state = create_mission_scheduler_state(
        state_path=state_path,
        now=NOW,
    )
    state = enqueue_mission(
        state,
        mission_path,
        now=NOW,
    )
    state, lease = lease_next_mission(
        state,
        owner="scheduler-worker-1",
        now=NOW,
    )
    assert lease is not None

    entry_id = state["current_entry_id"]
    released = release_mission_lease(
        state,
        entry_id=entry_id,
        lease_id=lease["lease_id"],
        owner="scheduler-worker-1",
        next_status="completed",
        now=NOW + timedelta(seconds=5),
    )

    entry = released["entries"][entry_id]
    assert entry["entry_status"] == "completed"
    assert entry["lease"] is None
    assert entry["completed_at"] is not None
    assert released["current_entry_id"] is None
    assert released["current_mission_id"] is None


def test_expired_lease_is_recovered_and_released_again(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "mission-scheduler.json"
    mission_path = tmp_path / "mission-1.json"
    _patch_missions(
        monkeypatch,
        {
            str(mission_path): _mission(),
        },
    )

    state = create_mission_scheduler_state(
        state_path=state_path,
        now=NOW,
    )
    state = enqueue_mission(
        state,
        mission_path,
        now=NOW,
    )
    state, first_lease = lease_next_mission(
        state,
        owner="scheduler-worker-1",
        lease_seconds=1,
        now=NOW,
    )
    assert first_lease is not None

    recovered, second_lease = lease_next_mission(
        state,
        owner="scheduler-worker-2",
        lease_seconds=60,
        now=NOW + timedelta(seconds=2),
    )

    assert second_lease is not None
    assert second_lease["lease_id"] != (
        first_lease["lease_id"]
    )
    entry = recovered["entries"][
        recovered["current_entry_id"]
    ]
    assert entry["entry_status"] == "leased"
    assert entry["lease"]["owner"] == (
        "scheduler-worker-2"
    )
    assert recovered["recovered_leases"] == 1


@pytest.mark.parametrize(
    ("action", "expected_status", "pause", "stop"),
    [
        ("pause", "paused", True, False),
        ("resume", "idle", False, False),
        ("stop", "stopping", False, True),
    ],
)
def test_request_scheduler_action(
    tmp_path: Path,
    action: str,
    expected_status: str,
    pause: bool,
    stop: bool,
) -> None:
    state = create_mission_scheduler_state(
        state_path=tmp_path / "scheduler.json",
        now=NOW,
    )

    result = request_mission_scheduler_action(
        state,
        action,
        now=NOW,
    )

    assert result["scheduler_status"] == (
        expected_status
    )
    assert result["pause_requested"] is pause
    assert result["stop_requested"] is stop
    assert validate_mission_scheduler_state(result) == []


def test_scheduler_iteration_marks_completed_mission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_state_path = (
        tmp_path / "mission-scheduler.json"
    )
    mission_path = tmp_path / "mission-1.json"
    runtime_session_scheduler = (
        tmp_path / "runtime-session-scheduler.json"
    )
    _patch_missions(
        monkeypatch,
        {
            str(mission_path): _mission(
                scheduler_state_path=str(
                    runtime_session_scheduler
                )
            ),
        },
    )

    state = create_mission_scheduler_state(
        state_path=scheduler_state_path,
        now=NOW,
    )
    state = enqueue_mission(
        state,
        mission_path,
        now=NOW,
    )
    save_mission_scheduler_state(
        state,
        scheduler_state_path,
    )

    driver = FakeMissionDriver(
        {
            "driver_status": "completed",
            "mission_status": "completed",
            "mission_completed": True,
            "mission_waiting": False,
            "stopped_reason": "mission_completed",
        }
    )

    result = run_mission_scheduler_iteration(
        scheduler_state_path=scheduler_state_path,
        worker_state_path=tmp_path / "worker.json",
        worker_name="worker-1",
        target_root=tmp_path / "target",
        workspace_root=tmp_path / "workspace",
        mission_driver=driver,
        owner="mission-runtime-test",
        now=NOW,
    )

    entry = result["entries"][
        result["entry_order"][0]
    ]
    assert len(driver.calls) == 1
    assert entry["entry_status"] == "completed"
    assert entry["mission_status"] == "completed"
    assert entry["lease"] is None
    assert entry["attempt_count"] == 1
    assert result["completed_missions"] == 1
    assert result["last_result"]["dispatched"] is True
    assert result["last_result"]["mission_status"] == (
        "completed"
    )


def test_scheduler_iteration_preserves_waiting_mission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_state_path = (
        tmp_path / "mission-scheduler.json"
    )
    mission_path = tmp_path / "mission-1.json"
    _patch_missions(
        monkeypatch,
        {
            str(mission_path): _mission(),
        },
    )

    state = create_mission_scheduler_state(
        state_path=scheduler_state_path,
        now=NOW,
    )
    state = enqueue_mission(
        state,
        mission_path,
        now=NOW,
    )
    save_mission_scheduler_state(
        state,
        scheduler_state_path,
    )

    driver = FakeMissionDriver(
        {
            "driver_status": "waiting",
            "mission_status": "waiting_for_operator",
            "mission_completed": False,
            "mission_waiting": True,
            "stopped_reason": (
                "mission_waiting_for_external_input"
            ),
        }
    )

    result = run_mission_scheduler_iteration(
        scheduler_state_path=scheduler_state_path,
        worker_state_path=tmp_path / "worker.json",
        worker_name="worker-1",
        target_root=tmp_path / "target",
        workspace_root=tmp_path / "workspace",
        mission_driver=driver,
        owner="mission-runtime-test",
        now=NOW,
    )

    entry = result["entries"][
        result["entry_order"][0]
    ]
    assert entry["entry_status"] == "waiting"
    assert entry["mission_status"] == (
        "waiting_for_operator"
    )
    assert entry["lease"] is None
    assert result["waiting_missions"] == 1


def test_scheduler_iteration_blocks_driver_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_state_path = (
        tmp_path / "mission-scheduler.json"
    )
    mission_path = tmp_path / "mission-1.json"
    _patch_missions(
        monkeypatch,
        {
            str(mission_path): _mission(),
        },
    )

    state = create_mission_scheduler_state(
        state_path=scheduler_state_path,
        now=NOW,
    )
    state = enqueue_mission(
        state,
        mission_path,
        now=NOW,
    )
    save_mission_scheduler_state(
        state,
        scheduler_state_path,
    )

    class FailingDriver:
        def run_mission(
            self,
            mission: Any,
            **kwargs: Any,
        ) -> dict[str, Any]:
            del mission, kwargs
            raise ValueError("driver_failure")

    result = run_mission_scheduler_iteration(
        scheduler_state_path=scheduler_state_path,
        worker_state_path=tmp_path / "worker.json",
        worker_name="worker-1",
        target_root=tmp_path / "target",
        workspace_root=tmp_path / "workspace",
        mission_driver=FailingDriver(),
        owner="mission-runtime-test",
        now=NOW,
    )

    entry = result["entries"][
        result["entry_order"][0]
    ]
    assert result["scheduler_status"] == "blocked"
    assert result["failure"]["critical"] is False
    assert result["last_result"]["dispatched"] is False
    assert "ValueError:driver_failure" in (
        result["last_result"]["reason"]
    )
    assert entry["entry_status"] == "queued"
    assert entry["lease"] is None
    assert entry["last_error"] == {
        "reason": "ValueError:driver_failure"
    }


def test_scheduler_iteration_is_idle_without_missions(
    tmp_path: Path,
) -> None:
    scheduler_state_path = (
        tmp_path / "mission-scheduler.json"
    )
    state = create_mission_scheduler_state(
        state_path=scheduler_state_path,
        now=NOW,
    )
    save_mission_scheduler_state(
        state,
        scheduler_state_path,
    )

    result = run_mission_scheduler_iteration(
        scheduler_state_path=scheduler_state_path,
        worker_state_path=tmp_path / "worker.json",
        worker_name="worker-1",
        target_root=tmp_path / "target",
        workspace_root=tmp_path / "workspace",
        now=NOW,
    )

    assert result["scheduler_status"] == "idle"
    assert result["idle_iterations"] == 1
    assert result["last_result"] == {
        "dispatched": False,
        "reason": "no_dispatchable_mission",
    }
