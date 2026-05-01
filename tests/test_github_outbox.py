from __future__ import annotations

from pathlib import Path

from core.tools.github_outbox import OUTBOX_DIR, OUTBOX_FILES, run


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

