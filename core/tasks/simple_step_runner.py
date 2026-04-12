from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from typing import Any, Dict


class SimpleStepRunner:
    """
    從 Scheduler 拆出的 simple step execution helper。

    目前責任：
    1. 執行 simple task step
    2. resolve task sandbox path
    3. resolve shared / task-local read-write path
    4. 經過 execution_guard 做安全檢查
    """

    def __init__(self, scheduler: Any) -> None:
        self.scheduler = scheduler

    @property
    def execution_guard(self) -> Any:
        return self.scheduler.execution_guard

    @property
    def shared_dir(self) -> str:
        return self.scheduler.shared_dir

    @property
    def tasks_root(self) -> str:
        return self.scheduler.tasks_root

    def extract_task_id(self, task: Dict[str, Any]) -> str:
        return self.scheduler._extract_task_id(task)

def _execute_simple_step(
    self,
    task: Dict[str, Any],
    step: Dict[str, Any],
) -> Dict[str, Any]:
    step_type = str(step.get("type") or "").strip().lower()
    task_dir = self._resolve_task_dir(task)

    guard_step = copy.deepcopy(step)

    if step_type == "run_python":
        run_path = str(step.get("path") or "").strip()
        if not run_path:
            raise ValueError("run_python step missing path")
        guard_step = {
            "type": "command",
            "command": f'{sys.executable} "{run_path}"',
        }

    elif step_type == "verify":
        guard_step = {
            "type": "noop",
            "message": "verify",
        }

    elif step_type == "ensure_file":
        raw_path = str(step.get("path") or "").strip()
        if not raw_path:
            raise ValueError("ensure_file step missing path")
        guard_step = {
            "type": "write_file",
            "path": raw_path,
            "content": "",
        }

    guard_result = self.execution_guard.check_step(step=guard_step, task_dir=task_dir)
    if not bool(guard_result.get("ok")):
        raise PermissionError(str(guard_result.get("error") or "guard blocked execution"))

    if step_type == "noop":
        return {
            "type": "noop",
            "message": str(step.get("message") or "noop ok"),
        }

    if step_type == "ensure_file":
        raw_path = str(step.get("path") or "").strip()
        if not raw_path:
            raise ValueError("ensure_file step missing path")

        full_path = str(guard_result.get("resolved_path") or "")
        if not full_path:
            full_path = self._resolve_step_path(raw_path, task_dir=task_dir, shared_dir=self.shared_dir)

        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        created = False
        if not os.path.exists(full_path):
            with open(full_path, "w", encoding="utf-8") as f:
                f.write("")
            created = True

        return {
            "type": "ensure_file",
            "path": raw_path,
            "full_path": full_path,
            "created": created,
            "preserved_existing": not created,
        }

    if step_type == "write_file":
        raw_path = str(step.get("path") or "").strip()
        if not raw_path:
            raise ValueError("write_file step missing path")

        content = step.get("content", "")
        if content is None:
            content = ""
        content = str(content)

        full_path = str(guard_result.get("resolved_path") or "")
        if not full_path:
            full_path = self._resolve_step_path(raw_path, task_dir=task_dir, shared_dir=self.shared_dir)

        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

        return {
            "type": "write_file",
            "path": raw_path,
            "full_path": full_path,
            "bytes": len(content.encode("utf-8")),
            "content": content,
        }

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
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "cwd": task_dir,
        }

        if completed.returncode != 0:
            raise RuntimeError(
                f"command failed: {command} | returncode={completed.returncode} | stderr={completed.stderr.strip()}"
            )

        return result

    if step_type == "run_python":
        raw_path = str(step.get("path") or "").strip()
        if not raw_path:
            raise ValueError("run_python step missing path")

        full_path = self._resolve_read_path_with_fallback(
            raw_path=raw_path,
            task_dir=task_dir,
            shared_dir=self.shared_dir,
        )

        read_guard = self.execution_guard.check_step(
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
            "python_executable": sys.executable,
            "returncode": int(completed.returncode),
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "cwd": task_dir,
        }

        if completed.returncode != 0:
            raise RuntimeError(
                f"python run failed: {raw_path} | returncode={completed.returncode} | stderr={completed.stderr.strip()}"
            )

        return result

    if step_type == "read_file":
        raw_path = str(step.get("path") or "").strip()
        if not raw_path:
            raise ValueError("read_file step missing path")

        full_path = self._resolve_read_path_with_fallback(
            raw_path=raw_path,
            task_dir=task_dir,
            shared_dir=self.shared_dir,
        )

        guard_check = self.execution_guard.check_step(
            step={"type": "read_file", "path": full_path},
            task_dir=task_dir,
        )
        if not bool(guard_check.get("ok")):
            raise PermissionError(str(guard_check.get("error") or "guard blocked read"))

        if not os.path.exists(full_path):
            raise FileNotFoundError(f"file not found: {full_path}")

        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        return {
            "type": "read_file",
            "path": raw_path,
            "full_path": full_path,
            "content": content,
        }

    if step_type == "verify":
        contains = str(step.get("contains") or "").strip()
        equals = step.get("equals", None)
        path = str(step.get("path") or "").strip()

        if not contains and equals is None and not path:
            raise ValueError("verify step requires contains / equals / path")

        target_text = ""

        if path:
            full_path = self._resolve_read_path_with_fallback(
                raw_path=path,
                task_dir=task_dir,
                shared_dir=self.shared_dir,
            )

            read_guard = self.execution_guard.check_step(
                step={"type": "read_file", "path": full_path},
                task_dir=task_dir,
            )
            if not bool(read_guard.get("ok")):
                raise PermissionError(str(read_guard.get("error") or "guard blocked verify read"))

            if not os.path.exists(full_path):
                raise FileNotFoundError(f"verify file not found: {full_path}")

            with open(full_path, "r", encoding="utf-8") as f:
                target_text = f.read()
        else:
            last = task.get("last_step_result")
            if isinstance(last, dict):
                last_result = last.get("result")
                if isinstance(last_result, dict):
                    if "stdout" in last_result:
                        target_text = str(last_result.get("stdout") or "")
                    elif "content" in last_result:
                        target_text = str(last_result.get("content") or "")
                    else:
                        target_text = json.dumps(last_result, ensure_ascii=False)
                else:
                    target_text = str(last_result or "")

        if contains:
            if contains not in target_text:
                raise RuntimeError(f"verify failed: '{contains}' not found")

        if equals is not None:
            expected = str(equals)
            if str(target_text).strip() != expected.strip():
                raise RuntimeError(
                    f"verify failed: expected exact match '{expected}', got '{str(target_text).strip()}'"
                )

        return {
            "type": "verify",
            "ok": True,
            "contains": contains,
            "equals": equals,
            "path": path,
            "checked_text": target_text,
        }

    raise ValueError(f"unsupported step type: {step_type}")

