from __future__ import annotations
from copy import deepcopy
from typing import Any, Mapping
from core.engineering.engineering_mutation_transaction_common import fingerprint

SCHEMA='zero.engineering.verification_plan.v1'
ALLOWED_TYPES=('pytest_files','python_compile_files','static_pattern_inspection','file_exists','file_not_exists','json_parse','canonical_artifact_validation')
FORBIDDEN_TYPES={'shell','command','powershell','cmd','bash','git','network','http','download','install','pip','python_eval','python_exec','arbitrary_subprocess','full_repository_pytest'}
AUTHORITY_BOUNDARY={'approval':'not_granted','authorization':'not_granted','token':'not_granted','mutation':'not_granted','shell':'not_granted','command':'not_granted','git':'not_granted','network':'not_granted'}

def _fp_body(a): return fingerprint({k:v for k,v in a.items() if k!='fingerprint'})
def _id(a,*names):
    for n in names:
        if isinstance(a,Mapping) and a.get(n): return a.get(n)
    return a.get('artifact_identity') if isinstance(a,Mapping) else None
def _afp(a): return a.get('fingerprint') or a.get('artifact_fingerprint') if isinstance(a,Mapping) else None
def _repair_targets(r): return sorted(dict.fromkeys(list(r.get('allowed_target_paths') or [])+[o.get('target_path') for o in r.get('ordered_operations') or [] if isinstance(o,Mapping) and o.get('target_path')]))
def _execution_targets(e): return sorted(dict.fromkeys([o.get('target_path') for o in e.get('operations') or e.get('operation_results') or [] if isinstance(o,Mapping) and o.get('target_path')] or list(e.get('affected_target_paths') or e.get('target_paths') or [])))
def _expectations(r):
    xs=r.get('verification_expectations') or []
    if xs: return [dict(x) for x in xs if isinstance(x,Mapping)]
    return [{'expectation_id':str(x),'expectation_type':'static_pattern_inspection','required':True,'target_paths':_repair_targets(r)} for x in r.get('verification_expectation_ids') or []]
def build_verification_plan(*, session:Mapping[str,Any], proposal:Mapping[str,Any], repair_plan:Mapping[str,Any], execution_result:Mapping[str,Any], expectation_ids:list[str]|None=None, optional_expectation_ids:list[str]|None=None, timeout_overrides:Mapping[str,int]|None=None, maximum_duration_seconds:int=30, maximum_output_bytes:int=4096, maximum_evidence_items:int=32)->dict[str,Any]:
    exps=_expectations(repair_plan); wanted=set(expectation_ids or [x.get('expectation_id') for x in exps]); optional=set(optional_expectation_ids or [])
    allowed=sorted(set(_repair_targets(repair_plan))|set(_execution_targets(execution_result)))
    steps=[]
    for x in exps:
        eid=str(x.get('expectation_id'))
        if eid not in wanted and eid not in optional: continue
        vt=str(x.get('verification_type') or x.get('expectation_type') or 'static_pattern_inspection')
        targets=sorted(dict.fromkeys(x.get('target_paths') or x.get('targets') or allowed))
        steps.append({'step_id':'verification-step-'+fingerprint({'eid':eid,'vt':vt,'targets':targets})[:16],'expectation_id':eid,'verification_type':vt,'target_reference':targets,'arguments':dict(x.get('arguments') or {}),'expected_outcome':x.get('expected_outcome','passed'),'mandatory':bool(x.get('required',True) and eid not in optional),'timeout_seconds':int((timeout_overrides or {}).get(eid, min(10, maximum_duration_seconds)))})
    body={'schema':SCHEMA,'task_id':session.get('task_id') or repair_plan.get('task_id'),'repository_identity':session.get('repository_identity') or repair_plan.get('repository_identity'),'execution_session_id':session.get('execution_session_id'),'proposal_identity':_id(proposal,'proposal_id'),'proposal_fingerprint':_afp(proposal),'repair_plan_identity':repair_plan.get('repair_plan_id'),'repair_plan_fingerprint':_afp(repair_plan),'execution_result_identity':_id(execution_result,'result_id','execution_id'),'execution_result_fingerprint':_afp(execution_result),'verification_expectations':exps,'verification_steps':steps,'allowed_target_paths':allowed,'prohibited_target_paths':sorted(repair_plan.get('prohibited_target_paths') or []),'maximum_duration_seconds':int(maximum_duration_seconds),'maximum_output_bytes':int(maximum_output_bytes),'maximum_evidence_items':int(maximum_evidence_items),'fail_fast':True,'required_success_policy':'all_mandatory_steps_passed','deterministic':True,'immutable':True,'authority_boundary':dict(AUTHORITY_BOUNDARY)}
    body['verification_plan_id']='engineering-verification-plan-'+fingerprint(body)[:24]; body['fingerprint']=_fp_body(body); return body
