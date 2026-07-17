from __future__ import annotations

from copy import deepcopy
from core.runtime.runtime_capability_bootstrap_integration import RuntimeCapabilityContextContainer, create_integration_request, integrate_capability_bootstrap
from core.runtime.runtime_capability_bootstrap_integration_validation import validate_integration_record, validate_integration_request, validate_runtime_context
from tests.test_runtime_capability_bootstrap_integration import completed_result

def test_request_context_and_record_validate():
    request = create_integration_request(execution_result=completed_result(), mode="accept_handoff"); record = integrate_capability_bootstrap(request, container=RuntimeCapabilityContextContainer())
    assert validate_integration_request(request).valid and validate_runtime_context(record["runtime_context"]).valid and validate_integration_record(record).valid

def test_linkage_consumer_and_safety_mismatches_fail_closed():
    for mutate in (
        lambda x: x.update(handoff_id="other"),
        lambda x: x.update(expected_consumer="other"),
        lambda x: x["handoff"].update(mutation_classification="future_mutation"),
        lambda x: x["handoff"].update(runtime_started=True),
        lambda x: x["handoff"].update(prohibited_actions=[]),
    ):
        request = create_integration_request(execution_result=completed_result(), mode="accept_handoff"); mutate(request)
        assert not validate_integration_request(request).valid

def test_sensitive_metadata_callable_and_command_are_rejected():
    for metadata in ({"token": "secret"}, {"command": "run"}, {"callable": lambda: None}):
        try: request = create_integration_request(execution_result=completed_result(), metadata=metadata)
        except (TypeError, ValueError): continue
        assert not validate_integration_request(request).valid

def test_binding_observation_does_not_affect_identity():
    request = create_integration_request(execution_result=completed_result(), mode="prepare_context"); container = RuntimeCapabilityContextContainer()
    first = integrate_capability_bootstrap(request, container=container); second = integrate_capability_bootstrap(request, container=container)
    assert first["binding_metadata"] != second["binding_metadata"] and first["fingerprint"] == second["fingerprint"]

