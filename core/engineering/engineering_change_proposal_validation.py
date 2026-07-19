from __future__ import annotations
from typing import Any
from core.engineering.engineering_change_proposal_common import *

def validate_change_proposal(proposal:dict[str,Any])->dict[str,Any]:
 rs=require_mapping(proposal)+validate_false_invariants(proposal)
 if proposal.get('schema')!=SCHEMAS['proposal']: rs.append('proposal_schema_invalid')
 if proposal.get('status')!='proposed': rs.append('proposal_not_proposed')
 for a in proposal.get('target_admissions',[]):
  if a.get('status')!='admitted': rs.append('target_not_admitted')
 for c in proposal.get('contents',[]):
  if c.get('status')!='accepted': rs.append('content_not_accepted')
 for d in proposal.get('diffs',[]):
  if d.get('status')!='accepted': rs.append('diff_not_accepted')
 rs+=validate_operation_conflicts(proposal.get('operations',[]))
 body={'proposal_id':proposal.get('proposal_id'),'proposal_fingerprint':proposal.get('fingerprint'),'workspace_id':proposal.get('workspace_id'),'status':'valid' if not rs else 'invalid','validation_codes':['schema_checked','linkage_checked','non_mutation_checked'],'reason_codes':reasons(rs)}
 return artifact('cval',SCHEMAS['validation'],body,'validation_id')
