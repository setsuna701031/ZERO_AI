from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json, os, stat
from pathlib import Path
from typing import Any, Mapping

from core.runtime.runtime_operator_session import fingerprint, parse_time, root_identity, time_text
from core.runtime.runtime_goal_graph import build_goal_graph, validate_goal_graph

CONTRACT = "zero.runtime.mission.v1"
INPUT_CONTRACT = "zero.runtime.mission_input.v1"
EVIDENCE_CONTRACT = "zero.runtime.mission_evidence.v1"
TERMINAL = {"completed", "blocked", "failed", "expired", "cancelled"}
TRANSITIONS = {
 "created":{"planning","cancelled","expired"}, "planning":{"waiting_for_plan_confirmation","blocked","cancelled","expired"},
 "waiting_for_plan_confirmation":{"ready","blocked","cancelled","expired"}, "ready":{"running","waiting_for_operator","completed","blocked","cancelled","expired"},
 "running":{"waiting_for_operator","partially_completed","completed","blocked","failed","cancelled","expired"},
 "waiting_for_operator":{"running","partially_completed","completed","blocked","failed","cancelled","expired"},
 "partially_completed":{"running","waiting_for_operator","waiting_for_replan_confirmation","completed","blocked","failed","cancelled","expired"},
 "waiting_for_replan_confirmation":{"running","blocked","cancelled","expired"},
 "completed":set(), "blocked":{"waiting_for_replan_confirmation"}, "failed":{"waiting_for_replan_confirmation"}, "expired":set(), "cancelled":set(),
}

def _mapping(value: Any) -> dict[str, Any]: return deepcopy(dict(value)) if isinstance(value, Mapping) else {}
def _unsigned(value: Mapping[str, Any]) -> dict[str, Any]:
    result = _mapping(value); result.pop("mission_fingerprint", None); return result
def seal_mission(mission: Mapping[str, Any]) -> dict[str, Any]:
    value = _unsigned(mission); value["mission_fingerprint"] = fingerprint(value); return value
def deterministic_mission_id(mission_input: Mapping[str, Any], target_root_identity: str, workspace_root_identity: str) -> str:
    return f"mission-{fingerprint({'input': _mapping(mission_input), 'target': target_root_identity, 'workspace': workspace_root_identity})[:20]}"

def transition_mission(mission: Mapping[str, Any], status: str, *, now: Any = None, recovery: bool = False) -> dict[str, Any]:
    value = _mapping(mission); current = value.get("mission_status")
    allowed = set(TRANSITIONS.get(current, set()))
    if recovery and current == "blocked": allowed.add("running")
    if status not in allowed: raise ValueError(f"invalid_mission_transition:{current}:{status}")
    at = time_text(now); value["mission_status"] = status; value["updated_at"] = at
    value.setdefault("phase_history", []).append({"from": current, "to": status, "at": at, "recovery": recovery})
    value["completed"] = status == "completed"
    if status == "completed":
        value["completed_at"] = value.get("completed_at") or at
        value["failure"] = None
    return seal_mission(value)

