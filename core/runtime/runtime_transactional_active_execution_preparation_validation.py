from dataclasses import dataclass
from typing import Any, Mapping
from core.runtime.runtime_transactional_active_execution import PREPARATION_CONTRACT,_fingerprint,_PREPARATION_PERMISSIONS,_PROHIBITED_EFFECTS
@dataclass(frozen=True)
class TransactionalActiveExecutionPreparationValidationResult:valid:bool;errors:tuple[str,...]
_CLAIMS=("execution_started_claim","execution_completion_claim","mutation_authorization_claim","mutation_performed_claim","transaction_committed_claim")
_REQUIRED={"contract","schema_version","preparation_id","preparation_fingerprint","execution_plan_id","execution_plan_fingerprint","execution_plan_review_id","execution_plan_review_fingerprint","executor_admission_token_id","executor_admission_token_fingerprint","controlled_activation_id","controlled_activation_fingerprint","active_authorization_id","active_authorization_fingerprint","intent_id","intent_fingerprint","target_root_identity","target_boundary","authorized_scope","prepared_scope","operation_descriptors","validation_descriptors","transaction_sequencing_metadata","dry_run_only","expected_effects","prohibited_effects","permissions","limitations","workspace_creation_required","snapshot_creation_required","mutation_required","validation_process_required","commit_required","rollback_capability_required","preparation_status","prepared",*_CLAIMS,"reasons","blocked_reasons","failure_reasons"}
def validate_transactional_active_plan_preparation(value:Any)->TransactionalActiveExecutionPreparationValidationResult:
 if not isinstance(value,Mapping):return TransactionalActiveExecutionPreparationValidationResult(False,("preparation_not_object",))
 e=[];status=value.get("preparation_status")
 if set(value)!=_REQUIRED:e.append("invalid_fields")
 if value.get("contract")!=PREPARATION_CONTRACT or value.get("schema_version")!="1" or status not in {"prepared","blocked","failed","invalid"} or value.get("prepared") is not(status=="prepared"):e.append("invalid_contract_or_status")
 if value.get("dry_run_only") is not True or value.get("expected_effects")!=[] or any(value.get(k) is not False for k in ("workspace_creation_required","snapshot_creation_required","mutation_required","validation_process_required","commit_required",*_CLAIMS)):e.append("side_effect_invariant_violation")
 p=value.get("permissions")
 if not isinstance(p,Mapping) or set(p)!=set(_PREPARATION_PERMISSIONS) or any(x is not False for x in p.values()):e.append("permission_invariant_violation")
 if not isinstance(value.get("prohibited_effects"),list) or any(x not in value["prohibited_effects"] for x in _PROHIBITED_EFFECTS) or value.get("prepared_scope")!=value.get("authorized_scope"):e.append("scope_or_prohibition_violation")
 try:f=_fingerprint({k:x for k,x in value.items() if k not in {"preparation_id","preparation_fingerprint"}})
 except (TypeError,ValueError):e.append("noncanonical_value")
 else:
  if value.get("preparation_fingerprint")!=f:e.append("fingerprint_mismatch")
  if value.get("preparation_id")!="transaction-preparation-"+f[:24]:e.append("id_mismatch")
 return TransactionalActiveExecutionPreparationValidationResult(not e,tuple(dict.fromkeys(e)))
