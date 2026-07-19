from __future__ import annotations
from .engineering_workspace_mutation_executor_common import *

def inspect_live_preconditions(binding,handoff,admission):
    rs=[]; details=[]; root=binding.root_path
    if admission.get('status')!='admitted': rs.append('executor_not_admitted')
    for o in ops_from_handoff(handoff):
        typ=op_type(o); tr=target_rel(o); tp,rr=resolve_inside(root,tr); rs+=rr; d={'operation_id':o.get('operation_id'),'operation_type':typ,'target_path_fingerprint':rel_fingerprint(tr or '')}
        if rr: details.append({**d,'status':'invalid'}); continue
        try:
            if typ=='create_text_file':
                if tp.exists(): rs.append('target_exists'); st='not_satisfied'
                else: st='satisfied'
            elif typ=='create_directory':
                if tp.exists(): rs.append('target_exists'); st='not_satisfied'
                else: st='satisfied'
            elif typ in ('replace_text_file','delete_file'):
                if not tp.exists(): rs.append('target_missing'); st='not_satisfied'
                elif not tp.is_file() or tp.is_symlink(): rs.append('target_kind_invalid'); st='not_satisfied'
                else:
                    fp,sz=file_fp(tp); eb=expected_before(o); st='satisfied' if (not eb or eb==fp) else 'not_satisfied';
                    if st!='satisfied': rs.append('precondition_mismatch')
                    d.update({'actual_before_fingerprint':fp,'actual_byte_count':sz})
            elif typ=='rename_path':
                sp,sr=resolve_inside(root,source_rel(o)); rs+=sr
                if sr or not sp.exists(): rs.append('source_missing'); st='not_satisfied'
                elif tp.exists(): rs.append('target_exists'); st='not_satisfied'
                elif sp.is_symlink(): rs.append('symlink_disallowed'); st='not_satisfied'
                else: st='satisfied'
            else: rs.append('unsupported_operation'); st='invalid'
        except Exception: rs.append('internal_execution_failure'); st='invalid'
        details.append({**d,'status':st})
    return finish('wsmut-pre','live_precondition','precondition_id',{'status':'satisfied' if not rs else ('invalid' if any(x in rs for x in ['path_escape','path_invalid']) else 'not_satisfied'),'admission_id':admission.get('admission_id'),'workspace_id':admission.get('workspace_id'),'transaction_id':admission.get('transaction_id'),'operation_preconditions':details,'reason_codes':reasons(rs)})
