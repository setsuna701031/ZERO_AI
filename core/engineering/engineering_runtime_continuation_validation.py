from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_planning_common import ValidationResult, result
from core.engineering.engineering_runtime_continuation import SCHEMA, DECISIONS, _fp_body
from core.engineering.engineering_verification_plan import AUTHORITY_BOUNDARY
def validate_runtime_continuation(v:Any)->ValidationResult:
 e=[]
 if not isinstance(v,Mapping): return ValidationResult(False,('artifact_not_mapping',))
 if v.get('schema')!=SCHEMA: e.append('schema_mismatch')
 if not str(v.get('runtime_continuation_id','')).startswith('engineering-runtime-continuation-'): e.append('identity_mismatch')
 if v.get('fingerprint')!=_fp_body(v): e.append('fingerprint_mismatch')
 if v.get('decision') not in DECISIONS or v.get('status')!=v.get('decision'): e.append('decision_invalid')
 if v.get('retry_eligible') is not False: e.append('retry_must_be_false')
 if v.get('authority_boundary')!=AUTHORITY_BOUNDARY: e.append('authority_boundary_invalid')
 return result(e)
