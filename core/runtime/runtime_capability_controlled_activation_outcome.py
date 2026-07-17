from __future__ import annotations
import re
from typing import Any,Mapping
from core.runtime.runtime_capability_activation_consumer_acceptance import _EXPIRIES,_LINEAGES,_FORBIDDEN,_governance_id,_time,_text,_identity
CAPABILITY_CONTROLLED_ACTIVATION_OUTCOME_SCHEMA="zero.runtime.capability_controlled_activation_outcome.v1"
CONTROLLED_ACTIVATION_OUTCOMES=frozenset({"activated","not_activated","blocked","failed","invalid","expired"})
MAX_EVIDENCE_CODE_LENGTH=128
_OUTCOME_FLAGS=("activation_executed_by_contract","runtime_process_started_by_contract","executor_admitted","execution_session_created","execution_authority_granted","mutation_authority_granted")
def _evidence(v:Any):
 if not isinstance(v,str):return None
 x=v.strip();low=x.lower()
 if not x or len(x)>MAX_EVIDENCE_CODE_LENGTH or any(ord(c)<32 or ord(c)==127 for c in x) or not re.fullmatch(r"[a-z0-9_\-]{1,128}",x) or any(t in low for t in ("traceback","password","secret","token_value","bearer","private_key","command_line","stdout","stderr")):return None
 return x
def record_capability_controlled_activation_outcome(controlled_activation_preparation:Any,*,outcome:Any,observed_at:Any=None,consumer_id:Any=None,evidence_code:Any=None)->dict[str,Any]:
 u=dict(controlled_activation_preparation) if isinstance(controlled_activation_preparation,Mapping) else {};ot,o=_time(observed_at,True);consumer=_governance_id(consumer_id);evidence=_evidence(evidence_code);reasons=[];errors=[];result="invalid"
 from core.runtime.runtime_capability_controlled_activation_preparation_validation import validate_capability_controlled_activation_preparation
 valid=validate_capability_controlled_activation_preparation(u)
 if o is None:errors.append("invalid_observed_at")
 if outcome not in CONTROLLED_ACTIVATION_OUTCOMES:errors.append("invalid_outcome")
 if consumer is None or (valid.valid and consumer!=u.get("consumer_id")):errors.append("invalid_consumer_id")
 if evidence is None:errors.append("invalid_evidence_code")
 forged=bool(set(u)&_FORBIDDEN) or any(n in u and u.get(n) is not False for n in _OUTCOME_FLAGS)
 if forged:result="blocked";reasons.append("authority_flag_violation");errors.append("activation_state_violation")
 elif not valid.valid:reasons.append("controlled_activation_preparation_invalid");errors.append("invalid_controlled_activation_preparation")
 elif errors:result="invalid";reasons.append("activation_outcome_evidence_invalid")
 else:
  _,p=_time(u.get("prepared_at"));limits=[_time(u.get(n))[1] for n in _EXPIRIES];s=u["status"]
  if s=="not_prepared":result="not_activated";reasons.append("controlled_activation_not_prepared")
  elif s in {"blocked","invalid","expired"}:result=s;reasons.append("controlled_activation_preparation_"+s)
  elif o<p:result="blocked";reasons.append("outcome_observation_not_yet_effective")
  elif o>=min(limits):result="expired";reasons.append("activation_observation_expired")
  else:result=outcome;reasons.append("consumer_reported_activation_"+outcome)
 base={"schema":CAPABILITY_CONTROLLED_ACTIVATION_OUTCOME_SCHEMA,"outcome":result,**{n:n==result for n in CONTROLLED_ACTIVATION_OUTCOMES},"observed_at":ot or "1970-01-01T00:00:00Z","consumer_id":consumer or "unavailable","evidence_code":evidence or "unavailable","prepared_at":_time(u.get("prepared_at"))[0] or "1970-01-01T00:00:00Z",**{n:_time(u.get(n))[0] or "1970-01-01T00:00:01Z" for n in _EXPIRIES},"controlled_activation_preparation_id":_text(u.get("preparation_id")),"controlled_activation_preparation_fingerprint":_text(u.get("fingerprint")),"activation_consumer_acceptance_id":_text(u.get("activation_consumer_acceptance_id")),"activation_consumer_acceptance_fingerprint":_text(u.get("activation_consumer_acceptance_fingerprint")),"activation_outcome_recorded":result=="activated","runtime_activation_reported":result=="activated",**{n:False for n in _OUTCOME_FLAGS},"reasons":sorted(set(reasons)),"errors":sorted(set(errors))}
 for z in _LINEAGES:base[z+"_id"]=_text(u.get(z+"_id"));base[z+"_fingerprint"]=_text(u.get(z+"_fingerprint"))
 r=_identity(base,"outcome","capability-controlled-activation-outcome-")
 from core.runtime.runtime_capability_controlled_activation_outcome_validation import validate_capability_controlled_activation_outcome
 if not validate_capability_controlled_activation_outcome(r).valid:raise RuntimeError("internal controlled activation outcome validation failed")
 return r
__all__=["CAPABILITY_CONTROLLED_ACTIVATION_OUTCOME_SCHEMA","CONTROLLED_ACTIVATION_OUTCOMES","MAX_EVIDENCE_CODE_LENGTH","record_capability_controlled_activation_outcome"]
