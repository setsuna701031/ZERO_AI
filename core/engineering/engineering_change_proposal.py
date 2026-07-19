from __future__ import annotations
from typing import Any
from core.engineering.engineering_change_proposal_common import *

def assemble_change_proposal(payload:dict[str,Any])->dict[str,Any]:
 rs=require_mapping(payload)
 ops=payload.get('operations',[]); contents=payload.get('contents',[]); policy=payload.get('scope_policy',{})
 rs+=bounded_int(len(ops),'operation_count',0) if len(ops)>policy.get('maximum_affected_files',10**9) else []
 if sum(c.get('content_byte_count',0) for c in contents)>policy.get('maximum_total_proposed_content_bytes',10**9): rs.append('total_content_too_large')
 rs+=validate_operation_conflicts(ops)
 body={'intent':payload.get('intent'),'workspace_evidence':payload.get('workspace_evidence'),'target_admissions':payload.get('target_admissions',[]),'scope_policy':policy,'preconditions':payload.get('preconditions',[]),'operations':ops,'contents':contents,'diffs':payload.get('diffs',[]),'workspace_id':payload.get('workspace_id') or payload.get('workspace_evidence',{}).get('workspace_id'),'workspace_execution_closure_id':payload.get('workspace_evidence',{}).get('workspace_execution_closure_id'),'execution_session_id':payload.get('workspace_evidence',{}).get('upstream_execution_session_id'),'authority_constraints':payload.get('authority_constraints',[]),'validation_requirements':payload.get('validation_requirements',[]),'mutation_authorized':False,'mutation_performed':False,'patch_applied':False,'filesystem_write_performed':False,'git_invoked':False,'shell_invoked':False,'runtime_kernel_invoked':False,'status':'proposed' if not rs else 'not_proposed','reason_codes':reasons(rs)}
 return artifact('cprp',SCHEMAS['proposal'],body,'proposal_id')
