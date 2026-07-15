import json

from cli.zero_mission import main

NOW = "2026-07-13T00:00:00+00:00"


def test_json_prepare_only(tmp_path, capsys):
    code = main(["read README.md", "--workspace-root", str(tmp_path), "--prepare-only", "--json", "--now", NOW])
    value = json.loads(capsys.readouterr().out)
    assert code == 0 and value["bootstrap_status"] == "prepared"


def test_blocked_exit_code_and_valid_json(tmp_path, capsys):
    code = main(["do an unknowable thing", "--workspace-root", str(tmp_path), "--json", "--now", NOW])
    value = json.loads(capsys.readouterr().out)
    assert code == 3 and value["manual_review_required"] is True


def test_invalid_workspace_exit_two(tmp_path, capsys):
    assert main(["read README.md", "--workspace-root", str(tmp_path / "missing"), "--json"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)
