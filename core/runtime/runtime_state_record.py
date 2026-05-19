"""Typed, owned runtime state records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import json
from typing import Any, Mapping

from core.runtime.runtime_authority import RuntimeAuthorityScope, RuntimeIdentity


RUNTIME_STATE_TYPES = frozenset(
    {
        "EXECUTION_STATE",
        "MUTATION_STATE",
        "AUTHORITY_STATE",
        "REPLAY_STATE",
        "REPAIR_STATE",
        "SESSION_STATE",
        "CAPABILITY_STATE",
        "AUDIT_STATE",
    }
)

STATE_ACCESS_DECISIONS = frozenset(
    {
        "allowed",
        "blocked",
        "read_only",
        "requires_confirmation",
        "sandbox_only",
    }
)


@dataclass(frozen=True)
class RuntimeStateOwner:
    owner_id: str
    identity: RuntimeIdentity
    authority_scope: RuntimeAuthorityScope
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeStateRecord:
    state_id: str
    state_type: str
    owner_id: str
    authority_scope_id: str
    lineage: dict[str, Any]
    created_at: str
    updated_at: str
    status: str
    data_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeStateAccessDecision:
    state: str
    reason: str
    state_id: str
    state_type: str
    owner_id: str
    identity_id: str
    authority_scope_id: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.state in {"allowed", "read_only", "sandbox_only"}


@dataclass(frozen=True)
class RuntimeStateAccessResult:
    decision: RuntimeStateAccessDecision
    evaluated: bool = True

    @property
    def allowed(self) -> bool:
        return self.decision.allowed

    @property
    def state(self) -> str:
        return self.decision.state

    def to_metadata(self) -> dict[str, Any]:
        return {
            "state_access_evaluated": self.evaluated,
            "state_access_state": self.decision.state,
            "state_access_reason": self.decision.reason,
            "state_id": self.decision.state_id,
            "state_type": self.decision.state_type,
            "state_owner_id": self.decision.owner_id,
            "state_identity_id": self.decision.identity_id,
            "state_authority_scope_id": self.decision.authority_scope_id,
            "state_access_metadata": dict(self.decision.metadata),
        }


class RuntimeStateAccessEvaluator:
    def evaluate(
        self,
        *,
        record: RuntimeStateRecord,
        identity: RuntimeIdentity,
        authority_scope: RuntimeAuthorityScope,
        access_type: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> RuntimeStateAccessResult:
        access = str(access_type or "").strip().lower()
        metadata_dict = dict(metadata or {})

        if record.state_type not in RUNTIME_STATE_TYPES:
            return self._result(
                state="blocked",
                reason="unsupported_state_type",
                record=record,
                identity=identity,
                authority_scope=authority_scope,
                metadata=metadata_dict,
            )

        if access not in {"read", "write", "append", "seal", "rollback"}:
            return self._result(
                state="blocked",
                reason="unsupported_state_access_type",
                record=record,
                identity=identity,
                authority_scope=authority_scope,
                metadata=metadata_dict,
            )

        if access == "read":
            if record.owner_id == identity.identity_id or metadata_dict.get("audit_read"):
                return self._result(
                    state="allowed",
                    reason="state_read_allowed",
                    record=record,
                    identity=identity,
                    authority_scope=authority_scope,
                    metadata=metadata_dict,
                )
            return self._result(
                state="read_only",
                reason="state_read_only_cross_owner",
                record=record,
                identity=identity,
                authority_scope=authority_scope,
                metadata=metadata_dict,
            )

        if record.owner_id != identity.identity_id and not metadata_dict.get("explicit_authority"):
            return self._result(
                state="blocked",
                reason="state_owner_mismatch",
                record=record,
                identity=identity,
                authority_scope=authority_scope,
                metadata=metadata_dict,
            )

        if authority_scope.requires_confirmation:
            return self._result(
                state="requires_confirmation",
                reason="state_authority_requires_confirmation",
                record=record,
                identity=identity,
                authority_scope=authority_scope,
                metadata=metadata_dict,
            )

        if authority_scope.sandbox_only:
            return self._result(
                state="sandbox_only",
                reason="state_authority_sandbox_only",
                record=record,
                identity=identity,
                authority_scope=authority_scope,
                metadata=metadata_dict,
            )

        return self._result(
            state="allowed",
            reason="state_access_allowed",
            record=record,
            identity=identity,
            authority_scope=authority_scope,
            metadata=metadata_dict,
        )

    def _result(
        self,
        *,
        state: str,
        reason: str,
        record: RuntimeStateRecord,
        identity: RuntimeIdentity,
        authority_scope: RuntimeAuthorityScope,
        metadata: Mapping[str, Any],
    ) -> RuntimeStateAccessResult:
        return RuntimeStateAccessResult(
            decision=RuntimeStateAccessDecision(
                state=state if state in STATE_ACCESS_DECISIONS else "blocked",
                reason=reason,
                state_id=record.state_id,
                state_type=record.state_type,
                owner_id=record.owner_id,
                identity_id=identity.identity_id,
                authority_scope_id=authority_scope.scope_id,
                metadata=dict(metadata),
            )
        )


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def hash_state_data(data: Any) -> str:
    payload = json.dumps(data, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
