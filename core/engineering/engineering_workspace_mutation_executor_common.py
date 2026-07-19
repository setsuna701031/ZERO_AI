from __future__ import annotations
import hashlib,json,os,shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any,Mapping

SCHEMAS={k:f"zero.engineering.workspace_mutation_{k}.v1" for k in ['root_binding','executor_admission','live_precondition','token_consumption','transaction_store','backup_capture','staging','stage_validation','commit_gate','atomic_commit','post_commit_verification','failure','rollback','recovery_verification','result','execution_evidence','execution_closure']}
SUPPORTED=("create_text_file","replace_text_file","delete_file","create_directory","rename_path")
TX_PARENT='.zero/transactions'; MAX_CONTENT=1_000_000; MAX_OPS=100; MAX_BACKUP=5_000_000
FALSE_FLAGS=("transaction_execution_authorized","authorization_token_consumed","preparation_token_consumed","mutation_executor_invoked","transaction_started","backup_created","commit_started","commit_completed","rollback_performed","recovery_performed","mutation_performed","filesystem_write_performed","patch_applied","git_invoked","shell_invoked","runtime_kernel_invoked","network_invoked","model_invoked","adapter_invoked")
FAILURE_CODES={"workspace_binding_invalid","upstream_linkage_invalid","executor_not_admitted","token_invalid","token_conflict","duplicate_transaction","transaction_state_invalid","path_invalid","path_escape","symlink_disallowed","precondition_mismatch","source_missing","target_exists","target_missing","target_kind_invalid","content_fingerprint_mismatch","backup_failed","backup_verification_failed","staging_failed","stage_validation_failed","commit_not_authorized","atomic_commit_failed","post_commit_verification_failed","rollback_failed","recovery_verification_failed","permission_denied","workspace_changed","unsupported_operation","invariant_violation","internal_execution_failure"}

def canonical_json(v:Any)->str: return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False)
def sha_bytes(b:bytes)->str: return hashlib.sha256(b).hexdigest()
def fingerprint(v:Any)->str: return sha_bytes(canonical_json(v).encode('utf-8'))
def identity(prefix:str,body:Mapping[str,Any])->str: return prefix+'-'+fingerprint(body)[:24]
def reasons(xs): return sorted(set(str(x) for x in xs if x))
def finish(prefix,schema_key,id_key,body):
    b=dict(body); b['schema']=SCHEMAS[schema_key]; b[id_key]=identity(prefix,{k:v for k,v in b.items() if k not in (id_key,'fingerprint','root_path')}); b['fingerprint']=fingerprint({k:v for k,v in b.items() if k!='fingerprint' and k!='root_path'}); return b
def write_json_atomic(path:Path,obj:Any):
    data=(canonical_json(obj)+'\n').encode('utf-8'); tmp=path.with_name(path.name+'.tmp');
    with tmp.open('xb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
    tmp.replace(path)
def read_json(path:Path):
    with path.open('r',encoding='utf-8') as f: return json.load(f)
def file_fp(p:Path):
    b=p.read_bytes(); b.decode('utf-8'); return sha_bytes(b),len(b)
def op_type(o): return o.get('operation_type') or o.get('operation_class')
def target_rel(o): return o.get('target_path') or o.get('target_relative_path') or o.get('path')
def source_rel(o): return o.get('source_path') or o.get('source_relative_path')
def content(o): return o.get('proposed_content') if 'proposed_content' in o else o.get('content','')
def expected_before(o): return o.get('expected_before_fingerprint') or o.get('before_fingerprint')
def expected_after(o): return o.get('expected_after_fingerprint') or o.get('proposed_after_fingerprint') or o.get('content_fingerprint')
def ops_from_package(pkg): return list(pkg.get('operations') or pkg.get('authorized_operations') or pkg.get('ordered_operations') or pkg.get('prepared_operations') or [])
def ops_from_handoff(h):
    pkg=h.get('transaction_package') or h.get('mutation_transaction_package') or h.get('package') or h.get('mutation_package') or {}
    return ops_from_package(pkg) or list(h.get('authorized_operations') or h.get('operations') or [])
def tx_package(h): return h.get('transaction_package') or h.get('mutation_transaction_package') or h.get('package') or h.get('mutation_package') or h
def rel_fingerprint(s): return sha_bytes(str(s).encode('utf-8'))
def is_drive_root(p:Path):
    return (p.anchor and str(p.resolve())==p.anchor) or (len(str(p)) in (2,3) and str(p)[1:2]==':')
def workspace_fingerprint(root:Path): return fingerprint({'workspace_root_name':root.resolve().name,'root_kind':'directory'})
def transaction_id(h,admission=None): return identity('wsmutx',{'handoff_id':h.get('handoff_id'),'handoff_fingerprint':h.get('fingerprint'),'package_id':tx_package(h).get('transaction_package_id') or tx_package(h).get('mutation_package_id'),'admission':(admission or {}).get('fingerprint')})

def safe_rel_path(rel:str)->tuple[bool,list[str]]:
    rs=[]
    if not isinstance(rel,str) or not rel: rs.append('path_invalid')
    if '\x00' in str(rel): rs.append('path_invalid')
    if str(rel).startswith(('\\\\','//')): rs.append('path_escape')
    if Path(str(rel)).is_absolute() or (len(str(rel))>1 and str(rel)[1]==':'): rs.append('path_escape')
    if '\\' in str(rel) or '//' in str(rel): rs.append('path_invalid')
    parts=str(rel).split('/')
    if any(p in ('','.', '..') for p in parts): rs.append('path_escape')
    if ':' in str(rel): rs.append('path_invalid')
    if str(rel)=='.zero' or str(rel).startswith(TX_PARENT) or str(rel).startswith('.zero/transactions/'): rs.append('path_escape')
    return (not rs,reasons(rs))

def resolve_inside(root:Path,rel:str):
    ok,rs=safe_rel_path(rel)
    if not ok: return None,rs
    p=(root/rel).resolve(strict=False); rr=root.resolve()
    try: p.relative_to(rr)
    except ValueError: return None,['path_escape']
    cur=rr
    for part in Path(rel).parts[:-1]:
        cur=cur/part
        if cur.exists() and cur.is_symlink(): return None,['symlink_disallowed']
    if p.exists() and p.is_symlink(): return None,['symlink_disallowed']
    return p,[]

@dataclass(frozen=True)
class RuntimeWorkspaceBinding:
    root_path: Path
    artifact: dict[str,Any]
