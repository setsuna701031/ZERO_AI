from copy import deepcopy
from core.runtime.runtime_capability_authorization_token_issuance_preparation import prepare_capability_authorization_token_issuance
from tests.test_runtime_capability_authorization_token_issuance_eligibility import evaluate
def prepare(value=None,at="2099-07-17T06:03:05Z"):return prepare_capability_authorization_token_issuance(evaluate() if value is None else value,prepared_at=at)
def test_prepared_stable_detached_and_bounded():
 u=evaluate();saved=deepcopy(u);a=prepare(u);b=prepare(dict(reversed(list(u.items()))));u["reasons"].append("x")
 assert a==b and u!=saved and a["prepared"] and a["issuance_preparation_created"]
 assert not any(a[n] for n in ("token_issued","token_signed","token_handed_off","token_material_created","runtime_activated","execution_authority_granted"))
def test_time_and_malformed():
 assert prepare(at="2099-07-17T06:02:29Z")["blocked"]
 assert prepare(at="2099-07-17T06:04:30Z")["expired"]
 assert prepare({})["invalid"]
def test_forged_flags_block():
 for n in ("token_issued","token_signed","token_handed_off","token_material_created","runtime_activated","execution_authority_granted"):
  u=evaluate();u[n]=True;assert prepare(u)["blocked"]
