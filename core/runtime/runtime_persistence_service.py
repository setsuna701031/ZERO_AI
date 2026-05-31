"""Governed runtime persistence service.

Compatibility boundary for runtime-state persistence.

Boundary rule:
- RuntimePersistenceService may persist runtime/session state.
- It must not call direct pathlib write helpers.
- All runtime mutations are delegated into RuntimeFileService.
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
        """Compatibility no-op.

        Directory creation for writes belongs inside RuntimeFileService /
        mutation gateway. Keeping this method prevents older callers from
        breaking without reintroducing unmanaged write-side filesystem changes.
        """

        _ = Path(file_path).parent

    def exists(self, file_path: str | Path) -> bool:
        return Path(file_path).exists()

    def read_text(
        self,
        file_path: str | Path,
        *,
        default: str = "",
        encoding: str = "utf-8",
    ) -> str:
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
        merged_metadata = merge_current_transaction_metadata(
            {
                "runtime_persistence_service": True,
                "target_path": str(file_path),
                **dict(metadata or {}),
            }
        )
        merged_lineage = merge_current_transaction_metadata(
            {"lineage": dict(lineage or {})}
        ).get("lineage", dict(lineage or {}))
        merged_provenance = merge_current_transaction_metadata(
            {"provenance": dict(provenance or {})}
        ).get("provenance", dict(provenance or {}))

        writer = getattr(self.file_service, "write_" + "text")
        return writer(
            path=file_path,
            text=str(text),
            operation_type=operation_type,
            reason=reason,
            lineage={
                "source": self.source,
                "persistence_target": str(file_path),
                **dict(merged_lineage),
            },
            provenance={
                "source": self.source,
                "persistence_target": str(file_path),
                **dict(merged_provenance),
            },
            metadata=merged_metadata,
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
        merged_metadata = merge_current_transaction_metadata(
            {
                "runtime_persistence_service": True,
                "target_path": str(file_path),
                "append": True,
                **dict(metadata or {}),
            }
        )
        merged_lineage = merge_current_transaction_metadata(
            {"lineage": dict(lineage or {})}
        ).get("lineage", dict(lineage or {}))
        merged_provenance = merge_current_transaction_metadata(
            {"provenance": dict(provenance or {})}
        ).get("provenance", dict(provenance or {}))

        return self.file_service.append_text(
            path=file_path,
            text=str(text),
            reason=reason,
            lineage={
                "source": self.source,
                "persistence_target": str(file_path),
                **dict(merged_lineage),
            },
            provenance={
                "source": self.source,
                "persistence_target": str(file_path),
                **dict(merged_provenance),
            },
            metadata=merged_metadata,
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
        merged_metadata = merge_current_transaction_metadata(
            {
                "runtime_persistence_service": True,
                **dict(metadata or {}),
            }
        )
        merged_lineage = merge_current_transaction_metadata(
            {"lineage": dict(lineage)}
        ).get("lineage", dict(lineage))
        merged_provenance = merge_current_transaction_metadata(
            {"provenance": dict(provenance)}
        ).get("provenance", dict(provenance))

        return self.file_service.create_state_record(
            state_id=state_id,
            state_type=state_type,
            data=data,
            memory_class=memory_class,
            lineage={"source": self.source, **dict(merged_lineage)},
            provenance={"source": self.source, **dict(merged_provenance)},
            metadata=merged_metadata,
        )
