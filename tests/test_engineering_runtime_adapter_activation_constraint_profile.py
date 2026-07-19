from tests.runtime_adapter_activation_eligibility_fixtures import request
from core.engineering.engineering_runtime_adapter_activation_constraint_profile import *
def test_valid_passive_profile_invariants():
 p=build_runtime_adapter_activation_constraint_profile(request()); assert validate_runtime_adapter_activation_constraint_profile(p).valid
 for k,v in {'passive_only':True,'executable':False,'activation_authorized':False,'activation_token_issued':False,'adapter_loaded':False,'adapter_activated':False,'adapter_invoked':False,'runtime_invoked':False,'executor_invoked':False,'scheduler_invoked':False,'authority_consumed':False,'mutation_performed':False}.items(): assert p[k] is v
def test_profile_linkage_and_invariant_rejection():
 p=build_runtime_adapter_activation_constraint_profile(request()); p['activation_eligibility_request_id']='x'; assert not validate_runtime_adapter_activation_constraint_profile(p).valid
 p=build_runtime_adapter_activation_constraint_profile(request()); p['adapter_loaded']=True; assert not validate_runtime_adapter_activation_constraint_profile(p).valid
