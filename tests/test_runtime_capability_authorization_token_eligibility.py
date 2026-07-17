from copy import deepcopy

from core.runtime.runtime_capability_authorization_token_eligibility import evaluate_capability_authorization_token_eligibility
from tests.test_runtime_capability_active_authorization import authorize, preparation

NOW = "2099-07-17T06:01:00Z"


def evaluate(value=None, at=NOW):
    return evaluate_capability_authorization_token_eligibility(authorize() if value is None else value, evaluated_at=at)


def test_status_mapping_and_boundaries():
    for source, target in (("approved", "eligible"), ("denied", "ineligible"), ("blocked", "blocked"), ("invalid", "invalid")):
        result = evaluate(authorize(preparation(source)))
        assert result["status"] == target and result[target]
    assert evaluate(authorize(authorized_at="2000-01-01T00:00:00Z"))["status"] == "expired"
    assert evaluate(at="2099-07-17T06:05:00Z")["status"] == "expired"
    assert evaluate(at="2099-07-17T05:59:59Z")["status"] == "blocked"


def test_stability_fingerprint_detachment_and_lineage():
    source = authorize(); saved = deepcopy(source)
    one = evaluate(source); two = evaluate(dict(reversed(list(source.items()))))
    source["reasons"].append("changed")
    assert one == two and source != saved
    assert evaluate(saved, "2099-07-17T06:02:00Z")["fingerprint"] != one["fingerprint"]
    for prefix in ("active_authorization_preparation", "active_authorization_eligibility", "authorization_review_decision", "authorization_review_request", "review_policy", "review_handoff", "review", "review_eligibility", "activation_proposal", "capability_profile", "capability_strategy"):
        assert one[prefix + "_id"] == saved[prefix + "_id"]


def test_eligibility_does_not_create_authority_or_token():
    result = evaluate()
    assert result["token_eligibility_confirmed"]
    assert not any(result[name] for name in ("token_preparation_created", "token_created", "token_issued", "token_signed", "runtime_activated", "execution_authority_granted"))


def test_malformed_fingerprint_and_forged_state_fail_closed():
    assert evaluate({})["status"] == "invalid"
    bad = authorize(); bad["fingerprint"] = "0" * 64
    assert evaluate(bad)["status"] == "invalid"
    for field in ("token_issued", "runtime_activated", "execution_authority_granted"):
        forged = authorize(); forged[field] = True
        result = evaluate(forged)
        assert result["status"] == "blocked" and not result["token_eligibility_confirmed"]
