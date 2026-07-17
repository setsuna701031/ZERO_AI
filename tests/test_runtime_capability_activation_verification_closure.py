from copy import deepcopy
import pytest
from core.runtime.runtime_capability_activation_verification_closure import close_capability_activation_verification as build
from tests.test_runtime_capability_controlled_activation_outcome import outcome
def closure(kind="activated",value=None,at="2099-07-17T06:03:28Z",verifier="capability-runtime-activation-verifier"):return build(outcome(kind) if value is None else value,verified_at=at,verifier_id=verifier)
@pytest.mark.parametrize("kind,target",[("activated","verified"),("not_activated","not_verified"),("blocked","blocked"),("failed","failed"),("invalid","invalid"),("expired","expired")])
def test_mapping(kind,target):
 x=closure(kind);assert x[target] and x["activation_verification_completed"] is(target=="verified") and x["activation_audit_closed"] is(target=="verified") and not x["runtime_process_started_by_contract"] and not x["executor_admitted"] and not x["execution_session_created"] and not x["execution_authority_granted"]
def test_stable_detached_time_identity():
 u=outcome();saved=deepcopy(u);assert closure(value=u)==closure(value=dict(reversed(list(u.items())))) and u==saved;assert closure(at="2099-07-17T06:03:26Z")["blocked"] and closure(at="2099-07-17T06:03:53Z")["expired"]
 for x in (None,"","https://host","host:42","C:\\path","bad\nvalue"):assert closure(verifier=x)["blocked"]
