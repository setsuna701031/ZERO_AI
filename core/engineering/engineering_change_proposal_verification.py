from __future__ import annotations
from typing import Any
from core.engineering.engineering_change_proposal_common import *

def verify_change_proposal(proposal:dict[str,Any], validation:dict[str,Any], safety_review:dict[str,Any])->dict[str,Any]:
 rs=validate_false_invariants(proposal)
 if validation.get('proposal_id')!=proposal.get('proposal_id') or validation.get('proposal_fingerprint')!=proposal.get('fingerprint'): rs.append('validation_linkage_mismatch')
 if safety_review.get('proposal_id')!=proposal.get('proposal_id') or safety_review.get('proposal_fingerprint')!=proposal.get('fingerprint'): rs.append('safety_review_linkage_mismatch')
 if validation.get('workspace_id')!=proposal.get('workspace_id') or safety_review.get('workspace_id')!=proposal.get('workspace_id'): rs.append('workspace_identity_drift')
 if validation.get('status')!='valid': rs.append('validation_not_valid')
 if safety_review.get('status')!='approved_for_handoff': rs.append('safety_review_not_approved_for_handoff')
 body={'proposal_id':proposal.get('proposal_id'),'proposal_fingerprint':proposal.get('fingerprint'),'validation_id':validation.get('validation_id'),'validation_fingerprint':validation.get('fingerprint'),'safety_review_id':safety_review.get('safety_review_id'),'safety_review_fingerprint':safety_review.get('fingerprint'),'workspace_id':proposal.get('workspace_id'),'status':'verified' if not rs else 'not_verified','verification_codes':['identity_reconstructed','linkage_verified','mutation_false_invariants_verified'],'reason_codes':reasons(rs)}
 return artifact('cver',SCHEMAS['verification'],body,'verification_id')
