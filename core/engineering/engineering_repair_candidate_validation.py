from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_mutation_transaction_common import fingerprint
from core.engineering.engineering_planning_common import ValidationResult, authority_errors, fp_ok, id_ok, no_overlap, path_ok, result, subset
from core.engineering.engineering_repair_candidate import SCHEMA, STATUSES, DEFECT_CLASSES, RISKS, CHANGE_KINDS, AUTHORITY_BOUNDARY

def validate_engineering_repair_candidate(value: Any, *, task_id: str|None=None, repository_identity: str|None=None, analysis_identity: str|None=None, analysis_fingerprint: str|None=None, request_scope: Any=None) -> ValidationResult:
    e=[]
    if not isinstance(value, Mapping): return ValidationResult(False,('artifact_not_mapping',))
    req={'schema','candidate_id','fingerprint','task_id','repository_identity','analysis_identity','analysis_fingerprint','requested_outcome','defect_classification','defect_summary','evidence_references','target_scope','prohibited_scope','affected_components','estimated_change_kind','risk_level','confidence','selection_status','status','deterministic','immutable','authority_boundary'}
    e += [f'missing:{k}' for k in sorted(req-set(value))]
    if value.get('schema')!=SCHEMA: e.append('schema_mismatch')
    if not id_ok(value.get('candidate_id'),'engineering-repair-candidate'): e.append('candidate_id_malformed')
    if not fp_ok(value.get('fingerprint')): e.append('fingerprint_malformed')
    if value.get('fingerprint') and value.get('fingerprint')!=fingerprint({k:v for k,v in value.items() if k!='fingerprint'}): e.append('fingerprint_mismatch')
    if task_id and value.get('task_id')!=task_id: e.append('task_id_mismatch')
    if repository_identity and value.get('repository_identity')!=repository_identity: e.append('repository_identity_mismatch')
    if analysis_identity and value.get('analysis_identity')!=analysis_identity: e.append('analysis_identity_mismatch')
    if analysis_fingerprint and value.get('analysis_fingerprint')!=analysis_fingerprint: e.append('analysis_fingerprint_mismatch')
    ev=value.get('evidence_references')
    if not isinstance(ev,list) or not ev: e.append('empty_evidence')
    else:
        ids=[]
        for item in ev:
            if not isinstance(item, Mapping): e.append('evidence_malformed'); continue
            ids.append(item.get('evidence_id'))
            if 'repository_relative_path' in item and not path_ok(item.get('repository_relative_path')): e.append('evidence_path_unsafe')
            if not isinstance(item.get('bounded_summary'),str) or len(item.get('bounded_summary',''))>640: e.append('summary_unbounded')
        if len(ids)!=len(set(ids)): e.append('duplicate_evidence_identity')
        if ids != sorted(ids): e.append('nondeterministic_evidence_order')
    targets=value.get('target_scope'); prohibited=value.get('prohibited_scope')
    if not isinstance(targets,list) or not targets or any(not path_ok(x) for x in targets): e.append('target_scope_invalid')
    if not isinstance(prohibited,list) or any(not path_ok(x) for x in prohibited): e.append('prohibited_scope_invalid')
    if isinstance(targets,list) and isinstance(prohibited,list) and not no_overlap(targets, prohibited): e.append('target_prohibited_overlap')
    if request_scope is not None and (not isinstance(targets,list) or not subset(targets, request_scope)): e.append('target_scope_outside_request')
    if value.get('defect_classification') not in DEFECT_CLASSES: e.append('unsupported_defect_classification')
    if value.get('estimated_change_kind') not in CHANGE_KINDS: e.append('estimated_change_kind_invalid')
    if value.get('risk_level') not in RISKS: e.append('risk_level_invalid')
    if value.get('selection_status') not in STATUSES or value.get('status')!=value.get('selection_status'): e.append('status_invalid')
    if not (isinstance(value.get('confidence'), (int,float)) and 0 <= float(value.get('confidence')) <= 1): e.append('confidence_invalid')
    if value.get('deterministic') is not True or value.get('immutable') is not True: e.append('determinism_immutability_invalid')
    if value.get('authority_boundary') != AUTHORITY_BOUNDARY: e.append('authority_boundary_invalid')
    e += authority_errors(value)
    return result(e)
