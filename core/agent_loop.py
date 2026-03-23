from __future__ import annotations

from typing import Any, Dict, Optional


class AgentLoop:
    """
    ZERO Agent Loop (Runtime 版)

    流程：
    User Input
        ↓
    TaskManager.create_task(...)
        ↓
    TaskRuntime.run_task(...)
        ↓
    Refresh latest task state
        ↓
    Output Result
    """

    def __init__(
        self,
        task_manager: Any = None,
        task_runtime: Any = None,
        **kwargs: Any,
    ) -> None:
        self.task_manager = task_manager
        self.task_runtime = task_runtime
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

        if self.task_manager is None:
            return self._build_response(
                success=False,
                mode="system",
                summary="Task manager is not available.",
                data={},
                error="task_manager is not configured.",
            )

        if self.task_runtime is None:
            return self._build_response(
                success=False,
                mode="system",
                summary="Task runtime is not available.",
                data={},
                error="task_runtime is not configured.",
            )

        # 1) 建立任務
        try:
            task = self.task_manager.create_task(user_input)
        except Exception as exc:
            return self._build_response(
                success=False,
                mode="task",
                summary="Failed to create task.",
                data={},
                error=str(exc),
            )

        if not isinstance(task, dict):
            return self._build_response(
                success=False,
                mode="task",
                summary="Task manager returned invalid task.",
                data={"raw_task": task},
                error="create_task(...) must return a dict.",
            )

        task_name = str(task.get("task_name", "")).strip()

        # 2) 執行任務
        try:
            runtime_result = self.task_runtime.run_task(task)
        except Exception as exc:
            latest_task = self._refresh_task(task_name, fallback_task=task)
            return self._build_response(
                success=False,
                mode="runtime",
                summary="Task runtime execution failed.",
                data={"task": latest_task},
                error=str(exc),
            )

        # 3) 正規化 runtime 結果
        normalized_result = self._normalize_runtime_result(runtime_result)

        # 4) 重新讀取最新 task 狀態
        latest_task = self._refresh_task(task_name, fallback_task=task)

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
    # Helpers
    # =========================================================

    def _refresh_task(
        self,
        task_name: str,
        fallback_task: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not task_name:
            return fallback_task

        get_task_method = getattr(self.task_manager, "get_task", None)
        if not callable(get_task_method):
            return fallback_task

        try:
            latest_task = get_task_method(task_name)
        except Exception:
            return fallback_task

        if isinstance(latest_task, dict):
            return latest_task

        return fallback_task

    def _normalize_runtime_result(self, runtime_result: Any) -> Dict[str, Any]:
        """
        允許 TaskRuntime.run_task(...) 回傳不同格式，
        這裡統一整理成固定結構。
        """

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