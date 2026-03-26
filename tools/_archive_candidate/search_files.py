from __future__ import annotations

from pathlib import Path

from config import MAX_SEARCH_RESULTS
from tools.base_tool import BaseTool
from utils.file_utils import is_text_like_file, resolve_user_path


class SearchFilesTool(BaseTool):
    name = "search_files"
    description = "在資料夾中搜尋關鍵字"

    def run(self, args: dict) -> str:
        keyword = str(args.get("keyword", "")).strip()
        root = resolve_user_path(args.get("path", "."))

        if not keyword:
            return "請提供關鍵字。"
        if not root.exists() or not root.is_dir():
            return f"搜尋路徑無效: {root}"

        results: list[str] = []
        for file_path in root.rglob("*"):
            if len(results) >= MAX_SEARCH_RESULTS:
                break
            if not file_path.is_file() or not is_text_like_file(file_path):
                continue
            try:
                with file_path.open("r", encoding="utf-8", errors="ignore") as f:
                    for index, line in enumerate(f, start=1):
                        if keyword.lower() in line.lower():
                            results.append(f"{file_path} : 第 {index} 行 : {line.strip()}")
                            if len(results) >= MAX_SEARCH_RESULTS:
                                break
            except Exception:
                continue

        if not results:
            return f"找不到關鍵字: {keyword}"
        return "\n".join(results)