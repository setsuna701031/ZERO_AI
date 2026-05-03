from __future__ import annotations

from pathlib import Path

from core.agent.repo_edit_review_adapter import run_agent_repo_edit_review
from core.repo_sandbox.review import apply_review, load_review, reject_review


def test_agent_adapter_creates_pending_review_without_touching_original() -> None:
    repo_root = Path.cwd()
    target = repo_root / "workspace" / "i_agent_review_sample.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")

    try:
        result = run_agent_repo_edit_review(
            'Update workspace/i_agent_review_sample.py and replace "VALUE = 1" with "VALUE = 2".',
            repo_root=repo_root,
        )

        assert result["status"] == "pending_review"
        assert result["agent_action"] == "await_review_decision"
        assert result["requires_review"] is True
        assert result["auto_apply"] is False
        assert result["file_path"] == "workspace/i_agent_review_sample.py"
        assert "-VALUE = 1" in result["diff"]
        assert "+VALUE = 2" in result["diff"]
        assert target.read_text(encoding="utf-8") == "VALUE = 1\n"

        review = load_review(result["review_id"])
        assert review is not None
        assert review.status == "pending_review"
    finally:
        if target.exists():
            target.unlink()


def test_agent_adapter_apply_requires_explicit_review_decision() -> None:
    repo_root = Path.cwd()
    target = repo_root / "workspace" / "i_agent_apply_sample.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")

    try:
        result = run_agent_repo_edit_review(
            'Update workspace/i_agent_apply_sample.py and replace "VALUE = 1" with "VALUE = 2".',
            repo_root=repo_root,
        )

        assert target.read_text(encoding="utf-8") == "VALUE = 1\n"

        apply_result = apply_review(result["review_id"])

        assert apply_result["status"] == "applied"
        assert target.read_text(encoding="utf-8") == "VALUE = 2\n"
    finally:
        if target.exists():
            target.unlink()


def test_agent_adapter_reject_keeps_original_unchanged() -> None:
    repo_root = Path.cwd()
    target = repo_root / "workspace" / "i_agent_reject_sample.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")

    try:
        result = run_agent_repo_edit_review(
            'Update workspace/i_agent_reject_sample.py and replace "VALUE = 1" with "VALUE = 2".',
            repo_root=repo_root,
        )

        reject_result = reject_review(result["review_id"], reason="test reject")

        assert reject_result["status"] == "rejected"
        assert target.read_text(encoding="utf-8") == "VALUE = 1\n"
    finally:
        if target.exists():
            target.unlink()


def test_agent_adapter_blocks_core_path() -> None:
    result = run_agent_repo_edit_review(
        'Update core/tasks/scheduler.py and replace "A" with "B".'
    )

    assert result["status"] == "blocked"
    assert result["agent_action"] == "blocked"
    assert result["auto_apply"] is False
