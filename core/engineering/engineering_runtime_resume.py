from __future__ import annotations
from .engineering_runtime_orchestrator_common import *
from .engineering_runtime_checkpoint import validate_checkpoint_chain
def determine_resume(store,workspace_identity,artifacts=()):
    req=store.get("request.json",{}); ses=store.get("session.json",{}); phase=store.get("phase.json",{}); cps=store.get("checkpoints.json",[]); rs=[]
    rs+=validate_artifact(req,SCHEMAS["runtime_request"]); rs+=validate_artifact(ses,SCHEMAS["runtime_session"]); rs+=validate_artifact(phase,SCHEMAS["runtime_phase"]); rs+=validate_checkpoint_chain(cps)
    if workspace_identity.get("workspace_id")!=ses.get("workspace_id") or workspace_identity.get("workspace_root_fingerprint")!=ses.get("workspace_root_fingerprint"): rs.append("workspace_identity_drift")
    if ses.get("terminal") or phase.get("phase") in ("execution_terminal","end_to_end_verified","closed"): return {"status":"duplicate_suppressed","session_id":ses.get("session_id"),"next_phase":None,"reason_codes":["completed_execution_replay_suppressed"]}
    try: next_phase=PHASES[PHASES.index(phase.get("phase"))+1]
    except (ValueError,IndexError): rs.append("ambiguous_phase"); next_phase=None
    if phase.get("phase")=="awaiting_operator_approval" and not artifacts: rs.append("operator_approval_required")
    if phase.get("phase")=="awaiting_mutation_authorization" and not artifacts: rs.append("mutation_authorization_required")
    return {"status":"resumable" if not rs else "invalid","session_id":ses.get("session_id"),"next_phase":next_phase,"reason_codes":reasons(rs)}
