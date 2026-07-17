from __future__ import annotations
from dataclasses import dataclass
import json
from typing import Any, Mapping
from core.runtime.runtime_capability_activation_authorization_request import ELIGIBILITY_SCHEMA,FUTURE_CONSUMERS,HANDOFF_SCHEMA,MODES,POLICY_SCHEMA,REQUEST_SCHEMA,REVIEWER_CLASSES,REVIEW_SCHEMA,STATUSES,_hash
from core.runtime.runtime_capability_activation_gate import AUTHORIZATION_CLASSES,FUTURE_CONSUMERS as ACTIVATION_CONSUMERS,REQUIRED_PROHIBITIONS

@dataclass(frozen=True)
class AuthorizationReviewValidationResult:
    valid: bool
    errors: tuple[str,...]

SENSITIVE=frozenset({"username","hostname","path","absolute_path","environment","api_key","token","credential","secret","password","exception","traceback","command","callable","provider","detector","module","class"})
PREFIXES={"policy_id":"capability-activation-review-policy-","request_id":"capability-activation-review-request-","eligibility_id":"capability-activation-review-eligibility-","review_id":"capability-activation-review-","handoff_id":"capability-activation-review-handoff-"}
def _result(e:list[str])->AuthorizationReviewValidationResult:return AuthorizationReviewValidationResult(not e,tuple(dict.fromkeys(e)))
def _safe(value:Any)->bool:
    try:json.dumps(value,allow_nan=False)
    except (TypeError,ValueError):return False
    def bad(v:Any)->bool:
        if isinstance(v,Mapping):return any(str(k).casefold() in SENSITIVE or bad(x) for k,x in v.items())
        if isinstance(v,(list,tuple)):return any(bad(x) for x in v)
        return not isinstance(v,(str,int,float,bool,type(None))) or isinstance(v,str) and ("traceback (most recent" in v.casefold() or "object at 0x" in v.casefold())
    return not bad(value)
def _identity(v:Mapping[str,Any],key:str,excluded:frozenset[str]=frozenset())->bool:
    try:
        fp=_hash({k:x for k,x in v.items() if k not in excluded|{key,"fingerprint"}})
        return v.get("fingerprint")==fp and v.get(key)==PREFIXES[key]+fp[:24]
    except (TypeError,ValueError):return False

def validate_authorization_review_policy(v:Any)->AuthorizationReviewValidationResult:
    if not isinstance(v,Mapping):return _result(["policy_not_object"])
    e=[]
    if v.get("schema")!=POLICY_SCHEMA:e.append("invalid_schema")
    if set(v.get("review_modes",[]))!=set(MODES) or not set(v.get("allowed_authorization_classes",[]))<=AUTHORIZATION_CLASSES or not set(v.get("allowed_activation_consumers",[]))<=ACTIVATION_CONSUMERS or not set(v.get("allowed_future_consumers",[]))<=FUTURE_CONSUMERS or v.get("required_reviewer_class") not in REVIEWER_CLASSES:e.append("invalid_allowlist")
    if not REQUIRED_PROHIBITIONS<=set(v.get("required_prohibited_actions",[])):e.append("unsafe_policy")
    if not _identity(v,"policy_id") or not _safe(v):e.append("policy_identity_or_safety_invalid")
    return _result(e)
