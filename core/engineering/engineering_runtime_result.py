from __future__ import annotations
from .engineering_runtime_orchestrator_common import *
def build_engineering_runtime_result(request,session,phase,checkpoints,components,invocation_outcome=None):
    mode=request.get("requested_orchestration_mode"); statuses=[x.get("status") for x in components.values() if isinstance(x,dict)]
    invocation_status=(invocation_outcome or {}).get("status")
    if invocation_status in ("invalid","blocked","not_closed"): status="invalid"
    elif invocation_status=="completed_without_mutation": status="completed_without_mutation"
    elif "recovery_required" in statuses: status="recovery_required"
    elif "failed_rolled_back" in statuses: status="failed_rolled_back"
    elif "duplicate_suppressed" in statuses: status="duplicate_suppressed"
    elif "succeeded" in statuses: status="succeeded"
    elif "not_admitted" in statuses: status="rejected"
    elif "awaiting_input" in statuses: status="awaiting_operator_approval" if "operator_pause" in components and components["operator_pause"].get("status")=="awaiting_input" else "awaiting_mutation_authorization"
    else: status={"preview":"previewed","analyze":"analyzed","propose":"proposal_ready","prepare":"mutation_prepared","authorize":"transaction_ready"}.get(mode,"invalid")
    body={"request_reference":ref(request),"session_reference":ref(session),"final_phase":phase.get("phase"),"checkpoint_ids":[x.get("checkpoint_id") for x in checkpoints],"component_references":{k:ref(v) for k,v in components.items() if isinstance(v,dict)},"workspace_id":request.get("workspace_id"),"scope_constraints":request.get("scope_constraints",[]),"authority_constraints":request.get("authority_constraints",[]),"status":status}
    if invocation_outcome is not None: body["reason_codes"]=sorted(set(invocation_outcome.get("reason_codes",[])))
    return artifact("runtime_result",body,"result_id")
