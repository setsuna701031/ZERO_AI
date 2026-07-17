from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.runtime.runtime_capability_scope import (
    RuntimeCapabilityScope as GovernedRuntimeCapabilityScope,
)
from core.runtime.runtime_file_service import RuntimeFileService
from core.runtime.runtime_persistence_service import RuntimePersistenceService


RUNTIME_STATUS_ACTIVE = "active"
RUNTIME_STATUS_QUARANTINED = "quarantined"
RUNTIME_STATUS_ISOLATED = "isolated"
RUNTIME_STATUS_FROZEN = "frozen"

CAPABILITY_READ = "read"
CAPABILITY_WRITE = "write"
CAPABILITY_EXECUTE = "execute"
CAPABILITY_MUTATE = "mutate"
CAPABILITY_SUPERVISE = "supervise"

AUTHORITY_ALLOW = "allow"
AUTHORITY_DENY = "deny"
AUTHORITY_ESCALATE = "escalate"

ISOLATION_SCOPE_SESSION = "session"
ISOLATION_SCOPE_NAMESPACE = "namespace"
ISOLATION_SCOPE_RUNTIME = "runtime"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_ownership_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _copy_dict(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _copy_list(value: Any) -> list[Any]:
    return copy.deepcopy(value) if isinstance(value, list) else []


@dataclass(frozen=True)
class RuntimeCapabilityScope:
    scope_id: str
    namespace: str
    owner_id: str
    capabilities: list[str] = field(default_factory=list)
    allowed_paths: list[str] = field(default_factory=list)
    denied_paths: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope_id": self.scope_id,
            "namespace": self.namespace,
            "owner_id": self.owner_id,
            "capabilities": copy.deepcopy(self.capabilities),
            "allowed_paths": copy.deepcopy(self.allowed_paths),
            "denied_paths": copy.deepcopy(self.denied_paths),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeCapabilityScope":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            scope_id=str(data.get("scope_id") or ""),
            namespace=str(data.get("namespace") or ""),
            owner_id=str(data.get("owner_id") or ""),
            capabilities=_copy_list(data.get("capabilities")),
            allowed_paths=_copy_list(data.get("allowed_paths")),
            denied_paths=_copy_list(data.get("denied_paths")),
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
        )


@dataclass(frozen=True)
class RuntimeIsolationBoundary:
    boundary_id: str
    runtime_id: str
    namespace: str
    owner_id: str
    isolation_scope: str = ISOLATION_SCOPE_RUNTIME
    status: str = RUNTIME_STATUS_ACTIVE
    quarantine_reason: str = ""
    restricted_capabilities: list[str] = field(default_factory=list)
    blocked_sessions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "boundary_id": self.boundary_id,
            "runtime_id": self.runtime_id,
            "namespace": self.namespace,
            "owner_id": self.owner_id,
            "isolation_scope": self.isolation_scope,
            "status": self.status,
            "quarantine_reason": self.quarantine_reason,
            "restricted_capabilities": copy.deepcopy(self.restricted_capabilities),
            "blocked_sessions": copy.deepcopy(self.blocked_sessions),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeIsolationBoundary":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            boundary_id=str(data.get("boundary_id") or ""),
            runtime_id=str(data.get("runtime_id") or ""),
            namespace=str(data.get("namespace") or ""),
            owner_id=str(data.get("owner_id") or ""),
            isolation_scope=str(data.get("isolation_scope") or ISOLATION_SCOPE_RUNTIME),
            status=str(data.get("status") or RUNTIME_STATUS_ACTIVE),
            quarantine_reason=str(data.get("quarantine_reason") or ""),
            restricted_capabilities=_copy_list(data.get("restricted_capabilities")),
            blocked_sessions=_copy_list(data.get("blocked_sessions")),
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
            updated_at=str(data.get("updated_at") or utc_timestamp()),
        )


@dataclass(frozen=True)
class RuntimeAuthorityDecision:
    decision_id: str
    runtime_id: str
    namespace: str
    owner_id: str
    capability: str
    target: str
    decision: str
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "runtime_id": self.runtime_id,
            "namespace": self.namespace,
            "owner_id": self.owner_id,
            "capability": self.capability,
            "target": self.target,
            "decision": self.decision,
            "reason": self.reason,
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeAuthorityDecision":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            decision_id=str(data.get("decision_id") or ""),
            runtime_id=str(data.get("runtime_id") or ""),
            namespace=str(data.get("namespace") or ""),
            owner_id=str(data.get("owner_id") or ""),
            capability=str(data.get("capability") or ""),
            target=str(data.get("target") or ""),
            decision=str(data.get("decision") or ""),
            reason=str(data.get("reason") or ""),
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
        )


