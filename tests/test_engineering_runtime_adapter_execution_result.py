from tests.runtime_reference_adapter_executor_fixtures import run_pipeline
def test_result_linkage_success_failure_cancel():
 assert run_pipeline()['res']['result_status']=='succeeded'
 assert run_pipeline(cancel=True)['res']['result_status']=='cancelled'
