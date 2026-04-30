from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


APPROVAL_SCHEMA = "approval_record.v1"
DEFAULT_OUTBOX_DIR = "workspace/github_outbox"
DEFAULT_APPROVAL_FILE = "approval_record.json"
DEFAULT_REJECTION_FILE = "rejection_record.json"
OUTBOX_ARTIFACT_NAMES = ("commit_message.txt", "pr_description.md")


def list_outbox_artifacts(*, workspace_root: Any = ".") -> Dict[str, Any]:
    root = Path(workspace_root).resolve(strict=False)
    outbox_dir = (root / DEFAULT_OUTBOX_DIR).resolve(strict=False)
    if not _is_relative_to(outbox_dir, root):
        return _error("outbox path escapes workspace root")

    artifacts = [
        _artifact_record(outbox_dir / name, root=root)
        for name in OUTBOX_ARTIFACT_NAMES
    ]
    return {
        "ok": True,
        "outbox_dir": _logical_path(outbox_dir, root=root),
        "outbox_path": str(outbox_dir),
        "artifacts": artifacts,
        "missing": [item["name"] for item in artifacts if not item["exists"]],
        "git_commit": False,
        "git_push": False,
        "github_create_pr": False,
    }


def write_approval_record(
    *,
    decision: str,
    workspace_root: Any = ".",
    task_id: str = "",
    trace_path: str = "",
    source: str = "approve_outbox_cli",
) -> Dict[str, Any]:
    normalized_decision = _normalize_decision(decision)
    if normalized_decision not in {"approved", "rejected"}:
        return _error("decision must be approved or rejected")

    root = Path(workspace_root).resolve(strict=False)
    outbox_dir = (root / DEFAULT_OUTBOX_DIR).resolve(strict=False)
    if not _is_relative_to(outbox_dir, root):
        return _error("outbox path escapes workspace root")

    listed = list_outbox_artifacts(workspace_root=root)
    if not listed.get("ok"):
        return listed

    artifacts = listed.get("artifacts", [])
    missing = listed.get("missing", [])
    if missing:
        return _error(f"missing required outbox artifacts: {', '.join(missing)}")

    output_name = DEFAULT_APPROVAL_FILE if normalized_decision == "approved" else DEFAULT_REJECTION_FILE
    output_path = outbox_dir / output_name
    approved = normalized_decision == "approved"
    record = {
        "schema": APPROVAL_SCHEMA,
        "source": str(source or "approve_outbox_cli"),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "decision": normalized_decision,
        "approved": approved,
        "replay_source": {
            "task_id": str(task_id or ""),
            "trace_path": str(trace_path or ""),
            "outbox_dir": _logical_path(outbox_dir, root=root),
        },
        "artifacts": artifacts,
        "safety": {
            "git_commit": False,
            "git_push": False,
            "github_create_pr": False,
            "mutation_attempt": 0,
        },
        "notes": "Dry-run approval record only; no commit, push, GitHub API call, or PR creation was executed.",
    }

    try:
        outbox_dir.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        return _error(str(exc))

    return {
        "ok": True,
        "decision": normalized_decision,
        "approved": approved,
        "record_path": str(output_path),
        "record_logical_path": _logical_path(output_path, root=root),
        "record": record,
        "changed_files": [str(output_path)],
        "git_commit": False,
        "git_push": False,
        "github_create_pr": False,
    }


def _normalize_decision(value: str) -> str:
    text = str(value or "").strip().lower()
    if text in {"yes", "y", "approve", "approved"}:
        return "approved"
    if text in {"no", "n", "reject", "rejected"}:
        return "rejected"
    return text


def _artifact_record(path: Path, *, root: Path) -> Dict[str, Any]:
    exists = path.exists() and path.is_file()
    return {
        "name": path.name,
        "path": _logical_path(path, root=root),
        "full_path": str(path),
        "exists": exists,
        "size_bytes": path.stat().st_size if exists else None,
        "sha256_12": _sha256_12(path) if exists else "",
    }


def _sha256_12(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()[:12]


def _logical_path(path: Path, *, root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(base.resolve(strict=False))
        return True
    except ValueError:
        return False


def _error(message: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "error": str(message or "approval_record_error"),
        "changed_files": [],
        "git_commit": False,
        "git_push": False,
        "github_create_pr": False,
    }
