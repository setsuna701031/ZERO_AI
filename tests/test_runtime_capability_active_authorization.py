from copy import deepcopy
import pytest
from core.runtime.runtime_capability_active_authorization import create_capability_active_authorization, DEFAULT_AUTHORIZATION_TTL_SECONDS
from tests.test_runtime_capability_active_authorization_preparation import eligibility, prepare

AT = "2099-07-17T06:00:00Z"
EXPIRES = "2099-07-17T06:05:00Z"
def preparation(status="approved"): return prepare(eligibility(status), AT)
def authorize(value=None, **kwargs): return create_capability_active_authorization(preparation() if value is None else value, authorized_at=kwargs.pop("authorized_at", AT), **kwargs)

def test_status_mapping_and_authority_boundary():
    for source, target in (("approved", "active"), ("denied", "not_authorized"), ("blocked", "blocked"), ("invalid", "invalid")):
        result = authorize(preparation(source)); assert result["status"] == target and result[target]
        assert result["active_authorization_created"] is (target == "active")
        assert result["authorization_granted"] is (target == "active")
        assert not any(result[x] for x in ("token_issued", "runtime_activated", "execution_authority_granted"))

def test_stability_ttl_expiry_and_detachment():
    source = preparation(); saved = deepcopy(source)
    one = authorize(source); two = authorize(dict(reversed(list(source.items()))))
    source["reasons"].append("changed")
    assert one == two and saved != source and one["authorization_ttl_seconds"] == DEFAULT_AUTHORIZATION_TTL_SECONDS
    assert authorize(saved, expires_at=EXPIRES, authorization_ttl_seconds=300)["fingerprint"] == one["fingerprint"]
    assert authorize(saved, expires_at="2099-07-17T06:04:00Z")["authorization_ttl_seconds"] == 240
    assert authorize(saved, authorized_at="2000-01-01T00:00:00Z")["status"] == "expired"

@pytest.mark.parametrize("ttl", [0, -1, 1.5, True, 901])
def test_invalid_ttl_fail_closed(ttl):
    result = authorize(authorization_ttl_seconds=ttl); assert result["status"] == "blocked" and not result["authorization_granted"]

def test_malformed_mismatch_and_authority_fail_closed():
    assert authorize({})["status"] == "invalid"
    bad = preparation(); bad["fingerprint"] = "0" * 64; assert authorize(bad)["status"] == "invalid"
    mismatch = authorize(expires_at="2099-07-17T06:04:00Z", authorization_ttl_seconds=300); assert mismatch["status"] == "blocked"
    forged = preparation(); forged["token_issued"] = True; assert authorize(forged)["status"] == "blocked"

def test_lineage_preserved():
    source = preparation(); result = authorize(source)
    assert result["active_authorization_preparation_id"] == source["preparation_id"]
    for prefix in ("active_authorization_eligibility", "authorization_review_decision", "authorization_review_request", "review_policy", "review_handoff", "review", "review_eligibility", "activation_proposal", "capability_profile", "capability_strategy"):
        assert result[prefix + "_id"] == source[prefix + "_id"]
