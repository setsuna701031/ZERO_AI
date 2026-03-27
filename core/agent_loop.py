from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


class AgentLoop:
    """
    ZERO Agent Loop (compat version)

    目標：
    - 兼容不同版本的 TaskManager
    - 兼容 router / non-router
    - tool mode 可直接執行
    - task mode 可走 TaskRuntime
    - 就算 TaskManager 沒有 create_task，也能自建 task payload 往下跑
    """

    def __init__(
        self,
        task_manager: Any = None,
        task_runtime: Any = None,
        router: Any = None,
        tool_registry: Any = None,
        **kwargs: Any,
    ) -> None:
        self.task_manager = task_manager
        self.task_runtime = task_runtime
        self.router = router
        self.tool_registry = tool_registry
        self.extra_config = kwargs

    # =========================================================
    # Main
    # =========================================================

    def run(self, user_input: str) -> Dict[str, Any]:
        if not isinstance(user_input, str) or user_input.strip() == "":
            return self._build_response(
                success=False,
                mode="system",
                summary="Empty user input.",
                data={},
                error="user_input cannot be empty.",
            )

        if self.task_runtime is None:
            return self._build_response(
                success=False,
                mode="system",
                summary="Task runtime is not available.",
                data={},
                error="task_runtime is not configured.",
            )

        route = self._route_input(user_input)

        if route["mode"] == "tool":
            return self._run_tool_mode(user_input=user_input, route=route)

        return self._run_task_mode(user_input=user_input, route=route)

    # =========================================================
    # Route
    # =========================================================

    def _route_input(self, user_input: str) -> Dict[str, Any]:
        if self.router is not None:
            route_method = getattr(self.router, "route", None)
            if callable(route_method):
                try:
                    routed = route_method(user_input)
                    if isinstance(routed, dict):
                        mode = str(routed.get("mode", "task")).strip() or "task"
                        return {
                            "mode": mode,
                            "tool_name": routed.get("tool_name"),
                            "tool_args": routed.get("tool_args", {}) or {},
                        }
                except Exception:
                    pass

        text = user_input.strip()

        if text.startswith("cmd:"):
            return {
                "mode": "tool",
                "tool_name": "command_tool",
                "tool_args": {
                    "command": text[4:].strip(),
                },
            }

        if text.startswith("ws:"):
            return {
                "mode": "tool",
                "tool_name": "workspace_tool",
                "tool_args": {
                    "action": "read_file",
                    "path": text[3:].strip(),
                },
            }

        return {
            "mode": "task",
            "tool_name": None,
            "tool_args": {},
        }

    # =========================================================
    # Tool Mode
    # =========================================================

    def _run_tool_mode(self, user_input: str, route: Dict[str, Any]) -> Dict[str, Any]:
        tool_name = self._normalize_tool_name(route.get("tool_name"))
        tool_args = route.get("tool_args", {})

        if not isinstance(tool_args, dict):
            tool_args = {}

        if not tool_name:
            return self._build_response(
                success=False,
                mode="tool",
                summary="Tool route missing tool_name.",
                data={"route": route},
                error="tool_name is required for tool mode.",
            )

        tool = self._get_tool(tool_name)
        if tool is None:
            return self._build_response(
                success=False,
                mode="tool",
                summary=f"Tool not found: {tool_name}",
                data={
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                },
                error=f"Tool '{tool_name}' is not registered.",
            )

        task = self._ensure_task_record(
            user_input=user_input,
            task_type="tool",
            route=route,
        )

        try:
            tool_result = self._run_tool(tool, tool_args)
            success = True

            if isinstance(tool_result, dict) and tool_result.get("success") is False:
                success = False

            self._update_task_status(task, "finished" if success else "failed")

            return self._build_response(
                success=success,
                mode="tool",
                summary=f"Tool executed: {tool_name}",
                data={
                    "task": self._refresh_task(task),
                    "runtime_result": {
                        "task_name": task.get("task_name", ""),
                        "status": "finished" if success else "failed",
                        "task_type": "tool",
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "tool_result": tool_result,
                    },
                },
                error=None if success else self._extract_error_from_tool_result(tool_result),
            )
        except Exception as exc:
            self._update_task_status(task, "failed")
            return self._build_response(
                success=False,
                mode="tool",
                summary=f"Tool execution failed: {tool_name}",
                data={
                    "task": self._refresh_task(task),
                    "runtime_result": {
                        "task_name": task.get("task_name", ""),
                        "status": "failed",
                        "task_type": "tool",
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                    },
                },
                error=str(exc),
            )

    # =========================================================
    # Task Mode
    # =========================================================

    def _run_task_mode(self, user_input: str, route: Dict[str, Any]) -> Dict[str, Any]:
        task = self._ensure_task_record(
            user_input=user_input,
            task_type="general",
            route=route,
        )

        try:
            runtime_result = self.task_runtime.run_task(task)
        except Exception as exc:
            self._update_task_status(task, "failed")
            return self._build_response(
                success=False,
                mode="runtime",
                summary="Task runtime execution failed.",
                data={"task": self._refresh_task(task)},
                error=str(exc),
            )

        normalized_result = self._normalize_runtime_result(runtime_result)
        latest_task = self._refresh_task(task)

        return self._build_response(
            success=normalized_result["success"],
            mode="runtime",
            summary=normalized_result["summary"],
            data={
                "task": latest_task,
                "runtime_result": normalized_result["data"],
            },
            error=normalized_result["error"],
        )

    # =========================================================
    # Task Compatibility Layer
    # =========================================================

    def _ensure_task_record(
        self,
        user_input: str,
        task_type: str,
        route: Dict[str, Any],
    ) -> Dict[str, Any]:
        task = self._try_create_task_via_manager(user_input)
        if isinstance(task, dict):
            return self._normalize_task_dict(task, user_input, task_type)

        fallback_task = self._build_fallback_task(user_input=user_input, task_type=task_type, route=route)
        self._try_save_task_via_manager(fallback_task)
        return fallback_task

    def _try_create_task_via_manager(self, user_input: str) -> Optional[Dict[str, Any]]:
        if self.task_manager is None:
            return None

        candidate_methods = [
            "create_task",
            "add_task",
            "new_task",
            "build_task",
        ]

        for method_name in candidate_methods:
            method = getattr(self.task_manager, method_name, None)
            if not callable(method):
                continue

            try:
                result = method(user_input)
                if isinstance(result, dict):
                    return result
            except TypeError:
                pass
            except Exception:
                pass

            try:
                result = method(goal=user_input)
                if isinstance(result, dict):
                    return result
            except TypeError:
                pass
            except Exception:
                pass

            try:
                result = method(task_input=user_input)
                if isinstance(result, dict):
                    return result
            except TypeError:
                pass
            except Exception:
                pass

        return None

    def _try_save_task_via_manager(self, task: Dict[str, Any]) -> None:
        if self.task_manager is None or not isinstance(task, dict):
            return

        candidate_methods = [
            "save_task",
            "register_task",
            "add_task",
            "insert_task",
        ]

        for method_name in candidate_methods:
            method = getattr(self.task_manager, method_name, None)
            if not callable(method):
                continue

            try:
                method(task)
                return
            except TypeError:
                pass
            except Exception:
                pass

            try:
                method(task.get("task_name"), task)
                return
            except TypeError:
                pass
            except Exception:
                pass

    def _update_task_status(self, task: Dict[str, Any], status: str) -> None:
        if not isinstance(task, dict):
            return

        task["status"] = status
        task["updated_at"] = self._now_iso()

        if self.task_manager is None:
            return

        task_name = str(task.get("task_name", "")).strip()
        if not task_name:
            return

        candidate_methods = [
            "update_task_status",
            "set_task_status",
            "mark_task_status",
        ]

        for method_name in candidate_methods:
            method = getattr(self.task_manager, method_name, None)
            if not callable(method):
                continue

            try:
                method(task_name, status)
                return
            except TypeError:
                pass
            except Exception:
                pass

            try:
                method(task, status)
                return
            except TypeError:
                pass
            except Exception:
                pass

    def _refresh_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(task, dict):
            return {}

        if self.task_manager is None:
            return task

        task_name = str(task.get("task_name", "")).strip()
        if not task_name:
            return task

        candidate_methods = [
            "get_task",
            "read_task",
            "find_task",
        ]

        for method_name in candidate_methods:
            method = getattr(self.task_manager, method_name, None)
            if not callable(method):
                continue

            try:
                result = method(task_name)
                if isinstance(result, dict):
                    return result
            except Exception:
                pass

        return task

    def _normalize_task_dict(
        self,
        task: Dict[str, Any],
        user_input: str,
        task_type: str,
    ) -> Dict[str, Any]:
        normalized = dict(task)

        if not normalized.get("task_name"):
            normalized["task_name"] = self._make_task_name(task_type)

        if not normalized.get("goal"):
            normalized["goal"] = user_input

        if not normalized.get("status"):
            normalized["status"] = "created"

        if not normalized.get("created_at"):
            normalized["created_at"] = self._now_iso()

        normalized["updated_at"] = self._now_iso()

        if not normalized.get("task_type"):
            normalized["task_type"] = task_type

        return normalized

    def _build_fallback_task(
        self,
        user_input: str,
        task_type: str,
        route: Dict[str, Any],
    ) -> Dict[str, Any]:
        now = self._now_iso()

        return {
            "task_name": self._make_task_name(task_type),
            "goal": user_input,
            "status": "created",
            "task_type": task_type,
            "route_mode": route.get("mode", "task"),
            "created_at": now,
            "updated_at": now,
        }

    # =========================================================
    # Tool Helpers
    # =========================================================

    def _get_tool(self, name: str) -> Optional[Any]:
        clean_name = self._normalize_tool_name(name)
        if not clean_name or self.tool_registry is None:
            return None

        get_tool = getattr(self.tool_registry, "get_tool", None)
        if callable(get_tool):
            try:
                tool = get_tool(clean_name)
                if tool is not None:
                    return tool
            except Exception:
                pass

        tools = getattr(self.tool_registry, "tools", None)
        if isinstance(tools, dict):
            return tools.get(clean_name)

        private_tools = getattr(self.tool_registry, "_tools", None)
        if isinstance(private_tools, dict):
            return private_tools.get(clean_name)

        return None

    def _run_tool(self, tool: Any, tool_args: Dict[str, Any]) -> Any:
        execute_method = getattr(tool, "execute", None)
        if callable(execute_method):
            try:
                return execute_method(tool_args)
            except TypeError:
                pass

        run_method = getattr(tool, "run", None)
        if callable(run_method):
            return run_method(**tool_args)

        call_method = getattr(tool, "__call__", None)
        if callable(call_method):
            return call_method(**tool_args)

        raise RuntimeError(
            f"Tool '{getattr(tool, 'name', str(tool))}' has no callable execute/run method."
        )

    def _extract_error_from_tool_result(self, tool_result: Any) -> Optional[str]:
        if isinstance(tool_result, dict):
            error = tool_result.get("error")
            if error:
                return str(error)
        return None

    # =========================================================
    # Result Normalization
    # =========================================================

    def _normalize_runtime_result(self, runtime_result: Any) -> Dict[str, Any]:
        if isinstance(runtime_result, dict):
            success = bool(runtime_result.get("success", True))
            summary = str(runtime_result.get("summary", "Task executed."))
            data = runtime_result.get("data", runtime_result)
            error = runtime_result.get("error")
            return {
                "success": success,
                "summary": summary,
                "data": data,
                "error": error,
            }

        if isinstance(runtime_result, str):
            return {
                "success": True,
                "summary": "Task executed.",
                "data": {"answer": runtime_result},
                "error": None,
            }

        if runtime_result is None:
            return {
                "success": True,
                "summary": "Task executed with no result.",
                "data": {},
                "error": None,
            }

        return {
            "success": True,
            "summary": "Task executed.",
            "data": {"result": runtime_result},
            "error": None,
        }

    # =========================================================
    # Common Helpers
    # =========================================================

    def _build_response(
        self,
        success: bool,
        mode: str,
        summary: str,
        data: Dict[str, Any],
        error: Optional[str],
    ) -> Dict[str, Any]:
        return {
            "success": success,
            "mode": mode,
            "summary": summary,
            "data": data,
            "error": error,
        }

    def _normalize_tool_name(self, value: Any) -> Optional[str]:
        if value is None:
            return None

        text = str(value).strip()
        if not text:
            return None

        if text.lower() == "none":
            return None

        return text

    def _make_task_name(self, task_type: str) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        return f"{task_type}_task_{stamp}"

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()