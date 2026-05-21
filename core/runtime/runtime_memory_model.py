from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping

from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in sorted(value.items())})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return tuple(_freeze(item) for item in sorted(value, key=str))
    return copy.deepcopy(value)


def _thaw(value: Any) -> Any:
    if isinstance(value, MappingProxyType):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
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
            object.__setattr__(self, "snapshot_id", "runtime-memory-" + _stable_hash(self.to_dict(False))[:16])
        if not self.fingerprint:
            object.__setattr__(self, "fingerprint", _stable_hash(self.to_dict(False)))

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
