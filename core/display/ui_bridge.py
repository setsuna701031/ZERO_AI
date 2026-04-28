# core/display/ui_bridge.py

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path("workspace")
SHARED_DIR = ROOT / "shared"
TASKS_DIR = ROOT / "tasks"
INBOX_DIR = ROOT / "inbox"


def _safe_read_text(path: Path, max_chars: int = 20000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"[error reading file] {exc}"

    if len(text) > max_chars:
        return text[:max_chars] + f"\n\n[truncated: showing first {max_chars} characters]"
    return text


def _safe_read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None

    if isinstance(data, dict):
        return data
    return {"value": data}


def _safe_name(name: str) -> str:
    return Path(str(name)).name.strip()


def get_latest_summary() -> Optional[str]:
    """
    Return latest *_summary.txt content from workspace/shared.
    """
    if not SHARED_DIR.exists():
        return None

    files = list(SHARED_DIR.glob("*_summary.txt"))
    if not files:
        return None

    latest = max(files, key=lambda f: f.stat().st_mtime)

    try:
        return latest.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"[error reading summary] {exc}"


def get_tasks(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Return latest task runtime info from workspace/tasks.
    """
    if not TASKS_DIR.exists():
        return []

    tasks: List[Dict[str, Any]] = []

    task_dirs = [p for p in TASKS_DIR.iterdir() if p.is_dir()]
    task_dirs = sorted(task_dirs, key=lambda p: p.stat().st_mtime, reverse=True)

    for task_dir in task_dirs:
        runtime_file = task_dir / "runtime_state.json"
        result_file = task_dir / "result.json"

        status = None
        step = None
        goal = None
        final_answer = None

        if runtime_file.exists():
            data = _safe_read_json(runtime_file)
            if data:
                status = data.get("status")
                step = data.get("step")
                goal = data.get("goal")
                final_answer = data.get("final_answer") or data.get("last_result")

        if result_file.exists() and not final_answer:
            result_data = _safe_read_json(result_file)
            if result_data:
                final_answer = (
                    result_data.get("final_answer")
                    or result_data.get("message")
                    or result_data.get("result")
                )

        if runtime_file.exists() or result_file.exists():
            tasks.append(
                {
                    "task_id": task_dir.name,
                    "status": status,
                    "step": step,
                    "goal": goal,
                    "final_answer": final_answer,
                }
            )

        if len(tasks) >= limit:
            break

    return tasks


def get_task_detail(task_id: str, max_chars: int = 20000) -> Dict[str, Any]:
    """
    Return inspectable detail for a single task directory.

    This is display/read-only. It does not execute or mutate the task.
    """
    safe_task_id = _safe_name(task_id)
    if not safe_task_id:
        return {
            "found": False,
            "task_id": task_id,
            "error": "empty task id",
        }

    task_dir = TASKS_DIR / safe_task_id
    if not task_dir.exists() or not task_dir.is_dir():
        return {
            "found": False,
            "task_id": safe_task_id,
            "error": f"task directory not found: {task_dir}",
        }

    files = {
        "runtime_state": task_dir / "runtime_state.json",
        "result": task_dir / "result.json",
        "plan": task_dir / "plan.json",
        "execution_log": task_dir / "execution_log.json",
        "trace": task_dir / "trace.json",
        "task_snapshot": task_dir / "task_snapshot.json",
    }

    parsed: Dict[str, Any] = {}
    raw_text: Dict[str, str] = {}
    available_files: List[str] = []

    for key, path in files.items():
        if not path.exists():
            continue

        available_files.append(path.name)
        data = _safe_read_json(path)
        if data is not None:
            parsed[key] = data
        else:
            raw_text[key] = _safe_read_text(path, max_chars=max_chars)

    runtime = parsed.get("runtime_state", {})
    result = parsed.get("result", {})
    plan = parsed.get("plan", {})

    if not isinstance(runtime, dict):
        runtime = {}
    if not isinstance(result, dict):
        result = {}
    if not isinstance(plan, dict):
        plan = {}

    summary = {
        "task_id": safe_task_id,
        "status": runtime.get("status") or result.get("status"),
        "step": runtime.get("step"),
        "goal": runtime.get("goal") or result.get("goal"),
        "final_answer": (
            result.get("final_answer")
            or result.get("message")
            or runtime.get("final_answer")
            or runtime.get("last_result")
        ),
        "pipeline_name": runtime.get("pipeline_name") or result.get("pipeline_name"),
        "mode": runtime.get("mode") or result.get("mode"),
        "scenario": runtime.get("scenario") or result.get("scenario"),
    }

    steps = plan.get("steps")
    if not isinstance(steps, list):
        steps = []

    return {
        "found": True,
        "task_id": safe_task_id,
        "task_dir": str(task_dir),
        "available_files": available_files,
        "summary": summary,
        "steps": steps,
        "parsed": parsed,
        "raw_text": raw_text,
    }


def get_system_status() -> str:
    """
    Rough system status based on latest task.
    """
    tasks = get_tasks(limit=1)

    if not tasks:
        return "idle"

    latest = tasks[0]
    status = latest.get("status")

    if status in {"running", "executing", "planning", "queued"}:
        return "running"

    return "idle"


def drop_text_file(content: str, filename: Optional[str] = None) -> str:
    """
    Simulate UI drop file -> workspace/inbox.
    """
    INBOX_DIR.mkdir(parents=True, exist_ok=True)

    if not filename:
        import time

        filename = f"ui_drop_{int(time.time())}.txt"

    safe_filename = _safe_name(filename)
    if not safe_filename:
        raise ValueError("invalid filename")

    path = INBOX_DIR / safe_filename
    path.write_text(content, encoding="utf-8")

    return str(path)


def list_shared_files(limit: int = 20) -> List[str]:
    if not SHARED_DIR.exists():
        return []

    files = [p for p in SHARED_DIR.iterdir() if p.is_file()]
    files = sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)

    return [f.name for f in files[:limit]]


def read_shared_file(filename: str, max_chars: int = 20000) -> Dict[str, Any]:
    """
    Read one file from workspace/shared by file name.

    This is intentionally restricted to workspace/shared and strips path parts.
    """
    safe_filename = _safe_name(filename)
    if not safe_filename:
        return {
            "found": False,
            "filename": filename,
            "error": "empty filename",
        }

    path = SHARED_DIR / safe_filename
    if not path.exists() or not path.is_file():
        return {
            "found": False,
            "filename": safe_filename,
            "error": f"shared file not found: {path}",
        }

    return {
        "found": True,
        "filename": safe_filename,
        "path": str(path),
        "content": _safe_read_text(path, max_chars=max_chars),
    }
