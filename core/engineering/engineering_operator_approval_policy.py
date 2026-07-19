from __future__ import annotations
from typing import Any
from core.engineering.engineering_mutation_preparation_common import *
def build_operator_approval_policy(payload:dict[str,Any])->dict[str,Any]:
 rs=[]
 if payload.get('status','active')!='active': rs.append('policy_not_active')
 for n in ('maximum_approved_operations','maximum_approved_files','maximum_approved_content_bytes','maximum_approved_diff_entries'):
  rs+=bounded_int(payload.get(n,0),n,1)
 if payload.get('automated_approval_allowed') is not False: rs.append('automated_approval_not_allowed')
 if payload.get('self_approval_allowed') is not False: rs.append('self_approval_not_allowed')
 if payload.get('delegation_allowed') is not False: rs.append('delegation_not_allowed')
 if payload.get('multi_party_approval_required') is not False: rs.append('multi_party_not_v1')
 if not seq(payload.get('allowed_operator_identity_classes')): rs.append('operator_identity_classes_required')
 body={**payload,'allowed_operator_identity_classes':seq(payload.get('allowed_operator_identity_classes')),'allowed_proposal_categories':seq(payload.get('allowed_proposal_categories')),'allowed_operation_classes':seq(payload.get('allowed_operation_classes')) or list(OP_TYPES),'allowed_path_prefixes':seq(payload.get('allowed_path_prefixes')),'allowed_authority_constraints':seq(payload.get('allowed_authority_constraints')),'approval_mode':payload.get('approval_mode','explicit_human'),'partial_approval_allowed':bool(payload.get('partial_approval_allowed',False)),'expiration_mode':payload.get('expiration_mode','none'),'operator_reason_required':bool(payload.get('operator_reason_required',True)),'multi_party_approval_required':False,'delegation_allowed':False,'self_approval_allowed':False,'automated_approval_allowed':False,'status':'active' if not rs else 'invalid','reason_codes':reasons(rs)}
 return artifact('oap',SCHEMAS['operator_approval_policy'],body,'policy_id')
