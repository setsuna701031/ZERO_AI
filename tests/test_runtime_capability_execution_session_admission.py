from copy import deepcopy
from core.runtime.runtime_capability_execution_session_admission import admit_capability_execution_session as build
def activation(status="verified"):return {"closure_id":"activation-1","fingerprint":"a"*64,"status":status,"activation_audit_closed":status=="verified"}
def admission():return build(activation(),capability_profile_id="profile-1",capability_strategy_id="strategy-1")
def test_admission_stable_detached_and_blocked():
    u=activation();saved=deepcopy(u);assert admission()["status"]=="admitted" and build(dict(reversed(list(u.items()))))==build(u) and u==saved
    assert build(activation("blocked"))["status"]=="blocked" and build(None)["status"]=="invalid"
