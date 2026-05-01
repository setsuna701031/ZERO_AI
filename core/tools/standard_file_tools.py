from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


SENSITIVE_PARTS = {".git", ".env", "__pycache__"}


class WorkspaceFileTool:
    def __init__(self, action: str, workspace_dir: str = "workspace") -> None:
        self.action = action
        self.workspace_dir = _resolve_workspace_dir(workspace_dir)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

    def execute(self, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
        payload = args if isinstance(args, dict) else {}
        path_value = payload.get("path", "")
        try:
            target = _resolve_safe_path(self.workspace_dir, path_value)
        except ValueError as exc:
            return _result(
                ok=False,
                status="blocked",
                action=self.action,
                path=str(path_value or ""),
                error=str(exc),
            )

        if self.action == "file_read":
            return self._read(target)
        if self.action == "file_write":
            return self._write(target, payload.get("content", ""))
        if self.action == "file_exists":
            return self._exists(target)
        if self.action == "list_files":
            return self._list(target, recursive=bool(payload.get("recursive", False)))

        return _result(
            ok=False,
            status="invalid_tool",
            action=self.action,
            path=str(path_value or ""),
            error=f"unsupported file action: {self.action}",
        )

    def run(self, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return self.execute(args)

    def invoke(self, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return self.execute(args)

    def _read(self, target: Path) -> Dict[str, Any]:
        if not target.exists():
            return _result(False, "failed", self.action, target, error="file_not_found")
        if not target.is_file():
            return _result(False, "failed", self.action, target, error="not_a_file")
        text = target.read_text(encoding="utf-8", errors="replace")
        return _result(
            True,
            "success",
            self.action,
            target,
            content=text,
            summary=f"read {len(text)} chars",
        )

    def _write(self, target: Path, content: Any) -> Dict[str, Any]:
        text = "" if content is None else str(content)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return _result(
            True,
            "success",
            self.action,
            target,
            bytes_written=len(text.encode("utf-8")),
            chars_written=len(text),
            changed_files=[str(target)],
            summary=f"wrote {len(text)} chars",
        )

    def _exists(self, target: Path) -> Dict[str, Any]:
        return _result(
            True,
            "success",
            self.action,
            target,
            exists=target.exists(),
            is_file=target.is_file(),
            is_dir=target.is_dir(),
            summary="checked path",
        )

    def _list(self, target: Path, *, recursive: bool) -> Dict[str, Any]:
        if not target.exists():
            return _result(False, "failed", self.action, target, error="path_not_found")
        if not target.is_dir():
            return _result(False, "failed", self.action, target, error="not_a_directory")

        iterator = target.rglob("*") if recursive else target.iterdir()
        files = [
            str(path.relative_to(self.workspace_dir).as_posix())
            for path in iterator
            if path.is_file() and not _has_sensitive_part(path)
        ]
        return _result(
            True,
            "success",
            self.action,
            target,
            files=sorted(files)[:200],
            truncated=len(files) > 200,
            summary=f"listed {min(len(files), 200)} files",
        )


class ReservedToolAdapter:
    def __init__(self, name: str) -> None:
        self.name = name

    def execute(self, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
        _ = args
        return {
            "ok": False,
            "status": "blocked",
            "tool": self.name,
            "summary": f"{self.name} adapter is reserved but not enabled",
            "error": "reserved_tool_not_enabled",
            "git_commit": False,
            "git_push": False,
            "github_create_pr": False,
        }


def _resolve_workspace_dir(workspace_dir: str) -> Path:
    path = Path(workspace_dir).resolve(strict=False)
    if path.name != "workspace":
        path = path / "workspace"
    return path


def _resolve_safe_path(workspace_dir: Path, path_value: Any) -> Path:
    raw = str(path_value or "").strip()
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
    target = (workspace_dir / normalized).resolve(strict=False)
    try:
        target.relative_to(workspace_dir)
    except ValueError as exc:
        raise ValueError("path escapes workspace") from exc
    return target


def _has_sensitive_part(path: Path) -> bool:
    return any(part in SENSITIVE_PARTS or part.startswith(".env") for part in path.parts)


def _result(
    ok: bool,
    status: str,
    action: str,
    path: Any,
    *,
    error: str | None = None,
    summary: str = "",
    changed_files: list[str] | None = None,
    **extra: Any,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "ok": bool(ok),
        "status": status,
        "tool": action,
        "path": str(path),
        "summary": summary,
        "error": error,
        "changed_files": changed_files or [],
        "git_commit": False,
        "git_push": False,
        "github_create_pr": False,
    }
    payload.update(extra)
    return payload
