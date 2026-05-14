from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.runtime.mutation_gateway import MutationGatewayRequest, run_governed_mutation
from core.runtime.mutation_runtime_pipeline import MutationRuntimePipelineResult
from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationRiskLevel,
    MutationScope,
    MutationVerificationRequirement,
)


def build_gateway_request_from_repair_transaction(
    transaction: Any,
    *,
    workspace_root: str | Path,
    sandbox_source_root: str | Path,
    rollback_root: str | Path,
    report_root: str | Path,
    initiator: str = "repair_transaction_gateway_adapter",
    intent: str = "governed repair transaction",
    reason: str = "convert runtime repair transaction into governed mutation request",
    allowed_paths: tuple[str, ...] | None = None,
    denied_paths: tuple[str, ...] = (),
    risk_level: MutationRiskLevel = MutationRiskLevel.MEDIUM,
    approval_mode: MutationApprovalMode = MutationApprovalMode.REVIEW_REQUIRED,
    verification: MutationVerificationRequirement = MutationVerificationRequirement.TARGETED_TESTS,
    dry_run: bool | None = None,
) -> MutationGatewayRequest:
    safe_transaction = transaction if isinstance(transaction, Mapping) else {}

    operations = _extract_operations(safe_transaction)
    relative_paths = _relative_paths_from_operations(operations)

    if not relative_paths:
        raise ValueError("repair_transaction_has_no_mutation_paths")

    sandbox_files = _extract_sandbox_files(safe_transaction)

    resolved_dry_run = bool(safe_transaction.get("dry_run", True)) if dry_run is None else bool(dry_run)

    scope = MutationScope(
        allowed_paths=tuple(allowed_paths or _derive_allowed_paths(relative_paths)),
        denied_paths=tuple(denied_paths),
        max_files_changed=len(relative_paths),
        allow_new_files=True,
        allow_delete_files=False,
    )

    metadata = {
        "source": "runtime_repair_apply_transaction",
        "transaction_id": _first_nonempty(safe_transaction.get("transaction_id")),
        "transaction_status": _first_nonempty(safe_transaction.get("transaction_status")),
        "task_id": _first_nonempty(safe_transaction.get("task_id")),
        "proposal_id": _first_nonempty(safe_transaction.get("proposal_id")),
        "adapter": "repair_transaction_gateway_adapter",
    }

    return MutationGatewayRequest(
        intent=intent,
        initiator=initiator,
        reason=reason,
        relative_paths=tuple(relative_paths),
        scope=scope,
        workspace_root=workspace_root,
        sandbox_source_root=sandbox_source_root,
        rollback_root=rollback_root,
        report_root=report_root,
        operations=tuple(operations),
        sandbox_files=sandbox_files,
        risk_level=risk_level,
        approval_mode=approval_mode,
        verification=verification,
        dry_run=resolved_dry_run,
        metadata=metadata,
    )


def run_governed_repair_transaction(
    transaction: Any,
    *,
    workspace_root: str | Path,
    sandbox_source_root: str | Path,
    rollback_root: str | Path,
    report_root: str | Path,
    initiator: str = "repair_transaction_gateway_adapter",
    intent: str = "governed repair transaction",
    reason: str = "execute runtime repair transaction through governed mutation gateway",
    allowed_paths: tuple[str, ...] | None = None,
    denied_paths: tuple[str, ...] = (),
    risk_level: MutationRiskLevel = MutationRiskLevel.MEDIUM,
    approval_mode: MutationApprovalMode = MutationApprovalMode.REVIEW_REQUIRED,
    verification: MutationVerificationRequirement = MutationVerificationRequirement.TARGETED_TESTS,
    dry_run: bool | None = None,
) -> MutationRuntimePipelineResult:
    request = build_gateway_request_from_repair_transaction(
        transaction,
        workspace_root=workspace_root,
        sandbox_source_root=sandbox_source_root,
        rollback_root=rollback_root,
        report_root=report_root,
        initiator=initiator,
        intent=intent,
        reason=reason,
        allowed_paths=allowed_paths,
        denied_paths=denied_paths,
        risk_level=risk_level,
        approval_mode=approval_mode,
        verification=verification,
        dry_run=dry_run,
    )
    return run_governed_mutation(request)


