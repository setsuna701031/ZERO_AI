import json
import subprocess
import sys

from cli.zero_capability_authorization_token_eligibility import run
from tests.test_runtime_capability_active_authorization import authorize, preparation
from tests.test_runtime_capability_authorization_token_eligibility import NOW


def write(tmp_path, source):
    path = tmp_path / (source + ".json")
    path.write_text(json.dumps(authorize(preparation(source))), encoding="utf-8")
    return path


def test_cli_statuses_and_output(tmp_path):
    for source, target in (("approved", "eligible"), ("denied", "ineligible"), ("blocked", "blocked"), ("invalid", "invalid")):
        output = tmp_path / (source + "-out.json")
        value, code = run(["--authorization", str(write(tmp_path, source)), "--evaluated-at", NOW, "--output", str(output)])
        assert code == 0 and value["status"] == target
        assert json.loads(output.read_text(encoding="utf-8")) == value
        assert not any(value[name] for name in ("token_preparation_created", "token_created", "token_issued", "token_signed", "runtime_activated", "execution_authority_granted"))


def test_cli_expired_bad_inputs_and_naive_time(tmp_path):
    value, code = run(["--authorization", str(write(tmp_path, "approved")), "--evaluated-at", "2100-01-01T00:00:00Z"])
    assert code == 0 and value["expired"]
    assert run(["--authorization", str(tmp_path / "missing")])[1] != 0
    bad = tmp_path / "bad"; bad.write_text("bad", encoding="utf-8")
    assert run(["--authorization", str(bad)])[1] != 0
    assert run(["--authorization", str(write(tmp_path, "approved")), "--evaluated-at", "naive"])[1] != 0


def test_python_m_entrypoint_and_flags(tmp_path):
    result = subprocess.run([sys.executable, "-m", "cli.zero_capability_authorization_token_eligibility", "--authorization", str(write(tmp_path, "approved")), "--evaluated-at", NOW], capture_output=True, text=True)
    assert result.returncode == 0 and json.loads(result.stdout)["eligible"] and "Traceback" not in result.stderr
    help_result = subprocess.run([sys.executable, "-m", "cli.zero_capability_authorization_token_eligibility", "--help"], capture_output=True, text=True)
    for flag in ("--issue-token", "--create-token", "--sign", "--activate", "--execute", "--run"):
        assert flag not in help_result.stdout
