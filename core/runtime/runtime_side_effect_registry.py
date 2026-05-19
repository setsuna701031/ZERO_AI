"""Central runtime side effect registry."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Mapping


__all__ = ["RuntimeSideEffectRecord", "RuntimeSideEffectRegistry"]


@dataclass(frozen=True)
class RuntimeSideEffectRecord:
    effect_id: str
    effect_type: str
    source_execution_id: str
    timestamp: str
    verified: bool
    rollbackable: bool
    artifact_path: str | None
    risk_level: str = "LOW"
    rollback_metadata: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeSideEffectRegistry:
    """In-memory side effect registry for a single guarded execution."""

    def __init__(self) -> None:
        self._records: list[RuntimeSideEffectRecord] = []

    def register(
        self,
        *,
        effect_type: str,
        source_execution_id: str,
        verified: bool = False,
        rollbackable: bool = False,
        artifact_path: str | None = None,
        risk_level: str = "LOW",
        rollback_metadata: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> RuntimeSideEffectRecord:
        record = RuntimeSideEffectRecord(
            effect_id=f"side_effect:{source_execution_id}:{len(self._records) + 1}",
            effect_type=str(effect_type or "unknown"),
            source_execution_id=source_execution_id,
            timestamp=datetime.now(UTC).isoformat(),
            verified=bool(verified),
            rollbackable=bool(rollbackable),
            artifact_path=artifact_path,
            risk_level=str(risk_level or "LOW"),
            rollback_metadata=dict(rollback_metadata or {}),
            metadata=dict(metadata or {}),
        )
        self._records.append(record)
        return record

    def register_plan_result(
        self,
        *,
        source_execution_id: str,
        plan_result: Mapping[str, Any],
    ) -> tuple[RuntimeSideEffectRecord, ...]:
        before_count = len(self._records)
        final_round = plan_result.get("final_round_result")
        if not isinstance(final_round, Mapping):
            return ()

        for item in final_round.get("results") or []:
            if not isinstance(item, Mapping):
                continue
            self._register_step_result(
                source_execution_id=source_execution_id,
                step_result=item,
            )

        return tuple(self._records[before_count:])

    def list_records(self) -> tuple[RuntimeSideEffectRecord, ...]:
        return tuple(replace(record) for record in self._records)

    def _register_step_result(
        self,
        *,
        source_execution_id: str,
        step_result: Mapping[str, Any],
    ) -> None:
        action = str(step_result.get("action") or "").strip().lower()
        artifact_path = str(
            step_result.get("resolved_path") or step_result.get("path") or ""
        ).strip() or None
        ok = str(step_result.get("status") or "").strip().lower() in {
            "done",
            "success",
            "ok",
            "passed",
        }

        if action in {"write_file", "workspace_write", "append_file", "workspace_append"}:
            self.register(
                effect_type="file_mutation",
                source_execution_id=source_execution_id,
                verified=ok,
                rollbackable=True,
                artifact_path=artifact_path,
                risk_level="MODERATE",
                rollback_metadata={"rollback_required": True},
                metadata={"step_result": dict(step_result)},
            )
            return

        if action == "mkdir":
            self.register(
                effect_type="generated_artifact",
                source_execution_id=source_execution_id,
                verified=ok,
                rollbackable=True,
                artifact_path=artifact_path,
                risk_level="MODERATE",
                rollback_metadata={"rollback_required": True},
                metadata={"step_result": dict(step_result)},
            )
            return

        if action in {"command", "run_command"}:
            self.register(
                effect_type="command_execution",
                source_execution_id=source_execution_id,
                verified=ok,
                rollbackable=False,
                artifact_path=artifact_path,
                risk_level="MODERATE",
                rollback_metadata={"rollback_required": False},
                metadata={"step_result": dict(step_result)},
            )
            return

        if action in {"apply_patch", "apply_unified_diff"}:
            self.register(
                effect_type="patch_apply",
                source_execution_id=source_execution_id,
                verified=ok,
                rollbackable=True,
                artifact_path=artifact_path,
                risk_level="HIGH",
                rollback_metadata={"rollback_required": True},
                metadata={"step_result": dict(step_result)},
            )
