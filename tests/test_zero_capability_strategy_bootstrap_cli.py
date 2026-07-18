import json
import subprocess
import sys

from cli.zero_capability_strategy_bootstrap import build_parser, run
from core.runtime.runtime_capability_strategy_runtime_decision import decide_capability_strategy_runtime
from tests.capability_strategy_runtime_fixtures import strategy


def test_cli_consume_configure_decide_success(tmp_path):
    source = tmp_path / "decision.json"
    source.write_text(json.dumps(decide_capability_strategy_runtime(strategy())), encoding="utf-8")
    for command, status in (("consume", "consumed"), ("configure", "configured"), ("decide", "accepted")):
        output = tmp_path / f"{command}.json"
        value, code = run([command, str(source), "--output", str(output)])
        assert code == 0 and value["status"] == status
        assert json.loads(output.read_text(encoding="utf-8")) == value


def test_cli_invalid_input_nonzero_without_traceback(tmp_path):
    source = tmp_path / "invalid.json"; source.write_text("{}", encoding="utf-8")
    completed = subprocess.run([sys.executable, "-m", "cli.zero_capability_strategy_bootstrap", "consume", str(source)], capture_output=True, text=True, encoding="utf-8")
    assert completed.returncode != 0 and "Traceback" not in completed.stderr
    assert json.loads(completed.stdout)["status"] == "rejected"


def test_no_runtime_ownership_commands_or_forbidden_imports():
    help_text = build_parser().format_help()
    assert all(term not in help_text for term in ("execute", "schedule", "mission", "agent", "approve", "authorize", "activate", "mutation"))
