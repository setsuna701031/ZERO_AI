from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict, Optional, Tuple


def prepare_simple_step_guard(
    scheduler,
    step: Dict[str, Any],
    step_type: str,
    step_scope: str,
) -> Tuple[Dict[str, Any], Dict[str, Any], str]:
    prepared_step = copy.deepcopy(step)
    guard_step = copy.deepcopy(prepared_step)
    effective_scope = step_scope

    if step_type == "run_python":
        run_path = str(prepared_step.get("path") or "").strip()
        if not run_path:
            raise ValueError("run_python step missing path")
        guard_step = {
            "type": "command",
            "command": f'{scheduler.sys_executable if hasattr(scheduler, "sys_executable") else __import__("sys").executable} "{run_path}"',
        }

    elif step_type == "verify":
        prepared_step = scheduler._normalize_verify_step(prepared_step)
        effective_scope = scheduler._normalize_step_scope(prepared_step.get("scope", None))
        guard_step = {
            "type": "noop",
            "message": "verify",
        }

    elif step_type == "ensure_file":
        raw_path = str(prepared_step.get("path") or "").strip()
        if not raw_path:
            raise ValueError("ensure_file step missing path")
        guard_step = {
            "type": "write_file",
            "path": raw_path,
            "content": "",
        }

    return prepared_step, guard_step, effective_scope


def execute_simple_basic_step(
    scheduler,
    task: Dict[str, Any],
    step: Dict[str, Any],
    step_type: str,
    task_dir: str,
    step_scope: str,
    guard_result: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if step_type == "noop":
        return {
            "type": "noop",
            "message": str(step.get("message") or "noop ok"),
        }

    if step_type == "ensure_file":
        raw_path = str(step.get("path") or "").strip()
        if not raw_path:
            raise ValueError("ensure_file step missing path")

        full_path = scheduler._resolve_guard_target_path(
            raw_path=raw_path,
            task_dir=task_dir,
            scope=step_scope,
            resolved_path=str(guard_result.get("resolved_path") or ""),
        )

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
            "scope": step_scope,
            "created": created,
            "preserved_existing": not created,
        }

    if step_type == "write_file":
        raw_path = str(step.get("path") or "").strip()
        if not raw_path:
            raise ValueError("write_file step missing path")

        if bool(step.get("use_previous_text", False)):
            content = scheduler._extract_text_from_previous_result(task)
        else:
            content = step.get("content", "")

        if content is None:
            content = ""
        content = str(content)

        full_path = scheduler._resolve_guard_target_path(
            raw_path=raw_path,
            task_dir=task_dir,
            scope=step_scope,
            resolved_path=str(guard_result.get("resolved_path") or ""),
        )

        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

        return {
            "type": "write_file",
            "path": raw_path,
            "full_path": full_path,
            "scope": step_scope,
            "bytes": len(content.encode("utf-8")),
            "content": content,
            "used_previous_text": bool(step.get("use_previous_text", False)),
        }

    if step_type == "read_file":
        raw_path = str(step.get("path") or "").strip()
        if not raw_path:
            raise ValueError("read_file step missing path")

        full_path = scheduler._resolve_read_path_with_fallback(
            raw_path=raw_path,
            task_dir=task_dir,
            shared_dir=scheduler.shared_dir,
            scope=step_scope,
        )

        guard_check = scheduler.execution_guard.check_step(
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
            "scope": step_scope,
            "content": content,
        }

    if step_type == "verify":
        contains = step.get("contains", None)
        equals = step.get("equals", None)
        exists = step.get("exists", None)
        path = str(step.get("path") or "").strip()

        if contains is None and equals is None and exists is None and not path:
            raise ValueError("verify step requires path / contains / equals / exists")

        target_text = ""
        full_path = ""

        if path:
            full_path = scheduler._resolve_read_path_with_fallback(
                raw_path=path,
                task_dir=task_dir,
                shared_dir=scheduler.shared_dir,
                scope=step_scope,
            )

            read_guard = scheduler.execution_guard.check_step(
                step={"type": "read_file", "path": full_path},
                task_dir=task_dir,
            )
            if not bool(read_guard.get("ok")):
                raise PermissionError(str(read_guard.get("error") or "guard blocked verify read"))

            file_exists = os.path.exists(full_path)

            if exists is True and not file_exists:
                raise FileNotFoundError(f"verify file not found: {full_path}")

            if exists is False and file_exists:
                raise RuntimeError(f"verify failed: file should not exist: {full_path}")

            if (contains is not None or equals is not None or exists is not False) and not file_exists:
                raise FileNotFoundError(f"verify file not found: {full_path}")

            if file_exists and (contains is not None or equals is not None):
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

        if contains is not None:
            contains_text = str(contains)
            if contains_text not in target_text:
                raise RuntimeError(f"verify contains failed: '{contains_text}' not found")

        if equals is not None:
            expected = str(equals)
            if str(target_text).strip() != expected.strip():
                raise RuntimeError(
                    f"verify equals failed: expected exact match '{expected}', got '{str(target_text).strip()}'"
                )

        return {
            "type": "verify",
            "ok": True,
            "path": path,
            "full_path": full_path,
            "scope": step_scope,
            "contains": contains,
            "equals": equals,
            "exists": exists,
            "checked_text": target_text,
            "verified": True,
        }

    return None
