from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from core.runtime.runtime_end_to_end_orchestrator import create_runtime_session
from core.runtime.runtime_goal_graph import propagate_dependency_states, ready_goal_ids
from core.runtime.runtime_mission_model import (INPUT_CONTRACT, TERMINAL, build_mission_evidence, create_mission_contract,
    load_mission, save_mission, seal_mission, transition_mission, validate_mission)
from core.runtime.runtime_operator_session import fingerprint, load_runtime_session, save_runtime_session, time_text
from core.runtime.runtime_session_queue import (create_scheduler_state, enqueue_session, load_scheduler_state, save_scheduler_state,
    validate_scheduler_state)

WAITING_SESSION = {"waiting_for_operator_approval","waiting_for_plan_review","waiting_for_active_authorization","waiting_for_candidate_bundle","waiting_for_transaction_invocation"}
SESSION_TERMINAL = {"completed","blocked","failed","expired","cancelled"}

def _mapping(value: Any) -> dict[str, Any]: return deepcopy(dict(value)) if isinstance(value, Mapping) else {}
def _session_dir(mission_path: Any, config: Mapping[str, Any]) -> Path:
    return Path(config.get("session_directory") or (Path(mission_path).parent / f"{Path(mission_path).stem}.sessions"))
def _save_if(value: Mapping[str, Any], path: Any) -> dict[str, Any]: return save_mission(value,path) if path else seal_mission(value)

