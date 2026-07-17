from copy import deepcopy
import pytest
from core.runtime.runtime_capability_controlled_activation_preparation import prepare_capability_controlled_activation as build
from tests.test_runtime_capability_activation_consumer_acceptance import acceptance,_retag
def preparation(value=None,at="2099-07-17T06:03:26Z"):return build(acceptance() if value is None else value,prepared_at=at)
def test_prepared_stable_safe():
 u=acceptance();saved=deepcopy(u);a=preparation(u);assert a==preparation() and u==saved and a["prepared"] and not a["activation_attempted"] and not a["runtime_process_started"]
@pytest.mark.parametrize("source,target",[("not_accepted","not_prepared"),("blocked","blocked"),("invalid","invalid"),("expired","expired")])
def test_mapping(source,target):
 u=_retag(acceptance(),source,("accepted","not_accepted","blocked","invalid","expired"),"acceptance_id","capability-activation-consumer-acceptance-");u["activation_consumer_acceptance_created"]=source=="accepted";u["activation_handoff_accepted"]=source=="accepted";u=_retag(u,source,("accepted","not_accepted","blocked","invalid","expired"),"acceptance_id","capability-activation-consumer-acceptance-");assert preparation(u)[target]
def test_time():assert preparation(at="2099-07-17T06:03:24Z")["blocked"] and preparation(at="2099-07-17T06:03:53Z")["expired"]
