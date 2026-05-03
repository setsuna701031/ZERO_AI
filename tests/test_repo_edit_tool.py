from pathlib import Path

from core.repo_sandbox.tool import RepoEditTool, run_repo_edit


def test_repo_edit_tool_replaces_text_in_sandbox_only(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    target = repo / "core" / "sample.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")

    tool = RepoEditTool(repo_root=repo)
    result = tool.run(
        {
            "file_path": "core/sample.py",
            "instruction": "Change sample value in sandbox only.",
            "mode": "replace_text",
            "old_text": "VALUE = 1",
            "new_text": "VALUE = 2",
        }
    )

    assert result.status == "success"
    assert result.changed_files == ["core/sample.py"]
    assert "-VALUE = 1" in result.diff
    assert "+VALUE = 2" in result.diff
    assert target.read_text(encoding="utf-8") == "VALUE = 1\n"


def test_repo_edit_tool_blocks_missing_explicit_file_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    result = RepoEditTool(repo_root=repo).run(
        {
            "instruction": "Try to edit without file path.",
            "mode": "replace_file",
            "new_content": "x",
        }
    )

    assert result.status == "blocked"
    assert "file_path" in (result.error or "")


def test_repo_edit_tool_blocks_dangerous_test_command(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "demo.py"
    target.write_text("print('hello')\n", encoding="utf-8")

    result = run_repo_edit(
        {
            "file_path": "demo.py",
            "instruction": "Change demo output in sandbox only.",
            "mode": "replace_text",
            "old_text": "hello",
            "new_text": "sandbox",
            "test_command": "git push",
        },
        repo_root=repo,
    )

    assert result["status"] == "blocked"
    assert result["changed_files"] == ["demo.py"]
    assert result["test_allowed"] is False
    assert "blocked" in result["test_result"].lower()
    assert target.read_text(encoding="utf-8") == "print('hello')\n"


def test_repo_edit_tool_refuses_blind_replace(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "demo.py"
    target.write_text("print('hello')\n", encoding="utf-8")

    result = RepoEditTool(repo_root=repo).run(
        {
            "file_path": "demo.py",
            "instruction": "Replace text that is not present.",
            "mode": "replace_text",
            "old_text": "missing text",
            "new_text": "replacement",
        }
    )

    assert result.status == "blocked"
    assert "old_text" in (result.error or "")
