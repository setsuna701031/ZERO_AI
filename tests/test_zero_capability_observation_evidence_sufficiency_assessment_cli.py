from cli import zero_capability_observation_evidence_sufficiency_assessment as cli
from core.runtime.runtime_capability_observation_evidence_sufficiency_assessment_validation import validate_capability_observation_evidence_sufficiency_assessment as validate
from tests.test_runtime_capability_observation_evidence_relevance_assessment import relevance
from tests.test_runtime_capability_observation_evidence_consumer_acceptance import acceptance
from tests.test_runtime_capability_observation_evidence_closure import closure
from tests.test_runtime_capability_read_only_observation_result import result
from tests.test_runtime_capability_observation_evidence_sufficiency_assessment import requirements
def test_cli(monkeypatch,tmp_path):
 (tmp_path/"target.txt").touch();vals={"r":relevance(tmp_path),"a":acceptance(tmp_path),"c":closure(tmp_path),"x":result(tmp_path),"s":requirements()};monkeypatch.setattr(cli,"_read",vals.__getitem__);x,code=cli.run(["--relevance","r","--acceptance","a","--observation-closure","c","--observation-result","x","--sufficiency-requirements","s"]);assert code==0 and validate(x).valid
