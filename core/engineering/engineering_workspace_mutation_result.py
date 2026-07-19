from __future__ import annotations
from .engineering_workspace_mutation_executor_common import *
def build_result(handoff,store,commit,post,rollback,recovery,token_state):
    if store.get('status')=='duplicate_suppressed': st='duplicate_suppressed'
    elif commit.get('status')=='committed' and post.get('status')=='verified': st='succeeded'
    elif recovery.get('status')=='verified' and rollback.get('status')=='rolled_back': st='failed_rolled_back'
    elif recovery.get('manual_recovery_required'): st='failed_recovery_required'
    elif commit.get('status') in ('invalid','failed') and not commit.get('committed_operation_ids'): st='rejected'
    else: st='invalid'
    return finish('wsmut-result','result','result_id',{'status':st,'handoff_id':handoff.get('handoff_id'),'handoff_fingerprint':handoff.get('fingerprint'),'transaction_id':store.get('transaction_id'),'commit_status':commit.get('status'),'post_commit_status':post.get('status'),'rollback_status':rollback.get('status'),'recovery_status':recovery.get('status'),'manual_recovery_required':st=='failed_recovery_required','authorization_token_state':token_state.get('authorization','not_consumed'),'preparation_token_state':token_state.get('preparation','not_consumed'),'mutation_performed':commit.get('status')=='committed','filesystem_write_performed':commit.get('status') in ('committed','partially_committed'),'git_invoked':False,'shell_invoked':False,'network_invoked':False,'model_invoked':False,'runtime_kernel_invoked':False,'reason_codes':[]})
