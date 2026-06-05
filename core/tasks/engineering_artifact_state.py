from __future__ import annotations

"""Read-only state summaries for engineering artifacts."""

import copy
import time
from pathlib import Path
from typing import Any, Mapping

from core.tasks.engineering_artifact_policy import EngineeringArtifactPolicy
from core.tasks.engineering_artifact_repository import EngineeringArtifactRepository


ENGINEERING_ARTIFACT_STATE_SCHEMA = "zero.engineering_artifact_state.v1"
ENGINEERING_ARTIFACT_SUMMARY_SCHEMA = "zero.engineering_artifact_summary.v1"

ARTIFACT_STATES = {"active", "empty", "archived"}


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _artifact_lifecycle_state(artifact: Mapping[str, Any]) -> str:
    metadata = _as_mapping(artifact.get("metadata"))
    for candidate in (
        artifact.get("artifact_state"),
        artifact.get("lifecycle_state"),
        artifact.get("state"),
        artifact.get("status"),
        metadata.get("artifact_state"),
        metadata.get("lifecycle_state"),
        metadata.get("state"),
        metadata.get("status"),
    ):
        state = _clean_text(candidate).lower()
        if state in ARTIFACT_STATES:
            return state
    return "active"


class EngineeringArtifactState:
    """Evaluate read-only artifact state and aggregate metrics."""

    def __init__(
        self,
        repo_root: str | Path,
        *,
        artifact_repository: EngineeringArtifactRepository | Any | None = None,
        artifact_policy: EngineeringArtifactPolicy | Any | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.artifact_repository = artifact_repository or EngineeringArtifactRepository(self.repo_root)
        self.artifact_policy = artifact_policy or EngineeringArtifactPolicy()

    def evaluate_artifact_state(self) -> dict[str, Any]:
        artifacts = self._list_artifacts()
        policy_summary = self.artifact_policy.build_artifact_summary(artifacts)
        if not artifacts:
            state = "empty"
        elif policy_summary.get("active_count") == 0:
            state = "archived"
        else:
            state = "active"
        return {
            "schema": ENGINEERING_ARTIFACT_STATE_SCHEMA,
            "ok": True,
            "state": state,
            **self.calculate_artifact_metrics(artifacts=artifacts, policy_summary=policy_summary),
            "policy_summary": policy_summary,
            "updated_at": time.time(),
        }

    def calculate_artifact_metrics(
        self,
        *,
        artifacts: list[Mapping[str, Any]] | None = None,
        policy_summary: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        records = [copy.deepcopy(dict(item)) for item in artifacts] if artifacts is not None else self._list_artifacts()
        summary = _as_mapping(policy_summary) or self.artifact_policy.build_artifact_summary(records)
        artifact_type_summary = _as_mapping(summary.get("artifact_type_summary"))
        artifact_types = {
            artifact_type: int(_as_float(type_summary.get("total")))
            for artifact_type, type_summary in artifact_type_summary.items()
            if isinstance(type_summary, Mapping)
        }
        latest_artifact = _as_mapping(summary.get("latest_artifact"))
        return {
            "schema": ENGINEERING_ARTIFACT_STATE_SCHEMA,
            "ok": True,
            "artifact_count": len(records),
            "active_artifact_count": int(_as_float(summary.get("active_count"))),
            "archived_artifact_count": int(_as_float(summary.get("archived_count"))),
            "goal_artifact_count": len([item for item in records if _clean_text(item.get("goal_id"))]),
            "portfolio_artifact_count": len([item for item in records if _clean_text(item.get("portfolio_id"))]),
            "program_artifact_count": len([item for item in records if _clean_text(item.get("program_id"))]),
            "artifact_types": artifact_types,
            "artifact_type_summary": artifact_type_summary,
            "latest_artifact": latest_artifact,
            "updated_at": time.time(),
        }

    def summarize_artifacts(self) -> dict[str, Any]:
        artifacts = self._list_artifacts()
        state = self.evaluate_artifact_state()
        policy_summary = _as_mapping(state.get("policy_summary"))
        return {
            "schema": ENGINEERING_ARTIFACT_SUMMARY_SCHEMA,
            "ok": True,
            "state": _clean_text(state.get("state"), "empty"),
            "artifacts": artifacts,
            **self.calculate_artifact_metrics(artifacts=artifacts, policy_summary=policy_summary),
            "policy_summary": policy_summary,
            "updated_at": time.time(),
        }

    def _list_artifacts(self) -> list[dict[str, Any]]:
        ordered = getattr(self.artifact_repository, "_ordered_records", None)
        if callable(ordered):
            return [copy.deepcopy(dict(item)) for item in ordered() if isinstance(item, Mapping)]
        return []


__all__ = [
    "ARTIFACT_STATES",
    "ENGINEERING_ARTIFACT_STATE_SCHEMA",
    "ENGINEERING_ARTIFACT_SUMMARY_SCHEMA",
    "EngineeringArtifactState",
]
