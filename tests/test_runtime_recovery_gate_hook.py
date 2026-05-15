from core.runtime.runtime_recovery_gate_hook import runtime_recovery_gate_hook


def test_runtime_recovery_gate_hook_returns_normalized_gate_result():
    context = {
        "transaction": {
            "recovery_id": "recovery_gate_hook_test",
            "source_session_id": "source_gate_hook_test",
            "repair_session_id": "repair_gate_hook_test",
            "replay_id": "replay_gate_hook_test",
            "status": "created",
            "steps": [],
            "payload": {"reason": "gate hook smoke"},
        }
    }

    result = runtime_recovery_gate_hook(
        context,
        manual_confirmation_provided=True,
    )

    assert isinstance(result, dict)
    assert "ok" in result
    assert "blocked" in result
    assert "reports" in result
    assert "contract" in result["reports"]
    assert "approval" in result["reports"]
    assert "dry_run" in result["reports"]
    assert "commit" in result["reports"]
