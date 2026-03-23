from __future__ import annotations

import locale
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional


class CommandTool:
    """
    安全版命令工具：
    1. 預設在 workspace_root 內執行
    2. 阻擋高風險命令
    3. 支援 execute(payload_dict) 與 run(**kwargs)
    4. 盡量修正 Windows cmd 輸出亂碼
    """

    name = "command_tool"
    description = "Execute safe shell commands inside the workspace directory."

    def __init__(self, workspace_root: Path | str) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)

        self.blocked_fragments = [
            "del /f /q",
            "rmdir /s /q",
            "format ",
            "shutdown ",
            "restart-computer",
            "stop-computer",
            "remove-item -recurse -force",
            "rm -rf /",
            "sudo rm -rf /",
            "mkfs",
            "diskpart",
            "bcdedit",
            "reg delete",
            "net user",
            "cipher /w",
        ]

    def execute(self, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = payload or {}

        if not isinstance(payload, dict):
            raise ValueError("payload must be a dict.")

        return self.run(
            command=payload.get("command", ""),
            cwd=payload.get("cwd"),
            timeout=int(payload.get("timeout", 20)),
            shell=bool(payload.get("shell", True)),
        )

    def run(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 20,
        shell: bool = True,
    ) -> Dict[str, Any]:
        if not isinstance(command, str) or command.strip() == "":
            raise ValueError("command cannot be empty.")

        normalized_command = command.strip()
        self._guard_command(normalized_command)

        run_cwd = self._resolve_cwd(cwd)

        if os.name == "nt":
            completed = self._run_windows_command(
                command=normalized_command,
                cwd=run_cwd,
                timeout=timeout,
                shell=shell,
            )
        else:
            completed = self._run_posix_command(
                command=normalized_command,
                cwd=run_cwd,
                timeout=timeout,
                shell=shell,
            )

        return {
            "ok": completed["returncode"] == 0,
            "success": completed["returncode"] == 0,
            "tool_name": self.name,
            "summary": f"Executed command: {normalized_command}",
            "action": "execute_command",
            "command": normalized_command,
            "cwd": str(run_cwd),
            "returncode": completed["returncode"],
            "stdout": completed["stdout"],
            "stderr": completed["stderr"],
            "encoding_used": completed.get("encoding_used", ""),
            "changed_files": [],
            "evidence": [],
            "results": [],
        }

    def _run_windows_command(
        self,
        command: str,
        cwd: Path,
        timeout: int,
        shell: bool,
    ) -> Dict[str, Any]:
        """
        Windows 下優先用 bytes 方式抓輸出，再自己嘗試解碼，
        避免 cp950 / utf-8 / OEM code page 混亂造成亂碼。
        """
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        wrapped_command = f"chcp 65001>nul & {command}"

        completed = subprocess.run(
            wrapped_command if shell else shlex.split(command, posix=False),
            cwd=str(cwd),
            capture_output=True,
            text=False,
            timeout=timeout,
            shell=shell,
            env=env,
        )

        stdout_text, stdout_encoding = self._decode_windows_bytes(completed.stdout)
        stderr_text, stderr_encoding = self._decode_windows_bytes(completed.stderr)

        encoding_used = stdout_encoding or stderr_encoding or ""

        return {
            "returncode": completed.returncode,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "encoding_used": encoding_used,
        }

    def _run_posix_command(
        self,
        command: str,
        cwd: Path,
        timeout: int,
        shell: bool,
    ) -> Dict[str, Any]:
        completed = subprocess.run(
            command if shell else shlex.split(command, posix=False),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=shell,
            encoding="utf-8",
            errors="replace",
        )

        return {
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "encoding_used": "utf-8",
        }

    def _decode_windows_bytes(self, data: bytes) -> tuple[str, str]:
        if not data:
            return "", ""

        candidates = []

        try:
            preferred = locale.getpreferredencoding(False)
            if preferred:
                candidates.append(preferred)
        except Exception:
            pass

        candidates.extend(
            [
                "utf-8",
                "cp950",
                "cp936",
                "cp932",
                "cp949",
                "mbcs",
                "oem",
                "latin-1",
            ]
        )

        seen = set()
        ordered_candidates = []
        for enc in candidates:
            key = str(enc).lower()
            if key not in seen:
                seen.add(key)
                ordered_candidates.append(enc)

        for enc in ordered_candidates:
            try:
                return data.decode(enc), enc
            except Exception:
                continue

        return data.decode("utf-8", errors="replace"), "utf-8-replace"

    def _resolve_cwd(self, cwd: Optional[str]) -> Path:
        if cwd is None or str(cwd).strip() == "":
            return self.workspace_root

        target = (self.workspace_root / str(cwd)).resolve()

        try:
            target.relative_to(self.workspace_root)
        except ValueError as exc:
            raise ValueError("cwd escapes workspace root, operation denied.") from exc

        if not target.exists():
            raise FileNotFoundError(f"cwd not found: {target}")

        if not target.is_dir():
            raise NotADirectoryError(f"cwd is not a directory: {target}")

        return target

    def _guard_command(self, command: str) -> None:
        lowered = command.lower()

        for fragment in self.blocked_fragments:
            if fragment in lowered:
                raise PermissionError(f"Blocked dangerous command fragment: {fragment}")

        dangerous_prefixes = [
            "del ",
            "erase ",
            "rmdir ",
            "format ",
            "shutdown ",
            "reg delete ",
            "diskpart",
        ]

        for prefix in dangerous_prefixes:
            if lowered.startswith(prefix):
                raise PermissionError(f"Blocked dangerous command: {command}")

        if lowered.startswith("powershell") and "remove-item" in lowered:
            raise PermissionError("Blocked dangerous PowerShell remove command.")

        if lowered.startswith("cmd") and "/c del " in lowered:
            raise PermissionError("Blocked dangerous cmd delete command.")