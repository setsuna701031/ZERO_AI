from __future__ import annotations
from typing import Any
from core.engineering.engineering_mutation_preparation_common import *
def evaluate_operator_approval_eligibility(policy:dict[str,Any],request:dict[str,Any],proposal:dict[str,Any],validation:dict[str,Any],safety_review:dict[str,Any],verification:dict[str,Any],closure:dict[str,Any],handoff:dict[str,Any])->dict[str,Any]:
 rs=[]
 if policy.get('status')!='active': rs.append('policy_not_active')
 rs+=validate_handoff_chain(proposal,validation,safety_review,verification,closure,handoff)
 if request.get('proposal_id')!=proposal.get('proposal_id') or request.get('proposal_fingerprint')!=proposal.get('fingerprint'): rs.append('request_proposal_mismatch')
 req=request.get('requested_operation_ids',[]); ops=proposal_ops(proposal)
 if not subset(req,ids(ops,'operation_id')): rs.append('requested_operation_expansion')
 if len(req)!=len(set(req)): rs.append('duplicate_requested_operation')
 sels=[op_summary(proposal,o) for o in selected_ops(proposal,req)]
 if set(request.get('requested_target_path_fingerprints',[]))-set(x['target_path_fingerprint'] for x in sels): rs.append('requested_target_expansion')
 if not scope_ok(request.get('requested_scope',[]),proposal.get('scope_policy',{}).get('allowed_path_prefixes',[])): rs.append('request_scope_expansion')
 if not authority_ok(request.get('requested_authority_constraints',[]),proposal.get('authority_constraints',[])): rs.append('request_authority_expansion')
 if len(req)>policy.get('maximum_approved_operations',0): rs.append('operation_bound_exceeded')
 if request.get('human_decision_required') is not True: rs.append('human_decision_not_required')
 if request.get('automated_decision_allowed') is not False: rs.append('automated_decision_allowed')
 rs+=conflict_reasons(sels)+validate_false_invariants(request)
 body={'policy_id':policy.get('policy_id'),'policy_fingerprint':policy.get('fingerprint'),'request_id':request.get('request_id'),'request_fingerprint':request.get('fingerprint'),'proposal_id':proposal.get('proposal_id'),'proposal_fingerprint':proposal.get('fingerprint'),'eligible_operation_ids':req if not rs else [],'status':'eligible' if not rs else 'not_eligible','reason_codes':reasons(rs),'mutation_authorized':False,'mutation_performed':False}
 return artifact('oae',SCHEMAS['operator_approval_eligibility'],body,'eligibility_id')
