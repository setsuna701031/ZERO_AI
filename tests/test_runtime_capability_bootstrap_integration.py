from __future__ import annotations

from core.runtime.runtime_capability_bootstrap_executor import create_execution_request, execute_capability_bootstrap
from core.runtime.runtime_capability_bootstrap_integration import RuntimeCapabilityContextContainer, create_integration_request, default_policy, integrate_capability_bootstrap
from tests.test_runtime_capability_bootstrap_plan import make_plan

def completed_result():
    plan, values = make_plan(); d, det, profile, strategy, _, _, _ = values
    return execute_capability_bootstrap(create_execution_request(plan=plan, artifacts={"discovery": d, "detection": det, "profile": profile, "strategy": strategy}, mode="prepare_handoff"))

def test_request_context_integration_and_eligibility_are_deterministic():
    result = completed_result(); a = create_integration_request(execution_result=result, mode="accept_handoff", requested_at="one"); b = create_integration_request(execution_result=dict(reversed(list(result.items()))), mode="accept_handoff", requested_at="two")
    assert a["request_id"] == b["request_id"]
    one = integrate_capability_bootstrap(a, container=RuntimeCapabilityContextContainer(), integrated_at="one"); two = integrate_capability_bootstrap(b, container=RuntimeCapabilityContextContainer(), integrated_at="two")
    assert one["integration_id"] == two["integration_id"] and one["runtime_context_id"] == two["runtime_context_id"]
    assert one["activation_eligibility"]["fingerprint"] == two["activation_eligibility"]["fingerprint"]

def test_accept_handoff_binds_context_but_never_starts_runtime():
    container = RuntimeCapabilityContextContainer(); record = integrate_capability_bootstrap(create_integration_request(execution_result=completed_result(), mode="accept_handoff"), container=container)
    assert record["integration_status"] == "accepted" and record["activation_eligibility"]["eligible"] is True
    assert record["runtime_started"] is False and record["mutation_performed"] is False
    assert container.resolve(record["runtime_context_id"])["runtime_started"] is False
    assert set(record["invocation_evidence"].values()) == {0}

def test_validate_only_does_not_bind_and_prepare_is_idempotent():
    result = completed_result(); container = RuntimeCapabilityContextContainer()
    validated = integrate_capability_bootstrap(create_integration_request(execution_result=result), container=container)
    assert validated["integration_status"] == "validated" and container.snapshot()["binding_count"] == 0
    request = create_integration_request(execution_result=result, mode="prepare_context")
    first = integrate_capability_bootstrap(request, container=container); second = integrate_capability_bootstrap(request, container=container)
    assert first["integration_id"] == second["integration_id"] and second["binding_metadata"]["state"] == "existing"

def test_conflicting_rebind_fails_closed():
    result = completed_result(); request = create_integration_request(execution_result=result, mode="prepare_context"); container = RuntimeCapabilityContextContainer()
    record = integrate_capability_bootstrap(request, container=container); changed = dict(record["runtime_context"]); changed["warnings"] = ["different"]
    container._bindings[record["runtime_context_id"]] = changed
    conflict = integrate_capability_bootstrap(request, container=container)
    assert conflict["integration_status"] == "rejected" and conflict["activation_blockers"] == ["runtime_context_conflict"]

def test_partial_is_not_accepted_without_explicit_policy():
    result = completed_result(); result["overall_status"] = "partial"; result["handoff_package"]["readiness"] = "partial"
    request = create_integration_request(execution_result=result, mode="accept_handoff")
    assert integrate_capability_bootstrap(request, container=RuntimeCapabilityContextContainer())["integration_status"] in {"invalid", "blocked"}

