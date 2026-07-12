from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


RUNTIME_WORKSPACE_OBSERVER_SCHEMA = "zero.runtime.workspace_observer.v1"
_EVIDENCE_KEYS = (
    "git_commit_actuator_record_path",
    "governed_commit_record_path",
    "rollback_evidence_path",
    "result_path",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _nested_values(value: Any, key: str) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, Mapping):
        if key in value:
            found.append(value[key])
        for child in value.values():
            if isinstance(child, (Mapping, list, tuple)):
                found.extend(_nested_values(child, key))
    elif isinstance(value, (list, tuple)):
        for child in value:
            if isinstance(child, (Mapping, list, tuple)):
                found.extend(_nested_values(child, key))
    return found


def _first(value: Mapping[str, Any], key: str, default: Any = None) -> Any:
    values = _nested_values(value, key)
    return values[0] if values else default


def _safe_candidate(
    workspace_root: Path, value: Any, *, allow_absolute: bool
) -> tuple[Path | None, str]:
    text = _text(value)
    if not text:
        return None, "empty_path"
    candidate = Path(text)
    if candidate.is_absolute() and not allow_absolute:
        return None, "absolute_path_denied"
    try:
        root = workspace_root.resolve(strict=True)
        resolved = (
            candidate.resolve(strict=False)
            if candidate.is_absolute()
            else (root / candidate).resolve(strict=False)
        )
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return None, "path_outside_workspace"
    return resolved, ""


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _observe_file(
    root: Path, value: Any, max_file_bytes: int
) -> tuple[dict[str, Any], str]:
    path_text = _text(value)
    path, issue = _safe_candidate(root, value, allow_absolute=False)
    base = {
        "path": path_text,
        "exists": False,
        "is_file": False,
        "size_bytes": 0,
        "readable": False,
        "content_hash_sha256": "",
        "text_preview": "",
        "preview_truncated": False,
        "observation_status": "denied_invalid_path" if issue else "missing",
    }
    if issue or path is None:
        return base, f"{issue}:{path_text}"
    try:
        base["exists"] = path.exists()
        base["is_file"] = path.is_file()
        if not base["exists"]:
            return base, f"missing:{path_text}"
        if not base["is_file"]:
            base["observation_status"] = "not_file"
            return base, f"not_file:{path_text}"
        size = path.stat().st_size
        base["size_bytes"] = size
        if size > max_file_bytes:
            base["readable"] = True
            base["preview_truncated"] = True
            base["observation_status"] = "oversized"
            return base, f"oversized:{path_text}"
        data = path.read_bytes()
        base["readable"] = True
        base["content_hash_sha256"] = sha256(data).hexdigest()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            base["observation_status"] = "binary"
            return base, ""
        preview_limit = min(max_file_bytes, 4096)
        base["text_preview"] = text[:preview_limit]
        base["preview_truncated"] = len(text) > preview_limit
        base["observation_status"] = "observed"
        return base, ""
    except (OSError, RuntimeError) as exc:
        base["observation_status"] = "unreadable"
        return base, f"unreadable:{path_text}:{type(exc).__name__}"


def _observe_evidence(
    root: Path, evidence_type: str, value: Any, max_file_bytes: int
) -> tuple[dict[str, Any], str]:
    path_text = _text(value)
    path, issue = _safe_candidate(root, value, allow_absolute=True)
    observation = {
        "evidence_type": evidence_type,
        "path": path_text,
        "exists": False,
        "readable": False,
        "size_bytes": 0,
        "content_hash_sha256": "",
        "parsed_json": None,
        "parse_error": "",
    }
    if issue or path is None:
        observation["parse_error"] = issue
        return observation, f"evidence_{issue}:{path_text}"
    try:
        observation["exists"] = path.is_file()
        if not observation["exists"]:
            return observation, f"evidence_missing:{path_text}"
        size = path.stat().st_size
        observation["size_bytes"] = size
        if size > max_file_bytes:
            observation["parse_error"] = "evidence_oversized"
            return observation, f"evidence_oversized:{path_text}"
        data = path.read_bytes()
        observation["readable"] = True
        observation["content_hash_sha256"] = sha256(data).hexdigest()
        try:
            observation["parsed_json"] = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            observation["parse_error"] = type(exc).__name__
            return observation, f"evidence_parse_error:{path_text}"
        return observation, ""
    except (OSError, RuntimeError) as exc:
        observation["parse_error"] = type(exc).__name__
        return observation, f"evidence_unreadable:{path_text}"


