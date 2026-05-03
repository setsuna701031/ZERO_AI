"""Strict review and apply flow for controlled repo sandbox edits.

Safety boundary:
- repo_edit writes only to workspace/repo_sandbox/worktree/...
- review records a pending decision and never touches the original repo file
- apply_review copies the sandbox worktree file back to the original repo file only after explicit approval
- reject_review never touches the original repo file
- if the sandbox file is missing, apply_review returns error; it does not reconstruct edits from payload
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import json
import uuid

REVIEW_STATUS_PENDING = "pending_review"
REVIEW_STATUS_APPLIED = "applied"
REVIEW_STATUS_REJECTED = "rejected"
REVIEW_STATUS_BLOCKED = "blocked"
REVIEW_STATUS_ERROR = "error"


@dataclass(frozen=True)
class RepoEditReview:
    review_id: str
    status: str
    file_path: str
    sandbox_path: str
    diff: str
    reason: str = ""
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if data["metadata"] is None:
            data["metadata"] = {}
        return data


def _repo_root(repo_root: str | Path = ".") -> Path:
    return Path(repo_root).resolve()


def _review_dir(repo_root: str | Path = ".") -> Path:
    path = _repo_root(repo_root) / "workspace" / "repo_sandbox_reviews"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _normalize_relative_path(path: str | Path) -> str:
    raw = str(path).strip().strip("'\"`").replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]
    return raw


def _is_blocked_apply_path(path: str) -> bool:
    lowered = path.lower().replace("\\", "/")
    blocked_parts = [
        ".git",
        "__pycache__",
        ".env",
        "venv/",
        ".venv/",
        "site-packages",
        "token",
        "secret",
        "password",
        "credential",
        "key",
    ]
    return any(part in lowered for part in blocked_parts)


def _safe_repo_file(file_path: str | Path, repo_root: str | Path = ".") -> Path:
    root = _repo_root(repo_root)
    normalized = _normalize_relative_path(file_path)

    candidate = Path(normalized)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (root / normalized).resolve()

    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"refusing to apply outside repo root: {resolved}") from exc

    if _is_blocked_apply_path(relative.as_posix()):
        raise ValueError(f"refusing to apply blocked path: {relative.as_posix()}")

    return resolved


def _default_sandbox_path(file_path: str | Path, repo_root: str | Path = ".") -> Path:
    root = _repo_root(repo_root)
    normalized = _normalize_relative_path(file_path)
    return (root / "workspace" / "repo_sandbox" / "worktree" / normalized).resolve()


def _extract_sandbox_path(result: dict[str, Any], file_path: str, repo_root: str | Path = ".") -> str:
    for key in ("sandbox_path", "sandbox_file", "edited_path", "modified_path"):
        value = result.get(key)
        if value:
            candidate = Path(str(value))
            if not candidate.is_absolute():
                candidate = _repo_root(repo_root) / candidate
            return str(candidate.resolve())

    return str(_default_sandbox_path(file_path, repo_root))


def save_review(review: RepoEditReview, *, repo_root: str | Path = ".") -> Path:
    path = _review_dir(repo_root) / f"{review.review_id}.json"
    path.write_text(json.dumps(review.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_review(review_id: str, *, repo_root: str | Path = ".") -> RepoEditReview:
    path = _review_dir(repo_root) / f"{review_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return RepoEditReview(
        review_id=data["review_id"],
        status=data["status"],
        file_path=data["file_path"],
        sandbox_path=data.get("sandbox_path", ""),
        diff=data.get("diff", ""),
        reason=data.get("reason", ""),
        metadata=data.get("metadata") or {},
    )


def create_review_from_repo_edit_result(
    result: dict[str, Any],
    *,
    repo_root: str | Path = ".",
    reason: str = "",
) -> RepoEditReview:
    status = result.get("status")
    file_path = _normalize_relative_path(result.get("file_path") or result.get("file") or "")

    if status != "success":
        review = RepoEditReview(
            review_id=str(uuid.uuid4()),
            status=REVIEW_STATUS_BLOCKED if status == "blocked" else REVIEW_STATUS_ERROR,
            file_path=file_path,
            sandbox_path="",
            diff=str(result.get("diff") or ""),
            reason=reason or str(result.get("error") or result.get("reason") or status or "repo edit did not succeed"),
            metadata={"source_result": result},
        )
        save_review(review, repo_root=repo_root)
        return review

    if not file_path:
        review = RepoEditReview(
            review_id=str(uuid.uuid4()),
            status=REVIEW_STATUS_ERROR,
            file_path="",
            sandbox_path="",
            diff=str(result.get("diff") or ""),
            reason="repo_edit result did not include file path",
            metadata={"source_result": result},
        )
        save_review(review, repo_root=repo_root)
        return review

    review = RepoEditReview(
        review_id=str(uuid.uuid4()),
        status=REVIEW_STATUS_PENDING,
        file_path=file_path,
        sandbox_path=_extract_sandbox_path(result, file_path, repo_root),
        diff=str(result.get("diff") or ""),
        reason=reason or "pending human review",
        metadata={"source_result": result},
    )
    save_review(review, repo_root=repo_root)
    return review


def reject_review(review_id: str, *, repo_root: str | Path = ".", reason: str = "rejected by user") -> dict[str, Any]:
    review = load_review(review_id, repo_root=repo_root)
    rejected = RepoEditReview(
        review_id=review.review_id,
        status=REVIEW_STATUS_REJECTED,
        file_path=review.file_path,
        sandbox_path=review.sandbox_path,
        diff=review.diff,
        reason=reason,
        metadata=review.metadata or {},
    )
    save_review(rejected, repo_root=repo_root)
    return {
        "status": REVIEW_STATUS_REJECTED,
        "review_id": review_id,
        "file_path": review.file_path,
        "reason": reason,
    }


def apply_review(review_id: str, *, repo_root: str | Path = ".") -> dict[str, Any]:
    review = load_review(review_id, repo_root=repo_root)

    if review.status != REVIEW_STATUS_PENDING:
        return {
            "status": REVIEW_STATUS_BLOCKED,
            "review_id": review_id,
            "reason": f"review is not pending: {review.status}",
        }

    if not review.sandbox_path:
        return {
            "status": REVIEW_STATUS_ERROR,
            "review_id": review_id,
            "reason": "review does not include sandbox_path; cannot apply safely",
        }

    sandbox_file = Path(review.sandbox_path).resolve()
    if not sandbox_file.exists():
        return {
            "status": REVIEW_STATUS_ERROR,
            "review_id": review_id,
            "reason": f"sandbox file not found: {sandbox_file}",
        }

    try:
        target_file = _safe_repo_file(review.file_path, repo_root)
    except ValueError as exc:
        return {
            "status": REVIEW_STATUS_BLOCKED,
            "review_id": review_id,
            "file_path": review.file_path,
            "reason": str(exc),
        }

    target_file.parent.mkdir(parents=True, exist_ok=True)
    before = target_file.read_text(encoding="utf-8") if target_file.exists() else ""
    after = sandbox_file.read_text(encoding="utf-8")
    target_file.write_text(after, encoding="utf-8")

    applied = RepoEditReview(
        review_id=review.review_id,
        status=REVIEW_STATUS_APPLIED,
        file_path=review.file_path,
        sandbox_path=review.sandbox_path,
        diff=review.diff,
        reason="applied after explicit review decision",
        metadata={
            **(review.metadata or {}),
            "before_size": len(before),
            "after_size": len(after),
        },
    )
    save_review(applied, repo_root=repo_root)

    return {
        "status": REVIEW_STATUS_APPLIED,
        "review_id": review_id,
        "file_path": review.file_path,
        "applied_path": str(target_file),
    }


__all__ = [
    "RepoEditReview",
    "REVIEW_STATUS_PENDING",
    "REVIEW_STATUS_APPLIED",
    "REVIEW_STATUS_REJECTED",
    "REVIEW_STATUS_BLOCKED",
    "REVIEW_STATUS_ERROR",
    "create_review_from_repo_edit_result",
    "save_review",
    "load_review",
    "reject_review",
    "apply_review",
]
