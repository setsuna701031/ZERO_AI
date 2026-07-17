from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Mapping

from core.runtime.runtime_operator_session import INPUT_CONTRACT, fingerprint, load_runtime_session, time_text, parse_time

CONTRACT = "zero.runtime.mission_execution_approval_flow.v1"
PLAN_CONTRACT = "zero.runtime.natural_mission_execution_plan.v1"
APPROVAL_CONTRACT = "zero.runtime.natural_mission_execution_approval.v1"


def _load_artifact(path: Any) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8-sig")); claimed = value.get("artifact_fingerprint"); unsigned = deepcopy(value); unsigned.pop("artifact_fingerprint", None)
    if claimed != fingerprint(unsigned): raise ValueError("bootstrap_artifact_fingerprint_mismatch")
    return value


def _save(value: Mapping[str, Any], path: Any, fingerprint_field: str) -> dict[str, Any]:
    result = deepcopy(dict(value)); result.pop(fingerprint_field, None); result[fingerprint_field] = fingerprint(result); destination = Path(path); destination.parent.mkdir(parents=True, exist_ok=True); temporary = destination.with_name(f".{destination.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle: handle.write(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)+"\n"); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, destination); return result


def _publish(artifact: Mapping[str,Any], topic: str, payload: Mapping[str,Any], key: str, now: Any) -> None:
    try:
        from core.runtime.runtime_mission_session import load_mission_session_state
        from core.runtime.runtime_event_bus import load_event_bus_state,publish,save_event_bus_state
        session=load_mission_session_state(artifact["session_reference"]["path"]);path=Path(session["event_bus_state_path"])
        if not path.exists(): return
        bus=load_event_bus_state(path);bus,_=publish(bus,event_type="mission",topic=topic,source=session["session_id"],payload=payload,idempotency_key=key,correlation_id=artifact["mission_reference"]["mission_id"],now=now);save_event_bus_state(bus,path)
    except (OSError,ValueError,KeyError): return


def create_mission_execution_plan(bootstrap_artifact: Mapping[str, Any], *, now: Any = None) -> dict[str, Any]:
    artifact = deepcopy(dict(bootstrap_artifact)); intents = deepcopy(artifact.get("structured_intents") or []); paths = sorted({str(i.get("path")) for i in intents if i.get("path")}); mutation = any(i.get("operation") in {"create_file", "create_directory"} for i in intents)
    seed = {"bootstrap_id": artifact.get("bootstrap_id"), "mission": (artifact.get("mission_reference") or {}).get("mission_id"), "intents": intents}
    created=time_text(now)
    value = {"contract": PLAN_CONTRACT, "plan_id": f"natural-mission-plan-{fingerprint(seed)[:20]}", "bootstrap_id": artifact.get("bootstrap_id"), "mission_id": (artifact.get("mission_reference") or {}).get("mission_id"), "session_id": (artifact.get("session_reference") or {}).get("session_id"), "mission_fingerprint": artifact.get("mission_fingerprint"), "goal_graph_fingerprint": (artifact.get("graph_reference") or {}).get("graph_fingerprint"), "goal_ids": deepcopy((artifact.get("graph_reference") or {}).get("goal_order") or []), "operations": intents, "target_paths": paths, "workspace_root": artifact.get("workspace_root"), "target_root": artifact.get("target_root"), "effect_summary": "controlled mutation" if mutation else "controlled read-only execution", "risk_classification": "mutation" if mutation else "read_only", "approval_required": mutation, "approval_status": "pending" if mutation else "not_required", "required_approval_scope": paths if mutation else [], "created_at": created, "expires_at": time_text(parse_time(created) + timedelta(hours=1)), "review_reason": None, "approval_reference": None, "admission_reference": None, "plan_status": "waiting_for_operator_approval" if mutation else "ready"}
    value["plan_fingerprint"] = fingerprint(value); return value


def validate_mission_execution_plan(plan: Mapping[str, Any]) -> list[str]:
    value = deepcopy(dict(plan)); reasons=[]; claimed=value.pop("plan_fingerprint",None)
    if value.get("contract") != PLAN_CONTRACT: reasons.append("invalid_mission_execution_plan_contract")
    if claimed != fingerprint(value): reasons.append("mission_execution_plan_fingerprint_mismatch")
    if not value.get("plan_id") or not value.get("mission_id") or not value.get("session_id"): reasons.append("mission_execution_plan_identity_required")
    if any(Path(p).is_absolute() or ".." in Path(p).parts for p in value.get("target_paths") or []): reasons.append("unsafe_approval_scope")
    return reasons


def ensure_pending_execution_plan(artifact_path: Any, *, now: Any = None) -> dict[str, Any]:
    artifact = _load_artifact(artifact_path); plan_path = Path(artifact_path).with_name("execution-plan.json")
    if plan_path.exists():
        plan=json.loads(plan_path.read_text(encoding="utf-8-sig")); reasons=validate_mission_execution_plan(plan)
        if reasons: raise ValueError(";".join(reasons))
    else: plan=create_mission_execution_plan(artifact,now=now); _save(plan,plan_path,"plan_fingerprint")
    return plan


def mission_execution_status(artifact_path: Any, *, now: Any = None) -> dict[str, Any]:
    artifact = _load_artifact(artifact_path)
    plan = ensure_pending_execution_plan(artifact_path, now=now)
    approval_path = Path(artifact_path).with_name("execution-approval.json")
    approval = json.loads(approval_path.read_text(encoding="utf-8-sig")) if approval_path.exists() else {}
    from core.runtime.runtime_mission_model import load_mission
    from core.runtime.runtime_mission_session import load_mission_session_state
    mission = load_mission(artifact["mission_reference"]["path"], check_expiry=False)
    session = load_mission_session_state(artifact["session_reference"]["path"])
    value = {"contract": CONTRACT, "mission_id": mission["mission_id"], "session_id": session["session_id"], "mission_status": mission["mission_status"], "session_status": session["session_status"], "execution_status": session.get("execution_status") or ("completed" if mission["mission_status"] == "completed" else "waiting"), "approval_status": approval.get("approval_status") or plan.get("approval_status"), "plan_status": plan.get("plan_status"), "completed_goal_count": len(mission.get("completed_goal_ids") or []), "waiting_goal_count": len(mission.get("waiting_goal_ids") or []), "running_goal_count": len(mission.get("running_goal_ids") or []), "blocked_goal_count": len(mission.get("blocked_goal_ids") or []), "failed_goal_count": len(mission.get("failed_goal_ids") or []), "completed_at": session.get("completed_at")}
    value["flow_fingerprint"] = fingerprint(value)
    return value


def review_mission_execution_plan(artifact_path: Any, *, decision: str, operator_id: str, approved_scope: list[str] | None = None, reason: str = "", now: Any = None) -> dict[str, Any]:
    operator=str(operator_id or "").strip()
    if not operator: raise ValueError("operator_id_required")
    if decision not in {"approve","deny"}: raise ValueError("invalid_approval_decision")
    artifact=_load_artifact(artifact_path); plan=ensure_pending_execution_plan(artifact_path,now=now); scope=sorted(set(approved_scope if approved_scope is not None else plan["required_approval_scope"]))
    if not set(scope).issubset(set(plan["required_approval_scope"])): raise ValueError("approval_scope_expansion")
    if decision=="deny" and not reason.strip(): raise ValueError("denial_reason_required")
    approval_path=Path(artifact_path).with_name("execution-approval.json")
    if approval_path.exists():
        existing=json.loads(approval_path.read_text(encoding="utf-8-sig"))
        if existing.get("plan_id")==plan["plan_id"] and existing.get("operator_id")==operator and existing.get("decision")==decision and existing.get("approved_scope")== (scope if decision=="approve" else []): return existing
        raise ValueError("mission_execution_approval_already_recorded")
    seed={"plan_fingerprint":plan["plan_fingerprint"],"operator_id":operator,"decision":decision,"scope":scope}
    value={"contract":APPROVAL_CONTRACT,"approval_id":f"natural-mission-approval-{fingerprint(seed)[:20]}","plan_id":plan["plan_id"],"plan_fingerprint":plan["plan_fingerprint"],"mission_id":plan["mission_id"],"session_id":plan["session_id"],"mission_fingerprint":plan["mission_fingerprint"],"goal_graph_fingerprint":plan["goal_graph_fingerprint"],"workspace_root":plan["workspace_root"],"target_root":plan["target_root"],"approved_scope":scope if decision=="approve" else [],"operator_id":operator,"decision":decision,"approval_status":"approved" if decision=="approve" else "denied","reason":reason,"approved_at":time_text(now),"expires_at":plan["expires_at"],"idempotency_key":fingerprint(seed),"execution_authority_granted":False,"requires_existing_controlled_execution_chain":True}
    value=_save(value,approval_path,"approval_fingerprint")
    plan["approval_status"]=value["approval_status"]; plan["approval_reference"]={"approval_id":value["approval_id"],"path":str(approval_path),"fingerprint":value["approval_fingerprint"]}; plan["review_reason"]=reason; plan["plan_status"]="approved" if decision=="approve" else "denied"; _save(plan,Path(artifact_path).with_name("execution-plan.json"),"plan_fingerprint")
    if decision=="deny":
        from core.runtime.runtime_mission_model import load_mission,save_mission,transition_mission
        from core.runtime.runtime_mission_session import load_mission_session_state,save_mission_session_state
        mission=load_mission(artifact["mission_reference"]["path"],check_expiry=False)
        if mission["mission_status"] not in {"completed","blocked","failed","cancelled","expired"}: save_mission(transition_mission(mission,"blocked",now=now),artifact["mission_reference"]["path"])
        session=load_mission_session_state(artifact["session_reference"]["path"])
        if session["session_status"] not in {"completed","failed","stopped"}: session["session_status"]="blocked";session["failure"]={"critical":False,"reason":"operator_denied","approval_id":value["approval_id"]};save_mission_session_state(session,artifact["session_reference"]["path"])
    _publish(artifact,"mission_execution.approved" if decision=="approve" else "mission_execution.denied",{"mission_id":plan["mission_id"],"plan_id":plan["plan_id"],"approval_id":value["approval_id"],"operator_id":operator},f"{plan['session_id']}:{value['approval_id']}:{decision}",now)
    return value


def _envelope(session: Mapping[str,Any], kind: str, payload: Mapping[str,Any], operator: str, index: int, now: Any) -> dict[str,Any]:
    return {"contract":INPUT_CONTRACT,"session_id":session["session_id"],"input_id":f"{session['session_id']}:{kind}:{index}","input_type":kind,"operator_id":operator,"submitted_at":time_text(now),"payload":deepcopy(dict(payload))}


def _security(plan: Mapping[str,Any]) -> dict[str,Any]:
    keys=("execution_started","mutation_started","mutation_allowed","patch_generation_allowed","patch_application_allowed","autonomous_apply_allowed","requires_controlled_executor","requires_separate_execution_step","requires_post_execution_validation","requires_rollback_capability")
    return {key:plan[key] for key in keys}


def _drive_operator_session(session: Mapping[str,Any], *, scheduler_path: Any, target: Path, workspace: Path, transaction_workspace: Path, operator: str, content_by_path: Mapping[str,str], now: Any) -> dict[str,Any]:
    from core.runtime.runtime_session_queue import load_scheduler_state,save_scheduler_state
    from core.runtime.runtime_session_scheduler import submit_operator_input
    from core.runtime.runtime_execution_plan_review_gate import RUNTIME_EXECUTION_PLAN_OPERATOR_REVIEW_CONTRACT
    from core.runtime.runtime_executor_admission_token import RUNTIME_OPERATOR_EXECUTION_REQUEST_CONTRACT
    from core.runtime.runtime_active_execution_authorization import RUNTIME_ACTIVE_AUTHORIZATION_REQUEST_CONTRACT
    from core.runtime.runtime_transactional_active_execution import BUNDLE_CONTRACT,REQUEST_CONTRACT
    state=load_scheduler_state(scheduler_path); session=deepcopy(dict(session)); current_time=parse_time(time_text(now)); expires=time_text(current_time+timedelta(minutes=10)); execution_expires=time_text(current_time+timedelta(minutes=5))
    payload={"decision":"approve","reason":"Natural Mission operator approval","expires_at":expires}
    state,session=submit_operator_input(state,_envelope(session,"proposal_approval",payload,operator,1,now),target_root=target,workspace_root=workspace,now=now);save_scheduler_state(state,scheduler_path)
    plan=session["artifacts"]["execution_plan"]
    review={"contract":RUNTIME_EXECUTION_PLAN_OPERATOR_REVIEW_CONTRACT,"review_id":f"review-{session['session_id']}","plan_id":plan["plan_id"],"operator_id":operator,"decision":"approved","reviewed_at":time_text(now),"expires_at":expires,"acknowledged_scope":deepcopy(plan["allowed_files"]),"acknowledged_constraints":deepcopy(plan["execution_constraints"]),"acknowledged_security_invariants":_security(plan),"acknowledged_evidence_requirements":deepcopy(plan["evidence_requirements"]),"notes":"Natural Mission approved plan"}
    state,session=submit_operator_input(load_scheduler_state(scheduler_path),_envelope(session,"execution_plan_review",review,operator,2,now),target_root=target,workspace_root=workspace,now=now);save_scheduler_state(state,scheduler_path); reviewed=session["artifacts"]["plan_review"]
    controlled={"contract":RUNTIME_OPERATOR_EXECUTION_REQUEST_CONTRACT,"request_id":f"controlled-{session['session_id']}","review_result_id":reviewed["result_id"],"plan_id":plan["plan_id"],"operator_id":operator,"requested_mode":"controlled_dry_run","requested_at":time_text(now),"expires_at":expires,"acknowledged_scope":deepcopy(plan["allowed_files"]),"acknowledged_dry_run":True,"acknowledged_no_file_mutation":True}
    state,session=submit_operator_input(load_scheduler_state(scheduler_path),_envelope(session,"controlled_execution_request",controlled,operator,3,now),target_root=target,workspace_root=workspace,now=now);save_scheduler_state(state,scheduler_path); activation=session["artifacts"]["controlled_execution_result"]
    authorization={"contract":RUNTIME_ACTIVE_AUTHORIZATION_REQUEST_CONTRACT,"authorization_id":f"auth-{session['session_id']}","controlled_execution_result_id":activation["activation_id"],"token_id":activation["token"]["token_id"],"plan_id":activation["plan_id"],"review_result_id":activation["review_result_id"],"operator_execution_request_id":activation["operator_request_id"],"operator_id":operator,"decision":"authorized","authorized_mode":"prepared_active_execution","authorized_at":time_text(now),"expires_at":expires,"acknowledged_scope":deepcopy(activation["token"]["allowed_files"]),"acknowledged_snapshot_manifest_id":activation["snapshot_manifest"]["manifest_id"],"acknowledged_validation_evidence_id":activation["validation_evidence"]["validation_evidence_id"],"acknowledged_rollback_state_id":activation["rollback_prepared_state"]["rollback_state_id"],"acknowledged_risks":["operator_approved_mutation"],"acknowledged_no_automatic_commit":True,"acknowledged_manual_rollback_authority":True}
    state,session=submit_operator_input(load_scheduler_state(scheduler_path),_envelope(session,"active_execution_authorization",authorization,operator,4,now),target_root=target,workspace_root=workspace,now=now);save_scheduler_state(state,scheduler_path); auth=session["artifacts"]["active_authorization_result"]; files=[]
    for relative in auth["authorized_scope"]:
        path=target/relative; before=path.read_bytes() if path.exists() else None; expected={"expected_exists":before is not None}
        if before is not None: expected.update(expected_sha256=sha256(before).hexdigest(),expected_size=len(before))
        content=str(content_by_path.get(relative, path.read_text(encoding="utf-8-sig") if path.exists() else "")); files.append({"relative_path":relative,"operation":"replace" if before is not None else "create","expected_pre_state":expected,"candidate_content_encoding":"utf-8","candidate_content":content,"candidate_content_hash":sha256(content.encode()).hexdigest(),"maximum_size":100000,"validation_requirements":[]})
    bundle={"contract":BUNDLE_CONTRACT,"candidate_bundle_id":f"bundle-{session['session_id']}","plan_id":auth["plan_id"],"authorization_result_id":auth["authorization_result_id"],"target_root_identity":session["target_root_identity"],"scope_fingerprint":fingerprint(auth["authorized_scope"]),"created_at":time_text(now),"expires_at":execution_expires,"files":files,"validation_profile_id":"none","project_validation_required":False,"approved_test_files":[],"validation_scope":[]};bundle["bundle_fingerprint"]=fingerprint(bundle)
    state,session=submit_operator_input(load_scheduler_state(scheduler_path),_envelope(session,"candidate_bundle",bundle,operator,5,now),target_root=target,workspace_root=workspace,now=now);save_scheduler_state(state,scheduler_path)
    invocation={"contract":REQUEST_CONTRACT,"invocation_request_id":f"invoke-{session['session_id']}","authorization_result_id":auth["authorization_result_id"],"authorization_id":auth["authorization_id"],"controlled_execution_result_id":auth["controlled_execution_result_id"],"token_id":auth["token_id"],"plan_id":auth["plan_id"],"review_result_id":auth["review_result_id"],"operator_id":operator,"requested_mode":"transactional_active_execution","requested_at":time_text(now),"expires_at":execution_expires,"target_root_identity":session["target_root_identity"],"acknowledged_scope":auth["authorized_scope"],"candidate_bundle_id":bundle["candidate_bundle_id"],"candidate_bundle_fingerprint":bundle["bundle_fingerprint"],"validation_profile_id":"none","acknowledged_transactional_execution":True,"acknowledged_automatic_rollback":True,"acknowledged_no_git_commit":True,"acknowledged_no_scope_expansion":True}
    transaction_workspace.mkdir(parents=True,exist_ok=True)
    state,session=submit_operator_input(load_scheduler_state(scheduler_path),_envelope(session,"transactional_invocation",invocation,operator,6,now),target_root=target,workspace_root=transaction_workspace,now=now);save_scheduler_state(state,scheduler_path);return session


def execute_approved_mission(artifact_path: Any, *, operator_id: str, max_iterations: int = 20, now: Any = None) -> dict[str,Any]:
    artifact=_load_artifact(artifact_path); approval_path=Path(artifact_path).with_name("execution-approval.json")
    if not approval_path.exists(): raise ValueError("mission_execution_approval_required")
    approval=json.loads(approval_path.read_text(encoding="utf-8-sig")); claimed=approval.get("approval_fingerprint"); unsigned=deepcopy(approval); unsigned.pop("approval_fingerprint",None)
    if claimed!=fingerprint(unsigned): raise ValueError("mission_execution_approval_fingerprint_mismatch")
    if approval.get("approval_status")!="approved": raise ValueError("mission_execution_approval_not_approved")
    if approval.get("expires_at") and parse_time(time_text(now)) >= parse_time(approval["expires_at"]): raise ValueError("mission_execution_approval_expired")
    mission_path=artifact["mission_reference"]["path"]
    from core.runtime.runtime_mission_model import load_mission
    from core.runtime.runtime_mission_orchestrator import confirm_mission_plan,advance_mission
    mission=load_mission(mission_path,check_expiry=False); target=Path(artifact["target_root"]);workspace=Path(artifact["workspace_root"]);scheduler=mission["scheduler_state_path"]
    if mission["mission_status"]=="waiting_for_plan_confirmation":
        graph=mission["goal_graph"]; payload={"graph_fingerprint":graph["graph_fingerprint"],"goal_ids":graph["goal_ids"],"goal_order":graph["goal_order"],"total_goal_count":len(mission["goals"]),"operator_acknowledgment":True}
        envelope={"contract":"zero.runtime.mission_input.v1","mission_id":mission["mission_id"],"input_id":f"confirm:{approval['approval_id']}","input_type":"confirm_goal_plan","operator_id":operator_id,"submitted_at":time_text(now),"payload":payload};mission=confirm_mission_plan(mission,envelope,scheduler_state=scheduler,now=now)
    content_by_path={i["path"]:i.get("content","") for i in artifact.get("structured_intents") or [] if i.get("operation")=="create_file"}
    completed_sessions=[]
    for _ in range(max_iterations):
        mission=advance_mission(mission,scheduler_state=scheduler,now=now,runtime_config={"target_root":target,"workspace_root":workspace})
        if mission["mission_status"]=="completed": break
        if not mission.get("waiting_goal_ids"): continue
        goal_id=mission["waiting_goal_ids"][0]; session=load_runtime_session(mission["goals"][goal_id]["session_path"],now=now)
        if session["session_status"] not in {"completed","blocked","failed"}:
            session=_drive_operator_session(session,scheduler_path=scheduler,target=target,workspace=workspace,transaction_workspace=Path(artifact_path).parent/"transaction-workspace",operator=operator_id,content_by_path=content_by_path,now=now)
            from core.runtime.runtime_operator_session import save_runtime_session, seal_session
            save_runtime_session(seal_session(session), mission["goals"][goal_id]["session_path"])
        completed_sessions.append({"goal_id":goal_id,"session_id":session["session_id"],"status":session["session_status"],"evidence":deepcopy(session.get("artifacts",{}).get("final_evidence"))});mission=advance_mission(mission,scheduler_state=scheduler,now=now,runtime_config={"target_root":target,"workspace_root":workspace})
        if mission["mission_status"]=="completed": break
    outer=None
    if mission["mission_status"]=="completed":
        from core.runtime.runtime_mission_session import converge_completed_mission_session
        outer=converge_completed_mission_session(artifact["session_reference"]["path"],now=now)
    result={"contract":CONTRACT,"mission_id":mission["mission_id"],"session_id":artifact["session_reference"]["session_id"],"plan_id":approval["plan_id"],"approval_id":approval["approval_id"],"mission_status":mission["mission_status"],"execution_status":"completed" if mission["mission_status"]=="completed" else "waiting","session_status":outer.get("session_status") if outer else "waiting","approval_status":approval["approval_status"],"plan_status":"approved","completed_goal_count":len(mission.get("completed_goal_ids") or []),"waiting_goal_count":len(mission.get("waiting_goal_ids") or []),"completed_sessions":completed_sessions,"evidence":deepcopy(mission.get("mission_evidence")),"completed_at":outer.get("completed_at") if outer else None};result["flow_fingerprint"]=fingerprint(result);_publish(artifact,"mission_execution.completed" if mission["mission_status"]=="completed" else "mission_execution.waiting",{"mission_id":mission["mission_id"],"plan_id":approval["plan_id"],"approval_id":approval["approval_id"],"mission_status":mission["mission_status"]},f"{result['session_id']}:{approval['approval_id']}:{mission['mission_status']}",now);return result


def execute_read_only_mission(artifact_path: Any, *, max_iterations: int = 20, now: Any = None) -> dict[str,Any]:
    artifact=_load_artifact(artifact_path); mission_path=artifact["mission_reference"]["path"]
    from core.runtime.runtime_mission_model import load_mission
    from core.runtime.runtime_mission_orchestrator import confirm_mission_plan,advance_mission
    from core.runtime.runtime_goal_executor import create_goal_execution_request,execute_goal
    from core.runtime.runtime_operator_session import save_runtime_session,set_artifact,seal_session
    from core.runtime.runtime_end_to_end_orchestrator import build_runtime_session_final_evidence
    mission=load_mission(mission_path,check_expiry=False); target=Path(artifact["target_root"]);workspace=Path(artifact["workspace_root"]);scheduler=mission["scheduler_state_path"]
    evidence_root=Path(artifact_path).resolve(strict=True).parent/"read-evidence"
    if any(g.get("goal_type") not in {"inspect","validate"} for g in mission["goals"].values()): raise ValueError("read_only_execution_requires_read_only_goals")
    if mission["mission_status"]=="waiting_for_plan_confirmation":
        graph=mission["goal_graph"];payload={"graph_fingerprint":graph["graph_fingerprint"],"goal_ids":graph["goal_ids"],"goal_order":graph["goal_order"],"total_goal_count":len(mission["goals"]),"operator_acknowledgment":True}; envelope={"contract":"zero.runtime.mission_input.v1","mission_id":mission["mission_id"],"input_id":f"read-only-confirm:{mission['mission_id']}","input_type":"confirm_goal_plan","operator_id":"runtime-read-only","submitted_at":time_text(now),"payload":payload};mission=confirm_mission_plan(mission,envelope,scheduler_state=scheduler,now=now)
    evidence=[]
    for _ in range(max_iterations):
        mission=advance_mission(mission,scheduler_state=scheduler,now=now,runtime_config={"target_root":target,"workspace_root":workspace})
        if mission["mission_status"]=="completed":break
        if not mission.get("waiting_goal_ids"):continue
        goal_id=mission["waiting_goal_ids"][0];goal=mission["goals"][goal_id];path=goal["session_path"];session=load_runtime_session(path,now=now)
        request=create_goal_execution_request(goal,session,operator_context={"expected_text":" "},now=now);result=execute_goal(request,workspace_root=target,artifact_root=evidence_root,now=now)
        if result["execution_status"]!="candidate_ready":
            session["session_status"]="blocked";session["failure"]={"critical":False,"reasons":result.get("reasons") or [result["execution_status"]]}
        else:
            session=set_artifact(session,"goal_execution_result",result);tx={"contract":"zero.runtime.read_only_transaction_projection.v1","transaction_status":"committed","transaction_mode":"controlled_read_only","mutation_performed":False,"committed_paths":[],"validation_status":"passed","validation_result":{"goal_execution_result_fingerprint":result["execution_result_fingerprint"],"tool_results":deepcopy(result.get("tool_results") or [])}};session=set_artifact(session,"transaction_result",tx);session["session_status"]="completed";session["current_phase"]="controlled_read_completed";session["completed"]=True;session["required_action"]="none";session["failure"]=None;session=set_artifact(session,"final_evidence",build_runtime_session_final_evidence(session));evidence.append({"goal_id":goal_id,"session_id":session["session_id"],"result_fingerprint":result["execution_result_fingerprint"]})
        save_runtime_session(seal_session(session),path);mission=advance_mission(mission,scheduler_state=scheduler,now=now,runtime_config={"target_root":target,"workspace_root":workspace})
        if mission["mission_status"] in {"completed","blocked","failed"}:break
    outer=None
    if mission["mission_status"]=="completed":
        from core.runtime.runtime_mission_session import converge_completed_mission_session
        outer=converge_completed_mission_session(artifact["session_reference"]["path"],now=now)
    value={"contract":CONTRACT,"mission_id":mission["mission_id"],"session_id":artifact["session_reference"]["session_id"],"mission_status":mission["mission_status"],"execution_status":"completed" if mission["mission_status"]=="completed" else "waiting","session_status":outer.get("session_status") if outer else "waiting","read_only":True,"mutation_performed":False,"evidence":evidence,"mission_evidence":deepcopy(mission.get("mission_evidence"))};value["flow_fingerprint"]=fingerprint(value);_publish(artifact,"mission_execution.read_completed",{"mission_id":mission["mission_id"],"mission_status":mission["mission_status"],"mutation_performed":False},f"{value['session_id']}:read:{mission['mission_status']}",now);return value


def deny_mission_execution(artifact_path: Any, *, operator_id: str, reason: str, now: Any = None) -> dict[str,Any]:
    return review_mission_execution_plan(artifact_path,decision="deny",operator_id=operator_id,reason=reason,now=now)


__all__=["create_mission_execution_plan","deny_mission_execution","ensure_pending_execution_plan","execute_approved_mission","execute_read_only_mission","mission_execution_status","review_mission_execution_plan","validate_mission_execution_plan"]
