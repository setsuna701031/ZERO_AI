from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION


RUNTIME_ACTIVITY_MEMORY_QUERY_SCHEMA = "zero.runtime.activity_memory_query.v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


_VOLATILE_FINGERPRINT_KEYS = {
    "created_at",
    "generated_at",
    "updated_at",
    "timestamp",
    "runtime_timestamp",
    "fingerprint",
    "object_id",
    "memory_address",
}


def _canonicalize_for_fingerprint(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize_for_fingerprint(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in _VOLATILE_FINGERPRINT_KEYS
        }
    if isinstance(value, list | tuple):
        return [_canonicalize_for_fingerprint(item) for item in value]
    if isinstance(value, set):
        canonical_items = [_canonicalize_for_fingerprint(item) for item in value]
        return sorted(
            canonical_items,
            key=lambda item: json.dumps(
                item,
                sort_keys=True,
                default=str,
                separators=(",", ":"),
            ),
        )
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Path):
        return value.as_posix()
    if is_dataclass(value) and not isinstance(value, type):
        return _canonicalize_for_fingerprint(asdict(value))
    if isinstance(value, bytes):
        return {"__bytes__": value.hex()}
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if hasattr(value, "to_dict") and callable(value.to_dict):
        try:
            converted = value.to_dict()
        except Exception:
            converted = None
        if converted is not None:
            return _canonicalize_for_fingerprint(converted)
    attrs = getattr(value, "__dict__", None)
    if isinstance(attrs, dict):
        public_attrs = {
            key: item
            for key, item in attrs.items()
            if not str(key).startswith("_")
        }
        return {
            "__type__": (
                f"{value.__class__.__module__}."
                f"{value.__class__.__qualname__}"
            ),
            "attrs": _canonicalize_for_fingerprint(public_attrs),
        }
    return {
        "__type__": (
            f"{value.__class__.__module__}."
            f"{value.__class__.__qualname__}"
        ),
        "value": str(value),
    }


