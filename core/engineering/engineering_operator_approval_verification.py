from __future__ import annotations
from typing import Any
from core.engineering.engineering_mutation_preparation_common import *
def verify_operator_approval(policy,request,eligibility,decision,approved_scope,proposal):
 rs=[]
 if policy.get('status')!='active': rs.append('policy_not_active')
 if request.get('status')!='requested': rs.append('request_not_requested')
 if eligibility.get('status')!='eligible': rs.append('eligibility_not_eligible')
 if decision.get('status') not in ('approved','partially_approved','rejected'): rs.append('decision_not_valid')
 if approved_scope.get('status') not in ('sealed','empty'): rs.append('scope_not_sealed')
 if decision.get('human_operator_decision') is not True: rs.append('human_decision_missing')
 if decision.get('automated_decision') is not False: rs.append('automated_decision_not_false')
 if approved_scope.get('proposal_id')!=proposal.get('proposal_id'): rs.append('proposal_linkage_mismatch')
 if not subset(approved_scope.get('approved_operation_ids',[]),request.get('requested_operation_ids',[])): rs.append('approved_subset_mismatch')
 if not scope_ok(approved_scope.get('approved_scope_prefixes',[]),request.get('requested_scope',[])): rs.append('scope_expansion')
 if not authority_ok(approved_scope.get('approved_authority_constraints',[]),request.get('requested_authority_constraints',[])): rs.append('authority_expansion')
 rs+=validate_operator_identity(decision.get('operator_id'),decision.get('operator_identity_class'),policy)+validate_false_invariants(request,decision,approved_scope)
 body={'policy_id':policy.get('policy_id'),'request_id':request.get('request_id'),'eligibility_id':eligibility.get('eligibility_id'),'decision_id':decision.get('decision_id'),'decision_fingerprint':decision.get('fingerprint'),'approved_scope_id':approved_scope.get('approved_scope_id'),'approved_scope_fingerprint':approved_scope.get('fingerprint'),'proposal_id':proposal.get('proposal_id'),'proposal_fingerprint':proposal.get('fingerprint'),'operator_identity_class':decision.get('operator_identity_class'),'status':'verified' if not rs else 'not_verified','reason_codes':reasons(rs),'mutation_authorized':False,'mutation_performed':False}
 return artifact('oav',SCHEMAS['operator_approval_verification'],body,'approval_verification_id')
