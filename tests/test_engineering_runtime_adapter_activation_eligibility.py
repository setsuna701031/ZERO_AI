from tests.runtime_adapter_activation_eligibility_fixtures import chain,request
from core.engineering.engineering_runtime_adapter_activation_eligibility import *
def test_final_eligible_mapping_and_links():
 *_,elig,__,___=chain(); assert elig['eligibility_status']=='eligible'; assert validate_runtime_adapter_activation_eligibility(elig).valid; assert elig['activation_authorized'] is False
 assert elig['activation_eligibility_request_fingerprint'] and elig['activation_eligibility_policy_fingerprint'] and elig['activation_constraint_profile_fingerprint'] and elig['activation_eligibility_evaluation_fingerprint']
def test_invalid_mapping_and_passive_enforcement():
 req=request(preparation_review_status='rejected'); *_,elig,__,___=chain(req); assert elig['eligibility_status']=='invalid'; elig['adapter_invoked']=True; assert not validate_runtime_adapter_activation_eligibility(elig).valid
