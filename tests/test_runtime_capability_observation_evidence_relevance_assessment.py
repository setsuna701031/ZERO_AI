from core.runtime.runtime_capability_observation_evidence_relevance_assessment import build_capability_observation_evidence_relevance_assessment as build
from tests.test_runtime_capability_observation_evidence_consumer_acceptance import acceptance
from tests.test_runtime_capability_observation_evidence_closure import closure
from tests.test_runtime_capability_read_only_observation_result import result
from tests.test_runtime_capability_bounded_observation_request import observation_request,limits
def question(qtype="target_exists",kind="existence"):return {"question_id":"q-1","question_type":qtype,"target_reference":{"relative_target":"target.txt"},"required_observation_kinds":[kind],"decision_scope":limits()}
def relevance(root,q=None):return build(acceptance(root),closure(root),result(root),observation_request(root=root),decision_question=question() if q is None else q)
def test_relevance_rules_and_boundaries(tmp_path):
 (tmp_path/"target.txt").touch();assert relevance(tmp_path)["relevance_status"]=="relevant" and relevance(tmp_path)==relevance(tmp_path)
 assert relevance(tmp_path,question("target_digest_available","sha256"))["relevance_status"]=="not_relevant"
 q=question();q["question_type"]="should_execute";assert relevance(tmp_path,q)["relevance_status"]=="blocked"
 q=question();q["target_reference"]={"relative_target":"other"};assert relevance(tmp_path,q)["relevance_status"]=="not_relevant"
