from copy import deepcopy
from core.runtime.runtime_capability_authorization_token_issuance_handoff_preparation import prepare_capability_authorization_token_issuance_handoff
from tests.test_runtime_capability_authorization_token_issuance import issue
def prepare_handoff(value=None,at="2099-07-17T06:03:15Z"):return prepare_capability_authorization_token_issuance_handoff(issue() if value is None else value,prepared_at=at)
def test_prepared_stable_detached_flags():
 u=issue();saved=deepcopy(u);a=prepare_handoff(u);b=prepare_handoff(dict(reversed(list(u.items()))));u["reasons"].append("x");assert a==b and u!=saved and a["prepared"] and a["handoff_preparation_created"]
 assert not any(a[n] for n in ("token_handed_off","handoff_completed","token_signed","token_material_created","bearer_credential_created","runtime_activated","execution_authority_granted"))
def test_boundaries_malformed_forged():
 assert prepare_handoff(at="2099-07-17T06:03:09Z")["blocked"]
 assert prepare_handoff(at="2099-07-17T06:04:10Z")["expired"]
 assert prepare_handoff({})["invalid"]
 u=issue();u["token_signed"]=True;assert prepare_handoff(u)["blocked"]
