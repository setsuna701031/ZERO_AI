from __future__ import annotations

import copy
from hashlib import sha256
from pathlib import Path

from core.runtime.runtime_active_execution_authorization import RUNTIME_ACTIVE_AUTHORIZATION_REQUEST_CONTRACT
from core.runtime.runtime_executor_admission_token import RUNTIME_OPERATOR_EXECUTION_REQUEST_CONTRACT
from core.runtime.runtime_execution_plan_review_gate import RUNTIME_EXECUTION_PLAN_OPERATOR_REVIEW_CONTRACT
from core.runtime.runtime_mission_model import load_mission
from core.runtime.runtime_mission_orchestrator import advance_mission, confirm_mission_plan, submit_mission_input
from core.runtime.runtime_natural_mission_planner import create_mission_from_planner_output, create_natural_mission_input, plan_natural_mission
from core.runtime.runtime_operator_session import INPUT_CONTRACT, fingerprint, load_runtime_session
from core.runtime.runtime_session_queue import load_scheduler_state, save_scheduler_state
from core.runtime.runtime_session_scheduler import submit_operator_input
from core.runtime.runtime_transactional_active_execution import BUNDLE_CONTRACT, REQUEST_CONTRACT
from core.runtime.runtime_worker_service import create_worker_state, run_worker_iteration, save_worker_state

NOW="2026-07-12T00:00:00+00:00"; EXPIRES="2026-07-12T00:05:00+00:00"

def _envelope(session,kind,payload,index):
    return {"contract":INPUT_CONTRACT,"session_id":session["session_id"],"input_id":f"{session['session_id']}-input-{index}","input_type":kind,"operator_id":"operator","submitted_at":NOW,"payload":copy.deepcopy(payload)}

def _security(plan):
    keys=("execution_started","mutation_started","mutation_allowed","patch_generation_allowed","patch_application_allowed","autonomous_apply_allowed","requires_controlled_executor","requires_separate_execution_step","requires_post_execution_validation","requires_rollback_capability")
    return {key:plan[key] for key in keys}

