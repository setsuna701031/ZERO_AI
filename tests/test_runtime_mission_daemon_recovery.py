from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest

from core.runtime.runtime_mission_daemon import (
    create_mission_daemon_state, load_mission_daemon_state,
    mission_daemon_health, save_mission_daemon_state,
)
from core.runtime.runtime_mission_daemon_recovery import (
    DEFAULT_RECOVERY_POLICY, normalize_recovery_state, recovery_decision,
    recovery_event_payload, recovery_policy, validate_iteration_checkpoint,
)

NOW = datetime(2026, 7, 12, tzinfo=timezone.utc)


def state(tmp_path):
    return create_mission_daemon_state(state_path=tmp_path / "daemon.json", daemon_name="d",
        scheduler_state_path=tmp_path / "scheduler.json", worker_state_path=tmp_path / "worker.json",
        worker_name="w", target_root=tmp_path / "target", workspace_root=tmp_path / "workspace", now=NOW)


def test_policy_defaults_and_overrides():
    assert recovery_policy() == DEFAULT_RECOVERY_POLICY
    assert recovery_policy({"daemon_recover_failed": True})["daemon_recover_failed"] is True


@pytest.mark.parametrize("value", [0, True, "3"])
def test_policy_rejects_invalid_attempts(value):
    with pytest.raises(ValueError):
        recovery_policy({"daemon_recovery_max_attempts": value})


def test_normalization_migrates_legacy_state():
    migrated, changed = normalize_recovery_state({"daemon_status": "created"}, now=NOW)
    assert changed and migrated["recovery_status"] == "not_required"
    assert migrated["iteration_phase"] == "idle"


def test_load_migrates_authentic_legacy_file(tmp_path):
    current = state(tmp_path)
    for key in ("recovery_status", "recovery_attempts", "recovery_failures", "last_recovery_at",
                "last_recovery_result", "previous_daemon_status", "iteration_phase", "iteration_checkpoint",
                "last_completed_loop_iteration", "last_scheduler_completed_iteration",
                "last_replanning_completed_iteration", "last_published_event_iteration",
                "last_published_event_topic", "last_published_event_id"):
        current.pop(key)
    from core.runtime.runtime_mission_daemon import seal_mission_daemon_state
    current = seal_mission_daemon_state(current)
    path = tmp_path / "daemon.json"
    path.write_text(json.dumps(current), encoding="utf-8-sig")
    loaded = load_mission_daemon_state(path)
    assert loaded["iteration_phase"] == "idle"


def test_tampered_state_is_not_migrated(tmp_path):
    path = tmp_path / "daemon.json"
    saved = save_mission_daemon_state(state(tmp_path), path)
    saved["daemon_name"] = "tampered"
    path.write_text(json.dumps(saved), encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint"):
        load_mission_daemon_state(path)


@pytest.mark.parametrize("status", ["created", "idle", "paused", "stopped"])
def test_clean_status_does_not_require_recovery(tmp_path, status):
    value = state(tmp_path); value["daemon_status"] = status
    assert recovery_decision(value)["required"] is False


@pytest.mark.parametrize("status", ["starting", "running", "blocked", "failed", "stopping"])
def test_active_status_requires_recovery(tmp_path, status):
    value = state(tmp_path); value["daemon_status"] = status
    assert recovery_decision(value)["required"] is True


def test_failed_is_blocked_by_default_policy(tmp_path):
    value = state(tmp_path); value["daemon_status"] = "failed"
    decision = recovery_decision(value)
    assert decision["recoverable"] is False
    assert "failed_recovery_disabled" in decision["reasons"]


@pytest.mark.parametrize("field", ["stop_requested", "pause_requested"])
def test_operator_control_prevents_recovery(tmp_path, field):
    value = state(tmp_path); value["daemon_status"] = "running"; value[field] = True
    assert recovery_decision(value)["recoverable"] is False


def test_attempt_exhaustion_prevents_recovery(tmp_path):
    value = state(tmp_path); value["daemon_status"] = "running"; value["recovery_attempts"] = 3
    assert recovery_decision(value)["recovery_attempts_exhausted"] is True


def test_checkpoint_validation(tmp_path):
    value = state(tmp_path); value["loop_iteration"] = 2; value["iteration_phase"] = "scheduler_pending"
    value["iteration_checkpoint"] = {"loop_iteration": 2}
    assert validate_iteration_checkpoint(value) == []
    value["iteration_checkpoint"]["loop_iteration"] = 1
    assert validate_iteration_checkpoint(value) == ["checkpoint_loop_iteration_mismatch"]


def test_recovery_payload_has_contract_fields(tmp_path):
    payload = recovery_event_payload(state(tmp_path), {"recovered": True})
    assert payload["daemon_id"]
    assert payload["recovery_result"] == {"recovered": True}


def test_health_exposes_recovery_fields(tmp_path):
    value = state(tmp_path); value["daemon_status"] = "blocked"; value["recovery_status"] = "blocked"
    value = save_mission_daemon_state(value, tmp_path / "daemon.json")
    health = mission_daemon_health(value, now=NOW)
    assert health["healthy"] is False
    assert health["checkpoint_valid"] is True
    assert health["recovery_status"] == "blocked"
