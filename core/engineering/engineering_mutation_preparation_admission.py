from __future__ import annotations
from typing import Any
from core.engineering.engineering_mutation_preparation_common import *
def admit_mutation_preparation(policy,request,approval_verification,decision,approved_scope,proposal):
 rs=[]
 if approval_verification.get('status')!='verified': rs.append('approval_not_verified')
 if decision.get('status') not in ('approved','partially_approved'): rs.append('decision_not_approved')
 if approved_scope.get('status')!='sealed' or not approved_scope.get('approved_operation_ids'): rs.append('approved_scope_empty')
 if request.get('requested_operation_ids')!=approved_scope.get('approved_operation_ids'): rs.append('request_scope_mismatch')
 classes=approved_scope.get('approved_operation_classes',[])
 if not subset(classes,policy.get('allowed_prepared_operation_classes',[])): rs.append('operation_class_not_allowed')
 if len(classes)>policy.get('maximum_prepared_operations',0): rs.append('operation_bound_exceeded')
 rs+=validate_false_invariants(request,approval_verification,decision,approved_scope)
 body={'preparation_policy_id':policy.get('preparation_policy_id'),'preparation_request_id':request.get('preparation_request_id'),'approval_verification_id':approval_verification.get('approval_verification_id'),'approved_scope_id':approved_scope.get('approved_scope_id'),'proposal_id':proposal.get('proposal_id'),'workspace_id':proposal.get('workspace_id'),'admitted_operation_ids':approved_scope.get('approved_operation_ids',[]) if not rs else [],'status':'admitted' if not rs else 'not_admitted','reason_codes':reasons(rs),'mutation_authorized':False,'mutation_performed':False}
 return artifact('mpa',SCHEMAS['mutation_preparation_admission'],body,'preparation_admission_id')
