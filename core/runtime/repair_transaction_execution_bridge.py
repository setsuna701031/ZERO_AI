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
    controlled_mutation_bridge: Any = None,
) -> MutationRuntimePipelineResult:
    executable = build_executable_repair_transaction(transaction)
    bridge_request = build_controlled_mutation_bridge_request(controlled_mutation_bridge)
    if bridge_request:
        executable = _with_controlled_mutation_bridge_metadata(executable, bridge_request)
        if approval_mode == MutationApprovalMode.AUTO:
            approval_mode = MutationApprovalMode.REVIEW_REQUIRED
        if verification == MutationVerificationRequirement.NONE:
            verification = MutationVerificationRequirement.TARGETED_TESTS

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


def build_controlled_mutation_bridge_request(source: Any) -> dict[str, Any]:
    if source is None:
        return {}
    payload = source if isinstance(source, Mapping) else {}
    bridge = payload.get("controlled_mutation_bridge")
    if isinstance(bridge, Mapping):
        bridge = dict(bridge)
    else:
        bridge = dict(payload)

    state = _first_nonempty(bridge.get("mutation_bridge_state"))
    eligible = bridge.get("mutation_bridge_eligible") is True
    terminal = (
        bridge.get("bridge_terminality") == "terminal"
        or bridge.get("mutation_bridge_blocked") is True
        and state == "bridge_blocked_terminal"
    )
    if not eligible:
        raise ValueError(f"controlled_mutation_bridge_not_eligible:{state or 'unknown'}")
    if terminal:
        raise ValueError("controlled_mutation_bridge_terminal_block")

    enforcement_snapshot = bridge.get("mutation_bridge_enforcement_snapshot")
    if not isinstance(enforcement_snapshot, Mapping) or not enforcement_snapshot:
        raise ValueError("controlled_mutation_bridge_missing_enforcement_snapshot")

    lineage = bridge.get("mutation_bridge_lineage")
    if not isinstance(lineage, Mapping) or not lineage:
        raise ValueError("controlled_mutation_bridge_missing_lineage")

    replay_snapshot = bridge.get("mutation_bridge_replay_snapshot")
    recovery_snapshot = bridge.get("mutation_bridge_recovery_snapshot")
    summary = bridge.get("controlled_mutation_bridge_summary")
    if not isinstance(summary, Mapping):
        summary = {}

    return {
        "controlled_mutation_bridge": True,
        "mutation_bridge_state": state or "bridge_ready_for_review",
        "mutation_bridge_reason": _first_nonempty(
            bridge.get("mutation_bridge_reason"),
            summary.get("reason"),
            "controlled mutation bridge review required",
        ),
        "mutation_bridge_eligible": True,
        "mutation_bridge_requires_review": True,
        "mutation_bridge_blocked": False,
        "mutation_bridge_lineage": dict(lineage),
        "mutation_bridge_enforcement_snapshot": dict(enforcement_snapshot),
        "mutation_bridge_replay_snapshot": dict(replay_snapshot) if isinstance(replay_snapshot, Mapping) else {},
        "mutation_bridge_recovery_snapshot": dict(recovery_snapshot) if isinstance(recovery_snapshot, Mapping) else {},
        "controlled_mutation_bridge_summary": {
            **dict(summary),
            "state": state or summary.get("state") or "bridge_ready_for_review",
            "eligible": True,
            "requires_review": True,
            "verification_required": True,
            "rollback_required": True,
        },
        "bridge_legality": "review_required",
        "bridge_requires_review": True,
        "bridge_terminality": "non_terminal",
        "bridge_verification_required": True,
        "bridge_rollback_required": True,
        "bridge_approval_mode": MutationApprovalMode.REVIEW_REQUIRED.value,
        "bridge_verification_mode": MutationVerificationRequirement.TARGETED_TESTS.value,
    }


def execute_committed_runtime_repair_transaction_mainline(
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
    controlled_mutation_bridge: Any = None,
):
    from core.runtime.repair_transaction_gateway_adapter import (
        run_governed_repair_transaction_mainline,
    )

    executable = build_executable_repair_transaction(transaction)
    bridge_request = build_controlled_mutation_bridge_request(controlled_mutation_bridge)
    if bridge_request:
        executable = _with_controlled_mutation_bridge_metadata(executable, bridge_request)
        if approval_mode == MutationApprovalMode.AUTO:
            approval_mode = MutationApprovalMode.REVIEW_REQUIRED
        if verification == MutationVerificationRequirement.NONE:
            verification = MutationVerificationRequirement.TARGETED_TESTS

    result = run_governed_repair_transaction_mainline(
        executable,
        workspace_root=workspace_root,
        sandbox_source_root=sandbox_source_root,
        rollback_root=rollback_root,
        report_root=report_root,
        initiator="repair_transaction_execution_bridge",
        intent="execute committed runtime repair transaction",
        reason="bridge committed runtime repair transaction into governed mutation execution",
        allowed_paths=tuple(allowed_roots),
        approval_mode=approval_mode,
        verification=verification,
        risk_level=risk_level,
        dry_run=dry_run,
    )

    impacted_files = [
        str(operation.get("target_path")).strip()
        for operation in executable.get("operations", [])
        if isinstance(operation, Mapping)
        and str(operation.get("target_path") or "").strip()
    ]

    impacted_files = list(dict.fromkeys(impacted_files))

    if hasattr(result, "metadata") and isinstance(result.metadata, dict):
        metadata = dict(result.metadata)
        metadata["changed_files"] = list(impacted_files)
        metadata["impacted_files"] = list(impacted_files)

        evidence = metadata.get("evidence")
        if not isinstance(evidence, dict):
            evidence = {}

        mutation_summary = evidence.get("mutation_summary")
        if not isinstance(mutation_summary, dict):
            mutation_summary = {}

        mutation_summary["changed_files"] = list(impacted_files)
        mutation_summary["impacted_files"] = list(impacted_files)

        evidence["mutation_summary"] = mutation_summary
        metadata["evidence"] = evidence

        try:
            object.__setattr__(result, "metadata", metadata)
        except Exception:
            pass

    return result


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


def _with_controlled_mutation_bridge_metadata(
    transaction: Mapping[str, Any],
    bridge_request: Mapping[str, Any],
) -> dict[str, Any]:
    executable = dict(transaction)
    metadata = _mapping_copy(executable.get("metadata"))
    metadata["controlled_mutation_bridge"] = dict(bridge_request)
    metadata["approval_required"] = True
    metadata["verification_required"] = True
    metadata["rollback_required"] = True
    metadata["audit_required"] = True
    authority = _mapping_copy(metadata.get("repair_authority_governance"))
    authority["controlled_mutation_bridge"] = {
        "eligible": True,
        "requires_review": True,
        "verification_required": True,
        "rollback_required": True,
        "audit_required": True,
    }
    metadata["repair_authority_governance"] = authority
    lineage = _mapping_copy(metadata.get("lineage"))
    bridge_lineage = bridge_request.get("mutation_bridge_lineage")
    if isinstance(bridge_lineage, Mapping):
        lineage["controlled_mutation_bridge"] = dict(bridge_lineage)
    metadata["lineage"] = lineage
    executable["metadata"] = metadata
    return executable


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
