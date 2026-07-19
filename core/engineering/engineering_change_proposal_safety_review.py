from __future__ import annotations
from typing import Any
from core.engineering.engineering_change_proposal_common import *

def review_change_proposal_safety(proposal:dict[str,Any], validation:dict[str,Any])->dict[str,Any]:
 rs=validate_false_invariants(proposal)
 if validation.get('status')!='valid': rs.append('validation_not_valid')
 
 body={'proposal_id':proposal.get('proposal_id'),'proposal_fingerprint':proposal.get('fingerprint'),'validation_id':validation.get('validation_id'),'validation_fingerprint':validation.get('fingerprint'),'workspace_id':proposal.get('workspace_id'),'status':'approved_for_handoff' if not rs else 'rejected','safety_review_codes':['passive_handoff_only','mutation_not_authorized','execution_not_invoked'],'reason_codes':reasons(rs)}
 return artifact('csaf',SCHEMAS['safety_review'],body,'safety_review_id')
