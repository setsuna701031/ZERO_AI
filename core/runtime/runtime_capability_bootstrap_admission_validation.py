from __future__ import annotations
from dataclasses import dataclass
import json
from typing import Any,Mapping
from core.runtime.runtime_capability_bootstrap_admission import DECISION_SCHEMA,FUTURE_CONSUMERS,HANDOFF_SCHEMA,MODES,POLICY_SCHEMA,REQUEST_SCHEMA,STATUSES,_hash
from core.runtime.runtime_capability_bootstrap_consumer import CONSUMER_ID,PROHIBITED_ACTIONS
@dataclass(frozen=True)
class AdmissionValidationResult:valid:bool;errors:tuple[str,...]
SENSITIVE=frozenset({"username","hostname","path","absolute_path","environment","api_key","token","credential","exception","traceback","command","callable","provider","detector","module","class"})
def _safe(v:Any)->bool:
 try:json.dumps(v,allow_nan=False)
 except (TypeError,ValueError):return False
 def bad(x:Any)->bool:
  if isinstance(x,Mapping):return any(str(k).casefold() in SENSITIVE or bad(y) for k,y in x.items())
  if isinstance(x,(list,tuple)):return any(bad(y) for y in x)
  return not isinstance(x,(str,int,float,bool,type(None))) or isinstance(x,str) and ("traceback (most recent" in x.casefold() or "object at 0x" in x.casefold())
 return not bad(v)
def _identity(v:Mapping[str,Any],key:str,excluded:frozenset[str]=frozenset())->bool:
 try:fp=_hash({k:x for k,x in v.items() if k not in excluded|{key,"fingerprint"}});return v.get("fingerprint")==fp and v.get(key)==({"policy_id":"capability-admission-policy-","request_id":"capability-admission-request-","decision_id":"capability-admission-decision-","handoff_id":"capability-activation-handoff-"}[key]+fp[:24])
 except (TypeError,ValueError):return False
def _r(e:list[str])->AdmissionValidationResult:return AdmissionValidationResult(not e,tuple(dict.fromkeys(e)))
def validate_admission_policy(v:Any)->AdmissionValidationResult:
 if not isinstance(v,Mapping):return _r(["policy_not_object"])
 e=[]
 if v.get("schema")!=POLICY_SCHEMA:e.append("invalid_schema")
 if set(v.get("allowed_consumer_ids",[]))!={CONSUMER_ID} or not set(v.get("future_consumer_allowlist",[]))<=FUTURE_CONSUMERS:e.append("invalid_allowlist")
 if not set(v.get("allowed_admission_modes",[]))<=MODES:e.append("invalid_modes")
 if not _identity(v,"policy_id") or not _safe(v):e.append("policy_identity_or_safety_invalid")
 return _r(e)
def validate_admission_request(v:Any)->AdmissionValidationResult:
 if not isinstance(v,Mapping):return _r(["request_not_object"])
 e=[]; required={"schema","request_id","fingerprint","consumption_result_id","consumption_result_fingerprint","lease_id","lease_fingerprint","consumer_eligibility_fingerprint","integration_id","integration_fingerprint","runtime_context_id","runtime_context_fingerprint","admission_mode","requested_future_consumer","policy","metadata","requested_at"}
 e += [f"missing:{x}" for x in sorted(required-set(v))]+[f"unexpected:{x}" for x in sorted(set(v)-required)]
 if v.get("schema")!=REQUEST_SCHEMA:e.append("invalid_schema")
 if v.get("admission_mode") not in MODES:e.append("unsupported_mode")
 if v.get("requested_future_consumer") not in FUTURE_CONSUMERS:e.append("unknown_future_consumer")
 if not validate_admission_policy(v.get("policy")).valid:e.append("invalid_policy")
 if not _identity(v,"request_id",frozenset({"requested_at"})):e.append("request_identity_mismatch")
 if not _safe({"metadata":v.get("metadata")}):e.append("unsafe_metadata")
 return _r(e)
def validate_activation_handoff(v:Any)->AdmissionValidationResult:
 if not isinstance(v,Mapping):return _r(["handoff_not_object"])
 e=[]
 if v.get("schema")!=HANDOFF_SCHEMA or v.get("future_consumer") not in FUTURE_CONSUMERS:e.append("invalid_handoff")
 if v.get("runtime_start_allowed") is not False or v.get("authorization_issued") is not False or v.get("token_issued") is not False or v.get("runtime_started") is not False or v.get("mutation_classification")!="none":e.append("unsafe_handoff")
 if not set(PROHIBITED_ACTIONS)<=set(v.get("prohibited_actions",[])):e.append("missing_prohibition")
 if not _identity(v,"handoff_id",frozenset({"prepared_at","admission_decision_linkage"})) or not _safe(v):e.append("handoff_identity_or_safety_invalid")
 return _r(e)
def validate_admission_decision(v:Any)->AdmissionValidationResult:
 if not isinstance(v,Mapping):return _r(["decision_not_object"])
 e=[]
 if v.get("schema")!=DECISION_SCHEMA or v.get("admission_status") not in STATUSES:e.append("invalid_decision")
 if v.get("admitted") is not (v.get("admission_status")=="admitted") or (v.get("admitted") and v.get("blockers")):e.append("decision_state_mismatch")
 if any(v.get(k) is not False for k in ("runtime_started","mutation_performed","authorization_issued","token_issued")):e.append("unsafe_decision")
 if any(x!=0 for x in v.get("invocation_evidence",{}).values()):e.append("unsafe_invocation_evidence")
 h=v.get("activation_handoff")
 if h is not None and not validate_activation_handoff(h).valid:e.append("invalid_handoff")
 if not _identity(v,"decision_id",frozenset({"evaluated_at","activation_handoff"})) or not _safe(v):e.append("decision_identity_or_safety_invalid")
 return _r(e)
__all__=["AdmissionValidationResult","validate_admission_policy","validate_admission_request","validate_activation_handoff","validate_admission_decision"]
