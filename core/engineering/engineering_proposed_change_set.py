from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_proposal_common import ALLOWED_CHANGE_CATEGORIES,fingerprint,stable_proposal_id
from core.engineering.engineering_proposal_scope import validate_engineering_proposal_scope
def build_engineering_proposed_change_set(scope:Mapping[str,Any],intent:Mapping[str,Any]|None=None)->list[dict[str,Any]]:
 if not validate_engineering_proposal_scope(scope).valid or scope.get("status")!="contained":raise ValueError("proposal_scope_invalid")
 intent={} if intent is None else intent;specs=intent.get("changes")
 if specs is None:specs=[{"goal_id":scope["included_goals"][0],"work_item_id":scope["included_work_items"][0],"change_category":scope["allowed_change_categories"][0],"target_repository_area":scope["included_repository_areas"][0],"change_objective":"Represent the sealed plan as a bounded change intention","current_state_evidence":scope["evidence_references"]}]
 if not isinstance(specs,list) or not specs:raise ValueError("proposed_changes_required")
 out=[]
 for spec in specs:
  if not isinstance(spec,Mapping) or set(spec)&{"patch","diff","before","after","source_content","command","executable_command"}:raise ValueError("forbidden_change_payload")
  refs=sorted(set(spec.get("current_state_evidence",[])));goal=spec.get("goal_id");work=spec.get("work_item_id");area=spec.get("target_repository_area");category=spec.get("change_category")
  if goal not in scope["included_goals"] or work not in scope["included_work_items"]:raise ValueError("planning_linkage_mismatch")
  if area not in scope["included_repository_areas"] or category not in ALLOWED_CHANGE_CATEGORIES or category not in scope["allowed_change_categories"]:raise ValueError("unsupported_proposed_change")
  if not refs or not set(refs)<=set(scope["evidence_references"]):raise ValueError("change_evidence_missing")
  material={"proposal_scope_id":scope["proposal_scope_id"],"goal_id":goal,"work_item_id":work,"change_category":category,"target_repository_area":area,"change_objective":str(spec.get("change_objective","")).strip(),"current_state_evidence":refs,"desired_state_description":str(spec.get("desired_state_description","A reviewable outcome consistent with the sealed engineering plan")),"constraints":scope["scope_constraints"],"expected_artifacts":sorted(set(spec.get("expected_artifacts",["implementation artifact","validation evidence"]))),"compatibility_considerations":sorted(set(spec.get("compatibility_considerations",["preserve frozen contracts"]))),"validation_references":[],"risk_references":[],"implementation_authority":"not_granted","mutation_authority":"not_granted","status":"proposed"}
  if not material["change_objective"]:raise ValueError("unsupported_proposed_change")
  item={**material,"proposed_change_id":stable_proposal_id("engineering-proposed-change-",material)};item["fingerprint"]=fingerprint(item);out.append(item)
 return sorted(out,key=lambda x:x["proposed_change_id"])
build_proposed_change_set=build_engineering_proposed_change_set
__all__=["build_engineering_proposed_change_set","build_proposed_change_set"]