def _extract_operations(transaction: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_operations = transaction.get("operations")
    if isinstance(raw_operations, list):
        operations = [
            _normalize_operation(item)
            for item in raw_operations
            if isinstance(item, Mapping)
        ]
        if operations:
            return operations

    staged_patches = transaction.get("staged_patches")
    if isinstance(staged_patches, list):
        operations = [
            _operation_from_staged_patch(item, transaction=transaction)
            for item in staged_patches
            if isinstance(item, Mapping)
        ]
        operations = [item for item in operations if item]
        if operations:
            return operations

    staged_patch = transaction.get("staged_patch")
    if isinstance(staged_patch, Mapping):
        operation = _operation_from_staged_patch(staged_patch, transaction=transaction)
        if operation:
            return [operation]

    return []


def _normalize_operation(operation: Mapping[str, Any]) -> dict[str, Any]:
    target_path = _normalize_relative_path(
        _first_nonempty(
            operation.get("target_path"),
            operation.get("relative_path"),
            operation.get("path"),
        )
    )
    op_type = _first_nonempty(operation.get("op_type"), operation.get("operation"), "write_file")

    if op_type == "delete_file":
        raise ValueError("delete_file_operations_are_not_supported_by_governed_mutation_adapter")

    if op_type not in {"write_file", "patch_file", "replace"}:
        raise ValueError(f"unsupported_repair_operation:{op_type}")

    normalized = dict(operation)
    normalized["target_path"] = target_path
    normalized["op_type"] = op_type
    return normalized


def _operation_from_staged_patch(
    staged_patch: Mapping[str, Any],
    *,
    transaction: Mapping[str, Any],
) -> dict[str, Any]:
    target_path = _normalize_relative_path(staged_patch.get("target_path"))

    raw_preview = transaction.get("raw_patch_preview")
    preview = raw_preview if isinstance(raw_preview, Mapping) else {}
    diff_text = _first_nonempty(preview.get("diff"), staged_patch.get("diff"))

    operation: dict[str, Any] = {
        "op_type": "patch_file",
        "target_path": target_path,
    }

    if diff_text:
        operation["patch"] = diff_text

    return operation


def _relative_paths_from_operations(operations: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []

    for operation in operations:
        path = _normalize_relative_path(operation.get("target_path"))
        if path and path not in paths:
            paths.append(path)

    return paths


def _extract_sandbox_files(transaction: Mapping[str, Any]) -> dict[str, Any]:
    raw_sandbox_files = transaction.get("sandbox_files")
    if not isinstance(raw_sandbox_files, Mapping):
        return {}

    sandbox_files: dict[str, Any] = {}
    for path, content in raw_sandbox_files.items():
        sandbox_files[_normalize_relative_path(path)] = content
    return sandbox_files


def _derive_allowed_paths(relative_paths: list[str]) -> tuple[str, ...]:
    roots: list[str] = []

    for path in relative_paths:
        normalized = _normalize_relative_path(path)
        root = normalized.split("/", 1)[0]
        if root and root not in roots:
            roots.append(root)

    return tuple(roots)


def _normalize_relative_path(path_value: Any) -> str:
    path_text = _first_nonempty(path_value).replace("\\", "/")
    if not path_text:
        raise ValueError("mutation_path_missing")

    while path_text.startswith("./"):
        path_text = path_text[2:]

    parts: list[str] = []
    for part in path_text.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            raise ValueError(f"mutation_path_escapes_workspace:{path_value}")
        parts.append(part)

    normalized = "/".join(parts)
    if not normalized:
        raise ValueError("mutation_path_missing")

    if normalized.startswith("/"):
        raise ValueError(f"mutation_path_must_be_relative:{path_value}")

    return normalized


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""