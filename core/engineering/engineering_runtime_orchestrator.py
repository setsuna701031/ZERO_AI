from __future__ import annotations
from .engineering_runtime_request import build_engineering_runtime_request
from .engineering_runtime_session import build_engineering_runtime_session
from .engineering_runtime_phase import build_engineering_runtime_phase,transition_phase
from .engineering_runtime_admission import admit_engineering_runtime
from .engineering_runtime_analysis_coordination import coordinate_engineering_runtime_analysis
from .engineering_runtime_proposal_coordination import coordinate_engineering_runtime_proposal
from .engineering_runtime_operator_pause import build_engineering_runtime_operator_pause
from .engineering_runtime_preparation_coordination import coordinate_engineering_runtime_preparation
from .engineering_runtime_authorization_pause import build_engineering_runtime_authorization_pause
from .engineering_runtime_transaction_coordination import coordinate_engineering_runtime_transaction
from .engineering_runtime_execution_coordination import coordinate_engineering_runtime_execution
from .engineering_runtime_checkpoint import build_engineering_runtime_checkpoint
from .engineering_runtime_result import build_engineering_runtime_result
from .engineering_runtime_verification import verify_engineering_runtime
from .engineering_runtime_evidence import build_engineering_runtime_evidence
from .engineering_runtime_closure import close_engineering_runtime
from .engineering_runtime_capability_admission import build_runtime_capability_admission
from .engineering_runtime_adapter_invocation_pipeline import orchestrate_runtime_adapter_invocation
from .engineering_runtime_formal_persistence import run_formal_persistence_mainline

