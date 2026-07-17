from cli import zero_capability_decision_policy_evaluation as cli
from core.runtime.runtime_capability_decision_policy_evaluation_validation import validate_capability_decision_policy_evaluation as validate
from tests.test_runtime_capability_decision_review_eligibility import eligibility
from tests.test_runtime_capability_bounded_decision_review_request import review_request
from tests.test_runtime_capability_decision_readiness_closure import decision_closure
def test_cli(monkeypatch,tmp_path):
 (tmp_path/"target.txt").touch();monkeypatch.setattr(cli,"_read",{"e":eligibility(tmp_path),"r":review_request(tmp_path),"c":decision_closure(tmp_path)}.__getitem__);x,code=cli.run(["--eligibility","e","--review-request","r","--readiness-closure","c"]);assert code==0 and validate(x).valid
