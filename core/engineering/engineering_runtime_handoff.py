from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_governed_execution_common import *
SCHEMA="zero.engineering.runtime_handoff.v1";ID_KEY="engineering_runtime_handoff_id";PREFIX="engineering-runtime-handoff-";KIND="runtime_handoff"
FIELDS={"engineering_execution_session_id","engineering_execution_session_fingerprint","runtime_contract_linkage","runtime_admission_linkage","runtime_activation_linkage","runtime_authorization_linkage","target_runtime_boundary","sealed_execution_scope","constraints","expected_result_schema","expected_evidence_schema","authority_declarations"}
def build_engineering_runtime_handoff(session:Mapping[str,Any],runtime_artifacts:Mapping[str,Any]|None=None)->dict[str,Any]:
 r=dict(runtime_artifacts or {});ok=session.get("status") in {"prepared","admitted","active"} and not contains_forbidden(r)
 p={"engineering_execution_session_id":session.get("engineering_execution_session_id"),"engineering_execution_session_fingerprint":session.get("fingerprint"),"runtime_contract_linkage":r.get("runtime_contract_linkage",{"boundary":"runtime-kernel","opaque":True}),"runtime_admission_linkage":r.get("runtime_admission_linkage"),"runtime_activation_linkage":r.get("runtime_activation_linkage"),"runtime_authorization_linkage":r.get("runtime_authorization_linkage"),"target_runtime_boundary":r.get("target_runtime_boundary","runtime-kernel"),"sealed_execution_scope":session.get("sealed_scope",{}),"constraints":session.get("constraints",[]),"expected_result_schema":r.get("expected_result_schema","zero.runtime.execution_result"),"expected_evidence_schema":r.get("expected_evidence_schema","zero.runtime.execution_evidence"),"authority_declarations":session.get("session_authority",{})}
 return artifact(SCHEMA,"prepared" if ok else "invalid",p,ID_KEY,PREFIX,KIND)
def validate_engineering_runtime_handoff(v:Any)->ValidationResult:return validate_artifact(v,schema=SCHEMA,statuses={"prepared","handed_off","blocked","invalid"},id_key=ID_KEY,prefix=PREFIX,kind=KIND,fields=FIELDS)
build_runtime_handoff=build_engineering_runtime_handoff
__all__=["build_engineering_runtime_handoff","build_runtime_handoff","validate_engineering_runtime_handoff"]
