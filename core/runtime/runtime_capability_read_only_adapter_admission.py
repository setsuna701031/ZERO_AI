from __future__ import annotations
from copy import deepcopy
from typing import Any,Mapping
from core.runtime.runtime_capability_execution_session_admission import _hash,_safe
CONTRACT="zero.runtime.capability_read_only_adapter_admission.v1";SCHEMA_VERSION="1";STATUSES=frozenset({"admitted","not_admitted","blocked","invalid"})
KINDS=["directory_listing","existence","metadata","sha256","text_preview"]
CAPABILITIES={"filesystem_read":True,"filesystem_metadata":True,"filesystem_write":False,"filesystem_mutation":False,"external_process":False,"network":False,"model_invocation":False}
def build_capability_read_only_adapter_admission(authority:Any,request:Any,bridge_closure:Any,*,adapter_id:Any="read-only-observation-adapter",adapter_kind:Any="bounded_read_only_observation_adapter",adapter_mode:Any="read_only",workspace_root_descriptor:Any=None,allowed_observation_kinds:Any=None,adapter_capabilities:Any=None)->dict[str,Any]:
 a,r,c=[deepcopy(dict(v)) if isinstance(v,Mapping) else {} for v in (authority,request,bridge_closure)]
 try:w=_safe(workspace_root_descriptor);k=_safe(KINDS if allowed_observation_kinds is None else allowed_observation_kinds);caps=_safe(CAPABILITIES if adapter_capabilities is None else adapter_capabilities)
 except (TypeError,ValueError):w={};k=[];caps={};bad=True
 else:bad=False
 link=r.get("authority_id")==a.get("authority_id") and r.get("authority_fingerprint")==a.get("fingerprint") and c.get("authority_id")==a.get("authority_id") and c.get("authority_fingerprint")==a.get("fingerprint") and c.get("request_id")==r.get("request_id") and c.get("request_fingerprint")==r.get("fingerprint")
 perms=isinstance(a.get("authority_constraints"),Mapping) and all(a["authority_constraints"].get(n) is False for n in ("mutation_permission","external_process_permission","network_permission","model_invocation_permission"))
 if bad or not isinstance(adapter_id,str) or not adapter_id or not isinstance(w,(str,Mapping)) or not w:status="invalid";why="malformed_read_only_admission"
 elif a.get("status")!="authorized" or r.get("status")!="accepted" or c.get("verification_status")!="verified_closed":status="not_admitted";why="upstream_not_eligible"
 elif not link or c.get("closed") is not True or c.get("execution_completion_claim",False) is not False or c.get("recommended_v1_2_outcome_status","not_completed")!="not_completed" or r.get("operation_class") not in {"inspect","observe","verify","describe"} or not perms or adapter_kind!="bounded_read_only_observation_adapter" or adapter_mode!="read_only" or caps!=CAPABILITIES or not isinstance(k,list) or not k or not set(k)<=set(KINDS):status="blocked";why="read_only_boundary_violation"
 else:status="admitted";why="read_only_adapter_admitted"
 b={"contract":CONTRACT,"schema_version":SCHEMA_VERSION,"authority_id":a.get("authority_id",""),"authority_fingerprint":a.get("fingerprint",""),"request_id":r.get("request_id",""),"request_fingerprint":r.get("fingerprint",""),"bridge_closure_id":c.get("bridge_closure_id",""),"bridge_closure_fingerprint":c.get("bridge_closure_fingerprint",""),"adapter_id":adapter_id if isinstance(adapter_id,str) else "","adapter_kind":adapter_kind if isinstance(adapter_kind,str) else "","adapter_mode":adapter_mode if isinstance(adapter_mode,str) else "","workspace_root_descriptor":w,"allowed_observation_kinds":sorted(k) if isinstance(k,list) else [],"adapter_capabilities":caps,"admission_status":status,"admitted":status=="admitted","reasons":[why],"blocked_reasons":[why] if status=="blocked" else []};f=_hash(b);return {**b,"read_only_admission_id":"capability-read-only-adapter-admission-"+f[:24],"read_only_admission_fingerprint":f}
admit_capability_read_only_adapter=build_capability_read_only_adapter_admission
