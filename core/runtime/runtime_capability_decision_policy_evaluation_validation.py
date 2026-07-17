from dataclasses import dataclass
from typing import Any,Mapping
from core.runtime.runtime_capability_decision_policy_evaluation import *
from core.runtime.runtime_capability_bounded_decision_review_request import PERMISSION_FIELDS
from core.runtime.runtime_capability_execution_session_admission import _hash
@dataclass(frozen=True)
class CapabilityDecisionPolicyEvaluationValidationResult:valid:bool;errors:tuple[str,...]
_REQ={"contract","schema_version","decision_policy_evaluation_id","decision_policy_evaluation_fingerprint","decision_review_eligibility_id","decision_review_eligibility_fingerprint","decision_review_request_id","decision_review_request_fingerprint","decision_readiness_closure_id","decision_readiness_closure_fingerprint","policy_id","policy_version","proposal_type","requested_effect_class","policy_rules","policy_results","policy_status","approved","approved_scope","approved_effect_class","approved_permissions","limitations","reasons","blocked_reasons"}
def validate_capability_decision_policy_evaluation(v:Any)->CapabilityDecisionPolicyEvaluationValidationResult:
 if not isinstance(v,Mapping):return CapabilityDecisionPolicyEvaluationValidationResult(False,("policy_evaluation_not_object",))
 e=[];s=v.get("policy_status");p=v.get("approved_permissions");ptype=v.get("proposal_type")
 if set(v)!=_REQ:e.append("invalid_fields")
 if v.get("contract")!=CONTRACT or v.get("schema_version")!=SCHEMA_VERSION or s not in STATUSES or v.get("approved") is not(s=="approved"):e.append("invalid_contract_or_status")
 if v.get("policy_id")!=POLICY_ID or type(v.get("policy_version")) is not int or v.get("policy_version")!=POLICY_VERSION:e.append("fixed_policy_mismatch")
 if not isinstance(p,Mapping) or set(p)!=PERMISSION_FIELDS or any(x is not False for x in p.values()):e.append("permission_violation")
 if s=="approved" and (ptype not in EFFECT_RULES or v.get("requested_effect_class") not in EFFECT_RULES[ptype] or v.get("approved_effect_class")!=v.get("requested_effect_class") or not isinstance(v.get("policy_results"),Mapping) or v["policy_results"].get("valid") is not True):e.append("fixed_rule_mismatch")
 try:f=_hash({k:x for k,x in v.items() if k not in {"decision_policy_evaluation_id","decision_policy_evaluation_fingerprint"}})
 except (TypeError,ValueError):e.append("noncanonical_value")
 else:
  if v.get("decision_policy_evaluation_fingerprint")!=f:e.append("fingerprint_mismatch")
  if v.get("decision_policy_evaluation_id")!="capability-decision-policy-evaluation-"+f[:24]:e.append("id_mismatch")
 return CapabilityDecisionPolicyEvaluationValidationResult(not e,tuple(dict.fromkeys(e)))
