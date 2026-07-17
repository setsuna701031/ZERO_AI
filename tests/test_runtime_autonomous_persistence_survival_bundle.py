from __future__ import annotations

from pathlib import Path

from core.runtime.runtime_autonomous_checkpoint import (
    RUNTIME_AUTONOMOUS_CHECKPOINT_SCHEMA,
    build_runtime_loop_checkpoint_record,
    validate_runtime_loop_checkpoint_record,
)
from core.runtime.runtime_autonomous_lease_renewal import (
    evaluate_runtime_lease_renewal_cycle_gate,
)
from core.runtime.runtime_autonomous_persistence import (
    build_long_running_runtime_survival_seal,
    load_runtime_autonomous_session,
    persist_runtime_autonomous_session,
)
from core.runtime.runtime_autonomous_resume_gate import (
    evaluate_crash_recovery_resume_gate,
)


def _checkpoint(**overrides):
    base = {
        "checkpoint_id": "checkpoint-1673",
        "runtime_session_id": "runtime-session-1673",
        "active_cursor": "cursor-work-02",
        "current_tick_index": 4,
        "last_completed_work_id": "work-01",
        "lease_id": "lease-1673",
        "lease_expiry_tick": 10,
        "runtime_state": "active",
    }
    base.update(overrides)
    return build_runtime_loop_checkpoint_record(**base)


def test_1673_checkpoint_persists_required_runtime_fields() -> None:
    checkpoint = _checkpoint()

    assert checkpoint["schema"] == RUNTIME_AUTONOMOUS_CHECKPOINT_SCHEMA
    assert checkpoint["runtime_session_id"] == "runtime-session-1673"
    assert checkpoint["active_cursor"] == "cursor-work-02"
    assert checkpoint["current_tick_index"] == 4
    assert checkpoint["last_completed_work_id"] == "work-01"
    assert checkpoint["lease_id"] == "lease-1673"
    assert checkpoint["lease_expiry_tick"] == 10
    assert checkpoint["lease_expiry"] == 10
    assert checkpoint["paused"] is False
    assert checkpoint["stopped"] is False
    assert checkpoint["runtime_state_mutated"] is False
    assert checkpoint["cursor_advanced"] is False
    assert checkpoint["work_started"] is False


def test_1674_checkpoint_validation_denies_missing_checkpoint() -> None:
    validation = validate_runtime_loop_checkpoint_record(None)

    assert validation["checkpoint_valid"] is False
    assert validation["denial_reason"] == "checkpoint_missing"


def test_1675_session_persistence_round_trips_checkpoint(tmp_path: Path) -> None:
    path = tmp_path / "runtime-session.json"
    checkpoint = _checkpoint(runtime_state="paused")

    persisted = persist_runtime_autonomous_session(path, checkpoint)
    loaded = load_runtime_autonomous_session(path)

    assert persisted["persisted"] is True
    assert loaded["loaded"] is True
    assert loaded["runtime_session_id"] == "runtime-session-1673"
    assert loaded["active_cursor"] == "cursor-work-02"
    assert loaded["current_tick_index"] == 4
    assert loaded["last_completed_work_id"] == "work-01"
    assert loaded["lease_id"] == "lease-1673"
    assert loaded["lease_expiry_tick"] == 10
    assert loaded["lease_expiry"] == 10
    assert loaded["paused"] is True
    assert loaded["stopped"] is False


def test_1676_load_missing_checkpoint_denies_resume_source(tmp_path: Path) -> None:
    loaded = load_runtime_autonomous_session(tmp_path / "missing.json")

    assert loaded["loaded"] is False
    assert loaded["denial_reason"] == "checkpoint_missing"


def test_1677_resume_gate_allows_valid_active_checkpoint_before_lease_expiry() -> None:
    gate = evaluate_crash_recovery_resume_gate(_checkpoint(), current_tick_index=5)

    assert gate["resume_authorized"] is True
    assert gate["runtime_session_id"] == "runtime-session-1673"
    assert gate["active_cursor"] == "cursor-work-02"
    assert gate["checkpoint_tick_index"] == 4
    assert gate["last_completed_work_id"] == "work-01"
    assert gate["denial_reason"] == ""
    assert gate["runtime_state_mutated"] is False
    assert gate["cursor_advanced"] is False
    assert gate["work_started"] is False


def test_1678_resume_gate_denies_missing_checkpoint() -> None:
    gate = evaluate_crash_recovery_resume_gate(None, current_tick_index=5)

    assert gate["resume_authorized"] is False
    assert gate["denial_reason"] == "checkpoint_missing"


def test_1679_resume_gate_denies_invalid_checkpoint() -> None:
    checkpoint = _checkpoint(runtime_session_id="")
    gate = evaluate_crash_recovery_resume_gate(checkpoint, current_tick_index=5)

    assert gate["resume_authorized"] is False
    assert gate["denial_reason"] == "checkpoint_invalid"


