from __future__ import annotations

from core.runtime.runtime_execution_authority_policy import evaluate_execution_authority
from core.runtime.runtime_execution_capability_unification import (
    CAPABILITY_TOKEN_LAYER,
    EXECUTION_AUTHORITY_LAYER,
    RUNTIME_ACTION_LAYER,
    RUNTIME_EXECUTION_CAPABILITY_FLOW,
    audit_runtime_execution_capability_unification,
    describe_runtime_execution_capability_flow,
)
from core.runtime.runtime_system_capability import RuntimeCapabilityClass, issue_runtime_system_capability


def test_runtime_execution_capability_layers_have_one_canonical_order() -> None:
    assert RUNTIME_EXECUTION_CAPABILITY_FLOW == (
        EXECUTION_AUTHORITY_LAYER,
        CAPABILITY_TOKEN_LAYER,
        RUNTIME_ACTION_LAYER,
    )
    description = describe_runtime_execution_capability_flow()
    assert description["rule"] == "execution_authority_decides_capability_token_proves_runtime_action_executes"
    assert description["no_execution_performed"] is True


def test_runtime_execution_capability_unification_audit_is_stable_and_policy_only() -> None:
    audit = audit_runtime_execution_capability_unification()
    payload = audit.to_dict()
    assert payload["ok"] is True
    assert payload["verified"] is True
    assert payload["reason"] == "runtime_execution_capability_layers_unified"
    assert payload["no_execution_performed"] is True
    assert {finding["name"] for finding in payload["findings"]} >= {
        "only_execute_role_may_perform_runtime_action",
        "runtime_actions_require_execution_gate",
        "system_capability_admin_does_not_grant_authority",
        "system_capability_inventory_has_no_wildcards",
    }


def test_system_capability_cannot_replace_execution_authority_for_step_execution() -> None:
    claims = {"task_id": "task:1", "package_id": "package:1", "session_id": "session:1"}
    system_capability = issue_runtime_system_capability(
        issuer="RuntimeDispatcher",
        capability_class=RuntimeCapabilityClass.EXECUTE,
        resource="runtime_task",
        action="execute",
        scope=claims,
        lineage=claims,
    )

    decision = evaluate_execution_authority(
        source="core.runtime.step_executor",
        action_type="execute",
        metadata={
            **claims,
            "step_id": "step:1",
            "runtime_system_capability": system_capability,
        },
    )

    assert decision.blocked is True
    assert decision.allowed is False
    assert decision.reason == "runtime_execution_capability_not_validated"
