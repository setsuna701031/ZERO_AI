from __future__ import annotations

"""Persistent repository for engineering programs.

EngineeringProgramRepository owns only program records and portfolio references.
It does not inspect portfolios, goals, runtime task chains, scheduler state, or
memory.
"""

import copy
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence


ENGINEERING_PROGRAM_REPOSITORY_SCHEMA = "zero.engineering_program_repository.v1"


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clean_portfolio_refs(value: Any) -> list[str]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        return []
    refs: list[str] = []
    seen: set[str] = set()
    for item in value:
        portfolio_id = _clean_text(item)
        if portfolio_id and portfolio_id not in seen:
            refs.append(portfolio_id)
            seen.add(portfolio_id)
    return refs


def _safe_program_id(value: str) -> str:
    safe = []
    for char in value:
        if char.isalnum() or char in {"-", "_", "."}:
            safe.append(char)
        elif char.isspace():
            safe.append("_")
    return "".join(safe).strip("._-").lower()[:80] or "program"


@dataclass(frozen=True)
class EngineeringProgram:
    program_id: str
    name: str
    description: str = ""
    portfolio_ids: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EngineeringProgram":
        program_id = _clean_text(value.get("program_id") or value.get("id"))
        name = _clean_text(value.get("name") or value.get("summary"), program_id)
        if not program_id:
            raise ValueError("engineering_program_requires_program_id")
        if not name:
            raise ValueError("engineering_program_requires_name")
        return cls(
            program_id=program_id,
            name=name,
            description=_clean_text(value.get("description")),
            portfolio_ids=_clean_portfolio_refs(value.get("portfolio_ids")),
            created_at=_as_float(value.get("created_at"), time.time()),
            updated_at=_as_float(value.get("updated_at"), time.time()),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "program_id": self.program_id,
            "name": self.name,
            "description": self.description,
            "portfolio_ids": _clean_portfolio_refs(self.portfolio_ids),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class EngineeringProgramRepository:
    """Create, load, list, and edit program portfolio references."""

    def __init__(
        self,
        repo_root: str | Path,
        *,
        storage_path: str | Path | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.storage_path = Path(storage_path) if storage_path is not None else self.repo_root / "runtime" / "programs" / "programs.json"
        if not self.storage_path.is_absolute():
            self.storage_path = self.repo_root / self.storage_path

    @property
    def storage_dir(self) -> Path:
        return self.storage_path.parent

    def create_program(self, program: Mapping[str, Any] | EngineeringProgram | str, **fields: Any) -> dict[str, Any]:
        records = self._read_records()
        raw = self._coerce_program_input(program, records, fields)
        record = EngineeringProgram.from_mapping(raw).as_dict()
        program_id = record["program_id"]
        if program_id in records:
            raise ValueError(f"engineering_program_already_exists:{program_id}")
        records[program_id] = record
        self._write_records(records)
        return copy.deepcopy(record)

    def load_program(self, program_id: str) -> dict[str, Any] | None:
        record = self._read_records().get(_clean_text(program_id))
        return copy.deepcopy(record) if record else None

    def list_programs(self) -> list[dict[str, Any]]:
        return [
            copy.deepcopy(record)
            for record in sorted(
                self._read_records().values(),
                key=lambda item: (_as_float(item.get("created_at")), _clean_text(item.get("program_id"))),
            )
        ]

    def add_portfolio(self, program_id: str, portfolio_id: str) -> dict[str, Any]:
        program = self.load_program(program_id)
        if program is None:
            raise KeyError(_clean_text(program_id))
        target_portfolio_id = _clean_text(portfolio_id)
        if not target_portfolio_id:
            raise ValueError("engineering_program_portfolio_ref_required")
        portfolio_ids = _clean_portfolio_refs(program.get("portfolio_ids"))
        if target_portfolio_id not in portfolio_ids:
            portfolio_ids.append(target_portfolio_id)
        return self._update_program(program["program_id"], {"portfolio_ids": portfolio_ids})

    def remove_portfolio(self, program_id: str, portfolio_id: str) -> dict[str, Any]:
        program = self.load_program(program_id)
        if program is None:
            raise KeyError(_clean_text(program_id))
        target_portfolio_id = _clean_text(portfolio_id)
        portfolio_ids = [item for item in _clean_portfolio_refs(program.get("portfolio_ids")) if item != target_portfolio_id]
        return self._update_program(program["program_id"], {"portfolio_ids": portfolio_ids})

    def _update_program(self, program_id: str, updates: Mapping[str, Any]) -> dict[str, Any]:
        target_program_id = _clean_text(program_id)
        if not target_program_id:
            raise ValueError("engineering_program_update_requires_program_id")
        records = self._read_records()
        existing = records.get(target_program_id)
        if existing is None:
            raise KeyError(target_program_id)
        merged = copy.deepcopy(existing)
        for key, value in updates.items():
            if key in {"program_id", "created_at"}:
                continue
            if key == "portfolio_ids":
                merged["portfolio_ids"] = _clean_portfolio_refs(value)
            else:
                merged[str(key)] = copy.deepcopy(value)
        merged["updated_at"] = time.time()
        updated = EngineeringProgram.from_mapping(merged).as_dict()
        records[target_program_id] = updated
        self._write_records(records)
        return copy.deepcopy(updated)

    def _coerce_program_input(
        self,
        program: Mapping[str, Any] | EngineeringProgram | str,
        records: Mapping[str, dict[str, Any]],
        fields: Mapping[str, Any],
    ) -> dict[str, Any]:
        if isinstance(program, EngineeringProgram):
            raw = program.as_dict()
        elif isinstance(program, Mapping):
            raw = copy.deepcopy(dict(program))
        else:
            raw = {"name": _clean_text(program)}
        raw.update(copy.deepcopy(dict(fields)))
        name = _clean_text(raw.get("name") or raw.get("summary"), "Untitled engineering program")
        program_id = _clean_text(raw.get("program_id") or raw.get("id"))
        if not program_id:
            program_id = self._new_program_id(name, records)
        now = time.time()
        raw.setdefault("program_id", program_id)
        raw.setdefault("name", name)
        raw.setdefault("description", "")
        raw.setdefault("portfolio_ids", [])
        raw.setdefault("created_at", now)
        raw.setdefault("updated_at", raw.get("created_at", now))
        return raw

    def _new_program_id(self, name: str, records: Mapping[str, dict[str, Any]]) -> str:
        seed = f"{name}:{time.time_ns()}"
        digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
        base = f"program_{_safe_program_id(name)[:32]}_{digest}"
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
        programs = data if isinstance(data, list) else data.get("programs") if isinstance(data, Mapping) else []
        records: dict[str, dict[str, Any]] = {}
        if isinstance(programs, list):
            for item in programs:
                if not isinstance(item, Mapping):
                    continue
                try:
                    record = EngineeringProgram.from_mapping(item).as_dict()
                except ValueError:
                    continue
                records[record["program_id"]] = record
        return records

    def _write_records(self, records: Mapping[str, Mapping[str, Any]]) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": ENGINEERING_PROGRAM_REPOSITORY_SCHEMA,
            "programs": [
                copy.deepcopy(dict(record))
                for record in sorted(
                    records.values(),
                    key=lambda item: (_as_float(item.get("created_at")), _clean_text(item.get("program_id"))),
                )
            ],
            "updated_at": time.time(),
        }
        self.storage_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


__all__ = [
    "ENGINEERING_PROGRAM_REPOSITORY_SCHEMA",
    "EngineeringProgram",
    "EngineeringProgramRepository",
]
