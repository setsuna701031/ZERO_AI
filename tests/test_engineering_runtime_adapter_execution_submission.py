from tests.runtime_reference_adapter_executor_fixtures import handoff_for
from core.engineering.engineering_runtime_adapter_execution_submission import build_execution_submission
def test_submission_accepts_and_rejects_drift():
 h,c=handoff_for(); s=build_execution_submission(h,c,{'a':1},'input.contract'); assert s['submission_status']=='accepted'
 assert build_execution_submission(h,c,{'a':1},'input.contract',adapter_id='other')['submission_status']=='rejected'
 assert build_execution_submission(h,c,object(),'input.contract')['submission_status']=='rejected'
