from copy import deepcopy
from core.runtime.runtime_capability_observation_evidence_sufficiency_assessment_validation import validate_capability_observation_evidence_sufficiency_assessment as validate
from tests.test_runtime_capability_observation_evidence_sufficiency_assessment import sufficiency
def test_validation_requirements_and_limits(tmp_path):
 (tmp_path/"target.txt").touch();x=sufficiency(tmp_path);assert validate(x).valid;y=deepcopy(x);y["sufficiency_requirements"]["require_observed"]=1;assert not validate(y).valid
