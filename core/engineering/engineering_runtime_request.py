from __future__ import annotations
from .engineering_runtime_orchestrator_common import *

def build_engineering_runtime_request(payload:Mapping[str,Any])->dict[str,Any]:
    p=dict(payload); rs=prohibited(p); mode=p.get("requested_orchestration_mode","preview")
    if mode not in MODES: rs.append("mode_invalid")
    for k in ("request_id","workspace_id","workspace_root_fingerprint"):
        if not isinstance(p.get(k),str) or not p[k].strip() or len(p[k])>256: rs.append(k+"_invalid")
    if p.get("automatic_approval") or p.get("automatic_authorization"): rs.append("automatic_authority_forbidden")
    p.setdefault("execution_requested",False); p.setdefault("explicit_human_approval_required",True); p.setdefault("explicit_human_authorization_required",True); p.setdefault("session_sequence",0)
    p["requested_orchestration_mode"]=mode; p["status"]="valid" if not rs else "invalid"; p["reason_codes"]=reasons(rs)
    return artifact("runtime_request",p,"runtime_request_artifact_id")

validate_engineering_runtime_request=lambda v: validate_artifact(v,SCHEMAS["runtime_request"])+([] if v.get("status")=="valid" else ["request_not_valid"])