@dataclass(frozen=True)
class RuntimeOwnershipRecord:
    runtime_id: str
    namespace: str
    owner_id: str
    session_ids: list[str] = field(default_factory=list)
    status: str = RUNTIME_STATUS_ACTIVE
    capability_scope: dict[str, Any] = field(default_factory=dict)
    isolation_boundary: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_id": self.runtime_id,
            "namespace": self.namespace,
            "owner_id": self.owner_id,
            "session_ids": copy.deepcopy(self.session_ids),
            "status": self.status,
            "capability_scope": copy.deepcopy(self.capability_scope),
            "isolation_boundary": copy.deepcopy(self.isolation_boundary),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeOwnershipRecord":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            runtime_id=str(data.get("runtime_id") or ""),
            namespace=str(data.get("namespace") or ""),
            owner_id=str(data.get("owner_id") or ""),
            session_ids=_copy_list(data.get("session_ids")),
            status=str(data.get("status") or RUNTIME_STATUS_ACTIVE),
            capability_scope=_copy_dict(data.get("capability_scope")),
            isolation_boundary=_copy_dict(data.get("isolation_boundary")),
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
            updated_at=str(data.get("updated_at") or utc_timestamp()),
        )


class RuntimeOwnershipIsolationFabricRejected(RuntimeError):
    pass


