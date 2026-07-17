from __future__ import annotations
from core.runtime.runtime_capability_bootstrap_consumer import ProcessLocalLeaseRegistry, consumer_descriptor, consume_capability_bootstrap, create_consumption_request
from core.runtime.runtime_capability_bootstrap_integration import RuntimeCapabilityContextContainer, create_integration_request, integrate_capability_bootstrap
from tests.test_runtime_capability_bootstrap_integration import completed_result

def accepted():
    container = RuntimeCapabilityContextContainer(); record = integrate_capability_bootstrap(create_integration_request(execution_result=completed_result(), mode="accept_handoff"), container=container)
    return record, container.resolve(record["runtime_context_id"])

def test_descriptor_request_and_results_are_deterministic_without_timestamps():
    integration, context = accepted(); a = create_consumption_request(integration=integration, runtime_context=context, requested_at="a"); b = create_consumption_request(integration=dict(reversed(list(integration.items()))), runtime_context=dict(reversed(list(context.items()))), requested_at="b")
    assert consumer_descriptor() == consumer_descriptor() and a["request_id"] == b["request_id"]
    one = consume_capability_bootstrap(a, integration=integration, runtime_context=context, registry=ProcessLocalLeaseRegistry(), consumed_at="a"); two = consume_capability_bootstrap(b, integration=integration, runtime_context=context, registry=ProcessLocalLeaseRegistry(), consumed_at="b")
    assert one["status"] == "validated" and one["consumption_id"] == two["consumption_id"] and one["eligibility"]["fingerprint"] == two["eligibility"]["fingerprint"]
    assert one["lease"] is None and set(one["invocation_evidence"].values()) == {0}

def test_lease_issue_idempotency_revoke_and_detached_consumption():
    integration, context = accepted(); registry = ProcessLocalLeaseRegistry()
    opening = create_consumption_request(integration=integration, runtime_context=context, mode="open_readonly_lease")
    first = consume_capability_bootstrap(opening, integration=integration, runtime_context=context, registry=registry); second = consume_capability_bootstrap(opening, integration=integration, runtime_context=context, registry=registry)
    assert first["status"] == second["status"] == "leased" and first["lease"]["lease_id"] == second["lease"]["lease_id"]
    consuming = create_consumption_request(integration=integration, runtime_context=context, mode="consume_context", lease_id=first["lease"]["lease_id"])
    result = consume_capability_bootstrap(consuming, integration=integration, runtime_context=context, registry=registry)
    assert result["status"] == "consumed" and result["read_only_context_view"]["runtime_context_id"] == context["runtime_context_id"]
    result["read_only_context_view"]["available_domains"].append("changed"); assert "changed" not in context["available_domains"]
    registry.revoke(first["lease"]["lease_id"]); revoked = consume_capability_bootstrap(consuming, integration=integration, runtime_context=context, registry=registry)
    assert revoked["status"] == "revoked" and registry.validate_state(first["lease"]["lease_id"]) is False

def test_fail_closed_for_bad_mode_scope_consumer_and_unsafe_runtime():
    integration, context = accepted()
    for field, value, expected in (("mode", "execute", "unsupported"), ("requested_lease_scope", "write", "invalid"), ("consumer_id", "other", "invalid")):
        request = create_consumption_request(integration=integration, runtime_context=context); request[field] = value
        result = consume_capability_bootstrap(request, integration=integration, runtime_context=context, registry=ProcessLocalLeaseRegistry()); assert result["status"] == expected
    unsafe = dict(integration); unsafe["runtime_started"] = True
    request = create_consumption_request(integration=unsafe, runtime_context=context)
    assert consume_capability_bootstrap(request, integration=unsafe, runtime_context=context, registry=ProcessLocalLeaseRegistry())["status"] in {"invalid", "rejected"}
