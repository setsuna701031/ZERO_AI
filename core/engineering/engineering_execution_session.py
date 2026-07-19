from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_governed_execution_common import *
SCHEMA="zero.engineering.execution_session.v1";ID_KEY="engineering_execution_session_id";PREFIX="engineering-execution-session-";KIND="execution_session"
FIELDS={"engineering_execution_admission_id","engineering_execution_admission_fingerprint","execution_preparation_closure_id","execution_preparation_closure_fingerprint","repository_identity","analyzed_revision","sealed_scope","constraints","expected_evidence","expected_validation","session_authority","session_lifecycle"}
def build_engineering_execution_session(admission:Mapping[str,Any],intake:Mapping[str,Any])->dict[str,Any]:
 ok=admission.get("admission_decision")=="admitted"; auth={**AUTHORITY_INTAKE,"execution_authority":"granted" if ok else "not_granted","session_bound":True,"scope_bound":True,"evidence_bound":True,"non_transferable":True,"non_reusable":True,"fail_closed":True}
 p={"engineering_execution_admission_id":admission.get("engineering_execution_admission_id"),"engineering_execution_admission_fingerprint":admission.get("fingerprint"),"execution_preparation_closure_id":intake.get("execution_preparation_closure_id"),"execution_preparation_closure_fingerprint":intake.get("execution_preparation_closure_fingerprint"),"repository_identity":intake.get("repository_identity"),"analyzed_revision":intake.get("analyzed_revision"),"sealed_scope":admission.get("admitted_scope",{}),"constraints":admission.get("admission_constraints",[]),"expected_evidence":["runtime_result","scope","authority","completion"],"expected_validation":["linkage","containment","integrity"],"session_authority":auth,"session_lifecycle":{"state":"prepared","authority_consumed":False}}
 return artifact(SCHEMA,"prepared" if ok else "invalid",p,ID_KEY,PREFIX,KIND)
def validate_engineering_execution_session(v:Any)->ValidationResult:return validate_artifact(v,schema=SCHEMA,statuses={"prepared","admitted","active","completed","blocked","failed","invalid","closed"},id_key=ID_KEY,prefix=PREFIX,kind=KIND,fields=FIELDS)
build_execution_session=build_engineering_execution_session
__all__=["build_engineering_execution_session","build_execution_session","validate_engineering_execution_session"]
