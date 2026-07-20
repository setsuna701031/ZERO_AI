from __future__ import annotations
from .engineering_runtime_orchestrator_common import *

def _status(artifact, field, expected, reason, rs):
    if not isinstance(artifact,dict) or artifact.get(field)!=expected or not artifact.get("fingerprint"): rs.append(reason)

def _controlled_flow_reasons(request,session,transaction,flow,mutation):
    rs=[]
    approval=flow.get("operator_approval",{}); authorization=flow.get("mutation_authorization",{})
    if mutation and (approval.get("decision") not in ("approved","partially_approved") or approval.get("automated_decision") is not False or not approval.get("operator_id") or not approval.get("fingerprint")): rs.append("operator_approval_not_explicit")
    if mutation and (authorization.get("decision")!="authorized" or authorization.get("automated_decision") is not False or not authorization.get("authorizer_id") or not authorization.get("fingerprint")): rs.append("mutation_authorization_not_explicit")
    _status(flow.get("adapter_admission"),"admission_status","admitted","adapter_not_admitted",rs)
    _status(flow.get("adapter_preparation"),"preparation_status","prepared","adapter_preparation_invalid",rs)
    _status(flow.get("preparation_review"),"review_status","approved","adapter_preparation_review_not_approved",rs)
    _status(flow.get("activation_eligibility"),"eligibility_status","eligible","activation_not_eligible",rs)
    _status(flow.get("activation_authorization"),"authorization_status","authorized","activation_not_authorized",rs)
    token=flow.get("activation_token",{}); verification=flow.get("activation_token_verification",{})
    if token.get("issuance_status")!="issued" or token.get("consumed") is not False or token.get("current_uses")!=0: rs.append("activation_token_invalid_or_consumed")
    _status(verification,"verification_status","verified","activation_token_not_verified",rs)
    _status(flow.get("invocation_handoff"),"eligible_for_concrete_adapter_execution",True,"invocation_not_governed",rs)
    _status(flow.get("environment_admission"),"environment_admission_status","admitted","environment_not_admitted",rs)
    _status(flow.get("resource_budget"),"resource_budget_status","bounded","resource_budget_invalid",rs)
    _status(flow.get("timeout_policy"),"timeout_policy_status","bounded","timeout_policy_invalid",rs)
    _status(flow.get("isolation_policy"),"isolation_policy_status","valid","isolation_policy_invalid",rs)
    _status(flow.get("execution_readiness"),"execution_readiness_status","ready","execution_not_ready",rs)
    capability=flow.get("capability",{}); execution_request=flow.get("execution_request",{})
    from .engineering_runtime_adapter_execution_capability import validate_runtime_adapter_execution_capability
    from .engineering_runtime_adapter_binding_resolution import build_runtime_adapter_binding_resolution,validate_runtime_adapter_binding_resolution
    if not validate_runtime_adapter_execution_capability(capability).valid: rs.append("adapter_descriptor_invalid")
    binding=build_runtime_adapter_binding_resolution(execution_request,capability)
    if not validate_runtime_adapter_binding_resolution(binding).valid or binding.get("binding_status")!="resolved": rs.append("adapter_binding_not_resolved")
    if execution_request.get("execution_session_id") not in (None,session.get("session_id")): rs.append("execution_session_mismatch")
    approved=flow.get("approved_scope"); authorized=flow.get("authorization_scope"); requested=execution_request.get("approved_scope")
    if approved is not None and requested!=approved: rs.append("approved_scope_mismatch")
    if mutation and authorized!=approved: rs.append("authorization_scope_mismatch")
    if transaction.get("status")!="ready": rs.append("transaction_not_ready")
    return reasons(rs),binding

