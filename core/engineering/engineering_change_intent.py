from __future__ import annotations
from typing import Any
from core.engineering.engineering_change_proposal_common import *
def build_change_intent(payload:dict[str,Any])->dict[str,Any]:
 rs=require_mapping(payload); cat=payload.get('intent_category');
 if cat not in INTENT_CATEGORIES: rs.append('unsupported_intent_category')
 for n in ('maximum_affected_files','maximum_proposed_content_bytes','maximum_diff_entries'):
  rs+=bounded_int(payload.get(n),n,1)
 rs+=contains_prohibited_payload(payload)
 body={'intent_category':cat,'summary_code':payload.get('summary_code',''), 'requested_target_paths':sorted(payload.get('requested_target_paths',[])), 'requested_operation_classes':sorted(payload.get('requested_operation_classes',[])), 'expected_goal_identifiers':sorted(payload.get('expected_goal_identifiers',[])), 'expected_validation_identifiers':sorted(payload.get('expected_validation_identifiers',[])), 'maximum_affected_files':payload.get('maximum_affected_files'), 'maximum_proposed_content_bytes':payload.get('maximum_proposed_content_bytes'), 'maximum_diff_entries':payload.get('maximum_diff_entries'), 'authority_constraints':payload.get('authority_constraints',[]), 'scope_constraints':payload.get('scope_constraints',[]), 'status':'accepted' if not rs else 'rejected','reason_codes':reasons(rs)}
 return artifact('cint',SCHEMAS['intent'],body,'intent_id')
