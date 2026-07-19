from __future__ import annotations
from typing import Any
from core.engineering.engineering_change_proposal_common import *

def close_change_proposal(proposal:dict[str,Any], validation:dict[str,Any], safety_review:dict[str,Any], verification:dict[str,Any], handoff:dict[str,Any])->dict[str,Any]:
 rs=validate_false_invariants(proposal)+validate_false_invariants(handoff)
 if proposal.get('status')!='proposed': rs.append('proposal_not_proposed')
 if validation.get('status')!='valid': rs.append('validation_not_valid')
 if safety_review.get('status')!='approved_for_handoff': rs.append('safety_review_not_approved_for_handoff')
 if verification.get('status')!='verified': rs.append('verification_not_verified')
 if handoff.get('status')!='handed_off': rs.append('handoff_not_handed_off')
 ids={proposal.get('proposal_id'),validation.get('proposal_id'),safety_review.get('proposal_id'),verification.get('proposal_id'),handoff.get('proposal_id')}
 if len(ids)!=1: rs.append('proposal_linkage_mismatch')
 body={'proposal_id':proposal.get('proposal_id'),'proposal_fingerprint':proposal.get('fingerprint'),'validation_id':validation.get('validation_id'),'verification_id':verification.get('verification_id'),'safety_review_id':safety_review.get('safety_review_id'),'approval_handoff_id':handoff.get('approval_handoff_id'),'workspace_id':proposal.get('workspace_id'),'operator_approval_obtained':False,'mutation_authorized':False,'mutation_prepared':False,'mutation_performed':False,'patch_applied':False,'filesystem_write_performed':False,'git_invoked':False,'runtime_kernel_invoked':False,'status':'closed' if not rs else 'not_closed','reason_codes':reasons(rs)}
 return artifact('ccls',SCHEMAS['closure'],body,'closure_id')
