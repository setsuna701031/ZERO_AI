from tests.runtime_reference_adapter_executor_fixtures import run_pipeline
def test_closure_success_cancel_failure():
 assert run_pipeline()['clo']['closure_status']=='closed'; assert run_pipeline(cancel=True)['clo']['closure_status']=='closed'
