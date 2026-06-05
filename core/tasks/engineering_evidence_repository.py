from __future__ import annotations

"""Persistent repository for engineering evidence records.

EngineeringEvidenceRepository owns only evidence records. It does not execute
work, schedule tasks, run loops, persist context, or render screens.
"""

import copy
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


ENGINEERING_EVIDENCE_REPOSITORY_SCHEMA = "zero.engineering_evidence_repository.v1"
ENGINEERING_EVIDENCE_RECORD_SCHEMA = "zero.engineering_evidence_record.v1"


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


def _safe_evidence_id(value: str) -> str:
    safe = []
    for char in value:
        if char.isalnum() or char in {"-", "_", "."}:
            safe.append(char)
        elif char.isspace():
            safe.append("_")
    return "".join(safe).strip("._-").lower()[:80] or "evidence"


@dataclass(frozen=True)
class EngineeringEvidence:
    evidence_id: str
    artifact_id: str = ""
    goal_id: str = ""
    portfolio_id: str = ""
    program_id: str = ""
    evidence_type: str = ""
    evidence_name: str = ""
    evidence_path: str = ""
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EngineeringEvidence":
        evidence_id = _clean_text(value.get("evidence_id") or value.get("id"))
        evidence_name = _clean_text(value.get("evidence_name") or value.get("name"), evidence_id)
        if not evidence_id:
            raise ValueError("engineering_evidence_requires_evidence_id")
        if not evidence_name:
            raise ValueError("engineering_evidence_requires_evidence_name")
        return cls(
            evidence_id=evidence_id,
            artifact_id=_clean_text(value.get("artifact_id")),
            goal_id=_clean_text(value.get("goal_id")),
            portfolio_id=_clean_text(value.get("portfolio_id")),
            program_id=_clean_text(value.get("program_id")),
            evidence_type=_clean_text(value.get("evidence_type") or value.get("type")).lower(),
            evidence_name=evidence_name,
            evidence_path=_clean_text(value.get("evidence_path") or value.get("path")),
            created_at=_as_float(value.get("created_at"), time.time()),
            metadata=_as_mapping(value.get("metadata")),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": ENGINEERING_EVIDENCE_RECORD_SCHEMA,
            "evidence_id": self.evidence_id,
            "artifact_id": self.artifact_id,
            "goal_id": self.goal_id,
            "portfolio_id": self.portfolio_id,
            "program_id": self.program_id,
            "evidence_type": self.evidence_type,
            "evidence_name": self.evidence_name,
            "evidence_path": self.evidence_path,
            "created_at": self.created_at,
            "metadata": copy.deepcopy(self.metadata),
        }


