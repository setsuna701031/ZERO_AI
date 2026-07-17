import json

from cli import zero_capability_runtime as cli
from core.runtime.runtime_governed_capability_runtime_closure_validation import validate_governed_capability_runtime_closure
from tests.test_runtime_governed_capability_runtime import completed_input


def test_cli_single_json_and_malformed_fail_closed(tmp_path, capsys):
    (tmp_path / "target.txt").touch()
    bundle = tmp_path / "input.json"
    bundle.write_text(json.dumps(completed_input(tmp_path)), encoding="utf-8")
    assert cli.main([str(bundle)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert validate_governed_capability_runtime_closure(output["runtime_orchestration_closure"]).valid
    malformed = tmp_path / "bad.json"; malformed.write_text("{", encoding="utf-8")
    assert cli.main([str(malformed)]) == 2
    failure = json.loads(capsys.readouterr().out)
    assert failure["audit_summary"]["status"] == "invalid"

