from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_planning_common import ValidationResult,planning_artifact,validate_planning_artifact
SCHEMA="zero.engineering.engineering_plan.v1";ID_KEY="engineering_plan_id";PREFIX="engineering-plan-"
FIELDS={"planning_context","goals","work_breakdown","dependency_ordering","validation_strategy","risk_assessment","repository_linkage","analysis_closure_linkage","planning_invariants"}
INVARIANTS={"read_only_planning":True,"evidence_traceable":True,"no_scope_expansion":True,"no_execution_authority":True,"no_mutation_authority":True,"no_approval_authority":True,"deterministic":True,"dependency_consistent":True,"validation_defined":True,"risks_assessed":True}
def build_engineering_plan(context:Mapping[str,Any],goals:list[Mapping[str,Any]],work_breakdown:list[Mapping[str,Any]],dependency_ordering:Mapping[str,Any],validation_strategy:list[Mapping[str,Any]],risk_assessment:list[Mapping[str,Any]])->dict[str,Any]:
 status="invalid" if dependency_ordering.get("cycle_status")!="acyclic" else ("blocked" if any(x.get("blocking_status")=="blocking" for x in risk_assessment) else ("insufficient_evidence" if not goals else "valid"))
 payload={"planning_context":dict(context),"goals":list(goals),"work_breakdown":list(work_breakdown),"dependency_ordering":dict(dependency_ordering),"validation_strategy":list(validation_strategy),"risk_assessment":list(risk_assessment),"repository_linkage":context["repository_identity"],"analysis_closure_linkage":{"repository_analysis_closure_id":context["repository_analysis_closure_id"],"repository_analysis_closure_fingerprint":context["repository_analysis_closure_fingerprint"],"analyzed_revision":context["analyzed_revision"]},"planning_invariants":dict(INVARIANTS)}
 return planning_artifact(SCHEMA,status,payload,ID_KEY,PREFIX)
def validate_engineering_plan(v:Any)->ValidationResult:return validate_planning_artifact(v,schema=SCHEMA,statuses={"valid","blocked","invalid","insufficient_evidence"},id_key=ID_KEY,prefix=PREFIX,fields=FIELDS)
__all__=["build_engineering_plan","validate_engineering_plan"]
