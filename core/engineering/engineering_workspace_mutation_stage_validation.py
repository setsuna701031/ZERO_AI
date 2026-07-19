from __future__ import annotations
from .engineering_workspace_mutation_executor_common import *
def validate_stage(handoff,store,backup,staging,token):
    rs=[]; ops=ops_from_handoff(handoff)
    if staging.get('status')!='staged': rs.append('staging_failed')
    if len(staging.get('staged_records',[]))!=len(ops): rs.append('stage_operation_count_mismatch')
    if token.get('status')!='pending': rs.append('token_invalid')
    for o,r in zip(ops,staging.get('staged_records',[])):
        if o.get('operation_id')!=r.get('operation_id'): rs.append('operation_order_mismatch')
        if op_type(o) in ('create_text_file','replace_text_file') and expected_after(o) and expected_after(o)!=r.get('staged_content_fingerprint'): rs.append('content_fingerprint_mismatch')
    return finish('wsmut-stageval','stage_validation','stage_validation_id',{'status':'valid' if not rs else 'rejected','transaction_id':store.get('transaction_id'),'reason_codes':reasons(rs)})
