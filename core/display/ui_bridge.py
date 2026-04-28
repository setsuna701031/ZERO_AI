# core/display/ui_bridge.py

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path("workspace")
SHARED_DIR = ROOT / "shared"
TASKS_DIR = ROOT / "tasks"
INBOX_DIR = ROOT / "inbox"


def _safe_read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _safe_read_text(path: Path, max_chars: int = 12000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"[error reading file] {exc}"

    if len(text) > max_chars:
        return text[:max_chars] + f"\n\n[truncated: showing first {max_chars} characters]"
    return text


def _safe_shared_path(filename: str) -> Optional[Path]:
    name = (filename or "").strip().replace("\\", "/")
    if not name or "/" in name or name in {".", ".."}:
        return None

    path = SHARED_DIR / name
    try:
        resolved = path.resolve()
        shared_resolved = SHARED_DIR.resolve()
        if shared_resolved not in resolved.parents and resolved != shared_resolved:
            return None
    except Exception:
        return None

    return path


def _safe_inbox_path(filename: str) -> Optional[Path]:
    name = (filename or "").strip().replace("\\", "/")
    if not name or "/" in name or name in {".", ".."}:
        return None

    path = INBOX_DIR / name
    try:
        resolved = path.resolve()
        inbox_resolved = INBOX_DIR.resolve()
        if inbox_resolved not in resolved.parents and resolved != inbox_resolved:
            return None
    except Exception:
        return None

    return path


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
    return _safe_read_text(latest)


def list_shared_files(limit: int = 20) -> List[str]:
    """
    Return recent file names under workspace/shared.
    """
    if not SHARED_DIR.exists():
        return []

    files = [f for f in SHARED_DIR.iterdir() if f.is_file()]
    files = sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)

    return [f.name for f in files[:limit]]


def read_shared_file(filename: str, max_chars: int = 12000) -> Optional[Dict[str, Any]]:
    """
    Read a single file from workspace/shared by file name only.
    Path traversal and nested paths are intentionally rejected.
    """
    path = _safe_shared_path(filename)
    if path is None:
        return None

    if not path.exists() or not path.is_file():
        return None

    return {
        "name": path.name,
        "path": str(path),
        "size": path.stat().st_size,
        "modified": path.stat().st_mtime,
        "content": _safe_read_text(path, max_chars=max_chars),
    }