def validate_authorization_review_request(v:Any)->AuthorizationReviewValidationResult:
    if not isinstance(v,Mapping):return _result(["request_not_object"])
    e=[];required={"schema","request_id","fingerprint","gate_decision_id","gate_decision_fingerprint","authorization_metadata_id","authorization_metadata_fingerprint","admission_decision_linkage","activation_handoff_linkage","runtime_context_linkage","requested_authorization_class","activation_consumer","future_consumer","review_mode","reviewer_class","policy","caller_metadata","requested_at"}
    e += [f"missing:{x}" for x in sorted(required-set(v))]+[f"unexpected:{x}" for x in sorted(set(v)-required)]
    if v.get("schema")!=REQUEST_SCHEMA:e.append("invalid_schema")
    if v.get("review_mode") not in MODES:e.append("unsupported_mode")
    if v.get("reviewer_class") not in REVIEWER_CLASSES:e.append("unsupported_reviewer_class")
    if v.get("requested_authorization_class") not in AUTHORIZATION_CLASSES:e.append("unsupported_authorization_class")
    if v.get("activation_consumer") not in ACTIVATION_CONSUMERS or v.get("future_consumer") not in FUTURE_CONSUMERS:e.append("unsupported_future_consumer")
    if not validate_authorization_review_policy(v.get("policy")).valid:e.append("invalid_policy")
    if not _identity(v,"request_id",frozenset({"requested_at"})):e.append("request_identity_mismatch")
    if not _safe({"caller_metadata":v.get("caller_metadata")}):e.append("unsafe_caller_metadata")
    return _result(e)
def validate_review_eligibility(v:Any)->AuthorizationReviewValidationResult:
    if not isinstance(v,Mapping):return _result(["eligibility_not_object"])
    e=[]
    if v.get("schema")!=ELIGIBILITY_SCHEMA or v.get("status") not in {"eligible","ineligible"}:e.append("invalid_eligibility")
    if v.get("eligible") is not (v.get("status")=="eligible") or v.get("eligible") and v.get("reason_codes"):e.append("eligibility_state_mismatch")
    if v.get("reviewer_class") not in REVIEWER_CLASSES:e.append("unsupported_reviewer_class")
    if not _identity(v,"eligibility_id") or not _safe(v):e.append("eligibility_identity_or_safety_invalid")
    return _result(e)
def validate_authorization_review_handoff(v:Any)->AuthorizationReviewValidationResult:
    if not isinstance(v,Mapping):return _result(["handoff_not_object"])
    e=[]
    if v.get("schema")!=HANDOFF_SCHEMA or v.get("review_status")!="reviewable" or v.get("reviewable") is not True:e.append("invalid_handoff")
    if v.get("reviewer_class") not in REVIEWER_CLASSES or v.get("future_activation_consumer") not in FUTURE_CONSUMERS:e.append("invalid_allowlist")
    if any(v.get(k) is not False for k in ("approval_issued","authorization_issued","token_issued","activation_performed","runtime_started","mutation_performed")):e.append("unsafe_handoff")
    if not REQUIRED_PROHIBITIONS<=set(v.get("prohibited_actions",[])):e.append("missing_prohibition")
    if not v.get("provenance"):e.append("missing_provenance")
    if not _identity(v,"handoff_id",frozenset({"prepared_at","review_linkage"})) or not _safe(v):e.append("handoff_identity_or_safety_invalid")
    return _result(e)
def validate_authorization_review(v:Any)->AuthorizationReviewValidationResult:
    if not isinstance(v,Mapping):return _result(["review_not_object"])
    e=[]
    if v.get("schema")!=REVIEW_SCHEMA or v.get("review_status") not in STATUSES:e.append("invalid_review")
    if v.get("reviewable") is not (v.get("review_status")=="reviewable") or v.get("reviewable") and v.get("blockers"):e.append("review_state_mismatch")
    if not validate_review_eligibility(v.get("eligibility")).valid:e.append("invalid_eligibility")
    if any(v.get(k) is not False for k in ("approval_issued","authorization_issued","token_issued","activation_performed","runtime_started","mutation_performed")):e.append("unsafe_review")
    if any(x!=0 for x in v.get("invocation_evidence",{}).values()):e.append("unsafe_invocation_evidence")
    handoff=v.get("review_handoff")
    if handoff is not None and not validate_authorization_review_handoff(handoff).valid:e.append("invalid_handoff")
    if not _identity(v,"review_id",frozenset({"reviewed_at","review_handoff","review_handoff_linkage"})) or not _safe(v):e.append("review_identity_or_safety_invalid")
    return _result(e)
__all__=["AuthorizationReviewValidationResult","validate_authorization_review_policy","validate_authorization_review_request","validate_review_eligibility","validate_authorization_review","validate_authorization_review_handoff"]
