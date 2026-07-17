from __future__ import annotations

from pathlib import Path

from core.tasks.scheduler import Scheduler


def test_save_task_snapshot_safe_does_not_deepcopy_full_results(tmp_path: Path) -> None:
    scheduler = Scheduler(workspace_dir=str(tmp_path / "workspace"))

    task_id = "task_snapshot_cap"
    task_dir = tmp_path / "workspace" / "tasks" / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    huge_nested = {
        "metadata": {
            "runtime_execution_result": {
                "canonical_evidence": {
                    "payload": ["x" * 1000 for _ in range(200)]
                }
            }
        }
    }

    task = {
        "task_id": task_id,
        "task_name": task_id,
        "status": "queued",
        "task_dir": str(task_dir),
        "snapshot_file": str(task_dir / "task.json"),
        "result_file": str(task_dir / "result.json"),
        "execution_log_file": str(task_dir / "execution_log.json"),
        "steps": [{"type": "read_file"}],
        "results": [
            {
                "step_index": i,
                "step": {"type": "write_file"},
                "result": {
                    "ok": i % 2 == 0,
                    "blocked": i % 2 == 1,
                    "message": "ok",
                    "metadata": huge_nested,
                },
            }
            for i in range(10)
        ],
        "execution_log": [
            {
                "step_index": i,
                "step": {"type": "write_file"},
                "result": {
                    "ok": True,
                    "message": "log",
                    "metadata": huge_nested,
                },
            }
            for i in range(10)
        ],
    }

    scheduler._save_task_snapshot_safe(task)

    assert (task_dir / "task.json").exists()
    assert (task_dir / "result.json").exists()
    assert (task_dir / "execution_log.json").exists()


def test_safe_snapshot_keeps_result_signal_without_metadata(tmp_path: Path) -> None:
    scheduler = Scheduler(workspace_dir=str(tmp_path / "workspace"))

    task_id = "task_snapshot_signal"
    task_dir = tmp_path / "workspace" / "tasks" / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    task = {
        "task_id": task_id,
        "task_name": task_id,
        "status": "blocked",
        "task_dir": str(task_dir),
        "snapshot_file": str(task_dir / "task.json"),
        "result_file": str(task_dir / "result.json"),
        "execution_log_file": str(task_dir / "execution_log.json"),
        "results": [
            {
                "step_index": 2,
                "step": {"type": "write_file"},
                "result": {
                    "ok": False,
                    "blocked": True,
                    "error_type": "execution_authority_denied",
                    "message": "approval_state_not_allowed",
                    "metadata": {"large": ["x" * 1000 for _ in range(100)]},
                },
            }
        ],
    }

    scheduler._save_task_snapshot_safe(task)

    data = (task_dir / "result.json").read_text(encoding="utf-8")
    assert "approval_state_not_allowed" in data
    assert "execution_authority_denied" in data
    assert "\"large\"" not in data
