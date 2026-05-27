from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class RepoFileSignal:
    path: str
    kind: str
    score: int = 0
    reasons: tuple[str, ...] = ()
    size_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        return payload


@dataclass(frozen=True)
class RepoContextSnapshot:
    snapshot_id: str
    repo_root: str
    task_intent: str = ""
    file_signals: tuple[RepoFileSignal, ...] = ()
    selected_files: tuple[str, ...] = ()
    test_files: tuple[str, ...] = ()
    runtime_files: tuple[str, ...] = ()
    recent_failure_files: tuple[str, ...] = ()
    created_at: str = ""
    normalized_digest: str = ""
    read_only: bool = True
    authoritative: bool = False
    mutation_attempted: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["file_signals"] = [item.to_dict() for item in self.file_signals]
        for key in ("selected_files", "test_files", "runtime_files", "recent_failure_files"):
            payload[key] = list(getattr(self, key))
        return payload


def scan_repo_files(repo_root: str | Path, *, max_files: int = 500) -> tuple[str, ...]:
    root = Path(repo_root).resolve()
    if not root.exists() or not root.is_dir():
        return ()
    ignored = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", "node_modules", ".venv", "venv", ".test_tmp"}
    files: list[str] = []
    for path in sorted(root.rglob("*"), key=lambda item: str(item).lower()):
        if len(files) >= max_files:
            break
        if any(part in ignored for part in path.parts):
            continue
        if path.is_file():
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                continue
            files.append(rel)
    return tuple(files)


def rank_repo_files_for_task(repo_root: str | Path, task_intent: str, *, files: Any = None, max_files: int = 20) -> tuple[RepoFileSignal, ...]:
    root = Path(repo_root).resolve()
    file_names = tuple(files) if files is not None else scan_repo_files(root)
    tokens = _tokens(task_intent)
    signals: list[RepoFileSignal] = []
    for rel in file_names:
        path = str(rel)
        lowered = path.lower()
        reasons: list[str] = []
        score = 0
        if lowered.startswith("core/runtime/") or lowered.startswith("core/operator/"):
            score += 4
            reasons.append("runtime_or_operator")
        if lowered.startswith("tests/"):
            score += 3
            reasons.append("test_file")
        for token in tokens:
            if token and token in lowered:
                score += 2
                reasons.append(f"intent:{token}")
        if "operator" in tokens and "operator" in lowered:
            score += 4
        if lowered.endswith(".py"):
            score += 1
        size = 0
        try:
            size = (root / path).stat().st_size
        except OSError:
            pass
        signals.append(RepoFileSignal(path=path, kind=_kind_for_path(path), score=score, reasons=tuple(dict.fromkeys(reasons)), size_bytes=size))
    ranked = sorted(signals, key=lambda item: (-item.score, item.path))[: max(1, int(max_files or 1))]
    return tuple(ranked)


def collect_test_files(repo_root: str | Path, *, files: Any = None) -> tuple[str, ...]:
    values = tuple(files) if files is not None else scan_repo_files(repo_root)
    return tuple(path for path in values if str(path).startswith("tests/") and str(path).endswith(".py"))


def collect_runtime_files(repo_root: str | Path, *, files: Any = None) -> tuple[str, ...]:
    values = tuple(files) if files is not None else scan_repo_files(repo_root)
    return tuple(path for path in values if str(path).startswith("core/runtime/") and str(path).endswith(".py"))


def collect_recent_failure_files(repo_root: str | Path, failures: Any = None, *, files: Any = None) -> tuple[str, ...]:
    values = tuple(files) if files is not None else scan_repo_files(repo_root)
    text = " ".join(str(item) for item in _iter_any(failures)).lower()
    if not text:
        return ()
    selected = [path for path in values if str(path).lower() in text or Path(str(path)).name.lower() in text]
    return tuple(dict.fromkeys(selected))


def build_repo_context_snapshot(
    repo_root: str | Path,
    *,
    task_intent: str = "",
    recent_failures: Any = None,
    max_files: int = 500,
    select_limit: int = 20,
) -> RepoContextSnapshot:
    root = Path(repo_root).resolve()
    files = scan_repo_files(root, max_files=max_files)
    signals = rank_repo_files_for_task(root, task_intent, files=files, max_files=select_limit)
    test_files = collect_test_files(root, files=files)
    runtime_files = collect_runtime_files(root, files=files)
    recent_failure_files = collect_recent_failure_files(root, recent_failures, files=files)
    selected = tuple(dict.fromkeys([*(item.path for item in signals if item.score > 0), *recent_failure_files]))[:select_limit]
    base = {
        "repo_root": str(root),
        "task_intent": str(task_intent or ""),
        "file_signals": [item.to_dict() for item in signals],
        "selected_files": list(selected),
        "test_files": list(test_files),
        "runtime_files": list(runtime_files),
        "recent_failure_files": list(recent_failure_files),
        "read_only": True,
        "authoritative": False,
        "mutation_attempted": False,
    }
    digest = _digest(base)
    return RepoContextSnapshot(
        snapshot_id="repo_context:" + digest[:16],
        repo_root=str(root),
        task_intent=str(task_intent or ""),
        file_signals=signals,
        selected_files=selected,
        test_files=test_files,
        runtime_files=runtime_files,
        recent_failure_files=recent_failure_files,
        normalized_digest=digest,
    )


def normalize_repo_context_snapshot(snapshot: RepoContextSnapshot | Mapping[str, Any]) -> dict[str, Any]:
    payload = snapshot.to_dict() if isinstance(snapshot, RepoContextSnapshot) else copy.deepcopy(dict(snapshot))
    return _normalize_value(payload)


def _kind_for_path(path: str) -> str:
    if path.startswith("tests/"):
        return "test"
    if path.startswith("core/runtime/"):
        return "runtime"
    if path.startswith("core/operator/"):
        return "operator"
    return "source" if path.endswith(".py") else "artifact"


def _tokens(text: str) -> tuple[str, ...]:
    raw = "".join(ch.lower() if ch.isalnum() or ch in {"_", "-"} else " " for ch in str(text or ""))
    return tuple(token for token in raw.replace("-", "_").split() if len(token) >= 3)


def _iter_any(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, Mapping)):
        return [value]
    try:
        return list(value)
    except TypeError:
        return [value]


def _normalize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalize_value(value[key]) for key in sorted(value) if key not in {"created_at", "updated_at", "timestamp"}}
    if isinstance(value, (list, tuple)):
        return [_normalize_value(item) for item in value]
    return copy.deepcopy(value)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(_normalize_value(value), sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
