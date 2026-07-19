from tests.runtime_reference_adapter_executor_fixtures import run_pipeline
from core.engineering.engineering_runtime_adapter_execution_verification import verify_execution_result
def test_verification_success_and_mismatch():
 p=run_pipeline(); assert p['ver']['verification_status']=='verified'; r=dict(p['res']); r['submission_id']='bad'; assert verify_execution_result(r,p['sub'],p['pre'],p['ctrl'],p['reg'])['verification_status']=='not_verified'
