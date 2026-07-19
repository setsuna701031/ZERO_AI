from __future__ import annotations
from .engineering_workspace_mutation_executor_common import *

def admit_workspace_mutation_executor(binding,handoff):
    rs=[]; pkg=tx_package(handoff); ops=ops_from_handoff(handoff)
    if binding.artifact.get('status')!='bound': rs.append('workspace_binding_invalid')
    if handoff.get('schema')!='zero.engineering.mutation_executor_handoff.v1': rs.append('handoff_schema_invalid')
    for k in ('transaction_closure','readiness','transaction_package_validation','authorization_token','preparation_token','authorization_verification','authorization_decision','authorized_scope','mutation_package_validation'):
        a=handoff.get(k,{})
        if a and a.get('status') in ('invalid','not_ready','not_verified','not_valid','failed'): rs.append(k+'_invalid')
    if handoff.get('human_mutation_authorization_obtained',handoff.get('human_authorization_obtained',True)) is not True: rs.append('human_authorization_missing')
    if handoff.get('transaction_planning_completed',True) is not True: rs.append('transaction_planning_incomplete')
    if handoff.get('transaction_execution_authorized',False) is not False: rs.append('upstream_already_authorized')
    for k in FALSE_FLAGS:
        if handoff.get(k,False) is not False: rs.append(k+'_not_false')
    tok=handoff.get('authorization_token',{})
    if tok and (tok.get('token_purpose')!='workspace_mutation_transaction_admission' or tok.get('use_limit')!=1 or tok.get('token_consumed') is not False): rs.append('token_invalid')
    ptok=handoff.get('preparation_token',{})
    if ptok and ptok.get('token_consumed') is not False: rs.append('preparation_token_consumed')
    if not ops: rs.append('empty_operation_subset')
    if len(ops)>MAX_OPS: rs.append('operation_bound_exceeded')
    targets=[]; ren=[]
    for o in ops:
        typ=op_type(o); tr=target_rel(o); sr=source_rel(o)
        if typ not in SUPPORTED: rs.append('unsupported_operation')
        if tr: 
            ok,rr=safe_rel_path(tr); rs+=rr; targets.append(tr)
        else: rs.append('target_missing')
        if typ=='rename_path':
            if not sr: rs.append('source_missing')
            else:
                ok,rr=safe_rel_path(sr); rs+=rr; ren.append((sr,tr))
                if sr==tr: rs.append('source_target_identity')
        if typ in ('create_text_file','replace_text_file'):
            c=content(o)
            if not isinstance(c,str): rs.append('binary_content')
            elif len(c.encode('utf-8'))>MAX_CONTENT: rs.append('content_bound_exceeded')
    if len(targets)!=len(set(targets)): rs.append('duplicate_target_conflict')
    for a in targets:
        for b in targets:
            if a!=b and (a.startswith(b+'/') or b.startswith(a+'/')): rs.append('parent_child_conflict')
    if any(a==d and b==c for a,b in ren for c,d in ren): rs.append('rename_cycle')
    body={'status':'admitted' if not rs else ('invalid' if 'handoff_schema_invalid' in rs else 'not_admitted'),'workspace_mutation_execution_admitted':not rs,'workspace_id':binding.artifact.get('workspace_id'),'workspace_root_fingerprint':binding.artifact.get('workspace_root_fingerprint'),'binding_id':binding.artifact.get('binding_id'),'handoff_id':handoff.get('handoff_id'),'handoff_fingerprint':handoff.get('fingerprint'),'transaction_package_id':pkg.get('transaction_package_id') or pkg.get('mutation_package_id'),'transaction_package_fingerprint':pkg.get('fingerprint'),'operation_ids':[o.get('operation_id') for o in ops],'operation_fingerprints':[o.get('operation_fingerprint') or o.get('fingerprint') for o in ops],'operation_count':len(ops),'reason_codes':reasons(rs)}
    body['transaction_id']=transaction_id(handoff,body)
    return finish('wsmut-admit','executor_admission','admission_id',body)
