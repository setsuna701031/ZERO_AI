from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class CommandObject:
    """
    統一命令物件

    所有 Chat / CLI 入口，最後都要轉成這個格式。
    """
    command: str
    args: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command": self.command,
            "args": self.args,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CommandObject":
        if not isinstance(data, dict):
            raise ValueError("CommandObject.from_dict expects a dictionary.")

        command = data.get("command", "")
        args = data.get("args", {})

        if not isinstance(command, str) or not command.strip():
            raise ValueError("CommandObject.command must be a non-empty string.")

        if args is None:
            args = {}

        if not isinstance(args, dict):
            raise ValueError("CommandObject.args must be a dictionary.")

        return cls(command=command.strip(), args=args)


@dataclass
class CommandResult:
    """
    統一命令回傳物件
    """
    success: bool
    command: str
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "command": self.command,
            "message": self.message,
            "data": self.data,
            "error": self.error,
        }

    @classmethod
    def ok(
        cls,
        command: str,
        message: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> "CommandResult":
        return cls(
            success=True,
            command=command,
            message=message,
            data=data or {},
            error=None,
        )

    @classmethod
    def fail(
        cls,
        command: str,
        message: str,
        error: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> "CommandResult":
        return cls(
            success=False,
            command=command,
            message=message,
            data=data or {},
            error=error,
        )