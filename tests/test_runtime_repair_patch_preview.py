from __future__ import annotations

from core.tasks.runtime_repair_patch_preview import (
    build_runtime_repair_patch_preview,
    build_runtime_repair_patch_previews,
)


def _allowed_scope_gate():
    return {
        "task_id": "task_001",
        "proposal_id": "proposal_001",
        "scope_allowed": True,
        "target_paths": ["workspace/tasks/task_001/example.py"],
    }


def test_patch_preview_builds_unified_diff_without_mutation_permission():
    result = build_runtime_repair_patch_preview(
        _allowed_scope_gate(),
        old_text="def add(a, b):\n    return a - b\n",
        new_text="def add(a, b):\n    return a + b\n",
    )

    assert result["preview_allowed"] is True
    assert result["preview_status"] == "ready"
    assert result["target_path"] == "workspace/tasks/task_001/example.py"
    assert "--- a/workspace/tasks/task_001/example.py" in result["diff"]
    assert "+++ b/workspace/tasks/task_001/example.py" in result["diff"]
    assert "-    return a - b" in result["diff"]
    assert "+    return a + b" in result["diff"]

    assert result["mutation_allowed"] is False
    assert result["execution_allowed"] is False
    assert result["schedule_allowed"] is False
    assert result["apply_allowed"] is False
    assert result["allowed_next_action"] == "human_review_patch_preview"


def test_patch_preview_blocks_when_scope_gate_is_not_allowed():
    result = build_runtime_repair_patch_preview(
        {
            "scope_allowed": False,
            "target_paths": ["workspace/tasks/task_001/example.py"],
        },
        old_text="a\n",
        new_text="b\n",
    )

    assert result["preview_allowed"] is False
    assert result["preview_status"] == "blocked"
    assert "mutation_scope_not_allowed" in result["blocked_reasons"]
    assert result["diff"] == ""
    assert result["apply_allowed"] is False


def test_patch_preview_blocks_missing_target_and_missing_text():
    result = build_runtime_repair_patch_preview(
        {"scope_allowed": True},
        old_text="",
        new_text="",
    )

    assert result["preview_allowed"] is False
    assert "target_path_missing" in result["blocked_reasons"]
    assert "old_text_missing" in result["blocked_reasons"]
    assert "new_text_missing" in result["blocked_reasons"]


def test_patch_preview_blocks_no_text_change():
    result = build_runtime_repair_patch_preview(
        _allowed_scope_gate(),
        old_text="same\n",
        new_text="same\n",
    )

    assert result["preview_allowed"] is False
    assert "no_text_change" in result["blocked_reasons"]
    assert result["diff"] == ""


def test_patch_preview_uses_explicit_target_path_over_scope_gate_path():
    result = build_runtime_repair_patch_preview(
        _allowed_scope_gate(),
        target_path="workspace/shared/demo.txt",
        old_text="old\n",
        new_text="new\n",
    )

    assert result["preview_allowed"] is True
    assert result["target_path"] == "workspace/shared/demo.txt"
    assert "--- a/workspace/shared/demo.txt" in result["diff"]


def test_patch_previews_accepts_multiple_requests():
    results = build_runtime_repair_patch_previews(
        _allowed_scope_gate(),
        [
            {
                "target_path": "workspace/shared/a.txt",
                "old_text": "a\n",
                "new_text": "b\n",
            },
            {
                "target_path": "workspace/shared/c.txt",
                "old_text": "c\n",
                "new_text": "d\n",
            },
        ],
    )

    assert len(results) == 2
    assert all(item["preview_allowed"] for item in results)
    assert results[0]["target_path"] == "workspace/shared/a.txt"
    assert results[1]["target_path"] == "workspace/shared/c.txt"


def test_patch_preview_blocks_oversized_text():
    result = build_runtime_repair_patch_preview(
        _allowed_scope_gate(),
        old_text="a" * 20,
        new_text="b" * 20,
        max_preview_bytes=10,
    )

    assert result["preview_allowed"] is False
    assert "old_text_too_large_for_preview" in result["blocked_reasons"]
    assert "new_text_too_large_for_preview" in result["blocked_reasons"]
