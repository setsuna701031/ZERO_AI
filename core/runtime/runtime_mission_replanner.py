from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from typing import Any, Mapping

from core.runtime.runtime_goal_graph import build_goal_graph
from core.runtime.runtime_mission_model import seal_mission, transition_mission
from core.runtime.runtime_operator_session import fingerprint, parse_time, time_text

REQUEST_CONTRACT="zero.runtime.mission_replanning_request.v1"
OUTPUT_CONTRACT="zero.runtime.mission_replanner_output.v1"
FORBIDDEN={"candidate_content","patch_text","diff","shell_command","command","argv","script","callable","executable_payload"}
def _mapping(v:Any)->dict[str,Any]:return deepcopy(dict(v)) if isinstance(v,Mapping) else {}

def create_replanning_request(mission:Mapping[str,Any],*,operator_instruction:str="",allowed_revision_scope:list[str]|None=None,memory_evidence:Any=None,planning_feedback_context:Mapping[str,Any]|None=None,now:Any=None)->dict[str,Any]:
    value=_mapping(mission);status=value.get("mission_status")
    if status in {"completed","cancelled","expired"}:raise ValueError("mission_not_replannable")
    critical=[g for g in value.get("goals",{}).values() if _mapping(g.get("failure")).get("critical")]
    if critical:raise ValueError("critical_goal_replan_blocked")
    failed=list(value.get("failed_goal_ids")or[]);blocked=list(value.get("blocked_goal_ids")or[])
    if not failed and not blocked and not str(operator_instruction).strip():raise ValueError("replanning_trigger_required")
    at=time_text(now);revision=int(value.get("replanning_revision",0))+1
    evidence={key:{"failure":deepcopy(value["goals"][key].get("failure")),"result_summary":deepcopy(value["goals"][key].get("result_summary")),"evidence_references":deepcopy(value["goals"][key].get("evidence_references",[])),"session_id":value["goals"][key].get("session_id")} for key in failed+blocked}
    memory=[{"reference":m.get("reference"),"fingerprint":m.get("fingerprint")or fingerprint(m),"similarity":m.get("similarity"),"summary":str(m.get("summary")or"")[:500]} for m in map(_mapping,list(memory_evidence or [])[:20])]
    seed={"mission":value.get("mission_id"),"fingerprint":value.get("mission_fingerprint"),"revision":revision,"at":at,"instruction":operator_instruction}
    result={"contract":REQUEST_CONTRACT,"replanning_request_id":f"replanning-request-{fingerprint(seed)[:20]}","mission_id":value.get("mission_id"),"current_mission_fingerprint":value.get("mission_fingerprint"),"current_graph_fingerprint":_mapping(value.get("goal_graph")).get("graph_fingerprint"),"failed_goal_ids":failed,"blocked_goal_ids":blocked,"completed_goal_ids":list(value.get("completed_goal_ids")or[]),"immutable_completed_goals":{key:deepcopy(value["goals"][key]) for key in value.get("completed_goal_ids",[])},"failure_evidence_summaries":evidence,"activity_memory_summaries":memory,"operator_instruction":str(operator_instruction),"allowed_revision_scope":deepcopy(allowed_revision_scope or value.get("planner_output_scope",[])),"submitted_at":at,"expires_at":time_text(parse_time(at)+timedelta(days=7)),"revision_number":revision,"audit_record":{"event_type":"mission_replanning_requested","created_at":at}}
    feedback=_mapping(planning_feedback_context)
    result["planning_feedback_context"]={"planning_feedback_reference":feedback.get("feedback_id") or feedback.get("planning_feedback_reference"),"avoid_patterns":list(feedback.get("avoid_patterns")or[])[:12],"recommended_validations":list(feedback.get("recommended_validations")or[])[:12],"risk_notes":list(feedback.get("risk_notes")or[])[:12],"known_failed_operation_patterns":list(feedback.get("known_failed_operation_patterns")or[])[:12]}
    result["request_fingerprint"]=fingerprint(result);return result