def _execute_read_only(flow,workspace_root,session):
    from .engineering_runtime_workspace_adapter_registry import default_workspace_adapter_registry
    from .engineering_runtime_workspace_root_admission import admit_workspace_root
    from .engineering_runtime_workspace_read_scope import create_read_scope
    from .engineering_runtime_workspace_execution_submission import build_workspace_execution_submission
    from .engineering_runtime_workspace_execution_preflight import build_workspace_execution_preflight
    from .engineering_runtime_workspace_controlled_executor import execute_workspace_adapter
    from .engineering_runtime_workspace_execution_result import build_workspace_execution_result
    from .engineering_runtime_workspace_execution_verification import verify_workspace_execution
    from .engineering_runtime_workspace_execution_evidence import build_workspace_execution_evidence
    from .engineering_runtime_workspace_execution_closure import close_workspace_execution
    cfg=flow.get("workspace_request",{}); reg=default_workspace_adapter_registry(); adm=admit_workspace_root(workspace_root,session.get("workspace_id")); scope=create_read_scope(**cfg.get("read_scope",{}))
    if not adm.get("admitted") or adm.get("workspace_root_fingerprint")!=session.get("workspace_root_fingerprint"):
        return {"blocked_reason":"workspace_identity_mismatch","workspace_admission":dict(adm)}
    handoff=flow.get("executor_handoff",{}); integration=flow.get("integration_closure",{})
    sub=build_workspace_execution_submission(handoff,integration,adm,scope,cfg.get("operation","workspace_exists"),cfg.get("relative_path",""),cfg.get("operation_parameters",{}),session.get("session_id"))
    pre,_=build_workspace_execution_preflight(sub,reg,adm,scope); controlled=execute_workspace_adapter(sub,pre,reg,adm,scope); result=build_workspace_execution_result(sub,pre,controlled); verification=verify_workspace_execution(sub,pre,controlled,result); evidence=build_workspace_execution_evidence(sub,pre,controlled,result,verification); closure=close_workspace_execution(result,verification,evidence)
    return {"result":result,"verification":verification,"evidence":evidence,"closure":closure}

def coordinate_engineering_runtime_execution(request,session,phase,transaction,executor_handoff,workspace_root=None,cli_execute=False,execute_confirmed=False,completed_execution=None,controlled_flow=None):
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
    result=None; binding={}; flow=controlled_flow if isinstance(controlled_flow,dict) else None
    mutation=not (flow and flow.get("execution_class")=="read_only")
    if status=="ready" and flow:
        flow_rs,binding=_controlled_flow_reasons(request,session,transaction,flow,mutation); rs.extend(flow_rs)
        if mutation and flow.get("capability",{}).get("adapter_id")=="zero.engineering.read_only_workspace": rs.append("read_only_adapter_mutation_forbidden")
        if mutation and flow.get("capability",{}).get("adapter_id")!="zero.engineering.governed_workspace_mutation": rs.append("unknown_mutation_adapter")
        if not mutation and flow.get("capability",{}).get("adapter_id")!="zero.engineering.read_only_workspace": rs.append("mutation_adapter_read_only_path_forbidden")
        if rs: status="rejected"
    if status=="ready":
        if flow and not mutation:
            result=_execute_read_only(flow,workspace_root,session)
            if result.get("blocked_reason"): rs.append(result["blocked_reason"]); status="rejected"
            else: upstream=(result.get("result") or {}).get("result_status"); status="succeeded" if upstream=="succeeded" else "invalid"
        else:
            from .engineering_governed_workspace_mutation_executor import execute_pipeline
            result=execute_pipeline(executor_handoff,workspace_root,execute_confirmed=True); upstream=(result.get("result") or {}).get("status"); status=upstream if upstream in ("succeeded","duplicate_suppressed","failed_rolled_back","recovery_required") else "invalid"
    return artifact("runtime_execution_coordination",{"session_id":session.get("session_id"),"status":status,"binding_reference":ref(binding) if binding else {},"executor_handoff_reference":ref(executor_handoff) if isinstance(executor_handoff,dict) else {},"upstream_result_reference":ref(result.get("result",{})) if result else {},"upstream_verification_reference":ref(result.get("verification",{})) if result else {},"upstream_evidence_reference":ref(result.get("evidence",{})) if result else {},"upstream_closure_reference":ref(result.get("closure",{})) if result else {},"reason_codes":reasons(rs)},"execution_coordination_id")
