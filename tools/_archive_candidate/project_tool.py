import os
from typing import Dict, Any, List
from config import settings


class ProjectTool:
    name = "project"

    PRIORITY_FILES = [
        "app.py",
        "main.py",
        "zero_v8.py",
        "zero.py",
        "agent_loop.py",
        "router.py",
        "tool_registry.py",
        "llm_client.py",
        "config.py"
    ]

    EXCLUDED_DIRS = {
        ".git", "__pycache__", ".venv", "venv",
        "node_modules", ".idea", ".vscode",
        "dist", "build"
    }

    TEXT_EXTS = {
        ".py", ".js", ".ts", ".json", ".md", ".txt"
    }

    def understand_project(self, cwd: str, query: str) -> Dict[str, Any]:
        if not os.path.isdir(cwd):
            return {"ok": False, "error": "Invalid path"}

        tree = self._scan_tree(cwd)

        relevant_files = self._find_relevant_files(cwd, query)

        # ⭐ fallback：如果沒抓到，就抓核心檔
        if not relevant_files:
            relevant_files = self._get_priority_files(cwd)

        content = self._read_files(relevant_files)

        return {
            "ok": True,
            "tool": self.name,
            "tree": tree,
            "relevant_files": relevant_files,
            "content": content
        }

    def _scan_tree(self, cwd: str) -> str:
        lines = []

        for root, dirs, files in os.walk(cwd):
            dirs[:] = [d for d in dirs if d not in self.EXCLUDED_DIRS]

            rel = os.path.relpath(root, cwd)
            indent = "  " * rel.count(os.sep)

            lines.append(f"{indent}{os.path.basename(root)}/")

            for f in files:
                lines.append(f"{indent}  {f}")

        return "\n".join(lines)

    def _find_relevant_files(self, cwd: str, query: str) -> List[str]:
        results = []

        for root, _, files in os.walk(cwd):
            for f in files:
                if not f.endswith(".py"):
                    continue

                path = os.path.join(root, f)

                if query.lower() in f.lower():
                    results.append(path)

        return results[:8]

    def _get_priority_files(self, cwd: str) -> List[str]:
        results = []

        for f in self.PRIORITY_FILES:
            path = os.path.join(cwd, f)
            if os.path.exists(path):
                results.append(path)

        return results

    def _read_files(self, files: List[str]) -> str:
        contents = []

        for path in files:
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    data = f.read(settings.max_file_chars)

                contents.append(f"\n===== {path} =====\n{data}")

            except Exception as e:
                contents.append(f"\n[ERROR reading {path}] {e}")

        return "\n".join(contents)