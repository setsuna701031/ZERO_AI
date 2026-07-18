import json
import subprocess
import sys

from cli.zero_capability_strategy_bootstrap_consumption import run
from core.runtime.runtime_capability_strategy_runtime_decision import decide_capability_strategy_runtime
from core.runtime.runtime_capability_strategy_bootstrap_configuration import configure_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_wiring import build_bootstrap_wiring_request, wire_capability_strategy_bootstrap
from tests.capability_strategy_runtime_fixtures import strategy


def _write_wiring(path):
    configuration = configure_capability_strategy_bootstrap(decide_capability_strategy_runtime(strategy()))
    wiring = wire_capability_strategy_bootstrap(build_bootstrap_wiring_request(bootstrap_configuration=configuration))
    path.write_text(json.dumps(wiring), encoding="utf-8")
    return wiring


def test_cli_consume_validate_inspect_and_input_unchanged(tmp_path):
    source = tmp_path / "wiring.json"; wiring = _write_wiring(source); original = source.read_bytes()
    consumption, code = run(["consume", str(source)])
    assert code == 0 and consumption["status"] == "consumed"
    artifact = tmp_path / "consumption.json"; artifact.write_text(json.dumps(consumption), encoding="utf-8")
    validation, code = run(["validate", str(artifact)])
    assert code == 0 and validation == {"valid": True, "errors": []}
    inspection, code = run(["inspect", str(artifact)])
    assert code == 0 and inspection["source_wiring_id"] == wiring["wiring_id"]
    assert source.read_bytes() == original


def test_cli_validation_failure_invalid_json_and_missing_file(tmp_path):
    invalid_artifact = tmp_path / "artifact.json"; invalid_artifact.write_text("{}", encoding="utf-8")
    result, code = run(["validate", str(invalid_artifact)])
    assert code != 0 and result["valid"] is False
    invalid_json = tmp_path / "invalid.json"; invalid_json.write_text("{", encoding="utf-8")
    for path in (invalid_json, tmp_path / "missing.json"):
        result, code = run(["consume", str(path)])
        assert code == 2 and result["error"] == "input_error"


def test_cli_subprocess_has_nonzero_without_traceback(tmp_path):
    source = tmp_path / "invalid.json"; source.write_text("{", encoding="utf-8")
    completed = subprocess.run([sys.executable, "-m", "cli.zero_capability_strategy_bootstrap_consumption", "consume", str(source)], capture_output=True, text=True, encoding="utf-8")
    assert completed.returncode != 0 and "Traceback" not in completed.stderr
    assert json.loads(completed.stdout)["error"] == "input_error"
