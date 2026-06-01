from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping


ARTIFACT_COMPLETION_REPORT_SCHEMA = "artifact_completion_report.v1"


@dataclass(frozen=True)
class ArtifactCompletionReport:
    task_id: str
    status: str
    lifecycle: tuple[dict[str, Any], ...]
    plan: dict[str, Any]
    runtime_receipt: dict[str, Any]
    execution_result: dict[str, Any]
    artifacts: tuple[dict[str, Any], ...]
    schema: str = ARTIFACT_COMPLETION_REPORT_SCHEMA
    fingerprint: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.fingerprint:
            object.__setattr__(self, "fingerprint", _fingerprint(self._payload(include_fingerprint=False)))

    def to_dict(self) -> dict[str, Any]:
        return self._payload(include_fingerprint=True)

    def _payload(self, *, include_fingerprint: bool) -> dict[str, Any]:
        payload = {
            "schema": self.schema,
            "task_id": self.task_id,
            "status": self.status,
            "lifecycle": copy.deepcopy(list(self.lifecycle)),
            "plan": copy.deepcopy(self.plan),
            "runtime_receipt": copy.deepcopy(self.runtime_receipt),
            "execution_result": copy.deepcopy(self.execution_result),
            "artifacts": copy.deepcopy(list(self.artifacts)),
            "metadata": copy.deepcopy(self.metadata),
        }
        if include_fingerprint:
            payload["fingerprint"] = self.fingerprint
        return payload


def build_artifact_completion_report(
    *,
    task_id: str,
    status: str,
    lifecycle: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
    plan: Mapping[str, Any],
    runtime_receipt: Mapping[str, Any],
    execution_result: Mapping[str, Any],
    artifacts: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
    metadata: Mapping[str, Any] | None = None,
) -> ArtifactCompletionReport:
    return ArtifactCompletionReport(
        task_id=str(task_id or ""),
        status=str(status or ""),
        lifecycle=tuple(copy.deepcopy(dict(item)) for item in lifecycle if isinstance(item, Mapping)),
        plan=copy.deepcopy(dict(plan or {})),
        runtime_receipt=copy.deepcopy(dict(runtime_receipt or {})),
        execution_result=copy.deepcopy(dict(execution_result or {})),
        artifacts=tuple(copy.deepcopy(dict(item)) for item in artifacts if isinstance(item, Mapping)),
        metadata={
            **copy.deepcopy(dict(metadata or {})),
            "report_only": True,
            "no_runtime_core_capability_added": True,
        },
    )


def _fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, default=str, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = [
    "ARTIFACT_COMPLETION_REPORT_SCHEMA",
    "ArtifactCompletionReport",
    "build_artifact_completion_report",
]
