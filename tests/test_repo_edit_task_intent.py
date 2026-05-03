from __future__ import annotations

from pathlib import Path

from core.repo_sandbox.intent import parse_code_edit_intent
from core.repo_sandbox.task_bridge import run_code_edit_task


def test_parse_ready_workspace_replace_intent() -> None:
    intent = parse_code_edit_intent(
        'Update workspace/g_intent_sample.py and replace "VALUE = 1" with "VALUE = 2".'
    )

    assert intent.status == "ready"
    assert intent.file_path == "workspace/g_intent_sample.py"
    assert intent.mode == "replace_text"
    assert intent.old_text == "VALUE = 1"
    assert intent.new_text == "VALUE = 2"


def test_parse_blocks_missing_file_path() -> None:
    intent = parse_code_edit_intent('replace "VALUE = 1" with "VALUE = 2"')

    assert intent.status == "blocked"
    assert "file path" in (intent.reason or "")


def test_parse_blocks_core_path() -> None:
    intent = parse_code_edit_intent(
        'Update core/tasks/scheduler.py and replace "A" with "B".'
    )

    assert intent.status == "blocked"


def test_task_bridge_runs_workspace_edit_in_sandbox_only() -> None:
    repo_root = Path.cwd()
    target = repo_root / "workspace" / "g_task_bridge_sample.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")

    try:
        result = run_code_edit_task(
            'Update workspace/g_task_bridge_sample.py and replace "VALUE = 1" with "VALUE = 2".'
        )

        assert result["status"] == "success"
        assert "-VALUE = 1" in result["diff"]
        assert "+VALUE = 2" in result["diff"]
        assert target.read_text(encoding="utf-8") == "VALUE = 1\n"
    finally:
        if target.exists():
            target.unlink()
