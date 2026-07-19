from core.engineering.engineering_runtime_adapter_preparation_review_handoff import *
from tests.runtime_adapter_preparation_review_fixtures import pipeline3
def test_handoff_mapping():
 rr,pol,elig,findings,review,handoff,*_=pipeline3(); assert validate_runtime_adapter_preparation_review_handoff(handoff).valid; assert handoff['eligible_for_activation_review'] is True
 for k in ('activation_authorized','adapter_activated','adapter_invoked','runtime_invoked','authority_consumed','mutation_performed'): assert handoff[k] is False
 bad=build_runtime_adapter_preparation_review_handoff({**review,'review_status':'not_approved'},rr); assert not validate_runtime_adapter_preparation_review_handoff(bad).valid; assert bad['eligible_for_activation_review'] is False
 bad=build_runtime_adapter_preparation_review_handoff({**review,'review_status':'invalid'},rr); assert bad['eligible_for_activation_review'] is False
