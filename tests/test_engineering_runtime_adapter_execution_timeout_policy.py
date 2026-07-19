from tests.runtime_adapter_execution_integration_fixtures import *
def test_timeout_bounds():
 p=pipeline(); assert p['to']['timeout_status']=='bounded'
 assert build_runtime_adapter_execution_timeout_policy(startup_timeout_ms='1',execution_timeout_ms=1,shutdown_timeout_ms=1,cancellation_mode='cooperative',cancellation_grace_ms=0)['timeout_status']=='invalid'
