from __future__ import annotations
from copy import deepcopy
from typing import Any,Mapping
from core.runtime.runtime_capability_execution_session_admission import _identity,_safe
CAPABILITY_CONTROLLED_EXECUTION_OUTCOME_SCHEMA="zero.runtime.capability_controlled_execution_outcome.v1"
CONTROLLED_EXECUTION_OUTCOME_STATUSES=frozenset({"completed","not_completed","blocked","failed","invalid"})
OBSERVED_EXECUTION_STATUSES=frozenset({"completed","not_completed","blocked","failed"})
def build_capability_controlled_execution_outcome(request:Any,*,observed_status:Any,evidence_references:Any=None,result_summary:Any=None,failure_or_blocked_reasons:Any=None)->dict[str,Any]:
    u=deepcopy(dict(request)) if isinstance(request,Mapping) else {};errors=[]
    try:evidence=_safe([] if evidence_references is None else evidence_references);summary=_safe({} if result_summary is None else result_summary);reasons=_safe([] if failure_or_blocked_reasons is None else failure_or_blocked_reasons)
    except (TypeError,ValueError):evidence=[];summary={};reasons=[];errors.append("non_json_safe_outcome")
    refs_ok=isinstance(evidence,list) and all(isinstance(x,str) and x and "\n" not in x and "\r" not in x for x in evidence)
    if not isinstance(request,Mapping) or observed_status not in OBSERVED_EXECUTION_STATUSES:status="invalid";errors.append("malformed_outcome")
    elif errors or not refs_ok:status="invalid";errors.append("malformed_evidence_reference");evidence=[]
    elif u.get("status")!="accepted":status="blocked";errors.append("request_not_accepted")
    else:status=observed_status
    base={"schema":CAPABILITY_CONTROLLED_EXECUTION_OUTCOME_SCHEMA,"status":status,"request_id":u.get("request_id","") if isinstance(u.get("request_id"),str) else "","request_fingerprint":u.get("fingerprint","") if isinstance(u.get("fingerprint"),str) else "","authority_id":u.get("authority_id","") if isinstance(u.get("authority_id"),str) else "","authority_fingerprint":u.get("authority_fingerprint","") if isinstance(u.get("authority_fingerprint"),str) else "","observed_status":observed_status if isinstance(observed_status,str) else "","evidence_references":evidence,"result_summary":summary,"failure_or_blocked_reasons":sorted(set(reasons+errors)) if isinstance(reasons,list) and all(isinstance(x,str) for x in reasons) else sorted(set(errors+["invalid_reasons"]))}
    return _identity(base,"outcome_id","capability-controlled-execution-outcome-")
record_capability_controlled_execution_outcome=build_capability_controlled_execution_outcome
__all__=["CAPABILITY_CONTROLLED_EXECUTION_OUTCOME_SCHEMA","CONTROLLED_EXECUTION_OUTCOME_STATUSES","OBSERVED_EXECUTION_STATUSES","build_capability_controlled_execution_outcome","record_capability_controlled_execution_outcome"]
