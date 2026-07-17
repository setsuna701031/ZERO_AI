import json
import subprocess
import sys

from cli.zero_capability_authorization_token import run
from tests.test_runtime_capability_authorization_token_preparation import prepare

def test_cli_created_output_and_file(tmp_path):
    source = tmp_path / "preparation.json"; output = tmp_path / "token.json"
    source.write_text(json.dumps(prepare()), encoding="utf-8")
    result, code = run(["--preparation", str(source), "--created-at", "2099-07-17T06:02:30Z", "--output", str(output)])
    assert code == 0 and result["created"] and json.loads(output.read_text(encoding="utf-8")) == result

def test_cli_errors_are_bounded(tmp_path):
    missing, code = run(["--preparation", str(tmp_path / "missing")])
    assert code == 2 and missing == {"error": "invalid_json_input"}
    source = tmp_path / "bad.json"; source.write_text("{", encoding="utf-8")
    assert run(["--preparation", str(source)])[1] == 2

def test_python_module_mode(tmp_path):
    source = tmp_path / "preparation.json"; source.write_text(json.dumps(prepare()), encoding="utf-8")
    completed = subprocess.run([sys.executable, "-m", "cli.zero_capability_authorization_token", "--preparation", str(source), "--created-at", "2099-07-17T06:02:30Z"], capture_output=True, text=True)
    assert completed.returncode == 0 and json.loads(completed.stdout)["created"]
