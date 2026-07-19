from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_governed_execution_common import *

SCHEMA="zero.engineering.governed_execution_intake.v1"; ID_KEY="governed_execution_intake_id"; PREFIX="engineering-governed-execution-intake-"; KIND="governed_execution_intake"
FIELDS={"execution_preparation_closure_id","execution_preparation_closure_fingerprint","authorization_closure_id","approval_closure_id","repository_identity","analyzed_revision","execution_objective","sealed_execution_scope","execution_constraints","evidence_references","authority_declarations"}

def build_engineering_governed_execution_intake(closure: Mapping[str,Any], intent: Mapping[str,Any]|None=None)->dict[str,Any]:
    supplied=dict(intent or {}); safe=not contains_forbidden(supplied)
    scope=supplied.get("sealed_execution_scope", supplied.get("execution_scope", {}))
    payload={"execution_preparation_closure_id":closure.get("execution_preparation_closure_id"),"execution_preparation_closure_fingerprint":closure.get("fingerprint"),"authorization_closure_id":closure.get("authorization_closure_id"),"approval_closure_id":closure.get("approval_closure_id"),"repository_identity":closure.get("repository_identity"),"analyzed_revision":closure.get("analyzed_revision"),"execution_objective":supplied.get("execution_objective","governed engineering execution"),"sealed_execution_scope":scope,"execution_constraints":sorted(set(supplied.get("execution_constraints",[]))),"evidence_references":sorted(set(supplied.get("evidence_references",[]))),"authority_declarations":dict(AUTHORITY_INTAKE)}
    status="accepted" if preparation_valid(closure) and safe else "invalid"
    return artifact(SCHEMA,status,payload,ID_KEY,PREFIX,KIND)

def validate_engineering_governed_execution_intake(value:Any)->ValidationResult: return validate_artifact(value,schema=SCHEMA,statuses={"accepted","blocked","invalid","insufficient_evidence"},id_key=ID_KEY,prefix=PREFIX,kind=KIND,fields=FIELDS)
build_governed_execution_intake=build_engineering_governed_execution_intake
__all__=["build_engineering_governed_execution_intake","build_governed_execution_intake","validate_engineering_governed_execution_intake"]
