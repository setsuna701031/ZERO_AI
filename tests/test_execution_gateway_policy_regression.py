from __future__ import annotations

from core.runtime.execution_gateway import safe_subprocess_run
import pytest

pytestmark = [pytest.mark.integration]




def test_gateway_neutral_success_does_not_freeze() -> None:
    result = safe_subprocess_run(
        ["python", "-c", "print(123)"],
        timeout=10,
        allow_paths=["workspace"],
    )

    assert result["ok"] is True
    assert result["metadata"].get("execution_outcome_finalized") is True
    assert result["metadata"].get("execution_outcome_verification_state") == "verified"
    assert result["metadata"].get("runtime_frozen") is False


def test_gateway_boundary_block_freezes() -> None:
    result = safe_subprocess_run(
        ["python", "-c", "print(123)", "core/runtime/execution_gateway.py"],
        timeout=10,
        allow_paths=["workspace"],
    )

    assert result["ok"] is False
    assert result["metadata"].get("execution_outcome_finalized") is True
    assert result["metadata"].get("execution_outcome_state") == "failed"
    assert result["metadata"].get("runtime_frozen") is True
    assert result["metadata"].get("blocked_reason") == "target_path_outside_allow_paths"


def test_gateway_attached_verified_outcome_does_not_freeze() -> None:
    result = safe_subprocess_run(
        ["python", "-c", "print(123)"],
        timeout=10,
        allow_paths=["workspace"],
        metadata={
            "rollback_verification": {
                "ok": True,
                "attached": True,
                "verification_result": "verified",
            },
            "rollback_outcome_verification": {
                "verification_state": "verified",
                "deterministic": True,
                "rollback_verified": True,
                "replay_verified": True,
                "legality_verified": True,
                "frozen": False,
            },
        },
    )

    assert result["ok"] is True
    assert result["metadata"].get("execution_outcome_finalized") is True
    assert result["metadata"].get("execution_outcome_verification_state") == "verified"
    assert result["metadata"].get("runtime_frozen") is False
