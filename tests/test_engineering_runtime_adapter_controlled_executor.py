from tests.runtime_reference_adapter_executor_fixtures import run_pipeline
def test_echo_success_and_flags_false():
 p=run_pipeline({'x':[1,2]}); c=p['ctrl']; assert c['controlled_execution_status']=='completed' and c['adapter_invoked'] is True and c['external_effects_performed'] is False
