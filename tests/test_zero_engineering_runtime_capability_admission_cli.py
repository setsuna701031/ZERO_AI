import json

from cli.zero_engineering_runtime import main
from tests.test_engineering_runtime_capability_admission import ADAPTER_FP, ADAPTER_ID, registration
from core.engineering.engineering_capability_registry import build_capability_registry
from tests.engineering_runtime_orchestrator_fixtures import request_payload


def invoke(capsys, tmp_path, capability="repository.read"):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(build_capability_registry([registration()])), encoding="utf-8")
    code = main(["capability-admission", "--json", json.dumps(request_payload()), "--capability-registry", str(path),
                 "--capability-id", capability, "--capability-operation", "repository.read",
                 "--adapter-id", ADAPTER_ID, "--adapter-fingerprint", ADAPTER_FP])
    return code, json.loads(capsys.readouterr().out)


def test_cli_capability_admission_inspect(capsys, tmp_path):
    code, result = invoke(capsys, tmp_path)
    assert code == 0 and result["status"] == "admitted" and result["adapter_invoked"] is False


def test_cli_invalid_capability_nonzero(capsys, tmp_path):
    code, result = invoke(capsys, tmp_path, "unknown")
    assert code != 0 and result["status"] == "not_registered"