class RuntimeOwnershipIsolationFabric:
    """
    Runtime ownership + isolation governance layer.

    Responsibilities:
      - namespace ownership
      - runtime capability scope
      - execution isolation boundary
      - quarantine enforcement
      - cross-runtime authority control
      - supervisor isolation escalation

    Non-responsibilities:
      - no scheduler execution
      - no transaction execution
      - no recovery orchestration
    """

    def __init__(
        self,
        *,
        storage_path: str | Path | None = None,
        supervisor: Any = None,
        journal: Any = None,
        audit: Any = None,
    ) -> None:
        self.storage_path = Path(storage_path) if storage_path is not None else None
        self.supervisor = supervisor
        self.journal = journal
        self.audit = audit
        workspace_root = self.storage_path.parent if self.storage_path is not None else Path("workspace")
        self.persistence_service = RuntimePersistenceService(
            workspace_root=workspace_root,
            source="runtime_ownership_isolation_fabric",
            file_service=RuntimeFileService(
                workspace_root=workspace_root,
                source="runtime_ownership_isolation_fabric",
                capability_scope=GovernedRuntimeCapabilityScope(
                    capability_id="capability:runtime_ownership_isolation_fabric:persistence",
                    allowed_mutation_types=("file_write", "generated_artifact_write"),
                    allowed_execution_types=("mutation", "file_write", "command"),
                    risk_ceiling="EXTERNAL",
                    replay_allowed=True,
                    rollback_allowed=True,
                    metadata={
                        "runtime_ownership_isolation_fabric": True,
                        "governed_persistence_capability": True,
                    },
                ),
            ),
        )
        self._ownerships: dict[str, RuntimeOwnershipRecord] = {}
        self._decisions: list[RuntimeAuthorityDecision] = []
        if self.storage_path is not None:
            self.load()

    @classmethod
    def with_workspace(
        cls,
        workspace_root: str | Path = "workspace",
        **kwargs: Any,
    ) -> "RuntimeOwnershipIsolationFabric":
        root = Path(workspace_root)
        fabric_dir = root / "runtime_ownership_isolation_fabric"
        fabric_dir.mkdir(parents=True, exist_ok=True)
        return cls(storage_path=fabric_dir / "runtime_ownership_isolation_fabric.json", **kwargs)

    def register_runtime(
        self,
        *,
        runtime_id: str,
        namespace: str,
        owner_id: str,
        session_ids: list[str] | None = None,
        capabilities: list[str] | None = None,
        allowed_paths: list[str] | None = None,
        denied_paths: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeOwnershipRecord:
        runtime_id = self._validate_text("runtime_id", runtime_id)
        namespace = self._validate_text("namespace", namespace)
        owner_id = self._validate_text("owner_id", owner_id)

        if runtime_id in self._ownerships:
            raise RuntimeOwnershipIsolationFabricRejected(f"runtime already exists: {runtime_id!r}")

        scope = RuntimeCapabilityScope(
            scope_id="runtime-scope-" + stable_ownership_fingerprint(
                {"runtime_id": runtime_id, "namespace": namespace}
            )[:16],
            namespace=namespace,
            owner_id=owner_id,
            capabilities=_copy_list(capabilities or []),
            allowed_paths=_copy_list(allowed_paths or []),
            denied_paths=_copy_list(denied_paths or []),
            metadata=_copy_dict(metadata),
        )

        boundary = RuntimeIsolationBoundary(
            boundary_id="runtime-boundary-" + stable_ownership_fingerprint(
                {"runtime_id": runtime_id, "owner_id": owner_id}
            )[:16],
            runtime_id=runtime_id,
            namespace=namespace,
            owner_id=owner_id,
            status=RUNTIME_STATUS_ACTIVE,
        )

        record = RuntimeOwnershipRecord(
            runtime_id=runtime_id,
            namespace=namespace,
            owner_id=owner_id,
            session_ids=_copy_list(session_ids or []),
            status=RUNTIME_STATUS_ACTIVE,
            capability_scope=scope.to_dict(),
            isolation_boundary=boundary.to_dict(),
            metadata=_copy_dict(metadata),
        )

        self._ownerships[runtime_id] = record
        self.save()
        return copy.deepcopy(record)

    def authorize(
        self,
        *,
        runtime_id: str,
        capability: str,
        target: str,
        owner_id: str,
    ) -> RuntimeAuthorityDecision:
        record = self.get_runtime(runtime_id)

        if record.status in {RUNTIME_STATUS_QUARANTINED, RUNTIME_STATUS_ISOLATED, RUNTIME_STATUS_FROZEN}:
            return self._decision(
                runtime_id=runtime_id,
                namespace=record.namespace,
                owner_id=owner_id,
                capability=capability,
                target=target,
                decision=AUTHORITY_DENY,
                reason=f"runtime status blocks capability: {record.status}",
            )

        scope = record.capability_scope
        capabilities = set(scope.get("capabilities") or [])

        if capability not in capabilities:
            return self._decision(
                runtime_id=runtime_id,
                namespace=record.namespace,
                owner_id=owner_id,
                capability=capability,
                target=target,
                decision=AUTHORITY_DENY,
                reason="capability not granted",
            )

        denied = scope.get("denied_paths") or []
        if any(str(target).startswith(str(item)) for item in denied):
            return self._decision(
                runtime_id=runtime_id,
                namespace=record.namespace,
                owner_id=owner_id,
                capability=capability,
                target=target,
                decision=AUTHORITY_DENY,
                reason="target path denied",
            )

        allowed = scope.get("allowed_paths") or []
        if allowed and not any(str(target).startswith(str(item)) for item in allowed):
            return self._decision(
                runtime_id=runtime_id,
                namespace=record.namespace,
                owner_id=owner_id,
                capability=capability,
                target=target,
                decision=AUTHORITY_ESCALATE,
                reason="target outside allowed capability scope",
            )

        return self._decision(
            runtime_id=runtime_id,
            namespace=record.namespace,
            owner_id=owner_id,
            capability=capability,
            target=target,
            decision=AUTHORITY_ALLOW,
            reason="capability granted",
        )

    def quarantine_runtime(
        self,
        runtime_id: str,
        *,
        reason: str,
        restricted_capabilities: list[str] | None = None,
        blocked_sessions: list[str] | None = None,
    ) -> RuntimeOwnershipRecord:
        record = self.get_runtime(runtime_id)

        boundary = RuntimeIsolationBoundary.from_dict(record.isolation_boundary)
        boundary = RuntimeIsolationBoundary.from_dict(
            {
                **boundary.to_dict(),
                "status": RUNTIME_STATUS_QUARANTINED,
                "quarantine_reason": reason,
                "restricted_capabilities": _copy_list(restricted_capabilities or []),
                "blocked_sessions": _copy_list(blocked_sessions or []),
                "updated_at": utc_timestamp(),
            }
        )

        updated = RuntimeOwnershipRecord(
            runtime_id=record.runtime_id,
            namespace=record.namespace,
            owner_id=record.owner_id,
            session_ids=record.session_ids,
            status=RUNTIME_STATUS_QUARANTINED,
            capability_scope=_copy_dict(record.capability_scope),
            isolation_boundary=boundary.to_dict(),
            metadata=_copy_dict(record.metadata),
            created_at=record.created_at,
            updated_at=utc_timestamp(),
        )

        self._ownerships[runtime_id] = updated
        self.save()
        return copy.deepcopy(updated)

    def isolate_runtime(
        self,
        runtime_id: str,
        *,
        reason: str,
    ) -> RuntimeOwnershipRecord:
        record = self.get_runtime(runtime_id)

        boundary = RuntimeIsolationBoundary.from_dict(record.isolation_boundary)
        boundary = RuntimeIsolationBoundary.from_dict(
            {
                **boundary.to_dict(),
                "status": RUNTIME_STATUS_ISOLATED,
                "quarantine_reason": reason,
                "updated_at": utc_timestamp(),
            }
        )

        updated = RuntimeOwnershipRecord(
            runtime_id=record.runtime_id,
            namespace=record.namespace,
            owner_id=record.owner_id,
            session_ids=record.session_ids,
            status=RUNTIME_STATUS_ISOLATED,
            capability_scope=_copy_dict(record.capability_scope),
            isolation_boundary=boundary.to_dict(),
            metadata=_copy_dict(record.metadata),
            created_at=record.created_at,
            updated_at=utc_timestamp(),
        )

        self._ownerships[runtime_id] = updated
        self.save()
        return copy.deepcopy(updated)

    def freeze_runtime(
        self,
        runtime_id: str,
        *,
        reason: str,
    ) -> RuntimeOwnershipRecord:
        record = self.get_runtime(runtime_id)

        boundary = RuntimeIsolationBoundary.from_dict(record.isolation_boundary)
        boundary = RuntimeIsolationBoundary.from_dict(
            {
                **boundary.to_dict(),
                "status": RUNTIME_STATUS_FROZEN,
                "quarantine_reason": reason,
                "updated_at": utc_timestamp(),
            }
        )

        updated = RuntimeOwnershipRecord(
            runtime_id=record.runtime_id,
            namespace=record.namespace,
            owner_id=record.owner_id,
            session_ids=record.session_ids,
            status=RUNTIME_STATUS_FROZEN,
            capability_scope=_copy_dict(record.capability_scope),
            isolation_boundary=boundary.to_dict(),
            metadata=_copy_dict(record.metadata),
            created_at=record.created_at,
            updated_at=utc_timestamp(),
        )

        self._ownerships[runtime_id] = updated
        self.save()
        return copy.deepcopy(updated)

    def get_runtime(self, runtime_id: str) -> RuntimeOwnershipRecord:
        runtime_id = self._validate_text("runtime_id", runtime_id)
        record = self._ownerships.get(runtime_id)
        if record is None:
            raise RuntimeOwnershipIsolationFabricRejected(f"runtime does not exist: {runtime_id!r}")
        return copy.deepcopy(record)

    def list_runtimes(self) -> list[RuntimeOwnershipRecord]:
        return [copy.deepcopy(item) for item in self._ownerships.values()]

    def list_decisions(self) -> list[RuntimeAuthorityDecision]:
        return [copy.deepcopy(item) for item in self._decisions]

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_phase": "runtime_ownership_isolation_fabric",
            "ownerships": [item.to_dict() for item in self._ownerships.values()],
            "decisions": [item.to_dict() for item in self._decisions[-500:]],
        }

    def load(self) -> None:
        if self.storage_path is None:
            return
        if not self.storage_path.exists():
            self._ownerships = {}
            self._decisions = []
            return

        payload = self.persistence_service.read_json(
            self.storage_path,
            default={},
        )
        self._ownerships = {}
        self._decisions = []

        if not isinstance(payload, dict):
            return

        for item in payload.get("ownerships") or []:
            if isinstance(item, dict):
                record = RuntimeOwnershipRecord.from_dict(item)
                if record.runtime_id:
                    self._ownerships[record.runtime_id] = record

        for item in payload.get("decisions") or []:
            if isinstance(item, dict):
                decision = RuntimeAuthorityDecision.from_dict(item)
                if decision.decision_id:
                    self._decisions.append(decision)

    def save(self) -> None:
        if self.storage_path is None:
            return
        self.persistence_service.write_json(
            self.storage_path,
            self.to_dict(),
            reason="runtime_ownership_isolation_fabric_save",
            metadata={"runtime_ownership_isolation_fabric": True},
        )

    def _decision(
        self,
        *,
        runtime_id: str,
        namespace: str,
        owner_id: str,
        capability: str,
        target: str,
        decision: str,
        reason: str,
    ) -> RuntimeAuthorityDecision:
        item = RuntimeAuthorityDecision(
            decision_id="runtime-decision-" + stable_ownership_fingerprint(
                {
                    "runtime_id": runtime_id,
                    "capability": capability,
                    "target": target,
                    "decision": decision,
                    "sequence": len(self._decisions) + 1,
                }
            )[:16],
            runtime_id=runtime_id,
            namespace=namespace,
            owner_id=owner_id,
            capability=capability,
            target=target,
            decision=decision,
            reason=reason,
        )
        self._decisions.append(item)
        self.save()
        return copy.deepcopy(item)

    def _validate_text(self, field_name: str, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise RuntimeOwnershipIsolationFabricRejected(f"{field_name}_required")
        return text
