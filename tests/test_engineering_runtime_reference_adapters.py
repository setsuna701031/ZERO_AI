from tests.runtime_reference_adapter_executor_fixtures import run_pipeline
def test_builtin_reference_adapters():
 assert run_pipeline({'a':1},'canonical_echo','echo')['res']['result_status']=='succeeded'
 assert run_pipeline({'source':{'a':1,'b':2},'fields':['b']},'canonical_select','select')['ctrl']['output']['canonical_output']=={'b':2}
 assert run_pipeline({'left':1,'right':1},'canonical_compare','compare')['ctrl']['output']['canonical_output']=={'equal':True}
 assert 'sha256' in run_pipeline({'a':1},'canonical_hash','hash')['ctrl']['output']['canonical_output']
