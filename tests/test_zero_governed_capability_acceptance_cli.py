import json

from cli.zero_governed_capability_acceptance import main
from core.runtime.runtime_governed_capability_acceptance import validate_governed_capability_acceptance
from tests.test_runtime_governed_capability_runtime import completed_input


def test_valid_cli_is_single_valid_json_and_creates_no_files(tmp_path, capsys):
    workspace = tmp_path / "workspace"; workspace.mkdir()
    (workspace / "target.txt").write_text("unchanged", encoding="utf-8")
    source = tmp_path / "input.json"
    source.write_text(json.dumps(completed_input(workspace)), encoding="utf-8")
    regressions = tmp_path / "regressions.json"
    regressions.write_text(json.dumps({x: {"passed": 1, "failed": 0, "skipped": 0, "duration": 0.01, "status": "passed"} for x in "ABCDEFG"}), encoding="utf-8")
    before = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
    assert main([str(source), "--regression-results", str(regressions)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["merge_ready"] is True and validate_governed_capability_acceptance(output)
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")) == before


def test_cli_input_failures_are_json_without_traceback(tmp_path, capsys):
    cases = [tmp_path / "missing.json", tmp_path]
    malformed = tmp_path / "malformed.json"; malformed.write_text("{", encoding="utf-8"); cases.append(malformed)
    binary = tmp_path / "binary.json"; binary.write_bytes(b"\xff"); cases.append(binary)
    unknown = tmp_path / "unknown.json"; unknown.write_text('{"contract":"unknown"}', encoding="utf-8"); cases.append(unknown)
    for path in cases:
        assert main([str(path)]) != 0
        text = capsys.readouterr().out
        assert "Traceback" not in text
        assert json.loads(text)["merge_ready"] is False
