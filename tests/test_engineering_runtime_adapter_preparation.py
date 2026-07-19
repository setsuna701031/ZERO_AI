from core.engineering.engineering_runtime_adapter_preparation import *
from tests.runtime_adapter_preparation_fixtures import pipeline2, request
from core.engineering.engineering_runtime_adapter_preparation_policy import build_default_runtime_adapter_preparation_policy
from core.engineering.engineering_runtime_adapter_preparation_eligibility import evaluate_runtime_adapter_preparation_eligibility
from core.engineering.engineering_runtime_adapter_invocation_descriptor import build_runtime_adapter_invocation_descriptor
def test_prepared_mapping():
 *_,prep,_,_,_,_=pipeline2(); assert prep['preparation_status']=='prepared'; assert validate_runtime_adapter_preparation(prep).valid
def test_not_prepared_and_invalid_mapping_linkage():
 req,adm,h,s=request(adapter='bad'); pol=build_default_runtime_adapter_preparation_policy(); elig=evaluate_runtime_adapter_preparation_eligibility(req,pol,adm,h,s); desc=build_runtime_adapter_invocation_descriptor(req,elig,adm); prep=build_runtime_adapter_preparation(req,pol,elig,desc); assert prep['preparation_status']=='invalid'
 good=pipeline2(); bad=build_runtime_adapter_preparation(good[0],good[1],good[2],{**good[3],'preparation_request_id':'x'}); assert 'invalid_descriptor' in bad['reason_codes']