def _drive_session(scheduler_path,target,workspace,session,*,content,validation_profile="none"):
    state=load_scheduler_state(scheduler_path)
    state,session=submit_operator_input(state,_envelope(session,"proposal_approval",{"decision":"approve","expires_at":EXPIRES},1),target_root=target,workspace_root=workspace,now=NOW);save_scheduler_state(state,scheduler_path)
    plan=session["artifacts"]["execution_plan"]
    review={"contract":RUNTIME_EXECUTION_PLAN_OPERATOR_REVIEW_CONTRACT,"review_id":f"review-{session['session_id']}","plan_id":plan["plan_id"],"operator_id":"operator","decision":"approved","reviewed_at":NOW,"expires_at":EXPIRES,"acknowledged_scope":copy.deepcopy(plan["allowed_files"]),"acknowledged_constraints":copy.deepcopy(plan["execution_constraints"]),"acknowledged_security_invariants":_security(plan),"acknowledged_evidence_requirements":copy.deepcopy(plan["evidence_requirements"]),"notes":"e2e review"}
    state,session=submit_operator_input(load_scheduler_state(scheduler_path),_envelope(session,"execution_plan_review",review,2),target_root=target,workspace_root=workspace,now=NOW);save_scheduler_state(state,scheduler_path)
    reviewed=session["artifacts"]["plan_review"]
    controlled={"contract":RUNTIME_OPERATOR_EXECUTION_REQUEST_CONTRACT,"request_id":f"controlled-{session['session_id']}","review_result_id":reviewed["result_id"],"plan_id":plan["plan_id"],"operator_id":"operator","requested_mode":"controlled_dry_run","requested_at":NOW,"expires_at":EXPIRES,"acknowledged_scope":copy.deepcopy(plan["allowed_files"]),"acknowledged_dry_run":True,"acknowledged_no_file_mutation":True}
    state,session=submit_operator_input(load_scheduler_state(scheduler_path),_envelope(session,"controlled_execution_request",controlled,3),target_root=target,workspace_root=workspace,now=NOW);save_scheduler_state(state,scheduler_path)
    activation=session["artifacts"]["controlled_execution_result"]
    authorization={"contract":RUNTIME_ACTIVE_AUTHORIZATION_REQUEST_CONTRACT,"authorization_id":f"auth-{session['session_id']}","controlled_execution_result_id":activation["activation_id"],"token_id":activation["token"]["token_id"],"plan_id":activation["plan_id"],"review_result_id":activation["review_result_id"],"operator_execution_request_id":activation["operator_request_id"],"operator_id":activation["token"]["operator_id"],"decision":"authorized","authorized_mode":"prepared_active_execution","authorized_at":NOW,"expires_at":EXPIRES,"acknowledged_scope":copy.deepcopy(activation["token"]["allowed_files"]),"acknowledged_snapshot_manifest_id":activation["snapshot_manifest"]["manifest_id"],"acknowledged_validation_evidence_id":activation["validation_evidence"]["validation_evidence_id"],"acknowledged_rollback_state_id":activation["rollback_prepared_state"]["rollback_state_id"],"acknowledged_risks":["manual_active_boundary_required"],"acknowledged_no_automatic_commit":True,"acknowledged_manual_rollback_authority":True}
    state,session=submit_operator_input(load_scheduler_state(scheduler_path),_envelope(session,"active_execution_authorization",authorization,4),target_root=target,workspace_root=workspace,now=NOW);save_scheduler_state(state,scheduler_path)
    auth=session["artifacts"]["active_authorization_result"];scope=auth["authorized_scope"];files=[]
    for relative in scope:
        path=target/relative;before_bytes=path.read_bytes() if path.exists() else None;expected={"expected_exists":before_bytes is not None}
        if before_bytes is not None:expected.update(expected_sha256=sha256(before_bytes).hexdigest(),expected_size=len(before_bytes))
        files.append({"relative_path":relative,"operation":"replace" if before_bytes is not None else "create","expected_pre_state":expected,"candidate_content_encoding":"utf-8","candidate_content":content,"candidate_content_hash":sha256(content.encode()).hexdigest(),"maximum_size":100000,"validation_requirements":[]})
    bundle={"contract":BUNDLE_CONTRACT,"candidate_bundle_id":f"bundle-{session['session_id']}","plan_id":auth["plan_id"],"authorization_result_id":auth["authorization_result_id"],"target_root_identity":session["target_root_identity"],"scope_fingerprint":fingerprint(scope),"created_at":NOW,"expires_at":EXPIRES,"files":files,"validation_profile_id":validation_profile,"project_validation_required":validation_profile!="none","approved_test_files":[],"validation_scope":[]}
    bundle["bundle_fingerprint"]=fingerprint(bundle)
    state,session=submit_operator_input(load_scheduler_state(scheduler_path),_envelope(session,"candidate_bundle",bundle,5),target_root=target,workspace_root=workspace,now=NOW);save_scheduler_state(state,scheduler_path)
    auth=session["artifacts"]["active_authorization_result"]
    invocation={"contract":REQUEST_CONTRACT,"invocation_request_id":f"invoke-{session['session_id']}","authorization_result_id":auth["authorization_result_id"],"authorization_id":auth["authorization_id"],"controlled_execution_result_id":auth["controlled_execution_result_id"],"token_id":auth["token_id"],"plan_id":auth["plan_id"],"review_result_id":auth["review_result_id"],"operator_id":auth["operator_id"],"requested_mode":"transactional_active_execution","requested_at":NOW,"expires_at":EXPIRES,"target_root_identity":session["target_root_identity"],"acknowledged_scope":scope,"candidate_bundle_id":bundle["candidate_bundle_id"],"candidate_bundle_fingerprint":bundle["bundle_fingerprint"],"validation_profile_id":validation_profile,"acknowledged_transactional_execution":True,"acknowledged_automatic_rollback":True,"acknowledged_no_git_commit":True,"acknowledged_no_scope_expansion":True}
    state,session=submit_operator_input(load_scheduler_state(scheduler_path),_envelope(session,"transactional_invocation",invocation,6),target_root=target,workspace_root=workspace,now=NOW);save_scheduler_state(state,scheduler_path)
    return session

