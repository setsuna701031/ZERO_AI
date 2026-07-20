from __future__ import annotations
from .engineering_runtime_orchestrator_common import *
def build_engineering_runtime_result(request,session,phase,checkpoints,components):
    mode=request.get("requested_orchestration_mode"); statuses=[x.get("status") for x in components.values() if isinstance(x,dict)]
    if "recovery_required" in statuses: status="recovery_required"
    elif "failed_rolled_back" in statuses: status="failed_rolled_back"
    elif "duplicate_suppressed" in statuses: status="duplicate_suppressed"
    elif "succeeded" in statuses: status="succeeded"
    elif "awaiting_input" in statuses: status="awaiting_operator_approval" if "operator_pause" in components and components["operator_pause"].get("status")=="awaiting_input" else "awaiting_mutation_authorization"
    else: status={"preview":"previewed","analyze":"analyzed","propose":"proposal_ready","prepare":"mutation_prepared","authorize":"transaction_ready"}.get(mode,"invalid")
    return artifact("runtime_result",{"request_reference":ref(request),"session_reference":ref(session),"final_phase":phase.get("phase"),"checkpoint_ids":[x.get("checkpoint_id") for x in checkpoints],"component_references":{k:ref(v) for k,v in components.items() if isinstance(v,dict)},"workspace_id":request.get("workspace_id"),"scope_constraints":request.get("scope_constraints",[]),"authority_constraints":request.get("authority_constraints",[]),"status":status},"result_id")
