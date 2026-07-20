from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_mutation_transaction_common import fingerprint
from core.engineering.engineering_planning_common import ValidationResult, authority_errors, fp_ok, id_ok, result
from core.engineering.engineering_repair_continuation_eligibility import SCHEMA, MAXIMUM_CYCLES, AUTHORITY_BOUNDARY
STATUSES=('eligible','blocked','cycle_limit_reached','manual_intervention_required')
def validate_repair_continuation_eligibility(value:Any, *, failure_analysis:Mapping[str,Any]|None=None)->ValidationResult:
 e=[]
 if not isinstance(value,Mapping): return ValidationResult(False,('artifact_not_mapping',))
 if value.get('schema')!=SCHEMA: e.append('schema_mismatch')
 if not id_ok(value.get('repair_continuation_eligibility_id'),'engineering-repair-continuation-eligibility'): e.append('eligibility_id_malformed')
 if not fp_ok(value.get('fingerprint')) or value.get('fingerprint')!=fingerprint({k:v for k,v in value.items() if k!='fingerprint'}): e.append('fingerprint_mismatch')
 if value.get('eligibility_status') not in STATUSES: e.append('status_invalid')
 if value.get('cycle_number') not in (1,2,3,4) or value.get('maximum_cycles')!=MAXIMUM_CYCLES: e.append('cycle_bound_invalid')
 if value.get('cycle_number',0)>MAXIMUM_CYCLES and value.get('eligible') is not False: e.append('cycle_limit_not_enforced')
 if value.get('human_approval_required') is not True: e.append('human_approval_not_required')
 if value.get('authority_boundary')!=AUTHORITY_BOUNDARY: e.append('authority_boundary_invalid')
 if value.get('deterministic') is not True or value.get('immutable') is not True: e.append('determinism_immutability_invalid')
 if failure_analysis and (value.get('failure_analysis_identity')!=failure_analysis.get('failure_analysis_id') or value.get('failure_analysis_fingerprint')!=failure_analysis.get('fingerprint')): e.append('failure_analysis_linkage_mismatch')
 e+=authority_errors(value); return result(e)
