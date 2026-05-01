from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from core.runtime.execution_session import ExecutionSession


SESSION_DIR = "execution_sessions"


class ExecutionSessionStore:
    def __init__(self, workspace_dir: str = "workspace") -> None:
        self.workspace_dir = Path(workspace_dir).resolve(strict=False)
        if self.workspace_dir.name != "workspace":
            self.workspace_dir = self.workspace_dir / "workspace"
        self.session_dir = self.workspace_dir / SESSION_DIR

    def save_session(self, session: ExecutionSession) -> Path:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        path = self.session_dir / f"{session.session_id}.json"
        path.write_text(
            json.dumps(session.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path

    def load_session(self, session_id: str) -> Dict[str, Any] | None:
        session_key = str(session_id or "").strip()
        if not session_key:
            return None
        path = self.session_dir / f"{session_key}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        if not self.session_dir.exists():
            return []
        files = sorted(
            self.session_dir.glob("*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        sessions: List[Dict[str, Any]] = []
        for path in files[: max(0, int(limit))]:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, dict):
                sessions.append(data)
        return sessions
