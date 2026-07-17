from copy import deepcopy
from core.runtime.runtime_capability_authorization_token_issuance_handoff import create_capability_authorization_token_issuance_handoff
from tests.test_runtime_capability_authorization_token_issuance_handoff_preparation import prepare_handoff
def handoff(value=None,recipient="runtime-activation-governance",at="2099-07-17T06:03:20Z"):return create_capability_authorization_token_issuance_handoff(prepare_handoff() if value is None else value,handed_off_at=at,recipient_id=recipient)
def test_handoff_stable_normalized_detached_and_non_delivery():
 u=prepare_handoff();saved=deepcopy(u);a=handoff(u," runtime-activation-governance ");b=handoff(dict(reversed(list(u.items()))));u["reasons"].append("x");assert a==b and u!=saved and a["handed_off"] and a["token_handed_off"] and a["recipient_id"]=="runtime-activation-governance"
 assert not any(a[n] for n in ("handoff_delivered","handoff_acknowledged","token_signed","token_material_created","bearer_credential_created","runtime_activated","execution_authority_granted","executor_admitted"))
def test_recipient_and_time_fail_closed():
 for r in (None,"",123,"bad\nvalue","https://host","C:\\secret"):
  assert handoff(recipient=r)["blocked"]
 assert handoff(at="2099-07-17T06:03:14Z")["blocked"]
 assert handoff(at="2099-07-17T06:04:10Z")["expired"]
 assert handoff({})["invalid"]
