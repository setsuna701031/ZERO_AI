import json
import subprocess
import sys

from tests.test_engineering_capability_registry import registration, registry

CLI = [sys.executable, "-m", "cli.zero_engineering_capability_registry"]


def run(tmp_path, value, *args):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return subprocess.run(CLI + list(args) + ["--input", str(path)], text=True, capture_output=True)


def test_cli_validation_and_lookup(tmp_path):
    value = registry()
    valid = run(tmp_path, value, "validate")
    found = run(tmp_path, value, "lookup", "--capability-id", "repository.read")
    assert valid.returncode == found.returncode == 0
    assert json.loads(valid.stdout)["valid"] is True
    assert json.loads(found.stdout)["lookup_status"] == "found"


def test_cli_ambiguous_operation_fails(tmp_path):
    value = registry(registration("repository.read", "shared.read"), registration("workspace.observe", "shared.read"))
    result = run(tmp_path, value, "operations", "--operation", "shared.read")
    assert result.returncode != 0
    assert json.loads(result.stdout)["lookup_status"] == "ambiguous"
