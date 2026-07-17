from __future__ import annotations

import json

from core.runtime.runtime_engineering_cli import CLIEngineeringCommandSurface, main


def test_cli_engineering_surface_run_goal(tmp_path):
    (tmp_path / "core/runtime").mkdir(parents=True, exist_ok=True)
    (tmp_path / "core/runtime/placeholder.py").write_text("OLD = True\n", encoding="utf-8")

    surface = CLIEngineeringCommandSurface.with_workspace(tmp_path)

    result = surface.run_goal(
        goal="update placeholder",
        target_file="core/runtime/placeholder.py",
        content="OLD = False\n",
        keywords=["runtime"],
        verify_contains="False",
    )

    assert result.ok is True
    assert result.status == "completed"
    assert result.session_id
    assert result.mutation_id
    assert (tmp_path / "core/runtime/placeholder.py").read_text(encoding="utf-8") == "OLD = False\n"

    inspected = surface.inspect_session(session_id=result.session_id)

    assert inspected.ok is True
    assert inspected.session_id == result.session_id


def test_cli_engineering_main_run(capsys, tmp_path):
    (tmp_path / "core/runtime").mkdir(parents=True, exist_ok=True)

    code = main(
        [
            "--workspace",
            str(tmp_path),
            "run",
            "--goal",
            "write cli file",
            "--target-file",
            "core/runtime/generated_cli_file.py",
            "--content",
            "CLI_FILE = True\n",
            "--verify-contains",
            "True",
            "--keyword",
            "runtime",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 0
    assert payload["ok"] is True
    assert payload["status"] == "completed"
    assert (tmp_path / "core/runtime/generated_cli_file.py").exists()


def test_cli_engineering_main_inspect(capsys, tmp_path):
    surface = CLIEngineeringCommandSurface.with_workspace(tmp_path)

    result = surface.run_goal(
        goal="inspectable goal",
        target_file="inspect.txt",
        content="inspect me",
        verify_contains="inspect",
    )

    code = main(
        [
            "--workspace",
            str(tmp_path),
            "inspect",
            "--session-id",
            result.session_id,
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 0
    assert payload["ok"] is True
    assert payload["session_id"] == result.session_id
