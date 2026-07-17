from copy import deepcopy
from core.runtime.runtime_capability_activation_gate import create_activation_gate_request, default_policy, evaluate_activation_gate, _identified
from core.runtime.runtime_capability_bootstrap_admission import admit_capability_bootstrap, create_admission_request
from tests.test_runtime_capability_bootstrap_admission import chain

def admitted_chain():
    result,lease,integration,context=chain(); request=create_admission_request(consumption_result=result,lease=lease,integration=integration,runtime_context=context,mode="prepare_activation_handoff"); admission=admit_capability_bootstrap(request,consumption_result=result,lease=lease,integration=integration,runtime_context=context)
    return admission,admission["activation_handoff"],result,lease,integration,context
def evaluate(values, **kw):
    admission,handoff,result,lease,integration,context=values; request=create_activation_gate_request(admission_decision=admission,activation_handoff=handoff,consumption_result=result,lease=lease,integration=integration,runtime_context=context,**kw)
    return evaluate_activation_gate(request,admission_decision=admission,activation_handoff=handoff,consumption_result=result,lease=lease,integration=integration,runtime_context=context)
def test_deterministic_allowed_and_sealed_authorization_metadata():
    values=admitted_chain(); one=evaluate(values,mode="prepare_authorization_request",requested_at="one"); two=evaluate(values,mode="prepare_authorization_request",requested_at="two")
    assert one["allowed"] and one["decision_id"]==two["decision_id"] and one["authorization_request"]["authorization_request_id"]==two["authorization_request"]["authorization_request_id"]
    assert all(one[k] is False for k in ("runtime_started","mutation_performed","authorization_issued","token_issued","activation_performed")) and set(one["invocation_evidence"].values())=={0}
def test_validate_only_and_failure_classification():
    values=admitted_chain(); assert evaluate(values,mode="validate_only")["gate_status"]=="validated"
    changed=list(values); changed[3]=deepcopy(changed[3]); changed[3]["lease_status"]="revoked"; changed[3]["revocation_status"]="revoked"
    assert evaluate(tuple(changed))["gate_status"]=="rejected"
    changed=list(values); changed[5]=deepcopy(changed[5]); changed[5]["available_domains"]=[]
    assert evaluate(tuple(changed))["gate_status"] in {"invalid","blocked"}
def test_warnings_default_block_and_explicit_policy_allows():
    values=list(admitted_chain()); values[0]=deepcopy(values[0]); values[0]["warnings"]=["safe_partial"]
    from core.runtime.runtime_capability_bootstrap_admission import _identified as identify
    values[0].pop("decision_id");values[0].pop("fingerprint");values[0]=identify(values[0],"decision_id","capability-admission-decision-",frozenset({"evaluated_at","activation_handoff"}))
    values[1]=deepcopy(values[1]);values[1]["admission_decision_linkage"]={"decision_id":values[0]["decision_id"],"fingerprint":values[0]["fingerprint"]}
    assert evaluate(tuple(values))["gate_status"]=="blocked"
    policy=default_policy();policy.pop("policy_id");policy.pop("fingerprint");policy["allow_warnings"]=True;policy=_identified(policy,"policy_id","capability-activation-gate-policy-")
    assert evaluate(tuple(values),policy=policy)["gate_status"]=="allowed"
