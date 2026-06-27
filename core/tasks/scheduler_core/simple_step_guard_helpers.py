from __future__ import annotations

import copy
from typing import Any, Dict, Tuple


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
            "scope": effective_scope,
        }

    elif step_type == "append_file":
        raw_path = str(prepared_step.get("path") or "").strip()
        if not raw_path:
            raise ValueError("append_file step missing path")
        guard_step = {
            "type": "append_file",
            "path": raw_path,
            "content": str(prepared_step.get("content") or ""),
            "scope": effective_scope,
        }

    elif step_type == "code_edit":
        raw_path = str(prepared_step.get("path") or prepared_step.get("file") or "").strip()
        if not raw_path:
            raise ValueError("code_edit step missing path")

        edit_mode = str(prepared_step.get("edit_mode") or "").strip().lower()
        if edit_mode == "direct_workspace_edit":
            effective_scope = "shared"

        guard_step = {
            "type": "write_file",
            "path": raw_path,
            "content": "",
            "scope": effective_scope,
            "edit_mode": edit_mode,
            "target_policy": str(prepared_step.get("target_policy") or ""),
        }

    return prepared_step, guard_step, effective_scope
