from __future__ import annotations

from core.runtime.runtime_capability_bootstrap_executor import create_execution_request, execute_capability_bootstrap
from tests.test_runtime_capability_bootstrap_plan import make_plan

def _request(mode="validation_only", **kwargs):
    plan, values = make_plan(); d, det, profile, strategy, _, _, _ = values
    return create_execution_request(plan=plan, artifacts={"discovery": d, "detection": det, "profile": profile, "strategy": strategy}, mode=mode, **kwargs)

def test_request_and_result_are_deterministic_and_timestamps_are_observations():
    first = _request(requested_at="one"); second = _request(requested_at="two")
    assert first["request_id"] == second["request_id"] and first["fingerprint"] == second["fingerprint"]
    assert execute_capability_bootstrap(first)["execution_id"] == execute_capability_bootstrap(second)["execution_id"]

def test_validation_only_executes_ordered_symbolic_steps_without_invocations():
    result = execute_capability_bootstrap(_request())
    assert result["overall_status"] == "completed"
    assert [x["execution_order"] for x in result["ordered_step_results"]] == list(range(len(result["ordered_step_results"])))
    assert set(result["invocation_evidence"].values()) == {0}
    assert result["safety_attestations"] == {"mutation_performed": False, "runtime_started": False, "validation_only": True}

def test_prepare_handoff_is_sealed_symbolic_and_cpu_offline_safe():
    result = execute_capability_bootstrap(_request("prepare_handoff")); handoff = result["handoff_package"]
    assert handoff["allowed_future_consumer"] == "runtime_bootstrap_executor_v1"
    assert handoff["mutation_classification"] == "none" and handoff["runtime_started"] is False
    assert result["strategy_context"]["accelerator_policy"] == "disabled"
    assert result["capability_context"]["network_policy"] == "offline_only"

def test_required_provider_unbound_blocks_and_does_not_run_later_steps():
    plan, values = make_plan(bound=False); d, det, profile, strategy, _, _, _ = values
    request = create_execution_request(plan=plan, artifacts={"discovery": d, "detection": det, "profile": profile, "strategy": strategy})
    result = execute_capability_bootstrap(request)
    assert result["overall_status"] == "blocked"
    assert result["ordered_step_results"][-1]["step_type"] == "verify_provider_bindings"
