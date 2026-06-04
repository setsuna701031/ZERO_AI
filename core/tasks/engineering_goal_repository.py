from __future__ import annotations

"""Persistent repository for engineering goal records.

EngineeringGoalRepository owns only goal record persistence. It does not run
goals, schedule goals, plan work, manage lifecycle state, or execute tasks.
"""

import copy
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


ENGINEERING_GOAL_REPOSITORY_SCHEMA = "zero.engineering_goal_repository.v1"
ENGINEERING_GOAL_RECORD_SCHEMA = "zero.engineering_goal_record.v1"


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


def _safe_goal_id(value: str) -> str:
    safe = []
    for char in value:
        if char.isalnum() or char in {"-", "_", "."}:
            safe.append(char)
        elif char.isspace():
            safe.append("_")
    cleaned = "".join(safe).strip("._-").lower()
    return cleaned[:80] or "goal"


@dataclass(frozen=True)
class EngineeringGoal:
    goal_id: str
    summary: str
    status: str = "pending"
    priority: float = 0.0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    description: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EngineeringGoal":
        goal_id = _clean_text(value.get("goal_id") or value.get("task_id") or value.get("package_id"))
        payload = _as_mapping(value.get("payload"))
        summary = _clean_text(
            value.get("summary")
            or value.get("goal")
            or payload.get("goal")
            or payload.get("summary"),
            goal_id,
        )
        if not goal_id:
            raise ValueError("engineering_goal_requires_goal_id")
        if not summary:
            raise ValueError("engineering_goal_requires_summary")
        return cls(
            goal_id=goal_id,
            summary=summary,
            status=_clean_text(value.get("status"), "pending").lower(),
            priority=_as_float(value.get("priority"), 0.0),
            created_at=_as_float(value.get("created_at"), time.time()),
            updated_at=_as_float(value.get("updated_at"), time.time()),
            description=_clean_text(value.get("description")),
            payload=payload,
            metadata=_as_mapping(value.get("metadata")),
        )

    def as_dict(self) -> dict[str, Any]:
        payload = copy.deepcopy(self.payload)
        payload.setdefault("goal", self.summary)
        payload.setdefault("goal_id", self.goal_id)
        payload.setdefault("task_id", self.goal_id)
        payload.setdefault("package_id", self.goal_id)
        payload.setdefault("task_type", "engineering_task")
        return {
            "schema": ENGINEERING_GOAL_RECORD_SCHEMA,
            "goal_id": self.goal_id,
            "summary": self.summary,
            "status": self.status,
            "priority": self.priority,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "description": self.description,
            "payload": payload,
            "metadata": copy.deepcopy(self.metadata),
        }


