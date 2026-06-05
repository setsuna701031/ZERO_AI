from __future__ import annotations

"""Persistent repository for engineering goal portfolios.

EngineeringPortfolioRepository owns only portfolio records and goal references.
It does not execute goals, schedule goals, run loops, persist memory, or call the
runtime orchestrator.
"""

import copy
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence


ENGINEERING_PORTFOLIO_REPOSITORY_SCHEMA = "zero.engineering_portfolio_repository.v1"
ENGINEERING_PORTFOLIO_SCHEMA = "zero.engineering_portfolio.v1"


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


def _clean_goal_refs(value: Any) -> list[str]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        return []
    refs: list[str] = []
    seen: set[str] = set()
    for item in value:
        goal_id = _clean_text(item)
        if goal_id and goal_id not in seen:
            refs.append(goal_id)
            seen.add(goal_id)
    return refs


def _safe_portfolio_id(value: str) -> str:
    safe = []
    for char in value:
        if char.isalnum() or char in {"-", "_", "."}:
            safe.append(char)
        elif char.isspace():
            safe.append("_")
    return "".join(safe).strip("._-").lower()[:80] or "portfolio"


@dataclass(frozen=True)
class EngineeringPortfolio:
    portfolio_id: str
    name: str
    goal_ids: list[str] = field(default_factory=list)
    description: str = ""
    lifecycle_state: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EngineeringPortfolio":
        portfolio_id = _clean_text(value.get("portfolio_id") or value.get("id"))
        name = _clean_text(value.get("name") or value.get("summary"), portfolio_id)
        if not portfolio_id:
            raise ValueError("engineering_portfolio_requires_portfolio_id")
        if not name:
            raise ValueError("engineering_portfolio_requires_name")
        return cls(
            portfolio_id=portfolio_id,
            name=name,
            goal_ids=_clean_goal_refs(value.get("goal_ids")),
            description=_clean_text(value.get("description")),
            lifecycle_state=_clean_text(value.get("lifecycle_state") or value.get("state")).lower(),
            metadata=_as_mapping(value.get("metadata")),
            created_at=_as_float(value.get("created_at"), time.time()),
            updated_at=_as_float(value.get("updated_at"), time.time()),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": ENGINEERING_PORTFOLIO_SCHEMA,
            "portfolio_id": self.portfolio_id,
            "name": self.name,
            "description": self.description,
            "lifecycle_state": self.lifecycle_state,
            "goal_ids": _clean_goal_refs(self.goal_ids),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class EngineeringPortfolioRepository:
    """Create, load, update, list, and edit portfolio goal references."""

    def __init__(
        self,
        repo_root: str | Path,
        *,
        storage_path: str | Path | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.storage_path = Path(storage_path) if storage_path is not None else self.repo_root / "runtime" / "portfolios" / "portfolios.json"
        if not self.storage_path.is_absolute():
            self.storage_path = self.repo_root / self.storage_path

    @property
    def storage_dir(self) -> Path:
        return self.storage_path.parent

    def create_portfolio(self, portfolio: Mapping[str, Any] | EngineeringPortfolio | str, **fields: Any) -> dict[str, Any]:
        records = self._read_records()
        raw = self._coerce_portfolio_input(portfolio, records, fields)
        record = EngineeringPortfolio.from_mapping(raw).as_dict()
        portfolio_id = record["portfolio_id"]
        if portfolio_id in records:
            raise ValueError(f"engineering_portfolio_already_exists:{portfolio_id}")
        records[portfolio_id] = record
        self._write_records(records)
        return copy.deepcopy(record)

    def load_portfolio(self, portfolio_id: str) -> dict[str, Any] | None:
        record = self._read_records().get(_clean_text(portfolio_id))
        return copy.deepcopy(record) if record else None

    def update_portfolio(self, portfolio_id: str, updates: Mapping[str, Any]) -> dict[str, Any]:
        target_portfolio_id = _clean_text(portfolio_id)
        if not target_portfolio_id:
            raise ValueError("engineering_portfolio_update_requires_portfolio_id")
        if not isinstance(updates, Mapping):
            raise ValueError("engineering_portfolio_updates_must_be_mapping")
        records = self._read_records()
        existing = records.get(target_portfolio_id)
        if existing is None:
            raise KeyError(target_portfolio_id)
        merged = copy.deepcopy(existing)
        for key, value in updates.items():
            if key in {"schema", "portfolio_id", "created_at"}:
                continue
            if key == "metadata" and isinstance(value, Mapping):
                metadata = _as_mapping(merged.get("metadata"))
                metadata.update(copy.deepcopy(dict(value)))
                merged["metadata"] = metadata
            elif key == "goal_ids":
                merged["goal_ids"] = _clean_goal_refs(value)
            else:
                merged[str(key)] = copy.deepcopy(value)
        merged["updated_at"] = time.time()
        updated = EngineeringPortfolio.from_mapping(merged).as_dict()
        records[target_portfolio_id] = updated
        self._write_records(records)
        return copy.deepcopy(updated)

    def list_portfolios(self) -> list[dict[str, Any]]:
        return [
            copy.deepcopy(record)
            for record in sorted(
                self._read_records().values(),
                key=lambda item: (_as_float(item.get("created_at")), _clean_text(item.get("portfolio_id"))),
            )
        ]

    def add_goal_to_portfolio(self, portfolio_id: str, goal_id: str) -> dict[str, Any]:
        portfolio = self.load_portfolio(portfolio_id)
        if portfolio is None:
            raise KeyError(_clean_text(portfolio_id))
        target_goal_id = _clean_text(goal_id)
        if not target_goal_id:
            raise ValueError("engineering_portfolio_goal_ref_required")
        goal_ids = _clean_goal_refs(portfolio.get("goal_ids"))
        if target_goal_id not in goal_ids:
            goal_ids.append(target_goal_id)
        return self.update_portfolio(portfolio["portfolio_id"], {"goal_ids": goal_ids})

    def remove_goal_from_portfolio(self, portfolio_id: str, goal_id: str) -> dict[str, Any]:
        portfolio = self.load_portfolio(portfolio_id)
        if portfolio is None:
            raise KeyError(_clean_text(portfolio_id))
        target_goal_id = _clean_text(goal_id)
        goal_ids = [item for item in _clean_goal_refs(portfolio.get("goal_ids")) if item != target_goal_id]
        return self.update_portfolio(portfolio["portfolio_id"], {"goal_ids": goal_ids})

    def list_portfolio_goals(self, portfolio_id: str) -> list[str]:
        portfolio = self.load_portfolio(portfolio_id)
        if portfolio is None:
            raise KeyError(_clean_text(portfolio_id))
        return _clean_goal_refs(portfolio.get("goal_ids"))

    def _coerce_portfolio_input(
        self,
        portfolio: Mapping[str, Any] | EngineeringPortfolio | str,
        records: Mapping[str, dict[str, Any]],
        fields: Mapping[str, Any],
    ) -> dict[str, Any]:
        if isinstance(portfolio, EngineeringPortfolio):
            raw = portfolio.as_dict()
        elif isinstance(portfolio, Mapping):
            raw = copy.deepcopy(dict(portfolio))
        else:
            raw = {"name": _clean_text(portfolio)}
        raw.update(copy.deepcopy(dict(fields)))
        name = _clean_text(raw.get("name") or raw.get("summary"), "Untitled engineering portfolio")
        portfolio_id = _clean_text(raw.get("portfolio_id") or raw.get("id"))
        if not portfolio_id:
            portfolio_id = self._new_portfolio_id(name, records)
        now = time.time()
        raw.setdefault("portfolio_id", portfolio_id)
        raw.setdefault("name", name)
        raw.setdefault("description", "")
        raw.setdefault("goal_ids", [])
        raw.setdefault("metadata", {})
        raw.setdefault("created_at", now)
        raw.setdefault("updated_at", raw.get("created_at", now))
        return raw

    def _new_portfolio_id(self, name: str, records: Mapping[str, dict[str, Any]]) -> str:
        seed = f"{name}:{time.time_ns()}"
        digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
        base = f"portfolio_{_safe_portfolio_id(name)[:32]}_{digest}"
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
        portfolios = data if isinstance(data, list) else data.get("portfolios") if isinstance(data, Mapping) else []
        records: dict[str, dict[str, Any]] = {}
        if isinstance(portfolios, list):
            for item in portfolios:
                if not isinstance(item, Mapping):
                    continue
                try:
                    record = EngineeringPortfolio.from_mapping(item).as_dict()
                except ValueError:
                    continue
                records[record["portfolio_id"]] = record
        return records

    def _write_records(self, records: Mapping[str, Mapping[str, Any]]) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": ENGINEERING_PORTFOLIO_REPOSITORY_SCHEMA,
            "portfolios": [
                copy.deepcopy(dict(record))
                for record in sorted(
                    records.values(),
                    key=lambda item: (_as_float(item.get("created_at")), _clean_text(item.get("portfolio_id"))),
                )
            ],
            "updated_at": time.time(),
        }
        self.storage_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


__all__ = [
    "ENGINEERING_PORTFOLIO_REPOSITORY_SCHEMA",
    "ENGINEERING_PORTFOLIO_SCHEMA",
    "EngineeringPortfolio",
    "EngineeringPortfolioRepository",
]
