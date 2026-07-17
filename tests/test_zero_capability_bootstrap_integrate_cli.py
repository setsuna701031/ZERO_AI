from __future__ import annotations

import json
from cli.zero_capability_bootstrap_integrate import run
from core.runtime.runtime_capability_bootstrap_integration import create_integration_request
from tests.test_runtime_capability_bootstrap_integration import completed_result

def test_modes_and_defaults_are_bounded():
    assert run(["modes"])[0]["modes"] == ["accept_handoff", "prepare_context", "validate_only"]
    assert run(["defaults"])[0]["mode"] == "validate_only"

def test_integrate_validate_explain_json(tmp_path):
    request = create_integration_request(execution_result=completed_result(), mode="accept_handoff"); request_path = tmp_path / "request.json"; request_path.write_text(json.dumps(request), encoding="utf-8")
    record, code = run(["integrate", str(request_path)]); assert code == 0 and record["runtime_started"] is False
    record_path = tmp_path / "record.json"; record_path.write_text(json.dumps(record), encoding="utf-8")
    assert run(["validate", str(record_path)])[0]["valid"] is True
    assert run(["explain", str(record_path)])[0]["integration_status"] == "accepted"

