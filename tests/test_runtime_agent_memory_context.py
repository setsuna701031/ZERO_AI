from __future__ import annotations

from core.agent.runtime_mission_reflection import build_mission_reflection
from core.runtime.runtime_activity_memory_query import build_memory_context, query_relevant_experiences
from core.runtime.runtime_memory_model import RuntimeActivityMemory, build_runtime_activity_experience


NOW = "2026-07-13T00:00:00Z"


def add(memory, tmp_path, entry_id, text, outcome, operation, path):
    entry = {"entry_id": entry_id, "mission_id": "m-" + entry_id, "mission_session_id": "s-" + entry_id, "status": outcome, "original_input": text, "normalized_input": text, "workspace_root": str(tmp_path), "attempt_count": 1, "max_attempts": 3, "approval_required": operation.startswith("create"), "approval_status": "approved", "last_result": {"status": outcome}, "failure": {"reasons": ["unsafe path"]} if outcome != "completed" else None}
    artifact = {"structured_intents": [{"operation": operation, "path": path}]}
    reflection = build_mission_reflection(entry, agent_id="agent", artifact=artifact, now=NOW)
    memory.record_experience(build_runtime_activity_experience(reflection, entry=entry, artifact=artifact))


def test_query_ranks_relevant_create_experience_deterministically(tmp_path):
    memory = RuntimeActivityMemory(tmp_path / "activity.jsonl")
    add(memory, tmp_path, "1", "create hello.txt", "completed", "create_file", "hello.txt")
    add(memory, tmp_path, "2", "read README.md", "completed", "read_file", "README.md")
    first = query_relevant_experiences(memory, "create second.txt", operation_types=["create_file"], target_paths=["second.txt"], top_k=1)
    second = query_relevant_experiences(memory, "create second.txt", operation_types=["create_file"], target_paths=["second.txt"], top_k=1)
    assert first == second and first["matches"][0]["outcome"] == "completed"
    assert "create" in first["matches"][0]["matched_tokens"]


def test_failed_experience_provides_avoid_pattern_without_blocking_context(tmp_path):
    memory = RuntimeActivityMemory(tmp_path / "activity.jsonl")
    add(memory, tmp_path, "1", "create ../outside.txt", "blocked", "create_file", "../outside.txt")
    context = build_memory_context(memory, "create outside.txt", operation_types=["create_file"], target_paths=["outside.txt"])
    assert "path_traversal" in context["failure_patterns"]
    assert "validate_workspace_relative_path" in context["recommended_validations"]
    assert context["context_fingerprint"]


def test_context_is_bounded_to_three_references(tmp_path):
    memory = RuntimeActivityMemory(tmp_path / "activity.jsonl")
    for index in range(5): add(memory, tmp_path, str(index), f"create file{index}.txt", "completed", "create_file", f"file{index}.txt")
    context = build_memory_context(memory, "create next.txt", operation_types=["create_file"], top_k=99)
    assert len(context["experience_references"]) == 3
    assert "records" not in context and "source_references" not in context

