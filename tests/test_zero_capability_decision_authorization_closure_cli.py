from cli import zero_capability_decision_authorization_closure as cli
from core.runtime.runtime_capability_decision_authorization_closure_validation import validate_capability_decision_authorization_closure as validate
from tests.test_runtime_capability_execution_authority import authority
from tests.test_runtime_capability_bounded_execution_request import request
from tests.test_runtime_capability_observation_evidence_closure import closure
from tests.test_runtime_capability_decision_readiness_closure import decision_closure
from tests.test_runtime_capability_bounded_decision_review_request import review_request
from tests.test_runtime_capability_decision_review_eligibility import eligibility
from tests.test_runtime_capability_decision_policy_evaluation import policy
from tests.test_runtime_capability_decision_authorization import authorization
def test_cli(monkeypatch,tmp_path):
 (tmp_path/"target.txt").touch();vals=dict(zip("axocrepz",(authority(),request(),closure(tmp_path),decision_closure(tmp_path),review_request(tmp_path),eligibility(tmp_path),policy(tmp_path),authorization(tmp_path))));monkeypatch.setattr(cli,"_read",vals.__getitem__);args=[]
 for n,k in zip(("authority","execution-request","observation-closure","readiness-closure","review-request","eligibility","policy","authorization"),vals):args += ["--"+n,k]
 x,code=cli.run(args);assert code==0 and validate(x).valid
