from dataclasses import dataclass
from typing import Any,Mapping
from core.runtime.runtime_capability_execution_session_admission import _hash
from core.runtime.runtime_capability_decision_transaction_preparation import CLOSURE_CONTRACT
@dataclass(frozen=True)
class TransactionPreparationIntegrationClosureValidationResult:valid:bool;errors:tuple[str,...]
def validate_capability_transaction_preparation_integration_closure(v:Any)->TransactionPreparationIntegrationClosureValidationResult:
 if not isinstance(v,Mapping):return TransactionPreparationIntegrationClosureValidationResult(False,("integration_closure_not_object",))
 e=[];s=v.get("verification_status")
 if v.get("contract")!=CLOSURE_CONTRACT or v.get("schema_version")!="1" or s not in {"verified_closed","not_verified","blocked","failed","invalid"} or v.get("closed") is not(s=="verified_closed"):e.append("invalid_contract_or_status")
 if any(v.get(k) is not False for k in ("execution_started_claim","execution_completion_claim","mutation_authorization_claim","mutation_performed_claim","transaction_committed_claim")):e.append("forbidden_claim")
 if s=="verified_closed" and (not isinstance(v.get("integration_checks"),Mapping) or not all(x is True for x in v["integration_checks"].values())):e.append("invalid_success_transition")
 try:f=_hash({k:x for k,x in v.items() if k not in {"integration_closure_id","integration_closure_fingerprint"}})
 except (TypeError,ValueError):e.append("noncanonical_value")
 else:
  if v.get("integration_closure_fingerprint")!=f or v.get("integration_closure_id")!="capability-transaction-preparation-integration-closure-"+f[:24]:e.append("identity_mismatch")
 return TransactionPreparationIntegrationClosureValidationResult(not e,tuple(dict.fromkeys(e)))
