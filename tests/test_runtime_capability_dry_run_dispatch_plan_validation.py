from tests.test_runtime_capability_dry_run_dispatch_plan import plan
from core.runtime.runtime_capability_dry_run_dispatch_plan_validation import validate_capability_dry_run_dispatch_plan as validate
def test_validation():x=plan();assert validate(x).valid;x["dry_run"]=False;assert not validate(x).valid
