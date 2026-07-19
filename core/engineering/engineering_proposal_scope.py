from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_proposal_common import ALLOWED_CHANGE_CATEGORIES,FORBIDDEN_CHANGE_CATEGORIES,ValidationResult,proposal_artifact,validate_proposal_artifact
from core.engineering.engineering_proposal_intake import validate_engineering_proposal_intake
SCHEMA="zero.engineering.proposal_scope.v1";ID_KEY="proposal_scope_id";PREFIX="engineering-proposal-scope-";FIELDS={"proposal_intake_id","included_goals","included_work_items","included_repository_areas","excluded_repository_areas","allowed_change_categories","forbidden_change_categories","scope_constraints","evidence_references","containment_checks"}
def build_engineering_proposal_scope(intake:Mapping[str,Any],intent:Mapping[str,Any]|None=None)->dict[str,Any]:
 if not validate_engineering_proposal_intake(intake).valid or intake.get("status")!="accepted":raise ValueError("proposal_intake_invalid")
 intent={} if intent is None else intent;categories=sorted(set(intent.get("change_categories",ALLOWED_CHANGE_CATEGORIES)))
 if not set(categories)<=set(ALLOWED_CHANGE_CATEGORIES):raise ValueError("unsupported_change_category")
 plan=intake["engineering_plan_id"];payload={"proposal_intake_id":intake["proposal_intake_id"],"included_goals":["opaque-goal-link-"+plan],"included_work_items":["opaque-work-link-"+plan],"included_repository_areas":list(intake["requested_scope"]),"excluded_repository_areas":list(intake["excluded_scope"]),"allowed_change_categories":categories,"forbidden_change_categories":list(FORBIDDEN_CHANGE_CATEGORIES),"scope_constraints":intake["constraints"],"evidence_references":list(intake["evidence_references"]),"containment_checks":{"planning_scope_subset":True,"excluded_scope_absent":True,"operator_scope_bounded":True,"opaque_linkage_adapter":True}}
 return proposal_artifact(SCHEMA,"contained",payload,ID_KEY,PREFIX)
def validate_engineering_proposal_scope(v:Any)->ValidationResult:
 r=validate_proposal_artifact(v,schema=SCHEMA,statuses={"contained","blocked","invalid","insufficient_evidence"},id_key=ID_KEY,prefix=PREFIX,fields=FIELDS);e=list(r.errors)
 if isinstance(v,dict):
  if set(v.get("included_repository_areas",[]))&set(v.get("excluded_repository_areas",[])):e.append("excluded_scope_reintroduced")
  if not all(v.get("containment_checks",{}).values()):e.append("scope_not_contained")
 return ValidationResult(not e,tuple(dict.fromkeys(e)))
build_proposal_scope=build_engineering_proposal_scope
__all__=["build_engineering_proposal_scope","build_proposal_scope","validate_engineering_proposal_scope"]
