from core.engineering.engineering_runtime_session_store import *
def test_atomic_canonical_store(tmp_path):
 write_session_artifact(tmp_path,"session-1","request.json",{"b":2,"a":1}); assert read_session_artifact(tmp_path,"session-1","request.json")=={"a":1,"b":2}
