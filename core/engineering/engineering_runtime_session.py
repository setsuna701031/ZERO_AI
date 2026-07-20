from __future__ import annotations
from .engineering_runtime_orchestrator_common import *
def build_engineering_runtime_session(request:Mapping[str,Any])->dict[str,Any]:
    identity={k:request.get(k) for k in ("request_id","workspace_id","workspace_root_fingerprint","session_sequence")}
    sid="engineering-session-"+fingerprint(identity)[:32]
    return artifact("runtime_session",{"session_id":sid,"request_id":request.get("request_id"),"request_fingerprint":request.get("fingerprint"),"workspace_id":request.get("workspace_id"),"workspace_root_fingerprint":request.get("workspace_root_fingerprint"),"status":"created","terminal":False},"session_artifact_id")
def transition_session(session:Mapping[str,Any],status:str)->dict[str,Any]:
    if session.get("terminal") or session.get("status") in TERMINAL_STATUSES: return artifact("runtime_session",{**dict(session),"status":"invalid","terminal":True,"reason_codes":["terminal_session_immutable"]},"session_artifact_id")
    return artifact("runtime_session",{k:v for k,v in session.items() if k not in ("schema","fingerprint","session_artifact_id")}|{"status":status,"terminal":status in TERMINAL_STATUSES},"session_artifact_id")
