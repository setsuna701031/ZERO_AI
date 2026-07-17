from copy import deepcopy

from core.runtime.runtime_capability_active_authorization_preparation import prepare_capability_active_authorization
from tests.test_runtime_capability_active_authorization_eligibility import NOW, decision, evaluate


def eligibility(status="approved"):
    return evaluate(decision(status))


def prepare(value=None, timestamp=NOW):
    return prepare_capability_active_authorization(eligibility() if value is None else value, prepared_at=timestamp)


def test_status_mapping_and_no_authority():
    for source, target in (("approved", "prepared"), ("denied", "not_prepared"), ("blocked", "blocked"), ("invalid", "invalid")):
        result = prepare(eligibility(source))
        assert result["status"] == target and result[target]
        assert all(result[name] is False for name in ("active_authorization_created", "authorization_granted", "token_issued", "runtime_activated", "execution_authority_granted"))


def test_stable_identity_fingerprint_timestamp_and_detachment():
    source = eligibility(); saved = deepcopy(source)
    one = prepare(source); two = prepare(dict(reversed(list(source.items()))))
    source["reasons"].append("changed")
    assert one == two and saved != source
    assert prepare(saved, "2026-07-17T07:00:00Z")["fingerprint"] != one["fingerprint"]


def test_linkages_are_preserved():
    source = eligibility(); result = prepare(source)
    assert result["active_authorization_eligibility_id"] == source["eligibility_id"]
    for output, input_name in (("authorization_review_decision", "authorization_review_decision"), ("authorization_review_request", "authorization_review_request"), ("review_policy", "review_policy"), ("review_handoff", "review_handoff"), ("review", "review"), ("review_eligibility", "review_eligibility"), ("activation_proposal", "activation_proposal"), ("capability_profile", "capability_profile"), ("capability_strategy", "capability_strategy")):
        assert result[output + "_id"] == source[input_name + "_id"]
        assert result[output + "_fingerprint"] == source[input_name + "_fingerprint"]


def test_malformed_fingerprint_and_authority_fail_closed():
    assert prepare({})["status"] == "invalid"
    forged = eligibility(); forged["fingerprint"] = "0" * 64
    assert prepare(forged)["status"] == "invalid"
    authority = eligibility(); authority["token_issued"] = True
    result = prepare(authority)
    assert result["status"] == "blocked" and "authority_flag_violation" in result["errors"]
