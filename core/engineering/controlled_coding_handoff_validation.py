from __future__ import annotations
from dataclasses import dataclass
from typing import Any,Mapping
from core.engineering.engineering_intake_common import generic_validate,passive_boundary
from core.engineering.controlled_coding_handoff import SCHEMA,STATUSES
from core.engineering.change_proposal_preparation_validation import validate_change_proposal_preparation
@dataclass(frozen=True)
class ControlledCodingHandoffValidationResult:valid:bool;errors:tuple[str,...]
_L={"source_change_proposal_preparation_id","source_change_proposal_preparation_fingerprint","source_planning_request_id","source_planning_request_fingerprint","source_repository_analysis_request_id","source_repository_analysis_request_fingerprint","source_mission_bootstrap_id","source_mission_bootstrap_fingerprint","source_developer_intent_id","source_developer_intent_fingerprint"};_R={"schema","controlled_coding_handoff_id","fingerprint","status","handoff_payload","reasons","boundary",*_L}
def _b(s):return passive_boundary("passive_handoff",developer_intake_complete=s=="handed_off",repository_analysis_started=False,approval_granted=False,authorization_granted=False)
def validate_controlled_coding_handoff(value:Any,source_preparation:Any=None)->ControlledCodingHandoffValidationResult:
 boundary=_b(value.get("status") if isinstance(value,Mapping) else None);e=generic_validate(value,_R,SCHEMA,set(STATUSES),"controlled_coding_handoff_id","engineering-controlled-coding-handoff-",boundary)
 if isinstance(value,Mapping) and ((value.get("status")=="handed_off")!=(isinstance(value.get("handoff_payload"),Mapping))):e.append("status_payload_contradiction")
 if isinstance(value,Mapping) and value.get("status")=="handed_off" and value["handoff_payload"].get("next_stage")!="repository_analysis_pending":e.append("invalid_next_stage")
 if source_preparation is not None:
  expected={"prepared":"handed_off","needs_clarification":"needs_clarification","rejected":"rejected","invalid":"invalid"}.get(source_preparation.get("status")) if isinstance(source_preparation,Mapping) else None
  if not isinstance(source_preparation,Mapping) or not validate_change_proposal_preparation(source_preparation).valid:e.append("invalid_source_preparation")
  else:
   from core.engineering.controlled_coding_handoff import build_controlled_coding_handoff
   if value.get("source_change_proposal_preparation_id")!=source_preparation.get("change_proposal_preparation_id") or value.get("source_change_proposal_preparation_fingerprint")!=source_preparation.get("fingerprint") or any(value.get(k)!=source_preparation.get(k) for k in _L if not k.startswith("source_change")) or value.get("status")!=expected or value!=build_controlled_coding_handoff(source_preparation):e.append("source_preparation_mismatch")
 return ControlledCodingHandoffValidationResult(not e,tuple(dict.fromkeys(e)))
__all__=["ControlledCodingHandoffValidationResult","validate_controlled_coding_handoff"]
