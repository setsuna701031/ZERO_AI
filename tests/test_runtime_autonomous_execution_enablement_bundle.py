from pathlib import Path

from core.runtime.runtime_autonomous_execution_enablement import (
    evaluate_autonomous_start_gate,
    evaluate_emergency_stop_authority,
    evaluate_execution_permission_lease,
    evaluate_live_runtime_seal,
    evaluate_runtime_enable_token,
)


def _token():
    return evaluate_runtime_enable_token(
        {
            "token_id": "enable-1",
            "token_identity": "operator-approved-runtime",
            "purpose": "runtime_autonomous_start",
            "runtime_enable_token_valid": True,
        }
    )


def _lease():
    return evaluate_execution_permission_lease(
        _token(),
        {"lease_id": "lease-1", "ttl_seconds": 30},
    )


def _start():
    return evaluate_autonomous_start_gate(
        _lease(),
        {"loop_controller_enabled": True, "tick_cycle_enabled": True},
        {"max_iterations": 2, "safety_stop_enabled": True},
    )


def test_valid_enable_token_authorizes_without_side_effects() -> None:
    result = _token()
    assert result["token_authorized"] is True
    assert result["token_id"] == "enable-1"
    assert result["runtime_state_mutated"] is False
    assert result["execution_started"] is False
    assert result["denial_reason"] == ""


def test_missing_enable_token_denies_deterministically() -> None:
    result = evaluate_runtime_enable_token(None)
    assert result["token_authorized"] is False
    assert result["denial_reason"] == "missing_enable_token"
    assert result == evaluate_runtime_enable_token(None)


def test_invalid_token_purpose_denies() -> None:
    result = evaluate_runtime_enable_token(
        {
            "token_id": "enable-1",
            "token_identity": "operator-approved-runtime",
            "purpose": "wrong",
            "runtime_enable_token_valid": True,
        }
    )
    assert result["token_authorized"] is False
    assert result["denial_reason"] == "invalid_token_purpose"


def test_valid_permission_lease_authorizes() -> None:
    result = _lease()
    assert result["lease_authorized"] is True
    assert result["lease_id"] == "lease-1"
    assert result["source_token_id"] == "enable-1"
    assert result["lease_positive_ttl"] is True
    assert result["runtime_state_mutated"] is False
    assert result["execution_started"] is False


def test_permission_lease_requires_authorized_token() -> None:
    token = dict(_token())
    token["token_authorized"] = False
    result = evaluate_execution_permission_lease(token, {"lease_id": "lease-1", "ttl_seconds": 30})
    assert result["lease_authorized"] is False
    assert result["denial_reason"] == "token_not_authorized"


def test_permission_lease_requires_positive_ttl() -> None:
    result = evaluate_execution_permission_lease(_token(), {"lease_id": "lease-1", "ttl_seconds": 0})
    assert result["lease_authorized"] is False
    assert result["denial_reason"] == "non_positive_lease_ttl"


def test_valid_autonomous_start_gate_authorizes_but_does_not_start_execution() -> None:
    result = _start()
    assert result["autonomous_start_authorized"] is True
    assert result["source_lease_id"] == "lease-1"
    assert result["max_iterations"] == 2
    assert result["safety_stop_enabled"] is True
    assert result["loop_controller_enabled"] is True
    assert result["tick_cycle_enabled"] is True
    assert result["runtime_state_mutated"] is False
    assert result["execution_started"] is False


def test_start_gate_requires_authorized_lease() -> None:
    lease = dict(_lease())
    lease["lease_authorized"] = False
    result = evaluate_autonomous_start_gate(lease, {}, {"max_iterations": 1})
    assert result["autonomous_start_authorized"] is False
    assert result["denial_reason"] == "permission_lease_not_authorized"


def test_start_gate_requires_safety_stop() -> None:
    result = evaluate_autonomous_start_gate(
        _lease(),
        {"loop_controller_enabled": True, "tick_cycle_enabled": True},
        {"max_iterations": 1, "safety_stop_enabled": False},
    )
    assert result["autonomous_start_authorized"] is False
    assert result["denial_reason"] == "safety_stop_required"


def test_emergency_stop_authority_authorizes_stop_without_mutation() -> None:
    result = evaluate_emergency_stop_authority(
        {
            "stop_token_id": "stop-1",
            "stop_reason": "operator_stop",
            "emergency_stop_requested": True,
        },
        {"active_runtime_id": "runtime-1"},
    )
    assert result["emergency_stop_authorized"] is True
    assert result["runtime_should_continue"] is False
    assert result["runtime_state_mutated"] is False
    assert result["execution_started"] is False


def test_live_runtime_seal_allows_start_unless_stop_is_authorized() -> None:
    live = evaluate_live_runtime_seal(_start())
    assert live["live_runtime_authorized"] is True
    assert live["runtime_should_continue"] is True
    stopped = evaluate_live_runtime_seal(
        _start(),
        {
            "emergency_stop_authorized": True,
            "stop_token_id": "stop-1",
            "stop_reason": "operator_stop",
        },
    )
    assert stopped["live_runtime_authorized"] is False
    assert stopped["runtime_should_continue"] is False
    assert stopped["denial_reason"] == "emergency_stop_authorized"


def test_source_boundary_has_no_forbidden_runtime_surface_imports_or_calls() -> None:
    source = Path("core/runtime/runtime_autonomous_execution_enablement.py").read_text(encoding="utf-8")
    lowered = source.lower()
    forbidden = [
        "import scheduler",
        "from scheduler",
        "import executor",
        "from executor",
        "task_runner",
        "agent_loop",
        "work_package_operator",
        "progress_memory",
        "run_one_step",
        ".run(",
    ]
    for token in forbidden:
        assert token not in lowered, f"{token!r} is contained in runtime enablement source"
