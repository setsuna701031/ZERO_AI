from __future__ import annotations
from copy import deepcopy
from typing import Any,Mapping
from core.runtime.runtime_capability_execution_session_admission import _hash,_safe
CONTRACT="zero.runtime.capability_dry_run_dispatch_plan.v1";SCHEMA_VERSION="1";STATUSES=frozenset({"planned","not_planned","blocked","invalid"})
PROHIBITED_EFFECTS=["external_side_effect","filesystem_mutation","filesystem_read","model_invocation","network_access","process_creation","scheduler_dispatch","worker_dispatch"]
def build_capability_dry_run_dispatch_plan(adapter_admission:Any,request:Any,*,dispatch_ordinal:Any=0,target_descriptor:Any=None,bounded_parameters:Any=None)->dict[str,Any]:
 a=deepcopy(dict(adapter_admission)) if isinstance(adapter_admission,Mapping) else {};r=deepcopy(dict(request)) if isinstance(request,Mapping) else {}
 try:t=_safe(r.get("target_descriptor") if target_descriptor is None else target_descriptor);p=_safe(r.get("bounded_parameters") if bounded_parameters is None else bounded_parameters)
 except (TypeError,ValueError):t={};p={};bad=True
 else:bad=False
 same=t==r.get("target_descriptor") and p==r.get("bounded_parameters");link=a.get("request_id")==r.get("request_id") and a.get("request_fingerprint")==r.get("fingerprint")
 if bad or not isinstance(dispatch_ordinal,int) or isinstance(dispatch_ordinal,bool) or dispatch_ordinal<0:status="invalid";why="malformed_dispatch_plan"
 elif a.get("admission_status")!="admitted":status="not_planned";why="adapter_not_admitted"
 elif not same or not link or a.get("adapter_mode")!="dry_run":status="blocked";why="dispatch_boundary_violation"
 else:status="planned";why="dry_run_dispatch_planned"
 b={"contract":CONTRACT,"schema_version":SCHEMA_VERSION,"adapter_admission_id":a.get("adapter_admission_id",""),"adapter_admission_fingerprint":a.get("adapter_admission_fingerprint",""),"authority_id":a.get("authority_id",""),"authority_fingerprint":a.get("authority_fingerprint",""),"request_id":r.get("request_id","") if isinstance(r.get("request_id"),str) else "","request_fingerprint":r.get("fingerprint","") if isinstance(r.get("fingerprint"),str) else "","adapter_id":a.get("adapter_id",""),"adapter_mode":a.get("adapter_mode",""),"operation_class":r.get("operation_class",""),"target_descriptor":t,"bounded_parameters":p,"dispatch_ordinal":dispatch_ordinal if isinstance(dispatch_ordinal,int) and not isinstance(dispatch_ordinal,bool) else -1,"dry_run":True,"expected_effects":[],"prohibited_effects":PROHIBITED_EFFECTS,"plan_status":status,"reasons":[why],"blocked_reasons":[why] if status=="blocked" else []};f=_hash(b);return {**b,"dispatch_plan_id":"capability-dry-run-dispatch-plan-"+f[:24],"dispatch_plan_fingerprint":f}
