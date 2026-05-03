"""Review lifecycle for controlled repo sandbox edits.

Design rules:
- Review is an approval record, not the source of task execution state.
- Applying a review may copy an already-produced sandbox file back to the repo.
- Rejecting a review must never touch the target file.
- Apply/reject must clear the matching pending review blocker from runtime_state.
- No fallback direct edit is performed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4
import json

from core.runtime.audit_log import AuditLogger


@dataclass
class ReviewRecord:
    review_id: str
    payload: dict[str, Any]
    diff: str = ""
    status: str = "pending_review"
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "payload": self.payload,
            "diff": self.diff,
            "status": self.status,
            "reason": self.reason,
            "file_path": self.payload.get("file_path"),
        }


_REVIEW_STORE: Dict[str, ReviewRecord] = {}


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalize_path(path: str) -> str:
    return str(path or "").replace("\\", "/").lstrip("./")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _runtime_state_path(payload: dict[str, Any]) -> Path | None:
    value = payload.get("runtime_state_file")
    if value:
        return Path(str(value))

    task_dir = payload.get("task_dir")
    if task_dir:
        return Path(str(task_dir)) / "runtime_state.json"

    return None


def _clear_review_runtime_fields(
    payload: dict[str, Any],
    review_id: str,
    resolution_status: str = "resolved",
) -> None:
    """Resolve the matching pending review blocker and clear legacy review fields.

    Blockers are kept as audit/runtime records.  The important part is that
    the matching review blocker is no longer active/pending after apply/reject.
    """
    state_path = _runtime_state_path(payload)
    if state_path is None:
        return

    state = _read_json(state_path)
    if not state:
        return

    blockers = state.get("blockers")
    if isinstance(blockers, list):
        updated_blockers: list[dict[str, Any]] = []
        for item in blockers:
            if not isinstance(item, dict):
                continue

            blocker = dict(item)
            blocker_type = str(blocker.get("type") or "").strip().lower()
            blocker_status = str(blocker.get("status") or "").strip().lower()
            blocker_id = str(
                blocker.get("id")
                or blocker.get("blocker_id")
                or blocker.get("review_id")
                or ""
            ).strip()

            is_pending_review_blocker = (
                blocker_type == "review"
                and blocker_status in {"pending", "pending_review", "active", "waiting"}
                and (not blocker_id or blocker_id == str(review_id))
            )

            if is_pending_review_blocker:
                blocker["status"] = str(resolution_status or "resolved").strip().lower() or "resolved"
                blocker["resolved_at"] = _now_text()
                blocker["resolution_review_id"] = str(review_id)

            updated_blockers.append(blocker)

        state["blockers"] = updated_blockers
    else:
        state["blockers"] = []

    active_blockers = []
    resolved_statuses = {"resolved", "applied", "rejected", "cancelled", "done", "cleared"}
    for item in state.get("blockers", []):
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "").strip().lower() not in resolved_statuses:
            active_blockers.append(item)

    review_blocker = next(
        (item for item in active_blockers if str(item.get("type") or "").strip().lower() == "review"),
        None,
    )

    # Compatibility fields. These mirror blocker state for older call sites.
    state["active_blocker_count"] = len(active_blockers)
    state["requires_review"] = bool(review_blocker)
    state["review_status"] = "pending_review" if review_blocker else ""
    state["review_id"] = str(review_blocker.get("id") or "") if review_blocker else ""
    state["review_payload"] = dict(review_blocker.get("payload") or {}) if review_blocker else {}

    if active_blockers:
        state["status"] = "waiting_review" if review_blocker else "waiting_blocker"
        state["waiting_reason"] = str(active_blockers[0].get("reason") or "")
        state["next_action"] = "wait_for_external_event"
    else:
        state["waiting_reason"] = ""
        state["next_action"] = "run_next_tick"
        if str(state.get("status") or "").strip().lower() in {
            "waiting_review",
            "waiting_blocker",
            "blocked",
            "waiting",
        }:
            state["status"] = "running"

    state["agent_action"] = ""
    state["updated_at"] = _now_text()

    _write_json(state_path, state)


def _find_sandbox_file(repo_root: Path, file_path: str, payload: dict[str, Any]) -> Path | None:
    explicit = payload.get("sandbox_path") or payload.get("sandbox_file") or payload.get("modified_path")
    if explicit:
        candidate = Path(str(explicit))
        if not candidate.is_absolute():
            candidate = repo_root / candidate
        if candidate.exists():
            return candidate

    workspace_root = payload.get("workspace_root")
    if workspace_root:
        candidate = Path(str(workspace_root)) / "repo_sandbox" / _normalize_path(file_path)
        if candidate.exists():
            return candidate

    normalized = _normalize_path(file_path)
    candidates = [
        repo_root / "workspace" / "repo_sandbox" / normalized,
        repo_root / "worktree" / "sandbox" / normalized,
        repo_root / ".sandbox" / normalized,
        repo_root / "sandbox" / normalized,
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None


def create_review(
    review_id: str | dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    diff: str = "",
    *,
    reason: str | None = None,
) -> ReviewRecord:
    """Create a pending review record.

    Supports both:
    - create_review("review-id", payload, diff="...")
    - create_review(payload)
    """
    if isinstance(review_id, dict) and payload is None:
        payload = dict(review_id)
        review_id = None

    resolved_review_id = str(review_id or f"review-{uuid4().hex[:12]}")
    resolved_payload = dict(payload or {})

    record = ReviewRecord(
        review_id=resolved_review_id,
        payload=resolved_payload,
        diff=str(diff or ""),
        status="pending_review",
        reason=reason,
    )
    _REVIEW_STORE[resolved_review_id] = record
    AuditLogger().log_payload_event(
        resolved_payload,
        "review_created",
        {
            "review_id": resolved_review_id,
            "file_path": resolved_payload.get("file_path"),
            "status": record.status,
            "has_diff": bool(str(diff or "")),
            "reason": reason,
        },
        source="review",
    )
    return record


def create_review_from_repo_edit_result(
    result: dict[str, Any],
    *,
    repo_root: str | Path = ".",
    reason: str | None = None,
) -> ReviewRecord:
    review_id = str(result.get("review_id") or f"review-{uuid4().hex[:12]}")
    payload = dict(result.get("payload") or {})

    file_path = payload.get("file_path") or result.get("file_path") or result.get("file")
    payload["file_path"] = file_path
    payload["_repo_root"] = str(repo_root)

    for key in (
        "runtime_state_file",
        "task_dir",
        "task_id",
        "workspace_root",
        "sandbox_path",
        "sandbox_file",
        "modified_path",
    ):
        if result.get(key) is not None:
            payload[key] = result[key]

    return create_review(
        review_id,
        payload,
        diff=str(result.get("diff") or ""),
        reason=reason,
    )


def get_review(review_id: str) -> ReviewRecord | None:
    return _REVIEW_STORE.get(str(review_id))


def load_review(review_id: str) -> ReviewRecord | None:
    return get_review(review_id)


def apply_review(review_id: str) -> dict[str, Any]:
    record = _REVIEW_STORE.get(str(review_id))
    if record is None:
        return {"status": "error", "error": "review not found", "review_id": review_id}

    if record.status not in {"pending_review", "pending"}:
        return {
            "status": "error",
            "error": f"review is not pending: {record.status}",
            "review_id": review_id,
        }

    file_path = record.payload.get("file_path")
    if not file_path:
        return {"status": "error", "error": "missing file_path", "review_id": review_id}

    repo_root = Path(str(record.payload.get("_repo_root") or record.payload.get("repo_root") or ".")).resolve()
    target = repo_root / _normalize_path(str(file_path))

    if not target.exists():
        return {
            "status": "error",
            "error": f"target not found: {file_path}",
            "review_id": review_id,
        }

    sandbox_file = _find_sandbox_file(repo_root, str(file_path), record.payload)
    if sandbox_file is None:
        return {
            "status": "error",
            "error": f"sandbox file missing for: {file_path}",
            "review_id": review_id,
        }

    target.write_text(sandbox_file.read_text(encoding="utf-8"), encoding="utf-8")
    record.status = "applied"

    _clear_review_runtime_fields(record.payload, str(review_id), resolution_status="applied")
    AuditLogger().log_payload_event(
        record.payload,
        "review_applied",
        {
            "review_id": str(review_id),
            "file_path": str(file_path),
            "target": str(target),
            "sandbox_file": str(sandbox_file),
            "status": record.status,
        },
        source="review",
    )

    return {
        "status": "applied",
        "file": str(file_path),
        "review_id": str(review_id),
    }


def reject_review(review_id: str, reason: str | None = None) -> dict[str, Any]:
    record = _REVIEW_STORE.get(str(review_id))
    if record is None:
        return {"status": "error", "error": "review not found", "review_id": review_id}

    if record.status not in {"pending_review", "pending"}:
        return {
            "status": "error",
            "error": f"review is not pending: {record.status}",
            "review_id": review_id,
        }

    record.status = "rejected"
    if reason:
        record.reason = reason

    _clear_review_runtime_fields(record.payload, str(review_id), resolution_status="rejected")
    AuditLogger().log_payload_event(
        record.payload,
        "review_rejected",
        {
            "review_id": str(review_id),
            "reason": record.reason,
            "status": record.status,
        },
        source="review",
    )

    return {
        "status": "rejected",
        "review_id": str(review_id),
        "reason": record.reason,
    }


__all__ = [
    "ReviewRecord",
    "create_review",
    "create_review_from_repo_edit_result",
    "get_review",
    "load_review",
    "apply_review",
    "reject_review",
]
