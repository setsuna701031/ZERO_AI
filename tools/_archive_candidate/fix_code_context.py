from __future__ import annotations

from pathlib import Path

from config import MAX_SEARCH_RESULTS
from tools.base_tool import BaseTool
from utils.file_utils import resolve_user_path


class FixCodeContextTool(BaseTool):
    name = "fix_code_context"
    description = "依關鍵字搜尋相關 Python 程式碼，提供修錯分析上下文"

    def run(self, args: dict) -> str:
        keyword = str(args.get("keyword", "")).strip()
        root = resolve_user_path(args.get("path", "."))

        if not keyword:
            return "請提供錯誤描述或關鍵字。"

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
            ".idea",
            ".vscode",
            "logs",
            "data",
        }

        matches: list[tuple[Path, int, str]] = []

        for file_path in sorted(root.rglob("*.py")):
            try:
                rel = file_path.relative_to(root)
            except ValueError:
                rel = file_path

            if any(part in ignore_dirs for part in rel.parts):
                continue

            try:
                with file_path.open("r", encoding="utf-8", errors="ignore") as f:
                    for line_no, line in enumerate(f, start=1):
                        if keyword.lower() in line.lower():
                            matches.append((file_path, line_no, line.rstrip()))
                            if len(matches) >= MAX_SEARCH_RESULTS:
                                break
            except Exception:
                continue

            if len(matches) >= MAX_SEARCH_RESULTS:
                break

        if not matches:
            return f"找不到與 '{keyword}' 相關的 Python 程式碼。"

        file_hits: dict[Path, list[tuple[int, str]]] = {}
        for file_path, line_no, line in matches:
            file_hits.setdefault(file_path, []).append((line_no, line))

        sections: list[str] = [
            f"搜尋根目錄: {root}",
            f"關鍵字: {keyword}",
            "",
        ]

        max_files = 6
        max_preview_lines = 80

        for index, (file_path, hit_lines) in enumerate(file_hits.items()):
            if index >= max_files:
                break

            try:
                rel = file_path.relative_to(root)
            except ValueError:
                rel = file_path

            sections.append(f"=== 檔案: {rel} ===")

            try:
                all_lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                sections.append("無法讀取檔案內容。")
                sections.append("")
                continue

            wanted_line_numbers: set[int] = set()
            for line_no, _ in hit_lines:
                start = max(1, line_no - 3)
                end = min(len(all_lines), line_no + 3)
                wanted_line_numbers.update(range(start, end + 1))

            preview_count = 0
            for ln in sorted(wanted_line_numbers):
                if preview_count >= max_preview_lines:
                    sections.append("... [內容過長，已截斷]")
                    break
                content = all_lines[ln - 1]
                sections.append(f"{ln}: {content}")
                preview_count += 1

            sections.append("")

        return "\n".join(sections)