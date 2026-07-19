from core.engineering.engineering_runtime_adapter_admission import *
from tests.runtime_adapter_admission_fixtures import pipeline,request
from core.engineering.engineering_runtime_adapter_admission_policy import build_default_runtime_adapter_admission_policy
def test_admitted_mapping_and_invariants():
 r,p,e,a,*_=pipeline(); assert a['admission_status']=='admitted'; assert a['boundary']['runtime_adapter_invoked'] is False; assert a['boundary']['authority_consumed'] is False; assert validate_runtime_adapter_admission(a).valid; assert inspect_runtime_adapter_admission(a)['valid']
def test_not_admitted_and_invalid_mapping():
 r,p,e,a,*_=pipeline(scope={'files':['c']}); assert a['admission_status']!='admitted'
 r,_,_,_=request(); bad=build_runtime_adapter_admission(r,{},build_default_runtime_adapter_admission_policy()); assert bad['admission_status']=='invalid'
