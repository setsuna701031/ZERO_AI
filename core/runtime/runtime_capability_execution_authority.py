from __future__ import annotations
from copy import deepcopy
from typing import Any,Mapping
from core.runtime.runtime_capability_execution_session_admission import _identity,_safe
CAPABILITY_EXECUTION_AUTHORITY_SCHEMA="zero.runtime.capability_execution_authority.v1"
EXECUTION_AUTHORITY_STATUSES=frozenset({"authorized","not_authorized","blocked","invalid"})
SAFE_OPERATION_CLASSES=frozenset({"inspect","observe","verify","describe"})
def issue_capability_execution_authority(session_admission:Any,*,issued_scope:Any=None,authority_constraints:Any=None,issued_at:Any=None,expires_at:Any=None)->dict[str,Any]:
    u=deepcopy(dict(session_admission)) if isinstance(session_admission,Mapping) else {};errors=[]
    try:scope=_safe({} if issued_scope is None else issued_scope)
    except (TypeError,ValueError):scope={};errors.append("invalid_scope")
    defaults={"maximum_request_count":1,"allowed_operation_classes":sorted(SAFE_OPERATION_CLASSES),"target_boundary":scope,"mutation_permission":False,"external_process_permission":False,"network_permission":False,"model_invocation_permission":False}
    try:c={**defaults,**({} if authority_constraints is None else _safe(authority_constraints))}
    except (TypeError,ValueError):c=defaults;errors.append("invalid_constraints")
    forbidden=any(c.get(n) is not False for n in ("mutation_permission","external_process_permission","network_permission","model_invocation_permission"))
    allowed=c.get("allowed_operation_classes");bounded=isinstance(allowed,list) and bool(allowed) and set(allowed)<=SAFE_OPERATION_CLASSES and isinstance(c.get("maximum_request_count"),int) and not isinstance(c.get("maximum_request_count"),bool) and c["maximum_request_count"]>0
    if not isinstance(session_admission,Mapping):status="invalid";reasons=["malformed_session_admission"]
    elif u.get("status")!="admitted":status="not_authorized";reasons=["session_not_admitted"]
    elif errors:status="invalid";reasons=errors
    elif forbidden or not bounded:status="blocked";reasons=["authority_constraints_not_bounded"]
    else:status="authorized";reasons=["bounded_authority_issued"]
    base={"schema":CAPABILITY_EXECUTION_AUTHORITY_SCHEMA,"status":status,"session_admission_id":u.get("session_admission_id","") if isinstance(u.get("session_admission_id"),str) else "","session_admission_fingerprint":u.get("fingerprint","") if isinstance(u.get("fingerprint"),str) else "","issued_scope":scope,"authority_constraints":c,"issued_at":issued_at if isinstance(issued_at,str) else "","expires_at":expires_at if isinstance(expires_at,str) else "","denied_reasons":[] if status=="authorized" else sorted(set(reasons)),"blocked_reasons":sorted(set(reasons)) if status=="blocked" else []}
    return _identity(base,"authority_id","capability-execution-authority-")
build_capability_execution_authority=issue_capability_execution_authority
__all__=["CAPABILITY_EXECUTION_AUTHORITY_SCHEMA","EXECUTION_AUTHORITY_STATUSES","SAFE_OPERATION_CLASSES","issue_capability_execution_authority","build_capability_execution_authority"]
