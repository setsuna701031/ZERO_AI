from dataclasses import dataclass, field
from typing import Any


@dataclass
class SessionState:
    current_project: str | None = None
    current_workdir: str | None = None
    last_route: dict[str, Any] | None = None
    last_result: str | None = None
    recent_files: list[str] = field(default_factory=list)
    recent_tools: list[str] = field(default_factory=list)

    def add_recent_file(self, path: str) -> None:
        if path in self.recent_files:
            self.recent_files.remove(path)
        self.recent_files.insert(0, path)
        del self.recent_files[10:]

    def add_recent_tool(self, tool_name: str) -> None:
        if tool_name in self.recent_tools:
            self.recent_tools.remove(tool_name)
        self.recent_tools.insert(0, tool_name)
        del self.recent_tools[10:]