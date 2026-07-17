from __future__ import annotations

import json
from cli.zero_capability_bootstrap_execute import run
from core.runtime.runtime_capability_bootstrap_executor import create_execution_request
from tests.test_runtime_capability_bootstrap_plan import make_plan

def test_modes_and_defaults_are_bounded():
    assert run(["modes"])[0]["modes"] == ["prepare_handoff", "validation_only"]
    assert run(["defaults"])[0]["mutation_allowed"] is False

def test_execute_validate_and_explain(tmp_path):
    plan, values = make_plan(); d, det, profile, strategy, _, _, _ = values
    request = create_execution_request(plan=plan, artifacts={"discovery": d, "detection": det, "profile": profile, "strategy": strategy}, mode="prepare_handoff")
    request_path = tmp_path / "request.json"; request_path.write_text(json.dumps(request), encoding="utf-8")
    result, code = run(["execute", str(request_path)]); assert code == 0
    result_path = tmp_path / "result.json"; result_path.write_text(json.dumps(result), encoding="utf-8")
    assert run(["validate-result", str(result_path)])[0]["valid"] is True
    assert run(["explain", str(result_path)])[0]["overall_status"] == "completed"

