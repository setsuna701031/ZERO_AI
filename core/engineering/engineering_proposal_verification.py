from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_proposal import INVARIANTS,validate_engineering_proposal
from core.engineering.engineering_proposal_common import ValidationResult,contains_forbidden_payload,fingerprint,proposal_artifact,stable_proposal_id,validate_proposal_artifact
from core.engineering.engineering_proposal_intake import validate_engineering_proposal_intake
from core.engineering.engineering_proposal_scope import validate_engineering_proposal_scope
from core.engineering.engineering_proposal_dependency_mapping import validate_engineering_proposal_dependency_mapping
SCHEMA="zero.engineering.proposal_verification.v1";ID_KEY="proposal_verification_id";PREFIX="engineering-proposal-verification-";FIELDS={"engineering_proposal_id","checks","errors","warnings","blocking_conditions"}
def verify_engineering_proposal(proposal:Mapping[str,Any])->dict[str,Any]:
 errors=[];checks=[]
 def add(name,ok,error):
  checks.append({"name":name,"passed":bool(ok)})
  if not ok:errors.append(error)
 intake=proposal.get("proposal_intake",{});scope=proposal.get("proposal_scope",{});changes=proposal.get("proposed_change_set",[]);deps=proposal.get("dependency_mapping",{});validations=proposal.get("validation_plan",[]);risks=proposal.get("risk_review",[])
 add("schema_ids_fingerprints",validate_engineering_proposal(proposal).valid,"invalid_proposal_contract")
 add("nested_artifacts",validate_engineering_proposal_intake(intake).valid and validate_engineering_proposal_scope(scope).valid and validate_engineering_proposal_dependency_mapping(deps).valid,"invalid_nested_artifact")
 add("planning_closure_linkage",proposal.get("planning_closure_linkage")=={"planning_closure_id":intake.get("planning_closure_id"),"planning_closure_fingerprint":intake.get("planning_closure_fingerprint")},"planning_closure_linkage_mismatch")
 add("engineering_plan_linkage",proposal.get("engineering_plan_linkage")=={"engineering_plan_id":intake.get("engineering_plan_id"),"engineering_plan_fingerprint":intake.get("engineering_plan_fingerprint")},"engineering_plan_linkage_mismatch")
 add("repository_revision_linkage",proposal.get("repository_linkage")=={"repository_identity":intake.get("repository_identity"),"analyzed_revision":intake.get("analyzed_revision")},"repository_linkage_mismatch")
 add("scope_containment",set(scope.get("included_repository_areas",[]))<=set(intake.get("requested_scope",[])) and set(scope.get("excluded_repository_areas",[]))==set(intake.get("excluded_scope",[])) and all(scope.get("containment_checks",{}).values()) and not(set(scope.get("included_repository_areas",[]))&set(scope.get("excluded_repository_areas",[]))),"scope_not_contained")
 goal_ids=set(scope.get("included_goals",[]));work_ids=set(scope.get("included_work_items",[]));change_ids={x.get("proposed_change_id") for x in changes}
 add("change_linkage",all(x.get("goal_id") in goal_ids and x.get("work_item_id") in work_ids and x.get("proposal_scope_id")==scope.get("proposal_scope_id") for x in changes),"proposed_change_linkage_mismatch")
 def record_valid(record,id_key,prefix):
  if not isinstance(record,Mapping):return False
  body={k:v for k,v in record.items() if k not in {id_key,"fingerprint"}}
  return record.get(id_key)==stable_proposal_id(prefix,body) and record.get("fingerprint")==fingerprint({**body,id_key:record.get(id_key)})
 add("record_fingerprints",all(record_valid(x,"proposed_change_id","engineering-proposed-change-") for x in changes) and all(record_valid(x,"proposal_validation_id","engineering-proposal-validation-") for x in validations) and all(record_valid(x,"proposal_risk_id","engineering-proposal-risk-") for x in risks),"record_fingerprint_mismatch")
 add("evidence_traceability",all(x.get("current_state_evidence") and set(x.get("current_state_evidence",[]))<=set(scope.get("evidence_references",[])) for x in changes),"evidence_missing")
 add("forbidden_payload_absent",not contains_forbidden_payload(proposal),"forbidden_payload")
 add("authority_absent",all(x.get("implementation_authority")=="not_granted" and x.get("mutation_authority")=="not_granted" for x in changes),"forbidden_authority")
 add("dependency_nodes",set(deps.get("proposed_change_nodes",[]))==change_ids,"missing_dependency_node")
 add("dependency_cycle",deps.get("cycle_status")=="acyclic","dependency_cycle")
 covered={x for v in validations for x in v.get("target_proposed_change_ids",[])};add("validation_coverage",change_ids<=covered,"validation_coverage_missing")
 add("risk_review_complete",bool(risks) and all(x.get("evidence_references") for x in risks),"risk_review_incomplete")
 add("invariants",proposal.get("proposal_invariants")==INVARIANTS,"invariant_mismatch")
 blocking=sorted(x.get("proposal_risk_id") for x in risks if x.get("proposal_blocking"));status="invalid" if errors else ("blocked" if blocking or proposal.get("status")=="blocked" else "verified")
 return proposal_artifact(SCHEMA,status,{"engineering_proposal_id":proposal.get("engineering_proposal_id"),"checks":checks,"errors":sorted(set(errors)),"warnings":[],"blocking_conditions":blocking},ID_KEY,PREFIX)
def validate_engineering_proposal_verification(v:Any)->ValidationResult:return validate_proposal_artifact(v,schema=SCHEMA,statuses={"verified","blocked","invalid"},id_key=ID_KEY,prefix=PREFIX,fields=FIELDS)
verify_proposal=verify_engineering_proposal
__all__=["validate_engineering_proposal_verification","verify_engineering_proposal","verify_proposal"]
