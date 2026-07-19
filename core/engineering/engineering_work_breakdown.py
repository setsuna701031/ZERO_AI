from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_planning_common import ALLOWED_ACTIONS,FORBIDDEN_ACTIONS,fingerprint,stable_id

def build_engineering_work_breakdown(goals:list[Mapping[str,Any]])->list[dict[str,Any]]:
    if not isinstance(goals,list) or not goals: raise ValueError("goals_required")
    out=[]
    for goal in goals:
        if not goal.get("goal_id") or not goal.get("source_evidence_references"): raise ValueError("invalid_goal")
        material={"goal_id":goal["goal_id"],"title":"Deliver: "+goal["title"],"objective":goal["desired_outcome"],"inputs":[goal["goal_id"]],"expected_outputs":["implementation artifact","validation evidence"],"repository_areas":sorted(goal["affected_components"]),"preconditions":["later governed authorization if mutation is required"],"completion_criteria":sorted(goal["validation_expectations"]),"validation_requirements":sorted(goal["validation_expectations"]),"estimated_complexity_category":"bounded","allowed_actions":list(ALLOWED_ACTIONS),"forbidden_actions":list(FORBIDDEN_ACTIONS),"evidence_references":sorted(goal["source_evidence_references"])}
        item={**material,"work_item_id":stable_id("engineering-work-item-",material)};item["fingerprint"]=fingerprint(item);out.append(item)
    return sorted(out,key=lambda x:x["work_item_id"])

build_work_breakdown=build_engineering_work_breakdown
__all__=["build_engineering_work_breakdown","build_work_breakdown"]
