from __future__ import annotations
from copy import deepcopy
from typing import Any,Mapping
from core.runtime.runtime_capability_execution_session_admission import _hash,_safe
from core.runtime.runtime_capability_execution_authority import SAFE_OPERATION_CLASSES
CONTRACT="zero.runtime.capability_executor_adapter_admission.v1";SCHEMA_VERSION="1";STATUSES=frozenset({"admitted","not_admitted","blocked","invalid"})
CAPABILITY_NAMES=("mutation","external_process","network","model_invocation","filesystem_read","filesystem_write")
def _seal(b):f=_hash(b);return {**b,"adapter_admission_id":"capability-executor-adapter-admission-"+f[:24],"adapter_admission_fingerprint":f}
def build_capability_executor_adapter_admission(authority:Any,request:Any,*,adapter_id:Any="dry-run-adapter",adapter_kind:Any="declarative_executor_adapter",adapter_mode:Any="dry_run",supported_operation_classes:Any=None,adapter_capabilities:Any=None)->dict[str,Any]:
 a=deepcopy(dict(authority)) if isinstance(authority,Mapping) else {};r=deepcopy(dict(request)) if isinstance(request,Mapping) else {};ops=sorted(SAFE_OPERATION_CLASSES) if supported_operation_classes is None else supported_operation_classes;caps={n:False for n in CAPABILITY_NAMES} if adapter_capabilities is None else adapter_capabilities
 try:ops=_safe(ops);caps=_safe(caps)
 except (TypeError,ValueError):ops=[];caps={};bad=True
 else:bad=False
 link=r.get("authority_id")==a.get("authority_id") and r.get("authority_fingerprint")==a.get("fingerprint");perms=isinstance(a.get("authority_constraints"),Mapping) and all(a["authority_constraints"].get(n) is False for n in ("mutation_permission","external_process_permission","network_permission","model_invocation_permission"));capok=isinstance(caps,Mapping) and set(caps)==set(CAPABILITY_NAMES) and all(caps.get(n) is False for n in CAPABILITY_NAMES)
 if bad or not isinstance(adapter_id,str) or not adapter_id:status="invalid";why="malformed_adapter_configuration"
 elif a.get("status")!="authorized" or r.get("status")!="accepted":status="not_admitted";why="upstream_not_eligible"
 elif not link or adapter_kind!="declarative_executor_adapter" or adapter_mode!="dry_run" or r.get("operation_class") not in ops or r.get("operation_class") not in SAFE_OPERATION_CLASSES or not perms or not capok:status="blocked";why="dry_run_boundary_violation"
 else:status="admitted";why="dry_run_adapter_admitted"
 b={"contract":CONTRACT,"schema_version":SCHEMA_VERSION,"authority_id":a.get("authority_id","") if isinstance(a.get("authority_id"),str) else "","authority_fingerprint":a.get("fingerprint","") if isinstance(a.get("fingerprint"),str) else "","request_id":r.get("request_id","") if isinstance(r.get("request_id"),str) else "","request_fingerprint":r.get("fingerprint","") if isinstance(r.get("fingerprint"),str) else "","adapter_id":adapter_id if isinstance(adapter_id,str) else "","adapter_kind":adapter_kind if isinstance(adapter_kind,str) else "","adapter_mode":adapter_mode if isinstance(adapter_mode,str) else "","supported_operation_classes":ops,"adapter_capabilities":caps,"admission_status":status,"admitted":status=="admitted","reasons":[why],"blocked_reasons":[why] if status=="blocked" else []};return _seal(b)
admit_capability_executor_adapter=build_capability_executor_adapter_admission
