from __future__ import annotations
from .engineering_runtime_orchestrator_common import *
from .engineering_runtime_checkpoint import validate_checkpoint_chain
def verify_engineering_runtime(request,session,phase,checkpoints,result):
    rs=validate_artifact(request,SCHEMAS["runtime_request"])+validate_artifact(session,SCHEMAS["runtime_session"])+validate_artifact(phase,SCHEMAS["runtime_phase"])+validate_artifact(result,SCHEMAS["runtime_result"])+validate_checkpoint_chain(checkpoints)
    if session.get("request_fingerprint")!=request.get("fingerprint"): rs.append("request_session_linkage_mismatch")
    if session.get("workspace_id")!=request.get("workspace_id"): rs.append("workspace_identity_mismatch")
    return artifact("runtime_verification",{"session_id":session.get("session_id"),"result_id":result.get("result_id"),"status":"verified" if not rs else "not_verified","reason_codes":reasons(rs),"invariant_codes":["NO_AUTO_APPROVAL","NO_AUTO_AUTHORIZATION","NO_SCOPE_EXPANSION","NO_AUTHORITY_EXPANSION","NO_DUPLICATE_EXECUTION","NO_FORBIDDEN_INVOCATION"]},"verification_id")
