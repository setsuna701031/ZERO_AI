from __future__ import annotations
from dataclasses import dataclass
from typing import Any,Mapping
from core.engineering.engineering_intake_common import generic_validate,passive_boundary
from core.engineering.mission_bootstrap import SCHEMA,STATUSES
from core.engineering.developer_intent_validation import validate_developer_intent
@dataclass(frozen=True)
class EngineeringMissionBootstrapValidationResult:valid:bool;errors:tuple[str,...]
_R={"schema","mission_bootstrap_id","fingerprint","status","source_developer_intent_id","source_developer_intent_fingerprint","bootstrap_payload","reasons","boundary"}
def _identity_valid(v):
 from core.engineering.engineering_intake_common import identity_valid
 return identity_valid(v,"mission_bootstrap_id","engineering-mission-bootstrap-")
def _boundary_valid(v):return v.get("boundary")==passive_boundary("passive_mission_bootstrap")
def _monotonic(v,s):return v.get("source_developer_intent_id")==s.get("developer_intent_id") and v.get("source_developer_intent_fingerprint")==s.get("fingerprint") and v.get("status")=={"accepted":"bootstrapped","needs_clarification":"needs_clarification","rejected":"rejected","invalid":"invalid"}.get(s.get("status")) and (v.get("bootstrap_payload") is None if v.get("status")!="bootstrapped" else v["bootstrap_payload"].get("intent_types")==s.get("intent_types") and v["bootstrap_payload"].get("explicit_constraints")==s.get("explicit_constraints") and v["bootstrap_payload"].get("mutation_allowed") is False)
def validate_engineering_mission_bootstrap(value:Any,source_intent:Any=None)->EngineeringMissionBootstrapValidationResult:
 e=generic_validate(value,_R,SCHEMA,set(STATUSES),"mission_bootstrap_id","engineering-mission-bootstrap-",passive_boundary("passive_mission_bootstrap"))
 if isinstance(value,Mapping) and ((value.get("status")=="bootstrapped")!=(isinstance(value.get("bootstrap_payload"),Mapping))):e.append("status_payload_contradiction")
 if source_intent is not None:
  if not isinstance(source_intent,Mapping) or not validate_developer_intent(source_intent).valid:e.append("invalid_source_intent")
  else:
   from core.engineering.mission_bootstrap import bootstrap_engineering_mission
   if not _monotonic(value,source_intent) or value!=bootstrap_engineering_mission(source_intent):e.append("source_intent_mismatch")
 return EngineeringMissionBootstrapValidationResult(not e,tuple(dict.fromkeys(e)))
__all__=["EngineeringMissionBootstrapValidationResult","validate_engineering_mission_bootstrap"]
