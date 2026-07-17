from dataclasses import dataclass
from typing import Any,Mapping
from core.runtime.runtime_capability_execution_session_admission import _hash
from core.runtime.runtime_capability_decision_transaction_preparation import HANDOFF_CONTRACT,PERMISSIONS,PROHIBITED
@dataclass(frozen=True)
class PreparedTransactionHandoffValidationResult:valid:bool;errors:tuple[str,...]
def validate_capability_prepared_transaction_handoff(v:Any)->PreparedTransactionHandoffValidationResult:
 if not isinstance(v,Mapping):return PreparedTransactionHandoffValidationResult(False,("handoff_not_object",))
 e=[]
 if v.get("contract")!=HANDOFF_CONTRACT or v.get("schema_version")!="1" or v.get("handoff_status") not in {"prepared","not_prepared","blocked","failed","invalid"}:e.append("invalid_contract_or_status")
 if v.get("dry_run_only") is not True or v.get("expected_effects")!=[] or any(v.get(k) is not False for k in ("execution_started_claim","execution_completion_claim","mutation_authorization_claim","mutation_performed_claim","transaction_committed_claim")):e.append("claim_invariant_violation")
 p=v.get("permissions");
 if not isinstance(p,Mapping) or set(p)!=set(PERMISSIONS) or any(x is not False for x in p.values()) or any(x not in v.get("prohibited_effects",[]) for x in PROHIBITED):e.append("permission_invariant_violation")
 try:f=_hash({k:x for k,x in v.items() if k not in {"handoff_id","handoff_fingerprint"}})
 except (TypeError,ValueError):e.append("noncanonical_value")
 else:
  if v.get("handoff_fingerprint")!=f or v.get("handoff_id")!="capability-prepared-transaction-handoff-"+f[:24]:e.append("identity_mismatch")
 return PreparedTransactionHandoffValidationResult(not e,tuple(dict.fromkeys(e)))
