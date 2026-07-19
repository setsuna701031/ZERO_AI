from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_proposal_common import ValidationResult,proposal_artifact,validate_proposal_artifact
from core.engineering.engineering_proposal_intake import validate_engineering_proposal_intake
from core.engineering.engineering_proposal_scope import validate_engineering_proposal_scope
from core.engineering.engineering_proposal_dependency_mapping import validate_engineering_proposal_dependency_mapping
SCHEMA="zero.engineering.engineering_proposal.v1";ID_KEY="engineering_proposal_id";PREFIX="engineering-proposal-";FIELDS={"proposal_intake","proposal_scope","proposed_change_set","dependency_mapping","validation_plan","risk_review","planning_closure_linkage","engineering_plan_linkage","repository_linkage","proposal_invariants"}
INVARIANTS={"planning_closure_verified":True,"evidence_traceable":True,"scope_contained":True,"no_patch_generated":True,"no_diff_generated":True,"no_repository_mutation":True,"no_execution_authority":True,"no_mutation_authority":True,"no_approval_authority":True,"no_authorization_authority":True,"deterministic":True,"dependency_consistent":True,"validation_defined":True,"risks_reviewed":True}
def build_engineering_proposal(intake:Mapping[str,Any],scope:Mapping[str,Any],changes:list[Mapping[str,Any]],dependencies:Mapping[str,Any],validations:list[Mapping[str,Any]],risks:list[Mapping[str,Any]])->dict[str,Any]:
 if not validate_engineering_proposal_intake(intake).valid or not validate_engineering_proposal_scope(scope).valid or not validate_engineering_proposal_dependency_mapping(dependencies).valid:raise ValueError("proposal_component_invalid")
 blocked=dependencies.get("cycle_status")!="acyclic" or any(x.get("proposal_blocking") for x in risks);covered={x for v in validations for x in v.get("target_proposed_change_ids",[])};missing=any(x["proposed_change_id"] not in covered for x in changes)
 status="blocked" if blocked or missing else ("insufficient_evidence" if not changes else "ready_for_review")
 payload={"proposal_intake":dict(intake),"proposal_scope":dict(scope),"proposed_change_set":list(changes),"dependency_mapping":dict(dependencies),"validation_plan":list(validations),"risk_review":list(risks),"planning_closure_linkage":{"planning_closure_id":intake["planning_closure_id"],"planning_closure_fingerprint":intake["planning_closure_fingerprint"]},"engineering_plan_linkage":{"engineering_plan_id":intake["engineering_plan_id"],"engineering_plan_fingerprint":intake["engineering_plan_fingerprint"]},"repository_linkage":{"repository_identity":intake["repository_identity"],"analyzed_revision":intake["analyzed_revision"]},"proposal_invariants":dict(INVARIANTS)}
 return proposal_artifact(SCHEMA,status,payload,ID_KEY,PREFIX)
def validate_engineering_proposal(v:Any)->ValidationResult:return validate_proposal_artifact(v,schema=SCHEMA,statuses={"ready_for_review","blocked","invalid","insufficient_evidence"},id_key=ID_KEY,prefix=PREFIX,fields=FIELDS)
__all__=["INVARIANTS","build_engineering_proposal","validate_engineering_proposal"]
