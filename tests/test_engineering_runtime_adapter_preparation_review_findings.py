from core.engineering.engineering_runtime_adapter_preparation_review_findings import *
from core.engineering.engineering_runtime_adapter_preparation_review_eligibility import evaluate_runtime_adapter_preparation_review_eligibility
from core.engineering.engineering_runtime_adapter_preparation_review_policy import build_default_runtime_adapter_preparation_review_policy
from tests.runtime_adapter_preparation_review_fixtures import review_request,pipeline3
def test_findings_behavior_and_no_mutation():
 rr,pol,elig,f,*_=pipeline3(advisory_findings=['advisory_note']); assert f['blocking_findings']==[]; assert f['advisory_findings']==['advisory_note']; assert f['findings']==['advisory_note']; assert validate_runtime_adapter_preparation_review_findings(f).valid
 r,*_=review_request(preparation_overrides={'prepared_scope':{'files':['*']}}); p=build_default_runtime_adapter_preparation_review_policy(); e=evaluate_runtime_adapter_preparation_review_eligibility(r,p); before=dict(r); f=build_runtime_adapter_preparation_review_findings(r,p,e); assert 'wildcard_scope' in f['blocking_findings']; assert r==before; assert f['blocking_findings']==sorted(f['blocking_findings'])
