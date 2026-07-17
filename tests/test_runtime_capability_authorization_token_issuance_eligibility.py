from copy import deepcopy

from core.runtime.runtime_capability_authorization_token import _hash
from core.runtime.runtime_capability_authorization_token_issuance_eligibility import (
    evaluate_capability_authorization_token_issuance_eligibility,
)
from tests.test_runtime_capability_authorization_token import create

EVALUATED_AT = "2099-07-17T06:03:00Z"

def evaluate(value=None, at=EVALUATED_AT):
    return evaluate_capability_authorization_token_issuance_eligibility(create() if value is None else value, evaluated_at=at)

def token_with_status(status):
    token = create()
    token["status"] = status
    for name in ("created", "not_created", "blocked", "invalid", "expired"): token[name] = name == status
    token["token_created"] = status == "created"
    base = {key: value for key, value in token.items() if key not in {"token_id", "fingerprint"}}
    token["fingerprint"] = _hash(base)
    token["token_id"] = "capability-authorization-token-" + token["fingerprint"][:24]
    return token

def test_status_mapping_and_time_boundaries():
    assert evaluate()["eligible"]
    for source, target in (("not_created", "ineligible"), ("blocked", "blocked"), ("invalid", "invalid"), ("expired", "expired")):
        assert evaluate(token_with_status(source))["status"] == target
    assert evaluate(at="2099-07-17T06:04:30Z")["expired"]
    assert evaluate(at="2099-07-17T06:04:31Z")["expired"]
    assert evaluate(at="2099-07-17T06:02:29Z")["blocked"]
    assert evaluate(at="2099-07-17T06:05:00Z")["expired"]

def test_stability_detachment_lineage_and_lifetime_preservation():
    source = create(); saved = deepcopy(source)
    one = evaluate(source); two = evaluate(dict(reversed(list(source.items()))))
    source["reasons"].append("changed")
    assert one == two and source != saved
    assert evaluate(saved, "2099-07-17T06:03:01Z")["fingerprint"] != one["fingerprint"]
    for source_name, target_name in (("created_at", "token_created_at"), ("expires_at", "token_expires_at"), ("token_ttl_seconds", "token_ttl_seconds"), ("authorized_at", "authorized_at"), ("authorization_expires_at", "authorization_expires_at"), ("authorization_ttl_seconds", "authorization_ttl_seconds")):
        assert one[target_name] == saved[source_name]
    for prefix in ("active_authorization_preparation", "active_authorization_eligibility", "authorization_review_decision", "authorization_review_request", "review_policy", "review_handoff", "review", "review_eligibility", "activation_proposal", "capability_profile", "capability_strategy"):
        assert one[prefix + "_id"] == saved[prefix + "_id"]

def test_eligible_confirms_only_eligibility():
    result = evaluate()
    assert result["issuance_eligibility_confirmed"]
    assert not any(result[name] for name in ("issuance_preparation_created", "token_issued", "token_signed", "token_handed_off", "token_material_created", "runtime_activated", "execution_authority_granted"))
    assert not any(field in result for field in ("token_value", "token_secret", "signature", "bearer", "credential"))

def test_malformed_fingerprint_and_forged_state_fail_closed():
    assert evaluate({})["invalid"]
    bad = create(); bad["fingerprint"] = "0" * 64
    assert evaluate(bad)["invalid"]
    for field in ("token_issued", "token_signed", "token_handed_off", "token_material_created", "runtime_activated", "execution_authority_granted"):
        forged = create(); forged[field] = True
        result = evaluate(forged)
        assert result["blocked"] and not result["issuance_eligibility_confirmed"]
