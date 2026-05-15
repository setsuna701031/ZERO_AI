# core/audit/review_execution_link.py
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_REVIEW_EXECUTION_LINK_PATH = Path("workspace/audit/review_execution_links.jsonl")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReviewExecutionLinkLog:
    """
    Append-only link log between operator review decisions and actual execution evidence.

    Purpose:
    - Connect review_item_id to execution/mutation/rollback/trace identifiers.
    - Keep provenance outside scheduler and agent_loop.
    - Produce replay-friendly JSONL evidence for AER governance.
    """

    def __init__(self, path: Path | str = DEFAULT_REVIEW_EXECUTION_LINK_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record_link(
        self,
        *,
        review_item_id: str,
        decision: str,
        ok: bool,
        operator_id: str = "local_operator",
        execution_id: Optional[str] = None,
        mutation_id: Optional[str] = None,
        rollback_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        applied_files: Optional[List[str]] = None,
        command: Optional[str] = None,
        result: Any = None,
        error: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        event = {
            "link_id": str(uuid.uuid4()),
            "timestamp": utc_now_iso(),
            "event_type": "review.execution_link",
            "ok": bool(ok),
            "operator_id": str(operator_id or "local_operator"),
            "review_item_id": str(review_item_id or ""),
            "decision": str(decision or ""),
            "execution_id": execution_id,
            "mutation_id": mutation_id,
            "rollback_id": rollback_id,
            "trace_id": trace_id,
            "applied_files": list(applied_files or []),
            "command": command,
            "result": self._json_safe(result),
            "error": self._json_safe(error),
            "metadata": self._json_safe(metadata or {}),
        }

        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

        return event

    def tail(self, limit: int = 20) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []

        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 20

        limit = max(1, limit)

        lines = self.path.read_text(encoding="utf-8", errors="ignore").splitlines()
        selected = lines[-limit:]

        events: List[Dict[str, Any]] = []
        for line in selected:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                events.append(
                    {
                        "event_type": "review.execution_link_corrupt_line",
                        "raw": line,
                    }
                )

        return events

    def find_by_review_item_id(self, review_item_id: str) -> List[Dict[str, Any]]:
        target = str(review_item_id or "")
        if not target or not self.path.exists():
            return []

        matches: List[Dict[str, Any]] = []

        for line in self.path.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if str(event.get("review_item_id") or "") == target:
                matches.append(event)

        return matches

    def _json_safe(self, value: Any) -> Any:
        try:
            json.dumps(value, ensure_ascii=False)
            return value
        except TypeError:
            return repr(value)


def record_review_execution_link(
    *,
    review_item_id: str,
    decision: str,
    ok: bool,
    operator_id: str = "local_operator",
    execution_id: Optional[str] = None,
    mutation_id: Optional[str] = None,
    rollback_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    applied_files: Optional[List[str]] = None,
    command: Optional[str] = None,
    result: Any = None,
    error: Any = None,
    metadata: Optional[Dict[str, Any]] = None,
    path: Path | str = DEFAULT_REVIEW_EXECUTION_LINK_PATH,
) -> Dict[str, Any]:
    return ReviewExecutionLinkLog(path=path).record_link(
        review_item_id=review_item_id,
        decision=decision,
        ok=ok,
        operator_id=operator_id,
        execution_id=execution_id,
        mutation_id=mutation_id,
        rollback_id=rollback_id,
        trace_id=trace_id,
        applied_files=applied_files,
        command=command,
        result=result,
        error=error,
        metadata=metadata,
    )