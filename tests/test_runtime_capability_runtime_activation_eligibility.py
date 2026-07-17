from tests.test_runtime_capability_authorization_token_issuance_handoff import handoff
from core.runtime.runtime_capability_runtime_activation_eligibility import evaluate_capability_runtime_activation_eligibility as build
def eligibility(value=None,at="2099-07-17T06:03:21Z"):return build(handoff() if value is None else value,evaluated_at=at)
def test_eligible_stable_safe():
 a=eligibility();b=eligibility();assert a==b and a["eligible"] and a["runtime_activation_eligibility_confirmed"] and not a["runtime_activated"]
def test_boundaries():assert eligibility(at="2099-07-17T06:03:19Z")["blocked"] and eligibility(at="2099-07-17T06:04:10Z")["expired"] and eligibility({})["invalid"]