def _resolve_task_dir(self, task: Dict[str, Any]) -> str:
    task_dir = str(task.get("task_dir") or "").strip()
    if not task_dir:
        task_name = str(task.get("task_name") or self._extract_task_id(task) or "unknown_task")
        task_dir = os.path.join(self.tasks_root, task_name)

    sandbox_dir = os.path.join(task_dir, "sandbox")
    os.makedirs(sandbox_dir, exist_ok=True)
    return sandbox_dir

def _resolve_step_path(self, raw_path: str, task_dir: str, shared_dir: str) -> str:
    normalized = raw_path.replace("\\", "/").strip()

    if os.path.isabs(normalized):
        return os.path.abspath(normalized)

    if normalized.startswith("workspace/shared/"):
        relative_part = normalized[len("workspace/shared/"):].strip("/")
        return os.path.abspath(os.path.join(shared_dir, relative_part))

    if normalized.startswith("shared/"):
        relative_part = normalized[len("shared/"):].strip("/")
        return os.path.abspath(os.path.join(shared_dir, relative_part))

    return os.path.abspath(os.path.join(task_dir, normalized))

def _resolve_read_path_with_fallback(self, raw_path: str, task_dir: str, shared_dir: str) -> str:
    normalized = raw_path.replace("\\", "/").strip()

    if os.path.isabs(normalized):
        return os.path.abspath(normalized)

    if normalized.startswith("workspace/shared/"):
        relative_part = normalized[len("workspace/shared/"):].strip("/")
        return os.path.abspath(os.path.join(shared_dir, relative_part))

    if normalized.startswith("shared/"):
        relative_part = normalized[len("shared/"):].strip("/")
        return os.path.abspath(os.path.join(shared_dir, relative_part))

    task_local = os.path.abspath(os.path.join(task_dir, normalized))
    if os.path.exists(task_local):
        return task_local

    shared_fallback = os.path.abspath(os.path.join(shared_dir, normalized))
    if os.path.exists(shared_fallback):
        return shared_fallback

    return task_local
