from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Set

from .command_models import CommandObject, CommandResult
from .task_manager import TaskManager


class CommandDispatcher:
    """
    ZERO Command Dispatcher

    職責：
    - 接收標準 CommandObject
    - 驗證命令是否存在
    - 驗證必要參數
    - 分派到 TaskManager
    - 回傳統一 CommandResult
    """

    def __init__(self, task_manager: Optional[TaskManager] = None) -> None:
        self.task_manager = task_manager or TaskManager()

        # 所有 command 註冊在這裡
        self._handlers: Dict[str, Callable[[Dict[str, Any]], CommandResult]] = {
            "task_new": self.task_manager.task_new,
            "task_list": self.task_manager.task_list,
            "task_show": self.task_manager.task_show,
            "task_status": self.task_manager.task_status,
            "task_plan_show": self.task_manager.task_plan_show,
            "task_resume": self.task_manager.task_resume,
            "task_run_next": self.task_manager.task_run_next,
            "task_rerun_step": self.task_manager.task_rerun_step,
        }

        # 每個 command 必要參數
        self._required_args: Dict[str, Set[str]] = {
            "task_new": {"goal"},
            "task_list": set(),
            "task_show": {"task_id"},
            "task_status": {"task_id"},
            "task_plan_show": {"task_id"},
            "task_resume": {"task_id"},
            "task_run_next": {"task_id"},
            "task_rerun_step": {"task_id", "step_id"},
        }

    def dispatch(self, command_obj: Any) -> CommandResult:
        """
        可接受：
        - CommandObject
        - {"command": "...", "args": {...}} dict
        """
        try:
            normalized_command = self._normalize_command(command_obj)
        except Exception as exc:
            return CommandResult.fail(
                command="unknown",
                message="Failed to dispatch command.",
                error=str(exc),
            )

        command_name = normalized_command.command
        args = normalized_command.args

        if command_name not in self._handlers:
            return CommandResult.fail(
                command=command_name,
                message="Failed to dispatch command.",
                error=f"Unsupported command: {command_name}",
            )

        validation_error = self._validate_required_args(command_name, args)
        if validation_error is not None:
            return CommandResult.fail(
                command=command_name,
                message="Failed to dispatch command.",
                error=validation_error,
            )

        handler = self._handlers[command_name]

        try:
            return handler(args)
        except Exception as exc:
            return CommandResult.fail(
                command=command_name,
                message="Command execution failed.",
                error=str(exc),
            )

    def get_supported_commands(self) -> Dict[str, Set[str]]:
        return {
            name: required.copy()
            for name, required in self._required_args.items()
        }

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _normalize_command(self, command_obj: Any) -> CommandObject:
        if isinstance(command_obj, CommandObject):
            return command_obj

        if isinstance(command_obj, dict):
            return CommandObject.from_dict(command_obj)

        raise ValueError("command_obj must be a CommandObject or dictionary.")

    def _validate_required_args(
        self,
        command_name: str,
        args: Dict[str, Any],
    ) -> Optional[str]:
        required = self._required_args.get(command_name, set())

        if not isinstance(args, dict):
            return "args must be a dictionary."

        missing = []
        for key in required:
            value = args.get(key)
            if value is None:
                missing.append(key)
                continue
            if isinstance(value, str) and not value.strip():
                missing.append(key)

        if missing:
            missing_text = ", ".join(sorted(missing))
            return f"Missing required args for {command_name}: {missing_text}"

        return None