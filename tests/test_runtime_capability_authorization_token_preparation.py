from copy import deepcopy

from core.runtime.runtime_capability_authorization_token_preparation import prepare_capability_authorization_token
from tests.test_runtime_capability_authorization_token_eligibility import evaluate
from tests.test_runtime_capability_active_authorization import authorize, preparation

PREPARED_AT = "2099-07-17T06:02:00Z"


def prepare(value=None, at=PREPARED_AT):
    return prepare_capability_authorization_token(evaluate() if value is None else value, prepared_at=at)


def test_status_mapping_and_time_boundaries():
    for source, target in (("approved", "prepared"), ("denied", "not_prepared"), ("blocked", "blocked"), ("invalid", "invalid")):
        result = prepare(evaluate(authorize(preparation(source))))
        assert result["status"] == target and result[target]
    assert prepare(evaluate(authorize(authorized_at="2000-01-01T00:00:00Z")))["expired"]
    assert prepare(at="2099-07-17T06:05:00Z")["expired"]
    assert prepare(at="2099-07-17T06:05:01Z")["expired"]
    assert prepare(at="2099-07-17T05:59:59Z")["blocked"]


def test_stability_detachment_lineage_and_lifetime_preservation():
    source = evaluate(); saved = deepcopy(source)
    one = prepare(source); two = prepare(dict(reversed(list(source.items()))))
    source["reasons"].append("changed")
    assert one == two and source != saved
    assert prepare(saved, "2099-07-17T06:03:00Z")["fingerprint"] != one["fingerprint"]
    assert one["authorized_at"] == saved["authorized_at"]
    assert one["expires_at"] == saved["expires_at"]
    assert one["authorization_ttl_seconds"] == saved["authorization_ttl_seconds"]
    assert one["eligibility_evaluated_at"] == saved["evaluated_at"]
    for prefix in ("active_authorization_preparation", "active_authorization_eligibility", "authorization_review_decision", "authorization_review_request", "review_policy", "review_handoff", "review", "review_eligibility", "activation_proposal", "capability_profile", "capability_strategy"):
        assert one[prefix + "_id"] == saved[prefix + "_id"]


def test_prepared_creates_only_preparation_record():
    result = prepare()
    assert result["token_preparation_created"]
    assert not any(result[name] for name in ("token_created", "token_issued", "token_signed", "token_material_created", "runtime_activated", "execution_authority_granted"))
    for forbidden in ("token_value", "token_secret", "signature", "bearer", "credential"):
        assert forbidden not in result


def test_malformed_fingerprint_and_forged_state_fail_closed():
    assert prepare({})["invalid"]
    bad = evaluate(); bad["fingerprint"] = "0" * 64
    assert prepare(bad)["invalid"]
    for field in ("token_created", "token_issued", "token_signed", "runtime_activated", "execution_authority_granted"):
        forged = evaluate(); forged[field] = True
        result = prepare(forged)
        assert result["blocked"] and not result["token_preparation_created"]
