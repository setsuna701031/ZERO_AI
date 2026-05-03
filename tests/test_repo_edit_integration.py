from __future__ import annotations

from pathlib import Path

from core.tools.tool_runner import run_tool

# Import side effect: registers "repo_edit"
import core.tools.repo_edit_tool  # noqa: F401


def test_repo_edit_integration() -> None:
    repo_root = Path.cwd()
    target = repo_root / "workspace" / "repo_edit_integration_sample.py"

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")

    result = run_tool(
        "repo_edit",
        {
            "file_path": "workspace/repo_edit_integration_sample.py",
            "instruction": "Change sample value in sandbox only.",
            "mode": "replace_text",
            "old_text": "VALUE = 1",
            "new_text": "VALUE = 2",
        },
    )

    assert result["status"] == "success"
    assert "-VALUE = 1" in result["diff"]
    assert "+VALUE = 2" in result["diff"]

    # Original repo file must remain unchanged.
    assert target.read_text(encoding="utf-8") == "VALUE = 1\n"

    target.unlink()