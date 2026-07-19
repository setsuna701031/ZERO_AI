from tests.runtime_reference_adapter_executor_fixtures import run_pipeline
def test_pre_start_cancellation_not_invoked():
 p=run_pipeline(cancel=True); assert p['ctrl']['controlled_execution_status']=='cancelled'; assert p['ctrl']['adapter_invoked'] is False; assert p['res']['result_status']=='cancelled'
