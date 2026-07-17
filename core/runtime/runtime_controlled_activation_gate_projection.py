from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_controlled_activation_gate_contract import (
    CONTROLLED_ACTIVATION_GATE_CONTRACT_VERSION,
)
from core.runtime.runtime_controlled_activation_gate_policy import (
    CONTROLLED_ACTIVATION_GATE_POLICY_VERSION,
)


def project_controlled_activation_gate_review(
    request_payload: Mapping[str, Any],
    policy_result: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": CONTROLLED_ACTIVATION_GATE_CONTRACT_VERSION,
        "policy_version": CONTROLLED_ACTIVATION_GATE_POLICY_VERSION,
        "enabled": False,
        "gate_review_only": True,
        "preview_only": True,
        "gate_request_id": str(request_payload.get("gate_request_id") or ""),
        "activation_attempt_id": str(request_payload.get("activation_attempt_id") or ""),
        "transition_id": str(request_payload.get("transition_id") or ""),
        "projected_gate_status": "controlled_activation_gate_review_reserved",
        "controlled_activation_gate_ready_preview": bool(
            policy_result.get("controlled_activation_gate_ready_preview")
        ),
        "controlled_activation_allowed": False,
        "runtime_mode_transition_performed": False,
        "controlled_active_enabled": False,
        "real_mutation_enabled": False,
        "real_tool_execution_enabled": False,
        "autonomous_execution_enabled": False,
        "new_task_dispatched": False,
        "tool_invoked": False,
        "external_io_performed": False,
        "blockers": list(policy_result.get("blockers") or []),
    }
