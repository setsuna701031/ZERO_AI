from __future__ import annotations
from .engineering_workspace_mutation_executor_common import *
from .engineering_workspace_mutation_transaction_store import transition_state,store_paths

def verify_post_commit(binding,handoff,store,commit):
    rs=[]
    if commit.get('status')!='committed': rs.append('atomic_commit_failed')
    for o in ops_from_handoff(handoff):
        tp,rr=resolve_inside(binding.root_path,target_rel(o)); rs+=rr; typ=op_type(o)
        try:
            if typ in ('create_text_file','replace_text_file'):
                if not tp.is_file() or (expected_after(o) and file_fp(tp)[0]!=expected_after(o)): rs.append('content_fingerprint_mismatch')
            elif typ=='delete_file' and tp.exists(): rs.append('target_exists')
            elif typ=='create_directory' and not tp.is_dir(): rs.append('target_missing')
            elif typ=='rename_path':
                sp,_=resolve_inside(binding.root_path,source_rel(o))
                if sp.exists() or not tp.exists(): rs.append('precondition_mismatch')
        except Exception: rs.append('post_commit_verification_failed')
    if not (store_paths(binding,store['transaction_id'])['commit_marker']).exists(): rs.append('post_commit_verification_failed')
    if not rs: transition_state(binding,store['transaction_id'],'post_commit_verified')
    return finish('wsmut-post','post_commit_verification','post_commit_verification_id',{'status':'verified' if not rs else 'not_verified','transaction_id':store.get('transaction_id'),'reason_codes':reasons(rs)})
