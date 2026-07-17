import json
from cli.zero_capability_dry_run_dispatch_result import run
from tests.test_runtime_capability_dry_run_dispatch_plan import plan
from core.runtime.runtime_capability_dry_run_dispatch_result_validation import validate_capability_dry_run_dispatch_result as validate
def test_cli(tmp_path):
 p=tmp_path/"p";p.write_text(json.dumps(plan()));x,c=run(["--dispatch-plan",str(p),"--observed-status","simulated"]);assert c==0 and validate(x).valid
