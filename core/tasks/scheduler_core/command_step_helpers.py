from __future__ import annotations

import os
import subprocess
import sys
from typing import Any, Dict, Optional

MAX_COMMAND_OUTPUT_CHARS = 12000


def _truncate_output(value: str, limit: int = MAX_COMMAND_OUTPUT_CHARS) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n<truncated: {len(text) - limit} characters omitted>"


def execute_command_like_step(
    scheduler,
    step: Dict[str, Any],
    step_type: str,
    task_dir: str,
    step_scope: str,
) -> Optional[Dict[str, Any]]:
    if step_type == "command":
        command = str(step.get("command") or "").strip()
        if not command:
            raise ValueError("command step missing command")

        completed = subprocess.run(
            command,
            shell=True,
            cwd=task_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        result = {
            "type": "command",
            "command": command,
            "returncode": int(completed.returncode),
            "stdout": _truncate_output(completed.stdout),
            "stderr": _truncate_output(completed.stderr),
            "stdout_truncated": len(completed.stdout or "") > MAX_COMMAND_OUTPUT_CHARS,
            "stderr_truncated": len(completed.stderr or "") > MAX_COMMAND_OUTPUT_CHARS,
            "cwd": task_dir,
        }

        if completed.returncode != 0:
            raise RuntimeError(
                f"command failed: {command} | returncode={completed.returncode} | stderr={_truncate_output(completed.stderr.strip(), 2000)}"
            )

        return result

    if step_type == "run_python":
        raw_path = str(step.get("path") or "").strip()
        if not raw_path:
            raise ValueError("run_python step missing path")

        full_path = scheduler._resolve_read_path_with_fallback(
            raw_path=raw_path,
            task_dir=task_dir,
            shared_dir=scheduler.shared_dir,
            scope=step_scope,
        )

        read_guard = scheduler.execution_guard.check_step(
            step={"type": "read_file", "path": full_path},
            task_dir=task_dir,
        )
        if not bool(read_guard.get("ok")):
            raise PermissionError(str(read_guard.get("error") or "guard blocked python file read"))

        if not os.path.exists(full_path):
            raise FileNotFoundError(f"python file not found: {full_path}")

        completed = subprocess.run(
            [sys.executable, full_path],
            cwd=task_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        result = {
            "type": "run_python",
            "path": raw_path,
            "full_path": full_path,
            "scope": step_scope,
            "python_executable": sys.executable,
            "returncode": int(completed.returncode),
            "stdout": _truncate_output(completed.stdout),
            "stderr": _truncate_output(completed.stderr),
            "stdout_truncated": len(completed.stdout or "") > MAX_COMMAND_OUTPUT_CHARS,
            "stderr_truncated": len(completed.stderr or "") > MAX_COMMAND_OUTPUT_CHARS,
            "cwd": task_dir,
        }

        if completed.returncode != 0:
            raise RuntimeError(
                f"python run failed: {raw_path} | returncode={completed.returncode} | stderr={_truncate_output(completed.stderr.strip(), 2000)}"
            )

        return result

    return None
