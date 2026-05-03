from pathlib import Path

import pytest

from core.repo_sandbox import ControlledEditSession, PolicyViolation, RepoSandbox


def test_sandbox_copy_edit_diff_and_repo_unchanged(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    target = repo / "core" / "example.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")

    sandbox = RepoSandbox(repo)
    prepared = sandbox.prepare(["core/example.py"])

    assert len(prepared) == 1
    assert prepared[0].sandbox_path.exists()
    assert prepared[0].original_path.exists()

    sandbox.write_text("core/example.py", "VALUE = 2\n")

    assert target.read_text(encoding="utf-8") == "VALUE = 1\n"
    assert sandbox.changed_files() == ["core/example.py"]

    diff = sandbox.build_all_diffs()
    assert "--- a/core/example.py" in diff
    assert "+++ b/core/example.py" in diff
    assert "-VALUE = 1" in diff
    assert "+VALUE = 2" in diff


def test_policy_blocks_dangerous_paths(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    sandbox = RepoSandbox(repo)

    with pytest.raises(PolicyViolation):
        sandbox.prepare([".git/config"])

    with pytest.raises(PolicyViolation):
        sandbox.prepare(["../outside.py"])

    secret = repo / "token.txt"
    secret.write_text("x", encoding="utf-8")
    with pytest.raises(PolicyViolation):
        sandbox.prepare(["token.txt"])


def test_controlled_edit_blocks_dangerous_command(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    target = repo / "demo.py"
    target.parent.mkdir(parents=True)
    target.write_text("print('hello')\n", encoding="utf-8")

    session = ControlledEditSession(repo)
    session.prepare_files(["demo.py"])
    session.edit_file(
        "demo.py",
        lambda text: text.replace("hello", "sandbox"),
        reason="replace demo output in sandbox only",
    )

    result = session.result(test_command="git push")

    assert result.changed_files == ["demo.py"]
    assert result.test_allowed is False
    assert result.blocked_reason is not None
    assert "blocked" in result.test_result.lower()
    assert "sandbox" not in target.read_text(encoding="utf-8")
