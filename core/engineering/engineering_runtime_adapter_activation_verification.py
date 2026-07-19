from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_runtime_adapter_activation_common import *
SCHEMA='zero.engineering.runtime_adapter_activation_verification.v1'
ID_KEY='activation_verification_id'
PREFIX='rtav-'
STATUS_KEY='verification_status'
STATUSES={'not_verified', 'verified', 'invalid'}
BASE_FIELDS={'controlled_activation_id', 'verified_scope', 'adapter_id', 'token_id', 'token_consumption_id', 'activation_preparation_id', 'controlled_activation_fingerprint', 'adapter_version', 'execution_session_id', 'token_consumption_fingerprint', 'invocation_descriptor_id', 'activation_result_fingerprint', 'activation_result_id', 'activation_admission_id'}
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
def validate_runtime_adapter_activation_verification(artifact:Any): return _validate(artifact)
def inspect_runtime_adapter_activation_verification(artifact:Any):
 r=_validate(artifact); return inspect_result(r.valid,r.errors)
from core.engineering.engineering_runtime_adapter_activation_admission import validate_runtime_adapter_activation_admission
from core.engineering.engineering_runtime_adapter_activation_preparation import validate_runtime_adapter_activation_preparation
from core.engineering.engineering_runtime_adapter_controlled_activation import validate_runtime_adapter_controlled_activation
from core.engineering.engineering_runtime_adapter_activation_token_consumption import validate_runtime_adapter_activation_token_consumption
from core.engineering.engineering_runtime_adapter_activation_result import validate_runtime_adapter_activation_result
def verify_runtime_adapter_activation_boundary(admission, preparation, controlled_activation, token_consumption, activation_result):
 a=admission if isinstance(admission,Mapping) else {}; p=preparation if isinstance(preparation,Mapping) else {}; c=controlled_activation if isinstance(controlled_activation,Mapping) else {}; t=token_consumption if isinstance(token_consumption,Mapping) else {}; r=activation_result if isinstance(activation_result,Mapping) else {}
 identity=all(validate(x).valid for validate,x in [(validate_runtime_adapter_activation_admission,a),(validate_runtime_adapter_activation_preparation,p),(validate_runtime_adapter_controlled_activation,c),(validate_runtime_adapter_activation_token_consumption,t),(validate_runtime_adapter_activation_result,r)])
 linkage=len({x.get('token_id') for x in [a,p,c,t,r]})==1 and len({x.get('adapter_id') for x in [a,p,c,t,r]})==1 and len({x.get('execution_session_id') for x in [a,p,c,t,r]})==1
 usage=t.get('max_uses')==1 and t.get('previous_uses')==0 and t.get('current_uses')==1
 state=t.get('token_state_before')=='issued_unconsumed' and t.get('token_state_after')=='consumed'
 gov=c.get('governance_transition_committed') is True and r.get('governance_transition_committed') is True
 non=all(passive_false(x) for x in [c,t,r])
 ok=identity and a.get('admission_status')=='admitted' and p.get('preparation_status')=='prepared' and c.get('activation_status')=='activated' and t.get('consumption_status')=='consumed' and r.get('result_status')=='activated' and linkage and usage and state and gov and non
 return _build('verified' if ok else 'not_verified', ['verified'] if ok else ['activation_boundary_not_verified'], activation_result_id=r.get('activation_result_id'), activation_result_fingerprint=r.get('fingerprint'), controlled_activation_id=c.get('controlled_activation_id'), controlled_activation_fingerprint=c.get('fingerprint'), token_consumption_id=t.get('token_consumption_id'), token_consumption_fingerprint=t.get('fingerprint'), activation_preparation_id=p.get('activation_preparation_id'), activation_admission_id=a.get('activation_admission_id'), token_id=r.get('token_id'), adapter_id=r.get('adapter_id'), adapter_version=r.get('adapter_version'), execution_session_id=r.get('execution_session_id'), invocation_descriptor_id=r.get('invocation_descriptor_id'), verified_scope=r.get('activated_scope'), identity_valid=identity, linkage_valid=linkage, scope_valid=scope_bounded(r.get('activated_scope'),a.get('activation_scope')), usage_transition_valid=usage, token_state_transition_valid=state, governance_transition_valid=gov, authority_valid=True, non_execution_invariants_valid=non)