def get_tasks(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Return latest task info from workspace/tasks.
    """
    if not TASKS_DIR.exists():
        return []

    task_dirs = [p for p in TASKS_DIR.iterdir() if p.is_dir()]
    task_dirs = sorted(task_dirs, key=lambda p: p.stat().st_mtime, reverse=True)

    tasks: List[Dict[str, Any]] = []

    for task_dir in task_dirs:
        runtime_file = task_dir / "runtime_state.json"
        result_file = task_dir / "result.json"

        runtime_data = _safe_read_json(runtime_file) if runtime_file.exists() else None
        result_data = _safe_read_json(result_file) if result_file.exists() else None

        if not runtime_data and not result_data:
            continue

        status = None
        step = None
        goal = None
        final_answer = None

        if runtime_data:
            status = runtime_data.get("status")
            step = runtime_data.get("step")
            goal = runtime_data.get("goal")
            final_answer = (
                runtime_data.get("final_answer")
                or runtime_data.get("last_result")
                or runtime_data.get("result")
            )

        if result_data:
            status = result_data.get("status", status)
            goal = result_data.get("goal", goal)
            final_answer = (
                result_data.get("final_answer")
                or result_data.get("answer")
                or result_data.get("message")
                or final_answer
            )

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


def get_task_detail(task_id: str) -> Optional[Dict[str, Any]]:
    """
    Read one task directory from workspace/tasks.
    """
    safe_task_id = (task_id or "").strip()
    if not safe_task_id or "/" in safe_task_id or "\\" in safe_task_id or safe_task_id in {".", ".."}:
        return None

    task_dir = TASKS_DIR / safe_task_id
    if not task_dir.exists() or not task_dir.is_dir():
        return None

    runtime_file = task_dir / "runtime_state.json"
    result_file = task_dir / "result.json"
    plan_file = task_dir / "plan.json"
    trace_file = task_dir / "trace.json"
    execution_log_file = task_dir / "execution_log.json"

    runtime_data = _safe_read_json(runtime_file) if runtime_file.exists() else {}
    result_data = _safe_read_json(result_file) if result_file.exists() else {}
    plan_data = _safe_read_json(plan_file) if plan_file.exists() else {}

    files = []
    for item in sorted(task_dir.iterdir(), key=lambda p: p.name):
        if item.is_file():
            files.append(
                {
                    "name": item.name,
                    "path": str(item),
                    "size": item.stat().st_size,
                }
            )

    status = runtime_data.get("status") or result_data.get("status")
    step = runtime_data.get("step")
    goal = runtime_data.get("goal") or result_data.get("goal")
    final_answer = (
        result_data.get("final_answer")
        or result_data.get("answer")
        or result_data.get("message")
        or runtime_data.get("final_answer")
        or runtime_data.get("last_result")
    )

    return {
        "task_id": safe_task_id,
        "path": str(task_dir),
        "status": status,
        "step": step,
        "goal": goal,
        "final_answer": final_answer,
        "scenario": runtime_data.get("scenario") or result_data.get("scenario"),
        "mode": runtime_data.get("mode") or result_data.get("mode"),
        "pipeline_name": runtime_data.get("pipeline_name") or result_data.get("pipeline_name"),
        "execution_name": runtime_data.get("execution_name") or result_data.get("execution_name"),
        "files": files,
        "has_runtime_state": runtime_file.exists(),
        "has_result": result_file.exists(),
        "has_plan": plan_file.exists(),
        "has_trace": trace_file.exists(),
        "has_execution_log": execution_log_file.exists(),
        "runtime_state": runtime_data,
        "result": result_data,
        "plan": plan_data,
    }


def get_system_status() -> str:
    """
    Rough display-layer system status based on the most recent task.
    """
    tasks = get_tasks(limit=1)

    if not tasks:
        return "idle"

    latest = tasks[0]
    status = str(latest.get("status") or "").lower()

    if status in {"running", "executing", "queued"}:
        return "running"

    if status in {"failed", "error"}:
        return "error"

    return "idle"


def drop_text_file(content: str, filename: Optional[str] = None) -> str:
    """
    Simulate UI drop text -> workspace/inbox.

    This is intentionally input-only. It does not run scheduler, agent_loop, or any task executor.
    """
    INBOX_DIR.mkdir(parents=True, exist_ok=True)

    if not filename:
        filename = f"ui_drop_{int(time.time())}.txt"

    safe_path = _safe_inbox_path(filename)
    if safe_path is None:
        raise ValueError("Invalid inbox filename. Use a simple file name only.")

    safe_path.write_text(content, encoding="utf-8")
    return str(safe_path)


def list_inbox_files(limit: int = 20) -> List[Dict[str, Any]]:
    """
    Return recent files in workspace/inbox.
    """
    if not INBOX_DIR.exists():
        return []

    files = [f for f in INBOX_DIR.iterdir() if f.is_file()]
    files = sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)

    return [
        {
            "name": f.name,
            "path": str(f),
            "size": f.stat().st_size,
            "modified": f.stat().st_mtime,
        }
        for f in files[:limit]
    ]


def read_inbox_file(filename: str, max_chars: int = 12000) -> Optional[Dict[str, Any]]:
    """
    Read one workspace/inbox file by file name only.
    """
    path = _safe_inbox_path(filename)
    if path is None:
        return None

    if not path.exists() or not path.is_file():
        return None

    return {
        "name": path.name,
        "path": str(path),
        "size": path.stat().st_size,
        "modified": path.stat().st_mtime,
        "content": _safe_read_text(path, max_chars=max_chars),
    }
