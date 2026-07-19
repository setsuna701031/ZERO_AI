from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_governed_execution_common import *
SCHEMA="zero.engineering.execution_admission.v1"; ID_KEY="engineering_execution_admission_id"; PREFIX="engineering-execution-admission-"; KIND="execution_admission"
FIELDS={"governed_execution_intake_id","governed_execution_intake_fingerprint","admission_policy_linkage","authorization_linkage","preparation_linkage","admitted_scope","excluded_scope","admission_constraints","session_limits","authority_declarations","admission_decision","rejection_reasons"}
def build_engineering_execution_admission(intake:Mapping[str,Any], policy:Mapping[str,Any]|None=None)->dict[str,Any]:
 p=dict(policy or {}); admitted=intake.get("status")=="accepted" and not contains_forbidden(p); decision="admitted" if admitted else ("invalid" if intake.get("status")=="invalid" else "not_admitted")
 payload={"governed_execution_intake_id":intake.get("governed_execution_intake_id"),"governed_execution_intake_fingerprint":intake.get("fingerprint"),"admission_policy_linkage":p.get("admission_policy_linkage",{"policy":"bounded-governed-execution-v1"}),"authorization_linkage":intake.get("authorization_closure_id"),"preparation_linkage":intake.get("execution_preparation_closure_id"),"admitted_scope":intake.get("sealed_execution_scope",{}) if admitted else {},"excluded_scope":p.get("excluded_scope",[]),"admission_constraints":sorted(set(p.get("admission_constraints",intake.get("execution_constraints",[])))),"session_limits":p.get("session_limits",{"bounded":True,"reusable":False}),"authority_declarations":dict(AUTHORITY_INTAKE),"admission_decision":decision,"rejection_reasons":[] if admitted else ["intake_not_accepted"]}
 return artifact(SCHEMA,decision,payload,ID_KEY,PREFIX,KIND)
def validate_engineering_execution_admission(value:Any)->ValidationResult:return validate_artifact(value,schema=SCHEMA,statuses={"admitted","not_admitted","blocked","invalid"},id_key=ID_KEY,prefix=PREFIX,kind=KIND,fields=FIELDS)
build_execution_admission=build_engineering_execution_admission
__all__=["build_engineering_execution_admission","build_execution_admission","validate_engineering_execution_admission"]