def test_1680_resume_gate_denies_expired_lease_without_renewal_authority() -> None:
    gate = evaluate_crash_recovery_resume_gate(_checkpoint(), current_tick_index=10)

    assert gate["resume_authorized"] is False
    assert gate["lease_expired"] is True
    assert gate["denial_reason"] == "lease_expired_renewal_not_authorized"


def test_1681_resume_gate_allows_expired_lease_when_renewal_is_authorized() -> None:
    gate = evaluate_crash_recovery_resume_gate(
        _checkpoint(),
        current_tick_index=10,
        renewal_authorized=True,
    )

    assert gate["resume_authorized"] is True
    assert gate["lease_renewal_required"] is True
    assert gate["lease_renewal_authorized"] is True


def test_1682_resume_gate_denies_paused_and_stopped_states() -> None:
    paused = evaluate_crash_recovery_resume_gate(
        _checkpoint(runtime_state="paused"),
        current_tick_index=5,
    )
    stopped = evaluate_crash_recovery_resume_gate(
        _checkpoint(runtime_state="stopped"),
        current_tick_index=5,
    )

    assert paused["resume_authorized"] is False
    assert paused["denial_reason"] == "runtime_paused"
    assert stopped["resume_authorized"] is False
    assert stopped["denial_reason"] == "runtime_stopped"


def test_1683_lease_renewal_requires_active_runtime_and_no_emergency_stop() -> None:
    renewed = evaluate_runtime_lease_renewal_cycle_gate(
        _checkpoint(),
        {"renewal_authorized": True, "ttl_ticks": 6},
        current_tick_index=10,
    )
    paused = evaluate_runtime_lease_renewal_cycle_gate(
        _checkpoint(runtime_state="paused"),
        {"renewal_authorized": True, "ttl_ticks": 6},
        current_tick_index=10,
    )
    stopped = evaluate_runtime_lease_renewal_cycle_gate(
        _checkpoint(),
        {"renewal_authorized": True, "ttl_ticks": 6, "emergency_stop": True},
        current_tick_index=10,
    )

    assert renewed["lease_renewal_authorized"] is True
    assert renewed["lease_expiry_tick"] == 16
    assert renewed["lease_expiry"] == 16
    assert renewed["renewed_checkpoint"]["lease_expiry_tick"] == 16
    assert renewed["renewed_checkpoint"]["lease_expiry"] == 16
    assert renewed["runtime_state_mutated"] is False
    assert renewed["cursor_advanced"] is False
    assert renewed["work_started"] is False
    assert paused["lease_renewal_authorized"] is False
    assert paused["denial_reason"] == "runtime_not_active"
    assert stopped["lease_renewal_authorized"] is False
    assert stopped["denial_reason"] == "emergency_stop_active"


def test_1684_lease_renewal_denies_missing_authority_and_non_positive_ttl() -> None:
    missing = evaluate_runtime_lease_renewal_cycle_gate(
        _checkpoint(),
        {"ttl_ticks": 6},
        current_tick_index=10,
    )
    bad_ttl = evaluate_runtime_lease_renewal_cycle_gate(
        _checkpoint(),
        {"renewal_authorized": True, "ttl_ticks": 0},
        current_tick_index=10,
    )

    assert missing["lease_renewal_authorized"] is False
    assert missing["denial_reason"] == "renewal_not_authorized"
    assert bad_ttl["lease_renewal_authorized"] is False
    assert bad_ttl["denial_reason"] == "non_positive_renewal_ttl"


def test_1685_survival_seal_closes_only_for_persisted_and_resumable_checkpoint(tmp_path: Path) -> None:
    path = tmp_path / "runtime-session.json"
    persisted = persist_runtime_autonomous_session(path, _checkpoint())
    resume = evaluate_crash_recovery_resume_gate(
        load_runtime_autonomous_session(path)["checkpoint"],
        current_tick_index=5,
    )
    seal = build_long_running_runtime_survival_seal(persisted, resume)

    assert seal["closed"] is True
    assert seal["survival_authorized"] is True
    assert seal["runtime_session_id"] == "runtime-session-1673"
    assert seal["active_cursor"] == "cursor-work-02"
    assert seal["current_tick_index"] == 4
    assert seal["last_completed_work_id"] == "work-01"
    assert seal["lease_id"] == "lease-1673"


def test_1696_source_boundary_has_no_forbidden_runtime_surface_imports_or_calls() -> None:
    files = [
        Path("core/runtime/runtime_autonomous_checkpoint.py"),
        Path("core/runtime/runtime_autonomous_persistence.py"),
        Path("core/runtime/runtime_autonomous_resume_gate.py"),
        Path("core/runtime/runtime_autonomous_lease_renewal.py"),
    ]
    forbidden = [
        "scheduler",
        "executor",
        "task_runner",
        "agent_loop",
        "work_package_operator",
        "progress_memory",
        "run_one_step",
        ".run(",
    ]

    for file in files:
        source = file.read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert token not in source, f"{token!r} is contained in {file}"
