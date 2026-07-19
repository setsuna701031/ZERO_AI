from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_governed_execution_common import *
SCHEMA="zero.engineering.execution_outcome.v1";ID_KEY="engineering_execution_outcome_id";PREFIX="engineering-execution-outcome-";KIND="execution_outcome"
FIELDS={"engineering_execution_session_id","engineering_execution_session_fingerprint","engineering_runtime_handoff_id","engineering_execution_observation_id","engineering_execution_evidence_id","result_status","completed_scope","incomplete_scope","blocked_scope","failure_summary","authority_consumption_state","validation_readiness"}
def build_engineering_execution_outcome(session:Mapping[str,Any],handoff:Mapping[str,Any],observation:Mapping[str,Any],evidence:Mapping[str,Any])->dict[str,Any]:
 state=observation.get("lifecycle_state"); sufficient=evidence.get("integrity_status")=="sufficient"
 if state in {"completed","success","succeeded"} and sufficient: result="completed"
 elif state in {"failed","error"}: result="failed"
 elif state=="blocked": result="blocked"
 elif not sufficient: result="insufficient_evidence"
 else: result="partially_completed"
 scope=observation.get("scope_observations",{}); p={"engineering_execution_session_id":session.get("engineering_execution_session_id"),"engineering_execution_session_fingerprint":session.get("fingerprint"),"engineering_runtime_handoff_id":handoff.get("engineering_runtime_handoff_id"),"engineering_execution_observation_id":observation.get("engineering_execution_observation_id"),"engineering_execution_evidence_id":evidence.get("engineering_execution_evidence_id"),"result_status":result,"completed_scope":scope if result=="completed" else {},"incomplete_scope":scope if result in {"partially_completed","insufficient_evidence"} else {},"blocked_scope":scope if result=="blocked" else {},"failure_summary":observation.get("error_summary") if result=="failed" else None,"authority_consumption_state":{"execution_authority":"consumed" if result in {"completed","partially_completed","blocked","failed"} else "closed","mutation_authority":"not_retained","reusable_execution_token":False},"validation_readiness":sufficient}
 return artifact(SCHEMA,result,p,ID_KEY,PREFIX,KIND)
def validate_engineering_execution_outcome(v:Any)->ValidationResult:return validate_artifact(v,schema=SCHEMA,statuses={"completed","partially_completed","blocked","failed","invalid","insufficient_evidence"},id_key=ID_KEY,prefix=PREFIX,kind=KIND,fields=FIELDS)
build_execution_outcome=build_engineering_execution_outcome
__all__=["build_engineering_execution_outcome","build_execution_outcome","validate_engineering_execution_outcome"]
