from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_planning_common import ValidationResult,planning_artifact,validate_planning_artifact
from core.engineering.engineering_plan import validate_engineering_plan
from core.engineering.engineering_planning_verification import validate_engineering_planning_verification
SCHEMA="zero.engineering.planning_closure.v1";ID_KEY="planning_closure_id";PREFIX="engineering-planning-closure-";FIELDS={"engineering_plan_id","engineering_plan_fingerprint","verification_id","verification_fingerprint","repository_identity","analyzed_revision","planning_summary","unresolved_risks","blocked_items","next_boundary_declaration"}
NEXT={"permitted_destination":"governed proposal preparation or implementation intake boundary","proposal_created":False,"mutation_authorized":False,"executor_authorized":False,"approval_authorized":False,"authorization_granted":False}
def build_engineering_planning_closure(plan:Mapping[str,Any],verification:Mapping[str,Any])->dict[str,Any]:
 plan_ok=validate_engineering_plan(plan).valid;verification_ok=validate_engineering_planning_verification(verification).valid and verification.get("engineering_plan_id")==plan.get("engineering_plan_id")
 blocking=[x for x in plan.get("risk_assessment",[]) if x.get("blocking_status")=="blocking"]
 status="closed" if plan_ok and verification_ok and verification.get("status")=="verified" and not blocking else ("blocked" if blocking or verification.get("status")=="blocked" else ("insufficient_evidence" if plan.get("status")=="insufficient_evidence" else "invalid"))
 payload={"engineering_plan_id":plan.get("engineering_plan_id"),"engineering_plan_fingerprint":plan.get("fingerprint"),"verification_id":verification.get("verification_id"),"verification_fingerprint":verification.get("fingerprint"),"repository_identity":plan.get("repository_linkage"),"analyzed_revision":plan.get("analysis_closure_linkage",{}).get("analyzed_revision"),"planning_summary":{"goal_count":len(plan.get("goals",[])),"work_item_count":len(plan.get("work_breakdown",[])),"validation_count":len(plan.get("validation_strategy",[])),"risk_count":len(plan.get("risk_assessment",[]))},"unresolved_risks":[x.get("risk_id") for x in plan.get("risk_assessment",[]) if x.get("residual_risk") not in {None,"none"}],"blocked_items":plan.get("dependency_ordering",{}).get("blocked_items",[]),"next_boundary_declaration":dict(NEXT)}
 return planning_artifact(SCHEMA,status,payload,ID_KEY,PREFIX)
def validate_engineering_planning_closure(v:Any)->ValidationResult:return validate_planning_artifact(v,schema=SCHEMA,statuses={"closed","blocked","invalid","insufficient_evidence"},id_key=ID_KEY,prefix=PREFIX,fields=FIELDS)
build_planning_closure=build_engineering_planning_closure
__all__=["build_engineering_planning_closure","build_planning_closure","validate_engineering_planning_closure"]
