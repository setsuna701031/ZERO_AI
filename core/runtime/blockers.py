"""Generic blocker helpers for ZERO runtime states.

A blocker is a small, serializable record that tells the loop why a task
must wait for an external decision or event. Review approval is one blocker
kind, not a special case in the loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

RESOLVED_BLOCKER_STATUSES = {
    "resolved",
    "applied",
    "rejected",
    "cancelled",
    "done",
    "cleared",
}


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass(frozen=True)
class RuntimeBlocker:
    type: str
    id: str
    status: str = "pending"
    reason: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now_text)
    resolved_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": str(self.type or "generic").strip().lower() or "generic",
            "id": str(self.id or "").strip(),
            "status": str(self.status or "pending").strip().lower() or "pending",
            "reason": str(self.reason or "").strip(),
            "payload": dict(self.payload or {}),
            "created_at": str(self.created_at or now_text()),
            "resolved_at": str(self.resolved_at or ""),
        }


def make_review_blocker(review_id: str, *, reason: str = "pending review", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return RuntimeBlocker(
        type="review",
        id=str(review_id or "").strip(),
        status="pending",
        reason=reason or "pending review",
        payload=dict(payload or {}),
    ).to_dict()


def normalize_blockers(blockers: Any) -> list[dict[str, Any]]:
    if not isinstance(blockers, list):
        return []

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(blockers, start=1):
        if isinstance(item, RuntimeBlocker):
            data = item.to_dict()
        elif isinstance(item, dict):
            data = dict(item)
        else:
            continue

        blocker_type = str(data.get("type") or "generic").strip().lower() or "generic"
        blocker_id = str(data.get("id") or data.get("blocker_id") or f"{blocker_type}_{index}").strip()
        payload = data.get("payload")
        if not isinstance(payload, dict):
            payload = {}

        normalized.append(
            {
                "type": blocker_type,
                "id": blocker_id,
                "status": str(data.get("status") or "pending").strip().lower() or "pending",
                "reason": str(data.get("reason") or "").strip(),
                "payload": payload,
                "created_at": str(data.get("created_at") or now_text()),
                "resolved_at": str(data.get("resolved_at") or ""),
            }
        )

    return normalized


def active_blockers(blockers: Any) -> list[dict[str, Any]]:
    return [
        item
        for item in normalize_blockers(blockers)
        if str(item.get("status") or "") not in RESOLVED_BLOCKER_STATUSES
    ]


def has_active_blockers(runtime_state: dict[str, Any] | None) -> bool:
    if not isinstance(runtime_state, dict):
        return False
    return bool(active_blockers(runtime_state.get("blockers", [])))


def first_active_blocker(runtime_state: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(runtime_state, dict):
        return None
    active = active_blockers(runtime_state.get("blockers", []))
    return active[0] if active else None


__all__ = [
    "RuntimeBlocker",
    "RESOLVED_BLOCKER_STATUSES",
    "make_review_blocker",
    "normalize_blockers",
    "active_blockers",
    "has_active_blockers",
    "first_active_blocker",
]
