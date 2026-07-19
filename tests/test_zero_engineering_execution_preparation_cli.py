import json

from cli.zero_engineering_execution_preparation import STAGES, run
from tests.test_engineering_execution_preparation import authorization_closure


def test_cli_all_stages(tmp_path):
    source = tmp_path / "authorization.json"
    source.write_text(json.dumps(authorization_closure()), encoding="utf-8")
    for stage in STAGES:
        value, code = run([str(source), "--stage", stage])
        assert code == 0
        assert "error" not in value


def test_cli_rejects_invalid_json(tmp_path):
    source = tmp_path / "bad.json"
    source.write_text("{", encoding="utf-8")
    assert run([str(source)])[1] == 2
