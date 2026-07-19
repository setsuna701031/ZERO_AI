from __future__ import annotations
from typing import Any
from core.engineering.engineering_mutation_preparation_common import *
def seal_operator_approved_scope(decision:dict[str,Any],request:dict[str,Any],proposal:dict[str,Any])->dict[str,Any]:
 rs=[]
 if decision.get('status')=='invalid': rs.append('decision_invalid')
 approved=[] if decision.get('status')=='rejected' else seq(decision.get('approved_operation_ids'))
 ops=selected_ops(proposal,approved); sums=[op_summary(proposal,o) for o in ops]
 body={'proposal_id':proposal.get('proposal_id'),'proposal_fingerprint':proposal.get('fingerprint'),'request_id':request.get('request_id'),'decision_id':decision.get('decision_id'),'decision_fingerprint':decision.get('fingerprint'),'approved_operations':sums,'approved_operation_ids':approved,'approved_operation_fingerprints':[x['operation_fingerprint'] for x in sums],'approved_relative_path_fingerprints':[x['target_path_fingerprint'] for x in sums],'approved_content_fingerprints':[x['content_fingerprint'] for x in sums if x.get('content_fingerprint')],'approved_diff_fingerprints':[x['diff_fingerprint'] for x in sums if x.get('diff_fingerprint')],'approved_precondition_fingerprints':[x['precondition_fingerprint'] for x in sums if x.get('precondition_fingerprint')],'approved_operation_classes':[x['operation_type'] for x in sums],'approved_scope_prefixes':seq(decision.get('approved_scope')),'approved_authority_constraints':seq(decision.get('approved_authority_constraints')),'approved_file_count':len(sums),'approved_content_byte_total':sum(o.get('content_byte_count',0) for o in ops),'approved_diff_entry_total':sum(o.get('diff_entry_count',0) for o in ops),'mutation_authorized':False,'mutation_performed':False,'status':'invalid' if rs else ('empty' if not approved else 'sealed'),'reason_codes':reasons(rs)}
 return artifact('oas',SCHEMAS['operator_approved_scope'],body,'approved_scope_id')
