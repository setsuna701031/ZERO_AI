from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

import core.runtime.runtime_mission_daemon as daemon_module
from core.runtime.runtime_mission_daemon import (
    CONTRACT,
    create_mission_daemon_state,
    load_mission_daemon_state,
    mission_daemon_health,
    request_mission_daemon_action,
    run_mission_daemon,
    run_mission_daemon_iteration,
    save_mission_daemon_state,
    validate_mission_daemon_state,
)


NOW = datetime(2026, 7, 12, 5, 0, 0, tzinfo=timezone.utc)


def _create_saved_state(
    tmp_path: Path,
    *,
    daemon_status: str = "created",
) -> tuple[Path, dict[str, Any]]:
    daemon_state_path = tmp_path / "mission-daemon.json"
    state = create_mission_daemon_state(
        state_path=daemon_state_path,
        daemon_name="primary",
        scheduler_state_path=(
            tmp_path / "mission-scheduler.json"
        ),
        worker_state_path=tmp_path / "worker.json",
        worker_name="worker-1",
        target_root=tmp_path / "target",
        workspace_root=tmp_path / "workspace",
        owner="mission-runtime-test",
        now=NOW,
    )
    state["daemon_status"] = daemon_status
    state = save_mission_daemon_state(
        state,
        daemon_state_path,
    )
    return daemon_state_path, state


def test_create_save_and_load_daemon_state(
    tmp_path: Path,
) -> None:
    daemon_state_path = tmp_path / "mission-daemon.json"

    state = create_mission_daemon_state(
        state_path=daemon_state_path,
        daemon_name="primary",
        scheduler_state_path=(
            tmp_path / "mission-scheduler.json"
        ),
        worker_state_path=tmp_path / "worker.json",
        worker_name="worker-1",
        target_root=tmp_path / "target",
        workspace_root=tmp_path / "workspace",
        owner="mission-runtime-test",
        now=NOW,
    )

    assert state["contract"] == CONTRACT
    assert state["daemon_status"] == "created"
    assert state["daemon_name"] == "primary"
    assert state["worker_name"] == "worker-1"
    assert state["owner"] == "mission-runtime-test"
    assert state["loop_iteration"] == 0
    assert validate_mission_daemon_state(state) == []

    saved = save_mission_daemon_state(
        state,
        daemon_state_path,
    )
    loaded = load_mission_daemon_state(
        daemon_state_path
    )

    assert daemon_state_path.exists()
    assert loaded == saved
    assert loaded["daemon_fingerprint"] == (
        saved["daemon_fingerprint"]
    )


@pytest.mark.parametrize(
    ("action", "expected_status", "pause", "stop"),
    [
        ("pause", "paused", True, False),
        ("resume", "idle", False, False),
        ("stop", "stopping", False, True),
    ],
)
def test_request_daemon_action(
    tmp_path: Path,
    action: str,
    expected_status: str,
    pause: bool,
    stop: bool,
) -> None:
    _, state = _create_saved_state(tmp_path)

    result = request_mission_daemon_action(
        state,
        action,
        now=NOW,
    )

    assert result["daemon_status"] == expected_status
    assert result["pause_requested"] is pause
    assert result["stop_requested"] is stop
    assert validate_mission_daemon_state(result) == []


