from __future__ import annotations

from pathlib import Path

from core.runtime.runtime_autonomous_live_smoke_harness import (
    run_runtime_autonomous_live_smoke,
)


def test_1697_live_smoke_completes_exactly_one_controlled_cycle(tmp_path: Path) -> None:
    result = run_runtime_autonomous_live_smoke(tmp_path / "live-smoke.json")

    assert result["cycle_count"] == 1
    assert len(result["calls"]["tick"]) == 1
    assert len(result["calls"]["wake"]) == 1
    assert len(result["calls"]["dispatch"]) == 1
    assert len(result["calls"]["activation"]) == 1
    assert len(result["calls"]["controlled"]) == 1

    assert result["boot"]["token"]["token_authorized"] is True
    assert result["boot"]["lease"]["lease_authorized"] is True
    assert result["boot"]["start"]["autonomous_start_authorized"] is True

    assert result["tick"]["activation"]["loop_activation_authorized"] is True
    assert result["tick"]["cycle"]["tick_cycle_authorized"] is True
    assert result["tick"]["stop"]["loop_stop_required"] is True
    assert result["tick"]["stop"]["stop_reason"] == "max_iterations_reached"


def test_1705_live_smoke_covers_wake_dispatch_and_controlled_run_paths(tmp_path: Path) -> None:
    result = run_runtime_autonomous_live_smoke(tmp_path / "live-smoke.json")

    assert result["wake"]["admission"]["scheduler_wake_authorized"] is True
    assert result["wake"]["bridge"]["scheduler_wake_bridge_authorized"] is True
    assert result["wake"]["bridge"]["scheduler_handler_called"] is True
    assert result["wake"]["bridge"]["scheduler_dispatch_started"] is False

    assert result["dispatch"]["admission"]["scheduler_dispatch_admitted"] is True
    assert result["dispatch"]["bridge"]["dispatch_bridge_authorized"] is True
    assert result["dispatch"]["selection"]["runnable_selection_authorized"] is True
    assert result["dispatch"]["handoff"]["executor_handoff_authorized"] is True

    assert result["activation"]["admission"]["executor_activation_admitted"] is True
    assert result["activation"]["bridge"]["executor_activation_bridge_authorized"] is True
    assert result["activation"]["bridge"]["activation_handler_called"] is True
    assert result["controlled"]["admission"]["controlled_run_admitted"] is True
    assert result["controlled"]["bridge"]["controlled_run_bridge_authorized"] is True
    assert result["controlled"]["bridge"]["run_handler_called"] is True
    assert result["controlled"]["intake"]["result_intake_authorized"] is True


def test_1713_live_smoke_closes_result_and_persists_checkpoint(tmp_path: Path) -> None:
    result = run_runtime_autonomous_live_smoke(tmp_path / "live-smoke.json")

    closure = result["closure"]
    assert closure["loop_closure_candidate_created"] is True
    assert closure["result_intake_authorized"] is True
    assert closure["result_validation_authorized"] is True
    assert closure["progress_apply_candidate_created"] is True
    assert closure["closure_work_id"] == "live-smoke-work-1"
    assert closure["progress_memory_mutated"] is False
    assert closure["cursor_advanced"] is False
    assert closure["runtime_state_mutated"] is False

    checkpoint = result["persistence"]["checkpoint"]
    assert checkpoint["valid_checkpoint"] is True
    assert checkpoint["runtime_session_id"] == "runtime-session-live-smoke"
    assert checkpoint["active_cursor"] == "cursor-live-smoke-1"
    assert checkpoint["current_tick_index"] == 1
    assert checkpoint["last_completed_work_id"] == "live-smoke-work-1"
    assert checkpoint["lease_id"] == "live-smoke-lease"
    assert checkpoint["lease_expiry_tick"] == 5
    assert result["persistence"]["persisted"]["persisted"] is True
    assert result["persistence"]["loaded"]["loaded"] is True


def test_1721_live_smoke_resume_renewal_and_stop_gates_hold(tmp_path: Path) -> None:
    result = run_runtime_autonomous_live_smoke(tmp_path / "live-smoke.json")

    assert result["resume"]["accepted"]["resume_authorized"] is True
    assert result["resume"]["expired_denied"]["resume_authorized"] is False
    assert (
        result["resume"]["expired_denied"]["denial_reason"]
        == "lease_expired_renewal_not_authorized"
    )
    assert result["resume"]["renewal"]["lease_renewal_authorized"] is True
    assert result["resume"]["renewal"]["lease_expiry_tick"] == 9
    assert result["resume"]["emergency_renewal"]["lease_renewal_authorized"] is False
    assert result["resume"]["emergency_renewal"]["denial_reason"] == "emergency_stop_active"

    assert result["graceful_stop"]["emergency_stop"]["emergency_stop_authorized"] is True
    assert result["graceful_stop"]["live_after_stop"]["live_runtime_authorized"] is False
    assert result["graceful_stop"]["live_after_stop"]["denial_reason"] == "emergency_stop_authorized"


def test_1725_live_smoke_keeps_direct_surfaces_and_mutation_locked(tmp_path: Path) -> None:
    result = run_runtime_autonomous_live_smoke(tmp_path / "live-smoke.json")

    assert result["direct_surface_call_flags"]["scheduler_invoked"] is False
    assert result["direct_surface_call_flags"]["executor_invoked"] is False
    assert result["direct_surface_call_flags"]["cursor_directly_changed"] is False

    guarded_records = [
        result["boot"]["start"],
        result["tick"]["activation"],
        result["tick"]["cycle"],
        result["tick"]["stop"],
        result["wake"]["admission"],
        result["wake"]["bridge"],
        result["dispatch"]["admission"],
        result["dispatch"]["bridge"],
        result["dispatch"]["selection"],
        result["dispatch"]["handoff"],
        result["activation"]["admission"],
        result["activation"]["bridge"],
        result["controlled"]["admission"],
        result["controlled"]["bridge"],
        result["controlled"]["intake"],
        result["closure"],
        result["persistence"]["checkpoint"],
        result["persistence"]["persisted"],
        result["persistence"]["loaded"],
        result["resume"]["accepted"],
        result["resume"]["renewal"],
    ]

    for record in guarded_records:
        assert record.get("runtime_state_mutated") is False

    assert result["controlled"]["bridge"]["executor_called"] is False
    assert result["activation"]["bridge"]["execution_started"] is False
    assert result["dispatch"]["handoff"]["execution_started"] is False


def test_1728_harness_source_has_no_forbidden_runtime_surface_imports_or_calls() -> None:
    source = Path("core/runtime/runtime_autonomous_live_smoke_harness.py").read_text(
        encoding="utf-8"
    )
    lowered = source.lower()
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

    for token in forbidden:
        assert token not in lowered, f"{token!r} is contained in live smoke harness"
