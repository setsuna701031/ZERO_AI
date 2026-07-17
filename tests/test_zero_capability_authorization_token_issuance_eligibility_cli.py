import json
import subprocess
import sys

from cli.zero_capability_authorization_token_issuance_eligibility import run
from tests.test_runtime_capability_authorization_token import create
from tests.test_runtime_capability_authorization_token_issuance_eligibility import token_with_status

def write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")

def test_cli_statuses_output_and_file(tmp_path):
    source = tmp_path / "token.json"; output = tmp_path / "eligibility.json"
    write(source, create())
    result, code = run(["--token", str(source), "--evaluated-at", "2099-07-17T06:03:00Z", "--output", str(output)])
    assert code == 0 and result["eligible"] and json.loads(output.read_text(encoding="utf-8")) == result
    for token_status, result_status in (("not_created", "ineligible"), ("blocked", "blocked"), ("invalid", "invalid"), ("expired", "expired")):
        write(source, token_with_status(token_status))
        result, code = run(["--token", str(source), "--evaluated-at", "2099-07-17T06:03:00Z"])
        assert code == 0 and result["status"] == result_status

def test_cli_bounded_errors(tmp_path):
    assert run(["--token", str(tmp_path / "missing")])[1] == 2
    source = tmp_path / "bad.json"; source.write_text("{", encoding="utf-8")
    assert run(["--token", str(source)])[1] == 2
    write(source, create())
    assert run(["--token", str(source), "--evaluated-at", "2099-07-17T06:03:00"])[1] == 2

def test_python_module_mode_and_non_authority_flags(tmp_path):
    source = tmp_path / "token.json"; write(source, create())
    completed = subprocess.run([sys.executable, "-m", "cli.zero_capability_authorization_token_issuance_eligibility", "--token", str(source), "--evaluated-at", "2099-07-17T06:03:00Z"], capture_output=True, text=True)
    result = json.loads(completed.stdout)
    assert completed.returncode == 0 and result["eligible"]
    assert not any(result[name] for name in ("issuance_preparation_created", "token_issued", "token_signed", "token_handed_off", "token_material_created", "runtime_activated", "execution_authority_granted"))
