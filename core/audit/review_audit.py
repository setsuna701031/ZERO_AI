# core/audit/review_audit.py
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_REVIEW_AUDIT_PATH = Path("workspace/audit/review_audit.jsonl")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReviewAuditLog:
    """
    Append-only audit log for operator review governance.

    Purpose:
    - Record review queue reads, approvals, rejections, and errors.
    - Keep audit responsibility outside scheduler/control_api internals.
    - Produce JSONL evidence that can later feed observability/replay layers.
    """

    def __init__(self, path: Path | str = DEFAULT_REVIEW_AUDIT_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        event_type: str,
        ok: bool,
        operator_id: str = "local_operator",
        item_id: Optional[str] = None,
        command: Optional[str] = None,
        action: Optional[str] = None,
        result: Any = None,
        error: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        event = {
            "event_id": str(uuid.uuid4()),
            "timestamp": utc_now_iso(),
            "event_type": str(event_type or "review_event"),
            "ok": bool(ok),
            "operator_id": str(operator_id or "local_operator"),
            "item_id": item_id,
            "command": command,
            "action": action,
            "result": self._json_safe(result),
            "error": self._json_safe(error),
            "metadata": self._json_safe(metadata or {}),
        }

        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

        return event

    def record_queue_read(
        self,
        *,
        ok: bool,
        operator_id: str = "local_operator",
        command: Optional[str] = None,
        result: Any = None,
        error: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.record(
            event_type="review.queue_read",
            ok=ok,
            operator_id=operator_id,
            command=command,
            action="get_review_queue",
            result=result,
            error=error,
            metadata=metadata,
        )

    def record_approval(
        self,
        *,
        item_id: str,
        ok: bool,
        operator_id: str = "local_operator",
        command: Optional[str] = None,
        result: Any = None,
        error: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.record(
            event_type="review.approved",
            ok=ok,
            operator_id=operator_id,
            item_id=item_id,
            command=command,
            action="approve_review_item",
            result=result,
            error=error,
            metadata=metadata,
        )

    def record_rejection(
        self,
        *,
        item_id: str,
        ok: bool,
        operator_id: str = "local_operator",
        command: Optional[str] = None,
        result: Any = None,
        error: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.record(
            event_type="review.rejected",
            ok=ok,
            operator_id=operator_id,
            item_id=item_id,
            command=command,
            action="reject_review_item",
            result=result,
            error=error,
            metadata=metadata,
        )

    def tail(self, limit: int = 20) -> list[Dict[str, Any]]:
        if not self.path.exists():
            return []

        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 20

        limit = max(1, limit)

        lines = self.path.read_text(encoding="utf-8", errors="ignore").splitlines()
        selected = lines[-limit:]

        events: list[Dict[str, Any]] = []
        for line in selected:
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                parsed = {
                    "event_type": "review.audit_corrupt_line",
                    "raw": line,
                }
            events.append(parsed)

        return events

    def _json_safe(self, value: Any) -> Any:
        try:
            json.dumps(value, ensure_ascii=False)
            return value
        except TypeError:
            return repr(value)


def record_review_audit_event(
    *,
    event_type: str,
    ok: bool,
    operator_id: str = "local_operator",
    item_id: Optional[str] = None,
    command: Optional[str] = None,
    action: Optional[str] = None,
    result: Any = None,
    error: Any = None,
    metadata: Optional[Dict[str, Any]] = None,
    path: Path | str = DEFAULT_REVIEW_AUDIT_PATH,
) -> Dict[str, Any]:
    return ReviewAuditLog(path=path).record(
        event_type=event_type,
        ok=ok,
        operator_id=operator_id,
        item_id=item_id,
        command=command,
        action=action,
        result=result,
        error=error,
        metadata=metadata,
    )