def create_mission_contract(mission_input: Mapping[str, Any], *, goal_plan: Any, target_root: Any, workspace_root: Any, now: Any = None, runtime_config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    source = _mapping(mission_input); config = _mapping(runtime_config); at = time_text(now)
    target_id, workspace_id = root_identity(target_root), root_identity(workspace_root)
    mission_id = deterministic_mission_id(source, target_id, workspace_id)
    built = build_goal_graph(goal_plan, mission_id=mission_id)
    expires = time_text(config.get("mission_expires_at") or (parse_time(at) + timedelta(days=30)))
    goals = built["goals"]
    for goal in goals.values():
        goal.update(created_at=at, updated_at=at, started_at=None, completed_at=None, expires_at=expires,
                    operator_confirmation_required=bool(goal.get("operator_confirmation_required", True)), session_id=None, session_path=None,
                    session_fingerprint=None, attempt_count=0, max_attempts=int(goal.get("max_attempts", 3)), result_summary=None,
                    failure=None, evidence_references=[], audit_record={"event_type":"mission_goal_created","created_at":at})
        goal["goal_fingerprint"] = fingerprint({k:v for k,v in goal.items() if k != "goal_fingerprint"})
    title = str(source.get("mission_title") or source.get("title") or "Mission").strip()
    description = str(source.get("mission_description") or source.get("description") or source.get("text") or "").strip()
    mission = {"contract":CONTRACT,"mission_id":mission_id,"mission_status":"created","mission_title":title,"mission_description":description,
      "mission_input":source,"created_at":at,"updated_at":at,"expires_at":expires,"target_root_identity":target_id,"workspace_root_identity":workspace_id,
      "planning_mode":"operator_confirmed","mission_policy":str(config.get("dependency_policy") or "block_dependents"),"goal_graph":built["graph"],"goal_order":built["goal_order"],"goals":goals,
      "ready_goal_ids":[],"running_goal_ids":[],"waiting_goal_ids":[],"completed_goal_ids":[],"failed_goal_ids":[],"blocked_goal_ids":[],"cancelled_goal_ids":[],
      "session_references":{},"processed_input_ids":[],"checkpoints":[],"phase_history":[],"mission_evidence":None,"failure":None,"completed":False,
      "natural_mission_request_reference":None,"planning_request_reference":None,"planner_output_reference":None,"planning_revision":0,"planning_status":"not_started","clarification_required":False,"clarification_history":[],"replan_required":False,"replanning_status":"not_started","replanning_revision":0,"replanning_history":[],"immutable_completed_goal_ids":[],"planner_evidence_references":[],"last_planning_checkpoint":None,
      "audit_record":{"event_type":"runtime_mission_created","created_at":at,"operator_actions":[]}}
    mission = seal_mission(mission); mission = transition_mission(mission,"planning",now=now); return transition_mission(mission,"waiting_for_plan_confirmation",now=now)

def validate_mission(mission: Mapping[str, Any], *, target_root: Any = None, workspace_root: Any = None, now: Any = None, check_expiry: bool = True) -> list[str]:
    value = _mapping(mission); reasons: list[str] = []
    if value.get("contract") != CONTRACT: reasons.append("mission_migration_required")
    if value.get("mission_status") not in TRANSITIONS: reasons.append("invalid_mission_status")
    if value.get("mission_fingerprint") != fingerprint(_unsigned(value)): reasons.append("mission_fingerprint_mismatch")
    reasons.extend(validate_goal_graph(value.get("goal_graph") or {}, value.get("goals") or {}, mission_id=str(value.get("mission_id") or "")))
    try:
        if target_root is not None and root_identity(target_root) != value.get("target_root_identity"): reasons.append("target_root_mismatch")
        if workspace_root is not None and root_identity(workspace_root) != value.get("workspace_root_identity"): reasons.append("workspace_root_mismatch")
        if check_expiry and value.get("expires_at") and parse_time(now or datetime.now(timezone.utc)) >= parse_time(value["expires_at"]): reasons.append("mission_expired")
    except (OSError, ValueError, TypeError): reasons.append("invalid_mission_identity")
    return reasons

def _unsafe(path: Path) -> bool:
    try: return path.is_symlink() or bool(getattr(path.lstat(),"st_file_attributes",0) & getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",0x400))
    except OSError: return False
def save_mission(mission: Mapping[str, Any], path: Any) -> dict[str, Any]:
    destination=Path(path)
    if destination.exists() and _unsafe(destination): raise ValueError("unsafe_mission_path")
    destination.parent.mkdir(parents=True,exist_ok=True)
    if _unsafe(destination.parent): raise ValueError("unsafe_mission_directory")
    value=seal_mission(mission); temporary=destination.with_name(f".{destination.name}.tmp")
    with temporary.open("w",encoding="utf-8",newline="\n") as handle:
        handle.write(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+"\n"); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary,destination); return value
def load_mission(path: Any, **validation: Any) -> dict[str, Any]:
    source=Path(path)
    if _unsafe(source): raise ValueError("unsafe_mission_path")
    try: value=json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError,UnicodeError,json.JSONDecodeError) as exc: raise ValueError("invalid_mission_json") from exc
    reasons=validate_mission(value,**validation)
    if reasons: raise ValueError(";".join(reasons))
    return value

def build_mission_evidence(mission: Mapping[str, Any]) -> dict[str, Any]:
    value=_mapping(mission); goals=value.get("goals") or {}; references=value.get("session_references") or {}
    evidence={"contract":EVIDENCE_CONTRACT,"mission_id":value.get("mission_id"),"mission_fingerprint":value.get("mission_fingerprint"),"mission_title":value.get("mission_title"),
      "created_at":value.get("created_at"),"completed_at":value.get("updated_at"),"goal_graph_fingerprint":_mapping(value.get("goal_graph")).get("graph_fingerprint"),"total_goals":len(goals),
      "completed_goals":list(value.get("completed_goal_ids") or []),"failed_goals":list(value.get("failed_goal_ids") or []),"blocked_goals":list(value.get("blocked_goal_ids") or []),"cancelled_goals":list(value.get("cancelled_goal_ids") or []),
      "goal_session_mapping":{key:[r.get("session_id") for r in refs] if isinstance(refs,list) else refs.get("session_id") for key,refs in references.items()},
      "goal_transaction_mapping":{key:_mapping(goal.get("result_summary")).get("transaction_status") for key,goal in goals.items()},"committed_goal_paths":{key:_mapping(goal.get("result_summary")).get("committed_paths",[]) for key,goal in goals.items()},
      "rolled_back_goal_paths":{key:_mapping(goal.get("result_summary")).get("rolled_back_paths",[]) for key,goal in goals.items()},"operator_actions_timeline":deepcopy(_mapping(value.get("audit_record")).get("operator_actions",[])),
      "goal_completion_order":[key for key in value.get("goal_order",[]) if key in value.get("completed_goal_ids",[])],"validation_summaries":{key:_mapping(goal.get("result_summary")).get("validation_status") for key,goal in goals.items()},
      "rollback_summaries":{key:_mapping(goal.get("result_summary")).get("rollback_status") for key,goal in goals.items()},"mission_policy":value.get("mission_policy"),"final_mission_status":value.get("mission_status"),
      "task_completed_successfully":value.get("mission_status")=="completed" and not value.get("failed_goal_ids") and not value.get("blocked_goal_ids"),"partial_completion":bool(value.get("completed_goal_ids")) and value.get("mission_status")!="completed",
      "critical_failure":any(bool(_mapping(goal.get("failure")).get("critical")) for goal in goals.values()),"audit_record":{"event_type":"runtime_mission_final_evidence","created_at":value.get("updated_at")}}
    evidence["evidence_fingerprint"]=fingerprint(evidence); return evidence

__all__=["CONTRACT","EVIDENCE_CONTRACT","INPUT_CONTRACT","TERMINAL","TRANSITIONS","build_mission_evidence","create_mission_contract","deterministic_mission_id","load_mission","save_mission","seal_mission","transition_mission","validate_mission"]
