from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_mutation_transaction_common import fingerprint
from core.engineering.engineering_planning_common import ValidationResult, authority_errors, fp_ok, id_ok, no_overlap, path_ok, result, subset
from core.engineering.engineering_repair_plan import SCHEMA, PLAN_STATUSES, OPERATION_TYPES, EXPECTATION_TYPES, AUTHORITY_BOUNDARY

def validate_engineering_repair_plan(value: Any, *, candidate: Mapping[str,Any]|None=None, task_id: str|None=None, repository_identity: str|None=None, analysis_identity: str|None=None, request_scope: Any=None) -> ValidationResult:
    e=[]
    if not isinstance(value, Mapping): return ValidationResult(False,('artifact_not_mapping',))
    if value.get('schema')!=SCHEMA: e.append('schema_mismatch')
    if not id_ok(value.get('repair_plan_id'),'engineering-repair-plan'): e.append('repair_plan_id_malformed')
    if not fp_ok(value.get('fingerprint')): e.append('fingerprint_malformed')
    if value.get('fingerprint') and value.get('fingerprint')!=fingerprint({k:v for k,v in value.items() if k!='fingerprint'}): e.append('fingerprint_mismatch')
    if task_id and value.get('task_id')!=task_id: e.append('task_id_mismatch')
    if repository_identity and value.get('repository_identity')!=repository_identity: e.append('repository_identity_mismatch')
    if analysis_identity and value.get('analysis_identity')!=analysis_identity: e.append('analysis_identity_mismatch')
    if value.get('plan_status') not in PLAN_STATUSES or value.get('status')!=value.get('plan_status'): e.append('status_invalid')
    allowed=value.get('allowed_target_paths'); prohibited=value.get('prohibited_target_paths')
    if not isinstance(allowed,list) or not allowed or any(not path_ok(x) for x in allowed): e.append('allowed_targets_invalid')
    if not isinstance(prohibited,list) or any(not path_ok(x) for x in prohibited): e.append('prohibited_targets_invalid')
    if isinstance(allowed,list) and isinstance(prohibited,list) and not no_overlap(allowed,prohibited): e.append('allowed_prohibited_overlap')
    if request_scope is not None and (not isinstance(allowed,list) or not subset(allowed, request_scope)): e.append('target_outside_request_scope')
    if candidate:
        if candidate.get('selection_status')!='selected': e.append('candidate_not_selected')
        if value.get('candidate_identity')!=candidate.get('candidate_id'): e.append('candidate_identity_mismatch')
        if value.get('candidate_fingerprint')!=candidate.get('fingerprint'): e.append('candidate_fingerprint_mismatch')
        if value.get('analysis_identity')!=candidate.get('analysis_identity'): e.append('analysis_identity_mismatch')
        if value.get('repository_identity')!=candidate.get('repository_identity'): e.append('repository_identity_mismatch')
        if isinstance(allowed,list) and not subset(allowed, candidate.get('target_scope',[])): e.append('target_outside_candidate_scope')
        if not set(candidate.get('prohibited_scope',[])).issubset(set(prohibited or [])): e.append('mandatory_prohibited_scope_removed')
    ops=value.get('ordered_operations')
    if not isinstance(ops,list) or not ops: e.append('empty_operations')
    else:
        seqs=[]; ids=[]; ver_ids=set()
        for ex in value.get('verification_expectations') or []: ver_ids.add(ex.get('expectation_id') if isinstance(ex,Mapping) else None)
        for i,o in enumerate(ops,start=1):
            if not isinstance(o,Mapping): e.append('operation_malformed'); continue
            ids.append(o.get('operation_id')); seqs.append(o.get('sequence'))
            if o.get('sequence')!=i: e.append('operation_order_invalid')
            if not id_ok(o.get('operation_id'),'engineering-repair-operation'): e.append('operation_id_malformed')
            if o.get('operation_type') not in OPERATION_TYPES: e.append('operation_type_invalid')
            if not path_ok(o.get('target_path')): e.append('operation_path_unsafe')
            if isinstance(allowed,list) and not any(o.get('target_path')==a for a in allowed): e.append('operation_not_declared_allowed_target')
            if isinstance(prohibited,list) and any(o.get('target_path')==p or str(o.get('target_path','')).startswith(p.rstrip('/')+'/') for p in prohibited): e.append('operation_inside_prohibited_scope')
            if not o.get('verification_expectation_ids') or not set(o.get('verification_expectation_ids',[])).issubset(ver_ids): e.append('missing_required_verification')
            if not isinstance(o.get('rationale'),str) or len(o.get('rationale',''))>512: e.append('rationale_unbounded')
        if len(ids)!=len(set(ids)): e.append('duplicate_operation_id')
        if len(seqs)!=len(set(seqs)): e.append('duplicate_sequence')
        if value.get('operation_count')!=len(ops): e.append('operation_count_mismatch')
        if value.get('ordered_operation_ids')!=ids: e.append('ordered_operation_ids_mismatch')
    vex=value.get('verification_expectations')
    if not isinstance(vex,list) or not vex: e.append('empty_verification_expectations')
    else:
        ids=[]
        for x in vex:
            if not isinstance(x,Mapping): e.append('verification_expectation_malformed'); continue
            ids.append(x.get('expectation_id'))
            if x.get('expectation_type') not in EXPECTATION_TYPES: e.append('verification_expectation_type_invalid')
            if x.get('required') is not True: e.append('verification_expectation_not_required')
        if len(ids)!=len(set(ids)): e.append('duplicate_verification_expectation')
        if ids != sorted(ids): e.append('verification_expectation_order_invalid')
    if value.get('authority_boundary')!=AUTHORITY_BOUNDARY: e.append('authority_boundary_invalid')
    if value.get('deterministic') is not True or value.get('immutable') is not True: e.append('determinism_immutability_invalid')
    e += authority_errors(value)
    return result(e)
