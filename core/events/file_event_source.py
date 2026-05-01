from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from core.events.event_schema import EventRecord


SUPPORTED_SUFFIXES = {".txt", ".md", ".json"}


class FileEventSource:
    def __init__(self, workspace_dir: str = "workspace") -> None:
        self.workspace_dir = _resolve_workspace_dir(workspace_dir)
        self.inbox_dir = self.workspace_dir / "events_inbox"
        self.outbox_dir = self.workspace_dir / "events_outbox"
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        (self.inbox_dir / ".gitkeep").touch()
        (self.outbox_dir / ".gitkeep").touch()

    def poll_once(self) -> List[EventRecord]:
        events: List[EventRecord] = []
        for path in sorted(self.inbox_dir.iterdir()):
            if not path.is_file() or path.name == ".gitkeep":
                continue
            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            events.append(
                EventRecord(
                    event_id=str(uuid4()),
                    event_type="file_created_or_seen",
                    source="file_event_source",
                    path=str(path.resolve(strict=False)),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    payload=self._payload_for_file(path),
                )
            )
        return events

    def poll_once_dicts(self) -> List[Dict[str, Any]]:
        return [asdict(event) for event in self.poll_once()]

    def _payload_for_file(self, path: Path) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "filename": path.name,
            "suffix": path.suffix.lower(),
            "size_bytes": path.stat().st_size,
        }
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            payload["read_error"] = str(exc)
            return payload

        payload["text_preview"] = _preview(text)
        if path.suffix.lower() == ".json":
            try:
                parsed = json.loads(text)
            except Exception as exc:
                payload["json_error"] = str(exc)
            else:
                payload["json_summary"] = _json_summary(parsed)
        return payload


def _resolve_workspace_dir(workspace_dir: str) -> Path:
    path = Path(workspace_dir).resolve(strict=False)
    if path.name != "workspace":
        path = path / "workspace"
    return path


def _preview(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if len(normalized) <= 200:
        return normalized
    return f"{normalized[:200]}... <truncated len={len(normalized)}>"


def _json_summary(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return {"type": "dict", "keys": sorted(str(key) for key in value.keys())[:20]}
    if isinstance(value, list):
        return {"type": "list", "items": len(value)}
    return {"type": type(value).__name__}
