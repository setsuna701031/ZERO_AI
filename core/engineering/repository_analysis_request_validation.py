from __future__ import annotations
from dataclasses import dataclass
from typing import Any,Mapping
from core.engineering.engineering_intake_common import generic_validate,passive_boundary
from core.engineering.repository_analysis_request import SCHEMA,STATUSES
from core.engineering.mission_bootstrap_validation import validate_engineering_mission_bootstrap
@dataclass(frozen=True)
class RepositoryAnalysisRequestValidationResult:valid:bool;errors:tuple[str,...]
_L={"source_mission_bootstrap_id","source_mission_bootstrap_fingerprint","source_developer_intent_id","source_developer_intent_fingerprint"};_R={"schema","repository_analysis_request_id","fingerprint","status","analysis_request_payload","reasons","boundary",*_L}
def _monotonic(v,s):return all(v.get(k)==s.get(k) for k in _L if k.startswith("source_developer")) and v.get("source_mission_bootstrap_id")==s.get("mission_bootstrap_id") and v.get("source_mission_bootstrap_fingerprint")==s.get("fingerprint") and v.get("status")=={"bootstrapped":"prepared","needs_clarification":"needs_clarification","rejected":"rejected","invalid":"invalid"}.get(s.get("status")) and (v.get("analysis_request_payload") is None if v.get("status")!="prepared" else v["analysis_request_payload"].get("scope_hints")==s["bootstrap_payload"].get("allowed_scope") and v["analysis_request_payload"].get("safety_constraints")==s["bootstrap_payload"].get("explicit_constraints"))
def validate_repository_analysis_request(value:Any,source_bootstrap:Any=None)->RepositoryAnalysisRequestValidationResult:
 e=generic_validate(value,_R,SCHEMA,set(STATUSES),"repository_analysis_request_id","engineering-repository-analysis-request-",passive_boundary("passive_analysis_request"))
 if isinstance(value,Mapping) and ((value.get("status")=="prepared")!=(isinstance(value.get("analysis_request_payload"),Mapping))):e.append("status_payload_contradiction")
 if source_bootstrap is not None:
  if not isinstance(source_bootstrap,Mapping) or not validate_engineering_mission_bootstrap(source_bootstrap).valid:e.append("invalid_source_bootstrap")
  else:
   from core.engineering.repository_analysis_request import prepare_repository_analysis_request
   if not _monotonic(value,source_bootstrap) or value!=prepare_repository_analysis_request(source_bootstrap):e.append("source_bootstrap_mismatch")
 return RepositoryAnalysisRequestValidationResult(not e,tuple(dict.fromkeys(e)))
__all__=["RepositoryAnalysisRequestValidationResult","validate_repository_analysis_request"]
