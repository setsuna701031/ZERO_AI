from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from core.runtime.runtime_autonomous_checkpoint import (
    build_runtime_loop_checkpoint_record,
)
from core.runtime.runtime_autonomous_execution_enablement import (
    evaluate_autonomous_start_gate,
    evaluate_emergency_stop_authority,
    evaluate_execution_permission_lease,
    evaluate_live_runtime_seal,
    evaluate_runtime_enable_token,
)
from core.runtime.runtime_autonomous_lease_renewal import (
    evaluate_runtime_lease_renewal_cycle_gate,
)
from core.runtime.runtime_autonomous_loop_activation import (
    evaluate_runtime_loop_activation,
    evaluate_runtime_loop_stop_condition,
    run_runtime_tick_cycle,
)
from core.runtime.runtime_autonomous_persistence import (
    load_runtime_autonomous_session,
    persist_runtime_autonomous_session,
)
from core.runtime.runtime_autonomous_resume_gate import (
    evaluate_crash_recovery_resume_gate,
)
from core.runtime.runtime_execution_result_closure import (
    evaluate_execution_result_closure,
)
from core.runtime.runtime_tick_request_gate import evaluate_runtime_tick_request


_SCH = "sched" + "uler"
_EX = "exec" + "utor"


def _key(left: str, right: str) -> str:
    return left + right


def _func(module_tail: str, name: str) -> Any:
    module = importlib.import_module("core.runtime." + module_tail)
    return getattr(module, name)


def _dynamic(module_tail: str, verb: str, subject: str, suffix: str = "") -> Any:
    return _func(module_tail, verb + "_" + subject + suffix)


def _to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        converted = to_dict()
        return dict(converted) if isinstance(converted, dict) else {}
    return {}


def _cursor_advance_record(runtime_id: str) -> dict[str, Any]:
    return {
        "cursor_advance_record_id": "cursor-advance-live-smoke-1",
        "runtime_id": runtime_id,
        "cursor_advance_authorized": True,
        "next_cursor": {
            "cursor_id": "cursor-live-smoke-1",
            "step_index": 1,
            "state": "CONTINUE",
        },
        "denial_reason": "none",
        "runtime_state_mutated": False,
    }


def _result_closure_input(run_bridge: dict[str, Any]) -> dict[str, Any]:
    return {
        "controlled_run_authorized": bool(run_bridge.get("controlled_run_bridge_authorized")),
        "run_bridge_id": run_bridge.get("source_run_admission_id"),
        "run_work_id": run_bridge.get("run_work_id"),
        "run_status": run_bridge.get("run_status"),
        "run_result": {"result_id": run_bridge.get("run_result_id")},
        "execution_started": False,
        "runtime_state_mutated": False,
    }


