"""Immutable runtime mutation transaction contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.runtime.runtime_authority import RuntimeAuthorityScope, RuntimeIdentity
from core.runtime.runtime_capability_scope import RuntimeCapabilityScope
from core.runtime.runtime_mutation_policy import MutationPolicyResult


MUTATION_TRANSACTION_STATUSES = frozenset(
    {
        "created",
        "policy_checked",
        "snapshot_created",
        "applied",
        "verified",
        "committed",
        "rolled_back",
        "blocked",
        "failed",
    }
)


@dataclass(frozen=True)
class RuntimeMutationRequest:
    request_id: str
    operation_type: str
    target_path: str
    content: str | bytes | None = None
    patch: str | None = None
    lineage: dict[str, Any] = field(default_factory=dict)
    replay_id: str | None = None
    audit_id: str | None = None
    dry_run: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    identity: RuntimeIdentity | None = None
    authority_scope: RuntimeAuthorityScope | None = None
    capability_scope: RuntimeCapabilityScope | None = None
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeMutationOperation:
    operation_id: str
    operation_type: str
    target_path: str
    before_hash: str | None
    after_hash: str | None
    patch_hash: str | None
    rollbackable: bool
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeMutationTransaction:
    transaction_id: str
    request_id: str
    lineage: dict[str, Any]
    policy_result: MutationPolicyResult
    operations: tuple[RuntimeMutationOperation, ...]
    snapshot_id: str | None
    status: str
    started_at: str
    finished_at: str | None
    verified: bool
    rollback_required: bool
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeMutationTransactionResult:
    transaction: RuntimeMutationTransaction
    status: str
    side_effects: tuple[Any, ...] = ()
    execution_result: Any = None
    snapshot_result: Any = None
    verified: bool = False
    rollback_metadata: dict[str, Any] = field(default_factory=dict)
    replay_metadata: dict[str, Any] = field(default_factory=dict)
    audit_metadata: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def blocked(self) -> bool:
        return self.status == "blocked"
