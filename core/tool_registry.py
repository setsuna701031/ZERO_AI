from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional


class ToolRegistry:
    """
    ZERO Tool Registry

    作用：
    1. 統一註冊工具
    2. 統一取得工具
    3. 統一執行工具
    4. 統一列出工具
    5. 避免 AgentLoop 直接依賴每一個 tool 類別
    """

    def __init__(self, workspace_root: Optional[str] = None) -> None:
        self._tools: Dict[str, Any] = {}
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else None
        self._auto_register_default_tools()

    @property
    def tools(self) -> Dict[str, Any]:
        """
        給舊版 AgentLoop 相容使用。
        """
        return self._tools

    # =========================
    # Default tool registration
    # =========================

    def _auto_register_default_tools(self) -> None:
        """
        啟動時自動註冊預設工具。
        目前先保守註冊：
        - workspace（需要 workspace_root）
        - file（若存在）
        - command（需要 workspace_root）
        """
        self._try_register_workspace_tool()
        self._try_register_file_tool()
        self._try_register_command_tool()

    def _try_register_workspace_tool(self) -> None:
        try:
            if self.workspace_root is None:
                print("[ToolRegistry] skip workspace tool: workspace_root is not set")
                return

            from tools.workspace_tool import WorkspaceTool

            result = self.register(WorkspaceTool(workspace_root=self.workspace_root))
            if not result.get("ok", False):
                print(f"[ToolRegistry] skip workspace tool: {result.get('summary')}")
        except Exception as exc:
            print(f"[ToolRegistry] skip workspace tool: {exc}")

    def _try_register_file_tool(self) -> None:
        try:
            from tools.file_tool import FileTool

            file_tool = None

            # 先嘗試帶 workspace_root 建立
            if self.workspace_root is not None:
                try:
                    file_tool = FileTool(workspace_root=self.workspace_root)
                except TypeError:
                    file_tool = None

            # 若上面不適用，再退回無參數初始化
            if file_tool is None:
                file_tool = FileTool()

            result = self.register(file_tool)
            if not result.get("ok", False):
                print(f"[ToolRegistry] skip file tool: {result.get('summary')}")
        except Exception as exc:
            print(f"[ToolRegistry] skip file tool: {exc}")

    def _try_register_command_tool(self) -> None:
        try:
            if self.workspace_root is None:
                print("[ToolRegistry] skip command tool: workspace_root is not set")
                return

            from tools.command_tool import CommandTool

            result = self.register(CommandTool(workspace_root=self.workspace_root))
            if not result.get("ok", False):
                print(f"[ToolRegistry] skip command tool: {result.get('summary')}")
        except Exception as exc:
            print(f"[ToolRegistry] skip command tool: {exc}")

    # =========================
    # Public API
    # =========================

    def register(self, tool: Any) -> Dict[str, Any]:
        """
        註冊單一工具

        工具需至少具備：
        - name 屬性
        - execute(payload) 方法
        """
        if tool is None:
            return {
                "ok": False,
                "error": "tool_is_none",
                "summary": "Cannot register tool: tool is None."
            }

        tool_name = getattr(tool, "name", None)
        if not isinstance(tool_name, str) or tool_name.strip() == "":
            return {
                "ok": False,
                "error": "invalid_tool_name",
                "summary": "Cannot register tool: missing valid tool.name."
            }

        execute_method = getattr(tool, "execute", None)
        if not callable(execute_method):
            return {
                "ok": False,
                "error": "missing_execute_method",
                "summary": f"Cannot register tool '{tool_name}': execute(payload) is required."
            }

        normalized_name = tool_name.strip()
        self._tools[normalized_name] = tool

        return {
            "ok": True,
            "tool_name": normalized_name,
            "summary": f"Tool registered: {normalized_name}"
        }

    def unregister(self, tool_name: str) -> Dict[str, Any]:
        normalized_name = str(tool_name or "").strip()

        if normalized_name == "":
            return {
                "ok": False,
                "error": "missing_tool_name",
                "summary": "Cannot unregister tool: tool_name is required."
            }

        if normalized_name not in self._tools:
            return {
                "ok": False,
                "error": "tool_not_found",
                "summary": f"Tool not found: {normalized_name}"
            }

        del self._tools[normalized_name]

        return {
            "ok": True,
            "tool_name": normalized_name,
            "summary": f"Tool unregistered: {normalized_name}"
        }

    def has_tool(self, tool_name: str) -> bool:
        normalized_name = str(tool_name or "").strip()
        return normalized_name in self._tools

    def get_tool(self, tool_name: str) -> Optional[Any]:
        normalized_name = str(tool_name or "").strip()
        return self._tools.get(normalized_name)

    def list_tools(self) -> Dict[str, Any]:
        names = sorted(self._tools.keys())
        return {
            "ok": True,
            "count": len(names),
            "tools": names,
            "summary": f"Registered {len(names)} tool(s)."
        }

    def list_tool_names(self) -> List[str]:
        return sorted(self._tools.keys())

    def list_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        提供給 tool_registry_inspector / API 使用的工具定義列表
        """
        definitions: List[Dict[str, Any]] = []

        for tool_name in sorted(self._tools.keys()):
            tool = self._tools[tool_name]

            description = getattr(tool, "description", "") or ""
            version = getattr(tool, "version", "") or ""
            category = getattr(tool, "category", "") or ""
            metadata = getattr(tool, "metadata", None)

            execute_method = getattr(tool, "execute", None)
            callable_execute = callable(execute_method)

            definitions.append({
                "name": tool_name,
                "description": description,
                "version": version,
                "category": category,
                "callable": callable_execute,
                "class_name": tool.__class__.__name__,
                "module": tool.__class__.__module__,
                "metadata": metadata if isinstance(metadata, dict) else {},
            })

        return definitions

    def execute_tool(
        self,
        tool_name: str,
        payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        normalized_name = str(tool_name or "").strip()
        payload = payload or {}

        if normalized_name == "":
            return self._build_error(
                tool_name="",
                summary="Tool name is required.",
                error="missing_tool_name",
                payload=payload
            )

        tool = self.get_tool(normalized_name)
        if tool is None:
            return self._build_error(
                tool_name=normalized_name,
                summary=f"Tool not found: {normalized_name}",
                error="tool_not_found",
                payload=payload
            )

        try:
            result = tool.execute(payload)
        except Exception as exc:
            return self._build_error(
                tool_name=normalized_name,
                summary=f"Tool execution failed: {exc}",
                error="tool_execution_exception",
                payload=payload
            )

        if not isinstance(result, dict):
            return self._build_error(
                tool_name=normalized_name,
                summary=f"Tool '{normalized_name}' returned non-dict result.",
                error="invalid_tool_result",
                payload=payload
            )

        if "tool_name" not in result:
            result["tool_name"] = normalized_name

        if "ok" not in result:
            result["ok"] = False

        if "changed_files" not in result:
            result["changed_files"] = []

        if "evidence" not in result:
            result["evidence"] = []

        if "results" not in result:
            result["results"] = []

        return result

    def register_many(self, tools: List[Any]) -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []

        for tool in tools:
            results.append(self.register(tool))

        success_count = sum(1 for item in results if item.get("ok", False))
        failed_count = len(results) - success_count

        return {
            "ok": failed_count == 0,
            "summary": f"Registered {success_count} tool(s), failed {failed_count}.",
            "success_count": success_count,
            "failed_count": failed_count,
            "results": results,
        }

    # =========================
    # Compatibility helpers
    # =========================

    def dispatch(self, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        相容某些舊程式碼直接呼叫 registry.dispatch(payload)
        """
        payload = payload or {}

        if not isinstance(payload, dict):
            return self._build_error(
                tool_name="",
                summary="Payload must be a dict.",
                error="payload_must_be_dict",
                payload={}
            )

        tool_name = str(payload.get("tool_name", "")).strip()
        if tool_name == "":
            return self._build_error(
                tool_name="",
                summary="Tool name missing.",
                error="tool_name_missing",
                payload=payload
            )

        return self.execute_tool(tool_name=tool_name, payload=payload)

    # =========================
    # Helpers
    # =========================

    def _build_error(
        self,
        tool_name: str,
        summary: str,
        error: str,
        payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return {
            "ok": False,
            "tool_name": tool_name,
            "summary": summary,
            "changed_files": [],
            "evidence": [],
            "results": [],
            "error": error,
            "payload": payload or {},
        }