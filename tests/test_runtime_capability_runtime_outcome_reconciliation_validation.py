from tests.test_runtime_capability_runtime_outcome_reconciliation import reconciliation
from core.runtime.runtime_capability_runtime_outcome_reconciliation_validation import validate_capability_runtime_outcome_reconciliation as validate
def test_validation():x=reconciliation();assert validate(x).valid;x["execution_completion_claim"]=True;assert not validate(x).valid
