from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_planning_common import ValidationResult, result, subset
from core.engineering.engineering_verification_admission import SCHEMA, RUNNER_IDENTITY, _fp_body
from core.engineering.engineering_verification_plan import ALLOWED_TYPES, AUTHORITY_BOUNDARY
STATUSES={'admitted','blocked','invalid','consumed'}
def validate_verification_admission(v:Any, plan:Mapping[str,Any]|None=None)->ValidationResult:
 e=[]
 if not isinstance(v,Mapping): return ValidationResult(False,('artifact_not_mapping',))
 if v.get('schema')!=SCHEMA: e.append('schema_mismatch')
 if not str(v.get('verification_admission_id','')).startswith('engineering-verification-admission-'): e.append('identity_mismatch')
 if v.get('fingerprint')!=_fp_body(v): e.append('fingerprint_mismatch')
 if v.get('admission_status') not in STATUSES or v.get('status')!=v.get('admission_status'): e.append('status_invalid')
 if v.get('runner_identity')!=RUNNER_IDENTITY: e.append('runner_identity_invalid')
 if v.get('single_use') is not True: e.append('single_use_required')
 if v.get('authority_boundary')!=AUTHORITY_BOUNDARY: e.append('authority_boundary_invalid')
 if any(x not in ALLOWED_TYPES for x in v.get('allowed_verification_types') or []): e.append('unsupported_verification_type')
 if plan:
  if v.get('verification_plan_identity')!=plan.get('verification_plan_id') or v.get('verification_plan_fingerprint')!=plan.get('fingerprint'): e.append('plan_linkage_mismatch')
  if not subset(v.get('allowed_target_paths') or [], plan.get('allowed_target_paths') or []): e.append('scope_expanded')
  for k in ('maximum_duration_seconds','maximum_output_bytes','maximum_evidence_items','execution_session_id','execution_result_identity'):
   if v.get(k)!=plan.get(k): e.append(k+'_mismatch')
 return result(e)
