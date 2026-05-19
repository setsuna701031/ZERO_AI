from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from core.runtime.execution_session import ExecutionSession
from core.runtime.runtime_persistence_service import RuntimePersistenceService


SESSION_DIR = "execution_sessions"


class ExecutionSessionStore:
    def __init__(self, workspace_dir: str = "workspace") -> None:
        self.workspace_dir = Path(workspace_dir).resolve(strict=False)
        if self.workspace_dir.name != "workspace":
            self.workspace_dir = self.workspace_dir / "workspace"
        self.session_dir = self.workspace_dir / SESSION_DIR
        self.persistence = RuntimePersistenceService(workspace_root=self.workspace_dir)

    def save_session(self, session: ExecutionSession) -> Path:
        path = self.session_dir / f"{session.session_id}.json"
        self.persistence.write_json(
            path,
            session.to_dict(),
            reason="execution_session_store_save",
            lineage={
                "caller": "execution_session_store",
                "artifact_type": "execution_session",
                "session_id": session.session_id,
            },
            provenance={
                "caller": "execution_session_store",
                "artifact_type": "execution_session",
            },
            metadata={
                "caller": "execution_session_store",
                "artifact_type": "execution_session",
                "engineering_runtime_continuity": True,
            },
        )
        return path

    def load_session(self, session_id: str) -> Dict[str, Any] | None:
        session_key = str(session_id or "").strip()
        if not session_key:
            return None
        path = self.session_dir / f"{session_key}.json"
        if not path.exists():
            return None
        payload = self.persistence.read_json(path, None)
        return payload if isinstance(payload, dict) else None

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
            data = self.persistence.read_json(path, None)
            if isinstance(data, dict):
                sessions.append(data)
        return sessions
