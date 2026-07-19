from __future__ import annotations
from pathlib import Path
from .engineering_workspace_mutation_executor_common import *

def bind_workspace_root(workspace_root, handoff):
    rs=[]
    if not workspace_root: rs.append('trusted_workspace_root_required'); root=None
    else:
        root=Path(workspace_root)
        try: resolved=root.resolve(strict=True)
        except Exception: resolved=root; rs.append('workspace_root_not_found')
        if not rs:
            if not resolved.is_dir(): rs.append('workspace_root_not_directory')
            if str(resolved)==resolved.anchor: rs.append('filesystem_root_disallowed')
            if is_drive_root(resolved): rs.append('drive_root_disallowed')
            try:
                if not any(resolved.iterdir()): rs.append('workspace_root_empty')
            except Exception: rs.append('workspace_root_unreadable')
            fp=workspace_fingerprint(resolved)
            if handoff.get('workspace_root_fingerprint') and handoff.get('workspace_root_fingerprint')!=fp: rs.append('workspace_root_fingerprint_mismatch')
            if handoff.get('workspace_id') and handoff.get('workspace_id')!=(tx_package(handoff).get('workspace_id') or handoff.get('workspace_id')): rs.append('workspace_id_mismatch')
    art=finish('wsmut-root','root_binding','binding_id',{'workspace_id':handoff.get('workspace_id') or tx_package(handoff).get('workspace_id'),'workspace_root_fingerprint':handoff.get('workspace_root_fingerprint') or (workspace_fingerprint(resolved) if not rs else None),'root_kind_code':'trusted_directory','relative_transaction_directory_name':TX_PARENT,'status':'bound' if not rs else 'invalid','reason_codes':reasons(rs)})
    return RuntimeWorkspaceBinding(resolved if not rs else Path('.'),art)
