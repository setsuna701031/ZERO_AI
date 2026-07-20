from __future__ import annotations
from typing import Any
from core.engineering.engineering_mutation_transaction_common import fingerprint
from core.engineering.engineering_planning_common import ValidationResult, authority_errors, fp_ok, id_ok, result
from core.engineering.engineering_feedback_report import SCHEMA, AUTHORITY_BOUNDARY
def validate_feedback_report(value:Any)->ValidationResult:
 e=[]
 from typing import Mapping
 if not isinstance(value,Mapping): return ValidationResult(False,('artifact_not_mapping',))
 if value.get('schema')!=SCHEMA: e.append('schema_mismatch')
 if not id_ok(value.get('feedback_report_id'),'engineering-feedback-report'): e.append('report_id_malformed')
 if not fp_ok(value.get('fingerprint')) or value.get('fingerprint')!=fingerprint({k:v for k,v in value.items() if k!='fingerprint'}): e.append('fingerprint_mismatch')
 if value.get('authority_boundary')!=AUTHORITY_BOUNDARY: e.append('authority_boundary_invalid')
 for k in ('failure_analysis_reference','eligibility_reference','continuation_cycle_reference'):
  if not isinstance(value.get(k),dict) or not value[k].get('identity') or not value[k].get('fingerprint'): e.append(k+'_invalid')
 if value.get('deterministic') is not True or value.get('immutable') is not True: e.append('determinism_immutability_invalid')
 e+=authority_errors(value); return result(e)
