import json
from cli.zero_capability_runtime_outcome_reconciliation import run
from tests.test_runtime_capability_execution_authority import authority
from tests.test_runtime_capability_bounded_execution_request import request
from tests.test_runtime_capability_executor_adapter_admission import adapter_admission
from tests.test_runtime_capability_dry_run_dispatch_plan import plan
from tests.test_runtime_capability_dry_run_dispatch_result import result
from core.runtime.runtime_capability_runtime_outcome_reconciliation_validation import validate_capability_runtime_outcome_reconciliation as validate
def test_cli(tmp_path):
 vals=[authority(),request(),adapter_admission(),plan(),result()];names=["authority","request","adapter-admission","dispatch-plan","dispatch-result"];args=[]
 for n,v in zip(names,vals):p=tmp_path/n;p.write_text(json.dumps(v));args += ["--"+n,str(p)]
 x,c=run(args);assert c==0 and validate(x).valid
