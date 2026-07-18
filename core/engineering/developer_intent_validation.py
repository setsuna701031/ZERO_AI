from __future__ import annotations
from dataclasses import dataclass
from typing import Any,Mapping
from core.engineering.developer_intent import SCHEMA,STATUSES
from core.engineering.engineering_intake_common import generic_validate,passive_boundary,normalize_request
@dataclass(frozen=True)
class DeveloperIntentValidationResult:valid:bool;errors:tuple[str,...]
_REQUIRED={"schema","developer_intent_id","fingerprint","normalized_request","intent_types","requested_outcomes","explicit_constraints","requested_validation","scope_hints","risk_flags","status","reasons","boundary"}
def _identity_valid(v):
 from core.engineering.engineering_intake_common import identity_valid
 return identity_valid(v,"developer_intent_id","engineering-developer-intent-")
def _boundary_valid(v):return v.get("boundary")==passive_boundary("natural_language_intake")
def validate_developer_intent(value:Any)->DeveloperIntentValidationResult:
 errors=generic_validate(value,_REQUIRED,SCHEMA,set(STATUSES),"developer_intent_id","engineering-developer-intent-",passive_boundary("natural_language_intake"))
 if isinstance(value,Mapping):
  lists=("intent_types","requested_outcomes","explicit_constraints","requested_validation","scope_hints","risk_flags","reasons")
  if any(not isinstance(value.get(k),list) or not all(isinstance(x,str) and x for x in value.get(k,[])) for k in lists):errors.append("invalid_fields")
  if value.get("intent_types")!=sorted(set(value.get("intent_types",[]))):errors.append("noncanonical_intents")
  if value.get("status")=="accepted" and not value.get("intent_types"):errors.append("empty_accepted_intent")
  if value.get("status")!="invalid":
   try: normalized=normalize_request(value.get("normalized_request"))
   except (TypeError,ValueError):errors.append("invalid_normalized_request")
   else:
    if normalized!=value.get("normalized_request"):errors.append("request_not_normalized")
 return DeveloperIntentValidationResult(not errors,tuple(dict.fromkeys(errors)))
__all__=["DeveloperIntentValidationResult","validate_developer_intent"]
