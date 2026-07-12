from __future__ import annotations
import copy
import pytest
from core.runtime.runtime_natural_mission_planner import *
NOW="2026-07-12T00:00:00+00:00"
def roots(tmp_path):t=tmp_path/"target";w=tmp_path/"work";t.mkdir();w.mkdir();return t,w
def natural(tmp_path,text="Inspect README, update documentation, finally validate tests",scope=None):
 t,w=roots(tmp_path);return t,w,create_natural_mission_input(text,operator_id="operator",target_root=t,workspace_root=w,requested_scope=scope or [],now=NOW)
def test_deterministic_ids_rule_plan_and_input_unchanged(tmp_path):
 t,w,n=natural(tmp_path);original=copy.deepcopy(n);a=plan_natural_mission(n,target_root=t,workspace_root=w,now=NOW);b=plan_natural_mission(n,target_root=t,workspace_root=w,now=NOW)
 assert a==b and n==original and a["planning_request"]["contract"]==PLANNING_REQUEST_CONTRACT and a["planner_output"]["contract"]==PLANNER_OUTPUT_CONTRACT
 assert [g["goal_type"] for g in a["planner_output"]["goals"]]==["inspect","document","validate"]
 assert a["planner_output"]["goals"][-1]["depends_on"]
def test_scope_conflict_empty_and_expired_rejected(tmp_path):
 t,w=roots(tmp_path)
 with pytest.raises(ValueError,match="empty"):create_natural_mission_input("",operator_id="op",target_root=t,workspace_root=w,now=NOW)
 with pytest.raises(ValueError,match="operator"):create_natural_mission_input("inspect",operator_id="",target_root=t,workspace_root=w,now=NOW)
 with pytest.raises(ValueError,match="conflict"):create_natural_mission_input("inspect",operator_id="op",target_root=t,workspace_root=w,requested_scope=["docs"],excluded_scope=["docs/private"],now=NOW)
def test_clarification_injected_provider_and_invalid_output(tmp_path):
 t,w,n=natural(tmp_path,text="do something") ;result=plan_natural_mission(n,target_root=t,workspace_root=w,now=NOW);assert result["planner_output"]["plan_status"]=="clarification_required"
 def bad(req):return {"contract":PLANNER_OUTPUT_CONTRACT}
 with pytest.raises(ValueError):plan_natural_mission(n,target_root=t,workspace_root=w,planner_provider=bad,now=NOW)
def test_context_bounds_binary_and_scope_preserved(tmp_path):
 t,w,n=natural(tmp_path,scope=["README.md"]);(t/"README.md").write_text("small",encoding="utf8");(t/"binary.bin").write_bytes(b"a\0b")
 context=collect_repository_context(t,["README.md"]);assert context["file_count"]==1
 result=plan_natural_mission(n,target_root=t,workspace_root=w,repository_context=context,now=NOW);assert result["planner_output"]["scope_summary"]["included"]==["README.md"]
def test_executable_provider_goal_rejected(tmp_path):
 t,w,n=natural(tmp_path);req=create_planning_request(n,now=NOW);out=deterministic_rule_planner(req);out["goals"][0]["command"]="forbidden";out["planner_output_fingerprint"]=__import__('core.runtime.runtime_operator_session',fromlist=['fingerprint']).fingerprint({k:v for k,v in out.items() if k!='planner_output_fingerprint'})
 assert "executable_planner_goal_forbidden" in validate_planner_output(out,req,now=NOW)
