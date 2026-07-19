from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_proposal_common import fingerprint,stable_proposal_id
def build_engineering_proposal_validation_plan(changes:list[Mapping[str,Any]],intent:Mapping[str,Any]|None=None)->list[dict[str,Any]]:
 specs=(intent or {}).get("validations");out=[]
 if specs is None:
  specs=[{"target_proposed_change_ids":[x["proposed_change_id"]],"source_planning_validation_ids":["opaque-validation-link-"+x["work_item_id"]],"category":"contract compatibility","validation_objective":"Verify the proposed change remains within the sealed plan and frozen contracts"} for x in changes]
 for spec in specs:
  targets=sorted(set(spec.get("target_proposed_change_ids",[])));valid={x["proposed_change_id"] for x in changes}
  if not targets or not set(targets)<=valid:raise ValueError("validation_target_invalid")
  material={"target_proposed_change_ids":targets,"source_planning_validation_ids":sorted(set(spec.get("source_planning_validation_ids",[]))),"category":spec.get("category","manual review"),"validation_objective":str(spec.get("validation_objective","")).strip(),"evidence_required":sorted(set(spec.get("evidence_required",["recorded review evidence"]))),"pass_criteria":sorted(set(spec.get("pass_criteria",["bounded criteria satisfied"]))),"fail_criteria":sorted(set(spec.get("fail_criteria",["criteria failure or missing evidence"]))),"bounded_validation_description":str(spec.get("bounded_validation_description","Perform the bounded validation in a later governed environment")),"expected_environment_category":spec.get("expected_environment_category","governed_review"),"estimated_cost_category":spec.get("estimated_cost_category","focused"),"long_running":bool(spec.get("long_running",False)),"required_before_approval":bool(spec.get("required_before_approval",True)),"required_before_authorization":bool(spec.get("required_before_authorization",True)),"required_after_implementation":bool(spec.get("required_after_implementation",True))}
  if not material["source_planning_validation_ids"] or not material["validation_objective"]:raise ValueError("validation_evidence_missing")
  value={**material,"proposal_validation_id":stable_proposal_id("engineering-proposal-validation-",material)};value["fingerprint"]=fingerprint(value);out.append(value)
 return sorted(out,key=lambda x:x["proposal_validation_id"])
build_proposal_validation_plan=build_engineering_proposal_validation_plan
__all__=["build_engineering_proposal_validation_plan","build_proposal_validation_plan"]
