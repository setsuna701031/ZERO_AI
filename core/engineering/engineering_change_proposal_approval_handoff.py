from __future__ import annotations
from typing import Any
from core.engineering.engineering_change_proposal_common import *

def build_approval_handoff(proposal:dict[str,Any], verification:dict[str,Any], safety_review:dict[str,Any])->dict[str,Any]:
 rs=[]
 if verification.get('status')!='verified': rs.append('verification_not_verified')
 if safety_review.get('status')!='approved_for_handoff': rs.append('safety_review_not_approved_for_handoff')
 body={'proposal_id':proposal.get('proposal_id'),'proposal_fingerprint':proposal.get('fingerprint'),'verification_id':verification.get('verification_id'),'verification_fingerprint':verification.get('fingerprint'),'safety_review_id':safety_review.get('safety_review_id'),'safety_review_fingerprint':safety_review.get('fingerprint'),'workspace_id':proposal.get('workspace_id'),'workspace_root_fingerprint':proposal.get('workspace_evidence',{}).get('workspace_root_fingerprint'),'operation_count':len(proposal.get('operations',[])),'target_path_fingerprints':[sha256_text(o.get('target_relative_path','')) for o in proposal.get('operations',[])],'proposed_content_fingerprints':[c.get('content_sha256') for c in proposal.get('contents',[])],'diff_fingerprints':[d.get('fingerprint') for d in proposal.get('diffs',[])],'precondition_fingerprints':[x.get('fingerprint') for x in proposal.get('preconditions',[])],'authority_constraints':proposal.get('authority_constraints',[]),'scope_policy_id':proposal.get('scope_policy',{}).get('scope_policy_id'),'operator_approval_obtained':False,'mutation_authorized':False,'mutation_prepared':False,'mutation_performed':False,'patch_applied':False,'filesystem_write_performed':False,'git_invoked':False,'runtime_kernel_invoked':False,'status':'handed_off' if not rs else 'not_handed_off','reason_codes':reasons(rs)}
 return artifact('chap',SCHEMAS['approval_handoff'],body,'approval_handoff_id')
