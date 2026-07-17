from __future__ import annotations
import copy
import pytest
from core.runtime.runtime_goal_graph import MAX_GOALS, build_goal_graph, ready_goal_ids, stable_topological_order

def goal(name, deps=None, priority=0):
    return {"goal_id":name,"goal_title":name,"goal_description":f"do {name}","goal_type":"inspect","goal_status":"pending","priority":priority,"depends_on":deps or [],"target_scope":[],"required_capabilities":[],"acceptance_criteria":[],"validation_requirements":[]}
def test_empty_cycle_missing_and_self_rejected():
    with pytest.raises(ValueError,match="empty"):build_goal_graph([],mission_id="m")
    with pytest.raises(ValueError,match="self"):build_goal_graph([goal("a",["a"])],mission_id="m")
    with pytest.raises(ValueError,match="missing"):build_goal_graph([goal("a",["x"])],mission_id="m")
    with pytest.raises(ValueError,match="cycle"):build_goal_graph([goal("a",["b"]),goal("b",["a"])],mission_id="m")
def test_stable_fan_in_ready_and_input_unchanged():
    source=[goal("a",priority=1),goal("b"),goal("c",["a","b"])] ; original=copy.deepcopy(source)
    result=build_goal_graph(source,mission_id="m")
    assert result["goal_order"]==["a","b","c"] and ready_goal_ids(result["goals"])==["a","b"] and source==original
    assert stable_topological_order(result["goals"])==result["goal_order"]
def test_duplicate_and_executable_fields_rejected():
    with pytest.raises(ValueError,match="duplicate_goal_id"):build_goal_graph([goal("a"),goal("a")],mission_id="m")
    item=goal("a");item["command"]="echo no"
    with pytest.raises(ValueError,match="forbidden"):build_goal_graph([item],mission_id="m")
def test_size_limit():
    with pytest.raises(ValueError,match="limit"):build_goal_graph([goal(str(i)) for i in range(MAX_GOALS+1)],mission_id="m")
