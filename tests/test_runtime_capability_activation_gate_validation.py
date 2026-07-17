from copy import deepcopy
from core.runtime.runtime_capability_activation_gate import create_activation_gate_request, evaluate_activation_gate
from core.runtime.runtime_capability_activation_gate_validation import validate_activation_authorization_request, validate_activation_gate_decision, validate_activation_gate_policy, validate_activation_gate_request
from tests.test_runtime_capability_activation_gate import admitted_chain

def artifacts(mode="prepare_authorization_request"):
    admission,handoff,result,lease,integration,context=admitted_chain(); request=create_activation_gate_request(admission_decision=admission,activation_handoff=handoff,consumption_result=result,lease=lease,integration=integration,runtime_context=context,mode=mode); decision=evaluate_activation_gate(request,admission_decision=admission,activation_handoff=handoff,consumption_result=result,lease=lease,integration=integration,runtime_context=context); return request,decision
def test_contracts_validate():
    request,decision=artifacts(); assert validate_activation_gate_policy(request["policy"]).valid and validate_activation_gate_request(request).valid and validate_activation_gate_decision(decision).valid and validate_activation_authorization_request(decision["authorization_request"]).valid
def test_tampering_and_unsafe_metadata_rejected():
    request,_=artifacts("evaluate_gate"); bad=deepcopy(request);bad["runtime_context_fingerprint"]="wrong";assert not validate_activation_gate_request(bad).valid
    for metadata in ({"token":"secret"},{"command":"run"},{"provider":object()}):
        values=admitted_chain()
        try: candidate=create_activation_gate_request(admission_decision=values[0],activation_handoff=values[1],consumption_result=values[2],lease=values[3],integration=values[4],runtime_context=values[5],caller_metadata=metadata)
        except (TypeError,ValueError): continue
        assert not validate_activation_gate_request(candidate).valid
def test_unsupported_values_fail_closed():
    values=admitted_chain(); request=create_activation_gate_request(admission_decision=values[0],activation_handoff=values[1],consumption_result=values[2],lease=values[3],integration=values[4],runtime_context=values[5],mode="activate")
    decision=evaluate_activation_gate(request,admission_decision=values[0],activation_handoff=values[1],consumption_result=values[2],lease=values[3],integration=values[4],runtime_context=values[5]); assert decision["gate_status"]=="unsupported" and not decision["allowed"]
