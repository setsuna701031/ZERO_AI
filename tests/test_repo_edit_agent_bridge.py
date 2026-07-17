from __future__ import annotations

from pathlib import Path

from core.tools.repo_edit_agent_bridge import (
    extract_explicit_file_path,
    run_repo_edit_decision,
    should_route_to_repo_edit,
)


def test_extract_explicit_file_path_from_task_text() -> None:
    assert (
        extract_explicit_file_path("Modify file workspace/example.py and append text")
        == "workspace/example.py"
    )
    assert (
        extract_explicit_file_path("file_path: core/tools/sample_tool.py")
        == "core/tools/sample_tool.py"
    )


def test_repo_edit_decision_blocks_when_file_path_missing() -> None:
    should_route, decision = should_route_to_repo_edit(
        "Improve the repository edit logic without specifying a file."
    )

    assert should_route is False
    assert decision["status"] == "blocked"
    assert "explicit file_path" in decision["reason"]


def test_repo_edit_decision_blocks_high_risk_core_files() -> None:
    result = run_repo_edit_decision(
        {
            "file_path": "core/agent/agent_loop.py",
            "instruction": "Try direct high-risk core self edit.",
            "mode": "replace_text",
            "old_text": "x",
            "new_text": "y",
        }
    )

    assert result["status"] == "blocked"
    assert "high-risk core file" in result["decision"]["reason"]


def test_repo_edit_decision_blocks_unsealed_mapping_edit() -> None:
    repo_root = Path.cwd()
    target = repo_root / "workspace" / "repo_edit_agent_bridge_sample.py"

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")

    result = run_repo_edit_decision(
        {
            "file_path": "workspace/repo_edit_agent_bridge_sample.py",
            "instruction": "Change sample value through F-package bridge.",
            "mode": "replace_text",
            "old_text": "VALUE = 1",
            "new_text": "VALUE = 2",
        }
    )

    assert result["status"] == "blocked"
    assert result["tool"] == "repo_edit"
    assert result["routed"] is False
    assert "sealed runtime dispatch" in result["reason"]

    # An unsealed compatibility route cannot mutate the repository.
    assert target.read_text(encoding="utf-8") == "VALUE = 1\n"

    target.unlink()