def _stable_hash(value: Any) -> str:
    payload = json.dumps(
        _canonicalize_for_fingerprint(value),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                str(key): _freeze(item)
                for key, item in sorted(value.items())
            }
        )
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return tuple(_freeze(item) for item in sorted(value, key=str))
    return copy.deepcopy(value)


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _thaw(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return copy.deepcopy(value)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return _thaw(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return copy.deepcopy(value)
    if isinstance(value, tuple):
        return list(copy.deepcopy(value))
    return []


def _goal_tokens(value: Any) -> set[str]:
    text = _text(value).lower()
    if not text:
        return set()

    latin_tokens = re.findall(r"[a-z0-9_.\-/]+", text)
    chinese_tokens = re.findall(r"[\u4e00-\u9fff]{2,}", text)

    tokens = {
        token.strip("._-/")
        for token in latin_tokens + chinese_tokens
        if token.strip("._-/")
    }
    return {token for token in tokens if len(token) >= 2}


def _record_paths(record: Mapping[str, Any]) -> set[str]:
    return {
        _text(path).replace("\\", "/").lower()
        for path in _list(record.get("changed_files"))
        if _text(path)
    }


def _activity_similarity(
    goal: str,
    record: Mapping[str, Any],
) -> tuple[float, list[str]]:
    query_tokens = _goal_tokens(goal)
    record_goal = _text(record.get("goal"))
    record_tokens = _goal_tokens(record_goal)

    if not query_tokens or not record_tokens:
        return 0.0, []

    overlap = sorted(query_tokens & record_tokens)
    union = query_tokens | record_tokens
    token_score = len(overlap) / len(union) if union else 0.0

    query_paths = {
        token.replace("\\", "/").lower()
        for token in query_tokens
        if "/" in token or "." in token
    }
    record_paths = _record_paths(record)
    path_overlap = query_paths & record_paths
    path_score = 1.0 if path_overlap else 0.0

    exact_goal_score = 1.0 if goal.strip().lower() == record_goal.lower() else 0.0
    score = (
        token_score * 0.65
        + path_score * 0.20
        + exact_goal_score * 0.15
    )
    return round(score, 6), overlap


def _load_activity_records(
    log_path: str | Path,
) -> tuple[list[dict[str, Any]], int]:
    path = Path(log_path)
    if not path.exists():
        return [], 0

    records: list[dict[str, Any]] = []
    invalid_line_count = 0

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except Exception:
            invalid_line_count += 1
            continue
        if isinstance(payload, dict):
            records.append(payload)
        else:
            invalid_line_count += 1

    return records, invalid_line_count


@dataclass(frozen=True)
class RuntimeActivityExperience:
    record: Any
    similarity: float
    matched_tokens: Any = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "record", _freeze(self.record or {}))
        object.__setattr__(
            self,
            "matched_tokens",
            tuple(_text(item) for item in self.matched_tokens if _text(item)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "similarity": self.similarity,
            "matched_tokens": list(self.matched_tokens),
            "record": _thaw(self.record),
        }


@dataclass(frozen=True)
class RuntimeActivityMemory:
    log_path: str | Path = "workspace/operator_activity/activity.jsonl"

    def read_all(self) -> dict[str, Any]:
        records, invalid_line_count = _load_activity_records(self.log_path)
        return {
            "schema": RUNTIME_ACTIVITY_MEMORY_QUERY_SCHEMA,
            "ok": True,
            "memory_status": "loaded" if records else "empty",
            "records": records,
            "record_count": len(records),
            "invalid_line_count": invalid_line_count,
            "log_path": str(self.log_path),
        }

    def query(
        self,
        goal: Any,
        *,
        limit: int = 5,
        status: str | None = None,
        minimum_similarity: float = 0.0,
    ) -> dict[str, Any]:
        normalized_goal = _text(goal)
        if not normalized_goal:
            return {
                "schema": RUNTIME_ACTIVITY_MEMORY_QUERY_SCHEMA,
                "ok": False,
                "memory_status": "denied",
                "denial_reason": "goal_required",
                "query_goal": "",
                "matches": [],
                "match_count": 0,
                "log_path": str(self.log_path),
            }

        loaded = self.read_all()
        requested_status = _text(status).lower()
        bounded_limit = max(1, int(limit))
        threshold = max(0.0, min(1.0, float(minimum_similarity)))

        matches: list[RuntimeActivityExperience] = []
        for record in loaded["records"]:
            if requested_status:
                record_status = _text(record.get("status")).lower()
                if record_status != requested_status:
                    continue

            similarity, matched_tokens = _activity_similarity(
                normalized_goal,
                record,
            )
            if similarity < threshold:
                continue

            matches.append(
                RuntimeActivityExperience(
                    record=record,
                    similarity=similarity,
                    matched_tokens=matched_tokens,
                )
            )

        matches.sort(
            key=lambda item: (
                item.similarity,
                _text(_mapping(item.record).get("recorded_at")),
            ),
            reverse=True,
        )
        selected = matches[:bounded_limit]

        return {
            "schema": RUNTIME_ACTIVITY_MEMORY_QUERY_SCHEMA,
            "ok": True,
            "memory_status": "matched" if selected else "no_match",
            "query_goal": normalized_goal,
            "requested_status": requested_status,
            "minimum_similarity": threshold,
            "matches": [item.to_dict() for item in selected],
            "match_count": len(selected),
            "record_count": loaded["record_count"],
            "invalid_line_count": loaded["invalid_line_count"],
            "log_path": str(self.log_path),
        }

    def decision_context(
        self,
        goal: Any,
        *,
        limit: int = 3,
    ) -> dict[str, Any]:
        completed = self.query(
            goal,
            limit=limit,
            status="completed",
            minimum_similarity=0.01,
        )
        failed = self.query(
            goal,
            limit=limit,
            status="failed",
            minimum_similarity=0.01,
        )
        rolled_back = self.query(
            goal,
            limit=limit,
            status="rolled_back",
            minimum_similarity=0.01,
        )

        successful_paths: list[str] = []
        prior_denial_reasons: list[str] = []

        for match in completed["matches"]:
            record = _mapping(match.get("record"))
            for path in _list(record.get("changed_files")):
                normalized = _text(path)
                if normalized and normalized not in successful_paths:
                    successful_paths.append(normalized)

        for group in (failed["matches"], rolled_back["matches"]):
            for match in group:
                record = _mapping(match.get("record"))
                reason = _text(record.get("denial_reason"))
                if reason and reason not in prior_denial_reasons:
                    prior_denial_reasons.append(reason)

        return {
            "schema": RUNTIME_ACTIVITY_MEMORY_QUERY_SCHEMA,
            "ok": True,
            "memory_status": (
                "context_available"
                if (
                    completed["match_count"]
                    or failed["match_count"]
                    or rolled_back["match_count"]
                )
                else "empty"
            ),
            "goal": _text(goal),
            "completed_experiences": completed["matches"],
            "failed_experiences": failed["matches"],
            "rolled_back_experiences": rolled_back["matches"],
            "successful_paths": successful_paths,
            "prior_denial_reasons": prior_denial_reasons,
            "experience_count": (
                completed["match_count"]
                + failed["match_count"]
                + rolled_back["match_count"]
            ),
            "log_path": str(self.log_path),
        }


@dataclass(frozen=True)
class RuntimeMemorySnapshot:
    snapshot_id: str
    checkpoint_id: str
    state: Any = field(default_factory=dict)
    transactions: Any = field(default_factory=dict)
    replay: Any = field(default_factory=dict)
    recovery: Any = field(default_factory=dict)
    capabilities: Any = field(default_factory=dict)
    intent: Any = field(default_factory=dict)
    scheduler: Any = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now)
    fingerprint: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "state", _freeze(self.state or {}))
        object.__setattr__(
            self,
            "transactions",
            _freeze(self.transactions or {}),
        )
        object.__setattr__(self, "replay", _freeze(self.replay or {}))
        object.__setattr__(self, "recovery", _freeze(self.recovery or {}))
        object.__setattr__(
            self,
            "capabilities",
            _freeze(self.capabilities or {}),
        )
        object.__setattr__(self, "intent", _freeze(self.intent or {}))
        object.__setattr__(self, "scheduler", _freeze(self.scheduler or {}))
        if not self.snapshot_id:
            object.__setattr__(
                self,
                "snapshot_id",
                "runtime-memory-"
                + _stable_hash(self._fingerprint_payload())[:16],
            )
        if not self.fingerprint:
            object.__setattr__(
                self,
                "fingerprint",
                _stable_hash(self._fingerprint_payload()),
            )

    def view(self) -> "RuntimeMemoryView":
        return RuntimeMemoryView(snapshot=self)

    def to_dict(self, include_fingerprint: bool = True) -> dict[str, Any]:
        payload = {
            "runtime_version": RUNTIME_KERNEL_VERSION,
            "abi_version": RUNTIME_ABI_VERSION,
            "artifact_type": "runtime_memory_snapshot",
            "snapshot_id": self.snapshot_id,
            "checkpoint_id": self.checkpoint_id,
            "created_at": self.created_at,
            "state": _thaw(self.state),
            "transactions": _thaw(self.transactions),
            "replay": _thaw(self.replay),
            "recovery": _thaw(self.recovery),
            "capabilities": _thaw(self.capabilities),
            "intent": _thaw(self.intent),
            "scheduler": _thaw(self.scheduler),
        }
        if include_fingerprint:
            payload["fingerprint"] = self.fingerprint
        return payload

    def _fingerprint_payload(self) -> dict[str, Any]:
        return {
            "runtime_version": RUNTIME_KERNEL_VERSION,
            "abi_version": RUNTIME_ABI_VERSION,
            "artifact_type": "runtime_memory_snapshot",
            "checkpoint_id": self.checkpoint_id,
            "state": _thaw(self.state),
            "transactions": _thaw(self.transactions),
            "replay": _thaw(self.replay),
            "recovery": _thaw(self.recovery),
            "capabilities": _thaw(self.capabilities),
            "intent": _thaw(self.intent),
            "scheduler": _thaw(self.scheduler),
        }