def create_mission(mission_input: Mapping[str, Any], *, goal_plan: Any = None, target_root: Any, workspace_root: Any,
                   mission_path: Any = None, scheduler_state_path: Any = None, now: Any = None,
                   runtime_config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if goal_plan is None: raise ValueError("goal_plan_required")
    if mission_path and Path(mission_path).resolve(strict=False).is_relative_to(Path(target_root).resolve(strict=True)): raise ValueError("mission_path_inside_target_root")
    mission=create_mission_contract(mission_input,goal_plan=goal_plan,target_root=target_root,workspace_root=workspace_root,now=now,runtime_config=runtime_config)
    mission["mission_path"]=str(Path(mission_path).resolve(strict=False)) if mission_path else None
    mission["scheduler_state_path"]=str(Path(scheduler_state_path).resolve(strict=False)) if scheduler_state_path else None
    if scheduler_state_path and not Path(scheduler_state_path).exists(): save_scheduler_state(create_scheduler_state(state_path=scheduler_state_path,now=now),scheduler_state_path)
    return _save_if(mission,mission_path)

def _validate_input(mission: Mapping[str, Any], operator_input: Mapping[str, Any]) -> tuple[dict[str,Any],bool]:
    envelope=_mapping(operator_input)
    if envelope.get("contract")!=INPUT_CONTRACT: raise ValueError("invalid_mission_input_contract")
    if envelope.get("mission_id")!=mission.get("mission_id"): raise ValueError("mission_input_mismatch")
    if not str(envelope.get("input_id") or "").strip() or not str(envelope.get("operator_id") or "").strip(): raise ValueError("operator_identity_required")
    return envelope,envelope["input_id"] in mission.get("processed_input_ids",[])

def _record_input(mission: dict[str,Any], envelope: Mapping[str,Any]) -> None:
    mission.setdefault("processed_input_ids",[]).append(envelope["input_id"])
    mission.setdefault("audit_record",{}).setdefault("operator_actions",[]).append({key:envelope.get(key) for key in ("input_id","input_type","operator_id","submitted_at")})

def confirm_mission_plan(mission: Mapping[str, Any], operator_input: Mapping[str, Any], *, scheduler_state: Any = None,
                         now: Any = None, runtime_config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    value=_mapping(mission); reasons=validate_mission(value,now=now)
    if reasons: raise ValueError(";".join(reasons))
    envelope,duplicate=_validate_input(value,operator_input)
    if duplicate: return value
    if value.get("mission_status")!="waiting_for_plan_confirmation": raise ValueError("wrong_mission_phase_input")
    kind=envelope.get("input_type"); payload=_mapping(envelope.get("payload")); graph=value["goal_graph"]
    if kind=="reject_goal_plan": value=transition_mission(value,"blocked",now=now); value["failure"]={"reasons":["goal_plan_rejected"]}
    elif kind=="confirm_goal_plan":
        required={"graph_fingerprint":graph["graph_fingerprint"],"goal_ids":graph["goal_ids"],"goal_order":graph["goal_order"],"total_goal_count":len(value["goals"])}
        for key,expected in required.items():
            if payload.get(key)!=expected: raise ValueError(f"plan_confirmation_mismatch:{key}")
        if payload.get("operator_acknowledgment") is not True: raise ValueError("operator_acknowledgment_required")
        if value.get("planner_output_reference"):
            planner_checks={"natural_request_id":_mapping(value.get("natural_mission_request_reference")).get("request_id"),"planner_output_id":_mapping(value.get("planner_output_reference")).get("planner_output_id"),"planner_output_fingerprint":_mapping(value.get("planner_output_reference")).get("fingerprint"),"included_scope":_mapping(value.get("planner_output_summary")).get("included_scope",[]),"excluded_scope":_mapping(value.get("planner_output_summary")).get("excluded_scope",[]),"risk_summary":_mapping(value.get("planner_output_summary")).get("risk_summary",[]),"operator_boundaries":_mapping(value.get("planner_output_summary")).get("operator_boundaries",[])}
            for key,expected in planner_checks.items():
                if payload.get(key)!=expected:raise ValueError(f"plan_confirmation_mismatch:{key}")
        graph["confirmed"]=True; unsigned=_mapping(graph); unsigned.pop("graph_fingerprint",None); graph["graph_fingerprint"]=fingerprint(unsigned)
        value=transition_mission(value,"ready",now=now)
        value["planning_status"]="confirmed"
    else: raise ValueError("wrong_mission_input_type")
    _record_input(value,envelope); return _save_if(seal_mission(value),value.get("mission_path"))

def _project_goal(goal: dict[str,Any], session: Mapping[str,Any], now: Any) -> None:
    status=session.get("session_status"); at=time_text(now)
    if status in WAITING_SESSION: projected="waiting_for_operator"
    elif status in {"created","running","transaction_running"}: projected="running"
    elif status=="completed":
        tx=_mapping(_mapping(session.get("artifacts")).get("transaction_result")); transaction=tx.get("transaction_status")
        projected="completed" if transaction=="committed" else "failed"
        validation_status=tx.get("validation_status") or ("passed" if tx.get("validation_passed") is True else "failed" if tx.get("validation_passed") is False else "not_run")
        rollback_status=tx.get("rollback_status") or ("verified" if tx.get("rollback_verified") is True else "failed" if tx.get("rollback_executed") and tx.get("rollback_verified") is False else "not_required")
        goal["result_summary"]={"transaction_status":transaction,"validation_status":validation_status,"validation_evidence":deepcopy(tx.get("validation_result") or {}),"rollback_status":rollback_status,"rollback_evidence":deepcopy(tx.get("rollback_result") or {}),"committed_paths":deepcopy(tx.get("committed_paths") or tx.get("changed_files") or []),"rolled_back_paths":deepcopy(tx.get("rolled_back_paths") or [])}
    elif status=="blocked": projected="blocked"
    elif status in {"failed","expired"}: projected="failed"
    elif status=="cancelled": projected="cancelled"
    else: raise ValueError("unknown_session_status")
    old=goal.get("goal_status"); goal["goal_status"]=projected; goal["updated_at"]=at
    if projected=="running" and not goal.get("started_at"): goal["started_at"]=at
    if projected in {"completed","failed","blocked","cancelled"} and old not in {"completed","failed","blocked","cancelled"}: goal["completed_at"]=at
    if projected in {"failed","blocked"}: goal["failure"]=_mapping(session.get("failure")) or {"reasons":[f"session_{status}"]}

def _rebuild_lists(value: dict[str,Any]) -> None:
    mapping={"ready":"ready_goal_ids","running":"running_goal_ids","waiting_for_operator":"waiting_goal_ids","completed":"completed_goal_ids","failed":"failed_goal_ids","blocked":"blocked_goal_ids","cancelled":"cancelled_goal_ids"}
    for field in mapping.values(): value[field]=[]
    for goal_id in value["goal_order"]:
        field=mapping.get(value["goals"][goal_id].get("goal_status"))
        if field: value[field].append(goal_id)

def _create_goal_session(value: dict[str,Any], goal_id: str, *, target_root: Any, workspace_root: Any, mission_path: Any,
                         scheduler: Mapping[str,Any], now: Any, config: Mapping[str,Any]) -> tuple[dict[str,Any],dict[str,Any]]:
    goal=value["goals"][goal_id]
    if goal.get("session_id"): return value,_mapping(scheduler)
    directory=_session_dir(mission_path,config); directory.mkdir(parents=True,exist_ok=True)
    attempt=int(goal.get("attempt_count",0))+1; path=directory/f"{goal_id}.attempt-{attempt}.json"
    natural={"task_id":f"{value['mission_id']}:{goal_id}:attempt-{attempt}","text":goal["goal_description"],"mission_id":value["mission_id"],"goal_id":goal_id,
             "goal_title":goal["goal_title"],"approved_target_scope":deepcopy(goal.get("target_scope") or []),"target_files":deepcopy(goal.get("target_scope") or []),
             "acceptance_criteria":deepcopy(goal.get("acceptance_criteria") or []),"validation_requirements":deepcopy(goal.get("validation_requirements") or [])}
    session=create_runtime_session(natural,target_root=target_root,workspace_root=workspace_root,session_path=path,now=now,runtime_config=config.get("session_runtime_config"))
    reference={"session_id":session["session_id"],"session_path":str(path.resolve()),"session_fingerprint":session["session_fingerprint"],"mission_id":value["mission_id"],"goal_id":goal_id,"attempt":attempt,"archived":False}
    value.setdefault("session_references",{}).setdefault(goal_id,[]).append(reference)
    goal.update(session_id=session["session_id"],session_path=reference["session_path"],session_fingerprint=session["session_fingerprint"],attempt_count=attempt,goal_status="waiting_for_operator",started_at=time_text(now),updated_at=time_text(now))
    scheduler=enqueue_session(scheduler,path,priority=int(goal.get("priority",0)),now=now,target_root=target_root,workspace_root=workspace_root)
    return value,scheduler

def advance_mission(mission: Mapping[str, Any], *, scheduler_state: Any, now: Any = None,
                    runtime_config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    value=_mapping(mission); config=_mapping(runtime_config); reasons=validate_mission(value,now=now)
    if reasons: raise ValueError(";".join(reasons))
    if value.get("mission_status") in TERMINAL: return value
    if value.get("mission_status")=="waiting_for_plan_confirmation": return value
    scheduler_path=scheduler_state if isinstance(scheduler_state,(str,Path)) else value.get("scheduler_state_path")
    if isinstance(scheduler_state,Mapping): scheduler=_mapping(scheduler_state)
    else:
        if not scheduler_path or not Path(scheduler_path).exists(): raise ValueError("missing_scheduler_state")
        scheduler=load_scheduler_state(scheduler_path)
    if validate_scheduler_state(scheduler): raise ValueError("invalid_scheduler_state")
    target=config.get("target_root"); workspace=config.get("workspace_root")
    if target is None or workspace is None: raise ValueError("runtime_roots_required")
    for goal_id in value["goal_order"]:
        goal=value["goals"][goal_id]
        if not goal.get("session_path"): continue
        try: session=load_runtime_session(goal["session_path"],target_root=target,workspace_root=workspace,now=now)
        except ValueError as exc: goal["goal_status"]="blocked"; goal["failure"]={"reasons":[str(exc)]}; continue
        if session.get("session_id")!=goal.get("session_id"): goal["goal_status"]="blocked"; goal["failure"]={"reasons":["session_identity_mismatch"]}; continue
        _project_goal(goal,session,now); goal["session_fingerprint"]=session["session_fingerprint"]
    value["goals"]=propagate_dependency_states(value["goals"],policy=value.get("mission_policy","block_dependents"))
    for goal_id in ready_goal_ids(value["goals"]): value["goals"][goal_id]["goal_status"]="ready"
    for goal_id in value["goal_order"]:
        if value["goals"][goal_id]["goal_status"]=="ready": value,scheduler=_create_goal_session(value,goal_id,target_root=target,workspace_root=workspace,mission_path=value.get("mission_path"),scheduler=scheduler,now=now,config=config)
    _rebuild_lists(value); statuses={goal.get("goal_status") for goal in value["goals"].values()}
    if statuses=={"completed"}: new_status="completed"
    elif "failed" in statuses and not ({"running","waiting_for_operator","ready","pending"}&statuses): new_status="partially_completed" if "completed" in statuses else "failed"
    elif "blocked" in statuses and not ({"running","waiting_for_operator","ready","pending"}&statuses): new_status="partially_completed" if "completed" in statuses else "blocked"
    elif "waiting_for_operator" in statuses: new_status="waiting_for_operator"
    else: new_status="running"
    if new_status!=value["mission_status"]: value=transition_mission(value,new_status,now=now)
    value.setdefault("checkpoints",[]).append({"checkpoint_id":f"mission-checkpoint-{fingerprint({'mission':value['mission_id'],'at':time_text(now),'status':new_status,'lists':[value[k] for k in ('completed_goal_ids','failed_goal_ids','blocked_goal_ids')]})[:16]}","at":time_text(now),"mission_status":new_status})
    if new_status in TERMINAL or new_status=="partially_completed": value["mission_evidence"]=build_mission_evidence(seal_mission(value))
    value=seal_mission(value)
    if scheduler_path: save_scheduler_state(scheduler,scheduler_path)
    return _save_if(value,value.get("mission_path"))

def submit_mission_input(mission: Mapping[str,Any], operator_input: Mapping[str,Any], *, scheduler_state: Any=None, now: Any=None, runtime_config: Mapping[str,Any]|None=None) -> dict[str,Any]:
    if operator_input.get("input_type") in {"confirm_goal_plan","reject_goal_plan"}: return confirm_mission_plan(mission,operator_input,scheduler_state=scheduler_state,now=now,runtime_config=runtime_config)
    value=_mapping(mission); envelope,duplicate=_validate_input(value,operator_input)
    if duplicate:return value
    kind=envelope.get("input_type"); payload=_mapping(envelope.get("payload")); goal_id=payload.get("goal_id")
    if kind=="cancel_mission": return cancel_mission(value,operator_id=envelope["operator_id"],now=now)
    if kind=="request_replan":
        from core.runtime.runtime_mission_replanner import create_replanning_request,deterministic_replanner,stage_replan
        request=create_replanning_request(value,operator_instruction=str(payload.get("operator_instruction")or""),allowed_revision_scope=payload.get("allowed_revision_scope"),memory_evidence=payload.get("memory_evidence"),now=now)
        output=deterministic_replanner(request,value);value=stage_replan(value,request,output,now=now);_record_input(value,envelope);return _save_if(seal_mission(value),value.get("mission_path"))
    if kind=="confirm_replan":
        from core.runtime.runtime_mission_replanner import confirm_replan
        value=confirm_replan(value,payload,now=now);_record_input(value,envelope);return _save_if(seal_mission(value),value.get("mission_path"))
    if kind=="reject_replan":
        if value.get("mission_status")!="waiting_for_replan_confirmation":raise ValueError("wrong_replan_confirmation_phase")
        value["replan_required"]=False;value["replanning_status"]="rejected";value["replanning_history"][-1]["status"]="rejected";value=transition_mission(value,"blocked",now=now);_record_input(value,envelope);return _save_if(seal_mission(value),value.get("mission_path"))
    if kind=="provide_planning_clarification":
        value.setdefault("clarification_history",[]).append({"input_id":envelope["input_id"],"operator_id":envelope["operator_id"],"submitted_at":envelope.get("submitted_at"),"payload":deepcopy(payload)});value["planning_revision"]=int(value.get("planning_revision",0))+1;value["clarification_required"]=False;value["planning_status"]="clarification_received";_record_input(value,envelope);return _save_if(seal_mission(value),value.get("mission_path"))
    if goal_id not in value.get("goals",{}): raise ValueError("unknown_goal_id")
    goal=value["goals"][goal_id]
    if kind=="reprioritize_goal":
        priority=payload.get("priority")
        if isinstance(priority,bool) or not isinstance(priority,int) or not -100<=priority<=100: raise ValueError("invalid_priority")
        if goal.get("session_id"): raise ValueError("active_goal_not_reprioritizable")
        goal["priority"]=priority
    elif kind in {"retry_goal","unblock_goal"}:
        if goal.get("goal_status") not in {"failed","blocked"}: raise ValueError("goal_not_retryable")
        if _mapping(goal.get("failure")).get("critical"): raise ValueError("critical_goal_not_retryable")
        if int(goal.get("attempt_count",0))>=int(goal.get("max_attempts",0)): raise ValueError("goal_max_attempts_exceeded")
        refs=value.get("session_references",{}).get(goal_id,[])
        if refs: refs[-1]["archived"]=True
        goal.update(goal_status="pending",session_id=None,session_path=None,session_fingerprint=None,failure=None,completed_at=None)
        if value.get("mission_status") == "blocked": value = transition_mission(value, "running", now=now, recovery=True)
    else: raise ValueError("unsupported_mission_input_type")
    _record_input(value,envelope); return _save_if(seal_mission(value),value.get("mission_path"))

def cancel_mission(mission: Mapping[str,Any], *, operator_id: str, now: Any=None) -> dict[str,Any]:
    if not str(operator_id).strip(): raise ValueError("operator_id_required")
    value=_mapping(mission)
    if value.get("mission_status") in TERMINAL:return value
    for goal in value.get("goals",{}).values():
        if goal.get("goal_status") in {"pending","ready"}:goal["goal_status"]="cancelled"
    value=transition_mission(value,"cancelled",now=now); _rebuild_lists(value); value["mission_evidence"]=build_mission_evidence(seal_mission(value)); return _save_if(seal_mission(value),value.get("mission_path"))

__all__=["advance_mission","cancel_mission","confirm_mission_plan","create_mission","load_mission","save_mission","submit_mission_input"]
