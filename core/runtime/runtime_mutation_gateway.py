"""Governed runtime mutation gateway."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.runtime.executor import Executor
from core.runtime.runtime_execution_request import RuntimeExecutionRequest
from core.runtime.runtime_authority import RuntimeAuthorityEvaluator
from core.runtime.runtime_capability_scope import RuntimeCapabilityScopeEvaluator
from core.runtime.runtime_kernel_protection import RuntimeKernelProtection
from core.runtime.runtime_mutation_policy import RuntimeMutationPolicy
from core.runtime.runtime_mutation_policy import classify_mutation_risk
from core.runtime.runtime_mutation_transaction import (
    RuntimeMutationOperation,
    RuntimeMutationRequest,
    RuntimeMutationTransaction,
    RuntimeMutationTransactionResult,
)
from core.runtime.runtime_side_effect_registry import RuntimeSideEffectRegistry
from core.runtime.runtime_lifecycle_context import (
    create_current_lifecycle_record,
    lifecycle_id_for_artifact,
    mark_current_lifecycle_active,
    mark_current_lifecycle_committed,
    mark_current_lifecycle_failed,
    mark_current_lifecycle_verified,
)
from core.runtime.runtime_transaction_context import (
    bind_current_mutation,
    bind_current_snapshot,
    bind_current_side_effect,
    merge_current_transaction_metadata,
)
from core.runtime.runtime_state_snapshot import (
    RuntimeStateSnapshotter,
    hash_bytes,
    hash_text,
)


APPROVED_MUTATION_OPERATIONS = {
    "file_write",
    "generated_artifact_write",
}


class RuntimeMutationGateway:
    """Only approved entrance for runtime mutation."""

    def __init__(
        self,
        *,
        workspace_root: str | Path,
        mutation_policy: RuntimeMutationPolicy | None = None,
        authority_evaluator: RuntimeAuthorityEvaluator | None = None,
        capability_evaluator: RuntimeCapabilityScopeEvaluator | None = None,
        kernel_protection: RuntimeKernelProtection | None = None,
        side_effect_registry: RuntimeSideEffectRegistry | None = None,
        snapshotter: RuntimeStateSnapshotter | None = None,
        executor: Executor | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.mutation_policy = mutation_policy or RuntimeMutationPolicy()
        self.authority_evaluator = authority_evaluator or RuntimeAuthorityEvaluator()
        self.capability_evaluator = capability_evaluator or RuntimeCapabilityScopeEvaluator()
        self.kernel_protection = kernel_protection or RuntimeKernelProtection()
        self.side_effect_registry = side_effect_registry or RuntimeSideEffectRegistry()
        self.snapshotter = snapshotter or RuntimeStateSnapshotter()
        self.executor = executor or Executor(
            workspace_root=self.workspace_root,
            side_effect_registry=self.side_effect_registry,
        )

    def mutate(self, request: RuntimeMutationRequest) -> RuntimeMutationTransactionResult:
        request_metadata = merge_current_transaction_metadata(request.metadata)
        request_lineage = merge_current_transaction_metadata({"lineage": dict(request.lineage)}).get("lineage", dict(request.lineage))
        request_provenance = merge_current_transaction_metadata({"provenance": dict(request.provenance)}).get("provenance", dict(request.provenance))
        try:
            from dataclasses import replace as _dataclass_replace
            request = _dataclass_replace(
                request,
                metadata=request_metadata,
                lineage=request_lineage,
                provenance=request_provenance,
            )
        except Exception:
            pass
        started_at = _utc_timestamp()
        transaction_id = f"runtime_mutation:{request.request_id}"
        bind_current_mutation(transaction_id, metadata={"source": "runtime_mutation_gateway"})
        mutation_lifecycle_id = lifecycle_id_for_artifact("mutation", transaction_id)
        create_current_lifecycle_record(
            lifecycle_id=mutation_lifecycle_id,
            artifact_id=transaction_id,
            artifact_type="mutation",
            lineage=request.lineage,
            provenance=request.provenance,
            metadata={"source": "runtime_mutation_gateway"},
        )
        mark_current_lifecycle_active(
            mutation_lifecycle_id,
            metadata={"source": "runtime_mutation_gateway"},
        )
        target_path = self._resolve_target_path(request.target_path)
        if request.identity is None:
            return self._blocked_without_execution(
                request=request,
                transaction_id=transaction_id,
                status_reason="runtime_identity_required",
                started_at=started_at,
            )
        if request.authority_scope is None:
            return self._blocked_without_execution(
                request=request,
                transaction_id=transaction_id,
                status_reason="runtime_authority_scope_required",
                started_at=started_at,
            )
        if request.capability_scope is None:
            return self._blocked_without_execution(
                request=request,
                transaction_id=transaction_id,
                status_reason="runtime_capability_scope_required",
                started_at=started_at,
            )
        risk_level = classify_mutation_risk(
            operation_type=request.operation_type,
            target_path=str(target_path),
            metadata=request.metadata,
        )
        authority_result = self.authority_evaluator.evaluate(
            identity=request.identity,
            authority_scope=request.authority_scope,
            mutation_type=request.operation_type,
            target_path=str(target_path),
            risk_level=risk_level,
            lineage=request.lineage,
        )
        capability_result = self.capability_evaluator.evaluate(
            capability_scope=request.capability_scope,
            mutation_type=request.operation_type,
            target_path=str(target_path),
            risk_level=risk_level,
            requires_replay=bool(request.replay_id),
            requires_rollback=True,
            metadata=request.metadata,
        )
        protection_result = self.kernel_protection.evaluate(
            identity=request.identity,
            target_path=str(target_path),
            mutation_type=request.operation_type,
            risk_level=risk_level,
            metadata={
                **dict(request.metadata),
                "explicit_authority": bool(
                    request.metadata.get("explicit_authority", False)
                    or request.authority_scope.metadata.get("explicit_authority", False)
                ),
            },
        )
        policy_result = self.mutation_policy.evaluate(
            operation_type=request.operation_type,
            target_path=str(target_path),
            lineage=request.lineage,
            metadata={
                **dict(request.metadata),
                "dry_run": request.dry_run,
                "replay_id": request.replay_id,
                "audit_id": request.audit_id,
                **authority_result.to_metadata(),
                **capability_result.to_metadata(),
                **protection_result.to_metadata(),
            },
        )
        execution_result = self._record_execution_governance(
            request=request,
            transaction_id=transaction_id,
            policy_metadata={
                **policy_result.to_metadata(),
                **authority_result.to_metadata(),
                **capability_result.to_metadata(),
                **protection_result.to_metadata(),
                "provenance": dict(request.provenance),
            },
        )

        if (
            not authority_result.allowed
            or authority_result.state == "requires_confirmation"
            or not capability_result.allowed
            or not protection_result.allowed
        ):
            reason = self._first_block_reason(
                authority_result=authority_result,
                capability_result=capability_result,
                protection_result=protection_result,
            )
            transaction = self._transaction(
                transaction_id=transaction_id,
                request=request,
                policy_result=policy_result,
                operations=(),
                snapshot_id=None,
                status="blocked",
                started_at=started_at,
                finished_at=_utc_timestamp(),
                verified=False,
                rollback_required=False,
                metadata={
                    "reason": reason,
                    "authority": authority_result.to_metadata(),
                    "capability": capability_result.to_metadata(),
                    "protection": protection_result.to_metadata(),
                    "provenance": dict(request.provenance),
                },
            )
            return RuntimeMutationTransactionResult(
                transaction=transaction,
                status="blocked",
                side_effects=tuple(execution_result.side_effects),
                execution_result=execution_result,
                verified=False,
                rollback_metadata={"rollback_required": False},
                replay_metadata=self._replay_metadata(request, transaction_id),
                audit_metadata=self._audit_metadata(request, transaction_id),
                metadata={
                    "policy": policy_result.to_metadata(),
                    "authority": authority_result.to_metadata(),
                    "capability": capability_result.to_metadata(),
                    "protection": protection_result.to_metadata(),
                    "provenance": dict(request.provenance),
                },
            )

        if not policy_result.allowed or policy_result.state == "requires_confirmation":
            transaction = self._transaction(
                transaction_id=transaction_id,
                request=request,
                policy_result=policy_result,
                operations=(),
                snapshot_id=None,
                status="blocked",
                started_at=started_at,
                finished_at=_utc_timestamp(),
                verified=False,
                rollback_required=False,
                metadata={"reason": policy_result.decision.reason},
            )
            return RuntimeMutationTransactionResult(
                transaction=transaction,
                status="blocked",
                side_effects=tuple(execution_result.side_effects),
                execution_result=execution_result,
                verified=False,
                rollback_metadata={"rollback_required": False},
                replay_metadata=self._replay_metadata(request, transaction_id),
                audit_metadata=self._audit_metadata(request, transaction_id),
                metadata={
                    "policy": policy_result.to_metadata(),
                    "authority": authority_result.to_metadata(),
                    "capability": capability_result.to_metadata(),
                    "protection": protection_result.to_metadata(),
                    "provenance": dict(request.provenance),
                },
            )

        if request.operation_type not in APPROVED_MUTATION_OPERATIONS:
            transaction = self._transaction(
                transaction_id=transaction_id,
                request=request,
                policy_result=policy_result,
                operations=(),
                snapshot_id=None,
                status="blocked",
                started_at=started_at,
                finished_at=_utc_timestamp(),
                verified=False,
                rollback_required=True,
                metadata={"reason": "mutation_operation_not_enabled_for_gateway_v1"},
            )
            return RuntimeMutationTransactionResult(
                transaction=transaction,
                status="blocked",
                side_effects=tuple(execution_result.side_effects),
                execution_result=execution_result,
                verified=False,
                rollback_metadata={"rollback_required": True},
                replay_metadata=self._replay_metadata(request, transaction_id),
                audit_metadata=self._audit_metadata(request, transaction_id),
                metadata={
                    "policy": policy_result.to_metadata(),
                    "authority": authority_result.to_metadata(),
                    "capability": capability_result.to_metadata(),
                    "protection": protection_result.to_metadata(),
                    "provenance": dict(request.provenance),
                },
            )

        snapshot_result = self.snapshotter.capture(
            snapshot_id=f"snapshot:{transaction_id}",
            source_transaction_id=transaction_id,
            target_paths=(target_path,),
            metadata={
                "request_id": request.request_id,
                "lineage": dict(request.lineage),
                "replay_id": request.replay_id,
                "audit_id": request.audit_id,
                "authority": authority_result.to_metadata(),
                "capability": capability_result.to_metadata(),
                "protection": protection_result.to_metadata(),
                "provenance": dict(request.provenance),
            },
        )
        bind_current_snapshot(
            snapshot_result.snapshot.snapshot_id,
            metadata={"source": "runtime_mutation_gateway"},
        )
        snapshot_lifecycle_id = lifecycle_id_for_artifact("snapshot", snapshot_result.snapshot.snapshot_id)
        create_current_lifecycle_record(
            lifecycle_id=snapshot_lifecycle_id,
            artifact_id=snapshot_result.snapshot.snapshot_id,
            artifact_type="snapshot",
            lineage=request.lineage,
            provenance=request.provenance,
            metadata={"source": "runtime_mutation_gateway"},
        )
        mark_current_lifecycle_active(
            snapshot_lifecycle_id,
            metadata={"source": "runtime_mutation_gateway"},
        )
        mark_current_lifecycle_verified(
            snapshot_lifecycle_id,
            metadata={"source": "runtime_mutation_gateway"},
        )
        mark_current_lifecycle_committed(
            snapshot_lifecycle_id,
            metadata={"source": "runtime_mutation_gateway"},
        )
        before_hash = snapshot_result.snapshot.records[0].content_hash

        if request.dry_run or policy_result.state == "dry_run_only":
            operation = RuntimeMutationOperation(
                operation_id=f"{transaction_id}:operation:1",
                operation_type=request.operation_type,
                target_path=str(target_path),
                before_hash=before_hash,
                after_hash=before_hash,
                patch_hash=hash_text(request.patch or ""),
                rollbackable=True,
                metadata={"dry_run": True},
            )
            transaction = self._transaction(
                transaction_id=transaction_id,
                request=request,
                policy_result=policy_result,
                operations=(operation,),
                snapshot_id=snapshot_result.snapshot.snapshot_id,
                status="verified",
                started_at=started_at,
                finished_at=_utc_timestamp(),
                verified=True,
                rollback_required=False,
                metadata={"dry_run": True},
            )
            return RuntimeMutationTransactionResult(
                transaction=transaction,
                status="verified",
                side_effects=tuple(execution_result.side_effects),
                execution_result=execution_result,
                snapshot_result=snapshot_result,
                verified=True,
                rollback_metadata=snapshot_result.snapshot.rollback_metadata,
                replay_metadata=self._replay_metadata(request, transaction_id),
                audit_metadata=self._audit_metadata(request, transaction_id),
                metadata={
                    "policy": policy_result.to_metadata(),
                    "authority": authority_result.to_metadata(),
                    "capability": capability_result.to_metadata(),
                    "protection": protection_result.to_metadata(),
                    "provenance": dict(request.provenance),
                },
            )

        content = self._content_bytes(request.content)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content)
        after_hash = hash_bytes(target_path.read_bytes())
        operation = RuntimeMutationOperation(
            operation_id=f"{transaction_id}:operation:1",
            operation_type=request.operation_type,
            target_path=str(target_path),
            before_hash=before_hash,
            after_hash=after_hash,
            patch_hash=hash_text(request.patch or ""),
            rollbackable=True,
            metadata={
                "snapshot_id": snapshot_result.snapshot.snapshot_id,
                "policy": policy_result.to_metadata(),
            },
        )
        effect = self.side_effect_registry.register(
            effect_type=request.operation_type,
            source_execution_id=transaction_id,
            verified=after_hash == hash_bytes(content),
            rollbackable=True,
            artifact_path=str(target_path),
            risk_level=policy_result.risk_level,
            rollback_metadata={
                **snapshot_result.snapshot.rollback_metadata,
                "snapshot_id": snapshot_result.snapshot.snapshot_id,
                "before_hash": before_hash,
                "after_hash": after_hash,
            },
            metadata={
                "request_id": request.request_id,
                "lineage": dict(request.lineage),
                "replay_id": request.replay_id,
                "audit_id": request.audit_id,
                "policy": policy_result.to_metadata(),
                "authority": authority_result.to_metadata(),
                "capability": capability_result.to_metadata(),
                "protection": protection_result.to_metadata(),
                "provenance": dict(request.provenance),
            },
        )
        bind_current_side_effect(
            effect.effect_id,
            metadata={"source": "runtime_mutation_gateway", "artifact_path": str(target_path)},
        )
        effect_lifecycle_id = lifecycle_id_for_artifact("side_effect", effect.effect_id)
        create_current_lifecycle_record(
            lifecycle_id=effect_lifecycle_id,
            artifact_id=effect.effect_id,
            artifact_type="side_effect",
            lineage=request.lineage,
            provenance=request.provenance,
            metadata={"source": "runtime_mutation_gateway", "artifact_path": str(target_path)},
        )
        mark_current_lifecycle_active(
            effect_lifecycle_id,
            metadata={"source": "runtime_mutation_gateway"},
        )
        mark_current_lifecycle_verified(
            effect_lifecycle_id,
            metadata={"source": "runtime_mutation_gateway"},
        )
        mark_current_lifecycle_committed(
            effect_lifecycle_id,
            metadata={"source": "runtime_mutation_gateway"},
        )
        mark_current_lifecycle_verified(
            mutation_lifecycle_id,
            metadata={"source": "runtime_mutation_gateway"},
        )
        mark_current_lifecycle_committed(
            mutation_lifecycle_id,
            metadata={"source": "runtime_mutation_gateway"},
        )
        transaction = self._transaction(
            transaction_id=transaction_id,
            request=request,
            policy_result=policy_result,
            operations=(operation,),
            snapshot_id=snapshot_result.snapshot.snapshot_id,
            status="committed",
            started_at=started_at,
            finished_at=_utc_timestamp(),
            verified=effect.verified,
            rollback_required=policy_result.state == "rollback_required",
            metadata={
                "snapshot_created": True,
                "side_effect_registered": True,
                "execution_result_id": execution_result.execution_id,
                "authority": authority_result.to_metadata(),
                "capability": capability_result.to_metadata(),
                "protection": protection_result.to_metadata(),
                "provenance": dict(request.provenance),
            },
        )
        return RuntimeMutationTransactionResult(
            transaction=transaction,
            status="committed",
            side_effects=(*tuple(execution_result.side_effects), effect),
            execution_result=execution_result,
            snapshot_result=snapshot_result,
            verified=effect.verified,
            rollback_metadata=dict(effect.rollback_metadata),
            replay_metadata=self._replay_metadata(request, transaction_id),
            audit_metadata=self._audit_metadata(request, transaction_id),
            metadata={
                "policy": policy_result.to_metadata(),
                "authority": authority_result.to_metadata(),
                "capability": capability_result.to_metadata(),
                "protection": protection_result.to_metadata(),
                "provenance": dict(request.provenance),
            },
        )

    def _record_execution_governance(
        self,
        *,
        request: RuntimeMutationRequest,
        transaction_id: str,
        policy_metadata: dict[str, Any],
    ) -> Any:
        execution_request = RuntimeExecutionRequest(
            execution_type="mutation",
            command="runtime_mutation_gateway.apply",
            working_directory=str(self.workspace_root),
            timeout=0,
            metadata={
                "operation": "file_mutation",
                "mutation_transaction_id": transaction_id,
                "mutation_request_id": request.request_id,
                "runtime_identity": {
                    "identity_id": request.identity.identity_id if request.identity else "",
                    "identity_type": request.identity.identity_type if request.identity else "",
                    "source": request.identity.source if request.identity else "",
                },
                "authority_scope_id": (
                    request.authority_scope.scope_id if request.authority_scope else ""
                ),
                "capability_scope_id": (
                    request.capability_scope.capability_id if request.capability_scope else ""
                ),
                "provenance": dict(request.provenance),
                **policy_metadata,
            },
            lineage={
                **dict(request.lineage),
                "request_id": request.request_id,
                "transaction_id": transaction_id,
                "identity_id": request.identity.identity_id if request.identity else "",
            },
            replay_id=request.replay_id or f"replay:{transaction_id}",
            repair_session_id=None,
            dry_run=True,
        )
        return self.executor.execute_request(execution_request)

    def _resolve_target_path(self, target_path: str) -> Path:
        candidate = Path(target_path)
        if not candidate.is_absolute():
            candidate = self.workspace_root / candidate
        resolved = candidate.resolve()
        if resolved != self.workspace_root and self.workspace_root not in resolved.parents:
            raise ValueError(f"mutation target outside workspace: {target_path}")
        return resolved

    def _blocked_without_execution(
        self,
        *,
        request: RuntimeMutationRequest,
        transaction_id: str,
        status_reason: str,
        started_at: str,
    ) -> RuntimeMutationTransactionResult:
        policy_result = self.mutation_policy.evaluate(
            operation_type=request.operation_type,
            target_path=request.target_path,
            lineage=request.lineage,
            metadata={"blocked": True, "block_reason": status_reason},
        )
        transaction = self._transaction(
            transaction_id=transaction_id,
            request=request,
            policy_result=policy_result,
            operations=(),
            snapshot_id=None,
            status="blocked",
            started_at=started_at,
            finished_at=_utc_timestamp(),
            verified=False,
            rollback_required=False,
            metadata={"reason": status_reason},
        )
        return RuntimeMutationTransactionResult(
            transaction=transaction,
            status="blocked",
            side_effects=(),
            verified=False,
            rollback_metadata={"rollback_required": False},
            replay_metadata=self._replay_metadata(request, transaction_id),
            audit_metadata=self._audit_metadata(request, transaction_id),
            metadata={"policy": policy_result.to_metadata()},
        )

    def _first_block_reason(
        self,
        *,
        authority_result: Any,
        capability_result: Any,
        protection_result: Any,
    ) -> str:
        if not authority_result.allowed or authority_result.state == "requires_confirmation":
            return str(authority_result.decision.reason)
        if not capability_result.allowed:
            return str(capability_result.permission.reason)
        if not protection_result.allowed:
            return str(protection_result.decision.reason)
        return "governance_blocked"

    def _transaction(
        self,
        *,
        transaction_id: str,
        request: RuntimeMutationRequest,
        policy_result: Any,
        operations: tuple[RuntimeMutationOperation, ...],
        snapshot_id: str | None,
        status: str,
        started_at: str,
        finished_at: str | None,
        verified: bool,
        rollback_required: bool,
        metadata: dict[str, Any],
    ) -> RuntimeMutationTransaction:
        return RuntimeMutationTransaction(
            transaction_id=transaction_id,
            request_id=request.request_id,
            lineage=dict(request.lineage),
            policy_result=policy_result,
            operations=operations,
            snapshot_id=snapshot_id,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            verified=verified,
            rollback_required=rollback_required,
            metadata={
                **dict(metadata),
                "lifecycle": self._lifecycle_for_status(status),
            },
        )

    def _lifecycle_for_status(self, status: str) -> tuple[str, ...]:
        base = ["created", "policy_checked"]
        if status == "blocked":
            return (*base, "blocked")
        if status == "failed":
            return (*base, "failed")
        if status == "rolled_back":
            return (*base, "snapshot_created", "applied", "rolled_back")
        if status == "verified":
            return (*base, "snapshot_created", "verified")
        if status == "committed":
            return (*base, "snapshot_created", "applied", "verified", "committed")
        return tuple(base)

    def _replay_metadata(
        self,
        request: RuntimeMutationRequest,
        transaction_id: str,
    ) -> dict[str, Any]:
        return {
            "replay_id": request.replay_id or f"replay:{transaction_id}",
            "transaction_id": transaction_id,
            "replay_observable": True,
        }

    def _audit_metadata(
        self,
        request: RuntimeMutationRequest,
        transaction_id: str,
    ) -> dict[str, Any]:
        return {
            "audit_id": request.audit_id,
            "transaction_id": transaction_id,
            "audit_compatible": True,
            "lineage": dict(request.lineage),
        }

    def _content_bytes(self, content: str | bytes | None) -> bytes:
        if isinstance(content, bytes):
            return content
        return str(content or "").encode("utf-8")


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def governed_runtime_write_bytes(
    *,
    workspace_root: str | Path,
    target_path: str | Path,
    content: bytes,
    request_id: str,
    identity: Any,
    authority_scope: Any,
    capability_scope: Any,
    lineage: dict[str, Any],
    provenance: dict[str, Any],
    operation_type: str = "file_write",
    metadata: dict[str, Any] | None = None,
) -> RuntimeMutationTransactionResult:
    return RuntimeMutationGateway(workspace_root=workspace_root).mutate(
        RuntimeMutationRequest(
            request_id=request_id,
            operation_type=operation_type,
            target_path=str(target_path),
            content=content,
            lineage=dict(lineage),
            identity=identity,
            authority_scope=authority_scope,
            capability_scope=capability_scope,
            provenance=dict(provenance),
            metadata=merge_current_transaction_metadata(metadata),
        )
    )


def governed_runtime_write_text(
    *,
    workspace_root: str | Path,
    target_path: str | Path,
    text: str,
    request_id: str,
    identity: Any,
    authority_scope: Any,
    capability_scope: Any,
    lineage: dict[str, Any],
    provenance: dict[str, Any],
    operation_type: str = "file_write",
    metadata: dict[str, Any] | None = None,
) -> RuntimeMutationTransactionResult:
    return governed_runtime_write_bytes(
        workspace_root=workspace_root,
        target_path=target_path,
        content=str(text).encode("utf-8"),
        request_id=request_id,
        identity=identity,
        authority_scope=authority_scope,
        capability_scope=capability_scope,
        lineage=lineage,
        provenance=provenance,
        operation_type=operation_type,
        metadata=merge_current_transaction_metadata(metadata),
    )
