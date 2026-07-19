from __future__ import annotations
from pathlib import Path
from .engineering_workspace_mutation_executor_common import *
ORDER=['created','preconditions_verified','backups_captured','staged','stage_verified','commit_admitted','committing','committed','post_commit_verified','rolling_back','rolled_back','recovery_verified','failed','invalid']
TERMINAL={'post_commit_verified','recovery_verified','failed'}
def store_paths(binding,txid):
    base=binding.root_path/TX_PARENT/txid
    return {'base':base,'manifest':base/'manifest.json','journal':base/'journal.json','staging':base/'staged','backup':base/'backup','commit_marker':base/'commit.marker.json','rollback_marker':base/'rollback.marker.json','completion_marker':base/'completion.marker.json'}
def create_transaction_store(binding,handoff,admission,dry_run=False):
    rs=[]; txid=admission.get('transaction_id') or transaction_id(handoff,admission); p=store_paths(binding,txid)
    if admission.get('status')!='admitted': rs.append('executor_not_admitted')
    existing=p['base'].exists()
    if existing:
        try: m=read_json(p['manifest']); st=m.get('state')
        except Exception: m={}; st='invalid'; rs.append('transaction_state_invalid')
        if st in TERMINAL: status='duplicate_suppressed'; rs.append('duplicate_transaction')
        else: status='invalid'; rs.append('duplicate_transaction')
    elif dry_run: status='planned'
    elif not rs:
        try:
            p['base'].mkdir(mode=0o700,parents=True,exist_ok=False); p['staging'].mkdir(); p['backup'].mkdir()
            m={'transaction_id':txid,'state':'created','workspace_id':admission.get('workspace_id'),'handoff_id':handoff.get('handoff_id'),'relative_transaction_directory':f'{TX_PARENT}/{txid}','operation_ids':admission.get('operation_ids',[]),'token_consumption':{'authorization':'not_consumed','preparation':'not_consumed'}}
            write_json_atomic(p['manifest'],m); write_json_atomic(p['journal'],{'transaction_id':txid,'entries':[]})
            status='created'
        except Exception: rs.append('internal_execution_failure'); status='invalid'
    else: status='invalid'
    return finish('wsmut-store','transaction_store','store_id',{'status':status,'transaction_id':txid,'relative_transaction_directory':f'{TX_PARENT}/{txid}','manifest_name':'manifest.json','journal_name':'journal.json','state':status if status in ORDER else status,'reason_codes':reasons(rs)})
def transition_state(binding,txid,new_state):
    p=store_paths(binding,txid); m=read_json(p['manifest']); old=m.get('state')
    if old in ORDER and new_state in ORDER and ORDER.index(new_state)>=ORDER.index(old):
        m['state']=new_state; write_json_atomic(p['manifest'],m); return True
    return False
def append_journal(binding,txid,event):
    p=store_paths(binding,txid); j=read_json(p['journal']); entries=j.get('entries',[]); e=dict(event); e['sequence']=len(entries); e['fingerprint']=fingerprint(e); entries.append(e); j['entries']=entries; write_json_atomic(p['journal'],j); return e
