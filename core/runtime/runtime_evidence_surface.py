from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Mapping

from core.runtime.runtime_evidence_registry import normalize_evidence_type


INDEX_SCHEMA = "runtime_evidence_index_v1"


def register_evidence(
    task_id: str,
    evidence_type: str,
    path: str | Path,
    metadata: Mapping[str, Any] | None = None,
    *,
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    """Register an evidence artifact in the task evidence index.

    The evidence surface is indexing-only: it records artifact metadata and does
    not execute repairs, load runtime authority, or decide task outcome.
    """
    root = _repo_root(repo_root)
    index_path = _evidence_index_path(repo_root=root, task_id=task_id)
    index = load_evidence_index(task_id, repo_root=root)

    item = {
        "task_id": _safe_text(task_id),
        "evidence_type": normalize_evidence_type(evidence_type),
        "path": str(path),
        "metadata": _metadata_dict(metadata),
    }

    evidence = _evidence_items(index)
    replaced = False
    for offset, existing in enumerate(evidence):
        if (
            existing.get("evidence_type") == item["evidence_type"]
            and existing.get("path") == item["path"]
        ):
            evidence[offset] = item
            replaced = True
            break

    if not replaced:
        evidence.append(item)

    index = {
        "schema": INDEX_SCHEMA,
        "task_id": _safe_text(task_id),
        "evidence_count": len(evidence),
        "evidence": evidence,
    }

    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps(index, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return copy.deepcopy(index)


def list_evidence(
    task_id: str,
    *,
    repo_root: Path | str | None = None,
) -> list[dict[str, Any]]:
    """List registered evidence items for a task."""
    return _evidence_items(load_evidence_index(task_id, repo_root=repo_root))


def load_evidence_index(
    task_id: str,
    *,
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    """Load the evidence index for a task, returning an empty index if missing."""
    root = _repo_root(repo_root)
    index_path = _evidence_index_path(repo_root=root, task_id=task_id)

    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return _empty_index(task_id)

    if not isinstance(data, Mapping):
        return _empty_index(task_id)

    evidence = _evidence_items(data)
    return {
        "schema": _safe_text(data.get("schema")) or INDEX_SCHEMA,
        "task_id": _safe_text(data.get("task_id")) or _safe_text(task_id),
        "evidence_count": int(data.get("evidence_count") or len(evidence)),
        "evidence": evidence,
    }


def evidence_index_path(
    task_id: str,
    *,
    repo_root: Path | str | None = None,
) -> Path:
    """Return the stable on-disk evidence index path for a task."""
    return _evidence_index_path(repo_root=_repo_root(repo_root), task_id=task_id)


def _evidence_index_path(*, repo_root: Path, task_id: str) -> Path:
    safe_task_id = _safe_filename(task_id) or "task"
    return (
        repo_root
        / "workspace"
        / "evidence"
        / "index"
        / f"{safe_task_id}_evidence_index.json"
    )


def _empty_index(task_id: str) -> dict[str, Any]:
    return {
        "schema": INDEX_SCHEMA,
        "task_id": _safe_text(task_id),
        "evidence_count": 0,
        "evidence": [],
    }


def _evidence_items(index: Any) -> list[dict[str, Any]]:
    if not isinstance(index, Mapping):
        return []
    raw_items = index.get("evidence")
    if not isinstance(raw_items, list):
        return []

    items: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        items.append(
            {
                "task_id": _safe_text(item.get("task_id")),
                "evidence_type": normalize_evidence_type(_safe_text(item.get("evidence_type"))),
                "path": _safe_text(item.get("path")),
                "metadata": _metadata_dict(item.get("metadata")),
            }
        )
    return items


def _metadata_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return copy.deepcopy(dict(value))


def _repo_root(value: Path | str | None) -> Path:
    if value is None:
        return Path.cwd().resolve()
    return Path(value).resolve()


def _safe_filename(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text)
    return text.strip("._-")[:120]


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
