from core.engineering.engineering_runtime_adapter_execution_output import validate_canonical_payload, build_execution_output
def test_output_rejects_callable_binary_oversize():
 assert validate_canonical_payload({'a':1})[0]
 assert not validate_canonical_payload(lambda x:x)[0]
 assert not validate_canonical_payload(b'x')[0]
 assert build_execution_output({}, {'x':'y'}, {'contract_id':'output.contract'})['output_valid']
