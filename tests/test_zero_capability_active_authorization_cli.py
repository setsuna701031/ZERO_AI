import json, subprocess, sys
from cli.zero_capability_active_authorization import run
from tests.test_runtime_capability_active_authorization import AT, preparation

def write(tmp_path, status):
    path = tmp_path / (status + ".json"); path.write_text(json.dumps(preparation(status)), encoding="utf-8"); return path

def test_cli_statuses_and_output(tmp_path):
    for source, target in (("approved", "active"), ("denied", "not_authorized"), ("blocked", "blocked"), ("invalid", "invalid")):
        output = tmp_path / (source + "-out.json")
        value, code = run(["--preparation", str(write(tmp_path, source)), "--authorized-at", AT, "--ttl-seconds", "300", "--output", str(output)])
        assert code == 0 and value["status"] == target and json.loads(output.read_text(encoding="utf-8")) == value
        assert not any(value[x] for x in ("token_issued", "runtime_activated", "execution_authority_granted"))

def test_cli_bad_inputs(tmp_path):
    assert run(["--preparation", str(tmp_path / "missing")])[1] != 0
    bad = tmp_path / "bad"; bad.write_text("bad", encoding="utf-8"); assert run(["--preparation", str(bad)])[1] != 0
    assert run(["--preparation", str(write(tmp_path, "approved")), "--authorized-at", "naive"])[1] != 0
    assert run(["--preparation", str(write(tmp_path, "approved")), "--ttl-seconds", "0"])[1] != 0

def test_python_m_entrypoint(tmp_path):
    result = subprocess.run([sys.executable, "-m", "cli.zero_capability_active_authorization", "--preparation", str(write(tmp_path, "approved")), "--authorized-at", AT], capture_output=True, text=True)
    assert result.returncode == 0 and json.loads(result.stdout)["active"] and "Traceback" not in result.stderr
