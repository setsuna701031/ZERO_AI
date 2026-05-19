"""Runtime memory constitution and access decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from core.runtime.runtime_capability_scope import RuntimeCapabilityScope


MEMORY_CLASSES = frozenset(
    {
        "EPHEMERAL",
        "SESSION",
        "AUDIT",
        "REPLAY",
        "REPAIR",
        "CAPABILITY",
        "KERNEL",
    }
)


@dataclass(frozen=True)
class RuntimeMemoryRecord:
    memory_id: str
    memory_class: str
    owner_id: str
    lineage: dict[str, Any]
    sealed: bool = False
    append_only: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeMemoryPolicy:
    policy_id: str
    memory_class: str
    protected: bool = False
    append_only: bool = False
    immutable_after_seal: bool = False
    owner_bound: bool = False
    lineage_required: bool = True
    capability_scope_required: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeMemoryDecision:
    state: str
    reason: str
    memory_id: str
    memory_class: str
    owner_id: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.state in {"allowed", "append_only"}


@dataclass(frozen=True)
class RuntimeMemoryResult:
    decision: RuntimeMemoryDecision
    evaluated: bool = True

    @property
    def allowed(self) -> bool:
        return self.decision.allowed

    def to_metadata(self) -> dict[str, Any]:
        return {
            "memory_evaluated": self.evaluated,
            "memory_state": self.decision.state,
            "memory_reason": self.decision.reason,
            "memory_id": self.decision.memory_id,
            "memory_class": self.decision.memory_class,
            "memory_owner_id": self.decision.owner_id,
            "memory_metadata": dict(self.decision.metadata),
        }


class RuntimeMemoryConstitution:
    def evaluate(
        self,
        *,
        record: RuntimeMemoryRecord,
        operation: str,
        actor_id: str,
        capability_scope: RuntimeCapabilityScope | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> RuntimeMemoryResult:
        operation_text = str(operation or "").strip().lower()
        metadata_dict = dict(metadata or {})
        policy = policy_for_memory_class(record.memory_class)

        if record.memory_class not in MEMORY_CLASSES:
            return self._result("blocked", "unsupported_memory_class", record, metadata_dict)

        if policy.lineage_required and not record.lineage:
            return self._result("blocked", "memory_lineage_required", record, metadata_dict)

        if record.memory_class == "KERNEL" and not metadata_dict.get("explicit_authority"):
            return self._result("blocked", "kernel_memory_requires_explicit_authority", record, metadata_dict)

        if policy.append_only and operation_text not in {"append", "read"}:
            return self._result("blocked", "audit_memory_append_only", record, metadata_dict)

        if policy.immutable_after_seal and record.sealed and operation_text not in {"read"}:
            return self._result("blocked", "replay_memory_immutable_after_seal", record, metadata_dict)

        if record.memory_class == "REPAIR" and not record.lineage:
            return self._result("blocked", "repair_memory_lineage_required", record, metadata_dict)

        if policy.capability_scope_required and capability_scope is None:
            return self._result("blocked", "capability_memory_scope_required", record, metadata_dict)

        if policy.owner_bound and actor_id != record.owner_id and not metadata_dict.get("explicit_authority"):
            return self._result("blocked", "session_memory_owner_bound", record, metadata_dict)

        state = "append_only" if policy.append_only else "allowed"
        return self._result(state, "memory_access_allowed", record, metadata_dict)

    def _result(
        self,
        state: str,
        reason: str,
        record: RuntimeMemoryRecord,
        metadata: Mapping[str, Any],
    ) -> RuntimeMemoryResult:
        return RuntimeMemoryResult(
            decision=RuntimeMemoryDecision(
                state=state,
                reason=reason,
                memory_id=record.memory_id,
                memory_class=record.memory_class,
                owner_id=record.owner_id,
                metadata=dict(metadata),
            )
        )


def policy_for_memory_class(memory_class: str) -> RuntimeMemoryPolicy:
    memory_class = str(memory_class or "").strip().upper()
    return RuntimeMemoryPolicy(
        policy_id=f"memory_policy:{memory_class or 'UNKNOWN'}",
        memory_class=memory_class,
        protected=memory_class == "KERNEL",
        append_only=memory_class == "AUDIT",
        immutable_after_seal=memory_class == "REPLAY",
        owner_bound=memory_class == "SESSION",
        lineage_required=memory_class in {"REPLAY", "REPAIR", "SESSION", "AUDIT", "KERNEL"},
        capability_scope_required=memory_class == "CAPABILITY",
    )
