from __future__ import annotations
import json
from cli.zero_capability_bootstrap_consume import run
from core.runtime.runtime_capability_bootstrap_consumer import create_consumption_request
from tests.test_runtime_capability_bootstrap_consumer import accepted

def test_modes_scopes_defaults_are_bounded():
    assert run(["modes"])[0]["modes"] == ["consume_context", "open_readonly_lease", "validate_only"]
    assert "write" not in run(["scopes"])[0]["scopes"] and run(["defaults"])[0]["mode"] == "validate_only"

def test_consume_validate_explain_json(tmp_path):
    integration, context = accepted(); request = create_consumption_request(integration=integration, runtime_context=context)
    input_path = tmp_path / "input.json"; input_path.write_text(json.dumps({"request": request, "integration": integration, "runtime_context": context}), encoding="utf-8")
    result, code = run(["consume", str(input_path)]); assert code == 0 and result["status"] == "validated"
    result_path = tmp_path / "result.json"; result_path.write_text(json.dumps(result), encoding="utf-8")
    assert run(["validate", str(result_path)])[0]["valid"] is True and run(["explain", str(result_path)])[0]["runtime_started"] is False

def test_cli_consumes_only_an_explicit_lease(tmp_path):
    integration, context = accepted(); opening = create_consumption_request(integration=integration, runtime_context=context, mode="open_readonly_lease")
    open_path = tmp_path / "open.json"; open_path.write_text(json.dumps({"request": opening, "integration": integration, "runtime_context": context}), encoding="utf-8")
    leased, _ = run(["consume", str(open_path)])
    consuming = create_consumption_request(integration=integration, runtime_context=context, mode="consume_context", lease_id=leased["lease"]["lease_id"])
    consume_path = tmp_path / "consume.json"; consume_path.write_text(json.dumps({"request": consuming, "integration": integration, "runtime_context": context, "lease": leased["lease"]}), encoding="utf-8")
    result, code = run(["consume", str(consume_path)]); assert code == 0 and result["status"] == "consumed"
