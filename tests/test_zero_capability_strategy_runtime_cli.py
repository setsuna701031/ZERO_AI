import json
import subprocess
import sys

from cli.zero_capability_strategy_runtime import build_parser, run
from tests.capability_strategy_runtime_fixtures import strategy


def test_cli_consume_integrate_decide_and_output(tmp_path):
    source = tmp_path / "strategy.json"; source.write_text(json.dumps(strategy()), encoding="utf-8")
    for command, status in (("consume", "consumed"), ("integrate", "integrated"), ("decide", "accepted")):
        output = tmp_path / f"{command}.json"
        value, code = run([command, str(source), "--output", str(output)])
        assert code == 0 and value["status"] == status
        assert json.loads(output.read_text(encoding="utf-8")) == value


def test_cli_invalid_input_nonzero_without_traceback(tmp_path):
    source = tmp_path / "invalid.json"; source.write_text("{}", encoding="utf-8")
    completed = subprocess.run([sys.executable, "-m", "cli.zero_capability_strategy_runtime", "consume", str(source)], text=True, capture_output=True, encoding="utf-8")
    assert completed.returncode != 0 and "Traceback" not in completed.stderr
    assert json.loads(completed.stdout)["status"] == "invalid"


def test_cli_boundary_has_no_runtime_ownership_commands():
    help_text = build_parser().format_help()
    assert all(term not in help_text for term in ("execute", "approve", "authorize", "schedule", "activate", "mutation"))
