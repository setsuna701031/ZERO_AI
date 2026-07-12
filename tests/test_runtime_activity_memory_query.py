from __future__ import annotations

import json
from pathlib import Path

from core.runtime.runtime_memory_model import RuntimeActivityMemory


def _write_records(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True)
            for record in records
        )
        + "\n",
        encoding="utf-8",
    )


def test_activity_memory_finds_similar_completed_experience(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "activity.jsonl"
    _write_records(
        log_path,
        [
            {
                "goal": (
                    "在 workspace 建立 sentinel_activity_check.txt，"
                    "內容寫入 verified"
                ),
                "status": "completed",
                "ok": True,
                "changed_files": [
                    "workspace/sentinel_activity_check.txt"
                ],
                "denial_reason": "",
                "recorded_at": "2026-07-10T05:15:17+00:00",
            },
            {
                "goal": "建立 unrelated.txt",
                "status": "failed",
                "ok": False,
                "changed_files": [],
                "denial_reason": "blocked",
                "recorded_at": "2026-07-10T05:10:00+00:00",
            },
        ],
    )

    memory = RuntimeActivityMemory(log_path)
    result = memory.query(
        "在 workspace 建立 sentinel_activity_check.txt，內容寫入 new value",
        status="completed",
        limit=3,
        minimum_similarity=0.01,
    )

    assert result["ok"] is True
    assert result["memory_status"] == "matched"
    assert result["match_count"] == 1
    assert result["matches"][0]["record"]["status"] == "completed"
    assert result["matches"][0]["record"]["changed_files"] == [
        "workspace/sentinel_activity_check.txt"
    ]
    assert result["matches"][0]["similarity"] > 0


def test_activity_memory_builds_decision_context(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "activity.jsonl"
    _write_records(
        log_path,
        [
            {
                "goal": "建立 workspace/example.txt",
                "status": "completed",
                "ok": True,
                "changed_files": ["workspace/example.txt"],
                "denial_reason": "",
                "recorded_at": "2026-07-10T05:15:17+00:00",
            },
            {
                "goal": "建立 workspace/example.txt",
                "status": "failed",
                "ok": False,
                "changed_files": [],
                "denial_reason": "unsafe_path",
                "recorded_at": "2026-07-10T05:14:17+00:00",
            },
            {
                "goal": "建立 workspace/example.txt",
                "status": "rolled_back",
                "ok": False,
                "changed_files": [],
                "denial_reason": "validation_failed",
                "recorded_at": "2026-07-10T05:13:17+00:00",
            },
        ],
    )

    result = RuntimeActivityMemory(log_path).decision_context(
        "建立 workspace/example.txt"
    )

    assert result["ok"] is True
    assert result["memory_status"] == "context_available"
    assert result["experience_count"] == 3
    assert result["successful_paths"] == ["workspace/example.txt"]
    assert result["prior_denial_reasons"] == [
        "unsafe_path",
        "validation_failed",
    ]


def test_activity_memory_empty_log_is_safe(tmp_path: Path) -> None:
    result = RuntimeActivityMemory(
        tmp_path / "missing.jsonl"
    ).decision_context("建立 workspace/new.txt")

    assert result["ok"] is True
    assert result["memory_status"] == "empty"
    assert result["experience_count"] == 0
    assert result["successful_paths"] == []
    assert result["prior_denial_reasons"] == []
