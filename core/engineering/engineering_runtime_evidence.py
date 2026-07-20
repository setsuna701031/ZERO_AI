from __future__ import annotations
from .engineering_runtime_orchestrator_common import *
def build_engineering_runtime_evidence(request,session,checkpoints,result,verification,components):
    return artifact("runtime_evidence",{"request_id":request.get("request_id"),"session_id":session.get("session_id"),"workspace_id":request.get("workspace_id"),"schema_ids":sorted({x.get("schema") for x in components.values() if isinstance(x,dict) and x.get("schema")}),"artifact_references":[ref(x) for x in components.values() if isinstance(x,dict)],"phase_sequence":[x.get("phase") for x in checkpoints],"checkpoint_ids":[x.get("checkpoint_id") for x in checkpoints],"status_codes":[result.get("status"),verification.get("status")],"invariant_codes":verification.get("invariant_codes",[])},"evidence_id")
