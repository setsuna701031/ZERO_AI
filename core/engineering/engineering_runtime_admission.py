from __future__ import annotations
from .engineering_runtime_orchestrator_common import *
from .engineering_runtime_request import validate_engineering_runtime_request
def admit_engineering_runtime(request,session,workspace_identity,prior_session=None,capability_admission=None):
    rs=validate_engineering_runtime_request(request)
    if workspace_identity.get("workspace_id")!=request.get("workspace_id") or workspace_identity.get("workspace_root_fingerprint")!=request.get("workspace_root_fingerprint"): rs.append("workspace_identity_mismatch")
    if prior_session and prior_session.get("terminal"): rs.append("terminal_session_replay")
    if request.get("requested_orchestration_mode")=="execute" and request.get("execution_requested") is not True: rs.append("execution_not_requested")
    if capability_admission is not None and capability_admission.get("status")!="admitted": rs.append("capability_admission_not_admitted")
    return artifact("runtime_admission",{"session_id":session.get("session_id"),"request_fingerprint":request.get("fingerprint"),"status":"admitted" if not rs else "not_admitted","reason_codes":reasons(rs),"human_approval_inferred":False,"human_authorization_inferred":False},"admission_id")
