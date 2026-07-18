from __future__ import annotations
from dataclasses import dataclass
from typing import Any,Mapping
from core.engineering.engineering_intake_common import generic_validate,passive_boundary
from core.engineering.planning_request import SCHEMA,STATUSES
from core.engineering.repository_analysis_request_validation import validate_repository_analysis_request
@dataclass(frozen=True)
class EngineeringPlanningRequestValidationResult:valid:bool;errors:tuple[str,...]
_L={"source_repository_analysis_request_id","source_repository_analysis_request_fingerprint","source_mission_bootstrap_id","source_mission_bootstrap_fingerprint","source_developer_intent_id","source_developer_intent_fingerprint"};_R={"schema","planning_request_id","fingerprint","status","planning_request_payload","reasons","boundary",*_L}
def validate_engineering_planning_request(value:Any,source_analysis:Any=None)->EngineeringPlanningRequestValidationResult:
 e=generic_validate(value,_R,SCHEMA,set(STATUSES),"planning_request_id","engineering-planning-request-",passive_boundary("passive_planning_request"))
 if isinstance(value,Mapping) and ((value.get("status")=="planned_request")!=(isinstance(value.get("planning_request_payload"),Mapping))):e.append("status_payload_contradiction")
 if source_analysis is not None:
  expected={"prepared":"planned_request","needs_clarification":"needs_clarification","rejected":"rejected","invalid":"invalid"}.get(source_analysis.get("status")) if isinstance(source_analysis,Mapping) else None
  if not isinstance(source_analysis,Mapping) or not validate_repository_analysis_request(source_analysis).valid:e.append("invalid_source_analysis")
  else:
   from core.engineering.planning_request import build_engineering_planning_request
   if value.get("source_repository_analysis_request_id")!=source_analysis.get("repository_analysis_request_id") or value.get("source_repository_analysis_request_fingerprint")!=source_analysis.get("fingerprint") or any(value.get(k)!=source_analysis.get(k) for k in _L if not k.startswith("source_repository")) or value.get("status")!=expected or value!=build_engineering_planning_request(source_analysis):e.append("source_analysis_mismatch")
 return EngineeringPlanningRequestValidationResult(not e,tuple(dict.fromkeys(e)))
__all__=["EngineeringPlanningRequestValidationResult","validate_engineering_planning_request"]
