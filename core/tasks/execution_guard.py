from __future__ import annotations

import os
import re
import shlex
from typing import Any, Dict, Optional


class ExecutionGuard:
    """
    最小可用執行守門員（收束修正版）

    目標：
    1. 所有 write_file / read_file / command 都先經過這裡
    2. 限制檔案操作只能在 workspace_root 之下
    3. command 預設關閉
    4. 收束期只有限放行安全 python command
    5. llm / llm_generate / verify / respond 視為非副作用 step，可直接放行
    6. 允許 trusted python interpreter + trusted script path
    """

    def __init__(
        self,
        workspace_root: str,
        shared_dir: str,
        allow_commands: bool = False,
    ) -> None:
        self.workspace_root = os.path.abspath(workspace_root)
        self.shared_dir = os.path.abspath(shared_dir)
        self.allow_commands = bool(allow_commands)

        # 專案根目錄 = workspace 的上一層
        self.project_root = os.path.abspath(os.path.join(self.workspace_root, os.pardir))

        # 收束期可信腳本白名單（位於 project root）
        self.trusted_project_scripts = {
            "main.py",
        }

    def check_step(
        self,
        step: Dict[str, Any],
        task_dir: str,
    ) -> Dict[str, Any]:
        step_type = str(step.get("type") or "").strip().lower()
        task_dir_abs = os.path.abspath(task_dir)

        # ---------------------------------------------------------
        # 無副作用 / 純判定 / 純生成 step
        # ---------------------------------------------------------
        if step_type in {
            "noop",
            "llm",
            "llm_generate",
            "verify",
            "verify_file",
            "respond",
            "final_answer",
        }:
            return {"ok": True}

        # ---------------------------------------------------------
        # write
        # ---------------------------------------------------------
        if step_type in {"write_file", "ensure_file"}:
            raw_path = str(step.get("path") or "").strip()
            if not raw_path:
                return {"ok": False, "error": f"{step_type} step missing path"}

            full_path = self._resolve_path(raw_path=raw_path, task_dir=task_dir_abs)
            if not self._is_under_workspace(full_path):
                return {
                    "ok": False,
                    "error": f"{step_type} blocked: path outside workspace: {full_path}",
                }

            return {
                "ok": True,
                "resolved_path": full_path,
            }

        # ---------------------------------------------------------
        # read
        # ---------------------------------------------------------
        if step_type == "read_file":
            raw_path = str(step.get("path") or "").strip()
            if not raw_path:
                return {"ok": False, "error": "read_file step missing path"}

            full_path = self._resolve_path(raw_path=raw_path, task_dir=task_dir_abs)
            if not self._is_under_workspace(full_path):
                return {
                    "ok": False,
                    "error": f"read_file blocked: path outside workspace: {full_path}",
                }

            return {
                "ok": True,
                "resolved_path": full_path,
            }

        # ---------------------------------------------------------
        # run_python
        # ---------------------------------------------------------
        if step_type == "run_python":
            raw_path = str(step.get("path") or "").strip()
            if not raw_path:
                return {"ok": False, "error": "run_python step missing path"}

            script_path = self._resolve_script_path(raw_path=raw_path, task_dir=task_dir_abs)
            if self._is_allowed_python_script(script_path):
                return {
                    "ok": True,
                    "guard_mode": "safe_run_python",
                    "resolved_script_path": script_path,
                }

            return {
                "ok": False,
                "error": f"python script blocked by guard: {script_path}",
            }

        # ---------------------------------------------------------
        # command
        # ---------------------------------------------------------
        if step_type == "command":
            command = str(step.get("command") or "").strip()
            if not command:
                return {"ok": False, "error": "command step missing command"}

            return self._check_command(command=command, task_dir=task_dir_abs)

        return {
            "ok": False,
            "error": f"unsupported step type: {step_type}",
        }

    def _check_command(self, command: str, task_dir: str) -> Dict[str, Any]:
        normalized = str(command or "").strip()
        lowered = normalized.lower()

        # Never allow ZERO to recursively call its own task runner from inside a task.
        # This guard stays active even when allow_commands=True.
        if self._is_self_invoking_zero_command(normalized):
            return {
                "ok": False,
                "error": "command blocked: self-invoking ZERO task command",
                "guard_mode": "blocked_self_invoking_zero_task",
            }

        if self.allow_commands:
            return {"ok": True}

        # 收束期白名單：
        # 1. python -c "print(...)"
        # 2. trusted python interpreter + trusted script path
        # 3. 直接執行 .py 也允許，但腳本仍必須落在允許範圍
        if self._is_safe_inline_python(lowered):
            return {"ok": True, "guard_mode": "safe_python_inline"}

        script_info = self._extract_python_script_info(normalized)
        if script_info is not None:
            script_path = self._resolve_script_path(
                raw_path=script_info["script_path"],
                task_dir=task_dir,
            )

            if not self._is_allowed_python_script(script_path):
                return {
                    "ok": False,
                    "error": f"python script blocked by guard: {script_path}",
                }

            return {
                "ok": True,
                "guard_mode": "safe_python_script",
                "resolved_script_path": script_path,
                "python_command": script_info["python_command"],
            }

        return {
            "ok": False,
            "error": "command execution blocked by guard",
        }

    def _is_self_invoking_zero_command(self, command: str) -> bool:
        try:
            parts = shlex.split(command, posix=False)
        except Exception:
            parts = command.split()

        cleaned = [str(part).strip().strip('"').strip("'") for part in parts if str(part).strip()]
        if len(cleaned) < 4:
            return False

        exe = os.path.basename(cleaned[0]).lower()
        if exe not in {"python", "python.exe", "py", "py.exe"}:
            return False

        script = os.path.basename(cleaned[1]).lower()
        if script != "app.py":
            return False

        lowered_args = [item.lower() for item in cleaned[2:]]
        if "task" not in lowered_args:
            return False

        task_index = lowered_args.index("task")
        if task_index + 1 >= len(lowered_args):
            return False

        task_action = lowered_args[task_index + 1]
        return task_action in {"run", "loop", "submit", "rerun", "retry"}

    def _is_safe_inline_python(self, lowered_command: str) -> bool:
        patterns = [
            r'^python\s+-c\s+"print\(.+\)"$',
            r"^python\s+-c\s+'print\(.+\)'$",
            r'^py\s+-c\s+"print\(.+\)"$',
            r"^py\s+-c\s+'print\(.+\)'$",
            r'^python\.exe\s+-c\s+"print\(.+\)"$',
            r"^python\.exe\s+-c\s+'print\(.+\)'$",
            r'^py\.exe\s+-c\s+"print\(.+\)"$',
            r"^py\.exe\s+-c\s+'print\(.+\)'$",
            r'^".*python(?:\.exe)?"\s+-c\s+"print\(.+\)"$',
            r"^'.*python(?:\.exe)?'\s+-c\s+'print\(.+\)'$",
        ]
        return any(re.match(p, lowered_command) for p in patterns)

    def _extract_python_script_info(self, command: str) -> Optional[Dict[str, str]]:
        try:
            parts = shlex.split(command, posix=False)
        except Exception:
            parts = command.split()

        if not parts:
            return None

        first = str(parts[0]).strip().strip('"').strip("'")
        first_lower = first.lower()
        exe_basename = os.path.basename(first_lower)

        # case 1: python/py/python.exe/py.exe <script>
        if exe_basename in {"python", "py", "python.exe", "py.exe"}:
            if len(parts) < 2:
                return None

            second = str(parts[1]).strip().strip('"').strip("'")
            if not second:
                return None

            if second.lower() == "-c":
                return None

            return {
                "python_command": first,
                "script_path": second,
            }

        # case 2: directly running a .py-like script command
        if first_lower.endswith(".py"):
            return {
                "python_command": "",
                "script_path": first,
            }

        return None

    def _resolve_script_path(self, raw_path: str, task_dir: str) -> str:
        clean = str(raw_path or "").strip().strip('"').strip("'")
        if not clean:
            return clean

        if os.path.isabs(clean):
            return os.path.abspath(clean)

        # shared/<file>
        if clean.replace("\\", "/").startswith("shared/"):
            relative_part = clean.replace("\\", "/")[len("shared/"):].strip("/")
            return os.path.abspath(os.path.join(self.shared_dir, relative_part))

        # task local
        candidate_task = os.path.abspath(os.path.join(task_dir, clean))
        if os.path.exists(candidate_task):
            return candidate_task

        # project root
        candidate_project = os.path.abspath(os.path.join(self.project_root, clean))
        if os.path.exists(candidate_project):
            return candidate_project

        # fallback task path
        return candidate_task

    def _is_allowed_python_script(self, script_path: str) -> bool:
        abs_script = os.path.abspath(script_path)

        if self._is_under_workspace(abs_script):
            return True

        if self._is_under_project_root(abs_script):
            rel = os.path.relpath(abs_script, self.project_root).replace("\\", "/")
            if rel in self.trusted_project_scripts:
                return True

        return False

    def _resolve_path(self, raw_path: str, task_dir: str) -> str:
        normalized = str(raw_path or "").replace("\\", "/").strip()

        if os.path.isabs(normalized):
            return os.path.abspath(normalized)

        if normalized.startswith("shared/"):
            relative_part = normalized[len("shared/"):].strip("/")
            return os.path.abspath(os.path.join(self.shared_dir, relative_part))

        return os.path.abspath(os.path.join(task_dir, normalized))

    def _is_under_workspace(self, path: str) -> bool:
        try:
            common = os.path.commonpath([self.workspace_root, os.path.abspath(path)])
            return common == self.workspace_root
        except Exception:
            return False

    def _is_under_project_root(self, path: str) -> bool:
        try:
            common = os.path.commonpath([self.project_root, os.path.abspath(path)])
            return common == self.project_root
        except Exception:
            return False