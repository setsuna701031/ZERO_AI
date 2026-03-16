from __future__ import annotations

from datetime import datetime


class MemoryManager:
    def __init__(self, store) -> None:
        self.store = store

    def remember(self, text: str) -> str:
        text = text.strip()
        if not text:
            return "沒有可記錄的內容。"

        summaries = self.store.load_summaries()
        item = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "text": text,
        }
        summaries.append(item)
        self.store.save_summaries(summaries)

        history = self.store.load_history()
        history.append({"type": "remember", **item})
        self.store.save_history(history)
        return f"已記錄: {text}"

    def show_memory(self) -> str:
        summaries = self.store.load_summaries()
        if not summaries:
            return "目前沒有記憶。"
        lines = []
        for item in summaries[-20:]:
            lines.append(f"- {item['time']} | {item['text']}")
        return "\n".join(lines)