def deterministic_replanner(request:Mapping[str,Any],mission:Mapping[str,Any])->dict[str,Any]:
    req=_mapping(request);m=_mapping(mission);completed=set(req.get("completed_goal_ids")or[]);failed=set(req.get("failed_goal_ids")or[])|set(req.get("blocked_goal_ids")or[])
    unchanged=[key for key in m.get("goal_order",[]) if key not in failed]
    replacements=[]
    for old in sorted(failed):
        source=m["goals"][old];new_id=f"{old}-revision-{req['revision_number']}"
        replacements.append({"replaces_goal_id":old,"provisional_goal_id":new_id,"title":f"Revised: {source['goal_title']}","description":f"Replan after sealed failure evidence: {source['goal_description']}","goal_type":source["goal_type"],"priority":source["priority"],"depends_on":[d for d in source.get("depends_on",[]) if d not in failed],"target_scope":deepcopy(source.get("target_scope",[])),"required_capabilities":deepcopy(source.get("required_capabilities",[])),"acceptance_criteria":deepcopy(source.get("acceptance_criteria",[])),"validation_requirements":deepcopy(source.get("validation_requirements",[])),"operator_confirmation_required":True,"max_attempts":source.get("max_attempts",3),"evidence_requirements":["sealed prior failure evidence"]})
    order=unchanged+[x["provisional_goal_id"] for x in replacements]
    value={"contract":OUTPUT_CONTRACT,"replanner_output_id":"","replanning_request_id":req.get("replanning_request_id"),"mission_id":req.get("mission_id"),"revision_number":req.get("revision_number"),"replan_status":"replanned","unchanged_goal_ids":unchanged,"removed_goal_ids":sorted(failed),"replacement_goals":replacements,"added_goals":[],"revised_dependencies":{x["provisional_goal_id"]:x["depends_on"] for x in replacements},"revised_goal_order":order,"preserved_completed_goals":sorted(completed),"preserved_evidence_references":{key:deepcopy(m["goals"][key].get("evidence_references",[])) for key in completed},"scope_delta":{"added":[],"removed":[]},"risk_delta":["Revised goals require operator confirmation and new Sessions"],"operator_boundaries":["replan confirmation required","Session approvals remain required"],"reasons":["sealed failure feedback incorporated"],"generated_at":req.get("submitted_at"),"expires_at":req.get("expires_at"),"audit_record":{"event_type":"mission_replanner_output_created","created_at":req.get("submitted_at")}}
    value["replanner_output_id"]=f"replanner-output-{fingerprint(value)[:20]}";value["output_fingerprint"]=fingerprint(value);return value

def validate_replanner_output(output:Mapping[str,Any],request:Mapping[str,Any],mission:Mapping[str,Any],*,now:Any=None)->list[str]:
    v=_mapping(output);req=_mapping(request);m=_mapping(mission);r=[]
    if v.get("contract")!=OUTPUT_CONTRACT:r.append("invalid_replanner_output_contract")
    if v.get("replanning_request_id")!=req.get("replanning_request_id") or v.get("mission_id")!=m.get("mission_id"):r.append("replanner_identity_mismatch")
    unsigned=_mapping(v);claimed=unsigned.pop("output_fingerprint",None)
    if claimed!=fingerprint(unsigned):r.append("replanner_output_fingerprint_mismatch")
    if v.get("revision_number")!=req.get("revision_number"):r.append("replanning_revision_mismatch")
    if sorted(v.get("preserved_completed_goals")or[])!=sorted(req.get("completed_goal_ids")or[]):r.append("completed_goals_not_preserved")
    if any(key in v.get("removed_goal_ids",[]) for key in req.get("completed_goal_ids",[])):r.append("completed_goal_removed")
    for goal in list(v.get("replacement_goals")or[])+list(v.get("added_goals")or[]):
        item=_mapping(goal)
        if FORBIDDEN.intersection(item):r.append("executable_replanner_goal_forbidden")
        allowed=req.get("allowed_revision_scope")or[]
        if allowed and any(not any(s==a or str(s).startswith(str(a)+"/") for a in allowed) for s in item.get("target_scope",[])):r.append("replan_scope_expansion")
    try:
        if parse_time(now or req.get("submitted_at"))>=parse_time(v.get("expires_at")):r.append("replanner_output_expired")
    except (TypeError,ValueError):r.append("invalid_replanner_expiration")
    return sorted(set(r))

