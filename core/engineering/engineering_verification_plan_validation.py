from __future__ import annotations
from pathlib import PurePosixPath
from typing import Any, Mapping
from core.engineering.engineering_planning_common import ValidationResult, result, subset, no_overlap
from core.engineering.engineering_verification_plan import SCHEMA, ALLOWED_TYPES, FORBIDDEN_TYPES, AUTHORITY_BOUNDARY, _fp_body
BAD=(';','&&','||','`','$(', '|','>','<','\n','\r','http://','https://','pip install','--rootdir','--confcutdir','--pyargs','--override-ini','python -c','-c','python -m','shell','command')
def _path_ok(v):
    if not isinstance(v,str) or not v or '\\' in v or '\x00' in v or len(v)>240: return False
    p=PurePosixPath(v); return not p.is_absolute() and '..' not in p.parts and ':' not in p.parts[0] and '*' not in v and not v.startswith('//')
def _contains_bad(v):
    if isinstance(v,Mapping):
        return any((str(k).lower() in {'command','argv','shell','executable','env','cwd'} and str(k).lower()!='authority_boundary') or (str(k).lower() not in {'authority_boundary','step_id','verification_type','expectation_id','schema','verification_plan_id'} and _contains_bad(x)) for k,x in v.items())
    if isinstance(v,list): return any(_contains_bad(x) for x in v)
    if isinstance(v,str): return any(b in v for b in BAD)
    return False
def validate_verification_plan(v:Any)->ValidationResult:
    e=[]
    if not isinstance(v,Mapping): return ValidationResult(False,('artifact_not_mapping',))
    if v.get('schema')!=SCHEMA: e.append('schema_mismatch')
    if not str(v.get('verification_plan_id','')).startswith('engineering-verification-plan-'): e.append('identity_mismatch')
    if v.get('fingerprint')!=_fp_body(v): e.append('fingerprint_mismatch')
    if v.get('deterministic') is not True or v.get('immutable') is not True: e.append('determinism_immutability_invalid')
    if v.get('authority_boundary')!=AUTHORITY_BOUNDARY: e.append('authority_boundary_invalid')
    if not (1<=int(v.get('maximum_duration_seconds',0))<=300): e.append('duration_bound_invalid')
    if not (128<=int(v.get('maximum_output_bytes',0))<=65536): e.append('output_bound_invalid')
    if not (1<=int(v.get('maximum_evidence_items',0))<=128): e.append('evidence_bound_invalid')
    allowed=v.get('allowed_target_paths') or []; prohibited=v.get('prohibited_target_paths') or []
    if not isinstance(allowed,list) or any(not _path_ok(x) for x in allowed): e.append('allowed_target_path_invalid')
    if not isinstance(prohibited,list) or any(not _path_ok(x) for x in prohibited): e.append('prohibited_target_path_invalid')
    if isinstance(allowed,list) and isinstance(prohibited,list) and not no_overlap(allowed,prohibited): e.append('scope_overlap')
    ids=set(x.get('expectation_id') for x in v.get('verification_expectations') or [] if isinstance(x,Mapping)); seen=[]
    for s in v.get('verification_steps') or []:
        if not isinstance(s,Mapping): e.append('step_malformed'); continue
        seen.append(s.get('step_id')); vt=s.get('verification_type')
        if vt in FORBIDDEN_TYPES or vt not in ALLOWED_TYPES: e.append('verification_type_not_allowed')
        if s.get('expectation_id') not in ids: e.append('expectation_linkage_invalid')
        targets=s.get('target_reference') if isinstance(s.get('target_reference'),list) else [s.get('target_reference')]
        if any(not _path_ok(x) for x in targets): e.append('target_path_invalid')
        elif not subset(targets, allowed): e.append('target_outside_scope')
        if any(subset([x], prohibited) for x in targets): e.append('target_prohibited')
        if not (1<=int(s.get('timeout_seconds',0))<=int(v.get('maximum_duration_seconds',0) or 0)): e.append('timeout_invalid')
        if _contains_bad(s): e.append('executable_payload_rejected')
        if vt=='pytest_files' and (targets==['.'] or any(x in {'','tests'} or ':' in x for x in targets)): e.append('full_repository_pytest_rejected')
    if len(seen)!=len(set(seen)): e.append('duplicate_step_id')
    if _contains_bad(v): e.append('executable_payload_rejected')
    return result(e)
