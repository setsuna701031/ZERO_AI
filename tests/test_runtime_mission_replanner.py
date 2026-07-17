from __future__ import annotations
import pytest
from core.runtime.runtime_mission_model import seal_mission
from core.runtime.runtime_mission_orchestrator import create_mission
from core.runtime.runtime_mission_replanner import *
NOW="2026-07-12T00:00:00+00:00"
def mission(tmp_path):
 t=tmp_path/"t";w=tmp_path/"w";t.mkdir();w.mkdir();g=[{"goal_id":"done","goal_title":"Done","goal_description":"done","goal_type":"inspect","priority":0,"depends_on":[],"target_scope":["README.md"],"acceptance_criteria":["ok"],"validation_requirements":["check"]},{"goal_id":"bad","goal_title":"Bad","goal_description":"bad","goal_type":"modify","priority":0,"depends_on":["done"],"target_scope":["README.md"],"acceptance_criteria":["ok"],"validation_requirements":["check"]}]
 m=create_mission({"title":"M"},goal_plan=g,target_root=t,workspace_root=w,mission_path=tmp_path/"m.json",scheduler_state_path=tmp_path/"s.json",now=NOW);m["mission_status"]="failed";m["goals"]["done"]["goal_status"]="completed";m["goals"]["done"]["result_summary"]={"transaction_status":"committed"};m["goals"]["bad"]["goal_status"]="failed";m["goals"]["bad"]["failure"]={"reasons":["validation"]};m["completed_goal_ids"]=["done"];m["failed_goal_ids"]=["bad"];m["planner_output_scope"]=["README.md"];return seal_mission(m)
def test_deterministic_request_output_and_immutable_completed(tmp_path):
 m=mission(tmp_path);r=create_replanning_request(m,operator_instruction="replan",now=NOW);r2=create_replanning_request(m,operator_instruction="replan",now=NOW);assert r==r2
 out=deterministic_replanner(r,m);assert out["preserved_completed_goals"]==["done"] and "done" not in out["removed_goal_ids"] and not validate_replanner_output(out,r,m,now=NOW)
 staged=stage_replan(m,r,out,now=NOW);assert staged["mission_status"]=="waiting_for_replan_confirmation" and staged["replan_required"]
def test_completed_cancelled_and_critical_rejected(tmp_path):
 m=mission(tmp_path);m["mission_status"]="completed"
 with pytest.raises(ValueError,match="not_replannable"):create_replanning_request(seal_mission(m),operator_instruction="x",now=NOW)
 second=tmp_path/"second";second.mkdir();m=mission(second);m["goals"]["bad"]["failure"]["critical"]=True
 with pytest.raises(ValueError,match="critical"):create_replanning_request(seal_mission(m),operator_instruction="x",now=NOW)
def test_scope_expansion_and_executable_rejected(tmp_path):
 m=mission(tmp_path);r=create_replanning_request(m,operator_instruction="x",allowed_revision_scope=["README.md"],now=NOW);out=deterministic_replanner(r,m);out["replacement_goals"][0]["target_scope"]=["src/new.py"];out["replacement_goals"][0]["command"]="x"
 from core.runtime.runtime_operator_session import fingerprint
 out["output_fingerprint"]=fingerprint({k:v for k,v in out.items() if k!="output_fingerprint"});reasons=validate_replanner_output(out,r,m,now=NOW);assert "replan_scope_expansion" in reasons and "executable_replanner_goal_forbidden" in reasons
