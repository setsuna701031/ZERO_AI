from __future__ import annotations

import json

import pytest

from core.agent.runtime_mission_reflection import build_mission_reflection
from core.runtime.runtime_memory_model import RuntimeActivityMemory, build_runtime_activity_experience


NOW = "2026-07-13T00:00:00Z"


def experience(tmp_path, text="建立 hello.txt", outcome="completed"):
    entry = {"entry_id": "e", "mission_id": "m", "mission_session_id": "s", "status": outcome, "original_input": text, "normalized_input": text, "workspace_root": str(tmp_path), "attempt_count": 1, "max_attempts": 3, "approval_required": True, "approval_status": "approved", "last_result": {"status": outcome}, "failure": None}
    reflection = build_mission_reflection(entry, agent_id="agent", artifact={"structured_intents": [{"operation": "create_file", "path": "hello.txt"}, {"operation": "check_exists", "path": "hello.txt"}]}, now=NOW)
    return build_runtime_activity_experience(reflection, entry=entry, artifact={"structured_intents": [{"operation": "create_file", "path": "hello.txt"}, {"operation": "check_exists", "path": "hello.txt"}]}, reflection_path=tmp_path / "reflection.json")


def test_experience_uses_existing_runtime_activity_memory_and_is_idempotent(tmp_path):
    memory = RuntimeActivityMemory(tmp_path / "activity.jsonl"); record = experience(tmp_path)
    first, created = memory.record_experience(record); second, created_again = memory.record_experience(record)
    assert created is True and created_again is False and first == second
    assert memory.read_all()["record_count"] == 1 and memory.experience(first["experience_id"])["reflection_id"] == first["reflection_id"]
    assert first["reflection_index"]["path"].endswith("reflection.json")


def test_experience_utf8_operation_paths_and_success_factors(tmp_path):
    record, _ = RuntimeActivityMemory(tmp_path / "activity.jsonl").record_experience(experience(tmp_path, "建立 中文檔案 hello.txt"))
    assert "create_file" in record["operation_types"] and record["target_paths"] == ["hello.txt"]
    assert "create_then_verify" in record["success_factors"]
    assert "中文檔案" in (tmp_path / "activity.jsonl").read_text(encoding="utf-8")


def test_activity_memory_atomic_write_leaves_no_temporary_file(tmp_path):
    memory = RuntimeActivityMemory(tmp_path / "activity.jsonl"); memory.record_experience(experience(tmp_path))
    assert not list(tmp_path.glob(".activity.jsonl.tmp"))
    assert json.loads((tmp_path / "activity.jsonl").read_text(encoding="utf-8"))["contract"].endswith("activity_experience.v1")


def test_tampered_experience_fails_safely(tmp_path):
    path = tmp_path / "activity.jsonl"; memory = RuntimeActivityMemory(path); record, _ = memory.record_experience(experience(tmp_path))
    record["outcome"] = "failed"; path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint_mismatch"): memory.experience(record["experience_id"])

