from __future__ import annotations

import json
from pathlib import Path

from config import HISTORY_FILE, MEMORY_FILE


class MemoryStore:
    def __init__(self) -> None:
        self.memory_file = Path(MEMORY_FILE)
        self.history_file = Path(HISTORY_FILE)
        self._ensure_files()

    def _ensure_files(self) -> None:
        if not self.memory_file.exists():
            self.memory_file.write_text("[]", encoding="utf-8")
        if not self.history_file.exists():
            self.history_file.write_text("[]", encoding="utf-8")

    def load_summaries(self) -> list[dict]:
        return json.loads(self.memory_file.read_text(encoding="utf-8"))

    def save_summaries(self, data: list[dict]) -> None:
        self.memory_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_history(self) -> list[dict]:
        return json.loads(self.history_file.read_text(encoding="utf-8"))

    def save_history(self, data: list[dict]) -> None:
        self.history_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )