from __future__ import annotations
from copy import deepcopy
from core.runtime.runtime_capability_bootstrap_consumer import ProcessLocalLeaseRegistry, consumer_descriptor, consume_capability_bootstrap, create_consumption_request
from core.runtime.runtime_capability_bootstrap_consumer_validation import validate_consumer_descriptor, validate_consumption_request, validate_consumption_result, validate_lease
from tests.test_runtime_capability_bootstrap_consumer import accepted

def test_canonical_contracts_validate():
    integration, context = accepted(); request = create_consumption_request(integration=integration, runtime_context=context)
    result = consume_capability_bootstrap(request, integration=integration, runtime_context=context, registry=ProcessLocalLeaseRegistry())
    assert validate_consumer_descriptor(consumer_descriptor()).valid and validate_consumption_request(request).valid and validate_consumption_result(result).valid

def test_sensitive_non_json_and_tampered_safety_fields_are_rejected():
    integration, context = accepted()
    for metadata in ({"token": "secret"}, {"command": "run anything"}):
        request = create_consumption_request(integration=integration, runtime_context=context, metadata=metadata)
        assert not validate_consumption_request(request).valid
    for metadata in ({"callback": lambda: None}, {"provider": object()}):
        try: create_consumption_request(integration=integration, runtime_context=context, metadata=metadata)
        except TypeError: pass
        else: raise AssertionError("non-JSON object entered canonical serialization")
    opening = create_consumption_request(integration=integration, runtime_context=context, mode="open_readonly_lease"); leased = consume_capability_bootstrap(opening, integration=integration, runtime_context=context, registry=ProcessLocalLeaseRegistry())["lease"]
    for key, value in (("read_only", False), ("mutation_allowed", True), ("runtime_start_allowed", True)):
        changed = deepcopy(leased); changed[key] = value; assert not validate_lease(changed).valid

def test_lease_conflict_fails_closed():
    integration, context = accepted(); registry = ProcessLocalLeaseRegistry(); request = create_consumption_request(integration=integration, runtime_context=context, mode="open_readonly_lease")
    lease = consume_capability_bootstrap(request, integration=integration, runtime_context=context, registry=registry)["lease"]; changed = deepcopy(lease); changed["safe_warnings"] = ["different"]
    try: registry.issue(changed)
    except ValueError as exc: assert str(exc) == "lease_conflict"
    else: raise AssertionError("conflicting lease accepted")
