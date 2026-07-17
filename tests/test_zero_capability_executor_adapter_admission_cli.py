import json
from cli.zero_capability_executor_adapter_admission import run
from tests.test_runtime_capability_execution_authority import authority
from tests.test_runtime_capability_bounded_execution_request import request
from core.runtime.runtime_capability_executor_adapter_admission_validation import validate_capability_executor_adapter_admission as validate
def test_cli(tmp_path):
 a=tmp_path/"a";r=tmp_path/"r";a.write_text(json.dumps(authority()));r.write_text(json.dumps(request()));x,c=run(["--authority",str(a),"--request",str(r)]);assert c==0 and validate(x).valid;assert run(["--authority","missing","--request",str(r)])[1]==2
