from __future__ import annotations

from pathlib import Path

from tools.base_tool import BaseTool
from utils.file_utils import resolve_user_path


class SummarizeProjectTool(BaseTool):
    name = "summarize_project"
    description = "整理專案結構與重要檔案內容，供 LLM 做整體摘要"

    def run(self, args: dict) -> str:
        root = resolve_user_path(args.get("path", "."))

        if not root.exists():
            return f"路徑不存在: {root}"

        if not root.is_dir():
            return f"不是資料夾: {root}"

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

        preferred_files = [
            "main.py",
            "config.py",
            "requirements.txt",
        ]

        preferred_dirs = [
            "core",
            "tools",
            "brain",
            "memory",
            "ui",
            "utils",
        ]

        tree_lines: list[str] = [f"專案根目錄: {root}"]
        selected_files: list[Path] = []

        all_paths = sorted(root.rglob("*"))

        for path in all_paths:
            try:
                rel = path.relative_to(root)
            except ValueError:
                rel = path

            if any(part in ignore_dirs for part in rel.parts):
                continue

            depth = len(rel.parts) - 1
            indent = "  " * max(depth, 0)

            if path.is_dir():
                tree_lines.append(f"{indent}[DIR] {rel}")
            else:
                tree_lines.append(f"{indent}[FILE] {rel}")

        # 先收主檔
        for name in preferred_files:
            file_path = root / name
            if file_path.exists() and file_path.is_file():
                selected_files.append(file_path)

        # 再收主要資料夾裡的 .py
        for dirname in preferred_dirs:
            dir_path = root / dirname
            if not dir_path.exists() or not dir_path.is_dir():
                continue

            for py_file in sorted(dir_path.rglob("*.py")):
                try:
                    rel = py_file.relative_to(root)
                except ValueError:
                    rel = py_file

                if any(part in ignore_dirs for part in rel.parts):
                    continue

                selected_files.append(py_file)

        # 去重
        unique_files: list[Path] = []
        seen: set[str] = set()

        for path in selected_files:
            try:
                rel = str(path.relative_to(root))
            except ValueError:
                rel = str(path)

            if rel not in seen:
                seen.add(rel)
                unique_files.append(path)

        file_sections: list[str] = []
        max_files = 18
        max_chars_per_file = 1200

        for file_path in unique_files[:max_files]:
            try:
                rel = file_path.relative_to(root)
            except ValueError:
                rel = file_path

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            content = content.strip()
            if not content:
                continue

            preview = content[:max_chars_per_file]

            file_sections.append(
                f"### 檔案: {rel}\n{preview}"
            )

        if not file_sections:
            file_sections_text = "沒有可讀取的重要檔案內容。"
        else:
            file_sections_text = "\n\n".join(file_sections)

        return (
            "=== 專案結構 ===\n"
            f"{chr(10).join(tree_lines)}\n\n"
            "=== 重要檔案內容 ===\n"
            f"{file_sections_text}"
        )