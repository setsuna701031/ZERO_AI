from __future__ import annotations

from pathlib import Path

from config import MAX_SEARCH_RESULTS
from tools.base_tool import BaseTool
from utils.file_utils import resolve_user_path


class SearchCodeTool(BaseTool):
    name = "search_code"
    description = "只搜尋專案 Python 程式碼中的關鍵字"

    def run(self, args: dict) -> str:
        keyword = str(args.get("keyword", "")).strip()
        root = resolve_user_path(args.get("path", "."))

        if not keyword:
            return "請提供關鍵字。"

        if not root.exists() or not root.is_dir():
            return f"搜尋路徑無效: {root}"

        ignore_dirs = {
            "venv",
            ".venv",
            "__pycache__",
            ".git",
            "site-packages",
            "node_modules",
            "dist",
            "build",
        }

        results: list[str] = []

        for file_path in root.rglob("*.py"):
            if len(results) >= MAX_SEARCH_RESULTS:
                break

            try:
                rel_path = file_path.relative_to(root)
            except ValueError:
                rel_path = file_path

            if any(part in ignore_dirs for part in rel_path.parts):
                continue

            try:
                with file_path.open("r", encoding="utf-8", errors="ignore") as f:
                    for index, line in enumerate(f, start=1):
                        if keyword.lower() in line.lower():
                            results.append(
                                f"{rel_path} : 第 {index} 行 : {line.strip()}"
                            )
                            if len(results) >= MAX_SEARCH_RESULTS:
                                break
            except Exception:
                continue

        if not results:
            return f"找不到程式碼關鍵字: {keyword}"

        lines = [f"搜尋根目錄: {root}", f"關鍵字: {keyword}", ""]
        lines.extend(results)
        return "\n".join(lines)