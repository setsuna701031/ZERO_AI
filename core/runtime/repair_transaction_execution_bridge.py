from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from core.runtime.governed_repair_execution import execute_governed_repair_transaction
from core.runtime.mutation_runtime_pipeline import MutationRuntimePipelineResult
from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationRiskLevel,
    MutationVerificationRequirement,
)

GovernedRepairGateHook = Callable[[dict[str, Any]], Any]


def execute_committed_runtime_repair_transaction(
    transaction: Any,
    *,
    workspace_root: str | Path,
    sandbox_source_root: str | Path,
    rollback_root: str | Path,
    report_root: str | Path,
    allowed_roots: list[str] | tuple[str, ...],
    approval_mode: MutationApprovalMode = MutationApprovalMode.REVIEW_REQUIRED,
    verification: MutationVerificationRequirement = MutationVerificationRequirement.TARGETED_TESTS,
    risk_level: MutationRiskLevel = MutationRiskLevel.MEDIUM,
    dry_run: bool | None = None,
    gate_hook: GovernedRepairGateHook | None = None,
    use_runtime_recovery_gate: bool = False,
) -> MutationRuntimePipelineResult:
    executable = build_executable_repair_transaction(transaction)

    return execute_governed_repair_transaction(
        executable,
        workspace_root=workspace_root,
        sandbox_source_root=sandbox_source_root,
        rollback_root=rollback_root,
        report_root=report_root,
        allowed_roots=allowed_roots,
        initiator="repair_transaction_execution_bridge",
        intent="execute committed runtime repair transaction",
        reason="bridge committed runtime repair transaction into governed mutation execution",
        approval_mode=approval_mode,
        verification=verification,
        risk_level=risk_level,
        dry_run=dry_run,
        gate_hook=gate_hook,
        use_runtime_recovery_gate=use_runtime_recovery_gate,
    )


def build_executable_repair_transaction(transaction: Any) -> dict[str, Any]:
    tx = transaction if isinstance(transaction, Mapping) else {}

    transaction_type = _first_nonempty(tx.get("transaction_type"))
    if transaction_type and transaction_type != "runtime_repair_transaction":
        raise ValueError(f"unsupported_runtime_repair_transaction_type:{transaction_type}")

    state = _first_nonempty(tx.get("state"))
    if state != "committed":
        raise ValueError(f"runtime_repair_transaction_not_committed:{state or 'unknown'}")

    committed_mutations = tx.get("committed_mutations")
    if not isinstance(committed_mutations, list) or not committed_mutations:
        raise ValueError("runtime_repair_transaction_has_no_committed_mutations")

    operations = [
        _operation_from_committed_mutation(item)
        for item in committed_mutations
        if isinstance(item, Mapping)
    ]
    operations = [item for item in operations if item]

    if not operations:
        raise ValueError("runtime_repair_transaction_has_no_executable_operations")

    transaction_id = _first_nonempty(tx.get("transaction_id"))
    mutation_request_id = _first_nonempty(
        _metadata_value(tx, "mutation_request_id"),
        tx.get("mutation_request_id"),
        f"repair_request:{transaction_id}",
    )
    replay_id = _first_nonempty(
        _metadata_value(tx, "replay_id"),
        tx.get("replay_id"),
        f"replay:{transaction_id}",
    )
    audit_id = _first_nonempty(
        _metadata_value(tx, "audit_id"),
        tx.get("audit_id"),
        f"audit:{transaction_id}",
    )

    return {
        "transaction_type": "runtime_repair_transaction_execution",
        "transaction_id": transaction_id,
        "mutation_request_id": mutation_request_id,
        "replay_id": replay_id,
        "audit_id": audit_id,
        "task_id": _first_nonempty(tx.get("task_id")),
        "proposal_id": _first_nonempty(tx.get("proposal_id")),
        "created_at": _first_nonempty(tx.get("created_at"), "1970-01-01T00:00:00Z"),
        "status": "staged",
        "dry_run": bool(tx.get("dry_run", False)),
        "operations": operations,
        "authorization": _mapping_copy(tx.get("authorization")),
        "scope_gate": _mapping_copy(tx.get("scope_gate")),
        "audit_events": [dict(item) for item in tx.get("audit_events", []) if isinstance(item, Mapping)],
        "metadata": {
            "source": "runtime_repair_transaction",
            "original_state": state,
            "transaction_type": _first_nonempty(tx.get("transaction_type"), "runtime_repair_transaction"),
            "transaction_version": _first_nonempty(tx.get("transaction_version")),
            "mutation_request_id": mutation_request_id,
            "replay_id": replay_id,
            "audit_id": audit_id,
            "lineage": _repair_transaction_lineage(
                tx,
                mutation_request_id=mutation_request_id,
                replay_id=replay_id,
                audit_id=audit_id,
            ),
            "repair_authority_governance": _repair_authority_governance(tx),
        },
    }


