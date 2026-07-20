from __future__ import annotations
from .engineering_runtime_orchestrator_common import *
def coordinate_engineering_runtime_execution(request,session,phase,transaction,executor_handoff,workspace_root=None,cli_execute=False,execute_confirmed=False,completed_execution=None):
    rs=[]
    if completed_execution and completed_execution.get("status") in ("succeeded","duplicate_suppressed"): status="duplicate_suppressed"
    else:
        if request.get("execution_requested") is not True: rs.append("execution_not_requested")
        if cli_execute is not True: rs.append("cli_execute_required")
        if execute_confirmed is not True: rs.append("execute_confirmation_required")
        if phase.get("phase")!="execution_ready": rs.append("phase_not_execution_ready")
        if transaction.get("status")!="ready": rs.append("transaction_not_ready")
        if not workspace_root: rs.append("trusted_workspace_root_required")
        if not isinstance(executor_handoff,dict): rs.append("executor_handoff_required")
        status="rejected" if rs else "ready"
    result=None
    if status=="ready":
        from .engineering_governed_workspace_mutation_executor import execute_pipeline
        result=execute_pipeline(executor_handoff,workspace_root,execute_confirmed=True)
        upstream=(result.get("result") or {}).get("status")
        status=upstream if upstream in ("succeeded","duplicate_suppressed","failed_rolled_back","recovery_required") else "invalid"
    return artifact("runtime_execution_coordination",{"session_id":session.get("session_id"),"status":status,"executor_handoff_reference":ref(executor_handoff) if isinstance(executor_handoff,dict) else {},"upstream_result_reference":ref(result.get("result",{})) if result else {},"reason_codes":reasons(rs)},"execution_coordination_id")