class EngineeringGoalRepository:
    """Save, load, update, and list persistent engineering goals."""

    def __init__(
        self,
        repo_root: str | Path,
        *,
        storage_path: str | Path | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.storage_path = Path(storage_path) if storage_path is not None else self.repo_root / "runtime" / "goals" / "goals.json"
        if not self.storage_path.is_absolute():
            self.storage_path = self.repo_root / self.storage_path

    @property
    def storage_dir(self) -> Path:
        return self.storage_path.parent

    def save_goal(self, goal: Mapping[str, Any] | EngineeringGoal | str, **fields: Any) -> dict[str, Any]:
        records = self._read_records()
        raw_goal = self._coerce_goal_input(goal, records, fields)
        goal_record = EngineeringGoal.from_mapping(raw_goal).as_dict()
        goal_id = goal_record["goal_id"]
        if goal_id in records:
            raise ValueError(f"engineering_goal_already_exists:{goal_id}")
        records[goal_id] = goal_record
        self._write_records(records)
        return copy.deepcopy(goal_record)

    def load_goal(self, goal_id: str) -> dict[str, Any] | None:
        record = self._read_records().get(_clean_text(goal_id))
        return copy.deepcopy(record) if record else None

    def update_goal(self, goal_id: str, updates: Mapping[str, Any]) -> dict[str, Any]:
        target_goal_id = _clean_text(goal_id)
        if not target_goal_id:
            raise ValueError("engineering_goal_update_requires_goal_id")
        if not isinstance(updates, Mapping):
            raise ValueError("engineering_goal_updates_must_be_mapping")
        records = self._read_records()
        existing = records.get(target_goal_id)
        if existing is None:
            raise KeyError(target_goal_id)
        merged = copy.deepcopy(existing)
        for key, value in updates.items():
            if key in {"schema", "goal_id", "created_at"}:
                continue
            if key == "payload" and isinstance(value, Mapping):
                payload = _as_mapping(merged.get("payload"))
                payload.update(copy.deepcopy(dict(value)))
                merged["payload"] = payload
            elif key == "metadata" and isinstance(value, Mapping):
                metadata = _as_mapping(merged.get("metadata"))
                metadata.update(copy.deepcopy(dict(value)))
                merged["metadata"] = metadata
            else:
                merged[str(key)] = copy.deepcopy(value)
        merged["updated_at"] = time.time()
        updated = EngineeringGoal.from_mapping(merged).as_dict()
        records[target_goal_id] = updated
        self._write_records(records)
        return copy.deepcopy(updated)

    def list_goals(self) -> list[dict[str, Any]]:
        return [
            copy.deepcopy(record)
            for record in sorted(
                self._read_records().values(),
                key=lambda item: (-_as_float(item.get("priority")), _as_float(item.get("created_at")), _clean_text(item.get("goal_id"))),
            )
        ]

    def _coerce_goal_input(
        self,
        goal: Mapping[str, Any] | EngineeringGoal | str,
        records: Mapping[str, dict[str, Any]],
        fields: Mapping[str, Any],
    ) -> dict[str, Any]:
        if isinstance(goal, EngineeringGoal):
            raw = goal.as_dict()
        elif isinstance(goal, Mapping):
            raw = copy.deepcopy(dict(goal))
        else:
            raw = {"summary": _clean_text(goal)}
        raw.update(copy.deepcopy(dict(fields)))
        summary = _clean_text(raw.get("summary") or raw.get("goal") or _as_mapping(raw.get("payload")).get("goal"))
        if not summary:
            summary = "Untitled engineering goal"
        goal_id = _clean_text(raw.get("goal_id") or raw.get("task_id") or raw.get("package_id"))
        if not goal_id:
            goal_id = self._new_goal_id(summary, records)
        now = time.time()
        raw.setdefault("goal_id", goal_id)
        raw.setdefault("summary", summary)
        raw.setdefault("status", "pending")
        raw.setdefault("priority", 0.0)
        raw.setdefault("created_at", now)
        raw.setdefault("updated_at", raw.get("created_at", now))
        payload = _as_mapping(raw.get("payload"))
        payload.setdefault("goal", summary)
        payload.setdefault("goal_id", goal_id)
        payload.setdefault("task_id", goal_id)
        payload.setdefault("package_id", goal_id)
        payload.setdefault("task_type", "engineering_task")
        raw["payload"] = payload
        return raw

    def _new_goal_id(self, summary: str, records: Mapping[str, dict[str, Any]]) -> str:
        seed = f"{summary}:{time.time_ns()}"
        digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
        base = f"goal_{_safe_goal_id(summary)[:32]}_{digest}"
        existing = set(records)
        if base not in existing:
            return base
        suffix = 2
        while f"{base}_{suffix}" in existing:
            suffix += 1
        return f"{base}_{suffix}"

    def _read_records(self) -> dict[str, dict[str, Any]]:
        if not self.storage_path.is_file():
            return {}
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        if isinstance(data, list):
            goals = data
        elif isinstance(data, Mapping):
            goals = data.get("goals")
        else:
            goals = []
        records: dict[str, dict[str, Any]] = {}
        if isinstance(goals, list):
            for item in goals:
                if not isinstance(item, Mapping):
                    continue
                try:
                    record = EngineeringGoal.from_mapping(item).as_dict()
                except ValueError:
                    continue
                records[record["goal_id"]] = record
        return records

    def _write_records(self, records: Mapping[str, Mapping[str, Any]]) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": ENGINEERING_GOAL_REPOSITORY_SCHEMA,
            "goals": [
                copy.deepcopy(dict(record))
                for record in sorted(
                    records.values(),
                    key=lambda item: (-_as_float(item.get("priority")), _as_float(item.get("created_at")), _clean_text(item.get("goal_id"))),
                )
            ],
            "updated_at": time.time(),
        }
        self.storage_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


__all__ = [
    "ENGINEERING_GOAL_RECORD_SCHEMA",
    "ENGINEERING_GOAL_REPOSITORY_SCHEMA",
    "EngineeringGoal",
    "EngineeringGoalRepository",
]