def orchestrate_engineering_runtime(payload,workspace_identity=None,workspace_root=None,cli_execute=False,execute_confirmed=False,session_root=None):
    request=build_engineering_runtime_request(payload.get("request",payload)); session=build_engineering_runtime_session(request); phase=build_engineering_runtime_phase(session["session_id"])
    components={}; checkpoints=[build_engineering_runtime_checkpoint(session,phase)]
    identity=workspace_identity or {"workspace_id":request.get("workspace_id"),"workspace_root_fingerprint":request.get("workspace_root_fingerprint")}
    capability_keys=("capability_registry","requested_capability_id","requested_operation","requested_adapter_id","requested_adapter_fingerprint")
    capability_input_present=any(key in payload for key in capability_keys)
    capability_admission=None
    if capability_input_present:
        capability_admission=build_runtime_capability_admission(session=session,request=request,
            capability_registry=payload.get("capability_registry"),requested_capability_id=payload.get("requested_capability_id"),
            requested_operation=payload.get("requested_operation"),requested_adapter_id=payload.get("requested_adapter_id"),
            requested_adapter_fingerprint=payload.get("requested_adapter_fingerprint"),prior_admission=payload.get("prior_capability_admission"))
        components["capability_admission"]=capability_admission
        checkpoints.append(build_engineering_runtime_checkpoint(session,phase,checkpoints[-1],[capability_admission]))
    admission=admit_engineering_runtime(request,session,identity,payload.get("prior_session"),capability_admission); components["admission"]=admission
    invocation_input=payload.get("adapter_invocation")
    invocation_outcome=None
    if invocation_input is not None:
        invocation=orchestrate_runtime_adapter_invocation(invocation_input,
            {"session_id":session.get("session_id"),"request_fingerprint":request.get("fingerprint"),"workspace_id":request.get("workspace_id")},
            capability_admission)
        invocation_outcome={"status":invocation["status"],"reason_codes":invocation["reason_codes"]}
        for name, artifact_value in invocation.get("artifacts",{}).items():
            components[name]=artifact_value
    invocation_admitted=invocation_input is None or invocation_outcome.get("status")=="completed_without_mutation"
    if admission["status"]=="admitted" and invocation_admitted: phase=transition_phase(phase,"session_admitted"); checkpoints.append(build_engineering_runtime_checkpoint(session,phase,checkpoints[-1],[admission]))
    mode=request.get("requested_orchestration_mode")
    if admission["status"]=="admitted" and invocation_admitted and mode!="inspect":
        analysis=coordinate_engineering_runtime_analysis(request,payload.get("analysis_artifacts",[])); components["analysis"]=analysis
        if analysis["status"]=="coordinated": phase=transition_phase(phase,"analysis_coordinated"); checkpoints.append(build_engineering_runtime_checkpoint(session,phase,checkpoints[-1],[analysis]))
        if mode in ("propose","prepare","authorize","execute") and analysis["status"]=="coordinated":
            proposal=coordinate_engineering_runtime_proposal(analysis,payload.get("proposal_artifacts",[])); components["proposal"]=proposal
            if proposal["status"]=="proposed": phase=transition_phase(phase,"proposal_coordinated"); checkpoints.append(build_engineering_runtime_checkpoint(session,phase,checkpoints[-1],[proposal]))
            if proposal["status"]=="proposed":
                phase=transition_phase(phase,"awaiting_operator_approval"); pause=build_engineering_runtime_operator_pause(proposal,payload.get("approval_artifacts",[])); components["operator_pause"]=pause; checkpoints.append(build_engineering_runtime_checkpoint(session,phase,checkpoints[-1],[pause],[pause.get("required_input")]))
                if mode in ("prepare","authorize","execute") and pause["status"]=="satisfied":
                    phase=transition_phase(phase,"operator_approval_verified"); prep=coordinate_engineering_runtime_preparation(pause,payload.get("preparation_artifacts",[])); components["preparation"]=prep; checkpoints.append(build_engineering_runtime_checkpoint(session,phase,checkpoints[-1],[pause]))
                    if prep["status"]=="coordinated": phase=transition_phase(phase,"preparation_coordinated"); checkpoints.append(build_engineering_runtime_checkpoint(session,phase,checkpoints[-1],[prep])); phase=transition_phase(phase,"awaiting_mutation_authorization"); auth=build_engineering_runtime_authorization_pause(prep,payload.get("authorization_artifacts",[])); components["authorization_pause"]=auth; checkpoints.append(build_engineering_runtime_checkpoint(session,phase,checkpoints[-1],[auth],[auth.get("required_input")]))
                    if mode in ("authorize","execute") and components.get("authorization_pause",{}).get("status")=="satisfied":
                        phase=transition_phase(phase,"mutation_authorization_verified"); tx=coordinate_engineering_runtime_transaction(components["authorization_pause"],payload.get("transaction_artifacts",[])); components["transaction"]=tx; checkpoints.append(build_engineering_runtime_checkpoint(session,phase,checkpoints[-1],[components["authorization_pause"]]))
                        if tx["status"]=="ready": phase=transition_phase(phase,"transaction_coordinated"); checkpoints.append(build_engineering_runtime_checkpoint(session,phase,checkpoints[-1],[tx])); phase=transition_phase(phase,"execution_ready"); checkpoints.append(build_engineering_runtime_checkpoint(session,phase,checkpoints[-1],[tx],execution_mode="enabled" if mode=="execute" else "disabled"))
                        if mode=="execute" and tx["status"]=="ready":
                            execution=coordinate_engineering_runtime_execution(request,session,phase,tx,payload.get("executor_handoff"),workspace_root,cli_execute,execute_confirmed,payload.get("completed_execution"),payload.get("controlled_adapter_flow")); components["execution"]=execution
                            if execution["status"] not in ("ready","rejected","invalid"):
                                phase=transition_phase(phase,"execution_started"); checkpoints.append(build_engineering_runtime_checkpoint(session,phase,checkpoints[-1],[execution],execution_mode="enabled"))
                                phase=transition_phase(phase,"execution_terminal"); checkpoints.append(build_engineering_runtime_checkpoint(session,phase,checkpoints[-1],[execution],execution_mode="enabled",result_status=execution["status"]))
    result=build_engineering_runtime_result(request,session,phase,checkpoints,components,invocation_outcome); verification=verify_engineering_runtime(request,session,phase,checkpoints,result); evidence=build_engineering_runtime_evidence(request,session,checkpoints,result,verification,components); closure=close_engineering_runtime(result,verification,evidence)
    formal=None
    if session_root and request.get("status")=="valid" and admission.get("status")=="admitted" and request.get("requested_orchestration_mode") in ("analyze","propose","prepare","pipeline"):
        formal=run_formal_persistence_mainline(payload=payload,request=request,session=session,session_root=session_root,workspace_root=workspace_root,mode=request.get("requested_orchestration_mode"))
        components["formal_persistence"]=formal
    response={"request":request,"session":session,"phase":phase,"checkpoints":checkpoints,**components,"result":result,"verification":verification,"evidence":evidence,"closure":closure}
    if formal:
        response.update({
            "session_root": formal.get("session_root"),
            "session_id": formal.get("session_id"),
            "current_phase": formal.get("current_phase"),
            "persisted_artifacts": formal.get("persisted_artifacts", []),
            "artifact_index": formal.get("artifact_index", {}),
            "required_operator_input": formal.get("required_operator_input", {}),
            "execution_enabled": formal.get("execution_enabled", False),
            "executor_invoked": formal.get("executor_invoked", False),
            "workspace_mutation_performed": formal.get("workspace_mutation_performed", False),
            "git_mutation_performed": formal.get("git_mutation_performed", False),
        })
    return response
