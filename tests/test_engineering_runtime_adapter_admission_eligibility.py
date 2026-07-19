from core.engineering.engineering_runtime_adapter_admission_eligibility import *
from tests.runtime_adapter_admission_fixtures import request,AUTH
def test_eligible_mapping():
 r,h,s,a=request(); e=evaluate_runtime_adapter_admission_eligibility(r,h,s,a); assert e['eligibility_status']=='eligible'; assert validate_runtime_adapter_admission_eligibility(e).valid; assert inspect_runtime_adapter_admission_eligibility(e)['valid']
def test_ineligible_linkage_and_terminal():
 r,h,s,a=request(); h={**h,'engineering_runtime_handoff_id':'bad'}; assert 'handoff_id_mismatch' in evaluate_runtime_adapter_admission_eligibility(r,h,s,a)['reason_codes']
 r,h,s,a=request(); h={**h,'fingerprint':'bad'}; assert 'handoff_fingerprint_mismatch' in evaluate_runtime_adapter_admission_eligibility(r,h,s,a)['reason_codes']
 r,h,s,a=request(); s={**s,'engineering_execution_session_id':'bad'}; assert 'session_id_mismatch' in evaluate_runtime_adapter_admission_eligibility(r,h,s,a)['reason_codes']
 r,h,s,a=request(); a={**a,'engineering_execution_admission_id':'bad'}; assert 'governed_admission_id_mismatch' in evaluate_runtime_adapter_admission_eligibility(r,h,s,a)['reason_codes']
 r,h,s,a=request(); h={**h,'status':'closed'}; assert 'terminal_upstream_state' in evaluate_runtime_adapter_admission_eligibility(r,h,s,a)['reason_codes']
def test_invalid_mapping_for_scope_authority_payloads():
 for kw in ({'scope':{'files':['c']}},{'scope':{'files':['*']}},{'auth':{**AUTH,'closed':True}},{'auth':{**AUTH,'token':'x'}}):
  r,h,s,a=request(**kw); assert evaluate_runtime_adapter_admission_eligibility(r,h,s,a)['eligibility_status'] in {'invalid','ineligible'}