def test_daemon_iteration_projects_running_scheduler(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    daemon_state_path, _ = _create_saved_state(tmp_path)

    def fake_scheduler_iteration(
        **kwargs: Any,
    ) -> dict[str, Any]:
        assert kwargs["worker_name"] == "worker-1"
        assert kwargs["owner"] == "mission-runtime-test"
        return {
            "scheduler_status": "running",
            "last_result": {
                "dispatched": True,
                "mission_id": "mission-1",
            },
            "failure": None,
        }

    monkeypatch.setattr(
        daemon_module,
        "run_mission_scheduler_iteration",
        fake_scheduler_iteration,
    )

    result = run_mission_daemon_iteration(
        daemon_state_path=daemon_state_path,
        now=NOW,
    )

    assert result["daemon_status"] == "running"
    assert result["loop_iteration"] == 1
    assert result["successful_iterations"] == 1
    assert result["idle_iterations"] == 0
    assert result["last_scheduler_status"] == "running"
    assert result["last_scheduler_result"] == {
        "dispatched": True,
        "mission_id": "mission-1",
    }


def test_daemon_iteration_projects_idle_scheduler(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    daemon_state_path, _ = _create_saved_state(tmp_path)

    monkeypatch.setattr(
        daemon_module,
        "run_mission_scheduler_iteration",
        lambda **_: {
            "scheduler_status": "idle",
            "last_result": {
                "dispatched": False,
                "reason": "no_dispatchable_mission",
            },
            "failure": None,
        },
    )

    result = run_mission_daemon_iteration(
        daemon_state_path=daemon_state_path,
        now=NOW,
    )

    assert result["daemon_status"] == "idle"
    assert result["idle_iterations"] == 1
    assert result["successful_iterations"] == 0
    assert result["last_scheduler_status"] == "idle"


def test_daemon_iteration_projects_blocked_scheduler(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    daemon_state_path, _ = _create_saved_state(tmp_path)

    monkeypatch.setattr(
        daemon_module,
        "run_mission_scheduler_iteration",
        lambda **_: {
            "scheduler_status": "blocked",
            "last_result": {
                "dispatched": False,
                "reason": "driver_failure",
            },
            "failure": {
                "critical": False,
                "reasons": ["driver_failure"],
            },
        },
    )

    result = run_mission_daemon_iteration(
        daemon_state_path=daemon_state_path,
        now=NOW,
    )

    assert result["daemon_status"] == "blocked"
    assert result["blocked_iterations"] == 1
    assert result["failure"] == {
        "critical": False,
        "reasons": ["driver_failure"],
    }


def test_daemon_iteration_captures_scheduler_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    daemon_state_path, _ = _create_saved_state(tmp_path)

    def fail_scheduler(**_: Any) -> dict[str, Any]:
        raise ValueError("scheduler_failure")

    monkeypatch.setattr(
        daemon_module,
        "run_mission_scheduler_iteration",
        fail_scheduler,
    )

    result = run_mission_daemon_iteration(
        daemon_state_path=daemon_state_path,
        now=NOW,
    )

    assert result["daemon_status"] == "failed"
    assert result["failed_iterations"] == 1
    assert result["failure"]["critical"] is False
    assert result["failure"]["reasons"] == [
        "ValueError:scheduler_failure"
    ]
    assert result["last_scheduler_result"] == {
        "error": "ValueError:scheduler_failure"
    }


def test_daemon_iteration_honors_pause(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    daemon_state_path, state = _create_saved_state(tmp_path)
    state = request_mission_daemon_action(
        state,
        "pause",
        now=NOW,
    )
    save_mission_daemon_state(
        state,
        daemon_state_path,
    )

    called = False

    def fake_scheduler(**_: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(
        daemon_module,
        "run_mission_scheduler_iteration",
        fake_scheduler,
    )

    result = run_mission_daemon_iteration(
        daemon_state_path=daemon_state_path,
        now=NOW,
    )

    assert called is False
    assert result["daemon_status"] == "paused"
    assert result["idle_iterations"] == 1


def test_daemon_iteration_honors_stop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    daemon_state_path, state = _create_saved_state(tmp_path)
    state = request_mission_daemon_action(
        state,
        "stop",
        now=NOW,
    )
    save_mission_daemon_state(
        state,
        daemon_state_path,
    )

    called = False

    def fake_scheduler(**_: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(
        daemon_module,
        "run_mission_scheduler_iteration",
        fake_scheduler,
    )

    result = run_mission_daemon_iteration(
        daemon_state_path=daemon_state_path,
        now=NOW,
    )

    assert called is False
    assert result["daemon_status"] == "stopped"
    assert result["stopped_at"] is not None


def test_run_daemon_stops_after_max_iterations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    daemon_state_path, _ = _create_saved_state(tmp_path)

    calls = 0

    def fake_iteration(
        *,
        daemon_state_path: Any,
        **_: Any,
    ) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        state = load_mission_daemon_state(
            daemon_state_path
        )
        state["loop_iteration"] = int(
            state.get("loop_iteration") or 0
        ) + 1

        if state.get("stop_requested"):
            state["daemon_status"] = "stopped"
            state["stopped_at"] = (
                NOW + timedelta(seconds=calls)
            ).isoformat()
        else:
            state["daemon_status"] = "running"
            state["successful_iterations"] = int(
                state.get("successful_iterations") or 0
            ) + 1

        return save_mission_daemon_state(
            state,
            daemon_state_path,
        )

    monkeypatch.setattr(
        daemon_module,
        "run_mission_daemon_iteration",
        fake_iteration,
    )

    result = run_mission_daemon(
        daemon_state_path=daemon_state_path,
        poll_interval_seconds=0.1,
        max_iterations=2,
        now_provider=lambda: NOW,
        sleep_provider=lambda _: None,
    )

    assert calls == 3
    assert result["daemon_status"] == "stopped"
    assert result["stop_requested"] is True


def test_run_daemon_stops_after_idle_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    daemon_state_path, _ = _create_saved_state(tmp_path)

    def fake_iteration(
        *,
        daemon_state_path: Any,
        **_: Any,
    ) -> dict[str, Any]:
        state = load_mission_daemon_state(
            daemon_state_path
        )
        state["loop_iteration"] = int(
            state.get("loop_iteration") or 0
        ) + 1

        if state.get("stop_requested"):
            state["daemon_status"] = "stopped"
        else:
            state["daemon_status"] = "idle"
            state["idle_iterations"] = int(
                state.get("idle_iterations") or 0
            ) + 1

        return save_mission_daemon_state(
            state,
            daemon_state_path,
        )

    monkeypatch.setattr(
        daemon_module,
        "run_mission_daemon_iteration",
        fake_iteration,
    )

    result = run_mission_daemon(
        daemon_state_path=daemon_state_path,
        poll_interval_seconds=0.1,
        idle_exit_after=2,
        now_provider=lambda: NOW,
        sleep_provider=lambda _: None,
    )

    assert result["daemon_status"] == "stopped"
    assert result["stop_requested"] is True
    assert result["idle_iterations"] >= 2


def test_daemon_health_is_healthy_with_fresh_heartbeat(
    tmp_path: Path,
) -> None:
    _, state = _create_saved_state(
        tmp_path,
        daemon_status="running",
    )

    result = mission_daemon_health(
        state,
        now=NOW + timedelta(seconds=30),
    )

    assert result["healthy"] is True
    assert result["heartbeat_fresh"] is True
    assert result["critical_failure"] is False
    assert result["reasons"] == []


def test_daemon_health_detects_stale_heartbeat(
    tmp_path: Path,
) -> None:
    _, state = _create_saved_state(
        tmp_path,
        daemon_status="running",
    )

    result = mission_daemon_health(
        state,
        now=NOW + timedelta(seconds=91),
    )

    assert result["healthy"] is False
    assert result["heartbeat_fresh"] is False
    assert "stale_mission_daemon_heartbeat" in (
        result["reasons"]
    )


def test_daemon_health_detects_failed_state(
    tmp_path: Path,
) -> None:
    _, state = _create_saved_state(
        tmp_path,
        daemon_status="failed",
    )
    state["failure"] = {
        "critical": True,
        "reasons": ["fatal"],
    }
    state = save_mission_daemon_state(
        state,
        tmp_path / "mission-daemon.json",
    )

    result = mission_daemon_health(
        state,
        now=NOW,
    )

    assert result["healthy"] is False
    assert result["critical_failure"] is True
    assert "mission_daemon_critical_failure" in (
        result["reasons"]
    )
