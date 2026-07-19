from tests.runtime_adapter_execution_integration_fixtures import *
def test_resource_bounds():
 p=pipeline(); assert p['bud']['budget_status']=='bounded'
 assert build_runtime_adapter_execution_resource_budget(max_wall_time_ms=-1,max_cpu_time_ms=1,max_memory_bytes=1,max_output_bytes=1,max_artifact_count=1,max_retry_count=0,max_parallel_units=1)['budget_status']=='invalid'
