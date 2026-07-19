from __future__ import annotations
from typing import Any
from core.engineering.engineering_mutation_preparation_common import *
def build_operator_approval_decision(payload:dict[str,Any],policy:dict[str,Any],request:dict[str,Any],eligibility:dict[str,Any],proposal:dict[str,Any])->dict[str,Any]:
 decision=payload.get('decision'); approved=seq(payload.get('approved_operation_ids')); requested=seq(request.get('requested_operation_ids')); rs=[]
 if eligibility.get('status')!='eligible': rs.append('eligibility_not_eligible')
 if decision not in ('approved','partially_approved','rejected'): rs.append('decision_invalid')
 rs+=validate_operator_identity(payload.get('operator_id'),payload.get('operator_identity_class'),policy)
 if payload.get('automated_decision') is not False: rs.append('automated_decision_true')
 if policy.get('operator_reason_required') and not payload.get('decision_reason_code'): rs.append('decision_reason_required')
 if decision=='approved' and set(approved)!=set(requested): rs.append('approved_requires_all_requested')
 if decision=='partially_approved' and not policy.get('partial_approval_allowed'): rs.append('partial_approval_not_allowed')
 if decision=='rejected' and approved: rs.append('rejected_approves_operations')
 if not subset(approved,requested) or not subset(approved,ids(proposal_ops(proposal),'operation_id')): rs.append('approved_operation_expansion')
 ops=selected_ops(proposal,approved); sums=[op_summary(proposal,o) for o in ops]
 if set(seq(payload.get('approved_target_path_fingerprints')))-set(x['target_path_fingerprint'] for x in sums): rs.append('target_substitution')
 if set(seq(payload.get('approved_content_fingerprints')))-set(x['content_fingerprint'] for x in sums if x.get('content_fingerprint')): rs.append('content_substitution')
 if set(seq(payload.get('approved_diff_fingerprints')))-set(x['diff_fingerprint'] for x in sums if x.get('diff_fingerprint')): rs.append('diff_substitution')
 if not scope_ok(seq(payload.get('approved_scope')),request.get('requested_scope',[])): rs.append('scope_expansion')
 if not authority_ok(seq(payload.get('approved_authority_constraints')),request.get('requested_authority_constraints',[])): rs.append('authority_expansion')
 body={**payload,'reviewed_proposal_id':proposal.get('proposal_id'),'reviewed_proposal_fingerprint':proposal.get('fingerprint'),'reviewed_operation_ids':requested,'approved_operation_ids':approved if decision!='rejected' else [],'human_operator_decision':not rs,'automated_decision':False,'mutation_authorized':False,'mutation_performed':False,'status':decision if not rs else 'invalid','reason_codes':reasons(rs)}
 return artifact('oad',SCHEMAS['operator_approval_decision'],body,'decision_id')
