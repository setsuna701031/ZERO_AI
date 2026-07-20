from __future__ import annotations

import posixpath
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from core.engineering.repository_analysis_common import MAX_ENTRIES, relative_path_valid


@dataclass(frozen=True)
class ScopedRepositoryScope:
    normalized_scope: tuple[str, ...]
    existing_files: tuple[str, ...]
    existing_directories: tuple[str, ...]
    proposed_missing_targets: tuple[str, ...]
    fingerprint_material: dict[str, Any]


def explicit_scope_values(runtime_request: Mapping[str, Any], payload: Mapping[str, Any] | None = None) -> list[str] | None:
    values: list[str] = []
    scope_requested = False
    for source in (runtime_request, payload or {}):
        for key in ("target_paths", "analysis_roots", "allowed_repository_paths"):
            raw = source.get(key) if isinstance(source, Mapping) else None
            if raw is not None:
                scope_requested = True
            if isinstance(raw, str):
                values.append(raw)
            elif isinstance(raw, list):
                values.extend(item for item in raw if isinstance(item, str))
        raw_scope = source.get("scope_constraints") if isinstance(source, Mapping) else None
        if raw_scope is not None:
            scope_requested = True
        if isinstance(raw_scope, list):
            values.extend(item for item in raw_scope if isinstance(item, str) and _looks_like_path(item))
    target = (payload or {}).get("formal_target_path") if isinstance(payload, Mapping) else None
    if target is not None:
        scope_requested = True
    if isinstance(target, str):
        values.append(target)
    return values if scope_requested else None


def normalize_scoped_repository_scope(repository_root: Path, requested_paths: Iterable[str]) -> ScopedRepositoryScope:
    root = repository_root.resolve(strict=True)
    raw = list(dict.fromkeys(requested_paths))
    if not raw:
        raise ValueError("scoped_analysis_empty_scope")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw:
        rel = _normalize_relative(item)
        if rel in seen:
            raise ValueError("scoped_analysis_duplicate_path")
        seen.add(rel)
        normalized.append(rel)
    files: set[str] = set()
    dirs: set[str] = set()
    missing: set[str] = set()
    for rel in sorted(normalized):
        path = root / rel
        if path.exists() or path.is_symlink():
            if path.is_symlink():
                raise ValueError("scoped_analysis_symlink_rejected")
            resolved = path.resolve(strict=True)
            _require_inside(root, resolved, "scoped_analysis_path_escape")
            if path.is_dir():
                dirs.add(rel)
            elif path.is_file():
                files.add(rel)
            else:
                raise ValueError("scoped_analysis_unsupported_path")
        else:
            parent_rel = PurePosixPath(rel).parent.as_posix()
            if parent_rel == ".":
                parent_rel = ""
            parent = root if not parent_rel else root / parent_rel
            if not parent.exists() or not parent.is_dir():
                raise ValueError("scoped_analysis_missing_parent")
            _require_inside(root, parent.resolve(strict=True), "scoped_analysis_parent_escape")
            if parent.is_symlink():
                raise ValueError("scoped_analysis_symlink_rejected")
            missing.add(rel)
            if parent_rel:
                dirs.add(parent_rel)
    if len(files) + len(dirs) + len(missing) > MAX_ENTRIES:
        raise ValueError("scoped_analysis_scope_exceeds_snapshot_limit")
    ordered = tuple(sorted(normalized))
    return ScopedRepositoryScope(
        normalized_scope=ordered,
        existing_files=tuple(sorted(files)),
        existing_directories=tuple(sorted(dirs)),
        proposed_missing_targets=tuple(sorted(missing)),
        fingerprint_material={
            "scoped_analysis_enabled": True,
            "normalized_scope": list(ordered),
            "proposed_missing_targets": sorted(missing),
        },
    )


def _normalize_relative(value: str) -> str:
    text = str(value)
    if not text.strip() or text != text.strip():
        raise ValueError("scoped_analysis_invalid_path")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        raise ValueError("scoped_analysis_control_character")
    if "\\" in text or "\x00" in text:
        raise ValueError("scoped_analysis_invalid_path")
    if Path(text).is_absolute() or (len(text) >= 2 and text[1] == ":"):
        raise ValueError("scoped_analysis_absolute_path")
    rel = posixpath.normpath(text)
    if rel in ("", ".") or rel.startswith("../") or rel == "..":
        raise ValueError("scoped_analysis_traversal")
    if not relative_path_valid(rel):
        raise ValueError("scoped_analysis_invalid_path")
    return rel


def _require_inside(root: Path, path: Path, reason: str) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(reason) from exc


def _looks_like_path(value: str) -> bool:
    return "/" in value or "." in PurePosixPath(value).name


__all__ = ["ScopedRepositoryScope", "explicit_scope_values", "normalize_scoped_repository_scope"]
