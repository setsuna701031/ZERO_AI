from __future__ import annotations
from typing import Any
from core.engineering.engineering_mutation_preparation_common import *
def build_mutation_preparation_request(policy,approval_verification,approved_scope,proposal,payload=None):
 payload=payload or {}; rs=[]
 if approval_verification.get('status')!='verified': rs.append('approval_not_verified')
 if approved_scope.get('status')!='sealed': rs.append('approved_scope_empty_or_invalid')
 body={'approval_verification_id':approval_verification.get('approval_verification_id'),'approval_verification_fingerprint':approval_verification.get('fingerprint'),'approved_scope_id':approved_scope.get('approved_scope_id'),'approved_scope_fingerprint':approved_scope.get('fingerprint'),'proposal_id':proposal.get('proposal_id'),'proposal_fingerprint':proposal.get('fingerprint'),'preparation_policy_id':policy.get('preparation_policy_id'),'preparation_policy_fingerprint':policy.get('fingerprint'),'workspace_id':proposal.get('workspace_id'),'workspace_root_fingerprint':payload.get('workspace_root_fingerprint'),'requested_operation_ids':approved_scope.get('approved_operation_ids',[]),'requested_preparation_sequence':payload.get('requested_preparation_sequence',0),'preparation_requested':True,'mutation_authorized':False,'mutation_performed':False,'status':'requested' if not rs else 'invalid','reason_codes':reasons(rs)}
 return artifact('mpr',SCHEMAS['mutation_preparation_request'],body,'preparation_request_id')
