from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional


class CommandTool:
    """
    ZERO Command Tool
    ------------------------------------------------------------
    負責 CLI 任務指令：
    - task help
    - task new <goal>
    - task plan <task_id>
    - task run-next <task_id>
    - task status <task_id>
    """

    # 這行非常重要，ToolRegistry 需要
    name = "command_tool"

    def __init__(
        self,
        workspace_root: Optional[str | Path] = None,
        task_manager: Any = None,
        task_runtime: Any = None,
        planner: Any = None,
        **kwargs: Any,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else Path("workspace").resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)

        self.task_manager = task_manager
        self.task_runtime = task_runtime
        self.planner = planner
        self.extra_config = kwargs

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def execute(self, command_text: str) -> Dict[str, Any]:
        return self.run(command_text)

    def run(self, command_text: str) -> Dict[str, Any]:
        if not isinstance(command_text, str) or not command_text.strip():
            return self._result(
                command="task",
                success=False,
                message="Empty command.",
                error="command_text is empty.",
            )

        parts = command_text.strip().split()
        if not parts:
            return self._result(
                command="task",
                success=False,
                message="Empty command.",
                error="command_text is empty.",
            )

        if parts[0] != "task":
            return self._result(
                command=parts[0],
                success=False,
                message="Unknown command.",
                error=f"unsupported root command: {parts[0]}",
            )

        if len(parts) == 1:
            return self._task_help()

        subcommand = parts[1].strip().lower()

        try:
            if subcommand == "help":
                return self._task_help()

            if subcommand == "new":
                goal = " ".join(parts[2:]).strip()
                return self._task_new(goal)

            if subcommand == "plan":
                if len(parts) < 3:
                    return self._result(
                        command="task_plan",
                        success=False,
                        message="Missing task_id.",
                        error="usage: task plan <task_id>",
                    )
                return self._task_plan(parts[2].strip())

            if subcommand == "run-next":
                if len(parts) < 3:
                    return self._result(
                        command="task_run_next",
                        success=False,
                        message="Missing task_id.",
                        error="usage: task run-next <task_id>",
                    )
                return self._task_run_next(parts[2].strip())

            if subcommand == "status":
                if len(parts) < 3:
                    return self._result(
                        command="task_status",
                        success=False,
                        message="Missing task_id.",
                        error="usage: task status <task_id>",
                    )
                return self._task_status(parts[2].strip())

            return self._result(
                command="task",
                success=False,
                message=f"Unknown task subcommand: {subcommand}",
                error=f"unsupported task subcommand: {subcommand}",
            )

        except Exception as exc:
            return self._result(
                command=f"task_{subcommand}",
                success=False,
                message="Command execution failed.",
                error=str(exc),
            )

    # -------------------------------------------------------------------------
    # Task Commands
    # -------------------------------------------------------------------------

    def _task_help(self) -> Dict[str, Any]:
        return self._result(
            command="task_help",
            success=True,
            message="Task help loaded.",
            data={
                "commands": [
                    "task help",
                    "task new <goal>",
                    "task plan <task_id>",
                    "task run-next <task_id>",
                    "task status <task_id>",
                ]
            },
            error=None,
        )

    def _task_new(self, goal: str) -> Dict[str, Any]:
        if not goal:
            return self._result(
                command="task_new",
                success=False,
                message="Task goal is required.",
                error="usage: task new <goal>",
            )

        if self.task_manager is None:
            return self._result(
                command="task_new",
                success=False,
                message="Task manager not available.",
                error="task_manager is not configured.",
            )

        create_task = getattr(self.task_manager, "create_task", None)
        if callable(create_task):
            result = create_task(goal)

            if isinstance(result, dict):
                return self._normalize_manager_result("task_new", result)

            return self._result(
                command="task_new",
                success=True,
                message="Task created.",
                data=result,
                error=None,
            )

        raise RuntimeError("task_manager.create_task() not found.")

    def _task_plan(self, task_id: str) -> Dict[str, Any]:
        if self.planner is None:
            return self._result(
                command="task_plan",
                success=False,
                message="Planner not available.",
                error="planner is not configured.",
            )

        plan_method = getattr(self.planner, "plan", None)
        if not callable(plan_method):
            raise RuntimeError("planner.plan() not found.")

        result = plan_method(task_id=task_id)
        return self._normalize_manager_result("task_plan", result)

    def _task_run_next(self, task_id: str) -> Dict[str, Any]:
        if self.task_runtime is None:
            return self._result(
                command="task_run_next",
                success=False,
                message="Task runtime not available.",
                error="task_runtime is not configured.",
            )

        run_next = getattr(self.task_runtime, "run_next_step", None)
        if callable(run_next):
            result = run_next(task_id)
            return self._normalize_manager_result("task_run_next", result)

        raise RuntimeError("task_runtime.run_next_step() not found.")

    def _task_status(self, task_id: str) -> Dict[str, Any]:
        if self.task_runtime is not None:
            get_status = getattr(self.task_runtime, "get_status", None)
            if callable(get_status):
                result = get_status(task_id)
                return self._normalize_manager_result("task_status", result)

        return self._result(
            command="task_status",
            success=False,
            message="No status provider available.",
            error="task_runtime.get_status not found.",
        )

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _normalize_manager_result(self, command: str, result: Dict[str, Any]) -> Dict[str, Any]:
        success = bool(result.get("success", True))
        message = str(result.get("message") or "OK")
        data = result.get("data")
        error = result.get("error")

        return self._result(
            command=command,
            success=success,
            message=message,
            data=data,
            error=error,
        )

    def _result(
        self,
        command: str,
        success: bool,
        message: str,
        data: Any = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "command": command,
            "success": success,
            "message": message,
            "data": data,
            "error": error,
        }