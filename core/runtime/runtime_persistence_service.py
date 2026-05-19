"""Governed runtime persistence service.

This module is the compatibility boundary for legacy runtime-state
persistence. It keeps TaskRuntime responsible for state transitions while
moving filesystem persistence behind governed runtime services.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from core.runtime.runtime_file_service import RuntimeFileService
from core.runtime.runtime_transaction_context import merge_current_transaction_metadata


class RuntimePersistenceService:
    """Governed facade for runtime JSON/text persistence."""

    def __init__(
        self,
        *,
        workspace_root: str | Path = "workspace",
        source: str = "runtime_persistence_service",
        file_service: RuntimeFileService | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.source = str(source or "runtime_persistence_service")
        self.file_service = file_service or RuntimeFileService(
            workspace_root=self.workspace_root,
            source=self.source,
        )

    def ensure_parent_dir(self, file_path: str | Path) -> None:
        parent = Path(file_path).parent
        if str(parent):
            parent.mkdir(parents=True, exist_ok=True)

    def exists(self, file_path: str | Path) -> bool:
        return Path(file_path).exists()

    def read_text(self, file_path: str | Path, *, default: str = "", encoding: str = "utf-8") -> str:
        try:
            return Path(file_path).read_text(encoding=encoding)
        except Exception:
            return default

    def read_json(self, file_path: str | Path, default: Any) -> Any:
        try:
            text = Path(file_path).read_text(encoding="utf-8")
            return json.loads(text)
        except Exception:
            return copy.deepcopy(default)

    def write_text(
        self,
        file_path: str | Path,
        text: str,
        *,
        reason: str = "runtime_persistence_write_text",
        lineage: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        operation_type: str = "file_write",
    ) -> dict[str, Any]:
        self.ensure_parent_dir(file_path)
        metadata = merge_current_transaction_metadata(metadata)
        lineage = merge_current_transaction_metadata({"lineage": dict(lineage or {})}).get("lineage", dict(lineage or {}))
        provenance = merge_current_transaction_metadata({"provenance": dict(provenance or {})}).get("provenance", dict(provenance or {}))
        writer = getattr(self.file_service, "write_text")
        return writer(
            path=file_path,
            text=str(text),
            operation_type=operation_type,
            reason=reason,
            lineage={
                "source": self.source,
                "persistence_target": str(file_path),
                **dict(lineage or {}),
            },
            provenance={
                "source": self.source,
                "persistence_target": str(file_path),
                **dict(provenance or {}),
            },
            metadata={
                "runtime_persistence_service": True,
                "target_path": str(file_path),
                **dict(metadata or {}),
            },
        )

    def write_json(
        self,
        file_path: str | Path,
        data: Any,
        *,
        reason: str = "runtime_persistence_write_json",
        lineage: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        text = json.dumps(data, ensure_ascii=False, indent=2)
        return self.write_text(
            file_path,
            text,
            reason=reason,
            lineage={"payload_type": "json", **dict(lineage or {})},
            provenance=provenance,
            metadata={"payload_type": "json", **dict(metadata or {})},
        )

    def append_text(
        self,
        file_path: str | Path,
        text: str,
        *,
        reason: str = "runtime_persistence_append_text",
        lineage: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.ensure_parent_dir(file_path)
        metadata = merge_current_transaction_metadata(metadata)
        lineage = merge_current_transaction_metadata({"lineage": dict(lineage or {})}).get("lineage", dict(lineage or {}))
        provenance = merge_current_transaction_metadata({"provenance": dict(provenance or {})}).get("provenance", dict(provenance or {}))
        appender = getattr(self.file_service, "append_text")
        return appender(
            path=file_path,
            text=str(text),
            reason=reason,
            lineage={
                "source": self.source,
                "persistence_target": str(file_path),
                **dict(lineage or {}),
            },
            provenance={
                "source": self.source,
                "persistence_target": str(file_path),
                **dict(provenance or {}),
            },
            metadata={
                "runtime_persistence_service": True,
                "target_path": str(file_path),
                "append": True,
                **dict(metadata or {}),
            },
        )

    def record_runtime_state(
        self,
        *,
        state_id: str,
        state_type: str,
        data: Any,
        lineage: dict[str, Any],
        provenance: dict[str, Any],
        memory_class: str = "SESSION",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = merge_current_transaction_metadata(metadata)
        lineage = merge_current_transaction_metadata({"lineage": dict(lineage)}).get("lineage", dict(lineage))
        provenance = merge_current_transaction_metadata({"provenance": dict(provenance)}).get("provenance", dict(provenance))
        return self.file_service.create_state_record(
            state_id=state_id,
            state_type=state_type,
            data=data,
            memory_class=memory_class,
            lineage={"source": self.source, **dict(lineage)},
            provenance={"source": self.source, **dict(provenance)},
            metadata={"runtime_persistence_service": True, **dict(metadata or {})},
        )
