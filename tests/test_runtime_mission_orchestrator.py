from __future__ import annotations
from pathlib import Path
from core.runtime.runtime_mission_orchestrator import advance_mission, confirm_mission_plan, create_mission
from core.runtime.runtime_session_queue import load_scheduler_state
NOW="2026-07-12T00:00:00+00:00"
def plan():return [{"goal_id":"g1","goal_title":"One","goal_description":"inspect one","goal_type":"inspect","priority":10,"depends_on":[],"target_scope":[],"acceptance_criteria":[],"validation_requirements":[]},{"goal_id":"g2","goal_title":"Two","goal_description":"inspect two","goal_type":"validate","priority":0,"depends_on":["g1"],"target_scope":[],"acceptance_criteria":[],"validation_requirements":[]}]
def test_confirmation_session_enqueue_and_idempotency(tmp_path):
    target=tmp_path/"target";workspace=tmp_path/"workspace";target.mkdir();workspace.mkdir();mission_path=tmp_path/"mission.json";scheduler=tmp_path/"scheduler.json"
    mission=create_mission({"title":"M"},goal_plan=plan(),target_root=target,workspace_root=workspace,mission_path=mission_path,scheduler_state_path=scheduler,now=NOW)
    assert mission["mission_status"]=="waiting_for_plan_confirmation" and not mission["session_references"]
    graph=mission["goal_graph"]; envelope={"contract":"zero.runtime.mission_input.v1","mission_id":mission["mission_id"],"input_id":"confirm-1","input_type":"confirm_goal_plan","operator_id":"operator","submitted_at":NOW,"payload":{"graph_fingerprint":graph["graph_fingerprint"],"goal_ids":graph["goal_ids"],"goal_order":graph["goal_order"],"total_goal_count":2,"operator_acknowledgment":True}}
    mission=confirm_mission_plan(mission,envelope,now=NOW);assert mission["mission_status"]=="ready"
    config={"target_root":target,"workspace_root":workspace};mission=advance_mission(mission,scheduler_state=scheduler,now=NOW,runtime_config=config)
    assert mission["waiting_goal_ids"]==["g1"] and mission["goals"]["g2"]["session_id"] is None
    first=mission["goals"]["g1"]["session_id"]; mission=advance_mission(mission,scheduler_state=scheduler,now=NOW,runtime_config=config)
    assert mission["goals"]["g1"]["session_id"]==first and len(load_scheduler_state(scheduler)["entries"])==1
