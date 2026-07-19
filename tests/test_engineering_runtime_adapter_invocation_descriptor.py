from core.engineering.engineering_runtime_adapter_invocation_descriptor import *
from tests.runtime_adapter_preparation_fixtures import pipeline2, request
from core.engineering.engineering_runtime_adapter_preparation_policy import build_default_runtime_adapter_preparation_policy
from core.engineering.engineering_runtime_adapter_preparation_eligibility import evaluate_runtime_adapter_preparation_eligibility
def test_valid_passive_descriptor():
 req,pol,elig,desc,*_=pipeline2(); assert validate_runtime_adapter_invocation_descriptor(desc).valid
 for k,v in INV.items(): assert desc[k] is v
def test_descriptor_rejects_ineligible_and_mismatch():
 req,adm,h,s=request(adapter='bad'); pol=build_default_runtime_adapter_preparation_policy(); elig=evaluate_runtime_adapter_preparation_eligibility(req,pol,adm,h,s); desc=build_runtime_adapter_invocation_descriptor(req,elig,adm); assert not validate_runtime_adapter_invocation_descriptor(desc).valid
 good=pipeline2()[3]; assert not validate_runtime_adapter_invocation_descriptor({**good,'prepared_scope':{'files':['b']}}).valid
