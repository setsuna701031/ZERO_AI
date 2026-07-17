import json
from cli.zero_capability_dry_run_dispatch_plan import run
from tests.test_runtime_capability_executor_adapter_admission import adapter_admission
from tests.test_runtime_capability_bounded_execution_request import request
from core.runtime.runtime_capability_dry_run_dispatch_plan_validation import validate_capability_dry_run_dispatch_plan as validate
def test_cli(tmp_path):
 a=tmp_path/"a";r=tmp_path/"r";a.write_text(json.dumps(adapter_admission()));r.write_text(json.dumps(request()));x,c=run(["--adapter-admission",str(a),"--request",str(r)]);assert c==0 and validate(x).valid
