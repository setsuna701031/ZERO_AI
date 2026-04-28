# core/world/world_state.py

from __future__ import annotations

import copy
import json
import os
import threading
from datetime import datetime
from typing import Any, Dict


WORLD_STATE_PATH = "workspace/world_state.json"


class WorldState:
    def __init__(self, path: str = WORLD_STATE_PATH) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._state: Dict[str, Any] = {
            "last_update": None,
            "data": {},
        }
        self._load_locked()

    def _load_locked(self) -> None:
        if not os.path.exists(self.path):
            return

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = json.load(f)

            if isinstance(loaded, dict):
                if not isinstance(loaded.get("data"), dict):
                    loaded["data"] = {}
                if "last_update" not in loaded:
                    loaded["last_update"] = None
                self._state = loaded
        except Exception:
            pass

    def _save_locked(self) -> None:
        folder = os.path.dirname(self.path)
        if folder:
            os.makedirs(folder, exist_ok=True)

        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, ensure_ascii=False)

    def update(self, source: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not source or not str(source).strip():
            raise ValueError("source is required")

        if not isinstance(payload, dict):
            raise TypeError("payload must be a dict")

        with self._lock:
            self._load_locked()
            data = self._state.get("data")
            if not isinstance(data, dict):
                data = {}
                self._state["data"] = data

            self._state["last_update"] = datetime.utcnow().isoformat()
            data[str(source).strip()] = copy.deepcopy(payload)
            self._save_locked()
            return copy.deepcopy(self._state)

    def get(self, *, reload: bool = True) -> Dict[str, Any]:
        with self._lock:
            if reload:
                self._load_locked()
            return copy.deepcopy(self._state)

    def clear_source(self, source: str) -> Dict[str, Any]:
        with self._lock:
            self._load_locked()
            data = self._state.get("data")
            if not isinstance(data, dict):
                data = {}
                self._state["data"] = data

            data.pop(str(source).strip(), None)
            self._state["last_update"] = datetime.utcnow().isoformat()
            self._save_locked()
            return copy.deepcopy(self._state)


world_state = WorldState()