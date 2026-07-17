from __future__ import annotations

import json
from pathlib import Path

from cli.zero_sentinel import (
    ZERO_SENTINEL_CLI_SCHEMA,
    start_sentinel,
    status_sentinel,
)


def _write_queue(queue_path: Path, tasks: list[dict]) -> None:
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(
        json.dumps({"tasks": tasks}, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def test_status_sentinel_handles_missing_queue(tmp_path: Path) -> None:
    result = status_sentinel(queue_path=tmp_path / "missing.json")

    assert result["schema"] == ZERO_SENTINEL_CLI_SCHEMA
    assert result["ok"] is True
    assert result["command"] == "status"
    assert result["queue_depth"] == 0
    assert result["queued_count"] == 0


def test_status_sentinel_reports_queue_counts(tmp_path: Path) -> None:
    queue_path = tmp_path / "queue.json"
    _write_queue(
        queue_path,
        [
            {"task_id": "task-1", "goal": "update a.txt with one", "status": "queued"},
            {"task_id": "task-2", "goal": "update b.txt with two", "status": "completed"},
            {"task_id": "task-3", "goal": "update c.txt with three", "status": "failed"},
        ],
    )

    result = status_sentinel(queue_path=queue_path)

    assert result["ok"] is True
    assert result["queue_depth"] == 3
    assert result["queued_count"] == 1
    assert result["completed_count"] == 1
    assert result["failed_count"] == 1


def test_start_sentinel_persists_queue_after_idle(tmp_path: Path) -> None:
    queue_path = tmp_path / "queue.json"
    _write_queue(queue_path, [])

    result = start_sentinel(queue_path=queue_path, max_cycles=2)

    assert result["schema"] == ZERO_SENTINEL_CLI_SCHEMA
    assert result["ok"] is True
    assert result["command"] == "start"
    assert result["sentinel_online"] is True
    assert result["sentinel_status"] == "idle"
    assert queue_path.exists()

    persisted = json.loads(queue_path.read_text(encoding="utf-8"))
    assert persisted["schema"] == ZERO_SENTINEL_CLI_SCHEMA
    assert persisted["tasks"] == []
