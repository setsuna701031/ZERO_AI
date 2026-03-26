from __future__ import annotations

from pathlib import Path

from tools.base_tool import BaseTool
from utils.file_utils import resolve_user_path


class ListFilesTool(BaseTool):
    name = "list_files"
    description = "列出資料夾內容"

    def run(self, args: dict) -> str:
        path = resolve_user_path(args.get("path", "."))
        if not path.exists():
            return f"路徑不存在: {path}"
        if not path.is_dir():
            return f"不是資料夾: {path}"

        items = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        if not items:
            return f"資料夾是空的: {path}"

        lines = [f"路徑: {path}"]
        for item in items:
            prefix = "[DIR]" if item.is_dir() else "[FILE]"
            lines.append(f"{prefix} {item.name}")
        return "\n".join(lines)