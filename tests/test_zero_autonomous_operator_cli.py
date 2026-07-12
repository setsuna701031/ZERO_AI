from __future__ import annotations

import json
from pathlib import Path

from cli.zero_autonomous_operator import (
    ZERO_AUTONOMOUS_OPERATOR_CLI_SCHEMA,
    status_queue,
    submit_task,
)


def test_submit_task_persists_queue(tmp_path: Path) -> None:
    queue_path = tmp_path / "queue.json"

    result = submit_task(
        "update zero_probe.txt with autonomous cli data",
        queue_path=queue_path,
    )

    assert result["schema"] == ZERO_AUTONOMOUS_OPERATOR_CLI_SCHEMA
    assert result["ok"] is True
    assert result["command"] == "submit"
    assert result["queue_depth"] == 1
    assert queue_path.exists()

    persisted = json.loads(queue_path.read_text(encoding="utf-8"))
    assert persisted["schema"] == ZERO_AUTONOMOUS_OPERATOR_CLI_SCHEMA
    assert persisted["tasks"][0]["goal"] == (
        "update zero_probe.txt with autonomous cli data"
    )
    assert persisted["tasks"][0]["status"] == "queued"


def test_status_queue_reports_counts(tmp_path: Path) -> None:
    queue_path = tmp_path / "queue.json"
    submit_task("update a.txt with one", queue_path=queue_path)
    submit_task("update b.txt with two", queue_path=queue_path)

    status = status_queue(queue_path=queue_path)

    assert status["schema"] == ZERO_AUTONOMOUS_OPERATOR_CLI_SCHEMA
    assert status["ok"] is True
    assert status["queue_depth"] == 2
    assert status["queued_count"] == 2
    assert status["completed_count"] == 0
    assert status["failed_count"] == 0


def test_status_queue_handles_missing_queue(tmp_path: Path) -> None:
    status = status_queue(queue_path=tmp_path / "missing.json")

    assert status["ok"] is True
    assert status["queue_depth"] == 0
    assert status["queue"] == []
