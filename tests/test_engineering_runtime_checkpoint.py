from core.engineering.engineering_runtime_checkpoint import *
def test_checkpoint_chain():
 s={"session_id":"s","request_fingerprint":"r","workspace_id":"w","workspace_root_fingerprint":"f"}; a=build_engineering_runtime_checkpoint(s,{"phase":"request_received"}); b=build_engineering_runtime_checkpoint(s,{"phase":"session_admitted"},a); assert validate_checkpoint_chain([a,b])==[]
