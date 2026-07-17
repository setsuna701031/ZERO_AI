from __future__ import annotations
from copy import deepcopy
import os
from pathlib import Path
from stat import S_ISDIR,S_ISREG
from typing import Any,Mapping
from core.runtime.runtime_capability_execution_session_admission import _hash
CONTRACT="zero.runtime.capability_safe_target_resolution.v1";SCHEMA_VERSION="1";STATUSES=frozenset({"resolved","missing","blocked","failed","invalid"})
def _reparse(st:Any)->bool:return bool(getattr(st,"st_file_attributes",0)&1024)
def build_capability_safe_target_resolution(admission:Any,observation_request:Any)->dict[str,Any]:
 a=deepcopy(dict(admission)) if isinstance(admission,Mapping) else {};q=deepcopy(dict(observation_request)) if isinstance(observation_request,Mapping) else {};root="";target="";exists=False;typ="unknown";size=0;symlink=False;contained=False;fail=[];block=[]
 link=q.get("read_only_admission_id")==a.get("read_only_admission_id") and q.get("read_only_admission_fingerprint")==a.get("read_only_admission_fingerprint")
 try:
  raw=a.get("workspace_root_descriptor");raw=raw.get("path") if isinstance(raw,Mapping) else raw
  if not isinstance(raw,str) or not raw:raise ValueError
  rp=Path(raw).absolute();rst=rp.lstat();root=str(rp)
  if not S_ISDIR(rst.st_mode):status="blocked";block=["workspace_root_not_directory"]
  elif rp.is_symlink() or _reparse(rst):status="blocked";symlink=True;block=["workspace_root_reparse_point"]
  elif a.get("admission_status")!="admitted" or q.get("request_status")!="accepted" or not link:status="invalid";fail=["invalid_resolution_chain"]
  else:
   cur=rp
   for part in q.get("relative_target","").split("/"):
    cur=cur/part
    try:st=cur.lstat()
    except FileNotFoundError:st=None;break
    if cur.is_symlink() or _reparse(st):symlink=True;break
   target=str(cur.absolute());contained=os.path.commonpath((os.path.normcase(root),os.path.normcase(target)))==os.path.normcase(root)
   if symlink or not contained:status="blocked";block=["target_reparse_or_escape"]
   elif st is None:status="missing";typ="missing"
   else:
    exists=True;typ="regular_file" if S_ISREG(st.st_mode) else "directory" if S_ISDIR(st.st_mode) else "other";size=st.st_size if typ=="regular_file" else 0;compatible=q.get("observation_kind") in ({"existence"} if typ=="missing" else {"existence","metadata"}|({"text_preview","sha256"} if typ=="regular_file" else {"directory_listing"} if typ=="directory" else set()))
    if compatible:status="resolved"
    else:status="blocked";block=["target_type_incompatible"]
 except FileNotFoundError:status="failed";fail=["workspace_root_missing"]
 except (OSError,RuntimeError,ValueError):status="failed";fail=["safe_resolution_failed"]
 b={"contract":CONTRACT,"schema_version":SCHEMA_VERSION,"read_only_admission_id":a.get("read_only_admission_id",""),"read_only_admission_fingerprint":a.get("read_only_admission_fingerprint",""),"observation_request_id":q.get("observation_request_id",""),"observation_request_fingerprint":q.get("observation_request_fingerprint",""),"workspace_root_canonical":root,"relative_target":q.get("relative_target","") if isinstance(q.get("relative_target"),str) else "","resolved_target_canonical":target,"target_exists":exists,"target_type":typ,"target_size_bytes":size,"symlink_or_reparse_detected":symlink,"containment_verified":contained,"resolution_status":status,"reasons":["target_"+status],"blocked_reasons":block,"failure_reasons":fail};f=_hash(b);return {**b,"target_resolution_id":"capability-safe-target-resolution-"+f[:24],"target_resolution_fingerprint":f}
resolve_capability_safe_target=build_capability_safe_target_resolution