def _operation_from_committed_mutation(mutation: Mapping[str, Any]) -> dict[str, Any]:
    raw = mutation.get("raw_mutation")
    raw_mutation = raw if isinstance(raw, Mapping) else mutation

    target_path = _first_nonempty(
        raw_mutation.get("target_path"),
        raw_mutation.get("path"),
        raw_mutation.get("file_path"),
        mutation.get("target_path"),
    )

    if not target_path:
        raise ValueError("committed_mutation_target_path_missing")

    action = _first_nonempty(
        raw_mutation.get("op_type"),
        raw_mutation.get("operation"),
        raw_mutation.get("action"),
        mutation.get("action"),
        "write_file",
    )

    if action in {"write", "replace", "create"}:
        action = "write_file"
    elif action in {"patch", "apply_patch"}:
        action = "patch_file"

    if action == "delete_file":
        raise ValueError("delete_file_operations_are_not_supported_by_execution_bridge")

    if action not in {"write_file", "patch_file"}:
        raise ValueError(f"unsupported_committed_mutation_action:{action}")

    operation: dict[str, Any] = {
        "op_type": action,
        "target_path": str(target_path),
    }

    if "content" in raw_mutation:
        operation["content"] = raw_mutation.get("content")

    if "patch" in raw_mutation:
        operation["patch"] = raw_mutation.get("patch")

    return operation


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _metadata_value(transaction: Mapping[str, Any], key: str) -> Any:
    metadata = transaction.get("metadata")
    if isinstance(metadata, Mapping):
        return metadata.get(key)
    return None


def _mapping_copy(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _repair_transaction_lineage(
    transaction: Mapping[str, Any],
    *,
    mutation_request_id: str,
    replay_id: str,
    audit_id: str,
) -> dict[str, Any]:
    metadata = _mapping_copy(transaction.get("metadata"))
    metadata_lineage = metadata.get("lineage") if isinstance(metadata.get("lineage"), Mapping) else {}
    return {
        **dict(metadata_lineage),
        "transaction_id": _first_nonempty(transaction.get("transaction_id")),
        "mutation_transaction_id": _first_nonempty(transaction.get("transaction_id")),
        "mutation_request_id": mutation_request_id,
        "task_id": _first_nonempty(transaction.get("task_id")),
        "proposal_id": _first_nonempty(transaction.get("proposal_id")),
        "session_id": _first_nonempty(metadata.get("session_id")),
        "replay_id": replay_id,
        "audit_id": audit_id,
        "source": "runtime_repair_transaction",
    }


def _repair_authority_governance(transaction: Mapping[str, Any]) -> dict[str, Any]:
    authorization = _mapping_copy(transaction.get("authorization"))
    scope_gate = _mapping_copy(transaction.get("scope_gate"))
    metadata = _mapping_copy(transaction.get("metadata"))
    return {
        "governance_source": "runtime_repair_transaction",
        "transaction_state": _first_nonempty(transaction.get("state")),
        "requires_approval": bool(transaction.get("requires_approval")),
        "authorization_present": bool(authorization),
        "scope_gate_present": bool(scope_gate),
        "scope_allowed": scope_gate.get("scope_allowed", True),
        "authorization": authorization,
        "scope_gate": scope_gate,
        "metadata_authority": _mapping_copy(metadata.get("authority")),
    }
