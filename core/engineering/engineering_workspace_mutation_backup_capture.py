from __future__ import annotations
from .engineering_workspace_mutation_executor_common import *
from .engineering_workspace_mutation_transaction_store import store_paths,transition_state,write_json_atomic

def capture_backups(binding,handoff,store):
    rs=[]; records=[]; total=0; p=store_paths(binding,store['transaction_id'])
    if store.get('status') not in ('created','preconditions_verified'): rs.append('transaction_state_invalid')
    for i,o in enumerate(ops_from_handoff(handoff)):
        typ=op_type(o)
        if typ not in ('replace_text_file','delete_file','rename_path'):
            records.append({'operation_id':o.get('operation_id'),'status':'not_required'}); continue
        rel=source_rel(o) if typ=='rename_path' else target_rel(o); src,rr=resolve_inside(binding.root_path,rel); rs+=rr
        try:
            if rr or not src.exists() or src.is_symlink(): rs.append('backup_failed'); records.append({'operation_id':o.get('operation_id'),'status':'failed'}); continue
            if src.is_file():
                b=src.read_bytes(); b.decode('utf-8'); total+=len(b)
                if total>MAX_BACKUP: rs.append('backup_byte_bound_exceeded'); records.append({'operation_id':o.get('operation_id'),'status':'failed'}); continue
                name=f'backup-{i}.bin'; bp=p['backup']/name
                with bp.open('xb') as f: f.write(b); f.flush(); os.fsync(f.fileno())
                rec={'operation_id':o.get('operation_id'),'status':'captured','backup_kind':'utf8_file','backup_relative_path':f'backup/{name}','before_fingerprint':sha_bytes(b),'byte_count':len(b),'backup_fingerprint':file_fp(bp)[0]}
            elif src.is_dir() and typ=='rename_path':
                rec={'operation_id':o.get('operation_id'),'status':'captured','backup_kind':'directory_metadata','source_path_fingerprint':rel_fingerprint(rel),'byte_count':0}
            else: rs.append('target_kind_invalid'); rec={'operation_id':o.get('operation_id'),'status':'failed'}
            records.append(rec)
        except Exception: rs.append('backup_failed'); records.append({'operation_id':o.get('operation_id'),'status':'failed'})
    if not rs: transition_state(binding,store['transaction_id'],'backups_captured')
    return finish('wsmut-backup','backup_capture','backup_capture_id',{'status':'captured' if not rs else 'failed','transaction_id':store.get('transaction_id'),'backup_records':records,'total_backup_bytes':total,'reason_codes':reasons(rs)})
