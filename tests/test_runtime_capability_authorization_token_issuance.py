from copy import deepcopy
from core.runtime.runtime_capability_authorization_token_issuance import issue_capability_authorization_token
from tests.test_runtime_capability_authorization_token_issuance_preparation import prepare
def issue(value=None,**kw):kw.setdefault("issued_at","2099-07-17T06:03:10Z");return issue_capability_authorization_token(prepare() if value is None else value,**kw)
def test_issued_ttl_stability_and_flags():
 u=prepare();saved=deepcopy(u);a=issue(u);b=issue(dict(reversed(list(u.items()))));u["reasons"].append("x");assert a==b and u!=saved and a["issued"] and a["token_issued"] and a["issuance_ttl_seconds"]==60
 assert not any(a[n] for n in ("token_signed","token_handed_off","token_material_created","bearer_credential_created","runtime_activated","execution_authority_granted"))
def test_explicit_ttl_expiry_and_fail_closed():
 assert issue(issuance_ttl_seconds=30)["issuance_expires_at"]=="2099-07-17T06:03:40Z"
 assert issue(issuance_expires_at="2099-07-17T06:03:50Z")["issuance_ttl_seconds"]==40
 assert issue(issuance_expires_at="2099-07-17T06:03:50Z",issuance_ttl_seconds=20)["blocked"]
 for t in (0,-1,1.5,True,121):assert issue(issuance_ttl_seconds=t)["blocked"]
 assert issue({})["invalid"]
