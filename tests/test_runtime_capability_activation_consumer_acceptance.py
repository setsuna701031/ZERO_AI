from copy import deepcopy
import pytest
from tests.test_runtime_capability_runtime_activation_admission_handoff import admission_handoff
from core.runtime.runtime_capability_activation_consumer_acceptance import accept_capability_activation_consumer_handoff as build
from core.runtime.runtime_capability_runtime_activation_eligibility import _hash
def _retag(x,status,statuses,id_field,prefix):
 x=deepcopy(x);x["status"]=status
 for n in statuses:x[n]=n==status
 f=_hash({a:b for a,b in x.items() if a not in {id_field,"fingerprint"}});x[id_field]=prefix+f[:24];x["fingerprint"]=f;return x
def acceptance(value=None,at="2099-07-17T06:03:25Z",consumer="capability-runtime-activation-consumer"):return build(admission_handoff() if value is None else value,accepted_at=at,consumer_id=consumer)
def test_accepted_stable_detached_safe():
 u=admission_handoff();saved=deepcopy(u);a=acceptance(u);b=acceptance(dict(reversed(list(u.items()))));u["reasons"].append("x");assert a==b and u!=saved and a["accepted"] and a["activation_handoff_accepted"] and not any(a[n] for n in ("activation_command_created","activation_attempted","runtime_process_started","runtime_activated","executor_admitted","execution_session_created","execution_authority_granted"))
@pytest.mark.parametrize("source,target",[("not_handed_off","not_accepted"),("blocked","blocked"),("invalid","invalid"),("expired","expired")])
def test_mapping(source,target):
 u=admission_handoff();u["runtime_admission_handoff_created"]=source=="handed_off";u["runtime_admission_handed_off"]=source=="handed_off";u=_retag(u,source,("handed_off","not_handed_off","blocked","invalid","expired"),"handoff_id","capability-runtime-activation-admission-handoff-");assert acceptance(u)[target]
def test_identity_time_fail_closed():
 for x in (None,"","https://host","host:42","C:\\path","pipe:name","bad\nvalue"):assert acceptance(consumer=x)["blocked"]
 assert acceptance(at="2099-07-17T06:03:23Z")["blocked"] and acceptance(at="2099-07-17T06:03:53Z")["expired"] and acceptance({})["invalid"]
