from cli.zero_engineering_authorization import build_pipeline
from tests.test_engineering_approval_intake import approval_pipeline
def approval_closure():return approval_pipeline()["closure"]
def authorization_pipeline(intent=None):return build_pipeline(approval_closure(),intent or {})
def test_only_approved_closure_is_accepted():assert authorization_pipeline()["intake"]["status"]=="accepted"
