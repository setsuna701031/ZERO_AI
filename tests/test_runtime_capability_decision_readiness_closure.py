from copy import deepcopy
from core.runtime.runtime_capability_decision_readiness_closure import close_capability_decision_readiness as build
from tests.test_runtime_capability_execution_authority import authority
from tests.test_runtime_capability_bounded_execution_request import request
from tests.test_runtime_capability_observation_evidence_closure import closure as observation_closure
from tests.test_runtime_capability_observation_evidence_consumer_acceptance import acceptance
from tests.test_runtime_capability_observation_evidence_relevance_assessment import relevance
from tests.test_runtime_capability_observation_evidence_sufficiency_assessment import sufficiency
from tests.test_runtime_capability_decision_readiness_assessment import readiness
def bridge(root):
 o=observation_closure(root);return {"verification_status":"verified_closed","bridge_closure_id":o["bridge_closure_id"],"bridge_closure_fingerprint":o["bridge_closure_fingerprint"]}
def decision_closure(root):return build(authority(),request(),bridge(root),observation_closure(root),acceptance(root),relevance(root),sufficiency(root),readiness(root))
def test_closure_and_claims(tmp_path):
 (tmp_path/"target.txt").touch();x=decision_closure(tmp_path);assert x["verification_status"]=="verified_closed" and x["closed"] and x["execution_completion_claim"] is False and x["authorization_claim"] is False and x["decision_made_claim"] is False
 d=deepcopy(readiness(tmp_path));d["authorization_claim"]=True;assert build(authority(),request(),bridge(tmp_path),observation_closure(tmp_path),acceptance(tmp_path),relevance(tmp_path),sufficiency(tmp_path),d)["verification_status"]!="verified_closed"
