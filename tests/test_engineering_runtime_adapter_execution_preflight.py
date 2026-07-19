from tests.runtime_reference_adapter_executor_fixtures import handoff_for
from core.engineering.engineering_runtime_reference_adapters import default_reference_adapter_registry
from core.engineering.engineering_runtime_adapter_execution_submission import build_execution_submission
from core.engineering.engineering_runtime_adapter_execution_preflight import build_execution_preflight
def test_preflight_admits_and_rejects_unknown():
 h,c=handoff_for(); reg=default_reference_adapter_registry(); s=build_execution_submission(h,c,{'a':1},'input.contract'); assert build_execution_preflight(s,reg)['reference_execution_admitted'] is True
 s=dict(s); s['adapter_id']='missing'; assert build_execution_preflight(s,reg)['preflight_status']=='rejected'
