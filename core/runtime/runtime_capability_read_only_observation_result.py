from __future__ import annotations
from copy import deepcopy
from hashlib import sha256
import os
from pathlib import Path
from stat import S_ISDIR,S_ISREG
from typing import Any,Mapping
from core.runtime.runtime_capability_execution_session_admission import _hash
CONTRACT="zero.runtime.capability_read_only_observation_result.v1";SCHEMA_VERSION="1";STATUSES=frozenset({"observed","not_observed","blocked","failed","invalid"})
def _reparse(st:Any)->bool:return bool(getattr(st,"st_file_attributes",0)&1024)
def build_capability_read_only_observation_result(admission:Any,request:Any,resolution:Any)->dict[str,Any]:
 a,q,z=[deepcopy(dict(v)) if isinstance(v,Mapping) else {} for v in (admission,request,resolution)];obs={};read=entries=0;truncated=False;block=[];fail=[]
 link=z.get("read_only_admission_id")==a.get("read_only_admission_id") and z.get("observation_request_id")==q.get("observation_request_id") and z.get("observation_request_fingerprint")==q.get("observation_request_fingerprint")
 try:
  if a.get("admission_status")!="admitted" or q.get("request_status")!="accepted" or z.get("resolution_status") not in {"resolved","missing"} or not link:status="invalid";raise StopIteration
  root=Path(z["workspace_root_canonical"]);p=Path(z["resolved_target_canonical"]);rst=root.lstat()
  if root.is_symlink() or _reparse(rst) or os.path.commonpath((os.path.normcase(str(root)),os.path.normcase(str(p))))!=os.path.normcase(str(root)):status="blocked";block=["containment_invariant_failed"];raise StopIteration
  cur=root
  for part in q["relative_target"].split("/"):
   cur=cur/part;st=cur.lstat()
   if cur.is_symlink() or _reparse(st):status="blocked";block=["reparse_detected"];raise StopIteration
  kind=q["observation_kind"];lim=q["limits"]
  if kind=="existence":obs={"exists":True,"target_type":z["target_type"]};status="observed"
  elif kind=="metadata":obs={"target_type":z["target_type"],"size_bytes":z["target_size_bytes"],"read_only_metadata":{"regular_file":z["target_type"]=="regular_file","directory":z["target_type"]=="directory"}};status="observed"
  elif kind=="text_preview":
   before=p.lstat();cap=lim["max_preview_bytes"]
   with p.open("rb") as h:data=h.read(cap+1)
   read=min(len(data),cap);data=data[:cap];after=p.lstat()
   if before.st_size!=after.st_size or before.st_mtime_ns!=after.st_mtime_ns:status="failed";fail=["target_changed_during_observation"]
   elif b"\x00" in data:status="not_observed";fail=["binary_content"]
   else:
    try:text=data.decode("utf-8")
    except UnicodeDecodeError:status="not_observed";fail=["invalid_utf8"]
    else:truncated=before.st_size>cap;obs={"encoding":"utf-8","preview":text,"preview_bytes":len(data),"file_size_bytes":before.st_size};status="observed"
  elif kind=="sha256":
   before=p.lstat();cap=lim["max_file_bytes"]
   if before.st_size>cap:status="blocked";block=["file_size_limit_exceeded"]
   else:
    d=sha256()
    with p.open("rb") as h:
     while read<before.st_size:
      chunk=h.read(min(65536,before.st_size-read));
      if not chunk:break
      read+=len(chunk);d.update(chunk)
    after=p.lstat()
    if read!=before.st_size or before.st_size!=after.st_size or before.st_mtime_ns!=after.st_mtime_ns:status="failed";fail=["target_changed_during_observation"]
    else:obs={"algorithm":"sha256","digest":d.hexdigest(),"file_size_bytes":before.st_size};status="observed"
  else:
   names=[];cap=lim["max_directory_entries"]
   with os.scandir(p) as it:
    for item in it:
     if len(names)>cap:break
     if len(item.name.encode("utf-8"))>lim["max_name_bytes"]:status="blocked";block=["entry_name_limit_exceeded"];raise StopIteration
     typ="symlink_or_reparse" if item.is_symlink() else "directory" if item.is_dir(follow_symlinks=False) else "regular_file" if item.is_file(follow_symlinks=False) else "other";names.append({"name":item.name,"entry_type":typ})
   truncated=len(names)>cap;names=sorted(names,key=lambda x:x["name"])[:cap];entries=len(names);obs={"entries":names};status="observed"
 except FileNotFoundError:
  if q.get("observation_kind")=="existence":status="observed";obs={"exists":False,"target_type":"missing"}
  else:status="not_observed";fail=["target_missing"]
 except StopIteration:pass
 except (OSError,RuntimeError,ValueError,KeyError):status="failed";fail=["observation_failed"]
 evidence={"kind":q.get("observation_kind","") if isinstance(q.get("observation_kind"),str) else "","bounded":True,"target_resolution_fingerprint":z.get("target_resolution_fingerprint","")}
 b={"contract":CONTRACT,"schema_version":SCHEMA_VERSION,"read_only_admission_id":a.get("read_only_admission_id",""),"read_only_admission_fingerprint":a.get("read_only_admission_fingerprint",""),"observation_request_id":q.get("observation_request_id",""),"observation_request_fingerprint":q.get("observation_request_fingerprint",""),"target_resolution_id":z.get("target_resolution_id",""),"target_resolution_fingerprint":z.get("target_resolution_fingerprint",""),"observation_kind":q.get("observation_kind","") if isinstance(q.get("observation_kind"),str) else "","result_status":status,"observed":status=="observed","observation":obs,"evidence_descriptor":evidence,"bytes_read":read,"entries_observed":entries,"truncated":truncated,"side_effects_performed":[],"reasons":["observation_"+status],"blocked_reasons":block,"failure_reasons":fail};f=_hash(b);return {**b,"observation_result_id":"capability-read-only-observation-result-"+f[:24],"observation_result_fingerprint":f}
observe_capability_read_only=build_capability_read_only_observation_result
