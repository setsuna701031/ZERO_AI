from copy import deepcopy

from core.runtime.runtime_capability_authorization_token import create_capability_authorization_token
from tests.test_runtime_capability_authorization_token_preparation import prepare

CREATED_AT = "2099-07-17T06:02:30Z"

def create(value=None, **kwargs):
    kwargs.setdefault("created_at", CREATED_AT)
    return create_capability_authorization_token(prepare() if value is None else value, **kwargs)

def test_created_is_deterministic_detached_and_non_authority_bearing():
    source = prepare(); saved = deepcopy(source)
    one = create(source); two = create(dict(reversed(list(source.items()))))
    source["reasons"].append("changed")
    assert one == two and source != saved
    assert one["created"] and one["token_created"]
    assert not any(one[name] for name in ("token_material_created", "token_signed", "token_issued", "token_handed_off", "runtime_activated", "execution_authority_granted"))
    assert not any(name in one for name in ("token_value", "token_secret", "bearer_token", "signature", "credential"))

def test_status_mapping_and_authorization_boundaries():
    for source, target in (("not_prepared", "not_created"), ("blocked", "blocked"), ("invalid", "invalid"), ("expired", "expired")):
        p = prepare(); p["status"] = source
        for name in ("prepared", "not_prepared", "blocked", "invalid", "expired"): p[name] = name == source
        p["token_preparation_created"] = source == "prepared"
        from core.runtime.runtime_capability_authorization_token_preparation import _hash
        base = {k: v for k, v in p.items() if k not in {"preparation_id", "fingerprint"}}
        p["fingerprint"] = _hash(base); p["preparation_id"] = "capability-authorization-token-preparation-" + p["fingerprint"][:24]
        assert create(p)["status"] == target
    assert create(created_at="2099-07-17T05:59:59Z")["blocked"]
    assert create(created_at="2099-07-17T06:05:00Z")["expired"]

def test_ttl_rules_and_fail_closed_input():
    assert create()["token_ttl_seconds"] == 120
    assert create(token_ttl_seconds=30)["expires_at"] == "2099-07-17T06:03:00Z"
    assert create(expires_at="2099-07-17T06:03:15Z")["token_ttl_seconds"] == 45
    assert create(token_ttl_seconds=180)["blocked"]
    for ttl in (0, -1, 1.5, True, 301): assert create(token_ttl_seconds=ttl)["blocked"]
    assert create({})["invalid"]
