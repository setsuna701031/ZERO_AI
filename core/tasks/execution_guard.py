from __future__ import annotations

import os
import re
import shlex
from typing import Any, Dict, Optional

from core.repo_sandbox.policy import RepoSandboxPolicy


class ExecutionGuard:
    """
    ZERO Execution Guard - S pack policy-layer integration.

    Responsibilities:
    1. Keep all read/write/run/command steps inside controlled workspace boundaries.
    2. Keep command execution conservative by default.
    3. Add a semantic policy layer without replacing the existing hard guard.
    4. Return policy/guard metadata for audit and downstream blocker handling.

    Boundary:
    - This guard only classifies/blocks a step before execution.
    - It does not create blockers by itself; policy->blocker integration belongs to
      the next layer/package.
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

        # Project root = parent of workspace root.
        self.project_root = os.path.abspath(os.path.join(self.workspace_root, os.pardir))

        # Conservative trusted project scripts.  Keep this list intentionally small.
        self.trusted_project_scripts = {
            "main.py",
        }

        # S pack: semantic policy layer.  The hard path/command guard below remains
        # the source of enforcement for execution safety; policy adds repo/sandbox
        # intent checks and structured decision metadata.
        self.policy = RepoSandboxPolicy()

    # ============================================================
    # public
    # ============================================================

    def check_step(
        self,
        step: Dict[str, Any],
        task_dir: str,
    ) -> Dict[str, Any]:
        step = step if isinstance(step, dict) else {}
        step_type = str(step.get("type") or "").strip().lower()
        task_dir_abs = os.path.abspath(task_dir)

        # ---------------------------------------------------------
        # No-side-effect / pure reasoning / pure verification steps
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
            return self._allow(
                guard_mode="no_side_effect_step",
                policy_action="allow",
                policy_reason="step has no direct side effect",
            )

        # ---------------------------------------------------------
        # write
        # ---------------------------------------------------------
        if step_type in {"write_file", "ensure_file"}:
            raw_path = str(step.get("path") or "").strip()
            if not raw_path:
                return self._deny(f"{step_type} step missing path", guard_mode="missing_path")

            policy_result = self._check_path_policy(raw_path, operation=step_type)
            if not policy_result.get("ok"):
                return self._deny(
                    str(policy_result.get("error") or "policy blocked path"),
                    guard_mode="policy_blocked_path",
                    policy_action="deny",
                    policy_reason=str(policy_result.get("policy_reason") or policy_result.get("error") or ""),
                )

            full_path = self._resolve_path(raw_path=raw_path, task_dir=task_dir_abs)
            if not self._is_under_workspace(full_path):
                return self._deny(
                    f"{step_type} blocked: path outside workspace: {full_path}",
                    guard_mode="path_outside_workspace",
                    resolved_path=full_path,
                    policy_action="deny",
                    policy_reason="path outside workspace",
                )

            return self._allow(
                guard_mode="workspace_write",
                resolved_path=full_path,
                policy_action="allow",
                policy_reason=str(policy_result.get("policy_reason") or "path allowed by policy"),
            )

        # ---------------------------------------------------------
        # read
        # ---------------------------------------------------------
        if step_type == "read_file":
            raw_path = str(step.get("path") or "").strip()
            if not raw_path:
                return self._deny("read_file step missing path", guard_mode="missing_path")

            policy_result = self._check_path_policy(raw_path, operation="read_file")
            if not policy_result.get("ok"):
                return self._deny(
                    str(policy_result.get("error") or "policy blocked path"),
                    guard_mode="policy_blocked_path",
                    policy_action="deny",
                    policy_reason=str(policy_result.get("policy_reason") or policy_result.get("error") or ""),
                )

            full_path = self._resolve_path(raw_path=raw_path, task_dir=task_dir_abs)
            if not self._is_under_workspace(full_path):
                return self._deny(
                    f"read_file blocked: path outside workspace: {full_path}",
                    guard_mode="path_outside_workspace",
                    resolved_path=full_path,
                    policy_action="deny",
                    policy_reason="path outside workspace",
                )

            return self._allow(
                guard_mode="workspace_read",
                resolved_path=full_path,
                policy_action="allow",
                policy_reason=str(policy_result.get("policy_reason") or "path allowed by policy"),
            )

        # ---------------------------------------------------------
        # run_python
        # ---------------------------------------------------------
        if step_type == "run_python":
            raw_path = str(step.get("path") or "").strip()
            if not raw_path:
                return self._deny("run_python step missing path", guard_mode="missing_path")

            script_path = self._resolve_script_path(raw_path=raw_path, task_dir=task_dir_abs)
            if self._is_allowed_python_script(script_path):
                return self._allow(
                    guard_mode="safe_run_python",
                    resolved_script_path=script_path,
                    policy_action="allow",
                    policy_reason="python script is in allowed workspace/project path",
                )

            return self._deny(
                f"python script blocked by guard: {script_path}",
                guard_mode="python_script_blocked",
                resolved_script_path=script_path,
                policy_action="deny",
                policy_reason="python script outside allowed workspace/project path",
            )

        # ---------------------------------------------------------
        # command
        # ---------------------------------------------------------
        if step_type == "command":
            command = str(step.get("command") or "").strip()
            if not command:
                return self._deny("command step missing command", guard_mode="missing_command")

            return self._check_command(command=command, task_dir=task_dir_abs)

        return self._deny(
            f"unsupported step type: {step_type}",
            guard_mode="unsupported_step",
            policy_action="deny",
            policy_reason="unsupported step type",
        )

    # ============================================================
    # command guard
    # ============================================================

    def _check_command(self, command: str, task_dir: str) -> Dict[str, Any]:
        normalized = str(command or "").strip()
        lowered = normalized.lower()

        # Never allow ZERO to recursively call its own task runner from inside a task.
        # This guard stays active even when allow_commands=True.
        if self._is_self_invoking_zero_command(normalized):
            return self._deny(
                "command blocked: self-invoking ZERO task command",
                guard_mode="blocked_self_invoking_zero_task",
                policy_action="deny",
                policy_reason="self-invoking ZERO task command",
            )

        # Hard guard override for explicitly enabled command mode.  Still return
        # policy metadata so audit can explain that this was an explicit bypass.
        if self.allow_commands:
            return self._allow(
                guard_mode="commands_explicitly_allowed",
                policy_action="allow",
                policy_reason="allow_commands=True",
            )

        # Existing safe inline Python support.
        if self._is_safe_inline_python(lowered):
            return self._allow(
                guard_mode="safe_python_inline",
                policy_action="allow",
                policy_reason="safe inline python print command",
            )

        # Existing trusted Python script support.
        script_info = self._extract_python_script_info(normalized)
        if script_info is not None:
            script_path = self._resolve_script_path(
                raw_path=script_info["script_path"],
                task_dir=task_dir,
            )

            if not self._is_allowed_python_script(script_path):
                return self._deny(
                    f"python script blocked by guard: {script_path}",
                    guard_mode="python_script_blocked",
                    resolved_script_path=script_path,
                    policy_action="deny",
                    policy_reason="python script outside allowed workspace/project path",
                )

            return self._allow(
                guard_mode="safe_python_script",
                resolved_script_path=script_path,
                python_command=script_info["python_command"],
                policy_action="allow",
                policy_reason="trusted python script path",
            )

        # S pack policy allowlist for test/demo/script commands.
        decision = self.policy.check_command(normalized)
        if decision.allowed:
            return self._allow(
                guard_mode="policy_allowed_command",
                policy_action="allow",
                policy_reason=decision.reason,
            )

        return self._deny(
            f"command execution blocked by guard: {decision.reason}",
            guard_mode="policy_blocked_command",
            policy_action="deny",
            policy_reason=decision.reason,
        )

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

    # ============================================================
    # path / script helpers
    # ============================================================

    def _check_path_policy(self, raw_path: str, operation: str) -> Dict[str, Any]:
        text = str(raw_path or "").strip()
        if not text:
            return {"ok": False, "error": f"{operation} missing path", "policy_reason": "empty path"}

        normalized = text.replace("\\", "/")

        # Absolute paths are governed by the hard workspace boundary below.
        # RepoSandboxPolicy is relative-path oriented, so do not feed absolute
        # Windows paths into it.
        if os.path.isabs(normalized):
            return {"ok": True, "policy_reason": "absolute path deferred to workspace boundary guard"}

        try:
            self.policy.normalize_relative_path(normalized)
        except Exception as exc:
            return {"ok": False, "error": f"policy blocked {operation} path: {exc}", "policy_reason": str(exc)}

        return {"ok": True, "policy_reason": "relative path allowed by repo sandbox policy"}

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

    # ============================================================
    # result helpers
    # ============================================================

    def _allow(self, **extra: Any) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"ok": True}
        payload.update(extra)
        return payload

    def _deny(self, error: str, **extra: Any) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "ok": False,
            "error": str(error or "blocked by execution guard"),
        }
        payload.update(extra)
        return payload
