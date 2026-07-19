from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_planning_common import fingerprint,stable_id
VALIDATION_CATEGORIES=("contract compatibility","deterministic output verification","focused regression","integration validation","manual review","read-only boundary verification","repository consistency validation","schema validation","unit test")
def build_engineering_validation_strategy(goals:list[Mapping[str,Any]],work_items:list[Mapping[str,Any]])->list[dict[str,Any]]:
 out=[]
 for item in sorted(work_items,key=lambda x:x["work_item_id"]):
  for category in ("schema validation","deterministic output verification","read-only boundary verification"):
   material={"target_ids":[item["goal_id"],item["work_item_id"]],"category":category,"objective":f"Verify {category} for the bounded work item","evidence_required":["recorded validation result"],"pass_criteria":["all bounded assertions pass"],"fail_criteria":["any bounded assertion fails or evidence is missing"],"bounded_command_description":"Run the focused validation selected by a later governed implementation boundary","estimated_cost_category":"focused","long_running":False}
   value={**material,"validation_id":stable_id("engineering-validation-",material)};value["fingerprint"]=fingerprint(value);out.append(value)
 return sorted(out,key=lambda x:x["validation_id"])
build_validation_strategy=build_engineering_validation_strategy
__all__=["VALIDATION_CATEGORIES","build_engineering_validation_strategy","build_validation_strategy"]
