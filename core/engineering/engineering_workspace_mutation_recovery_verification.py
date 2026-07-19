from __future__ import annotations
from .engineering_workspace_mutation_executor_common import *
from .engineering_workspace_mutation_transaction_store import transition_state

def verify_recovery(binding,handoff,store,rollback):
    rs=[]
    if rollback.get('status') not in ('rolled_back','not_required'): rs.append('recovery_verification_failed')
    if rollback.get('status')=='rolled_back': transition_state(binding,store['transaction_id'],'recovery_verified')
    return finish('wsmut-rec','recovery_verification','recovery_verification_id',{'status':'verified' if not rs else 'not_verified','transaction_id':store.get('transaction_id'),'manual_recovery_required':bool(rs),'reason_codes':reasons(rs)})
