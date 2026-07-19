from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_planning_closure import validate_engineering_planning_closure
from core.engineering.engineering_proposal_common import ValidationResult,proposal_artifact,scope_contained,validate_proposal_artifact
SCHEMA="zero.engineering.proposal_intake.v1";ID_KEY="proposal_intake_id";PREFIX="engineering-proposal-intake-"
FIELDS={"planning_closure_id","planning_closure_fingerprint","engineering_plan_id","engineering_plan_fingerprint","repository_identity","analyzed_revision","proposal_objective","requested_scope","excluded_scope","constraints","evidence_references","governance_declarations"}
OPAQUE_SCOPE="sealed_engineering_plan_scope"
GOVERNANCE={"approved":False,"authorized":False,"executable":False,"repository_mutation_allowed":False,"review_required":True}
def build_engineering_proposal_intake(closure:Mapping[str,Any],intent:Mapping[str,Any]|None=None)->dict[str,Any]:
 r=validate_engineering_planning_closure(closure)
 if not r.valid or closure.get("status")!="closed":raise ValueError("planning_closure_not_closed")
 intent={} if intent is None else dict(intent);allowed={"proposal_objective","requested_scope","excluded_scope","constraints","change_categories","changes","dependency_edges","validations","risks"}
 if set(intent)-allowed:raise ValueError("unsupported_proposal_intent")
 requested=intent.get("requested_scope",[OPAQUE_SCOPE]);excluded=intent.get("excluded_scope",[])
 if not isinstance(requested,list) or not isinstance(excluded,list) or not scope_contained(requested,[OPAQUE_SCOPE],excluded):raise ValueError("scope_expansion")
 objective=intent.get("proposal_objective","Prepare the sealed engineering plan for governed review")
 if not isinstance(objective,str) or not objective.strip():raise ValueError("invalid_proposal_objective")
 constraints=intent.get("constraints",{});
 if not isinstance(constraints,Mapping):raise ValueError("invalid_constraints")
 evidence=[closure["planning_closure_id"],closure["engineering_plan_id"],closure["verification_id"]]
 payload={"planning_closure_id":closure["planning_closure_id"],"planning_closure_fingerprint":closure["fingerprint"],"engineering_plan_id":closure["engineering_plan_id"],"engineering_plan_fingerprint":closure["engineering_plan_fingerprint"],"repository_identity":closure["repository_identity"],"analyzed_revision":closure["analyzed_revision"],"proposal_objective":objective.strip(),"requested_scope":sorted(set(requested)),"excluded_scope":sorted(set(excluded)),"constraints":{k:constraints[k] for k in sorted(constraints)},"evidence_references":sorted(evidence),"governance_declarations":dict(GOVERNANCE)}
 return proposal_artifact(SCHEMA,"accepted",payload,ID_KEY,PREFIX)
def validate_engineering_proposal_intake(v:Any)->ValidationResult:
 r=validate_proposal_artifact(v,schema=SCHEMA,statuses={"accepted","blocked","invalid","insufficient_evidence"},id_key=ID_KEY,prefix=PREFIX,fields=FIELDS);e=list(r.errors)
 if isinstance(v,dict):
  if v.get("governance_declarations")!=GOVERNANCE:e.append("unsafe_governance")
  if not scope_contained(v.get("requested_scope",[]),[OPAQUE_SCOPE],v.get("excluded_scope",[])):e.append("scope_expansion")
 return ValidationResult(not e,tuple(dict.fromkeys(e)))
build_proposal_intake=build_engineering_proposal_intake
__all__=["OPAQUE_SCOPE","build_engineering_proposal_intake","build_proposal_intake","validate_engineering_proposal_intake"]
