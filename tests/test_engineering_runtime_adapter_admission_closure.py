from core.engineering.engineering_runtime_adapter_admission_closure import *
from tests.runtime_adapter_admission_fixtures import pipeline
def test_closure_closed_mapping():
 r,p,e,a,*_=pipeline(); c=build_runtime_adapter_admission_closure(r,p,e,a); assert c['package_status']=='closed'; assert c['runtime_invocation_prohibition']; assert c['mutation_prohibition']; assert c['authority_consumption_prohibition']; assert validate_runtime_adapter_admission_closure(c).valid; assert inspect_runtime_adapter_admission_closure(c)['valid']
def test_closure_not_closed_and_invalid_mapping():
 r,p,e,a,*_=pipeline(); assert build_runtime_adapter_admission_closure(r,p,e,{})['package_status']=='not_closed'
 assert build_runtime_adapter_admission_closure({}, {}, {}, {})['package_status']=='invalid'
