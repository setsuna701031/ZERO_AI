from __future__ import annotations

import pytest

from core.runtime.execution_authority import normalize_authority_metadata, validate_authority_metadata
from core.runtime.runtime_execution_authority_gate import RuntimeExecutionAuthorityDenied, enforce_execution_authority
pytestmark = [pytest.mark.contract]




def test_compatibility_metadata_cannot_become_execution_authority() -> None:
    metadata = normalize_authority_metadata(
        task={"task_id": "task:1"},
        step={"step_id": "step:1", "type": "command"},
        context={"runtime_session": "session:1"},
    )
    assert metadata["descriptive_only"] is True
    assert metadata["approval_state"] == ""
    assert validate_authority_metadata(metadata, surface="command")["ok"] is False


def test_noncanonical_execute_run_dispatch_sources_fail_gate() -> None:
    for action in ("execute", "run", "dispatch"):
        with pytest.raises(RuntimeExecutionAuthorityDenied):
            enforce_execution_authority(
                source="task_runner",
                action_type=action,
                metadata={"side_effect": True},
            )


def test_canonical_process_endpoint_passes_gate() -> None:
    decision = enforce_execution_authority(
        source="core.runtime.execution_gateway",
        action_type="command",
        metadata={"side_effect": True},
    )
    assert decision.allowed is True
    assert decision.reason == "canonical_execution_authority"


def test_step_executor_without_live_capability_fails_gate() -> None:
    with pytest.raises(RuntimeExecutionAuthorityDenied) as context:
        enforce_execution_authority(
            source="core.runtime.step_executor",
            action_type="command",
            metadata={"side_effect": True, "runtime_capability_validated": True},
        )
    assert context.value.decision.reason == "runtime_execution_capability_not_validated"