@dataclass(frozen=True)
class RuntimeStateView:
    snapshot: RuntimeMemorySnapshot

    def get(self, key: str, default: Any = None) -> Any:
        state = _thaw(self.snapshot.state)
        return copy.deepcopy(state.get(key, default))

    def to_dict(self) -> dict[str, Any]:
        return _thaw(self.snapshot.state)


@dataclass(frozen=True)
class RuntimeTransactionView:
    snapshot: RuntimeMemorySnapshot

    def transaction(self, transaction_id: str) -> dict[str, Any]:
        transactions = _thaw(self.snapshot.transactions)
        return copy.deepcopy(transactions.get(transaction_id, {}))

    def to_dict(self) -> dict[str, Any]:
        return _thaw(self.snapshot.transactions)


@dataclass(frozen=True)
class RuntimeMemoryView:
    snapshot: RuntimeMemorySnapshot

    @property
    def state(self) -> RuntimeStateView:
        return RuntimeStateView(self.snapshot)

    @property
    def transactions(self) -> RuntimeTransactionView:
        return RuntimeTransactionView(self.snapshot)

    def replay_state(self) -> dict[str, Any]:
        return _thaw(self.snapshot.replay)

    def recovery_state(self) -> dict[str, Any]:
        return _thaw(self.snapshot.recovery)

    def to_dict(self) -> dict[str, Any]:
        return self.snapshot.to_dict()


def build_runtime_memory_snapshot(
    *,
    checkpoint_id: str,
    state: Mapping[str, Any] | None = None,
    transactions: Mapping[str, Any] | None = None,
    replay: Mapping[str, Any] | None = None,
    recovery: Mapping[str, Any] | None = None,
    capabilities: Mapping[str, Any] | None = None,
    intent: Mapping[str, Any] | None = None,
    scheduler: Mapping[str, Any] | None = None,
) -> RuntimeMemorySnapshot:
    seed = {
        "checkpoint_id": checkpoint_id,
        "state": dict(state or {}),
        "transactions": dict(transactions or {}),
        "replay": dict(replay or {}),
        "recovery": dict(recovery or {}),
        "capabilities": dict(capabilities or {}),
        "intent": dict(intent or {}),
        "scheduler": dict(scheduler or {}),
    }
    return RuntimeMemorySnapshot(
        snapshot_id="runtime-memory-" + _stable_hash(seed)[:16],
        checkpoint_id=checkpoint_id,
        state=seed["state"],
        transactions=seed["transactions"],
        replay=seed["replay"],
        recovery=seed["recovery"],
        capabilities=seed["capabilities"],
        intent=seed["intent"],
        scheduler=seed["scheduler"],
    )


__all__ = [
    "RUNTIME_ACTIVITY_MEMORY_QUERY_SCHEMA",
    "RuntimeActivityExperience",
    "RuntimeActivityMemory",
    "RuntimeMemorySnapshot",
    "RuntimeMemoryView",
    "RuntimeStateView",
    "RuntimeTransactionView",
    "build_runtime_memory_snapshot",
]
