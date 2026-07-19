from tests.runtime_adapter_activation_eligibility_fixtures import chain,request
from core.engineering.engineering_runtime_adapter_activation_eligibility_handoff import *
def test_valid_handoff_from_eligible_decision():
 *_,elig,ho,clo=chain(); assert ho['eligible_for_activation_authorization'] is True; assert validate_runtime_adapter_activation_eligibility_handoff(ho).valid
 for k in ('activation_authorized','activation_token_issued','adapter_loaded','adapter_activated','adapter_invoked','runtime_invoked','authority_consumed','mutation_performed'): assert ho[k] is False
 assert 'activation_token' not in ho
def test_invalid_decision_not_eligible_and_linkage():
 *_,elig,ho,_=chain(request(preparation_review_status='rejected')); assert ho['eligible_for_activation_authorization'] is False; ho['activation_eligibility_id']='x'; assert not validate_runtime_adapter_activation_eligibility_handoff(ho).valid
