from __future__ import annotations

from pathlib import Path

from tools.base_tool import BaseTool
from utils.file_utils import backup_file, resolve_user_path, write_text_file
from utils.safe_exec import ensure_write_allowed


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "寫入檔案內容"

    def run(self, args: dict) -> str:
        path = resolve_user_path(args.get("path", ""))
        content = str(args.get("content", ""))

        ensure_write_allowed(path)
        backup_info = ""
        if path.exists() and path.is_file():
            backup_path = backup_file(path)
            backup_info = f"\n已備份: {backup_path}"

        write_text_file(path, content)
        return f"已寫入檔案: {path}{backup_info}"