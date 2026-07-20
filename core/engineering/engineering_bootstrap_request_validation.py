from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_planning_common import ValidationResult, authority_errors, fp_ok, id_ok, no_overlap, path_ok, result, short_text
from core.engineering.engineering_mutation_transaction_common import fingerprint
from core.engineering.engineering_repair_candidate import CHANGE_KINDS
from core.engineering.engineering_repair_plan import EXPECTATION_TYPES
from core.engineering.engineering_bootstrap_request import SCHEMA, STATUSES, AUTHORITY_BOUNDARY

def validate_engineering_bootstrap_request(value:Any)->ValidationResult:
    e=[]
    if not isinstance(value,Mapping): return ValidationResult(False,('artifact_not_mapping',))
    req={'schema','bootstrap_request_id','fingerprint','repository_identity','repository_root_reference','requested_outcome','request_summary','target_scope','prohibited_scope','allowed_change_kinds','verification_expectations','constraints','assumptions','analysis_policy','planning_policy','bootstrap_status','status','deterministic','immutable','authority_boundary'}
    e += [f'missing:{k}' for k in sorted(req-set(value))]
    if value.get('schema')!=SCHEMA: e.append('schema_mismatch')
    if not id_ok(value.get('bootstrap_request_id'),'engineering-bootstrap-request'): e.append('bootstrap_request_id_malformed')
    if not fp_ok(value.get('fingerprint')) or value.get('fingerprint')!=fingerprint({k:v for k,v in value.items() if k!='fingerprint'}): e.append('fingerprint_mismatch')
    if value.get('bootstrap_status') not in STATUSES or value.get('status')!=value.get('bootstrap_status'): e.append('status_invalid')
    if not value.get('repository_identity'): e.append('repository_identity_missing')
    if not isinstance(value.get('repository_root_reference'),Mapping): e.append('repository_root_reference_invalid')
    for k,limit in [('requested_outcome',512),('request_summary',640)]:
        try: short_text(value.get(k),limit)
        except Exception: e.append(k+'_invalid')
    for k in ('target_scope','prohibited_scope','allowed_change_kinds','verification_expectations','constraints','assumptions'):
        if not isinstance(value.get(k),list): e.append(k+'_invalid')
    targets=value.get('target_scope') if isinstance(value.get('target_scope'),list) else []
    prohibited=value.get('prohibited_scope') if isinstance(value.get('prohibited_scope'),list) else []
    if not targets or len(targets)!=len(set(targets)) or targets!=sorted(targets) or any(not path_ok(x) for x in targets): e.append('target_scope_invalid')
    if len(prohibited)!=len(set(prohibited)) or prohibited!=sorted(prohibited) or any(not path_ok(x) for x in prohibited): e.append('prohibited_scope_invalid')
    if '.git' not in prohibited: e.append('mandatory_prohibited_scope_missing')
    if targets and prohibited and not no_overlap(targets,prohibited): e.append('target_prohibited_overlap')
    if any(x not in CHANGE_KINDS for x in value.get('allowed_change_kinds') or []): e.append('unsupported_change_kind')
    if len(value.get('verification_expectations') or [])!=len(set(value.get('verification_expectations') or [])): e.append('duplicate_verification_expectation')
    if any(x not in EXPECTATION_TYPES for x in value.get('verification_expectations') or []): e.append('unsupported_verification_expectation')
    if value.get('deterministic') is not True or value.get('immutable') is not True: e.append('determinism_immutability_invalid')
    if value.get('authority_boundary')!=AUTHORITY_BOUNDARY: e.append('authority_boundary_invalid')
    e += authority_errors(value)
    return result(e)
