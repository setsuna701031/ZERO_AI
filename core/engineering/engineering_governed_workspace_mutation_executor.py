from __future__ import annotations
from .engineering_workspace_mutation_root_binding import bind_workspace_root
from .engineering_workspace_mutation_executor_admission import admit_workspace_mutation_executor
from .engineering_workspace_mutation_live_precondition import inspect_live_preconditions
from .engineering_workspace_mutation_transaction_store import create_transaction_store,transition_state,store_paths
from .engineering_workspace_mutation_token_consumption import prepare_token_consumption,finalize_token_consumption
from .engineering_workspace_mutation_backup_capture import capture_backups
from .engineering_workspace_mutation_staging import stage_mutations
from .engineering_workspace_mutation_stage_validation import validate_stage
from .engineering_workspace_mutation_commit_gate import authorize_commit
from .engineering_workspace_mutation_atomic_commit import atomic_commit
from .engineering_workspace_mutation_post_commit_verification import verify_post_commit
from .engineering_workspace_mutation_rollback import rollback_transaction
from .engineering_workspace_mutation_recovery_verification import verify_recovery
from .engineering_workspace_mutation_result import build_result
from .engineering_workspace_mutation_execution_evidence import build_execution_evidence
from .engineering_workspace_mutation_execution_closure import close_execution
from .engineering_workspace_mutation_failure import normalize_failure
from .engineering_workspace_mutation_executor_common import *

def validate_only(handoff,workspace_root):
    binding=bind_workspace_root(workspace_root,handoff); admission=admit_workspace_mutation_executor(binding,handoff)
    pre=inspect_live_preconditions(binding,handoff,admission) if admission.get('status')=='admitted' else finish('wsmut-pre','live_precondition','precondition_id',{'status':'invalid','reason_codes':['executor_not_admitted']})
    txid=admission.get('transaction_id')
    store=finish('wsmut-store','transaction_store','store_id',{'status':'planned','transaction_id':txid,'relative_transaction_directory':f'{TX_PARENT}/{txid}','state':'planned','reason_codes':[]})
    return {'root_binding':binding.artifact,'executor_admission':admission,'live_precondition':pre,'transaction_store':store}

def execute_pipeline(handoff,workspace_root,execute_confirmed=False):
    if execute_confirmed is not True:
        v=validate_only(handoff,workspace_root); v['error']={'code':'execute_confirmation_required'}; return v
    binding=bind_workspace_root(workspace_root,handoff); admission=admit_workspace_mutation_executor(binding,handoff)
    if admission.get('status')!='admitted':
        fail=normalize_failure('executor_not_admitted',admission); return {'root_binding':binding.artifact,'executor_admission':admission,'failure':fail}
    pre=inspect_live_preconditions(binding,handoff,admission)
    if pre.get('status')!='satisfied':
        fail=normalize_failure('precondition_mismatch',pre); return {'root_binding':binding.artifact,'executor_admission':admission,'live_precondition':pre,'failure':fail}
    store=create_transaction_store(binding,handoff,admission)
    if store.get('status')=='duplicate_suppressed':
        dummy={'status':'duplicate_suppressed'}; token={'authorization':'consumed','preparation':'consumed'}; result=build_result(handoff,store,dummy,dummy,dummy,dummy,token); evidence=build_execution_evidence(handoff,admission,pre,store,dummy,dummy,dummy,dummy,dummy,dummy,dummy,dummy,result); closure=close_execution(result,evidence,store); return {'root_binding':binding.artifact,'executor_admission':admission,'live_precondition':pre,'transaction_store':store,'result':result,'execution_evidence':evidence,'execution_closure':closure}
    token=prepare_token_consumption(binding,handoff,admission,store); transition_state(binding,store['transaction_id'],'preconditions_verified')
    backup=capture_backups(binding,handoff,store); staging=stage_mutations(binding,handoff,store); stageval=validate_stage(handoff,store,backup,staging,token); gate=authorize_commit(binding,handoff,admission,pre,store,backup,staging,stageval,token)
    commit=atomic_commit(binding,handoff,store,gate); post={'status':'not_verified','reason_codes':[]}; rollback={'status':'not_required','reason_codes':[]}; recovery={'status':'verified','manual_recovery_required':False,'reason_codes':[]}
    if commit.get('status')=='committed': post=verify_post_commit(binding,handoff,store,commit)
    if commit.get('status')!='committed' or post.get('status')!='verified':
        rollback=rollback_transaction(binding,handoff,store,commit); recovery=verify_recovery(binding,handoff,store,rollback)
    tokens=finalize_token_consumption(binding,store['transaction_id'],success=(post.get('status')=='verified' or recovery.get('status')=='verified'))
    result=build_result(handoff,store,commit,post,rollback,recovery,tokens); evidence=build_execution_evidence(handoff,admission,pre,store,backup,staging,stageval,gate,commit,post,rollback,recovery,result); closure=close_execution(result,evidence,store)
    return {'root_binding':binding.artifact,'executor_admission':admission,'live_precondition':pre,'transaction_store':store,'token_consumption':token,'backup_capture':backup,'staging':staging,'stage_validation':stageval,'commit_gate':gate,'atomic_commit':commit,'post_commit_verification':post,'rollback':rollback,'recovery_verification':recovery,'result':result,'execution_evidence':evidence,'execution_closure':closure}
