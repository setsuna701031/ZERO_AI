from __future__ import annotations

from pathlib import Path

from config import MAX_READ_CHARS
from tools.base_tool import BaseTool
from utils.file_utils import is_text_like_file, resolve_user_path


class AnalyzeProjectTool(BaseTool):
    name = "analyze_project"
    description = "分析整個專案結構並整理重點"

    def run(self, args: dict) -> str:
        root = resolve_user_path(args.get("path", "."))
        if not root.exists():
            return f"路徑不存在: {root}"
        if not root.is_dir():
            return f"不是資料夾: {root}"

        ignore_dirs = {
            "__pycache__",
            ".git",
            "venv",
            ".venv",
            "node_modules",
            "dist",
            "build",
        }

        tree_lines: list[str] = [f"專案路徑: {root}"]
        file_summaries: list[str] = []

        for path in sorted(root.rglob("*")):
            try:
                rel = path.relative_to(root)
            except ValueError:
                rel = path

            if any(part in ignore_dirs for part in rel.parts):
                continue

            depth = len(rel.parts) - 1
            indent = "  " * depth

            if path.is_dir():
                tree_lines.append(f"{indent}[DIR] {rel.name}")
                continue

            tree_lines.append(f"{indent}[FILE] {rel.name}")

            if is_text_like_file(path):
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                    preview = content[: min(1200, MAX_READ_CHARS)].strip()
                    if preview:
                        file_summaries.append(
                            f"\n### 檔案: {rel}\n{preview}"
                        )
                except Exception:
                    continue

        if not file_summaries:
            return "\n".join(tree_lines)

        summary_text = "\n".join(file_summaries[:20])

        return (
            "=== 專案結構 ===\n"
            f"{chr(10).join(tree_lines)}\n\n"
            "=== 檔案內容預覽 ===\n"
            f"{summary_text}"
        )