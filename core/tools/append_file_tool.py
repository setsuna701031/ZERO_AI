from __future__ import annotations

import os
from typing import Any, Dict


class AppendFileTool:
    """
    ZERO File Tool v1 - safe append-only workspace file tool.

    Boundary:
    - This tool only appends UTF-8 text.
    - It does not overwrite existing content.
    - It only allows paths under workspace/shared.
    - It returns a normalized observation payload for audit/trace usage.
    """

    def __init__(self, workspace_root: str = "workspace") -> None:
        self.workspace_root = os.path.abspath(str(workspace_root or "workspace"))
        self.shared_root = os.path.abspath(os.path.join(self.workspace_root, "shared"))
        os.makedirs(self.shared_root, exist_ok=True)

    def execute(self, tool_input: Dict[str, Any] | None = None) -> Dict[str, Any]:
        payload = tool_input if isinstance(tool_input, dict) else {}
        raw_path = str(payload.get("path") or "").strip()
        content = payload.get("content")
        create_if_missing = bool(payload.get("create_if_missing", True))
        ensure_trailing_newline = bool(payload.get("ensure_trailing_newline", False))

        if not raw_path:
            return self._blocked("append_file requires path", raw_path=raw_path)

        if content is None:
            content = ""
        if not isinstance(content, str):
            content = str(content)
        if ensure_trailing_newline and content and not content.endswith("\n"):
            content += "\n"

        resolved = self._resolve_shared_path(raw_path)
        if not resolved.get("ok"):
            return self._blocked(str(resolved.get("error") or "path rejected"), raw_path=raw_path)

        path = str(resolved["path"])
        parent = os.path.dirname(path)

        if os.path.exists(path) and os.path.isdir(path):
            return self._failed("append_file target is a directory", raw_path=raw_path, resolved_path=path)

        if not os.path.exists(path) and not create_if_missing:
            return self._failed("append_file target does not exist and create_if_missing is false", raw_path=raw_path, resolved_path=path)

        try:
            os.makedirs(parent, exist_ok=True)
            before_size = os.path.getsize(path) if os.path.exists(path) else 0
            with open(path, "a", encoding="utf-8", newline="") as f:
                f.write(content)
            after_size = os.path.getsize(path) if os.path.exists(path) else before_size
        except Exception as exc:
            return self._failed(str(exc), raw_path=raw_path, resolved_path=path)

        rel_path = os.path.relpath(path, self.workspace_root).replace("\\", "/")
        return {
            "status": "success",
            "ok": True,
            "path": rel_path,
            "resolved_path": path,
            "bytes_before": before_size,
            "bytes_after": after_size,
            "bytes_appended": max(0, after_size - before_size),
            "chars_appended": len(content),
            "created": before_size == 0 and after_size >= 0,
            "side_effect_level": "workspace_write",
            "observation": {
                "type": "file_appended",
                "summary": f"appended {len(content)} chars to {rel_path}",
                "data": {
                    "path": rel_path,
                    "bytes_appended": max(0, after_size - before_size),
                    "chars_appended": len(content),
                },
            },
        }

    def run(self, tool_input: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return self.execute(tool_input)

    def invoke(self, tool_input: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return self.execute(tool_input)

    def _resolve_shared_path(self, raw_path: str) -> Dict[str, Any]:
        text = str(raw_path or "").strip().strip('"').strip("'")
        normalized = text.replace("\\", "/")

        if not normalized:
            return {"ok": False, "error": "empty path"}

        if os.path.isabs(text):
            candidate = os.path.abspath(text)
        elif normalized.startswith("workspace/shared/"):
            rel = normalized[len("workspace/shared/"):].strip("/")
            candidate = os.path.abspath(os.path.join(self.shared_root, rel))
        elif normalized.startswith("shared/"):
            rel = normalized[len("shared/"):].strip("/")
            candidate = os.path.abspath(os.path.join(self.shared_root, rel))
        else:
            return {
                "ok": False,
                "error": "append_file only allows paths under workspace/shared",
            }

        if not self._is_under_shared(candidate):
            return {
                "ok": False,
                "error": f"append_file path outside workspace/shared: {candidate}",
            }

        return {"ok": True, "path": candidate}

    def _is_under_shared(self, path: str) -> bool:
        try:
            common = os.path.commonpath([self.shared_root, os.path.abspath(path)])
            return common == self.shared_root
        except Exception:
            return False

    def _blocked(self, message: str, **extra: Any) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "status": "blocked",
            "ok": False,
            "error": str(message or "append_file blocked"),
            "side_effect_level": "none",
            "observation": {
                "type": "tool_error",
                "summary": str(message or "append_file blocked"),
                "data": {},
            },
        }
        payload.update(extra)
        return payload

    def _failed(self, message: str, **extra: Any) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "status": "failed",
            "ok": False,
            "error": str(message or "append_file failed"),
            "side_effect_level": "none",
            "observation": {
                "type": "tool_error",
                "summary": str(message or "append_file failed"),
                "data": {},
            },
        }
        payload.update(extra)
        return payload
