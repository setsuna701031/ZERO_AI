from tests.runtime_adapter_execution_integration_fixtures import *
def test_stage_valid_chain_and_invariants():
 p=pipeline()
 assert p['prep']['preparation_status']=='prepared'
 assert p['rev']['review_status']=='approved'
 assert p['auth']['authorization_status']=='authorized' and p['auth']['real_execution_authorized'] is False
 assert p['envlp']['envelope_status']=='sealed'
 assert p['ready']['readiness_status']=='ready'
 assert p['close']['closure_status']=='closed'
 for k in ('real_execution_authorized','executor_invoked','runtime_invoked','effects_performed','mutation_performed'):
  assert p['hand'][k] is False
