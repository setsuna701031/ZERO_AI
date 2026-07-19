from __future__ import annotations
from .engineering_workspace_mutation_executor_common import *
from .engineering_workspace_mutation_transaction_store import transition_state

def authorize_commit(binding,handoff,admission,precondition,store,backup,staging,stage_validation,token):
    rs=[]
    for cond,code in [(admission.get('status')=='admitted','executor_not_admitted'),(precondition.get('status')=='satisfied','precondition_mismatch'),(store.get('status')=='created','transaction_state_invalid'),(backup.get('status')=='captured','backup_failed'),(staging.get('status')=='staged','staging_failed'),(stage_validation.get('status')=='valid','stage_validation_failed'),(token.get('status')=='pending','token_invalid')]:
        if not cond: rs.append(code)
    if not rs: transition_state(binding,store['transaction_id'],'commit_admitted')
    return finish('wsmut-gate','commit_gate','commit_gate_id',{'status':'authorized' if not rs else 'not_authorized','transaction_execution_authorized':not rs,'transaction_id':store.get('transaction_id'),'admission_id':admission.get('admission_id'),'reason_codes':reasons(rs)})