def stage_replan(mission:Mapping[str,Any],request:Mapping[str,Any],output:Mapping[str,Any],*,now:Any=None)->dict[str,Any]:
    reasons=validate_replanner_output(output,request,mission,now=now)
    if reasons:raise ValueError(";".join(reasons))
    value=_mapping(mission);value["replan_required"]=True;value["replanning_status"]="waiting_for_replan_confirmation";value["replanning_revision"]=request["revision_number"]
    value.setdefault("replanning_history",[]).append({"revision_number":request["revision_number"],"old_graph_fingerprint":request["current_graph_fingerprint"],"request":deepcopy(request),"output":deepcopy(output),"status":"waiting_for_replan_confirmation"})
    if value.get("mission_status")!="waiting_for_replan_confirmation":value=transition_mission(value,"waiting_for_replan_confirmation",now=now)
    return seal_mission(value)

def confirm_replan(mission:Mapping[str,Any],payload:Mapping[str,Any],*,now:Any=None)->dict[str,Any]:
    value=_mapping(mission)
    if value.get("mission_status")!="waiting_for_replan_confirmation":raise ValueError("wrong_replan_confirmation_phase")
    history=value.get("replanning_history")or[];current=history[-1];req=current["request"];out=current["output"];p=_mapping(payload)
    checks={"revision_number":out["revision_number"],"old_graph_fingerprint":req["current_graph_fingerprint"],"unchanged_goal_ids":out["unchanged_goal_ids"],"completed_goal_ids":req["completed_goal_ids"],"removed_goal_ids":out["removed_goal_ids"],"added_goal_ids":[g["provisional_goal_id"] for g in out.get("added_goals",[])],"scope_delta":out["scope_delta"],"risk_delta":out["risk_delta"]}
    for key,expected in checks.items():
        if p.get(key)!=expected:raise ValueError(f"replan_confirmation_mismatch:{key}")
    if p.get("operator_acknowledgment") is not True:raise ValueError("operator_acknowledgment_required")
    completed={key:deepcopy(value["goals"][key]) for key in value.get("completed_goal_ids",[])};goals=[]
    for key in out["unchanged_goal_ids"]:
        if key in value["goals"]:goals.append(deepcopy(value["goals"][key]))
    for item in list(out.get("replacement_goals")or[])+list(out.get("added_goals")or[]):
        g=_mapping(item);goals.append({"goal_id":g["provisional_goal_id"],"goal_title":g["title"],"goal_description":g["description"],"goal_type":g["goal_type"],"goal_status":"pending","priority":g.get("priority",0),"depends_on":g.get("depends_on",[]),"target_scope":g.get("target_scope",[]),"required_capabilities":g.get("required_capabilities",[]),"acceptance_criteria":g.get("acceptance_criteria",[]),"validation_requirements":g.get("validation_requirements",[]),"max_attempts":g.get("max_attempts",3)})
    built=build_goal_graph(goals,mission_id=value["mission_id"],confirmed=True);value["goals"]=built["goals"]
    for key,goal in completed.items():value["goals"][key]=goal
    value["goal_graph"]=built["graph"];value["goal_order"]=built["goal_order"]
    value["immutable_completed_goal_ids"]=sorted(completed);value["replan_required"]=False;value["replanning_status"]="confirmed";current["status"]="confirmed"
    return transition_mission(seal_mission(value),"running",now=now)

__all__=["OUTPUT_CONTRACT","REQUEST_CONTRACT","confirm_replan","create_replanning_request","deterministic_replanner","stage_replan","validate_replanner_output"]
