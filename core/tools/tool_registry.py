from __future__ import annotations

from typing import Any, Dict, List, Optional


try:
    from core.tools.web_search_tool import WebSearchTool
except Exception:
    WebSearchTool = None  # type: ignore


try:
    from core.tools.workspace_tool import WorkspaceTool
except Exception:
    WorkspaceTool = None  # type: ignore


try:
    from core.tools.file_tool import FileTool
except Exception:
    FileTool = None  # type: ignore


try:
    from core.tools.command_tool import CommandTool
except Exception:
    CommandTool = None  # type: ignore


class ToolRegistry:
    """
    統一工具註冊中心

    這版目標：
    1. 工具註冊固定
    2. alias 解析固定
    3. execute / invoke 入口固定
    4. output / error 格式固定
    5. 兼容舊的 get_tool / get / resolve / find_tool 呼叫方式
    """

    def __init__(self, workspace_dir: str = "workspace") -> None:
        self.workspace_dir = workspace_dir
        self.tools: Dict[str, Any] = {}
        self.aliases: Dict[str, str] = {}
        self._register_default_tools()

    # =========================================================
    # public api
    # =========================================================

    def register(self, name: str, tool: Any, aliases: Optional[List[str]] = None) -> None:
        key = self._normalize_name(name)
        if not key:
            raise ValueError("tool name cannot be empty")

        self.tools[key] = tool
        self.aliases[key] = key

        for alias in aliases or []:
            alias_key = self._normalize_name(alias)
            if alias_key:
                self.aliases[alias_key] = key

    def has_tool(self, name: str) -> bool:
        return self._resolve_canonical_name(name) in self.tools

    def get_tool(self, name: str) -> Optional[Any]:
        canonical = self._resolve_canonical_name(name)
        if not canonical:
            return None
        return self.tools.get(canonical)

    def get(self, name: str) -> Optional[Any]:
        return self.get_tool(name)

    def resolve(self, name: str) -> Optional[Any]:
        return self.get_tool(name)

    def find_tool(self, name: str) -> Optional[Any]:
        return self.get_tool(name)

    def get_canonical_name(self, name: str) -> Optional[str]:
        canonical = self._resolve_canonical_name(name)
        return canonical if canonical in self.tools else None

    def list_tools(self) -> Dict[str, Any]:
        entries = []
        seen = set()

        for canonical_name in sorted(self.tools.keys()):
            if canonical_name in seen:
                continue
            seen.add(canonical_name)
            aliases = sorted(
                alias for alias, target in self.aliases.items()
                if target == canonical_name and alias != canonical_name
            )
            entries.append(
                {
                    "name": canonical_name,
                    "aliases": aliases,
                    "tool_type": type(self.tools[canonical_name]).__name__,
                }
            )

        return {
            "ok": True,
            "count": len(self.tools),
            "tools": entries,
        }

    def execute_tool(self, name: str, tool_input: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        統一工具執行入口

        固定回傳格式：
        {
            "ok": bool,
            "tool": "canonical_name or original_name",
            "input": {...},
            "output": {...} or raw_result,
            "error": None or {
                "type": str,
                "message": str,
                "retryable": bool
            }
        }
        """
        raw_name = self._normalize_name(name)
        payload = tool_input if isinstance(tool_input, dict) else {}

        if not raw_name:
            return self._error_result(
                tool=name,
                tool_input=payload,
                error_type="invalid_tool_name",
                message="tool name cannot be empty",
                retryable=False,
            )

        canonical_name = self._resolve_canonical_name(raw_name)
        if not canonical_name or canonical_name not in self.tools:
            return self._error_result(
                tool=raw_name,
                tool_input=payload,
                error_type="tool_not_found",
                message=f"tool not found: {raw_name}",
                retryable=False,
            )

        tool = self.tools[canonical_name]

        try:
            raw_result = self._invoke_tool(tool, payload)
            normalized_output = self._normalize_tool_output(raw_result)
            return self._success_result(
                tool=canonical_name,
                tool_input=payload,
                output=normalized_output,
            )
        except TypeError as exc:
            return self._error_result(
                tool=canonical_name,
                tool_input=payload,
                error_type="tool_invocation_error",
                message=str(exc),
                retryable=False,
            )
        except Exception as exc:
            return self._error_result(
                tool=canonical_name,
                tool_input=payload,
                error_type=exc.__class__.__name__,
                message=str(exc),
                retryable=self._is_retryable_exception(exc),
            )

    def invoke(self, name: str, tool_input: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.execute_tool(name, tool_input)

    def run(self, name: str, tool_input: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.execute_tool(name, tool_input)

    # =========================================================
    # default registration
    # =========================================================

    def _register_default_tools(self) -> None:
        web_search_tool = self._safe_build_web_search_tool()
        if web_search_tool is not None:
            self.register(
                "web_search",
                web_search_tool,
                aliases=["search_web", "websearch", "search"],
            )

        workspace_tool = self._safe_build_workspace_tool()
        if workspace_tool is not None:
            self.register(
                "workspace",
                workspace_tool,
                aliases=["workspace_tool"],
            )

        file_tool = self._safe_build_file_tool()
        if file_tool is not None:
            self.register(
                "file",
                file_tool,
                aliases=["file_tool"],
            )

        command_tool = self._safe_build_command_tool()
        if command_tool is not None:
            self.register(
                "command",
                command_tool,
                aliases=["command_tool", "shell"],
            )

    # =========================================================
    # builders
    # =========================================================

    def _safe_build_web_search_tool(self) -> Optional[Any]:
        if WebSearchTool is None:
            return None

        for kwargs in (
            {},
            {"workspace_dir": self.workspace_dir},
            {"workspace_root": self.workspace_dir},
        ):
            try:
                return WebSearchTool(**kwargs)
            except TypeError:
                continue
            except Exception:
                return None

        try:
            return WebSearchTool()
        except Exception:
            return None

    def _safe_build_workspace_tool(self) -> Optional[Any]:
        if WorkspaceTool is None:
            return None

        for kwargs in (
            {"workspace_root": self.workspace_dir},
            {"workspace_dir": self.workspace_dir},
        ):
            try:
                return WorkspaceTool(**kwargs)
            except TypeError:
                continue
            except Exception:
                return None

        for args in (
            (self.workspace_dir,),
            (),
        ):
            try:
                return WorkspaceTool(*args)
            except TypeError:
                continue
            except Exception:
                return None

        return None

    def _safe_build_file_tool(self) -> Optional[Any]:
        if FileTool is None:
            return None

        for kwargs in (
            {},
            {"workspace_dir": self.workspace_dir},
            {"workspace_root": self.workspace_dir},
        ):
            try:
                return FileTool(**kwargs)
            except TypeError:
                continue
            except Exception:
                return None

        try:
            return FileTool()
        except Exception:
            return None

    def _safe_build_command_tool(self) -> Optional[Any]:
        if CommandTool is None:
            return None

        for kwargs in (
            {},
            {"workspace_dir": self.workspace_dir},
            {"workspace_root": self.workspace_dir},
        ):
            try:
                return CommandTool(**kwargs)
            except TypeError:
                continue
            except Exception:
                return None

        try:
            return CommandTool()
        except Exception:
            return None

    # =========================================================
    # invoke helpers
    # =========================================================

    def _invoke_tool(self, tool: Any, tool_input: Dict[str, Any]) -> Any:
        """
        兼容常見工具介面：
        1. tool.execute(dict)
        2. tool.run(dict)
        3. tool.invoke(dict)
        4. callable(tool)(dict)
        5. callable(tool)(**dict)
        """
        for method_name in ("execute", "run", "invoke"):
            method = getattr(tool, method_name, None)
            if callable(method):
                try:
                    return method(tool_input)
                except TypeError:
                    return method(**tool_input)

        if callable(tool):
            try:
                return tool(tool_input)
            except TypeError:
                return tool(**tool_input)

        raise TypeError(f"tool {type(tool).__name__} is not invokable")

    def _normalize_tool_output(self, raw_result: Any) -> Any:
        """
        工具自己的輸出先保留，不在 registry 這層過度改寫。
        但最外層一定包成固定 envelope。
        """
        if isinstance(raw_result, dict):
            return raw_result
        if raw_result is None:
            return {}
        return {"result": raw_result}

    def _success_result(self, tool: str, tool_input: Dict[str, Any], output: Any) -> Dict[str, Any]:
        return {
            "ok": True,
            "tool": tool,
            "input": tool_input,
            "output": output,
            "error": None,
        }

    def _error_result(
        self,
        tool: str,
        tool_input: Dict[str, Any],
        error_type: str,
        message: str,
        retryable: bool,
    ) -> Dict[str, Any]:
        return {
            "ok": False,
            "tool": tool,
            "input": tool_input,
            "output": {},
            "error": {
                "type": error_type,
                "message": message,
                "retryable": retryable,
            },
        }

    def _is_retryable_exception(self, exc: Exception) -> bool:
        retryable_types = (
            TimeoutError,
            ConnectionError,
        )
        return isinstance(exc, retryable_types)

    def _normalize_name(self, name: Any) -> str:
        return str(name or "").strip().lower()

    def _resolve_canonical_name(self, name: Any) -> str:
        key = self._normalize_name(name)
        if not key:
            return ""
        return self.aliases.get(key, key)