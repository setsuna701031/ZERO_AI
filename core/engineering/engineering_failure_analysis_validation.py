from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_mutation_transaction_common import fingerprint
from core.engineering.engineering_planning_common import ValidationResult, authority_errors, fp_ok, id_ok, path_ok, result, subset
from core.engineering.engineering_failure_analysis import SCHEMA, CLASSIFICATIONS, REPAIRABILITY, AUTHORITY_BOUNDARY

def validate_failure_analysis(value:Any, *, verification_result:Mapping[str,Any]|None=None, original_repair_plan:Mapping[str,Any]|None=None, execution_result:Mapping[str,Any]|None=None)->ValidationResult:
    e=[]
    if not isinstance(value,Mapping): return ValidationResult(False,('artifact_not_mapping',))
    req={'schema','failure_analysis_id','fingerprint','task_id','repository_identity','execution_session_id','verification_result_identity','verification_result_fingerprint','failure_classification','failed_expectation_ids','failed_step_ids','affected_operation_ids','affected_target_paths','evidence_references','root_cause_hypotheses','confidence_level','repairability','reason_codes','bounded_summary','deterministic','immutable','authority_boundary'}
    e += [f'missing:{k}' for k in sorted(req-set(value))]
    if value.get('schema')!=SCHEMA: e.append('schema_mismatch')
    if not id_ok(value.get('failure_analysis_id'),'engineering-failure-analysis'): e.append('failure_analysis_id_malformed')
    if not fp_ok(value.get('fingerprint')) or value.get('fingerprint')!=fingerprint({k:v for k,v in value.items() if k!='fingerprint'}): e.append('fingerprint_mismatch')
    if value.get('failure_classification') not in CLASSIFICATIONS: e.append('classification_invalid')
    if value.get('repairability') not in REPAIRABILITY: e.append('repairability_invalid')
    if not isinstance(value.get('confidence_level'),(int,float)) or not 0<=float(value.get('confidence_level'))<=1: e.append('confidence_invalid')
    if value.get('deterministic') is not True or value.get('immutable') is not True: e.append('determinism_immutability_invalid')
    if value.get('authority_boundary')!=AUTHORITY_BOUNDARY: e.append('authority_boundary_invalid')
    if verification_result:
        if verification_result.get('verification_status')=='passed': e.append('passed_verification_rejected')
        if value.get('verification_result_identity')!=verification_result.get('verification_result_id'): e.append('verification_result_linkage_mismatch')
        if value.get('verification_result_fingerprint')!=verification_result.get('fingerprint'): e.append('verification_result_fingerprint_mismatch')
        known=[x.get('expectation_id') for x in verification_result.get('verification_expectation_results',[]) if isinstance(x,Mapping)]
        if not set(value.get('failed_expectation_ids') or []).issubset(set(known)): e.append('unknown_expectation_id')
    if execution_result and value.get('execution_result_fingerprint')!=(execution_result.get('fingerprint') or execution_result.get('artifact_fingerprint')): e.append('execution_result_linkage_mismatch')
    if original_repair_plan:
        targets=original_repair_plan.get('allowed_target_paths') or []
        if value.get('affected_target_paths') and not subset(value.get('affected_target_paths'), targets): e.append('target_outside_original_plan_scope')
        known_ops=set(original_repair_plan.get('ordered_operation_ids') or [])
        if not set(value.get('affected_operation_ids') or []).issubset(known_ops): e.append('unknown_operation_id')
    for p in value.get('affected_target_paths') or []:
        if not path_ok(p): e.append('affected_target_path_unsafe')
    if not isinstance(value.get('evidence_references'),list) or len(value.get('evidence_references') or [])>32: e.append('evidence_references_unbounded')
    if not isinstance(value.get('root_cause_hypotheses'),list) or len(value.get('root_cause_hypotheses') or [])>8: e.append('hypotheses_unbounded')
    e += authority_errors(value)
    return result(e)
