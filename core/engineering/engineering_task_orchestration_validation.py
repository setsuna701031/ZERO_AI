from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Mapping
from core.engineering.engineering_mutation_transaction_common import canonical_json, fingerprint

STATE_SCHEMA='zero.engineering.task_orchestration.v1'
REQUEST_SCHEMA='zero.engineering.task_request.v1'
VERIFICATION_SCHEMA='zero.engineering.task_verification.v1'
TERMINAL={'closed','failed','invalid','blocked'}
PHASES=['requested','admitted','analysis_ready','candidate_selected','plan_ready','awaiting_human_approval','approved','authorized','prepared','execution_ready','executed','verified','closed']

@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: tuple[str,...]=()

def stable_ref(a:Mapping[str,Any], *keys:str)->dict[str,Any]:
    if not isinstance(a, Mapping): return {}
    id_key=next((k for k in keys if a.get(k)), None) or next((k for k in a if k.endswith('_id') or k in ('token_id','closure_id','handoff_id','verification_id')), None)
    return {'schema':a.get('schema'), 'id':a.get(id_key) if id_key else None, 'fingerprint':a.get('fingerprint')}

def require_artifact(a:Any, schema:str|None=None, statuses:set[str]|None=None, status_key:str='status')->ValidationResult:
    e=[]
    if not isinstance(a, Mapping): return ValidationResult(False, ('artifact_not_mapping',))
    if schema and a.get('schema')!=schema: e.append('schema_mismatch')
    if statuses is not None and a.get(status_key) not in statuses: e.append('status_mismatch')
    if not a.get('fingerprint'): e.append('fingerprint_missing')
    return ValidationResult(not e, tuple(e))

def canonical_request(request:Mapping[str,Any])->dict[str,Any]:
    r=dict(request)
    r.setdefault('schema', REQUEST_SCHEMA)
    prohibited={'approval_granted','authorization_granted','token_issued','mutation_authorized','execution_authority'}
    body={k:v for k,v in r.items() if k not in {'request_id','fingerprint'} and k not in prohibited}
    if 'repository_identity' not in body: raise ValueError('repository_identity_required')
    if 'requested_outcome' not in body: raise ValueError('requested_outcome_required')
    body.setdefault('bounded_target_scope', [])
    body.setdefault('prohibited_scope', [])
    body.setdefault('requested_verification_expectations', [])
    body['execution_authority']=False
    body['approval_granted']=False
    body['authorization_granted']=False
    fp=fingerprint(body)
    body['request_id']='engineering-task-request-'+fp[:24]
    body['fingerprint']=fp
    return body

def task_identity(request:Mapping[str,Any])->tuple[str,str]:
    body={'schema':STATE_SCHEMA,'contract_version':'v2.0','repository_identity':request['repository_identity'],'request_identity':stable_ref(request,'request_id'),'bounded_target_scope':request.get('bounded_target_scope',[])}
    fp=fingerprint(body)
    return 'engineering-task-'+fp[:24], fp

def state_fingerprint(state:Mapping[str,Any])->str:
    return fingerprint({k:v for k,v in state.items() if k!='state_fingerprint'})

def validate_state(state:Any)->ValidationResult:
    e=[]
    if not isinstance(state, Mapping): return ValidationResult(False, ('state_not_mapping',))
    if state.get('schema')!=STATE_SCHEMA: e.append('invalid_schema')
    if state.get('task_fingerprint')!=state.get('state_fingerprint'): pass
    if state.get('state_fingerprint')!=state_fingerprint(state): e.append('state_fingerprint_mismatch')
    if state.get('lifecycle_state') not in {'requested','admitted','analysis_ready','candidate_selected','plan_ready','awaiting_human_approval','approved','authorized','prepared','execution_ready','executing','executed','verification_pending','verified','completed','closing','closed','blocked','failed','invalid'}: e.append('invalid_lifecycle_state')
    return ValidationResult(not e, tuple(e))

def same_ref(existing:dict[str,Any]|None, artifact:Mapping[str,Any], *id_keys:str)->bool:
    return existing == stable_ref(artifact,*id_keys)
