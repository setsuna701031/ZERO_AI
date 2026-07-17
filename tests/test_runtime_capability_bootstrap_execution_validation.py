from __future__ import annotations

from copy import deepcopy
from core.runtime.runtime_capability_bootstrap_execution_validation import validate_execution_request, validate_execution_result
from core.runtime.runtime_capability_bootstrap_executor import create_execution_request, execute_capability_bootstrap
from tests.test_runtime_capability_bootstrap_plan import make_plan

def _values():
    plan, values = make_plan(); d, det, profile, strategy, _, _, _ = values
    request = create_execution_request(plan=plan, artifacts={"discovery": d, "detection": det, "profile": profile, "strategy": strategy}, mode="prepare_handoff")
    return request, execute_capability_bootstrap(request)

def test_request_and_result_validate():
    request, result = _values()
    assert validate_execution_request(request).valid
    assert validate_execution_result(result).valid

def test_identity_and_sensitive_leakage_fail_closed():
    request, result = _values(); broken = deepcopy(request); broken["bootstrap_plan_id"] = "other"
    assert not validate_execution_request(broken).valid
    leaked = deepcopy(result); leaked["warnings"] = [{"token": "secret"}]
    assert not validate_execution_result(leaked).valid

def test_result_rejects_handoff_consumer_and_nonzero_invocations():
    _, result = _values(); result["handoff_package"]["allowed_future_consumer"] = "other"
    assert not validate_execution_result(result).valid
    _, result = _values(); result["invocation_evidence"]["network_invocations"] = 1
    assert not validate_execution_result(result).valid
