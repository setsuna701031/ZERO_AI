from __future__ import annotations

import hashlib
import os
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from core.engineering.repository_analysis_common import (AdmittedRepositoryRoot, EXCLUDED_DIRECTORIES,
    MAX_ENTRIES, MAX_HASH_BYTES, MAX_PREVIEW_BYTES, artifact, linked, relative_path_valid, validate_artifact)
from core.engineering.repository_root_admission import validate_repository_root_admission

SCHEMA = "zero.engineering.repository_snapshot.v1"; ID_KEY = "repository_snapshot_id"; PREFIX = "engineering-repository-snapshot-"
SENSITIVE = (".env", ".env.*", "*.pem", "*.key", "id_rsa*", "credentials*", "secrets*", "token*")


def _sensitive(name: str) -> bool:
    low = name.lower()
    return any(fnmatch(low, pattern) for pattern in SENSITIVE)


def build_repository_snapshot(admission: AdmittedRepositoryRoot, *, max_entries: int = MAX_ENTRIES,
                              max_hash_bytes: int = MAX_HASH_BYTES, max_preview_bytes: int = MAX_PREVIEW_BYTES) -> dict[str, Any]:
    source = admission.artifact
    common = {**linked(source, "root_admission", "repository_root_admission_id")}
    limits = {"max_entries": max(0, min(int(max_entries), MAX_ENTRIES)),
              "max_hash_bytes": max(0, min(int(max_hash_bytes), MAX_HASH_BYTES)),
              "max_preview_bytes": max(0, min(int(max_preview_bytes), MAX_PREVIEW_BYTES))}
    if not validate_repository_root_admission(source).valid or source.get("status") != "admitted" or admission.root is None:
        return artifact(SCHEMA, "rejected", {**common, "entries": [], "exclusions": sorted(EXCLUDED_DIRECTORIES),
            "limits": limits, "truncated": False, "warnings": ["repository_root_not_admitted"]}, ID_KEY, PREFIX)
    root = admission.root
    entries: list[dict[str, Any]] = []
    excluded: set[str] = set()
    warnings: set[str] = set()
    truncated = False
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        kept = []
        for dirname in sorted(dirnames):
            target = current_path / dirname
            rel = target.relative_to(root).as_posix()
            if dirname.lower() in EXCLUDED_DIRECTORIES:
                excluded.add(rel); continue
            if target.is_symlink():
                entries.append(_symlink_entry(root, target)); continue
            kept.append(dirname)
        dirnames[:] = kept
        if current_path != root:
            entries.append({"relative_path": current_path.relative_to(root).as_posix(), "entry_kind": "directory",
                            "size_bytes": 0, "sha256": None, "text_kind": "not_applicable", "read_status": "metadata_only"})
        for filename in sorted(filenames):
            path = current_path / filename
            entries.append(_file_entry(root, path, limits, warnings))
        if len(entries) >= limits["max_entries"]:
            truncated = True; break
    entries = sorted(entries, key=lambda item: item["relative_path"])[:limits["max_entries"]]
    status = "partial" if truncated or warnings else "captured"
    return artifact(SCHEMA, status, {**common, "entries": entries, "exclusions": sorted(excluded), "limits": limits,
                    "truncated": truncated, "warnings": sorted(warnings)}, ID_KEY, PREFIX)


def _symlink_entry(root: Path, path: Path) -> dict[str, Any]:
    rel = path.relative_to(root).as_posix(); status = "symlink_not_followed"
    try:
        path.resolve(strict=True).relative_to(root); status = "symlink_within_root_not_followed"
    except (OSError, RuntimeError, ValueError):
        status = "symlink_escape_or_unavailable"
    return {"relative_path": rel, "entry_kind": "symlink", "size_bytes": 0, "sha256": None,
            "text_kind": "not_applicable", "read_status": status}


def _file_entry(root: Path, path: Path, limits: dict[str, int], warnings: set[str]) -> dict[str, Any]:
    rel = path.relative_to(root).as_posix()
    if path.is_symlink(): return _symlink_entry(root, path)
    try: size = path.stat().st_size
    except OSError:
        warnings.add("unreadable_entry_present")
        return {"relative_path": rel, "entry_kind": "file", "size_bytes": 0, "sha256": None,
                "text_kind": "unknown", "read_status": "unreadable"}
    base = {"relative_path": rel, "entry_kind": "file", "size_bytes": size}
    if _sensitive(path.name):
        return {**base, "sha256": None, "text_kind": "sensitive", "read_status": "metadata_only", "sensitive_entry_present": True}
    if size > limits["max_hash_bytes"]:
        return {**base, "sha256": None, "text_kind": "oversized", "read_status": "oversized_metadata_only"}
    try: data = path.read_bytes()
    except OSError:
        warnings.add("unreadable_entry_present")
        return {**base, "sha256": None, "text_kind": "unknown", "read_status": "unreadable"}
    digest = hashlib.sha256(data).hexdigest()
    if b"\x00" in data:
        return {**base, "sha256": digest, "text_kind": "binary", "read_status": "hashed"}
    try: text = data.decode("utf-8")
    except UnicodeDecodeError:
        return {**base, "sha256": digest, "text_kind": "binary", "read_status": "hashed"}
    preview = data[:limits["max_preview_bytes"]]
    return {**base, "sha256": digest, "text_kind": "utf-8", "read_status": "read_bounded",
            "line_count": len(text.splitlines()), "bounded_preview_fingerprint": hashlib.sha256(preview).hexdigest()}


def validate_repository_snapshot(value: Any, source_admission: Any = None):
    fields = {"source_root_admission_id", "source_root_admission_fingerprint", "entries", "exclusions", "limits", "truncated", "warnings"}
    result = validate_artifact(value, schema=SCHEMA, statuses={"captured", "partial", "rejected", "invalid"}, id_key=ID_KEY, prefix=PREFIX, fields=fields)
    errors = list(result.errors)
    if isinstance(value, dict):
        entries = value.get("entries")
        if not isinstance(entries, list) or entries != sorted(entries, key=lambda x: x.get("relative_path", "")) or any(not relative_path_valid(x.get("relative_path")) for x in entries if isinstance(x, dict)):
            errors.append("invalid_entries")
        if source_admission is not None and (value.get("source_root_admission_id") != source_admission.get("repository_root_admission_id") or value.get("source_root_admission_fingerprint") != source_admission.get("fingerprint")):
            errors.append("source_admission_mismatch")
    from core.engineering.repository_analysis_common import ValidationResult
    return ValidationResult(not errors, tuple(dict.fromkeys(errors)))


__all__ = ["SCHEMA", "build_repository_snapshot", "validate_repository_snapshot"]
