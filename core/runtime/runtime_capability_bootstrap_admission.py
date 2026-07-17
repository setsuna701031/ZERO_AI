from __future__ import annotations
from copy import deepcopy
import hashlib, json
from typing import Any, Mapping
from core.runtime.runtime_capability_bootstrap_plan import canonical_json
from core.runtime.runtime_capability_bootstrap_consumer import CONSUMER_ID, PROHIBITED_ACTIONS

POLICY_SCHEMA="zero.runtime.capability_bootstrap_admission_policy.v1"
REQUEST_SCHEMA="zero.runtime.capability_bootstrap_admission_request.v1"
DECISION_SCHEMA="zero.runtime.capability_bootstrap_admission_decision.v1"
HANDOFF_SCHEMA="zero.runtime.capability_activation_handoff.v1"
MODES=frozenset({"validate_only","evaluate_admission","prepare_activation_handoff"})
STATUSES=frozenset({"validated","admitted","blocked","rejected","invalid","unsupported"})
FUTURE_CONSUMERS=frozenset({"capability_runtime_activation_gate_v1"})
REQUIRED=frozenset({"accepted_integration","active_readonly_lease","eligible_chain","inactive_runtime","mutation_free","valid_linkage","required_domains","strategy_allowed","worker_bounds","offline_safe","accelerator_consistent","prohibitions_complete","partial_policy","future_consumer_allowed"})

def _hash(v:Any)->str:return hashlib.sha256(canonical_json(v).encode()).hexdigest()
def _identified(v:Mapping[str,Any],key:str,prefix:str,excluded:frozenset[str]=frozenset())->dict[str,Any]:
 r=deepcopy(dict(v)); fp=_hash({k:x for k,x in r.items() if k not in excluded|{key,"fingerprint"}});r["fingerprint"]=fp;r[key]=prefix+fp[:24];return json.loads(canonical_json(r))

def default_policy()->dict[str,Any]:
 base={"schema":POLICY_SCHEMA,"allowed_consumer_ids":[CONSUMER_ID],"allowed_consumption_statuses":["consumed"],"required_lease_scopes":["combined_runtime_context_read"],"require_active_lease":True,"require_read_only_lease":True,"require_accepted_integration":True,"require_eligible_activation_decision":True,"require_runtime_inactive":True,"require_mutation_free_chain":True,"require_offline_safe_consistency":True,"require_provider_domain_readiness":True,"required_domains":["cpu"],"allowed_strategy_modes":["bounded"],"worker_bounds_policy":{"minimum":1,"maximum":8},"accelerator_policy":"disabled","allow_partial_consumption":False,"allowed_admission_modes":sorted(MODES),"future_consumer_allowlist":sorted(FUTURE_CONSUMERS),"safe_symbolic_metadata":{"contract":"admission_only"}}
 return _identified(base,"policy_id","capability-admission-policy-")

def create_admission_request(*,consumption_result:Mapping[str,Any],lease:Mapping[str,Any]|None,integration:Mapping[str,Any],runtime_context:Mapping[str,Any],mode:str="evaluate_admission",future_consumer:str="capability_runtime_activation_gate_v1",policy:Mapping[str,Any]|None=None,metadata:Mapping[str,Any]|None=None,requested_at:str|None=None)->dict[str,Any]:
 eligibility=consumption_result.get("eligibility",{})
 base={"schema":REQUEST_SCHEMA,"consumption_result_id":consumption_result.get("consumption_id"),"consumption_result_fingerprint":consumption_result.get("fingerprint"),"lease_id":lease.get("lease_id") if lease else None,"lease_fingerprint":lease.get("fingerprint") if lease else None,"consumer_eligibility_fingerprint":eligibility.get("fingerprint"),"integration_id":integration.get("integration_id"),"integration_fingerprint":integration.get("fingerprint"),"runtime_context_id":runtime_context.get("runtime_context_id"),"runtime_context_fingerprint":runtime_context.get("fingerprint"),"admission_mode":mode,"requested_future_consumer":future_consumer,"policy":deepcopy(dict(policy or default_policy())),"metadata":deepcopy(dict(metadata or {})),"requested_at":requested_at}
 return _identified(base,"request_id","capability-admission-request-",frozenset({"requested_at"}))

