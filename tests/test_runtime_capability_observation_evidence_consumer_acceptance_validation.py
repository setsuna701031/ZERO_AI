from copy import deepcopy
from core.runtime.runtime_capability_observation_evidence_consumer_acceptance_validation import validate_capability_observation_evidence_consumer_acceptance as validate
from tests.test_runtime_capability_observation_evidence_consumer_acceptance import acceptance
def test_validation_tampering_and_detachment(tmp_path):
 (tmp_path/"target.txt").touch();x=acceptance(tmp_path);assert validate(x).valid;y=deepcopy(x);y["observation_kind"]="unknown";assert not validate(y).valid
