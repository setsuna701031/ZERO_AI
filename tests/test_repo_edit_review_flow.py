from __future__ import annotations

from pathlib import Path

from core.repo_sandbox.review import apply_review, load_review, reject_review
from core.repo_sandbox.review_flow import decide_review, run_code_edit_review_task

# Import side effects: register repo_edit and repo_edit_review.
import core.tools.repo_edit_tool  # noqa: F401
import core.tools.repo_edit_review_tool  # noqa: F401


def test_review_flow_creates_pending_review_and_does_not_touch_original() -> None:
    repo_root = Path.cwd()
    target = repo_root / "workspace" / "h_review_sample.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")

    try:
        result = run_code_edit_review_task(
            'Update workspace/h_review_sample.py and replace "VALUE = 1" with "VALUE = 2".'
        )

        assert result["status"] == "pending_review"
        assert result["file_path"] == "workspace/h_review_sample.py"
        assert "-VALUE = 1" in result["diff"]
        assert "+VALUE = 2" in result["diff"]
        assert result["sandbox_path"]

        # Original repo file must remain unchanged until explicit apply.
        assert target.read_text(encoding="utf-8") == "VALUE = 1\n"

        review = load_review(result["review_id"])
        assert review.status == "pending_review"
    finally:
        if target.exists():
            target.unlink()


def test_review_apply_updates_original_after_explicit_decision() -> None:
    repo_root = Path.cwd()
    target = repo_root / "workspace" / "h_apply_sample.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")

    try:
        result = run_code_edit_review_task(
            'Update workspace/h_apply_sample.py and replace "VALUE = 1" with "VALUE = 2".'
        )

        assert target.read_text(encoding="utf-8") == "VALUE = 1\n"

        apply_result = apply_review(result["review_id"])

        assert apply_result["status"] == "applied"
        assert target.read_text(encoding="utf-8") == "VALUE = 2\n"

        review = load_review(result["review_id"])
        assert review.status == "applied"
    finally:
        if target.exists():
            target.unlink()


def test_review_reject_keeps_original_unchanged() -> None:
    repo_root = Path.cwd()
    target = repo_root / "workspace" / "h_reject_sample.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")

    try:
        result = run_code_edit_review_task(
            'Update workspace/h_reject_sample.py and replace "VALUE = 1" with "VALUE = 2".'
        )

        reject_result = reject_review(result["review_id"], reason="test reject")

        assert reject_result["status"] == "rejected"
        assert target.read_text(encoding="utf-8") == "VALUE = 1\n"

        review = load_review(result["review_id"])
        assert review.status == "rejected"
    finally:
        if target.exists():
            target.unlink()


def test_apply_review_errors_when_sandbox_file_is_missing() -> None:
    repo_root = Path.cwd()
    target = repo_root / "workspace" / "h_missing_sandbox_sample.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")

    try:
        result = run_code_edit_review_task(
            'Update workspace/h_missing_sandbox_sample.py and replace "VALUE = 1" with "VALUE = 2".'
        )
        sandbox_path = Path(result["sandbox_path"])
        if sandbox_path.exists():
            sandbox_path.unlink()

        apply_result = apply_review(result["review_id"])

        assert apply_result["status"] == "error"
        assert "sandbox file not found" in apply_result["reason"]
        assert target.read_text(encoding="utf-8") == "VALUE = 1\n"
    finally:
        if target.exists():
            target.unlink()


def test_decide_review_blocks_unknown_decision() -> None:
    result = decide_review("missing-review-id", "maybe")
    assert result["status"] == "blocked"