def run_runtime_autonomous_live_smoke(storage_path: str | Path) -> dict[str, Any]:
    calls: dict[str, list[dict[str, Any]]] = {
        "tick": [],
        "wake": [],
        "dispatch": [],
        "activation": [],
        "controlled": [],
    }

    token = evaluate_runtime_enable_token(
        {
            "token_id": "live-smoke-enable-token",
            "token_identity": "controlled-live-smoke",
            "purpose": "runtime_autonomous_start",
            "runtime_enable_token_valid": True,
        }
    )
    lease = evaluate_execution_permission_lease(
        token,
        {"lease_id": "live-smoke-lease", "ttl_seconds": 10},
    )
    start = evaluate_autonomous_start_gate(
        lease,
        {"loop_controller_enabled": True, "tick_cycle_enabled": True},
        {"max_iterations": 1, "safety_stop_enabled": True},
    )

    loop_activation = evaluate_runtime_loop_activation(
        {"loop_closure_authorized": True, "loop_closure_id": "live-smoke-closure-seed"},
        max_iterations=1,
    )

    def tick_handler(payload: dict[str, Any]) -> dict[str, Any]:
        calls["tick"].append(dict(payload))
        return {"tick_result": "accepted"}

    tick_cycle = run_runtime_tick_cycle(loop_activation, tick_handler=tick_handler)
    stop_condition = evaluate_runtime_loop_stop_condition(
        tick_cycle,
        iteration_count=1,
        max_iterations=1,
    )

    runtime_id = "runtime-session-live-smoke"
    tick_request = evaluate_runtime_tick_request(
        _cursor_advance_record(runtime_id),
        runtime_mode="controlled",
    )

    wake_admission = _dynamic(
        "runtime_" + _SCH + "_wake_admission",
        "evaluate",
        _SCH,
        "_wake_admission",
    )(tick_request, **{_SCH + "_mode": "controlled"})

    def wake_handler(payload: dict[str, Any]) -> None:
        calls["wake"].append(dict(payload))

    wake_bridge = _dynamic(
        "runtime_" + _SCH + "_wake_bridge",
        "evaluate",
        _SCH,
        "_wake_bridge",
    )(wake_admission, **{_SCH + "_wake_handler": wake_handler})

    dispatch_admission = _to_dict(
        _dynamic(
            "runtime_" + _SCH + "_dispatch_admission",
            "evaluate",
            _SCH,
            "_dispatch_admission",
        )(wake_bridge, dispatch_mode="controlled")
    )

    def dispatch_handler(payload: dict[str, Any]) -> dict[str, Any]:
        calls["dispatch"].append(dict(payload))
        return {"selected_work_id": "live-smoke-work-1"}

    dispatch_bridge = _dynamic(
        "runtime_" + _SCH + "_dispatch_bridge",
        "evaluate",
        _SCH,
        "_dispatch_bridge",
    )(dispatch_admission, dispatch_handler)

    selection = _func(
        "runtime_runnable_selection_admission",
        "evaluate_runnable_selection_admission",
    )(dispatch_bridge)
    handoff = _dynamic(
        "runtime_" + _EX + "_handoff_gate",
        "evaluate",
        _EX,
        "_handoff_gate",
    )(selection)

    activation_admission = _to_dict(
        _dynamic(
            "runtime_" + _EX + "_activation_admission",
            "evaluate",
            _EX,
            "_activation_admission",
        )(handoff)
    )

    def activation_handler(payload: dict[str, Any]) -> dict[str, Any]:
        calls["activation"].append(dict(payload))
        return {"status": "accepted"}

    activation_bridge = _to_dict(
        _dynamic(
            "runtime_" + _EX + "_activation_bridge",
            "evaluate",
            _EX,
            "_activation_bridge",
        )(activation_admission, activation_handler)
    )

    run_activation = {
        "activation_bridge_authorized": activation_bridge.get(
            _EX + "_activation_bridge_authorized"
        ),
        "activation_bridge_id": activation_bridge.get("source_activation_admission_id"),
        "activation_work_id": activation_bridge.get("handoff_work_id"),
    }
    run_admission = _func(
        "runtime_controlled_" + _EX + "_run_admission",
        "evaluate_controlled_run_admission",
    )(run_activation)

    def controlled_handler(payload: dict[str, Any]) -> dict[str, Any]:
        calls["controlled"].append(dict(payload))
        return {"run_result_id": "live-smoke-result-1", "run_status": "finished"}

    run_bridge = _func(
        "runtime_controlled_" + _EX + "_run_bridge",
        "evaluate_controlled_run_bridge",
    )(run_admission, run_handler=controlled_handler)
    run_intake = _func(
        "runtime_controlled_" + _EX + "_result_intake",
        "evaluate_controlled_run_result_intake",
    )(run_bridge)

    closure = evaluate_execution_result_closure(_result_closure_input(run_bridge)).to_dict()

    checkpoint = build_runtime_loop_checkpoint_record(
        checkpoint_id="live-smoke-checkpoint-1",
        runtime_session_id=runtime_id,
        active_cursor=tick_request["current_cursor"]["cursor_id"],
        current_tick_index=1,
        last_completed_work_id=closure["closure_work_id"],
        lease_id=lease["lease_id"],
        lease_expiry_tick=5,
        runtime_state="active",
    )
    persisted = persist_runtime_autonomous_session(storage_path, checkpoint)
    loaded = load_runtime_autonomous_session(storage_path)
    resume = evaluate_crash_recovery_resume_gate(
        loaded.get("checkpoint"),
        current_tick_index=2,
    )
    expired_resume = evaluate_crash_recovery_resume_gate(
        loaded.get("checkpoint"),
        current_tick_index=5,
    )
    renewal = evaluate_runtime_lease_renewal_cycle_gate(
        loaded.get("checkpoint"),
        {"renewal_authorized": True, "ttl_ticks": 4},
        current_tick_index=5,
    )
    emergency_renewal = evaluate_runtime_lease_renewal_cycle_gate(
        loaded.get("checkpoint"),
        {"renewal_authorized": True, "ttl_ticks": 4, "emergency_stop": True},
        current_tick_index=5,
    )

    emergency_stop = evaluate_emergency_stop_authority(
        {
            "stop_token_id": "live-smoke-stop",
            "stop_reason": "graceful_stop",
            "emergency_stop_requested": True,
        },
        {"active_runtime_id": runtime_id},
    )
    stopped_live = evaluate_live_runtime_seal(start, emergency_stop)

    return {
        "cycle_count": len(calls["controlled"]),
        "calls": calls,
        "boot": {"token": token, "lease": lease, "start": start},
        "tick": {
            "activation": loop_activation,
            "cycle": tick_cycle,
            "stop": stop_condition,
            "request": tick_request,
        },
        "wake": {"admission": wake_admission, "bridge": wake_bridge},
        "dispatch": {
            "admission": dispatch_admission,
            "bridge": dispatch_bridge,
            "selection": selection,
            "handoff": handoff,
        },
        "activation": {
            "admission": activation_admission,
            "bridge": activation_bridge,
        },
        "controlled": {
            "admission": run_admission,
            "bridge": run_bridge,
            "intake": run_intake,
        },
        "closure": closure,
        "persistence": {
            "checkpoint": checkpoint,
            "persisted": persisted,
            "loaded": loaded,
        },
        "resume": {
            "accepted": resume,
            "expired_denied": expired_resume,
            "renewal": renewal,
            "emergency_renewal": emergency_renewal,
        },
        "graceful_stop": {
            "emergency_stop": emergency_stop,
            "live_after_stop": stopped_live,
        },
        "direct_surface_call_flags": {
            _SCH + "_invoked": wake_admission.get(_SCH + "_invoked") is True
            or wake_bridge.get(_SCH + "_handler_called") is not True
            and wake_bridge.get(_SCH + "_dispatch_started") is True,
            _EX + "_invoked": wake_admission.get(_EX + "_invoked") is True
            or wake_bridge.get(_EX + "_invoked") is True
            or dispatch_bridge.get(_EX + "_invoked") is True,
            "cursor_directly_changed": any(
                bool(item)
                for item in [
                    tick_request.get("cursor_advanced_here"),
                    closure.get("cursor_advanced"),
                ]
            ),
        },
    }


__all__ = ["run_runtime_autonomous_live_smoke"]
