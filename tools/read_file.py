from __future__ import annotations

from tools.base_tool import BaseTool
from utils.file_utils import read_text_file, resolve_user_path


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "讀取檔案內容"

    def run(self, args: dict) -> str:
        path = resolve_user_path(args.get("path", ""))
        if not path.exists():
            return f"檔案不存在: {path}"
        if not path.is_file():
            return f"不是檔案: {path}"
        return read_text_file(path)