class EngineeringEvidenceRepository:
    """Create, list, get, and delete engineering evidence records."""

    def __init__(
        self,
        repo_root: str | Path,
        *,
        storage_path: str | Path | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.storage_path = Path(storage_path) if storage_path is not None else self.repo_root / "runtime" / "evidence" / "evidence.json"
        if not self.storage_path.is_absolute():
            self.storage_path = self.repo_root / self.storage_path

    @property
    def storage_dir(self) -> Path:
        return self.storage_path.parent

    def create_evidence(self, evidence: Mapping[str, Any] | EngineeringEvidence | str, **fields: Any) -> dict[str, Any]:
        records = self._read_records()
        raw = self._coerce_evidence_input(evidence, records, fields)
        record = EngineeringEvidence.from_mapping(raw).as_dict()
        evidence_id = record["evidence_id"]
        if evidence_id in records:
            raise ValueError(f"engineering_evidence_already_exists:{evidence_id}")
        records[evidence_id] = record
        self._write_records(records)
        return copy.deepcopy(record)

    def list_evidence(self) -> list[dict[str, Any]]:
        return self._ordered_records()

    def list_artifact_evidence(self, artifact_id: str) -> list[dict[str, Any]]:
        target_artifact_id = _clean_text(artifact_id)
        return [record for record in self._ordered_records() if _clean_text(record.get("artifact_id")) == target_artifact_id]

    def list_goal_evidence(self, goal_id: str) -> list[dict[str, Any]]:
        target_goal_id = _clean_text(goal_id)
        return [record for record in self._ordered_records() if _clean_text(record.get("goal_id")) == target_goal_id]

    def list_portfolio_evidence(self, portfolio_id: str) -> list[dict[str, Any]]:
        target_portfolio_id = _clean_text(portfolio_id)
        return [record for record in self._ordered_records() if _clean_text(record.get("portfolio_id")) == target_portfolio_id]

    def list_program_evidence(self, program_id: str) -> list[dict[str, Any]]:
        target_program_id = _clean_text(program_id)
        return [record for record in self._ordered_records() if _clean_text(record.get("program_id")) == target_program_id]

    def get_evidence(self, evidence_id: str) -> dict[str, Any] | None:
        record = self._read_records().get(_clean_text(evidence_id))
        return copy.deepcopy(record) if record else None

    def delete_evidence(self, evidence_id: str) -> dict[str, Any]:
        target_evidence_id = _clean_text(evidence_id)
        records = self._read_records()
        record = records.pop(target_evidence_id, None)
        if record is None:
            return {"ok": False, "evidence_id": target_evidence_id, "deleted": False, "reason": "evidence_not_found"}
        self._write_records(records)
        return {"ok": True, "evidence_id": target_evidence_id, "deleted": True, "evidence": copy.deepcopy(record)}

    def _coerce_evidence_input(
        self,
        evidence: Mapping[str, Any] | EngineeringEvidence | str,
        records: Mapping[str, dict[str, Any]],
        fields: Mapping[str, Any],
    ) -> dict[str, Any]:
        if isinstance(evidence, EngineeringEvidence):
            raw = evidence.as_dict()
        elif isinstance(evidence, Mapping):
            raw = copy.deepcopy(dict(evidence))
        else:
            raw = {"evidence_name": _clean_text(evidence)}
        raw.update(copy.deepcopy(dict(fields)))
        evidence_name = _clean_text(raw.get("evidence_name") or raw.get("name") or raw.get("evidence_path"), "Untitled evidence")
        evidence_id = _clean_text(raw.get("evidence_id") or raw.get("id"))
        if not evidence_id:
            evidence_id = self._new_evidence_id(evidence_name, records)
        raw.setdefault("evidence_id", evidence_id)
        raw.setdefault("evidence_name", evidence_name)
        raw.setdefault("artifact_id", "")
        raw.setdefault("goal_id", "")
        raw.setdefault("portfolio_id", "")
        raw.setdefault("program_id", "")
        raw.setdefault("evidence_type", "")
        raw.setdefault("evidence_path", "")
        raw.setdefault("created_at", time.time())
        raw.setdefault("metadata", {})
        return raw

    def _new_evidence_id(self, evidence_name: str, records: Mapping[str, dict[str, Any]]) -> str:
        seed = f"{evidence_name}:{time.time_ns()}"
        digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
        base = f"evidence_{_safe_evidence_id(evidence_name)[:32]}_{digest}"
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
                key=lambda item: (_as_float(item.get("created_at")), _clean_text(item.get("evidence_id"))),
            )
        ]

    def _read_records(self) -> dict[str, dict[str, Any]]:
        if not self.storage_path.is_file():
            return {}
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        evidence = data if isinstance(data, list) else data.get("evidence") if isinstance(data, Mapping) else []
        records: dict[str, dict[str, Any]] = {}
        if isinstance(evidence, list):
            for item in evidence:
                if not isinstance(item, Mapping):
                    continue
                try:
                    record = EngineeringEvidence.from_mapping(item).as_dict()
                except ValueError:
                    continue
                records[record["evidence_id"]] = record
        return records

    def _write_records(self, records: Mapping[str, Mapping[str, Any]]) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": ENGINEERING_EVIDENCE_REPOSITORY_SCHEMA,
            "evidence": [
                copy.deepcopy(dict(record))
                for record in sorted(
                    records.values(),
                    key=lambda item: (_as_float(item.get("created_at")), _clean_text(item.get("evidence_id"))),
                )
            ],
            "updated_at": time.time(),
        }
        self.storage_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


__all__ = [
    "ENGINEERING_EVIDENCE_RECORD_SCHEMA",
    "ENGINEERING_EVIDENCE_REPOSITORY_SCHEMA",
    "EngineeringEvidence",
    "EngineeringEvidenceRepository",
]
