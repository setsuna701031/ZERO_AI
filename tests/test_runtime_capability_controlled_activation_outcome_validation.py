from copy import deepcopy
import pytest
from core.runtime.runtime_capability_controlled_activation_outcome_validation import validate_capability_controlled_activation_outcome as validate
from tests.test_runtime_capability_controlled_activation_outcome import outcome
def test_all_outcomes_nonmutating():
 for kind in ("activated","not_activated","blocked","failed","invalid","expired"):
  x=outcome(kind);y=deepcopy(x);assert validate(x).valid and x==y
 assert not validate(None).valid
@pytest.mark.parametrize("field,value",[("schema","x"),("outcome_id","x"),("fingerprint","x"),("outcome","unknown"),("observed_at","naive"),("activation_executed_by_contract",True),("activated",False)])
def test_tamper(field,value):x=outcome();x[field]=value;assert not validate(x).valid
def test_lineage_forbidden():
 x=outcome();del x["controlled_activation_preparation_id"];assert not validate(x).valid
 for n in ("command","process_id","stdout","endpoint","private_key"):
  x=outcome();x[n]="x";assert not validate(x).valid
