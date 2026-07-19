from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_governed_execution_common import *
SCHEMA="zero.engineering.execution_evidence.v1";ID_KEY="engineering_execution_evidence_id";PREFIX="engineering-execution-evidence-";KIND="execution_evidence"
FIELDS={"engineering_execution_session_id","engineering_execution_session_fingerprint","engineering_execution_observation_id","engineering_execution_observation_fingerprint","runtime_result_linkage","evidence_records","scope_evidence","authority_evidence","validation_evidence","mutation_evidence","completion_evidence","integrity_status"}
def build_engineering_execution_evidence(session:Mapping[str,Any],observation:Mapping[str,Any],runtime_result:Mapping[str,Any]|None=None)->dict[str,Any]:
 r=dict(runtime_result or {}); raw=r.get("evidence",[]); records=[]
 for i,item in enumerate(raw if isinstance(raw,list) else []):
  body={"type":item.get("type","runtime") if isinstance(item,Mapping) else "runtime","source_linkage":item.get("source_linkage",{}) if isinstance(item,Mapping) else {},"claim":item.get("claim",item) if isinstance(item,Mapping) else item,"integrity_state":item.get("integrity_state","verified") if isinstance(item,Mapping) else "verified"}; records.append(identified(body,"evidence_record_id","engineering-evidence-record-"))
 integrity="sufficient" if records and all(x["integrity_state"]=="verified" for x in records) else "insufficient"
 p={"engineering_execution_session_id":session.get("engineering_execution_session_id"),"engineering_execution_session_fingerprint":session.get("fingerprint"),"engineering_execution_observation_id":observation.get("engineering_execution_observation_id"),"engineering_execution_observation_fingerprint":observation.get("fingerprint"),"runtime_result_linkage":observation.get("runtime_result_linkage"),"evidence_records":records,"scope_evidence":r.get("scope_evidence",r.get("scope",{})),"authority_evidence":r.get("authority_evidence",r.get("authority",{})),"validation_evidence":r.get("validation_evidence",r.get("verification",{})),"mutation_evidence":r.get("mutation_evidence",{}),"completion_evidence":r.get("completion_evidence",{}),"integrity_status":integrity}
 return artifact(SCHEMA,"accepted" if integrity=="sufficient" else "insufficient_evidence",p,ID_KEY,PREFIX,KIND)
def validate_engineering_execution_evidence(v:Any)->ValidationResult:return validate_artifact(v,schema=SCHEMA,statuses={"accepted","invalid","insufficient_evidence"},id_key=ID_KEY,prefix=PREFIX,kind=KIND,fields=FIELDS)
build_execution_evidence=build_engineering_execution_evidence
__all__=["build_engineering_execution_evidence","build_execution_evidence","validate_engineering_execution_evidence"]
