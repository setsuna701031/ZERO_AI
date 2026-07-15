import json

from cli.zero_agent import main


def test_planning_preview_json_is_parseable_and_prepare_only(tmp_path, capsys):
    code = main(["planning", "preview", "create second.txt with content hello second", "--workspace-root", str(tmp_path), "--json", "--now", "2026-07-13T00:00:00Z"])
    value = json.loads(capsys.readouterr().out)
    assert code == 0 and value["prepare_only"] is True
    assert value["scope_preserved"] is True and value["approval_preserved"] is True
    assert not (tmp_path / "second.txt").exists()
