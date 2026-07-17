from __future__ import annotations

"""Persistent repository for engineering artifacts.

EngineeringArtifactRepository owns only artifact records. It does not execute
work, schedule tasks, run loops, persist context, or render screens.
"""

import copy
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


ENGINEERING_ARTIFACT_REPOSITORY_SCHEMA = "zero.engineering_artifact_repository.v1"
ENGINEERING_ARTIFACT_RECORD_SCHEMA = "zero.engineering_artifact_record.v1"


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _safe_artifact_id(value: str) -> str:
    safe = []
    for char in value:
        if char.isalnum() or char in {"-", "_", "."}:
            safe.append(char)
        elif char.isspace():
            safe.append("_")
    return "".join(safe).strip("._-").lower()[:80] or "artifact"


@dataclass(frozen=True)
class EngineeringArtifact:
    artifact_id: str
    goal_id: str = ""
    portfolio_id: str = ""
    program_id: str = ""
    artifact_type: str = ""
    artifact_name: str = ""
    artifact_path: str = ""
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EngineeringArtifact":
        artifact_id = _clean_text(value.get("artifact_id") or value.get("id"))
        artifact_name = _clean_text(value.get("artifact_name") or value.get("name"), artifact_id)
        if not artifact_id:
            raise ValueError("engineering_artifact_requires_artifact_id")
        if not artifact_name:
            raise ValueError("engineering_artifact_requires_artifact_name")
        return cls(
            artifact_id=artifact_id,
            goal_id=_clean_text(value.get("goal_id")),
            portfolio_id=_clean_text(value.get("portfolio_id")),
            program_id=_clean_text(value.get("program_id")),
            artifact_type=_clean_text(value.get("artifact_type") or value.get("type")).lower(),
            artifact_name=artifact_name,
            artifact_path=_clean_text(value.get("artifact_path") or value.get("path")),
            created_at=_as_float(value.get("created_at"), time.time()),
            metadata=_as_mapping(value.get("metadata")),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": ENGINEERING_ARTIFACT_RECORD_SCHEMA,
            "artifact_id": self.artifact_id,
            "goal_id": self.goal_id,
            "portfolio_id": self.portfolio_id,
            "program_id": self.program_id,
            "artifact_type": self.artifact_type,
            "artifact_name": self.artifact_name,
            "artifact_path": self.artifact_path,
            "created_at": self.created_at,
            "metadata": copy.deepcopy(self.metadata),
        }


