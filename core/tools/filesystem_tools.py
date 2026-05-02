from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


SENSITIVE_PARTS = {".git", ".env", "__pycache__"}
MAX_READ_CHARS = 200_000
MAX_LIST_ITEMS = 200


class ReadFileTool:
    name = "read_file"

    def __init__(self, workspace_root: Any = "workspace") -> None:
        self.workspace_root = _resolve_workspace_root(workspace_root)
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def execute(self, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
        payload = args if isinstance(args, dict) else {}
        try:
            target = _resolve_safe_path(self.workspace_root, payload.get("path"))
        except ValueError as exc:
            return _result(False, "blocked", self.name, error=str(exc))

        if not target.exists():
            return _result(False, "failed", self.name, path=target, error="file_not_found")
        if not target.is_file():
            return _result(False, "failed", self.name, path=target, error="not_a_file")

        content = target.read_text(encoding="utf-8", errors="replace")
        truncated = len(content) > MAX_READ_CHARS
        if truncated:
            content = content[:MAX_READ_CHARS]
        return _result(
            True,
            "success",
            self.name,
            path=target,
            content=content,
            truncated=truncated,
            observation={
                "type": "file_content",
                "summary": f"read {len(content)} chars from {target.relative_to(self.workspace_root).as_posix()}",
                "data": {
                    "path": target.relative_to(self.workspace_root).as_posix(),
                    "content": content,
                    "truncated": truncated,
                },
            },
            summary=f"read {len(content)} chars",
        )

    def run(self, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return self.execute(args)

    def invoke(self, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return self.execute(args)


class WriteFileTool:
    name = "write_file"

    def __init__(self, workspace_root: Any = "workspace") -> None:
        self.workspace_root = _resolve_workspace_root(workspace_root)
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def execute(self, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
        payload = args if isinstance(args, dict) else {}
        try:
            target = _resolve_safe_path(self.workspace_root, payload.get("path"))
        except ValueError as exc:
            return _result(False, "blocked", self.name, error=str(exc))

        allow_overwrite = bool(payload.get("allow_overwrite", False))
        if target.exists() and not allow_overwrite:
            return _result(False, "blocked", self.name, path=target, error="overwrite_requires_explicit_allow_overwrite")
        if target.exists() and not target.is_file():
            return _result(False, "blocked", self.name, path=target, error="target_is_not_a_file")

        content = "" if payload.get("content") is None else str(payload.get("content"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        relative = target.relative_to(self.workspace_root).as_posix()
        return _result(
            True,
            "success",
            self.name,
            path=target,
            changed_files=[str(target)],
            bytes_written=len(content.encode("utf-8")),
            chars_written=len(content),
            observation={
                "type": "file_write",
                "summary": f"wrote {len(content)} chars to {relative}",
                "data": {
                    "path": relative,
                    "chars_written": len(content),
                    "bytes_written": len(content.encode("utf-8")),
                },
            },
            summary=f"wrote {len(content)} chars",
        )

    def run(self, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return self.execute(args)

    def invoke(self, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return self.execute(args)


class ListDirTool:
    name = "list_dir"

    def __init__(self, workspace_root: Any = "workspace") -> None:
        self.workspace_root = _resolve_workspace_root(workspace_root)
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def execute(self, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
        payload = args if isinstance(args, dict) else {}
        try:
            target = _resolve_safe_path(self.workspace_root, payload.get("path") or ".")
        except ValueError as exc:
            return _result(False, "blocked", self.name, error=str(exc))

        if not target.exists():
            return _result(False, "failed", self.name, path=target, error="path_not_found")
        if not target.is_dir():
            return _result(False, "failed", self.name, path=target, error="not_a_directory")

        recursive = bool(payload.get("recursive", False))
        iterator = target.rglob("*") if recursive else target.iterdir()
        items = []
        for path in iterator:
            if _has_sensitive_part(path):
                continue
            rel = path.relative_to(self.workspace_root).as_posix()
            items.append(
                {
                    "name": path.name,
                    "path": rel,
                    "is_file": path.is_file(),
                    "is_dir": path.is_dir(),
                    "size": path.stat().st_size if path.is_file() else 0,
                }
            )
            if len(items) >= MAX_LIST_ITEMS:
                break

        items = sorted(items, key=lambda item: item["path"])
        relative = target.relative_to(self.workspace_root).as_posix() if target != self.workspace_root else "."
        return _result(
            True,
            "success",
            self.name,
            path=target,
            items=items,
            count=len(items),
            truncated=len(items) >= MAX_LIST_ITEMS,
            observation={
                "type": "directory_listing",
                "summary": f"listed {len(items)} item(s) under {relative}",
                "data": {
                    "path": relative,
                    "items": items,
                    "truncated": len(items) >= MAX_LIST_ITEMS,
                },
            },
            summary=f"listed {len(items)} item(s)",
        )

    def run(self, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return self.execute(args)

    def invoke(self, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return self.execute(args)


def _resolve_workspace_root(value: Any) -> Path:
    path = Path(str(value or "workspace")).resolve(strict=False)
    if path.name != "workspace":
        path = path / "workspace"
    return path


def _resolve_safe_path(workspace_root: Path, value: Any) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("path is required")
    normalized = raw.replace("\\", "/").lstrip("/")
    if normalized.startswith("workspace/"):
        normalized = normalized[len("workspace/") :]
    parts = [part for part in normalized.split("/") if part]
    if any(part == ".." for part in parts):
        raise ValueError("parent traversal is not allowed")
    if any(part in SENSITIVE_PARTS or part.startswith(".env") for part in parts):
        raise ValueError("sensitive path is not allowed")
    target = (workspace_root / normalized).resolve(strict=False)
    try:
        target.relative_to(workspace_root)
    except ValueError as exc:
        raise ValueError("path escapes workspace") from exc
    return target


def _has_sensitive_part(path: Path) -> bool:
    return any(part in SENSITIVE_PARTS or part.startswith(".env") for part in path.parts)


def _result(
    ok: bool,
    status: str,
    tool: str,
    *,
    path: Path | None = None,
    error: str | None = None,
    changed_files: list[str] | None = None,
    summary: str = "",
    observation: Dict[str, Any] | None = None,
    **extra: Any,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "ok": bool(ok),
        "status": status,
        "tool": tool,
        "tool_class": "workspace_write" if tool == "write_file" else "read_only",
        "side_effect_level": "workspace_write" if tool == "write_file" and ok else "read_only",
        "path": "" if path is None else str(path),
        "summary": summary,
        "observation": observation or {
            "type": "tool_error" if not ok else "tool_result",
            "summary": error or summary,
            "data": {},
        },
        "changed_files": changed_files or [],
        "error": error,
        "git_commit": False,
        "git_push": False,
        "github_create_pr": False,
    }
    payload.update(extra)
    return payload
