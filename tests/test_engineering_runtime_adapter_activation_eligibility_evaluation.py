from tests.runtime_adapter_activation_eligibility_fixtures import request,chain
from core.engineering.engineering_runtime_adapter_activation_eligibility_policy import build_default_runtime_adapter_activation_eligibility_policy
from core.engineering.engineering_runtime_adapter_activation_constraint_profile import build_runtime_adapter_activation_constraint_profile
from core.engineering.engineering_runtime_adapter_activation_eligibility_evaluation import *
def test_eligible_mapping_and_reason_order():
 req,pol,prof,ev,*_=chain(); assert ev['eligibility_status']=='eligible'; assert ev['reason_codes']==[]; assert validate_runtime_adapter_activation_eligibility_evaluation(ev).valid
def test_ineligible_and_invalid_mapping():
 r=request(); r['requested_activation_scope']={'operations':['write']}; p=build_default_runtime_adapter_activation_eligibility_policy(); prof=build_runtime_adapter_activation_constraint_profile(r); ev=evaluate_runtime_adapter_activation_eligibility(r,p,prof); assert ev['eligibility_status']=='invalid'; assert ev['reason_codes']==sorted(ev['reason_codes'])
 p['frozen']=False; ev=evaluate_runtime_adapter_activation_eligibility(request(),p,build_runtime_adapter_activation_constraint_profile(request())); assert ev['eligibility_status']=='invalid'
def test_profile_linkage_enforced():
 r=request(); p=build_default_runtime_adapter_activation_eligibility_policy(); prof=build_runtime_adapter_activation_constraint_profile(r); prof['adapter_id']='other'; ev=evaluate_runtime_adapter_activation_eligibility(r,p,prof); assert 'adapter_identity_mismatch' in ev['reason_codes']
