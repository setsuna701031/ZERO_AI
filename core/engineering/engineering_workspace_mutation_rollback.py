from __future__ import annotations
from .engineering_workspace_mutation_executor_common import *
from .engineering_workspace_mutation_transaction_store import store_paths,transition_state,append_journal,write_json_atomic

def rollback_transaction(binding,handoff,store,commit):
    if commit.get('status')=='committed': return finish('wsmut-rb','rollback','rollback_id',{'status':'not_required','transaction_id':store.get('transaction_id'),'rolled_back_operation_ids':[],'reason_codes':[]})
    rs=[]; rb=[]; p=store_paths(binding,store['transaction_id']); transition_state(binding,store['transaction_id'],'rolling_back')
    committed=set(commit.get('committed_operation_ids',[])); ops=[o for o in ops_from_handoff(handoff) if o.get('operation_id') in committed]
    for o in reversed(ops):
        typ=op_type(o); tp,_=resolve_inside(binding.root_path,target_rel(o)); append_journal(binding,store['transaction_id'],{'phase':'before_rollback','operation_id':o.get('operation_id')})
        try:
            idx=ops_from_handoff(handoff).index(o); bp=p['backup']/f'backup-{idx}.bin'
            if typ=='create_text_file':
                if tp.exists() and tp.is_file(): tp.unlink()
            elif typ=='create_directory':
                tp.rmdir()
            elif typ in ('replace_text_file','delete_file'):
                with bp.open('rb') as f: data=f.read()
                with tp.open('wb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
            elif typ=='rename_path':
                sp,_=resolve_inside(binding.root_path,source_rel(o))
                if sp.exists() or not tp.exists(): rs.append('rollback_failed'); break
                tp.rename(sp)
            rb.append(o.get('operation_id')); append_journal(binding,store['transaction_id'],{'phase':'after_rollback','operation_id':o.get('operation_id')})
        except Exception: rs.append('rollback_failed'); break
    status='rolled_back' if not rs else ('partially_rolled_back' if rb else 'failed')
    if status=='rolled_back': transition_state(binding,store['transaction_id'],'rolled_back'); write_json_atomic(p['rollback_marker'],{'transaction_id':store['transaction_id'],'status':'rolled_back'})
    else: transition_state(binding,store['transaction_id'],'failed')
    return finish('wsmut-rb','rollback','rollback_id',{'status':status,'transaction_id':store.get('transaction_id'),'rolled_back_operation_ids':rb,'reason_codes':reasons(rs)})
