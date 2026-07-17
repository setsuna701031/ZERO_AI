from __future__ import annotations
from copy import deepcopy
from typing import Any,Mapping
from core.runtime.runtime_capability_execution_session_admission import _identity
CAPABILITY_EXECUTION_VERIFICATION_CLOSURE_SCHEMA="zero.runtime.capability_execution_verification_closure.v1"
EXECUTION_VERIFICATION_CLOSURE_STATUSES=frozenset({"verified_closed","not_verified","blocked","failed","invalid"})
def close_capability_execution_verification(session_admission:Any,authority:Any,request:Any,outcome:Any)->dict[str,Any]:
    values=[deepcopy(dict(x)) if isinstance(x,Mapping) else {} for x in (session_admission,authority,request,outcome)];a,h,r,o=values;checks=[];reasons=[]
    malformed=not all(isinstance(x,Mapping) for x in (session_admission,authority,request,outcome))
    pairs=((h,"session_admission",a,"session_admission"),(r,"authority",h,"authority"),(o,"request",r,"request"),(o,"authority",h,"authority"))
    for child,stem,parent,pstem in pairs:
        ok=child.get(stem+"_id")==parent.get(pstem+"_id") and child.get(stem+"_fingerprint")==parent.get("fingerprint")
        checks.append({"link":stem,"valid":ok})
        if not ok:reasons.append(stem+"_linkage_mismatch")
    refs=o.get("evidence_references");evidence_ok=isinstance(refs,list) and all(isinstance(x,str) and x and "\n" not in x and "\r" not in x for x in refs)
    if malformed:status="invalid";reasons.append("malformed_execution_chain")
    elif reasons or not evidence_ok:status="invalid";reasons.append("chain_validation_failed" if reasons else "evidence_reference_validation_failed")
    elif "blocked" in {a.get("status"),h.get("status"),r.get("status"),o.get("status")}:status="blocked";reasons.append("execution_chain_blocked")
    elif o.get("status")=="failed":status="failed";reasons.append("controlled_outcome_failed")
    elif (a.get("status"),h.get("status"),r.get("status"),o.get("status"))==("admitted","authorized","accepted","completed"):status="verified_closed";reasons.append("execution_chain_verified_closed")
    else:status="not_verified";reasons.append("execution_chain_not_complete")
    base={"schema":CAPABILITY_EXECUTION_VERIFICATION_CLOSURE_SCHEMA,"status":status,"session_admission_id":a.get("session_admission_id","") if isinstance(a.get("session_admission_id"),str) else "","session_admission_fingerprint":a.get("fingerprint","") if isinstance(a.get("fingerprint"),str) else "","authority_id":h.get("authority_id","") if isinstance(h.get("authority_id"),str) else "","authority_fingerprint":h.get("fingerprint","") if isinstance(h.get("fingerprint"),str) else "","request_id":r.get("request_id","") if isinstance(r.get("request_id"),str) else "","request_fingerprint":r.get("fingerprint","") if isinstance(r.get("fingerprint"),str) else "","outcome_id":o.get("outcome_id","") if isinstance(o.get("outcome_id"),str) else "","outcome_fingerprint":o.get("fingerprint","") if isinstance(o.get("fingerprint"),str) else "","chain_validation_results":checks,"evidence_reference_validation_results":{"valid":evidence_ok,"count":len(refs) if isinstance(refs,list) else 0},"closed":status=="verified_closed","reasons":sorted(set(reasons))}
    return _identity(base,"closure_id","capability-execution-verification-closure-")
build_capability_execution_verification_closure=close_capability_execution_verification
__all__=["CAPABILITY_EXECUTION_VERIFICATION_CLOSURE_SCHEMA","EXECUTION_VERIFICATION_CLOSURE_STATUSES","close_capability_execution_verification","build_capability_execution_verification_closure"]
