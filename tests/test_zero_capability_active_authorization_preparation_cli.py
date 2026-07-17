import json
import subprocess
import sys

from cli.zero_capability_active_authorization_preparation import run
from tests.test_runtime_capability_active_authorization_eligibility import NOW
from tests.test_runtime_capability_active_authorization_preparation import eligibility


def write(tmp_path, status):
    path = tmp_path / (status + ".json")
    path.write_text(json.dumps(eligibility(status)), encoding="utf-8")
    return path


def test_cli_statuses_and_output(tmp_path):
    for source, target in (("approved", "prepared"), ("denied", "not_prepared"), ("blocked", "blocked"), ("invalid", "invalid")):
        path = write(tmp_path, source); output = tmp_path / (source + "-out.json")
        value, code = run(["--eligibility", str(path), "--prepared-at", NOW, "--output", str(output)])
        assert code == 0 and value["status"] == target
        assert json.loads(output.read_text(encoding="utf-8")) == value
        assert not any(value[name] for name in ("active_authorization_created", "authorization_granted", "token_issued", "runtime_activated", "execution_authority_granted"))


def test_cli_bad_file_json_and_timestamp(tmp_path):
    assert run(["--eligibility", str(tmp_path / "missing")])[1] != 0
    bad = tmp_path / "bad"; bad.write_text("bad", encoding="utf-8")
    assert run(["--eligibility", str(bad)])[1] != 0
    assert run(["--eligibility", str(write(tmp_path, "approved")), "--prepared-at", "2026-01-01T00:00:00"])[1] != 0


def test_python_m_entrypoint(tmp_path):
    result = subprocess.run([sys.executable, "-m", "cli.zero_capability_active_authorization_preparation", "--eligibility", str(write(tmp_path, "approved")), "--prepared-at", NOW], capture_output=True, text=True)
    assert result.returncode == 0 and json.loads(result.stdout)["prepared"]
    assert "Traceback" not in result.stderr
