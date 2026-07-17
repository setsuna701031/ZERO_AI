import json
import subprocess
import sys

from cli.zero_capability_authorization_token_preparation import run
from tests.test_runtime_capability_authorization_token_eligibility import evaluate
from tests.test_runtime_capability_active_authorization import authorize, preparation
from tests.test_runtime_capability_authorization_token_preparation import PREPARED_AT


def write(tmp_path, source):
    path = tmp_path / (source + ".json")
    path.write_text(json.dumps(evaluate(authorize(preparation(source)))), encoding="utf-8")
    return path


def test_cli_statuses_and_output(tmp_path):
    for source, target in (("approved", "prepared"), ("denied", "not_prepared"), ("blocked", "blocked"), ("invalid", "invalid")):
        output = tmp_path / (source + "-out.json")
        value, code = run(["--eligibility", str(write(tmp_path, source)), "--prepared-at", PREPARED_AT, "--output", str(output)])
        assert code == 0 and value["status"] == target
        assert json.loads(output.read_text(encoding="utf-8")) == value
        assert not any(value[name] for name in ("token_created", "token_issued", "token_signed", "token_material_created", "runtime_activated", "execution_authority_granted"))


def test_cli_expired_bad_inputs_and_naive_time(tmp_path):
    value, code = run(["--eligibility", str(write(tmp_path, "approved")), "--prepared-at", "2100-01-01T00:00:00Z"])
    assert code == 0 and value["expired"]
    assert run(["--eligibility", str(tmp_path / "missing")])[1] != 0
    bad = tmp_path / "bad"; bad.write_text("bad", encoding="utf-8")
    assert run(["--eligibility", str(bad)])[1] != 0
    assert run(["--eligibility", str(write(tmp_path, "approved")), "--prepared-at", "naive"])[1] != 0


def test_python_m_entrypoint_and_flags(tmp_path):
    result = subprocess.run([sys.executable, "-m", "cli.zero_capability_authorization_token_preparation", "--eligibility", str(write(tmp_path, "approved")), "--prepared-at", PREPARED_AT], capture_output=True, text=True)
    assert result.returncode == 0 and json.loads(result.stdout)["prepared"] and "Traceback" not in result.stderr
    help_result = subprocess.run([sys.executable, "-m", "cli.zero_capability_authorization_token_preparation", "--help"], capture_output=True, text=True)
    for flag in ("--issue-token", "--create-token", "--sign", "--secret", "--bearer", "--activate", "--execute", "--run"):
        assert flag not in help_result.stdout
