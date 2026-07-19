from core.engineering.engineering_runtime_adapter_preparation_closure import *
from tests.runtime_adapter_preparation_fixtures import pipeline2, request
from core.engineering.engineering_runtime_adapter_preparation_policy import build_default_runtime_adapter_preparation_policy
from core.engineering.engineering_runtime_adapter_preparation_eligibility import evaluate_runtime_adapter_preparation_eligibility
from core.engineering.engineering_runtime_adapter_invocation_descriptor import build_runtime_adapter_invocation_descriptor
from core.engineering.engineering_runtime_adapter_preparation import build_runtime_adapter_preparation
def test_closed_mapping_and_non_execution():
 req,pol,elig,desc,prep,clo,*_=pipeline2(); assert clo['package_status']=='closed'; assert validate_runtime_adapter_preparation_closure(clo).valid
 for k in ('adapter_invocation_prohibited','runtime_invocation_prohibited','authority_consumption_prohibited','mutation_prohibited'): assert clo[k] is True
def test_not_closed_and_invalid_mapping():
 req,adm,h,s=request(adapter='bad'); pol=build_default_runtime_adapter_preparation_policy(); elig=evaluate_runtime_adapter_preparation_eligibility(req,pol,adm,h,s); desc=build_runtime_adapter_invocation_descriptor(req,elig,adm); prep=build_runtime_adapter_preparation(req,pol,elig,desc); clo=build_runtime_adapter_preparation_closure(req,pol,elig,desc,prep); assert clo['package_status']=='invalid'; assert not validate_runtime_adapter_preparation_closure({}).valid
