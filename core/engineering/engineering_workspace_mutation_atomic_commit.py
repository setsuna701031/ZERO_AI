from __future__ import annotations
from .engineering_workspace_mutation_executor_common import *
from .engineering_workspace_mutation_transaction_store import store_paths,transition_state,append_journal,write_json_atomic

def atomic_commit(binding,handoff,store,gate):
    rs=[]; committed=[]; p=store_paths(binding,store['transaction_id'])
    if gate.get('status')!='authorized': rs.append('commit_not_authorized'); return finish('wsmut-commit','atomic_commit','atomic_commit_id',{'status':'invalid','transaction_id':store.get('transaction_id'),'committed_operation_ids':[],'reason_codes':rs})
    transition_state(binding,store['transaction_id'],'committing')
    for i,o in enumerate(ops_from_handoff(handoff)):
        typ=op_type(o); tr=target_rel(o); tp,rr=resolve_inside(binding.root_path,tr); sr=[]
        append_journal(binding,store['transaction_id'],{'phase':'before_commit','operation_id':o.get('operation_id'),'operation_type':typ})
        try:
            if rr: raise ValueError('path')
            if typ=='create_text_file':
                if tp.exists(): rs.append('target_exists'); break
                (p['staging']/f'staged-{i}.txt').replace(tp)
            elif typ=='replace_text_file':
                if not tp.is_file() or tp.is_symlink(): rs.append('target_kind_invalid'); break
                if expected_before(o) and file_fp(tp)[0]!=expected_before(o): rs.append('precondition_mismatch'); break
                (p['staging']/f'staged-{i}.txt').replace(tp)
            elif typ=='delete_file':
                if not tp.is_file() or tp.is_symlink(): rs.append('target_kind_invalid'); break
                if expected_before(o) and file_fp(tp)[0]!=expected_before(o): rs.append('precondition_mismatch'); break
                tp.unlink()
            elif typ=='create_directory':
                if tp.exists(): rs.append('target_exists'); break
                tp.mkdir(exist_ok=False)
            elif typ=='rename_path':
                sp,sr=resolve_inside(binding.root_path,source_rel(o))
                if sr or not sp.exists() or sp.is_symlink() or tp.exists(): rs.append('precondition_mismatch'); break
                sp.rename(tp)
            else: rs.append('unsupported_operation'); break
            committed.append(o.get('operation_id')); append_journal(binding,store['transaction_id'],{'phase':'after_commit','operation_id':o.get('operation_id'),'operation_type':typ})
        except Exception:
            if not rs: rs.append('atomic_commit_failed')
            break
    status='committed' if not rs and len(committed)==len(ops_from_handoff(handoff)) else ('partially_committed' if committed else 'failed')
    if status=='committed': transition_state(binding,store['transaction_id'],'committed'); write_json_atomic(p['commit_marker'],{'transaction_id':store['transaction_id'],'status':'committed'})
    return finish('wsmut-commit','atomic_commit','atomic_commit_id',{'status':status,'transaction_id':store.get('transaction_id'),'committed_operation_ids':committed,'reason_codes':reasons(rs)})
