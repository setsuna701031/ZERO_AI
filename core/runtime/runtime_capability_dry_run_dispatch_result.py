from __future__ import annotations
from copy import deepcopy
from typing import Any,Mapping
from core.runtime.runtime_capability_execution_session_admission import _hash,_safe
CONTRACT="zero.runtime.capability_dry_run_dispatch_result.v1";SCHEMA_VERSION="1";OBSERVED=frozenset({"simulated","not_simulated","blocked","failed"});STATUSES=OBSERVED|{"invalid"}
_SUMMARY_KEYS=frozenset({"request_canonicalized","plan_generated","adapter_boundary_accepted","dry_run_simulation_generated"})
def build_capability_dry_run_dispatch_result(plan:Any,*,observed_status:Any,observation_summary:Any=None,evidence_references:Any=None,side_effects_performed:Any=None,failure_reasons:Any=None,blocked_reasons:Any=None)->dict[str,Any]:
 p=deepcopy(dict(plan)) if isinstance(plan,Mapping) else {}
 try:s=_safe({} if observation_summary is None else observation_summary);e=_safe([] if evidence_references is None else evidence_references);fx=_safe([] if side_effects_performed is None else side_effects_performed);fail=_safe([] if failure_reasons is None else failure_reasons);block=_safe([] if blocked_reasons is None else blocked_reasons)
 except (TypeError,ValueError):s={};e=[];fx=[];fail=["non_json_safe_result"];block=[];bad=True
 else:bad=False
 safe_summary=isinstance(s,Mapping) and set(s)<=_SUMMARY_KEYS;refs=isinstance(e,list) and all(isinstance(x,str) and x and "\n" not in x and "\r" not in x for x in e)
 if bad or observed_status not in OBSERVED or not safe_summary or not refs:status="invalid"
 elif fx!=[]:status="invalid";fail=["side_effect_invariant_violation"]
 elif p.get("plan_status")!="planned" or p.get("dry_run") is not True:status="blocked";block=["plan_not_dry_run_planned"]
 else:status=observed_status
 b={"contract":CONTRACT,"schema_version":SCHEMA_VERSION,"dispatch_plan_id":p.get("dispatch_plan_id",""),"dispatch_plan_fingerprint":p.get("dispatch_plan_fingerprint",""),"adapter_admission_id":p.get("adapter_admission_id",""),"adapter_admission_fingerprint":p.get("adapter_admission_fingerprint",""),"request_id":p.get("request_id",""),"request_fingerprint":p.get("request_fingerprint",""),"adapter_id":p.get("adapter_id",""),"operation_class":p.get("operation_class",""),"observed_status":observed_status if isinstance(observed_status,str) else "","result_status":status,"simulated":status=="simulated","side_effects_performed":fx,"observation_summary":s,"evidence_references":e if refs else [],"failure_reasons":fail,"blocked_reasons":block};f=_hash(b);return {**b,"dispatch_result_id":"capability-dry-run-dispatch-result-"+f[:24],"dispatch_result_fingerprint":f}
