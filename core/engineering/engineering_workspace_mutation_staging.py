from __future__ import annotations
from .engineering_workspace_mutation_executor_common import *
from .engineering_workspace_mutation_transaction_store import store_paths,transition_state,write_json_atomic

def stage_mutations(binding,handoff,store):
    rs=[]; rec=[]; p=store_paths(binding,store['transaction_id'])
    for i,o in enumerate(ops_from_handoff(handoff)):
        typ=op_type(o)
        try:
            if typ in ('create_text_file','replace_text_file'):
                c=content(o)
                if not isinstance(c,str): rs.append('content_fingerprint_mismatch'); continue
                b=c.encode('utf-8')
                if len(b)>MAX_CONTENT: rs.append('content_bound_exceeded'); continue
                exp=expected_after(o)
                if exp and exp!=sha_bytes(b): rs.append('content_fingerprint_mismatch')
                name=f'staged-{i}.txt'; sp=p['staging']/name
                with sp.open('xb') as f: f.write(b); f.flush(); os.fsync(f.fileno())
                rec.append({'operation_id':o.get('operation_id'),'operation_type':typ,'staged_relative_path':f'staged/{name}','staged_content_fingerprint':file_fp(sp)[0],'byte_count':len(b),'target_path_fingerprint':rel_fingerprint(target_rel(o))})
            else:
                name=f'intent-{i}.json'; ip=p['staging']/name; r={'operation_id':o.get('operation_id'),'operation_type':typ,'target_path_fingerprint':rel_fingerprint(target_rel(o) or ''),'source_path_fingerprint':rel_fingerprint(source_rel(o) or '')}
                write_json_atomic(ip,r); rec.append({**r,'staged_relative_path':f'staged/{name}'})
        except Exception: rs.append('staging_failed')
    if not rs: transition_state(binding,store['transaction_id'],'staged')
    return finish('wsmut-stage','staging','staging_id',{'status':'staged' if not rs else 'failed','transaction_id':store.get('transaction_id'),'staged_records':rec,'reason_codes':reasons(rs)})
