from core.engineering.engineering_runtime_adapter_preparation_review import *
from tests.runtime_adapter_preparation_review_fixtures import pipeline3
def test_review_mappings_and_invariants():
 rr,pol,elig,findings,review,*_=pipeline3(); assert review['review_status']=='approved'; assert validate_runtime_adapter_preparation_review(review).valid
 for k in ('activation_authorized','adapter_activated','adapter_invoked','runtime_invoked','executor_invoked','scheduler_invoked','authority_consumed','mutation_performed'): assert review[k] is False
 bad=build_runtime_adapter_preparation_review(rr,pol,{**elig,'eligibility_status':'ineligible','reason_codes':['scope_expansion']},findings); assert bad['review_status']=='not_approved'
 inv=build_runtime_adapter_preparation_review({**rr,'schema':'bad'},pol,elig,findings); assert inv['review_status']=='invalid'
 assert not validate_runtime_adapter_preparation_review({**review,'adapter_invoked':True}).valid
