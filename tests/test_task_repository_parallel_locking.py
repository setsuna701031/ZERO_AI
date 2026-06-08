from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_parallel_task_repository_writers_preserve_both_tasks(tmp_path: Path) -> None:
    db_path = tmp_path / "workspace" / "tasks.json"
    start_path = tmp_path / "start"
    worker_code = """
import sys
import time
from pathlib import Path
from core.tasks.task_repository import TaskRepository

db_path = sys.argv[1]
task_id = sys.argv[2]
start_path = Path(sys.argv[3])

class SlowRepository(TaskRepository):
    def save(self):
        time.sleep(0.2)
        return super().save()

repo = SlowRepository(db_path=db_path)
while not start_path.exists():
    time.sleep(0.01)
assert repo.add_task({"task_id": task_id, "goal": task_id, "status": "queued"})
"""
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", worker_code, str(db_path), task_id, str(start_path)],
            cwd=Path(__file__).resolve().parents[1],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for task_id in ("parallel-a", "parallel-b")
    ]
    start_path.touch()

    failures = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=30)
        if process.returncode != 0:
            failures.append(f"returncode={process.returncode}\nstdout={stdout}\nstderr={stderr}")

    assert not failures, "\n".join(failures)
    stored = json.loads(db_path.read_text(encoding="utf-8"))
    assert {task["task_id"] for task in stored["tasks"]} == {"parallel-a", "parallel-b"}
