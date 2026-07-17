from copy import deepcopy
import pytest
from core.runtime.runtime_capability_controlled_activation_outcome import record_capability_controlled_activation_outcome as build
from tests.test_runtime_capability_controlled_activation_preparation import preparation
def outcome(kind="activated",value=None,at="2099-07-17T06:03:27Z",consumer="capability-runtime-activation-consumer",evidence="consumer_reported_activation_success"):return build(preparation() if value is None else value,outcome=kind,observed_at=at,consumer_id=consumer,evidence_code=evidence)
@pytest.mark.parametrize("kind",["activated","not_activated","blocked","failed","invalid","expired"])
def test_outcomes(kind):
 x=outcome(kind);assert x["outcome"]==kind and x[kind] and x["activation_outcome_recorded"] is(kind=="activated") and x["runtime_activation_reported"] is(kind=="activated") and not x["activation_executed_by_contract"] and not x["runtime_process_started_by_contract"]
def test_stable_detached_and_boundaries():
 u=preparation();saved=deepcopy(u);assert outcome(value=u)==outcome(value=dict(reversed(list(u.items())))) and u==saved;assert outcome(at="2099-07-17T06:03:25Z")["blocked"] and outcome(at="2099-07-17T06:03:53Z")["expired"]
@pytest.mark.parametrize("consumer,evidence",[("https://host","ok"),("other-consumer","ok"),("capability-runtime-activation-consumer",None),("capability-runtime-activation-consumer","Traceback_secret"),("capability-runtime-activation-consumer","C:\\path")])
def test_identity_evidence_invalid(consumer,evidence):assert outcome(consumer=consumer,evidence=evidence)["invalid"]
def test_forged_fail_closed():u=preparation();u["process_id"]=1;assert outcome(value=u)["blocked"]
