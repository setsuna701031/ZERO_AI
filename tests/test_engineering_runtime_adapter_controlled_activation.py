from tests.runtime_adapter_activation_fixtures import *
def test_controlled_activation_invariants():
 p=pipeline(); ca=p['ca']; assert ca['activation_status']=='activated'; assert ca['governance_transition_committed'] is True; assert ca['token_consumption_required'] is True
 for k in ['adapter_loaded','adapter_code_executed','adapter_invoked','runtime_invoked','executor_invoked','scheduler_invoked','authority_consumed','repository_mutation_performed']: assert ca[k] is False
 assert build_runtime_adapter_controlled_activation(dict(p['pr'],preparation_status='not_prepared'),p['ad'])['activation_status']=='not_activated'
