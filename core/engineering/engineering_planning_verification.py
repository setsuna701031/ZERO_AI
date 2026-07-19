from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_planning_common import ValidationResult,planning_artifact,validate_planning_artifact
from core.engineering.engineering_plan import validate_engineering_plan
SCHEMA="zero.engineering.planning_verification.v1";ID_KEY="verification_id";PREFIX="engineering-planning-verification-";FIELDS={"engineering_plan_id","checks","errors","warnings"}
def verify_engineering_plan(plan:Mapping[str,Any])->dict[str,Any]:
 errors=[]; warnings=[]; goals=plan.get("goals",[]);work=plan.get("work_breakdown",[]);graph=plan.get("dependency_ordering",{});valid_goal_ids={x.get("goal_id") for x in goals};valid_work_ids={x.get("work_item_id") for x in work};refs=set(plan.get("planning_context",{}).get("evidence_references",[]))
 def check(name,ok,error):
  if not ok:errors.append(error)
  return {"name":name,"passed":bool(ok)}
 base=validate_engineering_plan(plan).valid
 checks=[check("schema_ids_fingerprints",base,"invalid_plan_contract"),check("closure_repository_revision_linkage",plan.get("repository_linkage")==plan.get("planning_context",{}).get("repository_identity") and plan.get("analysis_closure_linkage",{}).get("analyzed_revision")==plan.get("planning_context",{}).get("analyzed_revision"),"repository_linkage_mismatch"),check("goal_evidence",bool(goals) and all(set(x.get("source_evidence_references",[]))<=refs and x.get("source_evidence_references") for x in goals),"goal_evidence_missing"),check("work_goal_linkage",all(x.get("goal_id") in valid_goal_ids for x in work),"orphan_work_item"),check("dependency_nodes",set(graph.get("nodes",[]))==valid_work_ids,"missing_dependency_node"),check("dependency_cycle",graph.get("cycle_status")=="acyclic","dependency_cycle"),check("deterministic_order",set(graph.get("execution_order",[]))==valid_work_ids,"invalid_execution_order"),check("validation_coverage",all(any(x.get("work_item_id") in v.get("target_ids",[]) for v in plan.get("validation_strategy",[])) for x in work),"validation_coverage_missing"),check("scope_containment",all(set(x.get("repository_areas",[]))<=set(plan.get("planning_context",{}).get("allowed_scope",[])) for x in work),"scope_expansion"),check("authority_absence",all(plan.get("planning_invariants",{}).get(k) is True for k in ("no_execution_authority","no_mutation_authority","no_approval_authority")),"forbidden_authority")]
 blocking=any(x.get("blocking_status")=="blocking" for x in plan.get("risk_assessment",[]));checks.append({"name":"blocking_risks","passed":not blocking})
 status="invalid" if errors else ("blocked" if blocking else "verified")
 return planning_artifact(SCHEMA,status,{"engineering_plan_id":plan.get("engineering_plan_id"),"checks":checks,"errors":sorted(set(errors)),"warnings":warnings},ID_KEY,PREFIX)
def validate_engineering_planning_verification(v:Any)->ValidationResult:return validate_planning_artifact(v,schema=SCHEMA,statuses={"verified","blocked","invalid"},id_key=ID_KEY,prefix=PREFIX,fields=FIELDS)
verify_planning=verify_engineering_plan
__all__=["validate_engineering_planning_verification","verify_engineering_plan","verify_planning"]
