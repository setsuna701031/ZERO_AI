from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_planning_common import ValidationResult, result
from core.engineering.engineering_verification_run import SCHEMA, _fp_body
from core.engineering.engineering_verification_plan import AUTHORITY_BOUNDARY
STATUSES={'passed','failed','blocked','timed_out','invalid','runner_error'}; RUN_STATUSES={'passed','failed','blocked','invalid','runner_error'}
def validate_verification_run(v:Any)->ValidationResult:
 e=[]
 if not isinstance(v,Mapping): return ValidationResult(False,('artifact_not_mapping',))
 if v.get('schema')!=SCHEMA: e.append('schema_mismatch')
 if not str(v.get('verification_run_id','')).startswith('engineering-verification-run-'): e.append('identity_mismatch')
 if v.get('fingerprint')!=_fp_body(v): e.append('fingerprint_mismatch')
 if v.get('run_status') not in RUN_STATUSES or v.get('status')!=v.get('run_status'): e.append('status_invalid')
 if v.get('authority_boundary')!=AUTHORITY_BOUNDARY: e.append('authority_boundary_invalid')
 for s in v.get('step_results') or []:
  if not isinstance(s,Mapping) or s.get('status') not in STATUSES or not s.get('evidence_reference'): e.append('step_result_invalid')
 if len(v.get('evidence_references') or [])>128: e.append('evidence_references_invalid')
 return result(e)
