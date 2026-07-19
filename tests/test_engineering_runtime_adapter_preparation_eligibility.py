from core.engineering.engineering_runtime_adapter_preparation_eligibility import *
from tests.runtime_adapter_preparation_fixtures import pipeline2, request
from core.engineering.engineering_runtime_adapter_preparation_policy import build_default_runtime_adapter_preparation_policy
def test_eligible_mapping_and_ordering():
 req,pol,elig,*_=pipeline2(); assert elig['eligibility_status']=='eligible'; assert elig['reason_codes']==[]; assert validate_runtime_adapter_preparation_eligibility(elig).valid
def test_ineligible_and_invalid_mapping():
 req,adm,h,s=request(adapter='other'); pol=build_default_runtime_adapter_preparation_policy(); e=evaluate_runtime_adapter_preparation_eligibility(req,pol,adm,h,s); assert e['eligibility_status']=='ineligible'; assert 'adapter_identity_mismatch' in e['reason_codes']; assert e['reason_codes']==sorted(e['reason_codes'])
 bad=evaluate_runtime_adapter_preparation_eligibility({},pol,adm,h,s); assert bad['eligibility_status']=='invalid'