def _handoff(decision:Mapping[str,Any],result:Mapping[str,Any],lease:Mapping[str,Any],integration:Mapping[str,Any],context:Mapping[str,Any],prepared_at:str|None)->dict[str,Any]:
 base={"schema":HANDOFF_SCHEMA,"admission_decision_linkage":{"decision_id":decision.get("decision_id"),"fingerprint":decision.get("fingerprint")},"consumption_result_linkage":{"consumption_id":result.get("consumption_id"),"fingerprint":result.get("fingerprint")},"lease_linkage":{"lease_id":lease.get("lease_id"),"fingerprint":lease.get("fingerprint")},"integration_linkage":{"integration_id":integration.get("integration_id"),"fingerprint":integration.get("fingerprint")},"runtime_context_linkage":{"runtime_context_id":context.get("runtime_context_id"),"fingerprint":context.get("fingerprint")},"future_consumer":decision.get("future_consumer"),"admission_status":"admitted","read_only_context_entitlement":{"scope":lease.get("lease_scope"),"read_only":True},"prohibited_actions":sorted(set(PROHIBITED_ACTIONS)|{"authorize","issue_token"}),"required_authorization_class":"future_explicit_runtime_activation_authorization","mutation_classification":"none","runtime_start_allowed":False,"authorization_issued":False,"token_issued":False,"runtime_started":False,"safety_constraints":{"mutation_allowed":False,"offline_required":True},"provenance_chain":deepcopy(context.get("provenance_chain",{})),"prepared_at":prepared_at}
 return _identified(base,"handoff_id","capability-activation-handoff-",frozenset({"prepared_at","admission_decision_linkage"}))

