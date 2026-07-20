from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_mutation_transaction_common import fingerprint
from core.engineering.engineering_planning_common import ValidationResult, authority_errors, fp_ok, id_ok, result
from core.engineering.engineering_repair_continuation_cycle import SCHEMA, STATUSES, AUTHORITY_BOUNDARY
def validate_repair_continuation_cycle(value:Any, *, failure_analysis:Mapping[str,Any]|None=None, eligibility:Mapping[str,Any]|None=None)->ValidationResult:
 e=[]
 if not isinstance(value,Mapping): return ValidationResult(False,('artifact_not_mapping',))
 if value.get('schema')!=SCHEMA: e.append('schema_mismatch')
 if not id_ok(value.get('repair_continuation_cycle_id'),'engineering-repair-continuation-cycle'): e.append('cycle_id_malformed')
 if not fp_ok(value.get('fingerprint')) or value.get('fingerprint')!=fingerprint({k:v for k,v in value.items() if k!='fingerprint'}): e.append('fingerprint_mismatch')
 if value.get('cycle_status') not in STATUSES: e.append('status_invalid')
 if value.get('awaiting_human_approval') is not (value.get('cycle_status')=='awaiting_human_approval'): e.append('awaiting_flag_mismatch')
 if value.get('authority_boundary')!=AUTHORITY_BOUNDARY: e.append('authority_boundary_invalid')
 if failure_analysis and value.get('failure_analysis_fingerprint')!=failure_analysis.get('fingerprint'): e.append('failure_analysis_linkage_mismatch')
 if eligibility and value.get('eligibility_fingerprint')!=eligibility.get('fingerprint'): e.append('eligibility_linkage_mismatch')
 e+=authority_errors(value); return result(e)
