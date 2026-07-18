import json
import subprocess
import sys

from cli.zero_capability_strategy_runtime_integration_configuration import run
from core.runtime.runtime_capability_strategy_runtime_decision import decide_capability_strategy_runtime
from core.runtime.runtime_capability_strategy_bootstrap_configuration import configure_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_wiring import build_bootstrap_wiring_request, wire_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_consumption import consume_capability_strategy_bootstrap_wiring
from core.runtime.runtime_capability_strategy_bootstrap_runtime_integration_boundary import integrate_bootstrap_consumption
from core.runtime.runtime_capability_strategy_runtime_integration_consumer import consume_runtime_integration_boundary
from tests.capability_strategy_runtime_fixtures import strategy


def _write_consumer(path):
    bootstrap = configure_capability_strategy_bootstrap(decide_capability_strategy_runtime(strategy()))
    wiring = wire_capability_strategy_bootstrap(build_bootstrap_wiring_request(bootstrap_configuration=bootstrap))
    boundary = integrate_bootstrap_consumption(consume_capability_strategy_bootstrap_wiring(wiring))
    consumer = consume_runtime_integration_boundary(boundary)
    path.write_text(json.dumps(consumer), encoding="utf-8")
    return consumer


def test_cli_configure_validate_inspect_and_input_unchanged(tmp_path):
    source = tmp_path / "consumer.json"; consumer = _write_consumer(source); original = source.read_bytes()
    configuration, code = run(["configure", str(source)])
    assert code == 0 and configuration["status"] == "configured"
    artifact = tmp_path / "configuration.json"; artifact.write_text(json.dumps(configuration), encoding="utf-8")
    validation, code = run(["validate", str(artifact)])
    assert code == 0 and validation == {"valid": True, "errors": []}
    inspection, code = run(["inspect", str(artifact)])
    assert code == 0 and inspection["source_integration_consumer_id"] == consumer["consumer_id"]
    assert source.read_bytes() == original


def test_cli_validation_failure_invalid_json_and_missing_file(tmp_path):
    unsupported = tmp_path / "unsupported.json"; unsupported.write_text("{}", encoding="utf-8")
    result, code = run(["validate", str(unsupported)])
    assert code != 0 and result["valid"] is False
    invalid = tmp_path / "invalid.json"; invalid.write_text("{", encoding="utf-8")
    for path in (invalid, tmp_path / "missing.json"):
        result, code = run(["configure", str(path)])
        assert code == 2 and result["error"] == "input_error"


def test_cli_subprocess_nonzero_without_traceback(tmp_path):
    source = tmp_path / "invalid.json"; source.write_text("{", encoding="utf-8")
    completed = subprocess.run([sys.executable, "-m", "cli.zero_capability_strategy_runtime_integration_configuration", "configure", str(source)], capture_output=True, text=True, encoding="utf-8")
    assert completed.returncode != 0 and "Traceback" not in completed.stderr
    assert json.loads(completed.stdout)["error"] == "input_error"