class EngineeringArtifactRepository:
    """Create, list, get, and delete engineering artifact records."""

    def __init__(
        self,
        repo_root: str | Path,
        *,
        storage_path: str | Path | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.storage_path = Path(storage_path) if storage_path is not None else self.repo_root / "runtime" / "artifacts" / "artifacts.json"
        if not self.storage_path.is_absolute():
            self.storage_path = self.repo_root / self.storage_path

    @property
    def storage_dir(self) -> Path:
        return self.storage_path.parent

    def create_artifact(self, artifact: Mapping[str, Any] | EngineeringArtifact | str, **fields: Any) -> dict[str, Any]:
        records = self._read_records()
        raw = self._coerce_artifact_input(artifact, records, fields)
        record = EngineeringArtifact.from_mapping(raw).as_dict()
        artifact_id = record["artifact_id"]
        if artifact_id in records:
            raise ValueError(f"engineering_artifact_already_exists:{artifact_id}")
        records[artifact_id] = record
        self._write_records(records)
        return copy.deepcopy(record)

    def list_goal_artifacts(self, goal_id: str) -> list[dict[str, Any]]:
        target_goal_id = _clean_text(goal_id)
        return [record for record in self._ordered_records() if _clean_text(record.get("goal_id")) == target_goal_id]

    def list_portfolio_artifacts(self, portfolio_id: str) -> list[dict[str, Any]]:
        target_portfolio_id = _clean_text(portfolio_id)
        return [record for record in self._ordered_records() if _clean_text(record.get("portfolio_id")) == target_portfolio_id]

    def list_program_artifacts(self, program_id: str) -> list[dict[str, Any]]:
        target_program_id = _clean_text(program_id)
        return [record for record in self._ordered_records() if _clean_text(record.get("program_id")) == target_program_id]

    def get_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        record = self._read_records().get(_clean_text(artifact_id))
        return copy.deepcopy(record) if record else None

    def delete_artifact(self, artifact_id: str) -> dict[str, Any]:
        target_artifact_id = _clean_text(artifact_id)
        records = self._read_records()
        record = records.pop(target_artifact_id, None)
        if record is None:
            return {"ok": False, "artifact_id": target_artifact_id, "deleted": False, "reason": "artifact_not_found"}
        self._write_records(records)
        return {"ok": True, "artifact_id": target_artifact_id, "deleted": True, "artifact": copy.deepcopy(record)}

    def _coerce_artifact_input(
        self,
        artifact: Mapping[str, Any] | EngineeringArtifact | str,
        records: Mapping[str, dict[str, Any]],
        fields: Mapping[str, Any],
    ) -> dict[str, Any]:
        if isinstance(artifact, EngineeringArtifact):
            raw = artifact.as_dict()
        elif isinstance(artifact, Mapping):
            raw = copy.deepcopy(dict(artifact))
        else:
            raw = {"artifact_name": _clean_text(artifact)}
        raw.update(copy.deepcopy(dict(fields)))
        artifact_name = _clean_text(raw.get("artifact_name") or raw.get("name") or raw.get("artifact_path"), "Untitled artifact")
        artifact_id = _clean_text(raw.get("artifact_id") or raw.get("id"))
        if not artifact_id:
            artifact_id = self._new_artifact_id(artifact_name, records)
        raw.setdefault("artifact_id", artifact_id)
        raw.setdefault("artifact_name", artifact_name)
        raw.setdefault("goal_id", "")
        raw.setdefault("portfolio_id", "")
        raw.setdefault("program_id", "")
        raw.setdefault("artifact_type", "")
        raw.setdefault("artifact_path", "")
        raw.setdefault("created_at", time.time())
        raw.setdefault("metadata", {})
        return raw

    def _new_artifact_id(self, artifact_name: str, records: Mapping[str, dict[str, Any]]) -> str:
        seed = f"{artifact_name}:{time.time_ns()}"
        digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
        base = f"artifact_{_safe_artifact_id(artifact_name)[:32]}_{digest}"
        if base not in records:
            return base
        suffix = 2
        while f"{base}_{suffix}" in records:
            suffix += 1
        return f"{base}_{suffix}"

    def _ordered_records(self) -> list[dict[str, Any]]:
        return [
            copy.deepcopy(record)
            for record in sorted(
                self._read_records().values(),
                key=lambda item: (_as_float(item.get("created_at")), _clean_text(item.get("artifact_id"))),
            )
        ]

    def _read_records(self) -> dict[str, dict[str, Any]]:
        if not self.storage_path.is_file():
            return {}
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        artifacts = data if isinstance(data, list) else data.get("artifacts") if isinstance(data, Mapping) else []
        records: dict[str, dict[str, Any]] = {}
        if isinstance(artifacts, list):
            for item in artifacts:
                if not isinstance(item, Mapping):
                    continue
                try:
                    record = EngineeringArtifact.from_mapping(item).as_dict()
                except ValueError:
                    continue
                records[record["artifact_id"]] = record
        return records

    def _write_records(self, records: Mapping[str, Mapping[str, Any]]) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": ENGINEERING_ARTIFACT_REPOSITORY_SCHEMA,
            "artifacts": [
                copy.deepcopy(dict(record))
                for record in sorted(
                    records.values(),
                    key=lambda item: (_as_float(item.get("created_at")), _clean_text(item.get("artifact_id"))),
                )
            ],
            "updated_at": time.time(),
        }
        self.storage_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


__all__ = [
    "ENGINEERING_ARTIFACT_RECORD_SCHEMA",
    "ENGINEERING_ARTIFACT_REPOSITORY_SCHEMA",
    "EngineeringArtifact",
    "EngineeringArtifactRepository",
]
