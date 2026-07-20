from __future__ import annotations
from .engineering_workspace_mutation_executor_common import *
from .engineering_workspace_mutation_transaction_store import transition_state

def _scope_values(scope, *names):
    for name in names:
        value=scope.get(name) if isinstance(scope,dict) else None
        if value is not None: return list(value) if isinstance(value,(list,tuple)) else []
    return []

def _scope_still_matches_authorized_operations(handoff,admission):
    scope=handoff.get('authorized_scope')
    if not isinstance(scope,dict): return []
    ops=ops_from_handoff(handoff); op_ids=[o.get('operation_id') for o in ops]; targets=[target_rel(o) for o in ops]; types=[op_type(o) for o in ops]
    rs=[]
    if _scope_values(scope,'authorized_operation_ids','operation_ids','allowed_operation_ids')!=op_ids: rs.append('authorized_operation_scope_mismatch')
    if _scope_values(scope,'authorized_target_paths','target_paths','allowed_target_paths')!=targets: rs.append('authorized_target_scope_mismatch')
    if _scope_values(scope,'authorized_operation_types','operation_types','allowed_operation_types') not in ([],types): rs.append('authorized_operation_type_scope_mismatch')
    if scope.get('operation_count',admission.get('operation_count'))!=admission.get('operation_count'): rs.append('authorized_operation_count_mismatch')
    return rs

def authorize_commit(binding,handoff,admission,precondition,store,backup,staging,stage_validation,token):
    rs=[]
    for cond,code in [(admission.get('status')=='admitted','executor_not_admitted'),(precondition.get('status')=='satisfied','precondition_mismatch'),(store.get('status')=='created','transaction_state_invalid'),(backup.get('status')=='captured','backup_failed'),(staging.get('status')=='staged','staging_failed'),(stage_validation.get('status')=='valid','stage_validation_failed'),(token.get('status')=='pending','token_invalid')]:
        if not cond: rs.append(code)
    rs+=_scope_still_matches_authorized_operations(handoff,admission)
    if not rs: transition_state(binding,store['transaction_id'],'commit_admitted')
    return finish('wsmut-gate','commit_gate','commit_gate_id',{'status':'authorized' if not rs else 'not_authorized','transaction_execution_authorized':not rs,'transaction_id':store.get('transaction_id'),'admission_id':admission.get('admission_id'),'reason_codes':reasons(rs)})