def _runner_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    payload = _mapping(result)
    changed = _first(payload, "changed_files", [])
    changed_files = (
        [_text(item) for item in changed if _text(item)]
        if isinstance(changed, (list, tuple))
        else []
    )
    task_completed = (
        payload.get("task_completed") is True
        if "task_completed" in payload
        else payload.get("ok") is True
    )
    return {
        "runner_ok": payload.get("ok") is True,
        "task_completed": task_completed,
        "changed_files": changed_files,
        "denial_reason": _text(_first(payload, "denial_reason", "")),
        "validation_passed": _first(payload, "validation_passed") is True,
        "rollback_required": _first(payload, "rollback_required") is True,
        "rollback_completed": _first(payload, "rollback_completed") is True,
        "activity_recorded": _first(payload, "activity_recorded") is True,
        "execution_real": _first(payload, "execution_real") is True,
        "controlled": _first(payload, "controlled") is True,
    }


@dataclass(frozen=True)
class RuntimeWorkspaceObserver:
    workspace_root: str | Path = "."
    max_file_bytes: int = 262144

    def _observe(
        self,
        *,
        goal: Any,
        task_id: Any,
        changed_files: Sequence[Any] | None,
        runner_result: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        root = Path(self.workspace_root)
        base = {
            "schema": RUNTIME_WORKSPACE_OBSERVER_SCHEMA,
            "ok": True,
            "observer_status": "observed",
            "goal": _text(goal),
            "task_id": _text(task_id),
            "workspace_root": str(root),
            "changed_files_received": 0,
            "file_observations": [],
            "evidence_observations": [],
            "runner_summary": _runner_summary(_mapping(runner_result)),
            "issues": [],
            "read_only": True,
            "mutation_allowed": False,
            "repair_allowed": False,
            "decision_authority": False,
            "requested_changes_modified": False,
            "observed_at": _utc_now(),
            "observation_complete": True,
        }
        if not isinstance(self.max_file_bytes, int) or self.max_file_bytes <= 0:
            base.update(ok=False, observer_status="denied_invalid_configuration")
            base["issues"] = ["max_file_bytes_must_be_greater_than_zero"]
            return base
        try:
            if not root.resolve(strict=True).is_dir():
                raise NotADirectoryError(str(root))
        except (OSError, RuntimeError) as exc:
            base.update(ok=False, observer_status="denied_invalid_configuration")
            base["issues"] = [f"invalid_workspace_root:{type(exc).__name__}"]
            return base

        files = deepcopy(list(changed_files or []))
        base["changed_files_received"] = len(files)
        invalid_path = False
        for value in files:
            observation, issue = _observe_file(root, value, self.max_file_bytes)
            base["file_observations"].append(observation)
            if issue:
                base["issues"].append(issue)
            invalid_path = invalid_path or observation["observation_status"] == "denied_invalid_path"

        payload = _mapping(runner_result)
        seen: set[tuple[str, str]] = set()
        for evidence_type in _EVIDENCE_KEYS:
            for value in _nested_values(payload, evidence_type):
                key = (evidence_type, _text(value))
                if not key[1] or key in seen:
                    continue
                seen.add(key)
                observation, issue = _observe_evidence(
                    root, evidence_type, value, self.max_file_bytes
                )
                base["evidence_observations"].append(observation)
                if issue:
                    base["issues"].append(issue)

        if invalid_path:
            base.update(ok=False, observer_status="denied_invalid_path")
        elif not files and not base["evidence_observations"]:
            base["observer_status"] = "no_changes"
        elif base["issues"]:
            base["observer_status"] = "observed_with_issues"
        return base

    def observe(
        self,
        *,
        goal: Any,
        task_id: Any,
        changed_files: Sequence[Any] | None,
        runner_result: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        try:
            return self._observe(
                goal=goal,
                task_id=task_id,
                changed_files=changed_files,
                runner_result=runner_result,
            )
        except Exception as exc:
            return {
                "schema": RUNTIME_WORKSPACE_OBSERVER_SCHEMA,
                "ok": False,
                "observer_status": "observer_error",
                "goal": _text(goal),
                "task_id": _text(task_id),
                "workspace_root": str(self.workspace_root),
                "changed_files_received": 0,
                "file_observations": [],
                "evidence_observations": [],
                "runner_summary": {},
                "issues": [f"observer_error:{type(exc).__name__}"],
                "read_only": True,
                "mutation_allowed": False,
                "repair_allowed": False,
                "decision_authority": False,
                "requested_changes_modified": False,
                "observed_at": _utc_now(),
                "observation_complete": True,
            }


__all__ = [
    "RUNTIME_WORKSPACE_OBSERVER_SCHEMA",
    "RuntimeWorkspaceObserver",
]
