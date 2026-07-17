from __future__ import annotations
import json
import pytest
from core.runtime.runtime_mission_model import create_mission_contract, load_mission, save_mission, transition_mission
NOW="2026-07-12T00:00:00+00:00"
def plan():return [{"goal_id":"g","goal_title":"G","goal_description":"inspect","goal_type":"inspect","priority":0,"depends_on":[],"target_scope":[],"acceptance_criteria":[],"validation_requirements":[]}]
def setup(tmp_path):
    t=tmp_path/"target";w=tmp_path/"work";t.mkdir();w.mkdir();return t,w
def test_deterministic_contract_and_transition(tmp_path):
    t,w=setup(tmp_path); a=create_mission_contract({"title":"M"},goal_plan=plan(),target_root=t,workspace_root=w,now=NOW);b=create_mission_contract({"title":"M"},goal_plan=plan(),target_root=t,workspace_root=w,now=NOW)
    assert a==b and a["contract"]=="zero.runtime.mission.v1" and a["mission_status"]=="waiting_for_plan_confirmation"
    with pytest.raises(ValueError,match="invalid_mission_transition"):transition_mission(a,"completed",now=NOW)
def test_atomic_bom_and_tamper(tmp_path):
    t,w=setup(tmp_path); value=create_mission_contract({"title":"M"},goal_plan=plan(),target_root=t,workspace_root=w,now=NOW);path=tmp_path/"m.json";save_mission(value,path)
    path.write_text("\ufeff"+path.read_text(encoding="utf-8"),encoding="utf-8");assert load_mission(path,now=NOW)["mission_id"]==value["mission_id"]
    raw=json.loads(path.read_text(encoding="utf-8-sig"));raw["mission_title"]="tampered";path.write_text(json.dumps(raw),encoding="utf-8")
    with pytest.raises(ValueError,match="fingerprint"):load_mission(path,now=NOW)