def _setup(tmp_path,filename="README.md"):
    target=tmp_path/"target";workspace=tmp_path/"workspace";target.mkdir();workspace.mkdir();(target/filename).write_text("initial\n",encoding="utf-8")
    mission_path=tmp_path/"mission.json";scheduler=tmp_path/"scheduler.json"
    natural=create_natural_mission_input("Inspect the approved file, modify its documentation, and finally validate the result",operator_id="operator",target_root=target,workspace_root=workspace,requested_scope=[filename],acceptance_hints=["approved file updated"],validation_hints=["validation evidence recorded"],now=NOW)
    planned=plan_natural_mission(natural,target_root=target,workspace_root=workspace,now=NOW)
    mission=create_mission_from_planner_output(natural,planned["planner_output"],planning_request=planned["planning_request"],target_root=target,workspace_root=workspace,mission_path=mission_path,scheduler_state_path=scheduler,now=NOW)
    return target,workspace,mission_path,scheduler,natural,planned,mission

def _confirm(mission,planned):
    graph=mission["goal_graph"];summary=mission["planner_output_summary"]
    payload={"graph_fingerprint":graph["graph_fingerprint"],"goal_ids":graph["goal_ids"],"goal_order":graph["goal_order"],"total_goal_count":len(mission["goals"]),"operator_acknowledgment":True,"natural_request_id":mission["natural_mission_request_reference"]["request_id"],"planner_output_id":mission["planner_output_reference"]["planner_output_id"],"planner_output_fingerprint":mission["planner_output_reference"]["fingerprint"],"included_scope":summary["included_scope"],"excluded_scope":summary["excluded_scope"],"risk_summary":summary["risk_summary"],"operator_boundaries":summary["operator_boundaries"]}
    envelope={"contract":"zero.runtime.mission_input.v1","mission_id":mission["mission_id"],"input_id":"confirm-plan","input_type":"confirm_goal_plan","operator_id":"operator","submitted_at":NOW,"payload":payload}
    return confirm_mission_plan(mission,envelope,now=NOW)

def test_natural_mission_full_controlled_success_and_reload(tmp_path):
    target,workspace,mission_path,scheduler,natural,planned,mission=_setup(tmp_path);before=(target/"README.md").read_bytes()
    assert mission["mission_status"]=="waiting_for_plan_confirmation" and not mission["session_references"] and not load_scheduler_state(scheduler)["entries"] and (target/"README.md").read_bytes()==before
    assert planned["planner_output"]["goal_order"]==[g["provisional_goal_id"] for g in planned["planner_output"]["goals"]]
    mission=_confirm(mission,planned);config={"target_root":target,"workspace_root":workspace};worker_path=tmp_path/"worker.json"
    completed=0
    while mission["mission_status"]!="completed":
        mission=advance_mission(mission,scheduler_state=scheduler,now=NOW,runtime_config=config);goal_id=mission["waiting_goal_ids"][0];session=load_runtime_session(mission["goals"][goal_id]["session_path"],target_root=target,workspace_root=workspace,now=NOW)
        if not worker_path.exists():save_worker_state(create_worker_state(scheduler_state_path=scheduler,worker_state_path=worker_path,worker_name="e2e-worker",target_root=target,now=NOW),worker_path)
        worker=run_worker_iteration(scheduler_state_path=scheduler,worker_state_path=worker_path,worker_name="e2e-worker",target_root=target,workspace_root=workspace,now=NOW);assert worker["loop_iteration"]>=1
        content="updated documentation\n" if mission["goals"][goal_id]["goal_type"] in {"modify","document"} else (target/"README.md").read_text(encoding="utf-8")
        session=_drive_session(scheduler,target,workspace,session,content=content);assert session["artifacts"]["transaction_result"]["transaction_status"]=="committed" and session["artifacts"]["controlled_execution_result"]["validation_evidence"]
        completed+=1;mission=advance_mission(mission,scheduler_state=scheduler,now=NOW,runtime_config=config)
    assert completed==3 and mission["completed_goal_ids"]==mission["goal_order"] and mission["mission_evidence"]["task_completed_successfully"] is True
    reloaded=load_mission(mission_path,now=NOW);assert reloaded["planner_output_reference"]==mission["planner_output_reference"] and reloaded["mission_fingerprint"]==mission["mission_fingerprint"] and reloaded["checkpoints"]

