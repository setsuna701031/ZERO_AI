from copy import deepcopy
from core.runtime.runtime_capability_observation_evidence_relevance_assessment_validation import validate_capability_observation_evidence_relevance_assessment as validate
from tests.test_runtime_capability_observation_evidence_relevance_assessment import relevance
def test_validation_question_consistency(tmp_path):
 (tmp_path/"target.txt").touch();x=relevance(tmp_path);assert validate(x).valid;y=deepcopy(x);y["target_reference"]={"relative_target":"other"};assert not validate(y).valid
