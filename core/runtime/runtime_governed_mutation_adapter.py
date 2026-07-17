from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

from core.runtime.mutation_gateway import MutationGatewayRequest
from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationScope,
    MutationVerificationRequirement,
)
from core.runtime.mutation_verification import MutationVerificationCheck


ZERO_RUNTIME_GOVERNED_MUTATION_ADAPTER_SCHEMA = (
    "zero.runtime.governed_mutation_adapter.v1"
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> Mapping[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        result = to_dict()
        if isinstance(result, Mapping):
            return result
    return {}


def _relative_path(value: Any) -> str:
    text = _text(value).replace("\\", "/")
    if not text:
        raise ValueError("mutation_change_path_required")

    path = PurePosixPath(text)

    if path.is_absolute() or any(part == ".." for part in path.parts):
        raise ValueError("mutation_change_path_must_be_workspace_relative")

    normalized = str(path).rstrip("/")

    if normalized in {"", "."}:
        raise ValueError("mutation_change_path_required")

    return normalized


def _allowed_path(path: str) -> str:
    parts = PurePosixPath(path).parts
    if len(parts) >= 2:
        return "/".join(parts[:2])
    return parts[0]


def _operation(change: Mapping[str, Any]) -> dict[str, Any]:
    path = _relative_path(
        change.get("path")
        or change.get("relative_path")
        or change.get("target_path")
    )

    content = (
        change.get("content")
        if change.get("content") is not None
        else change.get("new_content")
    )

    if content is None:
        content = ""

    operation = _text(change.get("operation")).lower()

    op_type = "replace"
    if operation in {"delete_file", "delete", "remove_file"}:
        op_type = "delete"
    elif operation in {"create_file", "write_file", "update_file", "replace"}:
        op_type = "replace"

    return {
        "path": path,
        "target_path": path,
        "op_type": op_type,
        "content": str(content),
    }


def _verification_check(request: Mapping[str, Any]) -> MutationVerificationCheck:
    authority = _mapping(request.get("authority_context"))
    changes = [_mapping(item) for item in request.get("requested_changes") or []]

    validation_passed = (
        authority.get("force_validation_failure") is not True
        and not any(
            change.get("force_validation_failure") is True
            for change in changes
        )
    )

    return MutationVerificationCheck(
        name="operator_console_controlled_validation",
        passed=validation_passed,
        details=(
            "operator_console_validation_passed"
            if validation_passed
            else "operator_console_validation_failed"
        ),
    )


def _changed_files(payload: Mapping[str, Any]) -> list[str]:
    if isinstance(payload.get("impacted_files"), list):
        return [str(item) for item in payload.get("impacted_files") or []]

    apply_result = _mapping(payload.get("apply_result"))
    applied = [str(item) for item in apply_result.get("applied_paths") or []]
    skipped = [str(item) for item in apply_result.get("skipped_paths") or []]

    return applied or skipped


def _target_root(request: Mapping[str, Any]) -> str:
    requested = _text(
        request.get("target_root")
        or request.get("mutation_target_root")
    )
    return requested or "workspace"


def _repo_root_mutation_allowed(request: Mapping[str, Any]) -> bool:
    authority = _mapping(request.get("authority_context"))
    target_root = _target_root(request)

    approved_repo_targets = {".", "repo", "repository", "worktree"}

    return (
        target_root in approved_repo_targets
        and authority.get("controlled_execution_required") is True
        and authority.get("governed_mutation_adapter_required") is True
        and authority.get("operator_service_required") is True
        and authority.get("direct_dispatch_allowed") is False
        and authority.get("executor_bypass_allowed") is False
        and authority.get("validation_required") is True
        and authority.get("rollback_required") is True
    )


@dataclass
class RuntimeGovernedMutationAdapter:
    workspace_root: str | Path = (
        "workspace/operator_console/governed_mutation/workspace"
    )
    sandbox_source_root: str | Path = (
        "workspace/operator_console/governed_mutation/sandbox"
    )
    rollback_root: str | Path = (
        "workspace/operator_console/governed_mutation/rollback"
    )
    report_root: str | Path = (
        "workspace/operator_console/governed_mutation/reports"
    )
    repo_root: str | Path = "."
    governed_runtime_runner: Callable[[MutationGatewayRequest], Any] | None = None

    safe_governed_mutation_adapter: bool = True

    def execute_governed_mutation(
        self,
        request: Mapping[str, Any],
    ) -> dict[str, Any]:
        controlled_request = _mapping(request)

        try:
            gateway_request = self.to_gateway_request(controlled_request)

            runner = self.governed_runtime_runner
            if runner is None:
                from core.runtime.governed_mutation_runtime import (
                    run_governed_mutation_runtime,
                )

                runner = run_governed_mutation_runtime

            raw_result = runner(gateway_request)

        except Exception as exc:
            return {
                "schema": ZERO_RUNTIME_GOVERNED_MUTATION_ADAPTER_SCHEMA,
                "adapter_status": "blocked_governed_mutation_runtime_unavailable",
                "mutation_started": False,
                "mutation_completed": False,
                "validation_passed": False,
                "rollback_required": False,
                "rollback_completed": False,
                "commit_allowed": False,
                "changed_files": [],
                "repo_root_mutation": False,
                "non_mainline_issues": [
                    (
                        "governed_mutation_runtime_unavailable:"
                        f"{exc.__class__.__name__}"
                    )
                ],
            }

        payload = (
            raw_result.to_dict()
            if hasattr(raw_result, "to_dict")
            else dict(_mapping(raw_result))
        )

        verified = bool(payload.get("verified") is True)
        rolled_back = bool(payload.get("rolled_back") is True)
        failed = bool(payload.get("failed") is True)
        blocked = bool(payload.get("blocked") is True)
        changed_files = _changed_files(payload)

        return {
            "schema": ZERO_RUNTIME_GOVERNED_MUTATION_ADAPTER_SCHEMA,
            "adapter_status": "completed",
            "mutation_started": bool(
                payload.get("executed") is True
                or changed_files
            ),
            "mutation_completed": not blocked,
            "validation_passed": verified and not failed,
            "rollback_required": bool(rolled_back or failed),
            "rollback_completed": rolled_back,
            "commit_allowed": bool(
                verified
                and not failed
                and not rolled_back
            ),
            "changed_files": changed_files,
            "repo_root_mutation": bool(
                payload.get("repo_root_mutation") is True
            ),
            "governed_mutation_adapter_attached": True,
            "governed_runtime_result": payload,
            "non_mainline_issues": list(
                payload.get("non_mainline_issues") or []
            ),
        }

    def to_gateway_request(
        self,
        request: Mapping[str, Any],
    ) -> MutationGatewayRequest:
        changes = [
            _mapping(item)
            for item in request.get("requested_changes") or []
        ]

        operations = tuple(
            _operation(change)
            for change in changes
            if change
        )

        relative_paths = tuple(item["path"] for item in operations)

        if not relative_paths:
            raise ValueError("controlled_mutation_request_changes_required")

        authority = _mapping(request.get("authority_context"))
        lineage = _mapping(request.get("lineage"))
        repo_root_mutation = _repo_root_mutation_allowed(request)

        workspace_root = (
            Path(self.repo_root)
            if repo_root_mutation
            else Path(self.workspace_root)
        )

        metadata = {
            "schema": ZERO_RUNTIME_GOVERNED_MUTATION_ADAPTER_SCHEMA,
            "mutation_request_id": _text(request.get("mutation_request_id")),
            "execution_id": _text(request.get("execution_id")),
            "executor_result_id": _text(request.get("executor_result_id")),
            "authority_context": dict(authority),
            "lineage": dict(lineage),
            "runtime_operator_service_owner": True,
            "console_facade_only": True,
            "target_root": _target_root(request),
            "repo_root_mutation": repo_root_mutation,
        }

        return MutationGatewayRequest(
            intent="Controlled runtime operator mutation",
            initiator="RuntimeOperatorService",
            reason="controlled_mutation_unlock",
            relative_paths=relative_paths,
            scope=MutationScope(
                allowed_paths=tuple(
                    sorted(
                        {
                            _allowed_path(path)
                            for path in relative_paths
                        }
                    )
                ),
                max_files_changed=len(relative_paths),
                allow_new_files=True,
                allow_delete_files=False,
            ),
            workspace_root=workspace_root,
            sandbox_source_root=Path(self.sandbox_source_root),
            rollback_root=Path(self.rollback_root),
            report_root=Path(self.report_root),
            operations=operations,
            approval_mode=MutationApprovalMode.AUTO,
            verification=MutationVerificationRequirement.TARGETED_TESTS,
            verification_checks=(_verification_check(request),),
            dry_run=False,
            governed_mainline=True,
            metadata=metadata,
        )


__all__ = [
    "RuntimeGovernedMutationAdapter",
    "ZERO_RUNTIME_GOVERNED_MUTATION_ADAPTER_SCHEMA",
]