def test_validation_failure_requires_confirmed_replan_before_new_session(tmp_path):
    target,workspace,mission_path,scheduler,natural,planned,mission=_setup(tmp_path,"module.py");mission=_confirm(mission,planned);config={"target_root":target,"workspace_root":workspace}
    mission=advance_mission(mission,scheduler_state=scheduler,now=NOW,runtime_config=config);first_id=mission["waiting_goal_ids"][0];first=_drive_session(scheduler,target,workspace,load_runtime_session(mission["goals"][first_id]["session_path"],now=NOW),content="x = 1\n",validation_profile="python_compile");assert first["artifacts"]["transaction_result"]["transaction_status"]=="committed"
    mission=advance_mission(mission,scheduler_state=scheduler,now=NOW,runtime_config=config);second_id=mission["waiting_goal_ids"][0];second=_drive_session(scheduler,target,workspace,load_runtime_session(mission["goals"][second_id]["session_path"],now=NOW),content="def broken(:\n",validation_profile="python_compile");assert second["artifacts"]["transaction_result"]["transaction_status"]=="rolled_back"
    mission=advance_mission(mission,scheduler_state=scheduler,now=NOW,runtime_config=config);completed_snapshot=copy.deepcopy(mission["goals"][first_id]);old_sessions=sum(len(v) for v in mission["session_references"].values())
    request={"contract":"zero.runtime.mission_input.v1","mission_id":mission["mission_id"],"input_id":"request-replan","input_type":"request_replan","operator_id":"operator","submitted_at":NOW,"payload":{"operator_instruction":"Replace the failed goal using sealed validation evidence","allowed_revision_scope":["module.py"]}}
    mission=submit_mission_input(mission,request,now=NOW);assert mission["mission_status"]=="waiting_for_replan_confirmation" and mission["goals"][first_id]==completed_snapshot and sum(len(v) for v in mission["session_references"].values())==old_sessions
    current=mission["replanning_history"][-1];out=current["output"];req=current["request"]
    payload={"revision_number":out["revision_number"],"old_graph_fingerprint":req["current_graph_fingerprint"],"unchanged_goal_ids":out["unchanged_goal_ids"],"completed_goal_ids":req["completed_goal_ids"],"removed_goal_ids":out["removed_goal_ids"],"added_goal_ids":[g["provisional_goal_id"] for g in out["added_goals"]],"scope_delta":out["scope_delta"],"risk_delta":out["risk_delta"],"operator_acknowledgment":True}
    confirm={"contract":"zero.runtime.mission_input.v1","mission_id":mission["mission_id"],"input_id":"confirm-replan","input_type":"confirm_replan","operator_id":"operator","submitted_at":NOW,"payload":payload}
    mission=submit_mission_input(mission,confirm,now=NOW);assert mission["immutable_completed_goal_ids"]==[first_id] and mission["goals"][first_id]["result_summary"]["transaction_status"]=="committed"
    mission=advance_mission(mission,scheduler_state=scheduler,now=NOW,runtime_config=config);assert sum(len(v) for v in mission["session_references"].values())>old_sessions
