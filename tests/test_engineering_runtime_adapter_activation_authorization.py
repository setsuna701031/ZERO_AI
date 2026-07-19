from tests.runtime_adapter_activation_authorization_fixtures import chain_auth, request
from core.engineering.engineering_runtime_adapter_activation_authorization import *
from core.engineering.engineering_runtime_adapter_activation_authorization_policy import build_default_runtime_adapter_activation_authorization_policy
from core.engineering.engineering_runtime_adapter_activation_authorization_review import evaluate_runtime_adapter_activation_authorization_review
def test_authorized_mapping_and_invariants():
 req,pol,rev,auth,_,_=chain_auth(); assert auth['authorization_status']=='authorized'; assert validate_runtime_adapter_activation_authorization(auth).valid; assert auth['activation_authorized'] is True
 for k in ['activation_token_issued','token_material_present','adapter_loaded','adapter_activated','adapter_invoked','runtime_invoked','executor_invoked','scheduler_invoked','authority_consumed','mutation_performed']: assert auth[k] is False
def test_not_authorized_invalid_and_linkage():
 req=request(activation_eligibility_status='ineligible'); pol=build_default_runtime_adapter_activation_authorization_policy(); rev=evaluate_runtime_adapter_activation_authorization_review(req,pol); auth=build_runtime_adapter_activation_authorization(req,pol,rev); assert auth['authorization_status']=='not_authorized' or auth['authorization_status']=='invalid'
 rev=dict(rev); rev['review_status']='approved'; auth=build_runtime_adapter_activation_authorization(req,pol,rev); assert auth['authorization_status']!='authorized'
