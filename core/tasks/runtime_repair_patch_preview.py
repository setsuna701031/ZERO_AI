from __future__ import annotations

import difflib
from typing import Any, Dict, List, Mapping, Optional


DEFAULT_MAX_PREVIEW_BYTES = 120_000


def build_runtime_repair_patch_preview(
    scope_gate: Any,
    *,
    target_path: Any = "",
    old_text: Any = "",
    new_text: Any = "",
    original_text: Any = None,
    repaired_text: Any = None,
    max_preview_bytes: int = DEFAULT_MAX_PREVIEW_BYTES,
) -> Dict[str, Any]:
    """Build a read-only patch preview from a mutation scope gate.

    This layer never writes files, applies patches, executes commands, schedules
    tasks, or mutates the supplied scope gate. It only produces a unified diff
    preview and metadata for human/operator review.
    """
    safe_gate = scope_gate if isinstance(scope_gate, Mapping) else {}

    scope_allowed = bool(safe_gate.get("scope_allowed", False))
    task_id = _first_nonempty(safe_gate.get("task_id"))
    proposal_id = _first_nonempty(safe_gate.get("proposal_id"))

    resolved_old = _first_text(original_text, old_text)
    resolved_new = _first_text(repaired_text, new_text)
    resolved_path = _resolve_target_path(target_path=target_path, scope_gate=safe_gate)

    blocked_reasons: List[str] = []
    if not scope_allowed:
        blocked_reasons.append("mutation_scope_not_allowed")
    if not resolved_path:
        blocked_reasons.append("target_path_missing")
    if resolved_old == "":
        blocked_reasons.append("old_text_missing")
    if resolved_new == "":
        blocked_reasons.append("new_text_missing")
    if resolved_old == resolved_new and resolved_old != "":
        blocked_reasons.append("no_text_change")

    old_bytes = len(resolved_old.encode("utf-8", errors="replace"))
    new_bytes = len(resolved_new.encode("utf-8", errors="replace"))
    if old_bytes > max_preview_bytes:
        blocked_reasons.append("old_text_too_large_for_preview")
    if new_bytes > max_preview_bytes:
        blocked_reasons.append("new_text_too_large_for_preview")

    preview_allowed = not blocked_reasons

    diff_text = ""
    if preview_allowed:
        diff_text = _build_unified_diff(
            target_path=resolved_path,
            old_text=resolved_old,
            new_text=resolved_new,
        )

    changed_lines = _count_changed_lines(diff_text)
    impacted_files = [resolved_path] if resolved_path else []

    return {
        "ok": True,
        "task_id": task_id,
        "proposal_id": proposal_id,
        "preview_status": "ready" if preview_allowed else "blocked",
        "preview_allowed": preview_allowed,
        "target_path": resolved_path,
        "impacted_files": impacted_files,
        "diff": diff_text,
        "diff_line_count": len(diff_text.splitlines()) if diff_text else 0,
        "added_lines": changed_lines["added"],
        "removed_lines": changed_lines["removed"],
        "old_text_bytes": old_bytes,
        "new_text_bytes": new_bytes,
        "blocked_reasons": _unique(blocked_reasons),
        "mutation_allowed": False,
        "execution_allowed": False,
        "schedule_allowed": False,
        "apply_allowed": False,
        "allowed_next_action": "human_review_patch_preview" if preview_allowed else "inspect_patch_preview_block",
        "human_summary": _build_summary(
            preview_allowed=preview_allowed,
            target_path=resolved_path,
            added=changed_lines["added"],
            removed=changed_lines["removed"],
            blocked_reasons=blocked_reasons,
        ),
        "raw_scope_gate": dict(safe_gate),
    }


def build_runtime_repair_patch_previews(
    scope_gate: Any,
    patch_requests: Any,
    *,
    max_preview_bytes: int = DEFAULT_MAX_PREVIEW_BYTES,
) -> List[Dict[str, Any]]:
    """Build multiple read-only patch previews."""
    if not isinstance(patch_requests, list):
        return [
            build_runtime_repair_patch_preview(
                scope_gate,
                max_preview_bytes=max_preview_bytes,
            )
        ]

    previews: List[Dict[str, Any]] = []
    for item in patch_requests:
        request = item if isinstance(item, Mapping) else {}
        previews.append(
            build_runtime_repair_patch_preview(
                scope_gate,
                target_path=request.get("target_path") or request.get("path") or request.get("file_path"),
                old_text=request.get("old_text") if request.get("old_text") is not None else request.get("original_text"),
                new_text=request.get("new_text") if request.get("new_text") is not None else request.get("repaired_text"),
                max_preview_bytes=max_preview_bytes,
            )
        )
    return previews


def _build_unified_diff(*, target_path: str, old_text: str, new_text: str) -> str:
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)

    diff_lines = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{target_path}",
        tofile=f"b/{target_path}",
        lineterm="",
    )

    normalized: List[str] = []
    for line in diff_lines:
        if line.endswith("\n"):
            normalized.append(line.rstrip("\n"))
        else:
            normalized.append(line)
    return "\n".join(normalized)


def _count_changed_lines(diff_text: str) -> Dict[str, int]:
    added = 0
    removed = 0
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return {"added": added, "removed": removed}


def _resolve_target_path(*, target_path: Any, scope_gate: Mapping[str, Any]) -> str:
    direct = _normalize_path(target_path)
    if direct:
        return direct

    paths = scope_gate.get("target_paths")
    if isinstance(paths, list):
        for item in paths:
            normalized = _normalize_path(item)
            if normalized:
                return normalized

    path_decisions = scope_gate.get("path_decisions")
    if isinstance(path_decisions, list):
        for item in path_decisions:
            if not isinstance(item, Mapping):
                continue
            normalized = _normalize_path(item.get("normalized_path") or item.get("path"))
            if normalized:
                return normalized

    return ""


def _normalize_path(path: Any) -> str:
    text = str(path or "").strip()
    if not text:
        return ""
    text = text.replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")
    if len(text) >= 3 and text[1] == ":" and text[2] == "/":
        text = text[3:]
    if text.startswith("./"):
        text = text[2:]
    while text.startswith("/"):
        text = text[1:]
    return text.strip("/")


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value)
        if text != "":
            return text
    return ""


def _build_summary(
    *,
    preview_allowed: bool,
    target_path: str,
    added: int,
    removed: int,
    blocked_reasons: List[str],
) -> str:
    if preview_allowed:
        return f"Patch preview is ready for {target_path}: +{added} -{removed}. No mutation has been applied."
    return "Patch preview blocked: " + ", ".join(_unique(blocked_reasons))


def _unique(values: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""
