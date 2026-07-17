from __future__ import annotations
from copy import deepcopy
from typing import Any,Mapping
from core.runtime.runtime_capability_execution_session_admission import _identity,_safe
from core.runtime.runtime_capability_execution_authority import SAFE_OPERATION_CLASSES
CAPABILITY_BOUNDED_EXECUTION_REQUEST_SCHEMA="zero.runtime.capability_bounded_execution_request.v1"
BOUNDED_EXECUTION_REQUEST_STATUSES=frozenset({"accepted","not_accepted","blocked","invalid"})
FORBIDDEN_OPERATION_CLASSES=frozenset({"execute","mutate","write","delete","run_process","invoke_model","network_request","install","deploy"})
def build_capability_bounded_execution_request(authority:Any,*,operation_class:Any,target_descriptor:Any,bounded_parameters:Any=None,request_ordinal:Any=1)->dict[str,Any]:
    u=deepcopy(dict(authority)) if isinstance(authority,Mapping) else {};errors=[]
    try:target=_safe(target_descriptor);params=_safe({} if bounded_parameters is None else bounded_parameters)
    except (TypeError,ValueError):target={};params={};errors.append("non_json_safe_request")
    c=u.get("authority_constraints",{}) if isinstance(u.get("authority_constraints"),Mapping) else {};allowed=c.get("allowed_operation_classes",[]);limit=c.get("maximum_request_count",0)
    if not isinstance(authority,Mapping) or not isinstance(operation_class,str) or not isinstance(request_ordinal,int) or isinstance(request_ordinal,bool):status="invalid";reasons=["malformed_request"]
    elif errors:status="invalid";reasons=errors
    elif u.get("status")!="authorized":status="not_accepted";reasons=["authority_not_authorized"]
    elif operation_class in FORBIDDEN_OPERATION_CLASSES or operation_class not in SAFE_OPERATION_CLASSES or operation_class not in allowed:status="blocked";reasons=["operation_class_not_allowed"]
    elif request_ordinal<1 or request_ordinal>limit:status="blocked";reasons=["request_count_exceeded"]
    elif c.get("target_boundary") not in ({},None) and target!=c.get("target_boundary"):status="blocked";reasons=["target_outside_authority_scope"]
    else:status="accepted";reasons=["bounded_request_accepted"]
    base={"schema":CAPABILITY_BOUNDED_EXECUTION_REQUEST_SCHEMA,"status":status,"authority_id":u.get("authority_id","") if isinstance(u.get("authority_id"),str) else "","authority_fingerprint":u.get("fingerprint","") if isinstance(u.get("fingerprint"),str) else "","operation_class":operation_class if isinstance(operation_class,str) else "","target_descriptor":target,"bounded_parameters":params,"request_ordinal":request_ordinal if isinstance(request_ordinal,int) and not isinstance(request_ordinal,bool) else 0,"acceptance_reasons":sorted(set(reasons)) if status=="accepted" else [],"rejection_reasons":sorted(set(reasons)) if status=="not_accepted" else [],"blocked_reasons":sorted(set(reasons)) if status=="blocked" else []}
    return _identity(base,"request_id","capability-bounded-execution-request-")
create_capability_bounded_execution_request=build_capability_bounded_execution_request
__all__=["CAPABILITY_BOUNDED_EXECUTION_REQUEST_SCHEMA","BOUNDED_EXECUTION_REQUEST_STATUSES","FORBIDDEN_OPERATION_CLASSES","build_capability_bounded_execution_request","create_capability_bounded_execution_request"]
