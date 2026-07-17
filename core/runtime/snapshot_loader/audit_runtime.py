from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from core.runtime.snapshot_loader.approval_runtime import build_approval_request
from core.runtime.snapshot_loader.policy_decision import decide_execution_policy


def build_audit_record(
    action: str,
    payload: Optional[Mapping[str, Any]] = None,
    audit_id: str = "audit-record",
    source: str = "snapshot_loader",
) -> Dict[str, Any]:
    policy = decide_execution_policy(action)
    approval = build_approval_request(action, request_id=f"{audit_id}:approval")

    return {
        "audit_id": audit_id,
        "source": source,
        "action": policy["action"],
        "payload": dict(payload or {}),
        "classification": policy["classification"],
        "risk_level": policy["risk_level"],
        "policy_decision": policy["decision"],
        "policy_reason": policy["reason"],
        "approval_state": approval["state"],
        "approval_required": approval["approval_required"],
        "audit_required": approval["audit_required"],
        "governance_critical": policy["governance_critical"],
        "replay_sensitive": policy["replay_sensitive"],
        "mutation_capable": policy["mutation_capable"],
        "policy": policy,
        "approval": approval,
    }


def build_audit_lineage(
    records: list[Mapping[str, Any]],
    lineage_id: str = "runtime-audit-lineage",
) -> Dict[str, Any]:
    if not isinstance(records, list):
        raise TypeError("records must be a list")

    normalized_records = [dict(record) for record in records]

    return {
        "lineage_id": lineage_id,
        "record_count": len(normalized_records),
        "records": normalized_records,
        "actions": [record.get("action") for record in normalized_records],
        "policy_decisions": [
            record.get("policy_decision")
            for record in normalized_records
        ],
        "approval_states": [
            record.get("approval_state")
            for record in normalized_records
        ],
        "audit_required_actions": [
            record.get("action")
            for record in normalized_records
            if record.get("audit_required") is True
        ],
        "governance_critical_actions": [
            record.get("action")
            for record in normalized_records
            if record.get("governance_critical") is True
        ],
    }


def build_audit_runtime_summary() -> Dict[str, Any]:
    actions = [
        "readonly_execution",
        "mutation_runtime",
        "patch_apply",
        "unrestricted_shell",
    ]

    records = [
        build_audit_record(
            action=action,
            audit_id=f"audit-{action}",
        )
        for action in actions
    ]

    lineage = build_audit_lineage(
        records=records,
        lineage_id="snapshot-loader-audit-summary",
    )

    return {
        "audit_runtime": "snapshot_loader_audit_runtime",
        "records": records,
        "lineage": lineage,
        "audit_required_actions": lineage["audit_required_actions"],
        "governance_critical_actions": lineage["governance_critical_actions"],
    }