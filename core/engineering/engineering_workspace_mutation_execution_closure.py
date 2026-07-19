from __future__ import annotations
from .engineering_workspace_mutation_executor_common import *
def close_execution(result,evidence,store):
    if result.get('status') in ('succeeded','failed_rolled_back','duplicate_suppressed') and evidence.get('status')=='recorded': st='closed'
    elif result.get('status')=='failed_recovery_required': st='recovery_required'
    else: st='not_closed'
    return finish('wsmut-closure','execution_closure','closure_id',{'status':st,'result_id':result.get('result_id'),'result_fingerprint':result.get('fingerprint'),'evidence_id':evidence.get('evidence_id'),'evidence_fingerprint':evidence.get('fingerprint'),'transaction_id':store.get('transaction_id'),'reason_codes':[] if st in ('closed','recovery_required') else ['closure_incomplete']})
