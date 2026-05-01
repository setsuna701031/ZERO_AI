from __future__ import annotations

from pathlib import Path

from core.tools.github_outbox import OUTBOX_DIR, OUTBOX_FILES, run
from core.tools.tool_registry import ToolRegistry


def test_github_outbox_run_generates_required_files() -> None:
    run("test task")

    expected_files = [
        OUTBOX_FILES["commit_message"],
        OUTBOX_FILES["pr_description"],
        OUTBOX_FILES["devlog_entry"],
        OUTBOX_FILES["publish_plan"],
    ]
    for filename in expected_files:
        path = OUTBOX_DIR / filename
        assert path.exists(), f"missing outbox artifact: {path}"
        assert "test task" in path.read_text(encoding="utf-8")


def test_github_outbox_adapter_is_callable_from_tool_registry() -> None:
    registry = ToolRegistry()

    result = registry.execute_tool("github_outbox", {"task": "adapter test task"})

    assert result["ok"] is True
    output = result["output"]
    assert output["ok"] is True
    assert output["git_commit"] is False
    assert output["git_push"] is False
    assert output["github_create_pr"] is False

    for filename in OUTBOX_FILES.values():
        path = Path(output["artifacts"][filename])
        assert path.exists(), f"missing adapter outbox artifact: {path}"
        assert "adapter test task" in path.read_text(encoding="utf-8")
