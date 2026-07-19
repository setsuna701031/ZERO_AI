from tests.runtime_reference_adapter_executor_fixtures import run_pipeline
def test_evidence_excludes_payloads():
 e=run_pipeline({'secret':'not included'})['ev']; assert 'canonical_input_payload' not in e and 'secret' not in str(e)