def admit_capability_bootstrap(request:Mapping[str,Any],*,consumption_result:Mapping[str,Any],lease:Mapping[str,Any]|None,integration:Mapping[str,Any],runtime_context:Mapping[str,Any],evaluated_at:str|None=None)->dict[str,Any]:
 from core.runtime.runtime_capability_bootstrap_admission_validation import validate_admission_request
 from core.runtime.runtime_capability_bootstrap_consumer_validation import validate_consumption_result,validate_lease,validate_eligibility
 from core.runtime.runtime_capability_bootstrap_integration_validation import validate_integration_record,validate_runtime_context
 errors=list(validate_admission_request(request).errors);p=request.get("policy",{}); blockers=[]
 if not validate_consumption_result(consumption_result).valid: blockers.append("invalid_consumption_result")
 if lease is None: blockers.append("missing_lease")
 elif not validate_lease(lease).valid: blockers.append("invalid_lease")
 eligibility=consumption_result.get("eligibility",{})
 if not validate_eligibility(eligibility).valid or eligibility.get("eligible") is not True: blockers.append("consumer_ineligible")
 if not validate_integration_record(integration).valid: blockers.append("invalid_integration")
 if not validate_runtime_context(runtime_context).valid: blockers.append("invalid_runtime_context")
 if consumption_result.get("status") not in p.get("allowed_consumption_statuses",[]): blockers.append("consumption_status_not_allowed")
 if consumption_result.get("consumer_descriptor_linkage",{}).get("consumer_id") not in p.get("allowed_consumer_ids",[]): blockers.append("wrong_consumer")
 if integration.get("integration_status")!="accepted":blockers.append("integration_not_accepted")
 if integration.get("activation_eligibility",{}).get("eligible") is not True:blockers.append("activation_not_eligible")
 if lease:
  if lease.get("lease_status")!="active" or lease.get("revocation_status")!="not_revoked":blockers.append("lease_not_active")
  if lease.get("read_only") is not True or lease.get("mutation_allowed") is not False or lease.get("runtime_start_allowed") is not False:blockers.append("unsafe_lease")
  if lease.get("lease_scope") not in p.get("required_lease_scopes",[]):blockers.append("lease_scope_mismatch")
  if not set(PROHIBITED_ACTIONS)<=set(lease.get("prohibited_actions",[])):blockers.append("missing_prohibition")
 links=((request.get("consumption_result_id"),consumption_result.get("consumption_id")),(request.get("consumption_result_fingerprint"),consumption_result.get("fingerprint")),(request.get("integration_id"),integration.get("integration_id")),(request.get("integration_fingerprint"),integration.get("fingerprint")),(request.get("runtime_context_id"),runtime_context.get("runtime_context_id")),(request.get("runtime_context_fingerprint"),runtime_context.get("fingerprint")),(request.get("consumer_eligibility_fingerprint"),eligibility.get("fingerprint")))
 if any(a!=b for a,b in links) or (lease and (request.get("lease_id")!=lease.get("lease_id") or request.get("lease_fingerprint")!=lease.get("fingerprint"))):blockers.append("linkage_mismatch")
 if integration.get("runtime_context_id")!=runtime_context.get("runtime_context_id") or consumption_result.get("runtime_context_linkage",{}).get("fingerprint")!=runtime_context.get("fingerprint"):blockers.append("provenance_mismatch")
 if any(x is not False for x in (consumption_result.get("runtime_started"),integration.get("runtime_started"),runtime_context.get("runtime_started"))):blockers.append("runtime_already_started")
 if any(x is not False for x in (consumption_result.get("mutation_performed"),integration.get("mutation_performed"))):blockers.append("mutation_already_performed")
 missing=set(p.get("required_domains",[]))-set(runtime_context.get("available_domains",[]));
 if missing:blockers.append("required_domain_missing")
 if runtime_context.get("execution_mode") not in p.get("allowed_strategy_modes",[]):blockers.append("strategy_not_allowed")
 workers=runtime_context.get("worker_bounds",{}).get("max_workers");bounds=p.get("worker_bounds_policy",{})
 if isinstance(workers,bool) or not isinstance(workers,int) or not bounds.get("minimum",1)<=workers<=bounds.get("maximum",8):blockers.append("worker_bounds_invalid")
 if p.get("require_offline_safe_consistency") and runtime_context.get("network_mode")!="offline":blockers.append("offline_mismatch")
 if runtime_context.get("accelerator_policy")!=p.get("accelerator_policy"):blockers.append("accelerator_mismatch")
 warnings=list(consumption_result.get("warnings",[]))+list(integration.get("warnings",[]))
 if warnings and not p.get("allow_partial_consumption"):blockers.append("partial_not_allowed")
 if request.get("requested_future_consumer") not in p.get("future_consumer_allowlist",[]):blockers.append("unknown_future_consumer")
 blockers=sorted(set(blockers));mode=request.get("admission_mode")
 invalid_reasons={"invalid_consumption_result","invalid_lease","invalid_integration","invalid_runtime_context","linkage_mismatch","provenance_mismatch"}
 rejected_reasons={"wrong_consumer","unsafe_lease","runtime_already_started","mutation_already_performed"}
 unsupported=mode not in MODES or request.get("requested_future_consumer") not in FUTURE_CONSUMERS
 status="unsupported" if unsupported else "invalid" if errors or invalid_reasons.intersection(blockers) else "rejected" if rejected_reasons.intersection(blockers) else "validated" if mode=="validate_only" and not blockers else "blocked" if blockers else "admitted"
 admitted=status=="admitted";satisfied=sorted(REQUIRED) if admitted else [];evidence={k:0 for k in ("discovery_invocations","detector_invocations","provider_invocations","profile_builder_invocations","strategy_selection_invocations","registry_mutations","planner_invocations","executor_invocations","integration_invocations","consumer_invocations","runtime_startups","mission_agent_scheduler_worker_invocations","approval_invocations","authorization_invocations","token_issuances","filesystem_mutations","subprocess_invocations","network_invocations","dynamic_imports","model_gpu_activations")}
 base={"schema":DECISION_SCHEMA,"request_linkage":{"request_id":request.get("request_id"),"fingerprint":request.get("fingerprint")},"policy_linkage":{"policy_id":p.get("policy_id"),"fingerprint":p.get("fingerprint")},"consumption_result_linkage":{"consumption_id":consumption_result.get("consumption_id"),"fingerprint":consumption_result.get("fingerprint")},"lease_linkage":{"lease_id":lease.get("lease_id"),"fingerprint":lease.get("fingerprint")} if lease else None,"eligibility_linkage":{"fingerprint":eligibility.get("fingerprint")},"integration_linkage":{"integration_id":integration.get("integration_id"),"fingerprint":integration.get("fingerprint")},"runtime_context_linkage":{"runtime_context_id":runtime_context.get("runtime_context_id"),"fingerprint":runtime_context.get("fingerprint")},"admission_status":status,"admitted":admitted,"blockers":errors or blockers,"warnings":warnings,"required_conditions":sorted(REQUIRED),"satisfied_conditions":satisfied,"unsatisfied_conditions":errors or blockers,"future_consumer":request.get("requested_future_consumer"),"activation_handoff":None,"safety_attestations":{"runtime_started":False,"mutation_performed":False,"authorization_issued":False,"token_issued":False},"invocation_evidence":evidence,"runtime_started":False,"mutation_performed":False,"authorization_issued":False,"token_issued":False,"evaluated_at":evaluated_at}
 decision=_identified(base,"decision_id","capability-admission-decision-",frozenset({"evaluated_at","activation_handoff"}))
 if admitted and mode=="prepare_activation_handoff":decision["activation_handoff"]=_handoff(decision,consumption_result,lease,integration,runtime_context,evaluated_at)
 return json.loads(canonical_json(decision))

__all__=["POLICY_SCHEMA","REQUEST_SCHEMA","DECISION_SCHEMA","HANDOFF_SCHEMA","MODES","STATUSES","FUTURE_CONSUMERS","default_policy","create_admission_request","admit_capability_bootstrap"]
