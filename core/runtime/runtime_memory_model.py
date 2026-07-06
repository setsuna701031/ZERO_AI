from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION


MAX_THAW_DEPTH = 8
MAX_THAW_ITEMS = 200
MAX_THAW_BYTES = 4096


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
            "__type__": f"{value.__class__.__module__}.{value.__class__.__qualname__}",
            "attrs": _canonicalize_for_fingerprint(public_attrs),
        }
    return {
        "__type__": f"{value.__class__.__module__}.{value.__class__.__qualname__}",
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
            {str(key): _freeze(item) for key, item in sorted(value.items())}
        )
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return tuple(_freeze(item) for item in sorted(value, key=str))
    return copy.deepcopy(value)


def _thaw(
    value: Any,
    *,
    depth: int = 0,
    seen: set[int] | None = None,
) -> Any:
    if seen is None:
        seen = set()

    if depth > MAX_THAW_DEPTH:
        return {
            "__truncated__": True,
            "reason": "max_thaw_depth_exceeded",
            "max_depth": MAX_THAW_DEPTH,
        }

    value_id = id(value)
    if value_id in seen:
        return {
            "__truncated__": True,
            "reason": "cycle_detected",
        }

    if isinstance(value, bytes):
        if len(value) > MAX_THAW_BYTES:
            return {
                "__bytes_truncated__": True,
                "size": len(value),
                "sha256": hashlib.sha256(value).hexdigest(),
                "max_inline_bytes": MAX_THAW_BYTES,
            }
        return copy.deepcopy(value)

    if isinstance(value, MappingProxyType):
        seen.add(value_id)
        items = list(value.items())
        truncated = len(items) > MAX_THAW_ITEMS
        selected = items[:MAX_THAW_ITEMS]
        result = {
            key: _thaw(item, depth=depth + 1, seen=seen)
            for key, item in selected
        }
        if truncated:
            result["__truncated__"] = True
            result["__truncated_reason__"] = "max_mapping_items_exceeded"
            result["__original_item_count__"] = len(items)
            result["__max_items__"] = MAX_THAW_ITEMS
        seen.discard(value_id)
        return result

    if isinstance(value, Mapping):
        seen.add(value_id)
        items = list(value.items())
        truncated = len(items) > MAX_THAW_ITEMS
        selected = items[:MAX_THAW_ITEMS]
        result = {
            str(key): _thaw(item, depth=depth + 1, seen=seen)
            for key, item in selected
        }
        if truncated:
            result["__truncated__"] = True
            result["__truncated_reason__"] = "max_mapping_items_exceeded"
            result["__original_item_count__"] = len(items)
            result["__max_items__"] = MAX_THAW_ITEMS
        seen.discard(value_id)
        return result

    if isinstance(value, tuple | list):
        seen.add(value_id)
        items = list(value)
        truncated = len(items) > MAX_THAW_ITEMS
        result = [
            _thaw(item, depth=depth + 1, seen=seen)
            for item in items[:MAX_THAW_ITEMS]
        ]
        if truncated:
            result.append(
                {
                    "__truncated__": True,
                    "reason": "max_sequence_items_exceeded",
                    "original_item_count": len(items),
                    "max_items": MAX_THAW_ITEMS,
                }
            )
        seen.discard(value_id)
        return result

    return copy.deepcopy(value)


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
        object.__setattr__(self, "transactions", _freeze(self.transactions or {}))
        object.__setattr__(self, "replay", _freeze(self.replay or {}))
        object.__setattr__(self, "recovery", _freeze(self.recovery or {}))
        object.__setattr__(self, "capabilities", _freeze(self.capabilities or {}))
        object.__setattr__(self, "intent", _freeze(self.intent or {}))
        object.__setattr__(self, "scheduler", _freeze(self.scheduler or {}))
        if not self.snapshot_id:
            object.__setattr__(
                self,
                "snapshot_id",
                "runtime-memory-" + _stable_hash(self._fingerprint_payload())[:16],
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
    "RuntimeMemorySnapshot",
    "RuntimeMemoryView",
    "RuntimeStateView",
    "RuntimeTransactionView",
    "build_runtime_memory_snapshot",
]