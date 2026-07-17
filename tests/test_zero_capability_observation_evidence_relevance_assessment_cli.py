from cli import zero_capability_observation_evidence_relevance_assessment as cli
from core.runtime.runtime_capability_observation_evidence_relevance_assessment_validation import validate_capability_observation_evidence_relevance_assessment as validate
from tests.test_runtime_capability_observation_evidence_consumer_acceptance import acceptance
from tests.test_runtime_capability_observation_evidence_closure import closure
from tests.test_runtime_capability_read_only_observation_result import result
from tests.test_runtime_capability_bounded_observation_request import observation_request
from tests.test_runtime_capability_observation_evidence_relevance_assessment import question
def test_cli(monkeypatch,tmp_path):
 (tmp_path/"target.txt").touch();vals={"a":acceptance(tmp_path),"c":closure(tmp_path),"x":result(tmp_path),"q":observation_request(root=tmp_path),"d":question()};monkeypatch.setattr(cli,"_read",vals.__getitem__);x,code=cli.run(["--acceptance","a","--observation-closure","c","--observation-result","x","--observation-request","q","--decision-question","d"]);assert code==0 and validate(x).valid
