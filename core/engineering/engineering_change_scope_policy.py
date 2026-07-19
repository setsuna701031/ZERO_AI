from __future__ import annotations
from typing import Any
from core.engineering.engineering_change_proposal_common import *
def build_change_scope_policy(payload:dict[str,Any], parent:dict[str,Any]|None=None)->dict[str,Any]:
 rs=require_mapping(payload); allowed=payload.get('allowed_operation_classes',[])
 if not subset(allowed,OPERATION_TYPES): rs.append('unsupported_operation_class')
 for n in ('maximum_affected_files','maximum_created_files','maximum_replaced_files','maximum_delete_proposals','maximum_rename_proposals','maximum_directory_proposals','maximum_content_bytes_per_file','maximum_total_proposed_content_bytes','maximum_diff_entries','maximum_line_length','maximum_line_count'):
  rs+=bounded_int(payload.get(n),n,1)
 for n in ('allow_binary','allow_symlink_targets','allow_hidden_targets','require_existing_evidence_for_replace','require_existing_evidence_for_delete','require_missing_evidence_for_create','allow_scope_narrowing'):
  rs+=strict_bool(payload.get(n),n)
 if payload.get('allow_binary') is not False: rs.append('binary_not_allowed')
 if payload.get('allow_symlink_targets') is not False: rs.append('symlink_targets_not_allowed')
 if parent:
  if not subset(allowed,parent.get('allowed_operation_classes',[])): rs.append('scope_expansion')
  if not subset(payload.get('authority_constraints',[]),parent.get('authority_constraints',[])): rs.append('authority_expansion')
 body=dict(payload); body.update({'status':'accepted' if not rs else 'rejected','reason_codes':reasons(rs)})
 return artifact('cscp',SCHEMAS['scope_policy'],body,'scope_policy_id')
