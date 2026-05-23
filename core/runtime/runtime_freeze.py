from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_freeze_id(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return "runtime-freeze-" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class RuntimeFreezeState:
    runtime_frozen: bool
    reason: str = ""
    source: str = "runtime_freeze"
    freeze_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if not payload.get("freeze_id"):
            payload["freeze_id"] = stable_freeze_id(
                {
                    "runtime_frozen": self.runtime_frozen,
                    "reason": self.reason,
                    "source": self.source,
                    "metadata": self.metadata,
                    "created_at": self.created_at,
                }
            )
        return payload


@dataclass(frozen=True)
class RuntimeFreezeDecision:
    allowed: bool
    denied: bool
    runtime_frozen: bool
    reason: str
    action_type: str = "unknown"
    freeze_id: str | None = None
    source: str = "runtime_freeze"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RuntimeExecutionFrozen(RuntimeError):
    pass


class RuntimeFreezeAuthority:
    def evaluate(
        self,
        *,
        freeze_state: Any = None,
        runtime_frozen: bool | None = None,
        action_type: str = "unknown",
        reason: str | None = None,
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeFreezeDecision:
        state = normalize_runtime_freeze_state(
            freeze_state=freeze_state,
            runtime_frozen=runtime_frozen,
            reason=reason,
            source=source,
            metadata=metadata,
        )

        if state.runtime_frozen:
            state_payload = state.to_dict()
            return RuntimeFreezeDecision(
                allowed=False,
                denied=True,
                runtime_frozen=True,
                reason=state.reason or "runtime is frozen; execution denied",
                action_type=str(action_type or "unknown"),
                freeze_id=state_payload.get("freeze_id"),
                source=state.source,
                metadata={
                    **copy.deepcopy(state.metadata),
                    "freeze_state": state_payload,
                },
            )

        return RuntimeFreezeDecision(
            allowed=True,
            denied=False,
            runtime_frozen=False,
            reason="runtime is not frozen",
            action_type=str(action_type or "unknown"),
            freeze_id=None,
            source=state.source,
            metadata=copy.deepcopy(state.metadata),
        )

    def enforce(
        self,
        *,
        freeze_state: Any = None,
        runtime_frozen: bool | None = None,
        action_type: str = "unknown",
        reason: str | None = None,
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeFreezeDecision:
        decision = self.evaluate(
            freeze_state=freeze_state,
            runtime_frozen=runtime_frozen,
            action_type=action_type,
            reason=reason,
            source=source,
            metadata=metadata,
        )
        if decision.denied:
            raise RuntimeExecutionFrozen(decision.reason)
        return decision


def _get_attr_or_key(source: Any, name: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def normalize_runtime_freeze_state(
    *,
    freeze_state: Any = None,
    runtime_frozen: bool | None = None,
    reason: str | None = None,
    source: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> RuntimeFreezeState:
    if isinstance(freeze_state, RuntimeFreezeState):
        if runtime_frozen is None and reason is None and source is None and metadata is None:
            return freeze_state

        return RuntimeFreezeState(
            runtime_frozen=freeze_state.runtime_frozen if runtime_frozen is None else bool(runtime_frozen),
            reason=str(reason if reason is not None else freeze_state.reason),
            source=str(source if source is not None else freeze_state.source),
            freeze_id=freeze_state.freeze_id,
            metadata={
                **copy.deepcopy(freeze_state.metadata),
                **copy.deepcopy(metadata or {}),
            },
            created_at=freeze_state.created_at,
        )

    if isinstance(freeze_state, bool):
        runtime_frozen = bool(freeze_state)

    extracted_runtime_frozen = _get_attr_or_key(freeze_state, "runtime_frozen", None)
    if extracted_runtime_frozen is None:
        extracted_runtime_frozen = _get_attr_or_key(freeze_state, "frozen", None)
    if extracted_runtime_frozen is None:
        extracted_runtime_frozen = _get_attr_or_key(freeze_state, "is_frozen", None)

    if runtime_frozen is None:
        runtime_frozen = bool(extracted_runtime_frozen)

    extracted_reason = (
        _get_attr_or_key(freeze_state, "reason", None)
        or _get_attr_or_key(freeze_state, "message", None)
        or _get_attr_or_key(freeze_state, "freeze_reason", None)
    )
    extracted_source = (
        _get_attr_or_key(freeze_state, "source", None)
        or _get_attr_or_key(freeze_state, "origin", None)
        or "runtime_freeze"
    )
    extracted_freeze_id = (
        _get_attr_or_key(freeze_state, "freeze_id", None)
        or _get_attr_or_key(freeze_state, "id", None)
    )
    extracted_metadata = _get_attr_or_key(freeze_state, "metadata", {})

    merged_metadata: dict[str, Any] = {}
    if isinstance(extracted_metadata, Mapping):
        merged_metadata.update(copy.deepcopy(dict(extracted_metadata)))
    if metadata:
        merged_metadata.update(copy.deepcopy(metadata))

    resolved_reason = str(
        reason
        if reason is not None
        else extracted_reason
        if extracted_reason is not None
        else ("runtime is frozen; execution denied" if runtime_frozen else "")
    )

    state = RuntimeFreezeState(
        runtime_frozen=bool(runtime_frozen),
        reason=resolved_reason,
        source=str(source if source is not None else extracted_source),
        freeze_id=str(extracted_freeze_id) if extracted_freeze_id else None,
        metadata=merged_metadata,
    )

    if state.freeze_id:
        return state

    if state.runtime_frozen:
        payload = state.to_dict()
        return RuntimeFreezeState(
            runtime_frozen=state.runtime_frozen,
            reason=state.reason,
            source=state.source,
            freeze_id=payload.get("freeze_id"),
            metadata=state.metadata,
            created_at=state.created_at,
        )

    return state


def evaluate_runtime_freeze(
    *,
    freeze_state: Any = None,
    runtime_frozen: bool | None = None,
    action_type: str = "unknown",
    reason: str | None = None,
    source: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> RuntimeFreezeDecision:
    return RuntimeFreezeAuthority().evaluate(
        freeze_state=freeze_state,
        runtime_frozen=runtime_frozen,
        action_type=action_type,
        reason=reason,
        source=source,
        metadata=metadata,
    )


def enforce_runtime_not_frozen(
    *,
    freeze_state: Any = None,
    runtime_frozen: bool | None = None,
    action_type: str = "unknown",
    reason: str | None = None,
    source: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> RuntimeFreezeDecision:
    return RuntimeFreezeAuthority().enforce(
        freeze_state=freeze_state,
        runtime_frozen=runtime_frozen,
        action_type=action_type,
        reason=reason,
        source=source,
        metadata=metadata,
    )


__all__ = [
    "RuntimeExecutionFrozen",
    "RuntimeFreezeAuthority",
    "RuntimeFreezeDecision",
    "RuntimeFreezeState",
    "evaluate_runtime_freeze",
    "enforce_runtime_not_frozen",
    "normalize_runtime_freeze_state",
    "stable_freeze_id",
    "utc_timestamp",
]
