from __future__ import annotations

import ast
from pathlib import Path

from tools.base_tool import BaseTool
from utils.file_utils import resolve_user_path


class InspectProjectTool(BaseTool):
    name = "inspect_project"
    description = "抽取專案的結構化事實，例如檔案、class、function、import"

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

        py_files: list[Path] = []

        for file_path in sorted(root.rglob("*.py")):
            try:
                rel = file_path.relative_to(root)
            except ValueError:
                rel = file_path

            if any(part in ignore_dirs for part in rel.parts):
                continue

            py_files.append(file_path)

        file_lines: list[str] = []
        class_lines: list[str] = []
        function_lines: list[str] = []
        import_lines: list[str] = []
        tool_registry_lines: list[str] = []
        router_action_lines: list[str] = []

        for file_path in py_files:
            try:
                rel = file_path.relative_to(root)
            except ValueError:
                rel = file_path

            rel_str = str(rel).replace("\\", "/")
            file_lines.append(f"- {rel_str}")

            try:
                source = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue

            # 抽 class / function / import
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.ClassDef):
                    class_lines.append(f"- {rel_str}: class {node.name}")

                    # 額外抓工具類
                    base_names = []
                    for base in node.bases:
                        if isinstance(base, ast.Name):
                            base_names.append(base.id)
                        elif isinstance(base, ast.Attribute):
                            base_names.append(base.attr)

                    if "BaseTool" in base_names:
                        tool_registry_lines.append(f"- {rel_str}: tool class {node.name}")

                elif isinstance(node, ast.FunctionDef):
                    function_lines.append(f"- {rel_str}: def {node.name}")

                elif isinstance(node, ast.Import):
                    names = ", ".join(alias.name for alias in node.names)
                    import_lines.append(f"- {rel_str}: import {names}")

                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    names = ", ".join(alias.name for alias in node.names)
                    import_lines.append(f"- {rel_str}: from {module} import {names}")

            # 特別抓 tool_registry 的 register(...)
            if rel_str.endswith("tools/tool_registry.py"):
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        func = node.func
                        if isinstance(func, ast.Attribute) and func.attr == "register":
                            if node.args:
                                arg = node.args[0]
                                if isinstance(arg, ast.Call):
                                    if isinstance(arg.func, ast.Name):
                                        tool_registry_lines.append(
                                            f"- tool_registry.py registers {arg.func.id}"
                                        )

            # 特別抓 router 裡的 action="xxx"
            if rel_str.endswith("core/router.py"):
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        if isinstance(node.func, ast.Name) and node.func.id == "RouteResult":
                            route_type = None
                            action = None

                            for kw in node.keywords:
                                if kw.arg == "route_type" and isinstance(kw.value, ast.Constant):
                                    route_type = kw.value.value
                                if kw.arg == "action" and isinstance(kw.value, ast.Constant):
                                    action = kw.value.value

                            if route_type or action:
                                router_action_lines.append(
                                    f"- core/router.py: route_type={route_type}, action={action}"
                                )

        sections = []

        sections.append("=== 專案 Python 檔案 ===")
        sections.extend(file_lines or ["- 無"])

        sections.append("")
        sections.append("=== Class 定義 ===")
        sections.extend(class_lines or ["- 無"])

        sections.append("")
        sections.append("=== Function 定義 ===")
        sections.extend(function_lines or ["- 無"])

        sections.append("")
        sections.append("=== Import 關係 ===")
        sections.extend(import_lines[:80] or ["- 無"])

        sections.append("")
        sections.append("=== Tool 註冊資訊 ===")
        sections.extend(tool_registry_lines or ["- 無"])

        sections.append("")
        sections.append("=== Router 路由資訊 ===")
        sections.extend(router_action_lines or ["- 無"])

        return "\n".join(sections)