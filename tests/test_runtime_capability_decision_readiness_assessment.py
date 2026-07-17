from copy import deepcopy
from core.runtime.runtime_capability_decision_readiness_assessment import build_capability_decision_readiness_assessment as build
from tests.test_runtime_capability_observation_evidence_consumer_acceptance import acceptance
from tests.test_runtime_capability_observation_evidence_relevance_assessment import relevance
from tests.test_runtime_capability_observation_evidence_sufficiency_assessment import sufficiency
from tests.test_runtime_capability_observation_evidence_closure import closure
def readiness(root):return build(acceptance(root),relevance(root),sufficiency(root),closure(root))
def test_readiness_claims_and_mapping(tmp_path):
 (tmp_path/"target.txt").touch();x=readiness(tmp_path);assert x["decision_status"]=="ready" and x["execution_completion_claim"] is False and x["authorization_claim"] is False and x["recommended_next_stage"]=="bounded_decision_review"
 s=deepcopy(sufficiency(tmp_path));s["sufficiency_status"]="insufficient";s["sufficient"]=False;assert build(acceptance(tmp_path),relevance(tmp_path),s,closure(tmp_path))["decision_status"]=="not_ready"
