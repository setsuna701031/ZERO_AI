from tests.runtime_adapter_activation_authorization_fixtures import request
from core.engineering.engineering_runtime_adapter_activation_authorization_policy import build_default_runtime_adapter_activation_authorization_policy
from core.engineering.engineering_runtime_adapter_activation_authorization_review import *
def test_review_approved_and_deterministic_reasons():
 req=request(); pol=build_default_runtime_adapter_activation_authorization_policy(); r=evaluate_runtime_adapter_activation_authorization_review(req,pol); assert r['review_status']=='approved'; assert validate_runtime_adapter_activation_authorization_review(r).valid; assert r==evaluate_runtime_adapter_activation_authorization_review(req,pol)
def test_review_invalid_and_linkage():
 req=request(activation_eligibility_status='ineligible'); pol=build_default_runtime_adapter_activation_authorization_policy(); r=evaluate_runtime_adapter_activation_authorization_review(req,pol); assert r['review_status']=='invalid'; assert 'invalid_activation_authorization_request' in r['reason_codes']; p=dict(pol); p['frozen']=False; r=evaluate_runtime_adapter_activation_authorization_review(request(),p); assert 'invalid_activation_authorization_policy' in r['reason_codes']
