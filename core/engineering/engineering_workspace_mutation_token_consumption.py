from __future__ import annotations
from .engineering_workspace_mutation_executor_common import *
from .engineering_workspace_mutation_transaction_store import store_paths,read_json,write_json_atomic

def prepare_token_consumption(binding,handoff,admission,store):
    rs=[]; status='pending'
    tok=handoff.get('authorization_token',{}); ptok=handoff.get('preparation_token',{})
    if tok.get('token_consumed') is not False or ptok.get('token_consumed') is not False: rs.append('token_invalid'); status='invalid'
    if store.get('status')=='duplicate_suppressed': status='duplicate_suppressed'
    elif store.get('status')!='created': rs.append('transaction_state_invalid'); status='invalid'
    if status=='pending':
        p=store_paths(binding,store['transaction_id']); m=read_json(p['manifest']); m['token_consumption']={'authorization':'pending','preparation':'pending','authorization_token_id':tok.get('token_id'),'preparation_token_id':ptok.get('token_id')}; write_json_atomic(p['manifest'],m)
    return finish('wsmut-token','token_consumption','token_consumption_id',{'status':status,'transaction_id':store.get('transaction_id'),'authorization_token_id':tok.get('token_id'),'preparation_token_id':ptok.get('token_id'),'authorization_token_state':status if status!='pending' else 'pending','preparation_token_state':status if status!='pending' else 'pending','reason_codes':reasons(rs)})
def finalize_token_consumption(binding,txid,success=True):
    p=store_paths(binding,txid); m=read_json(p['manifest']); state='consumed' if success else 'consumed'; m['token_consumption']['authorization']=state; m['token_consumption']['preparation']=state; write_json_atomic(p['manifest'],m); return m['token_consumption']
