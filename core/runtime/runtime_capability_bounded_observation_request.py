from __future__ import annotations
from copy import deepcopy
from typing import Any,Mapping
from core.runtime.runtime_capability_execution_session_admission import _hash,_safe
CONTRACT="zero.runtime.capability_bounded_observation_request.v1";SCHEMA_VERSION="1";STATUSES=frozenset({"accepted","not_accepted","blocked","invalid"});KINDS=frozenset({"existence","metadata","text_preview","sha256","directory_listing"});LIMIT_FIELDS=frozenset({"max_file_bytes","max_preview_bytes","max_directory_entries","max_name_bytes"});HARD_LIMITS={"max_file_bytes":4194304,"max_preview_bytes":65536,"max_directory_entries":512,"max_name_bytes":1024}
def _target(v:Any)->tuple[str,bool]:
 if not isinstance(v,str) or not v or "\x00" in v:return "",False
 x="\\".join(v.split("/"));parts=x.split("\\")
 if x.startswith("\\") or ":" in x or any(p in ("","..") for p in parts):return x,False
 return "/".join(parts),True
def build_capability_bounded_observation_request(admission:Any,request:Any,*,observation_kind:Any,relative_target:Any,limits:Any)->dict[str,Any]:
 a=deepcopy(dict(admission)) if isinstance(admission,Mapping) else {};r=deepcopy(dict(request)) if isinstance(request,Mapping) else {}
 try:l=_safe(limits)
 except (TypeError,ValueError):l={};bad=True
 else:bad=False
 t,tok=_target(relative_target);lok=isinstance(l,Mapping) and set(l)==LIMIT_FIELDS and all(isinstance(l.get(n),int) and not isinstance(l.get(n),bool) and 0<l[n]<=HARD_LIMITS[n] for n in LIMIT_FIELDS)
 link=a.get("request_id")==r.get("request_id") and a.get("request_fingerprint")==r.get("fingerprint")
 if bad or not isinstance(observation_kind,str):status="invalid";why="malformed_observation_request"
 elif a.get("admission_status")!="admitted" or r.get("status")!="accepted":status="not_accepted";why="upstream_not_eligible"
 elif not link or observation_kind not in KINDS or observation_kind not in a.get("allowed_observation_kinds",[]) or not tok or not lok:status="blocked";why="observation_boundary_violation"
 else:status="accepted";why="bounded_observation_request_accepted"
 b={"contract":CONTRACT,"schema_version":SCHEMA_VERSION,"read_only_admission_id":a.get("read_only_admission_id",""),"read_only_admission_fingerprint":a.get("read_only_admission_fingerprint",""),"authority_id":a.get("authority_id",""),"authority_fingerprint":a.get("authority_fingerprint",""),"request_id":r.get("request_id",""),"request_fingerprint":r.get("fingerprint",""),"observation_kind":observation_kind if isinstance(observation_kind,str) else "","relative_target":t,"limits":dict(l) if isinstance(l,Mapping) else {},"request_status":status,"accepted":status=="accepted","reasons":[why],"blocked_reasons":[why] if status=="blocked" else []};f=_hash(b);return {**b,"observation_request_id":"capability-bounded-observation-request-"+f[:24],"observation_request_fingerprint":f}
