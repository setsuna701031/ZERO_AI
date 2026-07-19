from core.engineering.engineering_runtime_adapter_execution_failure import normalize_exception
def test_failure_normalized_no_traceback():
 f=normalize_exception(ValueError('secret path traceback')); assert 'traceback' not in str(f).lower() and 'secret path' not in str(f).lower()
