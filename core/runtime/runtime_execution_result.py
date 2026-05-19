"""Canonical runtime execution result contract."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any


__all__ = ["RuntimeExecutionResult"]


@dataclass(frozen=True)
class RuntimeExecutionResult(Mapping[str, Any]):
    execution_id: str
    execution_start_id: str
    execution_type: str
    status: str
    started_at: str
    finished_at: str
    stdout: str
    stderr: str
    return_code: int
    side_effects: tuple[Any, ...]
    artifacts: tuple[Any, ...]
    verified: bool
    blocked: bool
    rollback_required: bool
    lineage: dict[str, Any]
    replay_id: str | None
    repair_session_id: str | None
    risk_level: str = "LOW"
    risk_metadata: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_legacy_plan_result(
        cls,
        *,
        execution_id: str,
        execution_start_id: str,
        execution_type: str,
        started_at: str,
        finished_at: str,
        legacy_result: Mapping[str, Any],
        side_effects: tuple[Any, ...] = (),
        artifacts: tuple[Any, ...] = (),
        lineage: Mapping[str, Any] | None = None,
        replay_id: str | None = None,
        repair_session_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        risk_level: str = "LOW",
        risk_metadata: Mapping[str, Any] | None = None,
    ) -> "RuntimeExecutionResult":
        success = bool(legacy_result.get("success", False))
        final_verify_result = legacy_result.get("final_verify_result")
        verified = bool(
            isinstance(final_verify_result, Mapping)
            and final_verify_result.get("passed", success)
        )
        blocked = bool(legacy_result.get("blocked", False))
        rollback_required = bool(legacy_result.get("rollback_required", False))
        stdout = str(legacy_result.get("stdout") or legacy_result.get("output") or "")
        stderr = str(legacy_result.get("stderr") or "")
        return_code = 0 if success and not blocked else 1
        result_metadata = dict(metadata or {})
        result_metadata["legacy_result"] = dict(legacy_result)

        return cls(
            execution_id=execution_id,
            execution_start_id=execution_start_id,
            execution_type=execution_type,
            status="succeeded" if success and not blocked else "failed",
            started_at=started_at,
            finished_at=finished_at,
            stdout=stdout,
            stderr=stderr,
            return_code=return_code,
            side_effects=tuple(side_effects),
            artifacts=tuple(artifacts),
            verified=verified,
            blocked=blocked,
            rollback_required=rollback_required,
            lineage=dict(lineage or {}),
            replay_id=replay_id,
            repair_session_id=repair_session_id,
            risk_level=str(risk_level or "LOW"),
            risk_metadata=dict(risk_metadata or {}),
            metadata=result_metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "execution_start_id": self.execution_start_id,
            "execution_type": self.execution_type,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "return_code": self.return_code,
            "side_effects": list(self.side_effects),
            "artifacts": list(self.artifacts),
            "verified": self.verified,
            "blocked": self.blocked,
            "rollback_required": self.rollback_required,
            "lineage": dict(self.lineage),
            "replay_id": self.replay_id,
            "repair_session_id": self.repair_session_id,
            "risk_level": self.risk_level,
            "risk_metadata": dict(self.risk_metadata),
            "metadata": dict(self.metadata),
        }

    def legacy_result(self) -> dict[str, Any]:
        legacy = self.metadata.get("legacy_result")
        if isinstance(legacy, Mapping):
            return dict(legacy)
        return {}

    def __getitem__(self, key: str) -> Any:
        canonical = self.to_dict()
        if key in canonical:
            return canonical[key]
        legacy = self.legacy_result()
        if key in legacy:
            return legacy[key]
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        yielded = set()
        for key in self.to_dict():
            yielded.add(key)
            yield key
        for key in self.legacy_result():
            if key not in yielded:
                yield key

    def __len__(self) -> int:
        return len(list(iter(self)))

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default
