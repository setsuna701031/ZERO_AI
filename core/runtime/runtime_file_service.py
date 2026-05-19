"""Governed runtime file service.

This module is the compatibility boundary for legacy runtime file mutation.
It centralizes filesystem writes behind RuntimeMutationGateway helpers while
keeping read-only filesystem access local and explicit.

RuntimeFileService is intentionally small:
- StepExecutor may route file writes/backups/rollbacks here.
- Real mutation still goes through RuntimeMutationGateway.
- The service never calls raw write/delete APIs.
"""

from __future__ import annotations

import hashlib
import inspect
import os
import time
from pathlib import Path
from typing import Any

from core.runtime.runtime_authority import RuntimeAuthorityScope, RuntimeIdentity
from core.runtime.runtime_capability_scope import RuntimeCapabilityScope
from core.runtime.runtime_mutation_gateway import (
    governed_runtime_write_bytes,
    governed_runtime_write_text,
)
from core.runtime.runtime_state_gateway import governed_runtime_state_record
from core.runtime.runtime_state_record import RuntimeStateOwner


class RuntimeFileService:
    """Governed compatibility facade for runtime file persistence."""

    def __init__(
        self,
        *,
        workspace_root: str | Path,
        source: str = "runtime_file_service",
        identity: Any | None = None,
        authority_scope: Any | None = None,
        capability_scope: Any | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.source = str(source or "runtime_file_service")
        self.identity = identity
        self.authority_scope = authority_scope
        self.capability_scope = capability_scope

    def read_text(self, path: str | Path, *, encoding: str = "utf-8") -> str:
        return Path(path).read_text(encoding=encoding)

    def read_bytes(self, path: str | Path) -> bytes:
        return Path(path).read_bytes()

    def write_text(
        self,
        *,
        path: str | Path,
        text: str,
        operation_type: str = "file_write",
        reason: str = "runtime_file_write",
        lineage: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        target_path = Path(path)
        merged_lineage = self._lineage(
            reason=reason,
            target_path=target_path,
            lineage=lineage,
        )
        merged_provenance = self._provenance(
            reason=reason,
            target_path=target_path,
            provenance=provenance,
        )
        actor = self._identity(lineage=merged_lineage)
        authority = self._authority_scope()
        capability = self._capability_scope()
        result = governed_runtime_write_text(
            workspace_root=self.workspace_root,
            target_path=target_path,
            text=str(text),
            request_id=self._request_id(reason=reason, target_path=target_path),
            identity=actor,
            authority_scope=authority,
            capability_scope=capability,
            lineage=merged_lineage,
            provenance=merged_provenance,
            operation_type=operation_type,
            metadata={
                **dict(metadata or {}),
                "runtime_file_service": True,
                "reason": reason,
                "target_path": str(target_path),
            },
        )
        return self._require_committed(result, target_path=target_path, reason=reason)

    def write_bytes(
        self,
        *,
        path: str | Path,
        content: bytes,
        operation_type: str = "file_write",
        reason: str = "runtime_file_write_bytes",
        lineage: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        target_path = Path(path)
        merged_lineage = self._lineage(
            reason=reason,
            target_path=target_path,
            lineage=lineage,
        )
        merged_provenance = self._provenance(
            reason=reason,
            target_path=target_path,
            provenance=provenance,
        )
        actor = self._identity(lineage=merged_lineage)
        authority = self._authority_scope()
        capability = self._capability_scope()
        result = governed_runtime_write_bytes(
            workspace_root=self.workspace_root,
            target_path=target_path,
            content=bytes(content),
            request_id=self._request_id(reason=reason, target_path=target_path),
            identity=actor,
            authority_scope=authority,
            capability_scope=capability,
            lineage=merged_lineage,
            provenance=merged_provenance,
            operation_type=operation_type,
            metadata={
                **dict(metadata or {}),
                "runtime_file_service": True,
                "reason": reason,
                "target_path": str(target_path),
            },
        )
        return self._require_committed(result, target_path=target_path, reason=reason)

    def append_text(
        self,
        *,
        path: str | Path,
        text: str,
        reason: str = "runtime_file_append",
        lineage: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        target_path = Path(path)
        existing = ""
        if target_path.exists():
            existing = target_path.read_text(encoding="utf-8")
        return self.write_text(
            path=target_path,
            text=existing + str(text),
            operation_type="file_write",
            reason=reason,
            lineage=lineage,
            provenance=provenance,
            metadata={
                **dict(metadata or {}),
                "append": True,
                "existing_bytes": len(existing.encode("utf-8")),
                "appended_bytes": len(str(text).encode("utf-8")),
            },
        )

    def copy_file(
        self,
        *,
        source_path: str | Path,
        target_path: str | Path,
        operation_type: str = "generated_artifact_write",
        reason: str = "runtime_file_copy",
        lineage: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        source = Path(source_path)
        target = Path(target_path)
        content = source.read_bytes()
        return self.write_bytes(
            path=target,
            content=content,
            operation_type=operation_type,
            reason=reason,
            lineage={
                **dict(lineage or {}),
                "source_path": str(source),
                "target_path": str(target),
            },
            provenance=provenance,
            metadata={
                **dict(metadata or {}),
                "copy": True,
                "source_path": str(source),
                "source_hash": hashlib.sha256(content).hexdigest(),
            },
        )

    def create_state_record(
        self,
        *,
        state_id: str,
        state_type: str,
        data: Any,
        memory_class: str = "SESSION",
        lineage: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
        dependencies: tuple[str, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        merged_lineage = {
            **dict(lineage or {}),
            "source": self.source,
            "state_id": state_id,
            "state_type": state_type,
        }
        merged_provenance = {
            **self._base_provenance(reason="runtime_state_record"),
            **dict(provenance or {}),
        }
        actor = self._identity(lineage=merged_lineage)
        authority = self._authority_scope()
        owner = self._state_owner(identity=actor, authority_scope=authority)
        return governed_runtime_state_record(
            state_id=state_id,
            state_type=state_type,
            owner=owner,
            data=data,
            lineage=merged_lineage,
            provenance=merged_provenance,
            memory_class=memory_class,
            capability_scope=self._capability_scope(),
            dependencies=tuple(dependencies),
            metadata={
                **dict(metadata or {}),
                "runtime_file_service": True,
            },
        )

    def _require_committed(self, result: Any, *, target_path: Path, reason: str) -> dict[str, Any]:
        status = str(getattr(result, "status", "") or "").strip().lower()
        verified = bool(getattr(result, "verified", False))
        if status in {"committed", "verified"} and verified:
            return {
                "ok": True,
                "status": status,
                "verified": verified,
                "target_path": str(target_path),
                "result": result,
            }
        metadata = getattr(result, "metadata", None)
        transaction = getattr(result, "transaction", None)
        transaction_status = str(getattr(transaction, "status", "") or "").strip()
        raise RuntimeError(
            "governed runtime file mutation failed: "
            f"reason={reason}; target_path={target_path}; "
            f"status={status or transaction_status}; metadata={metadata}"
        )

    def _identity(self, *, lineage: dict[str, Any]) -> Any:
        if self.identity is not None:
            return self.identity
        return _construct(
            RuntimeIdentity,
            {
                "identity_id": f"runtime_file_service:{self.source}",
                "identity_type": "SYSTEM",
                "source": self.source,
                "display_name": "Runtime File Service",
                "lineage": dict(lineage),
                "metadata": {
                    "runtime_file_service": True,
                    "governed_compatibility": True,
                },
            },
        )

    def _authority_scope(self) -> Any:
        if self.authority_scope is not None:
            return self.authority_scope
        return _construct(
            RuntimeAuthorityScope,
            {
                "scope_id": f"runtime_file_service_scope:{self.source}",
                "allowed_execution_types": ("mutation", "command", "file_write"),
                "allowed_mutation_types": (
                    "file_write",
                    "generated_artifact_write",
                    "patch_apply",
                    "source_code_mutation",
                    "config_mutation",
                ),
                "allowed_paths": (str(self.workspace_root), str(self.workspace_root / "**"), "*"),
                "blocked_paths": (),
                "risk_ceiling": "EXTERNAL",
                "requires_confirmation": False,
                "sandbox_only": False,
                "metadata": {
                    "runtime_file_service": True,
                    "explicit_authority": True,
                    "workspace_root": str(self.workspace_root),
                },
            },
        )

    def _capability_scope(self) -> Any:
        if self.capability_scope is not None:
            return self.capability_scope
        return _construct(
            RuntimeCapabilityScope,
            {
                "capability_id": f"runtime_file_service_capability:{self.source}",
                "capability_name": "runtime_file_service",
                "accessible_paths": (str(self.workspace_root), str(self.workspace_root / "**"), "*"),
                "allowed_paths": (str(self.workspace_root), str(self.workspace_root / "**"), "*"),
                "blocked_paths": (),
                "allowed_mutation_types": (
                    "file_write",
                    "generated_artifact_write",
                    "patch_apply",
                    "source_code_mutation",
                    "config_mutation",
                ),
                "allowed_execution_types": ("mutation", "file_write", "command"),
                "risk_ceiling": "EXTERNAL",
                "sandbox_required": False,
                "sandbox_only": False,
                "replay_permissions": ("read", "write"),
                "rollback_permissions": ("read", "write"),
                "metadata": {
                    "runtime_file_service": True,
                    "workspace_root": str(self.workspace_root),
                },
            },
        )

    def _state_owner(self, *, identity: Any, authority_scope: Any) -> Any:
        return _construct(
            RuntimeStateOwner,
            {
                "owner_id": getattr(identity, "identity_id", f"runtime_file_service:{self.source}"),
                "identity": identity,
                "authority_scope": authority_scope,
                "metadata": {"runtime_file_service": True},
            },
        )

    def _lineage(
        self,
        *,
        reason: str,
        target_path: Path,
        lineage: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            **dict(lineage or {}),
            "source": self.source,
            "reason": reason,
            "target_path": str(target_path),
            "workspace_root": str(self.workspace_root),
        }

    def _provenance(
        self,
        *,
        reason: str,
        target_path: Path,
        provenance: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            **self._base_provenance(reason=reason),
            **dict(provenance or {}),
            "target_path": str(target_path),
        }

    def _base_provenance(self, *, reason: str) -> dict[str, Any]:
        return {
            "source": self.source,
            "reason": reason,
            "runtime_file_service": True,
            "timestamp_ns": time.time_ns(),
        }

    def _request_id(self, *, reason: str, target_path: Path) -> str:
        raw = f"{self.source}:{reason}:{target_path}:{time.time_ns()}".encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()[:16]
        return f"runtime_file:{digest}"


def _construct(cls: Any, values: dict[str, Any]) -> Any:
    """Construct dataclass-like runtime contracts without hard-coding drift.

    The runtime constitution modules have been evolving quickly.  This helper
    passes only fields accepted by the current constructor, while preserving all
    known governance metadata when the constructor accepts ``**kwargs``.
    """
    try:
        signature = inspect.signature(cls)
    except Exception:
        return cls(**values)

    parameters = signature.parameters
    accepts_kwargs = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )
    if accepts_kwargs:
        return cls(**values)

    accepted = {
        key: value
        for key, value in values.items()
        if key in parameters
    }
    return cls(**accepted)
