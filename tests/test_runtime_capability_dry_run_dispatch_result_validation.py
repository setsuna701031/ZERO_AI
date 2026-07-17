from tests.test_runtime_capability_dry_run_dispatch_result import result
from core.runtime.runtime_capability_dry_run_dispatch_result_validation import validate_capability_dry_run_dispatch_result as validate
def test_validation():x=result();assert validate(x).valid;x["side_effects_performed"]=["x"];assert not validate(x).valid
