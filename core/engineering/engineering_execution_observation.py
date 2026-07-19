from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_governed_execution_common import *
SCHEMA="zero.engineering.execution_observation.v1";ID_KEY="engineering_execution_observation_id";PREFIX="engineering-execution-observation-";KIND="execution_observation"
FIELDS={"engineering_execution_session_id","engineering_execution_session_fingerprint","engineering_runtime_handoff_id","engineering_runtime_handoff_fingerprint","runtime_result_linkage","lifecycle_state","observed_operations_summary","scope_observations","authority_observations","safety_boundary_observations","error_summary"}
def build_engineering_execution_observation(session:Mapping[str,Any],handoff:Mapping[str,Any],runtime_result:Mapping[str,Any]|None=None)->dict[str,Any]:
 r=dict(runtime_result or {}); present=bool(r); invalid=contains_forbidden(r)
 state=str(r.get("status","not_observed")); p={"engineering_execution_session_id":session.get("engineering_execution_session_id"),"engineering_execution_session_fingerprint":session.get("fingerprint"),"engineering_runtime_handoff_id":handoff.get("engineering_runtime_handoff_id"),"engineering_runtime_handoff_fingerprint":handoff.get("fingerprint"),"runtime_result_linkage":{"runtime_result_id":r.get("runtime_result_id",r.get("execution_id")),"fingerprint":r.get("fingerprint")},"lifecycle_state":state,"observed_operations_summary":r.get("operations_summary",[]),"scope_observations":r.get("scope",r.get("completed_scope",{})),"authority_observations":r.get("authority",{}),"safety_boundary_observations":r.get("safety_boundary",{}),"error_summary":r.get("error_summary",r.get("error"))}
 return artifact(SCHEMA,"invalid" if invalid else ("observed" if present else "insufficient_evidence"),p,ID_KEY,PREFIX,KIND)
def validate_engineering_execution_observation(v:Any)->ValidationResult:return validate_artifact(v,schema=SCHEMA,statuses={"observed","blocked","failed","invalid","insufficient_evidence"},id_key=ID_KEY,prefix=PREFIX,kind=KIND,fields=FIELDS)
build_execution_observation=build_engineering_execution_observation
__all__=["build_engineering_execution_observation","build_execution_observation","validate_engineering_execution_observation"]
