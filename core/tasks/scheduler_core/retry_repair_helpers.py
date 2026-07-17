from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Tuple

from core.tasks.scheduler_core.repair_injection_execution import safe_repair_injection_now


def _zero_v734_safe_now() -> str:
    return safe_repair_injection_now()


def _zero_v734_extract_nested_dict(payload: Any, keys: List[str]) -> Dict[str, Any]:
    current = payload
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def _zero_v734_extract_compile_target_from_step(step: Dict[str, Any]) -> str:
    if not isinstance(step, dict):
        return ""
    for key in ("path", "target_path", "file_path"):
        value = str(step.get(key) or "").strip()
        if value.endswith(".py"):
            return value

    command = str(step.get("command") or step.get("cmd") or "").strip()
    if not command:
        return ""

    match = re.search(r"py_compile\s+([^\s\"']+\.py)", command)
    if match:
        return match.group(1).strip().strip('"').strip("'")

    match = re.search(r"([^\s\"']+\.py)", command)
    if match:
        return match.group(1).strip().strip('"').strip("'")

    return ""


def _zero_v734_resolve_retry_compile_file(task: Dict[str, Any], failed_step: Dict[str, Any]) -> Tuple[str, str, str]:
    target = _zero_v734_extract_compile_target_from_step(failed_step)
    if not target:
        return "", "", ""

    cwd = str(failed_step.get("command_cwd") or failed_step.get("cwd") or "").strip()
    task_dir = str(task.get("task_dir") or "").strip()
    sandbox_dir = str(task.get("sandbox_dir") or "").strip()

    if not sandbox_dir and task_dir:
        sandbox_dir = os.path.join(task_dir, "sandbox")

    if not cwd:
        cwd = sandbox_dir or task_dir or os.getcwd()

    if os.path.isabs(target):
        full_path = os.path.abspath(target)
        rel_path = os.path.basename(target)
    else:
        full_path = os.path.abspath(os.path.join(cwd, target))
        rel_path = target.replace("\\", "/").lstrip("./")

    return full_path, rel_path, cwd


def _zero_v734_synthesize_python_compile_fix(source: str) -> Tuple[bool, str, str]:
    if not isinstance(source, str) or not source.strip():
        return False, source, "empty source"

    lines = source.splitlines()
    if not lines:
        return False, source, "empty source lines"

    fixed = list(lines)
    changed = False

    current_args: List[str] = []
    for index, line in enumerate(lines):
        def_match = re.match(r"^\s*def\s+[A-Za-z_]\w*\s*\(([^)]*)\)\s*:", line)
        if def_match:
            raw_args = def_match.group(1)
            parsed_args: List[str] = []
            for item in raw_args.split(","):
                name = item.strip().split("=")[0].strip()
                if ":" in name:
                    name = name.split(":", 1)[0].strip()
                if name and re.match(r"^[A-Za-z_]\w*$", name):
                    parsed_args.append(name)
            current_args = parsed_args
            continue

        return_match = re.match(r"^(\s*return\s+)([A-Za-z_]\w*)\s*\+\s*$", line)
        if not return_match:
            continue

        left_name = return_match.group(2)
        replacement_name = ""
        for candidate in current_args:
            if candidate != left_name:
                replacement_name = candidate
                break
        if not replacement_name and len(current_args) >= 2:
            replacement_name = current_args[1]
        if not replacement_name:
            replacement_name = "0"

        fixed[index] = f"{return_match.group(1)}{left_name} + {replacement_name}"
        changed = True

    if not changed:
        return False, source, "no supported incomplete return expression found"

    fixed_source = "\n".join(fixed)
    if source.endswith("\n"):
        fixed_source += "\n"
    return True, fixed_source, "fixed incomplete return expression"


def _zero_v734_build_retry_repair_steps(
    task: Dict[str, Any],
    failed_step: Dict[str, Any],
) -> Tuple[bool, List[Dict[str, Any]], Dict[str, Any]]:
    full_path, rel_path, cwd = _zero_v734_resolve_retry_compile_file(task, failed_step)
    if not full_path or not rel_path:
        return False, [], {"reason": "compile target not found"}

    try:
        with open(full_path, "r", encoding="utf-8") as f:
            source = f.read()
    except Exception as exc:
        return False, [], {
            "reason": "failed to read compile target",
            "path": full_path,
            "error": f"{type(exc).__name__}: {exc}",
        }

    ok, fixed_source, reason = _zero_v734_synthesize_python_compile_fix(source)
    if not ok:
        return False, [], {
            "reason": reason,
            "path": full_path,
        }

    repair_id_base = "auto_repair_compile_syntax"
    repair_steps = [
        {
            "id": f"{repair_id_base}_write",
            "type": "write_file",
            "path": rel_path,
            "content": fixed_source,
            "scope": "sandbox",
            "command_cwd": cwd,
            "repair_generated": True,
            "repair_source": "scheduler_retrying_repair_bridge_v1",
            "repair_reason": reason,
        },
        {
            "id": f"{repair_id_base}_verify",
            "type": "run_python",
            "command": f"python -m py_compile {rel_path}",
            "command_cwd": cwd,
            "repair_generated": True,
            "repair_source": "scheduler_retrying_repair_bridge_v1",
            "repair_reason": "verify repaired python file compiles",
        },
    ]
    return True, repair_steps, {
        "reason": reason,
        "path": full_path,
        "relative_path": rel_path,
        "cwd": cwd,
        "original_content": source,
        "fixed_content": fixed_source,
    }


def _zero_v734_task_allows_auto_repair(task: Dict[str, Any]) -> bool:
    if not isinstance(task, dict):
        return False

    for key in ("auto_repair", "auto-repair", "planner_autonomous_repair", "autonomous_repair", "repair_enabled"):
        if bool(task.get(key, False)):
            return True

    goal = str(task.get("goal") or task.get("title") or "").strip().lower()
    if "auto repair" in goal or "autonomous repair" in goal:
        return True

    repair_context = task.get("repair_context")
    if isinstance(repair_context, dict):
        session = repair_context.get("repair_session")
        if isinstance(session, dict) and bool(session.get("enabled")):
            return True
        strategy = repair_context.get("strategy")
        if isinstance(strategy, dict) and strategy.get("current_strategy"):
            return True

    return False


def _zero_v734_runtime_state_file_for_task(task: Dict[str, Any]) -> str:
    if not isinstance(task, dict):
        return ""
    value = str(task.get("runtime_state_file") or "").strip()
    if value:
        return value
    task_dir = str(task.get("task_dir") or "").strip()
    if task_dir:
        return os.path.join(task_dir, "runtime_state.json")
    return ""


def _zero_v734_read_runtime_state(task: Dict[str, Any]) -> Dict[str, Any]:
    path = _zero_v734_runtime_state_file_for_task(task)
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _zero_v734_write_runtime_state(task: Dict[str, Any], state: Dict[str, Any]) -> None:
    path = _zero_v734_runtime_state_file_for_task(task)
    if not path or not isinstance(state, dict):
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
