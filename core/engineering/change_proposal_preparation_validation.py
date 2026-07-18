from __future__ import annotations
from dataclasses import dataclass
from typing import Any,Mapping
from core.engineering.engineering_intake_common import generic_validate,passive_boundary
from core.engineering.change_proposal_preparation import SCHEMA,STATUSES
from core.engineering.planning_request_validation import validate_engineering_planning_request
@dataclass(frozen=True)
class ChangeProposalPreparationValidationResult:valid:bool;errors:tuple[str,...]
_L={"source_planning_request_id","source_planning_request_fingerprint","source_repository_analysis_request_id","source_repository_analysis_request_fingerprint","source_mission_bootstrap_id","source_mission_bootstrap_fingerprint","source_developer_intent_id","source_developer_intent_fingerprint"};_B=passive_boundary("passive_proposal_preparation",execution_plan_created=False,approval_granted=False,authorization_granted=False);_R={"schema","change_proposal_preparation_id","fingerprint","status","preparation_payload","reasons","boundary",*_L}
def validate_change_proposal_preparation(value:Any,source_planning:Any=None)->ChangeProposalPreparationValidationResult:
 e=generic_validate(value,_R,SCHEMA,set(STATUSES),"change_proposal_preparation_id","engineering-change-proposal-preparation-",_B)
 if isinstance(value,Mapping) and ((value.get("status")=="prepared")!=(isinstance(value.get("preparation_payload"),Mapping))):e.append("status_payload_contradiction")
 if source_planning is not None:
  expected={"planned_request":"prepared","needs_clarification":"needs_clarification","rejected":"rejected","invalid":"invalid"}.get(source_planning.get("status")) if isinstance(source_planning,Mapping) else None
  if not isinstance(source_planning,Mapping) or not validate_engineering_planning_request(source_planning).valid:e.append("invalid_source_planning")
  else:
   from core.engineering.change_proposal_preparation import prepare_change_proposal
   if value.get("source_planning_request_id")!=source_planning.get("planning_request_id") or value.get("source_planning_request_fingerprint")!=source_planning.get("fingerprint") or any(value.get(k)!=source_planning.get(k) for k in _L if not k.startswith("source_planning")) or value.get("status")!=expected or value!=prepare_change_proposal(source_planning):e.append("source_planning_mismatch")
 return ChangeProposalPreparationValidationResult(not e,tuple(dict.fromkeys(e)))
__all__=["ChangeProposalPreparationValidationResult","validate_change_proposal_preparation"]
