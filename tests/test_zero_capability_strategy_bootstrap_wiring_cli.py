import json
import subprocess
import sys

from cli.zero_capability_strategy_bootstrap_wiring import run
from core.runtime.runtime_capability_strategy_runtime_decision import decide_capability_strategy_runtime
from core.runtime.runtime_capability_strategy_bootstrap_configuration import configure_capability_strategy_bootstrap
from tests.capability_strategy_runtime_fixtures import strategy


def test_cli_wire_validate_inspect_success(tmp_path):
    configuration = configure_capability_strategy_bootstrap(decide_capability_strategy_runtime(strategy()))
    source = tmp_path / "configuration.json"; source.write_text(json.dumps(configuration), encoding="utf-8")
    output = tmp_path / "wiring.json"
    result, code = run(["wire", str(source), "--target", "integration", "--output", str(output)])
    assert code == 0 and result["status"] == "wired"
    assert json.loads(output.read_text(encoding="utf-8")) == result
    validation, code = run(["validate", str(output)]); assert code == 0 and validation == {"valid": True, "errors": []}
    inspection, code = run(["inspect", str(output)]); assert code == 0 and inspection["configuration_applied"] is True


def test_cli_invalid_input_nonzero_without_traceback(tmp_path):
    source = tmp_path / "invalid.json"; source.write_text("[]", encoding="utf-8")
    completed = subprocess.run([sys.executable, "-m", "cli.zero_capability_strategy_bootstrap_wiring", "wire", str(source)], capture_output=True, text=True, encoding="utf-8")
    assert completed.returncode != 0 and "Traceback" not in completed.stderr
    assert json.loads(completed.stdout)["error"] == "input_error"
