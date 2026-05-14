from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.runtime.governed_repair_execution import execute_governed_repair_transaction
from core.runtime.mutation_runtime_pipeline import MutationRuntimePipelineResult
from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationRiskLevel,
    MutationVerificationRequirement,
)


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
    )


def build_executable_repair_transaction(transaction: Any) -> dict[str, Any]:
    tx = transaction if isinstance(transaction, Mapping) else {}

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

    return {
        "transaction_id": _first_nonempty(tx.get("transaction_id")),
        "task_id": _first_nonempty(tx.get("task_id")),
        "proposal_id": _first_nonempty(tx.get("proposal_id")),
        "created_at": _first_nonempty(tx.get("created_at"), "1970-01-01T00:00:00Z"),
        "status": "staged",
        "dry_run": bool(tx.get("dry_run", False)),
        "operations": operations,
        "metadata": {
            "source": "runtime_repair_transaction",
            "original_state": state,
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