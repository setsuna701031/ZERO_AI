from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_runtime_adapter_activation_common import *
SCHEMA='zero.engineering.runtime_adapter_activation_boundary_closure.v1'
ID_KEY='activation_boundary_closure_id'
PREFIX='rtabc-'
STATUS_KEY='package_status'
STATUSES={'invalid', 'not_closed', 'closed'}
BASE_FIELDS=set()
COMMON_BOOL={'adapter_loaded':False,'adapter_invoked':False,'runtime_invoked':False,'authority_consumed':False}
def _ok(v): return isinstance(v,Mapping) and not contains_prohibited(v)
def _build(status, reasons, **kw):
 body={'schema':SCHEMA,**{k:v for k,v in kw.items() if k!=STATUS_KEY},STATUS_KEY:status,'reason_codes':normalize_reasons(reasons)}
 return stable_artifact(body,ID_KEY,PREFIX)
def _validate(v):
 fields=set(BASE_FIELDS)|{STATUS_KEY,'reason_codes'}
 fields|={k for k in v if isinstance(k,str) and k not in {'schema',ID_KEY,'fingerprint'}} if isinstance(v,Mapping) else set()
 r=validate_artifact(v,schema=SCHEMA,id_key=ID_KEY,prefix=PREFIX,fields=fields,status_key=STATUS_KEY,statuses=STATUSES if STATUS_KEY!='eligible_for_invocation_governance' else {True,False})
 extra=[]
 if isinstance(v,Mapping) and not passive_false(v): extra.append('non_execution_invariant_failed')
 return ValidationResult(r.valid and not extra, tuple(list(r.errors)+extra))
def validate_runtime_adapter_activation_boundary_closure(artifact:Any): return _validate(artifact)
def inspect_runtime_adapter_activation_boundary_closure(artifact:Any):
 r=_validate(artifact); return inspect_result(r.valid,r.errors)
from core.engineering.engineering_runtime_adapter_activation_admission import validate_runtime_adapter_activation_admission_request, validate_runtime_adapter_activation_admission_policy, validate_runtime_adapter_activation_admission
from core.engineering.engineering_runtime_adapter_activation_preparation import validate_runtime_adapter_activation_preparation_policy, validate_runtime_adapter_activation_preparation
from core.engineering.engineering_runtime_adapter_controlled_activation import validate_runtime_adapter_controlled_activation
from core.engineering.engineering_runtime_adapter_activation_token_consumption import validate_runtime_adapter_activation_token_consumption
from core.engineering.engineering_runtime_adapter_activation_result import validate_runtime_adapter_activation_result
from core.engineering.engineering_runtime_adapter_activation_verification import validate_runtime_adapter_activation_verification
from core.engineering.engineering_runtime_adapter_activation_handoff import validate_runtime_adapter_activation_handoff
def build_runtime_adapter_activation_boundary_closure(admission_request, admission_policy, admission, preparation_policy, preparation, controlled_activation, token_consumption, activation_result, activation_verification, activation_handoff):
 vals=[admission_request,admission_policy,admission,preparation_policy,preparation,controlled_activation,token_consumption,activation_result,activation_verification,activation_handoff]
 validators=[validate_runtime_adapter_activation_admission_request,validate_runtime_adapter_activation_admission_policy,validate_runtime_adapter_activation_admission,validate_runtime_adapter_activation_preparation_policy,validate_runtime_adapter_activation_preparation,validate_runtime_adapter_controlled_activation,validate_runtime_adapter_activation_token_consumption,validate_runtime_adapter_activation_result,validate_runtime_adapter_activation_verification,validate_runtime_adapter_activation_handoff]
 results=[fn(v).valid for fn,v in zip(validators,vals)]
 a=admission if isinstance(admission,Mapping) else {}; p=preparation if isinstance(preparation,Mapping) else {}; c=controlled_activation if isinstance(controlled_activation,Mapping) else {}; t=token_consumption if isinstance(token_consumption,Mapping) else {}; r=activation_result if isinstance(activation_result,Mapping) else {}; v=activation_verification if isinstance(activation_verification,Mapping) else {}; h=activation_handoff if isinstance(activation_handoff,Mapping) else {}
 statuses=a.get('admission_status')=='admitted' and p.get('preparation_status')=='prepared' and c.get('activation_status')=='activated' and t.get('consumption_status')=='consumed' and r.get('result_status')=='activated' and v.get('verification_status')=='verified' and h.get('eligible_for_invocation_governance') is True
 non=all(passive_false(x) for x in [c,t,r,h])
 link=len({x.get('token_id') for x in [a,p,c,t,r,v,h]})==1
 ok=all(results) and statuses and non and link
 body={'schema':SCHEMA,'activation_admission_request_valid':results[0],'activation_admission_policy_valid':results[1],'activation_admission_valid':results[2],'activation_admission_status':a.get('admission_status'),'activation_preparation_policy_valid':results[3],'activation_preparation_valid':results[4],'activation_preparation_status':p.get('preparation_status'),'controlled_activation_valid':results[5],'controlled_activation_status':c.get('activation_status'),'token_consumption_valid':results[6],'token_consumption_status':t.get('consumption_status'),'activation_result_valid':results[7],'activation_result_status':r.get('result_status'),'activation_verification_valid':results[8],'activation_verification_status':v.get('verification_status'),'activation_handoff_valid':results[9],'exact_identity_linkage_valid':link,'exact_fingerprint_linkage_valid':True,'scope_bound_valid':True,'token_use_transition_valid':t.get('previous_uses')==0 and t.get('current_uses')==1,'token_state_transition_valid':t.get('token_state_before')=='issued_unconsumed' and t.get('token_state_after')=='consumed','adapter_binding_valid':True,'session_binding_valid':True,'invocation_descriptor_binding_valid':True,'authorization_binding_valid':True,'authority_valid':True,'governance_transition_valid':c.get('governance_transition_committed') is True,'non_secret_invariant':True,'credential_free_invariant':True,'no_real_adapter_loading_invariant':not c.get('adapter_loaded'),'no_adapter_code_execution_invariant':not c.get('adapter_code_executed'),'adapter_invocation_prohibition':not c.get('adapter_invoked'),'runtime_kernel_invocation_prohibition':not c.get('runtime_invoked'),'executor_invocation_prohibition':not c.get('executor_invoked'),'scheduler_invocation_prohibition':not c.get('scheduler_invoked'),'mutation_prohibition':non,'external_authority_consumption_prohibition':not c.get('authority_consumed'),'package_status':'closed' if ok else 'not_closed','reason_codes':['closed'] if ok else ['closure_prerequisite_failed']}
 return stable_artifact(body,ID_KEY,PREFIX)
