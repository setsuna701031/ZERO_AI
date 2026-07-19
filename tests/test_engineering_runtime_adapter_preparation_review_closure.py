from core.engineering.engineering_runtime_adapter_preparation_review_closure import *
from core.engineering.engineering_runtime_adapter_preparation_review_handoff import build_runtime_adapter_preparation_review_handoff
from tests.runtime_adapter_preparation_review_fixtures import pipeline3
def test_closure_mapping_and_meaning():
 rr,pol,elig,findings,review,handoff,closure,*_=pipeline3(); assert closure['package_status']=='closed'; assert validate_runtime_adapter_preparation_review_closure(closure).valid
 assert closure['activation_prohibited'] and closure['adapter_invocation_prohibited'] and closure['runtime_invocation_prohibited'] and closure['authority_consumption_prohibited'] and closure['mutation_prohibited']
 badh=build_runtime_adapter_preparation_review_handoff({**review,'review_status':'not_approved'},rr); c=build_runtime_adapter_preparation_review_closure(rr,pol,elig,findings,{**review,'review_status':'not_approved'},badh); assert c['package_status']=='invalid'
 inv=build_runtime_adapter_preparation_review_closure({**rr,'schema':'bad'},pol,elig,findings,review,handoff); assert inv['package_status']=='invalid'
