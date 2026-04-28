# core/display/ui_bridge.py

import os
import json
from pathlib import Path
from typing import List, Dict, Optional

ROOT = Path("workspace")
SHARED_DIR = ROOT / "shared"
TASKS_DIR = ROOT / "tasks"
INBOX_DIR = ROOT / "inbox"


def get_latest_summary() -> Optional[str]:
    """
    Return latest *_summary.txt content
    """
    if not SHARED_DIR.exists():
        return None

    files = list(SHARED_DIR.glob("*_summary.txt"))
    if not files:
        return None

    latest = max(files, key=lambda f: f.stat().st_mtime)

    try:
        return latest.read_text(encoding="utf-8")
    except Exception as e:
        return f"[error reading summary] {e}"


def get_tasks(limit: int = 10) -> List[Dict]:
    """
    Return latest tasks info
    """
    if not TASKS_DIR.exists():
        return []

    tasks = []

    for task_dir in sorted(TASKS_DIR.iterdir(), reverse=True):
        runtime_file = task_dir / "runtime_state.json"

        if runtime_file.exists():
            try:
                data = json.loads(runtime_file.read_text(encoding="utf-8"))

                tasks.append({
                    "task_id": task_dir.name,
                    "status": data.get("status"),
                    "step": data.get("step"),
                    "goal": data.get("goal"),
                })
            except Exception:
                continue

        if len(tasks) >= limit:
            break

    return tasks


def get_system_status() -> str:
    """
    Rough system status
    """
    tasks = get_tasks(limit=1)

    if not tasks:
        return "idle"

    latest = tasks[0]
    status = latest.get("status")

    if status == "running":
        return "running"

    return "idle"


def drop_text_file(content: str, filename: Optional[str] = None) -> str:
    """
    Simulate UI drop file → inbox
    """
    INBOX_DIR.mkdir(parents=True, exist_ok=True)

    if not filename:
        import time
        filename = f"ui_drop_{int(time.time())}.txt"

    path = INBOX_DIR / filename

    path.write_text(content, encoding="utf-8")

    return str(path)


def list_shared_files(limit: int = 20) -> List[str]:
    if not SHARED_DIR.exists():
        return []

    files = sorted(SHARED_DIR.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)

    return [f.name for f in files[:limit]]